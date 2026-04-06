from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from cortexpilot_orch.contract.validator import ContractValidator, resolve_agent_registry_path
from cortexpilot_orch.store.run_store import RunStore


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def safe_artifact_path(uri: str, repo_root: Path) -> Path | None:
    if not isinstance(uri, str) or not uri.strip():
        return None
    candidate = Path(uri).expanduser()
    if not candidate.is_absolute():
        candidate = (repo_root / candidate).resolve()
    else:
        candidate = candidate.resolve()
    runtime_root = Path(os.getenv("CORTEXPILOT_RUNTIME_ROOT", repo_root / ".runtime-cache/cortexpilot")).resolve()
    if is_within(candidate, repo_root) or is_within(candidate, runtime_root):
        return candidate
    return None


def artifact_items(contract: dict[str, Any]) -> list[dict[str, Any]]:
    inputs = contract.get("inputs")
    if not isinstance(inputs, dict):
        return []
    artifacts = inputs.get("artifacts", [])
    if not isinstance(artifacts, list):
        return []
    return [item for item in artifacts if isinstance(item, dict)]


def load_json_artifact(artifact: dict[str, Any], repo_root: Path) -> tuple[object | None, str | None, Path | None]:
    uri = str(artifact.get("uri", "")).strip()
    path = safe_artifact_path(uri, repo_root)
    if path is None or not path.exists():
        return None, "artifact path invalid", None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, f"artifact json invalid: {exc}", path
    return payload, None, path


def load_agent_registry(repo_root: Path, schema_root: Path) -> tuple[dict[str, Any] | None, str | None]:
    path = resolve_agent_registry_path(repo_root)
    if not path.exists():
        return None, f"agent registry missing: {path}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, f"agent registry invalid: {exc}"
    try:
        ContractValidator(schema_root=schema_root).validate_report(payload, "agent_registry.v1.json")
    except Exception as exc:  # noqa: BLE001
        return None, f"agent registry schema invalid: {exc}"
    return payload, None


def validate_assigned_agent(registry: dict[str, Any], assigned_agent: dict[str, Any]) -> tuple[bool, str]:
    agents = registry.get("agents", [])
    if not isinstance(agents, list):
        return False, "agent registry invalid agents list"
    target_id = str(assigned_agent.get("agent_id", "")).strip()
    target_role = str(assigned_agent.get("role", "")).strip()
    for item in agents:
        if not isinstance(item, dict):
            continue
        if str(item.get("agent_id", "")).strip() != target_id:
            continue
        if str(item.get("role", "")).strip() != target_role:
            continue
        return True, ""
    return False, "assigned agent not registered"


def collect_patch_artifacts(
    artifacts: object,
    repo_root: Path,
    worktree_path: Path,
) -> list[Path]:
    if not isinstance(artifacts, list):
        return []
    repo_root = repo_root.resolve()
    worktree_root = worktree_path.resolve()
    patch_paths: list[Path] = []
    for item in artifacts:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "") or "")
        uri = str(item.get("uri", "") or "")
        rel_path = str(item.get("path", "") or "")
        candidate = uri or rel_path or name
        if not candidate or not candidate.endswith(".diff"):
            continue
        path = Path(candidate)
        if path.is_absolute():
            if path.exists():
                patch_paths.append(path)
            continue
        for base in (repo_root, worktree_root):
            resolved = (base / path).resolve()
            try:
                if not resolved.is_relative_to(base):
                    continue
            except AttributeError:
                if not str(resolved).startswith(str(base)):
                    continue
            if resolved.exists():
                patch_paths.append(resolved)
                break
    return patch_paths


def should_apply_dependency_patches(contract: dict[str, Any]) -> bool:
    assigned = contract.get("assigned_agent")
    if isinstance(assigned, dict):
        role = str(assigned.get("role", "")).strip().upper()
        if role in {"REVIEWER", "TEST_RUNNER"}:
            return True
    task_type = str(contract.get("task_type", "")).strip().upper()
    return task_type in {"REVIEW", "TEST"}


def apply_dependency_patches(
    worktree_path: Path,
    patch_paths: list[Path],
    store: RunStore,
    run_id: str,
) -> bool:
    if not patch_paths:
        return True
    for patch_path in patch_paths:
        if patch_path.exists() and patch_path.stat().st_size == 0:
            store.append_event(
                run_id,
                {
                    "level": "INFO",
                    "event": "DEPENDENCY_PATCH_SKIPPED",
                    "run_id": run_id,
                    "meta": {"patch": str(patch_path), "reason": "empty_patch"},
                },
            )
            continue
        try:
            subprocess.run(
                ["git", "apply", "--whitespace=nowarn", str(patch_path)],
                cwd=worktree_path,
                check=True,
                capture_output=True,
                text=True,
            )
            store.append_event(
                run_id,
                {
                    "level": "INFO",
                    "event": "DEPENDENCY_PATCH_APPLIED",
                    "run_id": run_id,
                    "meta": {"patch": str(patch_path)},
                },
            )
        except subprocess.CalledProcessError as exc:
            store.append_event(
                run_id,
                {
                    "level": "ERROR",
                    "event": "DEPENDENCY_PATCH_FAILED",
                    "run_id": run_id,
                    "meta": {
                        "patch": str(patch_path),
                        "stdout": (exc.stdout or "")[:2000],
                        "stderr": (exc.stderr or "")[:2000],
                    },
                },
            )
            return False
    return True


def load_search_requests(
    contract: dict[str, Any],
    repo_root: Path,
    schema_root: Path,
) -> tuple[dict[str, Any] | None, str | None]:
    names = {"search_requests.json", "search_queries.json"}
    for artifact in artifact_items(contract):
        name = str(artifact.get("name", "")).strip()
        if name not in names:
            continue
        payload, error, _path = load_json_artifact(artifact, repo_root)
        if error:
            return None, error
        if isinstance(payload, list):
            queries = [str(item).strip() for item in payload if str(item).strip()]
            if not queries:
                return None, "search queries empty"
            normalized = {
                "queries": queries,
                "repeat": 2,
                "parallel": 2,
                "providers": ["chatgpt_web", "grok_web"],
                "verify": {"providers": ["chatgpt_web", "grok_web"], "repeat": 2},
                "verify_ai": {"enabled": True},
            }
            try:
                ContractValidator(schema_root=schema_root).validate_report(normalized, "search_requests.v1.json")
            except Exception as exc:  # noqa: BLE001
                return None, f"search requests schema invalid: {exc}"
            return normalized, None
        if isinstance(payload, dict):
            raw_queries = payload.get("queries") or payload.get("query") or []
            if isinstance(raw_queries, str):
                raw_queries = [raw_queries]
            if not isinstance(raw_queries, list):
                return None, "search queries invalid"
            queries = [str(item).strip() for item in raw_queries if str(item).strip()]
            if not queries:
                return None, "search queries empty"
            repeat = payload.get("repeat", 2)
            parallel = payload.get("parallel", 2)
            providers = payload.get("providers") or payload.get("provider") or []
            if isinstance(providers, str):
                providers = [providers]
            if not isinstance(providers, list):
                return None, "search providers invalid"
            providers = [str(item).strip() for item in providers if str(item).strip()]
            if not providers:
                providers = ["chatgpt_web", "grok_web"]
            verify = payload.get("verify") or {}
            if not isinstance(verify, dict):
                return None, "search verify config invalid"
            verify_providers = verify.get("providers") or verify.get("provider") or []
            if isinstance(verify_providers, str):
                verify_providers = [verify_providers]
            if not isinstance(verify_providers, list):
                return None, "search verify providers invalid"
            verify_providers = [str(item).strip() for item in verify_providers if str(item).strip()]
            if not verify_providers:
                verify_providers = providers
            verify_repeat = verify.get("repeat", 2)
            try:
                repeat = max(1, int(repeat))
            except (TypeError, ValueError):
                repeat = 2
            try:
                parallel = max(1, int(parallel))
            except (TypeError, ValueError):
                parallel = 2
            try:
                verify_repeat = max(1, int(verify_repeat))
            except (TypeError, ValueError):
                verify_repeat = 2
            normalized = {
                "queries": queries,
                "repeat": repeat,
                "parallel": parallel,
                "providers": providers,
                "verify": {"providers": verify_providers, "repeat": verify_repeat},
                "verify_ai": payload.get("verify_ai") if isinstance(payload.get("verify_ai"), dict) else {"enabled": True},
            }
            task_template = str(payload.get("task_template") or "").strip().lower()
            if task_template:
                normalized["task_template"] = task_template
            template_payload = payload.get("template_payload")
            if isinstance(template_payload, dict) and template_payload:
                normalized["template_payload"] = template_payload
            browser_policy = payload.get("browser_policy")
            if isinstance(browser_policy, dict):
                normalized["browser_policy"] = browser_policy
            try:
                ContractValidator(schema_root=schema_root).validate_report(normalized, "search_requests.v1.json")
            except Exception as exc:  # noqa: BLE001
                return None, f"search requests schema invalid: {exc}"
            return normalized, None
        return None, "search requests payload invalid"
    return None, None


def load_browser_tasks(
    contract: dict[str, Any],
    repo_root: Path,
    schema_root: Path,
) -> tuple[dict[str, Any] | None, str | None]:
    names = {"browser_tasks.json", "browser_requests.json"}
    for artifact in artifact_items(contract):
        name = str(artifact.get("name", "")).strip()
        if name not in names:
            continue
        payload, error, _path = load_json_artifact(artifact, repo_root)
        if error:
            return None, error
        tasks: list[dict[str, Any]] = []
        headless = None
        if isinstance(payload, dict):
            headless = payload.get("headless")
            raw_tasks = payload.get("tasks", [])
        else:
            raw_tasks = payload
        if not isinstance(raw_tasks, list):
            return None, "browser tasks invalid"
        for item in raw_tasks:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            if not isinstance(url, str) or not url.strip():
                continue
            script = item.get("script", "")
            script = script if isinstance(script, str) else ""
            task_payload = {"url": url.strip(), "script": script}
            browser_policy = item.get("browser_policy")
            if isinstance(browser_policy, dict):
                task_payload["browser_policy"] = browser_policy
            tasks.append(task_payload)
        if not tasks:
            return None, "browser tasks empty"
        normalized: dict[str, Any] = {"tasks": tasks}
        if isinstance(headless, bool):
            normalized["headless"] = headless
        task_template = str(payload.get("task_template") or "").strip().lower() if isinstance(payload, dict) else ""
        if task_template:
            normalized["task_template"] = task_template
        template_payload = payload.get("template_payload") if isinstance(payload, dict) else None
        if isinstance(template_payload, dict) and template_payload:
            normalized["template_payload"] = template_payload
        try:
            ContractValidator(schema_root=schema_root).validate_report(normalized, "browser_tasks.v1.json")
        except Exception as exc:  # noqa: BLE001
            return None, f"browser tasks schema invalid: {exc}"
        return normalized, None
    return None, None


def load_tampermonkey_tasks(
    contract: dict[str, Any],
    repo_root: Path,
    schema_root: Path,
) -> tuple[dict[str, Any] | None, str | None]:
    names = {"tampermonkey_tasks.json", "tampermonkey_output.json"}
    for artifact in artifact_items(contract):
        name = str(artifact.get("name", "")).strip()
        if name not in names:
            continue
        payload, error, _path = load_json_artifact(artifact, repo_root)
        if error:
            return None, error
        if isinstance(payload, list):
            payload = {"tasks": payload}
        if isinstance(payload, dict):
            try:
                ContractValidator(schema_root=schema_root).validate_report(payload, "tampermonkey_tasks.v1.json")
            except Exception as exc:  # noqa: BLE001
                return None, f"tampermonkey tasks schema invalid: {exc}"
        tasks: list[dict[str, Any]] = []
        if isinstance(payload, dict):
            raw_tasks = payload.get("tasks", [])
        else:
            raw_tasks = payload
        if not isinstance(raw_tasks, list):
            return None, "tampermonkey tasks invalid"
        for item in raw_tasks:
            if not isinstance(item, dict):
                continue
            script = item.get("script") or item.get("script_name") or item.get("name")
            raw_output = item.get("raw_output", "")
            parsed = item.get("parsed")
            url = item.get("url")
            script_content = item.get("script_content")
            if not isinstance(script, str) or not script.strip():
                continue
            raw_output = raw_output if isinstance(raw_output, str) else ""
            if not raw_output and (not isinstance(script_content, str) or not script_content.strip()):
                continue
            task_payload = {
                "script": script.strip(),
                "raw_output": raw_output,
                "parsed": parsed,
                "url": url if isinstance(url, str) else "",
                "script_content": script_content if isinstance(script_content, str) else "",
            }
            browser_policy = item.get("browser_policy")
            if isinstance(browser_policy, dict):
                task_payload["browser_policy"] = browser_policy
            tasks.append(task_payload)
        if not tasks:
            return None, "tampermonkey tasks empty"
        return {"tasks": tasks}, None
    return None, None


def load_sampling_requests(
    contract: dict[str, Any],
    repo_root: Path,
) -> tuple[dict[str, Any] | None, str | None]:
    tool_aliases = {"open-interpreter": "open_interpreter"}
    allowed_tools = {"sampling", "aider", "continue", "open_interpreter"}

    def normalize_tool(raw_tool: object, *, default: str = "sampling") -> tuple[str | None, str | None]:
        if raw_tool is None:
            return default, None
        if not isinstance(raw_tool, str):
            return None, "sampling requests invalid tool"
        tool_name = raw_tool.strip().lower()
        if not tool_name:
            return None, "sampling requests empty tool"
        normalized = tool_aliases.get(tool_name, tool_name)
        if normalized not in allowed_tools:
            return None, "sampling requests invalid tool"
        return normalized, None

    names = {"sampling_requests.json", "sampling_tasks.json"}
    for artifact in artifact_items(contract):
        name = str(artifact.get("name", "")).strip()
        if name not in names:
            continue
        payload, error, _path = load_json_artifact(artifact, repo_root)
        if error:
            return None, error
        requests: list[dict[str, Any]] = []
        requested_tools: list[str] = []

        def add_tool(tool_name: str) -> None:
            if tool_name not in requested_tools:
                requested_tools.append(tool_name)

        if isinstance(payload, dict):
            raw_items = payload.get("requests", payload.get("tasks", []))
        else:
            raw_items = payload
        if not isinstance(raw_items, list):
            return None, "sampling requests invalid"
        for item in raw_items:
            if isinstance(item, str) and item.strip():
                normalized_tool, tool_error = normalize_tool(None)
                if tool_error:
                    return None, tool_error
                add_tool(normalized_tool)
                requests.append({"input": item.strip()})
                continue
            if not isinstance(item, dict):
                continue
            raw_input = item.get("input") or item.get("prompt") or ""
            if not isinstance(raw_input, str) or not raw_input.strip():
                continue
            normalized_tool, tool_error = normalize_tool(item.get("tool") if "tool" in item else None)
            if tool_error:
                return None, tool_error
            add_tool(normalized_tool)
            request_payload = {
                "id": str(item.get("id", "")).strip(),
                "input": raw_input.strip(),
                "model": item.get("model"),
            }
            if "tool" in item:
                request_payload["tool"] = normalized_tool
            requests.append(request_payload)
        if not requests:
            return None, "sampling requests empty"
        return {"requests": requests, "requested_tools": requested_tools}, None
    return None, None
