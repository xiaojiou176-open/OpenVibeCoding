from __future__ import annotations

import hashlib
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cortexpilot_orch.store.run_store import RunStore

TASK_RESULT_ROLES = {
    "PM",
    "TECH_LEAD",
    "WORKER",
    "REVIEWER",
    "TEST_RUNNER",
    "TEST",
    "SEARCHER",
    "RESEARCHER",
    "ORCHESTRATOR",
    "UI_UX",
    "FRONTEND",
    "BACKEND",
    "AI",
    "SECURITY",
    "INFRA",
    "OPS",
}

MANIFEST_TASK_ROLES = {
    "PM",
    "TECH_LEAD",
    "WORKER",
    "REVIEWER",
    "TEST_RUNNER",
    "TEST",
    "SEARCHER",
    "RESEARCHER",
    "UI_UX",
    "FRONTEND",
    "BACKEND",
    "AI",
    "SECURITY",
    "INFRA",
    "OPS",
}

FILESYSTEM_ORDER = {
    "read-only": 0,
    "workspace-write": 1,
    "danger-full-access": 2,
}

SHELL_ORDER = {
    "never": 0,
    "on-failure": 1,
    "untrusted": 2,
    "on-request": 3,
}

NETWORK_ORDER = {
    "deny": 0,
    "on-request": 1,
    "allow": 2,
}


def now_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_text(path.read_text(encoding="utf-8"))


def trace_url(trace_id: str, run_id: str) -> str:
    template = os.getenv("CORTEXPILOT_TRACE_URL_TEMPLATE", "").strip()
    if template:
        try:
            return template.format(trace_id=trace_id, run_id=run_id)
        except KeyError:
            return ""
    base = os.getenv("CORTEXPILOT_TRACE_BASE_URL", "").strip()
    if not base:
        return ""
    return f"{base.rstrip('/')}/{trace_id}"


def normalize_role(role: str, allowed: set[str], fallback: str) -> str:
    normalized = str(role or "").strip().upper()
    return normalized if normalized in allowed else fallback


def task_result_role(agent: dict[str, Any] | None) -> str:
    role = agent.get("role") if isinstance(agent, dict) else ""
    return normalize_role(role, TASK_RESULT_ROLES, "ORCHESTRATOR")


def manifest_task_role(agent: dict[str, Any] | None) -> str:
    role = agent.get("role") if isinstance(agent, dict) else ""
    return normalize_role(role, MANIFEST_TASK_ROLES, "WORKER")


def ensure_text_file(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(content, encoding="utf-8")


def artifact_ref(name: str, rel_path: str, content: str, media_type: str = "text/plain") -> dict[str, Any]:
    return {
        "name": name,
        "path": rel_path,
        "sha256": sha256_text(content),
        "media_type": media_type,
        "size_bytes": len(content.encode("utf-8")),
    }


def artifact_ref_from_path(name: str, run_dir: Path, rel_path: str, media_type: str = "text/plain") -> dict[str, Any]:
    path = run_dir / rel_path
    if not path.exists():
        ensure_text_file(path)
    content = path.read_text(encoding="utf-8")
    return artifact_ref(name, rel_path, content, media_type=media_type)


def artifact_ref_from_hash(
    name: str,
    rel_path: str,
    sha256: str,
    size_bytes: int,
    media_type: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": name,
        "path": rel_path,
        "sha256": sha256,
        "size_bytes": size_bytes,
    }
    if media_type:
        payload["media_type"] = media_type
    return payload


def guess_media_type(path: str) -> str | None:
    if path.endswith(".json"):
        return "application/json"
    if path.endswith(".jsonl"):
        return "application/x-ndjson"
    if path.endswith(".diff"):
        return "text/x-diff"
    if path.endswith(".txt"):
        return "text/plain"
    if path.endswith(".log"):
        return "text/plain"
    return None


def artifact_refs_from_hashes(run_dir: Path, hashes: dict[str, str]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for rel_path, sha in sorted(hashes.items()):
        path = run_dir / rel_path
        size_bytes = path.stat().st_size if path.exists() else 0
        media_type = guess_media_type(rel_path)
        refs.append(artifact_ref_from_hash(rel_path, rel_path, sha, size_bytes, media_type))
    return refs


def detect_agents_overrides(repo_root: Path) -> list[str]:
    paths: list[str] = []
    repo_override = repo_root / "AGENTS.override.md"
    if repo_override.exists():
        paths.append(str(repo_override))
    codex_home = Path(os.getenv("CODEX_HOME", Path.home() / ".codex"))
    home_override = codex_home / "AGENTS.override.md"
    if home_override.exists():
        paths.append(str(home_override))
    return paths


def per_run_codex_home_enabled() -> bool:
    raw = os.getenv("CORTEXPILOT_CODEX_HOME_PER_RUN", "").strip().lower()
    return raw in {"1", "true", "yes"}


def materialize_codex_home(base_home: Path, run_id: str, runtime_root: Path) -> Path:
    target = runtime_root / "codex-homes" / run_id
    target.mkdir(parents=True, exist_ok=True)
    for name in ("config.toml", "requirements.toml"):
        src = base_home / name
        if src.exists():
            shutil.copy2(src, target / name)
    return target


def gate_result(passed: bool, violations: list[str] | None = None) -> dict[str, Any]:
    return {"passed": passed, "violations": violations or []}


def append_gate_failed(
    store: RunStore,
    run_id: str,
    gate: str,
    reason: str,
    schema: str | None = None,
    path: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    context = {"gate": gate, "reason": reason}
    if schema:
        context["schema"] = schema
    if path:
        context["path"] = path
    if extra:
        context.update(extra)
    store.append_event(
        run_id,
        {
            "level": "ERROR",
            "event": "gate_failed",
            "run_id": run_id,
            "meta": context,
        },
    )


def append_policy_violation(
    store: RunStore,
    run_id: str,
    reason: str,
    path: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    context = {"reason": reason}
    if path:
        context["path"] = path
    if extra:
        context.update(extra)
    store.append_event(
        run_id,
        {
            "level": "ERROR",
            "event": "policy_violation",
            "run_id": run_id,
            "meta": context,
        },
    )


def build_policy_gate(
    integrated_gate: dict[str, Any] | None,
    network_gate: dict[str, Any] | None,
    mcp_gate: dict[str, Any] | None,
    sampling_gate: dict[str, Any] | None,
    tool_gate: dict[str, Any] | None,
    human_approval_required: bool,
    human_approved: bool | None,
) -> dict[str, Any]:
    violations: list[str] = []
    if integrated_gate and not integrated_gate.get("ok", True):
        violations.append("integrated_gate")
    if network_gate and not network_gate.get("ok", True):
        violations.append("network_gate")
    if mcp_gate and not mcp_gate.get("ok", True):
        violations.append("mcp_gate")
    if sampling_gate and not sampling_gate.get("ok", True):
        violations.append("sampling_gate")
    if tool_gate and not tool_gate.get("ok", True):
        violations.append("tool_gate")
    if human_approval_required and human_approved is False:
        violations.append("human_approval_required")
    return gate_result(len(violations) == 0, violations)


def extract_user_request(contract: dict[str, Any]) -> str:
    inputs = contract.get("inputs")
    if isinstance(inputs, dict):
        spec = inputs.get("spec")
        if isinstance(spec, str) and spec.strip():
            return spec.strip()
    return ""


def extract_evidence_refs(task_result: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(task_result, dict):
        return {}
    refs = task_result.get("evidence_refs")
    return refs if isinstance(refs, dict) else {}
