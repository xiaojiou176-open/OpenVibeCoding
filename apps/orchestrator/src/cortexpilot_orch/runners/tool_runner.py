from __future__ import annotations

import shutil
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cortexpilot_orch.gates.sampling_gate import is_sampling_tool, validate_sampling_policy
from cortexpilot_orch.runners.mcp_adapter_runtime import execute_mcp_adapter, normalize_adapter_tool
from cortexpilot_orch.store.run_store import RunStore

ROOT = Path(__file__).resolve().parents[5]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from tooling.browser.playwright_runner import BrowserRunner
from tooling.mcp import adapter as mcp_adapter
from tooling.search.search_engine import search_verify


def _run_artifacts_dir(store: RunStore, run_id: str) -> Path:
    run_dir = store._runs_root / run_id
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    return artifacts_dir


def _safe_slug(value: str) -> str:
    if not value:
        return "task"
    cleaned = []
    for ch in value:
        if ch.isalnum() or ch in {"-", "_"}:
            cleaned.append(ch)
        else:
            cleaned.append("_")
    slug = "".join(cleaned).strip("_")
    return slug[:40] or "task"


def _unique_artifact_dir(artifacts_root: Path, prefix: str, task_id: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    suffix = uuid.uuid4().hex[:8]
    slug = _safe_slug(task_id)
    path = artifacts_root / prefix / f"{slug}_{stamp}_{suffix}"
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---- Search artifacts sync ----
def _sync_search_artifacts(
    store: RunStore,
    run_id: str,
    query: str,
    provider: str | None,
    result: dict[str, Any],
) -> dict[str, Any]:
    meta = result.get("meta")
    if not isinstance(meta, dict):
        return result
    artifacts = meta.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        return result
    artifacts_root = _run_artifacts_dir(store, run_id)
    task_key = f"search_{provider or 'default'}_{_safe_slug(query)}"
    dest_dir = _unique_artifact_dir(artifacts_root, "search", task_key)
    copied: dict[str, str] = {}
    for name, src in artifacts.items():
        if not src:
            continue
        try:
            src_path = Path(str(src))
            if not src_path.exists() or not src_path.is_file():
                continue
            dest_path = dest_dir / src_path.name
            shutil.copy2(src_path, dest_path)
            copied[str(name)] = str(dest_path)
        except Exception:  # noqa: BLE001
            continue
    if copied:
        meta["artifacts_original"] = artifacts
        meta["artifacts"] = copied
        meta["artifacts_root"] = str(dest_dir)
        result["meta"] = meta
    return result


def _is_browser_policy_compat_error(exc: TypeError) -> bool:
    message = str(exc)
    return "unexpected keyword argument" in message and "browser_policy" in message


class ToolRunner:
    def __init__(self, run_id: str, store: RunStore | None = None) -> None:
        self._run_id = run_id
        self._store = store or RunStore()

    def _log_tool(self, payload: dict[str, Any]) -> None:
        entry = dict(payload or {})
        entry.setdefault("status", "ok")
        self._store.append_tool_call(self._run_id, entry)
        self._store.append_event(
            self._run_id,
            {
                "level": "INFO",
                "event": "TOOL_USED",
                "run_id": self._run_id,
                "meta": payload,
            },
        )

    def _log_failure(self, payload: dict[str, Any]) -> None:
        entry = dict(payload or {})
        entry.setdefault("status", "error")
        self._store.append_tool_call(self._run_id, entry)
        self._store.append_event(
            self._run_id,
            {
                "level": "ERROR",
                "event": "TOOL_FAILURE",
                "run_id": self._run_id,
                "meta": payload,
            },
        )

    def _append_policy_events(self, events: Any, source: str, task_id: str | None = None) -> None:
        if not isinstance(events, list):
            return
        for item in events:
            if not isinstance(item, dict):
                continue
            event_name = item.get("event")
            if not isinstance(event_name, str) or not event_name.strip():
                continue
            event_meta = {
                "source": source,
                **(item.get("meta") if isinstance(item.get("meta"), dict) else {}),
            }
            if isinstance(task_id, str) and task_id.strip():
                event_meta["task_id"] = task_id
            self._store.append_event(
                self._run_id,
                {
                    "level": item.get("level", "INFO"),
                    "event": event_name,
                    "run_id": self._run_id,
                    "meta": event_meta,
                },
            )

    def _append_policy_audit(
        self,
        policy_audit: dict[str, Any] | None,
        source: str,
        task_id: str | None = None,
    ) -> None:
        if not isinstance(policy_audit, dict):
            return
        self._append_policy_events(policy_audit.get("events"), source=source, task_id=task_id)

    def _resolve_task_id(
        self,
        explicit_task_id: str | None,
        *,
        default_task_id: str,
        contract: dict[str, Any] | None = None,
    ) -> str:
        if isinstance(explicit_task_id, str) and explicit_task_id.strip():
            return explicit_task_id.strip()
        if isinstance(contract, dict):
            contract_task_id = contract.get("task_id")
            if isinstance(contract_task_id, str) and contract_task_id.strip():
                return contract_task_id.strip()
        return default_task_id

    def run_browser(
        self,
        url: str,
        script_content: str,
        task_id: str | None = None,
        headless: bool | None = None,
        browser_policy: dict[str, Any] | None = None,
        policy_audit: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        artifacts_dir = _run_artifacts_dir(self._store, self._run_id)
        resolved_task_id = self._resolve_task_id(task_id, default_task_id="browser")
        task_key = resolved_task_id
        run_dir = _unique_artifact_dir(artifacts_dir, "browser", task_key)
        try:
            runner = BrowserRunner(run_dir, headless=headless, browser_policy=browser_policy)
        except TypeError as exc:
            if not _is_browser_policy_compat_error(exc):
                raise
            runner = BrowserRunner(run_dir, headless=headless)
        start = time.monotonic()
        self._append_policy_audit(policy_audit, source="browser", task_id=resolved_task_id)
        try:
            result = runner.run_script(script_content, url)
            self._append_policy_events(result.get("policy_events"), source="browser", task_id=resolved_task_id)
            payload = {
                "tool": "playwright",
                "task_id": resolved_task_id,
                "args": {"url": url},
                "duration_ms": result.get("duration_ms"),
                "artifacts": result.get("artifacts", {}),
                "mode": result.get("mode"),
            }
            if result.get("ok") is False:
                payload["error"] = result.get("error")
                self._log_failure(payload)
            else:
                self._log_tool(payload)
            return result
        except Exception as exc:  # noqa: BLE001
            payload = {
                "tool": "playwright",
                "task_id": resolved_task_id,
                "args": {"url": url},
                "duration_ms": int((time.monotonic() - start) * 1000),
                "error": str(exc),
            }
            self._log_failure(payload)
            return {"ok": False, "error": str(exc)}

    def run_search(
        self,
        query: str,
        provider: str | None = None,
        browser_policy: dict[str, Any] | None = None,
        policy_audit: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        start = time.monotonic()
        contract = self._store.read_active_contract(self._run_id)
        resolved_task_id = self._resolve_task_id(None, default_task_id="search", contract=contract)
        self._append_policy_audit(policy_audit, source="search", task_id=resolved_task_id)
        try:
            try:
                result = search_verify(query, provider=provider, browser_policy=browser_policy)
            except TypeError as exc:
                if not _is_browser_policy_compat_error(exc):
                    raise
                result = search_verify(query, provider=provider)
            result = _sync_search_artifacts(self._store, self._run_id, query, provider, result)
            if isinstance(result.get("meta"), dict):
                self._append_policy_events(
                    result["meta"].get("policy_events"),
                    source="search",
                    task_id=resolved_task_id,
                )
            payload = {
                "tool": "search",
                "task_id": resolved_task_id,
                "args": {"query": query, "provider": provider},
                "duration_ms": result.get("duration_ms"),
                "artifacts": result.get("meta", {}).get("artifacts", {}) if isinstance(result.get("meta"), dict) else {},
                "mode": result.get("mode"),
            }
            if result.get("ok") is False:
                payload["error"] = result.get("error")
                self._log_failure(payload)
            else:
                self._log_tool(payload)
            return result
        except Exception as exc:  # noqa: BLE001
            payload = {
                "tool": "search",
                "task_id": resolved_task_id,
                "args": {"query": query},
                "duration_ms": int((time.monotonic() - start) * 1000),
                "error": str(exc),
            }
            self._log_failure(payload)
            return {"ok": False, "error": str(exc)}

    def run_mcp(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        start = time.monotonic()
        try:
            requested_tool = str(tool_name).strip()
            requested_tool_normalized = requested_tool.lower()
            canonical_tool = normalize_adapter_tool(requested_tool_normalized) or requested_tool_normalized
            contract = self._store.read_active_contract(self._run_id)
            resolved_task_id = self._resolve_task_id(
                None,
                default_task_id=f"mcp_{_safe_slug(canonical_tool)}",
                contract=contract,
            )
            allowed_tools: list[str] = []
            if contract:
                permissions = contract.get("tool_permissions", {})
                allowed_tools = permissions.get("mcp_tools", []) if isinstance(permissions, dict) else []
            normalized_allowed_tools = {
                normalize_adapter_tool(str(item).strip().lower()) or str(item).strip().lower()
                for item in allowed_tools
                if str(item).strip()
            }

            if not normalized_allowed_tools or canonical_tool not in normalized_allowed_tools:
                denied_reason = "tool not allowed"
                self._store.append_event(
                    self._run_id,
                    {
                        "level": "ERROR",
                        "event": "MCP_TOOL_DENIED",
                        "run_id": self._run_id,
                        "meta": {
                            "tool": canonical_tool,
                            "requested_tool": requested_tool,
                            "task_id": resolved_task_id,
                            "reason": "tool not allowed",
                            "denied_reason": denied_reason,
                        },
                    },
                )
                denied_payload = {
                    "tool": "mcp",
                    "task_id": resolved_task_id,
                    "args": {"tool": canonical_tool, "requested_tool": requested_tool},
                    "duration_ms": int((time.monotonic() - start) * 1000),
                    "error": "mcp tool not allowed",
                    "reason": denied_reason,
                }
                self._log_failure(denied_payload)
                return {"ok": False, "error": "mcp tool not allowed", "reason": denied_reason}

            if is_sampling_tool(canonical_tool):
                sampling_gate = validate_sampling_policy(sorted(normalized_allowed_tools))
                sampling_ok = bool(sampling_gate.get("ok"))
                sampling_reason = sampling_gate.get("reason")
                if not isinstance(sampling_reason, str) or not sampling_reason.strip():
                    sampling_reason = "sampling blocked"
                sampling_meta = {
                    **sampling_gate,
                    "tool": canonical_tool,
                    "requested_tool": requested_tool,
                    "task_id": resolved_task_id,
                }
                if not sampling_ok:
                    sampling_meta["reason"] = sampling_reason
                self._store.append_event(
                    self._run_id,
                    {
                        "level": "INFO" if sampling_ok else "ERROR",
                        "event": "MCP_SAMPLING_GATE_RESULT",
                        "run_id": self._run_id,
                        "meta": sampling_meta,
                    },
                )
                if not sampling_ok:
                    self._log_failure(
                        {
                            "tool": "mcp",
                            "task_id": resolved_task_id,
                            "args": {"tool": canonical_tool, "requested_tool": requested_tool},
                            "duration_ms": int((time.monotonic() - start) * 1000),
                            "error": sampling_reason,
                            "reason": sampling_reason,
                        }
                    )
                    return {"ok": False, "error": sampling_reason, "reason": sampling_reason}
                self._store.append_event(
                    self._run_id,
                    {
                        "level": "INFO",
                        "event": "MCP_SAMPLING_REQUEST",
                        "run_id": self._run_id,
                        "meta": {
                            "tool": canonical_tool,
                            "requested_tool": requested_tool,
                            "payload": mcp_adapter.sanitize_mcp_payload(payload),
                            "task_id": resolved_task_id,
                        },
                    },
                )

            adapter_name = normalize_adapter_tool(canonical_tool)
            if adapter_name:
                mcp_adapter.record_mcp_call(self._run_id, canonical_tool, payload)
                result = execute_mcp_adapter(canonical_tool, payload, contract, repo_root=ROOT)
                log_payload = {
                    "tool": "mcp",
                    "task_id": resolved_task_id,
                    "args": {
                        "tool": canonical_tool,
                        "requested_tool": requested_tool,
                        "adapter": result.get("adapter"),
                        "command": result.get("command"),
                    },
                    "duration_ms": result.get("duration_ms", int((time.monotonic() - start) * 1000)),
                    "artifacts": {},
                    "exit_code": result.get("exit_code"),
                }
                if not result.get("ok"):
                    error_text = str(result.get("error", "")).strip() or "mcp adapter execution failed"
                    reason_text = str(result.get("reason", "")).strip() or error_text
                    log_payload["error"] = error_text
                    log_payload["reason"] = reason_text
                    self._log_failure(log_payload)
                    return {
                        **result,
                        "ok": False,
                        "error": error_text,
                        "reason": reason_text,
                    }
                self._log_tool(log_payload)
                return result

            mcp_adapter.record_mcp_call(self._run_id, canonical_tool, payload)
            reason = "non-adapter mcp execution is not supported"
            self._store.append_event(
                self._run_id,
                {
                    "level": "ERROR",
                    "event": "MCP_TOOL_EXECUTION_UNAVAILABLE",
                    "run_id": self._run_id,
                    "meta": {
                        "tool": canonical_tool,
                        "requested_tool": requested_tool,
                        "task_id": resolved_task_id,
                        "reason": reason,
                    },
                },
            )
            self._log_failure(
                {
                    "tool": "mcp",
                    "task_id": resolved_task_id,
                    "args": {"tool": canonical_tool, "requested_tool": requested_tool},
                    "duration_ms": int((time.monotonic() - start) * 1000),
                    "error": reason,
                    "reason": reason,
                }
            )
            return {"ok": False, "error": reason, "reason": reason}
        except Exception as exc:  # noqa: BLE001
            self._log_failure(
                {
                    "tool": "mcp",
                    "task_id": resolved_task_id if "resolved_task_id" in locals() else f"mcp_{_safe_slug(canonical_tool if 'canonical_tool' in locals() else str(tool_name))}",
                    "args": {
                        "tool": canonical_tool if "canonical_tool" in locals() else str(tool_name),
                        "requested_tool": requested_tool if "requested_tool" in locals() else str(tool_name),
                    },
                    "duration_ms": int((time.monotonic() - start) * 1000),
                    "error": str(exc),
                    "reason": str(exc),
                }
            )
            return {"ok": False, "error": str(exc), "reason": str(exc)}
