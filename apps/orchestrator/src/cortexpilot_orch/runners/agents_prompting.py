from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ROLE_PROMPT_MAP = {
    "PM": "10_pm.md",
    "TECH_LEAD": "20_tech_lead.md",
    "SEARCHER": "30_searcher.md",
    "RESEARCHER": "30_searcher.md",
    "REVIEWER": "40_reviewer.md",
    "WORKER": "50_worker_core.md",
    "UI_UX": "51_worker_frontend.md",
    "FRONTEND": "51_worker_frontend.md",
    "BACKEND": "52_worker_backend.md",
    "AI": "53_worker_ai.md",
    "SECURITY": "54_worker_security.md",
    "INFRA": "55_worker_infra.md",
    "OPS": "55_worker_infra.md",
    "TEST": "56_worker_test.md",
    "TEST_RUNNER": "56_worker_test.md",
}

OUTPUT_SCHEMA_BY_ROLE: dict[str, str] = {
    "REVIEWER": "review_report.v1.json",
    "TEST_RUNNER": "test_report.v1.json",
    "TEST": "test_report.v1.json",
}


def resolve_roles_root(worktree_path: Path) -> Path | None:
    candidate = worktree_path.resolve() / "codex" / "roles"
    if candidate.exists():
        return candidate
    fallback = Path(__file__).resolve().parents[5] / "codex" / "roles"
    if fallback.exists():
        return fallback
    policy_fallback = Path(__file__).resolve().parents[5] / "policies" / "agents" / "codex" / "roles"
    if policy_fallback.exists():
        return policy_fallback
    return None


def _skip_role_prompt_requested() -> bool:
    raw = os.getenv("CORTEXPILOT_SKIP_ROLE_PROMPT", "").strip().lower()
    return raw in {"1", "true", "yes"}


def load_role_prompt(role: str, worktree_path: Path) -> str:
    if _skip_role_prompt_requested():
        return ""
    roles_root = resolve_roles_root(worktree_path)
    if not roles_root:
        return ""
    file_name = ROLE_PROMPT_MAP.get(role, ROLE_PROMPT_MAP.get("WORKER", ""))
    if not file_name:
        return ""
    prompt_path = roles_root / file_name
    if not prompt_path.exists():
        return ""
    return prompt_path.read_text(encoding="utf-8").strip()


def resolve_role_prompt_path(role: str, worktree_path: Path) -> Path | None:
    if _skip_role_prompt_requested():
        return None
    roles_root = resolve_roles_root(worktree_path)
    if not roles_root:
        return None
    file_name = ROLE_PROMPT_MAP.get(role, ROLE_PROMPT_MAP.get("WORKER", ""))
    if not file_name:
        return None
    prompt_path = roles_root / file_name
    if not prompt_path.exists():
        return None
    return prompt_path


def output_schema_name_for_role(role: str | None) -> str:
    role_key = (role or "").strip().upper()
    return OUTPUT_SCHEMA_BY_ROLE.get(role_key, "agent_task_result.v1.json")


def output_schema_role_key(role: str | None) -> str:
    role_key = (role or "").strip().lower()
    return role_key or "worker"


def resolve_output_schema_artifact(
    contract: dict[str, Any],
    role: str | None,
) -> dict[str, Any] | None:
    inputs = contract.get("inputs")
    if not isinstance(inputs, dict):
        return None
    artifacts = inputs.get("artifacts")
    if not isinstance(artifacts, list):
        return None
    role_key = output_schema_role_key(role)
    candidates = {f"output_schema.{role_key}", "output_schema"}
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        name = artifact.get("name")
        if isinstance(name, str) and name.strip().lower() in candidates:
            return artifact
    return None


def resolve_output_schema_path(
    contract: dict[str, Any],
    role: str | None,
    schema_root: Path,
) -> Path:
    artifact = resolve_output_schema_artifact(contract, role)
    if not artifact:
        raise RuntimeError("output_schema artifact missing")
    uri = artifact.get("uri")
    if not isinstance(uri, str) or not uri.strip():
        raise RuntimeError("output_schema artifact uri missing")
    raw = Path(uri)
    if raw.is_absolute():
        candidate = raw.resolve()
    else:
        base_root = schema_root.parent
        candidate = (base_root / raw).resolve()
    if not candidate.exists():
        raise RuntimeError(f"output_schema artifact not found: {candidate}")
    schema_root = schema_root.resolve()
    try:
        if not candidate.is_relative_to(schema_root):
            raise RuntimeError(
                f"output_schema must live under {schema_root}: {candidate}"
            )
    except AttributeError:
        if not str(candidate).startswith(str(schema_root)):
            raise RuntimeError(
                f"output_schema must live under {schema_root}: {candidate}"
            )
    expected_name = output_schema_name_for_role(role)
    if candidate.name != expected_name:
        raise RuntimeError(
            f"output_schema mismatch for role {role or 'WORKER'}: "
            f"expected {expected_name}, got {candidate.name}"
        )
    return candidate


def load_output_schema(schema_path: Path) -> str:
    if not schema_path.exists():
        return ""
    try:
        payload = json.loads(schema_path.read_text(encoding="utf-8"))
        return json.dumps(payload, ensure_ascii=False, indent=2)
    except Exception:  # noqa: BLE001
        return ""


def is_fixed_json_template(instruction: str) -> bool:
    markers = (
        "RETURN EXACTLY THIS JSON",
        "OUTPUT JSON ONLY",
        "Return exactly this JSON",
        "Output JSON only",
    )
    upper = instruction.upper()
    if any(marker in instruction for marker in markers):
        return True
    if "RETURN EXACTLY THIS JSON" in upper or "OUTPUT JSON ONLY" in upper:
        return True
    return False


def extract_fixed_json_payload(instruction: str) -> dict[str, Any] | None:
    if not isinstance(instruction, str):
        return None
    start = instruction.find("{")
    end = instruction.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    candidate = instruction[start : end + 1]
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def decorate_instruction(
    role: str,
    instruction: str,
    worktree_path: Path,
    schema_path: Path,
    schema_name: str,
) -> str:
    if is_fixed_json_template(instruction):
        return instruction
    role_prompt = load_role_prompt(role, worktree_path)
    inline_output_schema = os.getenv("CORTEXPILOT_INLINE_OUTPUT_SCHEMA", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    schema_text = load_output_schema(schema_path) if inline_output_schema else ""
    schema_block = ""
    if schema_text:
        schema_block = (
            f"Output must be valid JSON that matches the following JSON Schema ({schema_name}):\n"
            f"{schema_text}\n"
        )
    if not role_prompt:
        return (
            f"{schema_block}"
            f"Output JSON only. The output must conform to {schema_name}.\n"
            "Do not include any extra text.\n\n"
            f"Task:\n{instruction}"
        )
    return (
        f"{role_prompt}\n\n"
        f"{schema_block}"
        f"Output JSON only. The output must conform to {schema_name}.\n"
        "Do not include any extra text.\n\n"
        f"Task:\n{instruction}"
    )


def build_codex_payload(contract: dict[str, Any], instruction: str, worktree_path: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "prompt": instruction,
        "cwd": str(worktree_path.resolve()),
    }
    tool_permissions = contract.get("tool_permissions")
    if isinstance(tool_permissions, dict):
        filesystem = tool_permissions.get("filesystem")
        if filesystem in {"read-only", "workspace-write"}:
            payload["sandbox"] = filesystem
        shell = tool_permissions.get("shell")
        if shell == "deny":
            payload["approval-policy"] = "never"
        elif shell in {"untrusted", "on-request", "never"}:
            payload["approval-policy"] = shell
    model = os.getenv("CORTEXPILOT_CODEX_MODEL", "").strip()
    if model:
        payload["model"] = model
    return payload


def agent_instructions(
    task_id: str,
    tool_name: str,
    codex_payload: dict[str, Any],
    force_exact_output: bool,
    output_schema_name: str,
) -> str:
    timebox_raw = os.getenv("CORTEXPILOT_CODEX_TIMEBOX_SEC", "").strip()
    timebox_note = ""
    if timebox_raw:
        timebox_note = (
            "\nTimebox: "
            f"{timebox_raw} seconds. "
            "If you are not done, stop and return the best partial results within the TaskResult JSON."
        )
    if force_exact_output:
        return (
            "You are a strict worker agent. "
            f"Call the MCP tool `{tool_name}` exactly once using the following JSON payload. "
            "After the tool finishes, output the tool response EXACTLY as-is. "
            "Do not wrap, summarize, or add any extra text. "
            "If the tool response is JSON, output that JSON verbatim.\n\n"
            f"{timebox_note}\n"
            f"task_id={task_id}\n"
            f"codex payload: {json.dumps(codex_payload, ensure_ascii=False)}"
        )
    return (
        "You are a strict worker agent. "
        f"Call the MCP tool `{tool_name}` exactly once using the following JSON payload. "
        f"After the tool finishes, output ONLY valid JSON that conforms to {output_schema_name}. "
        "If the tool response contains a threadId or sessionId, include them in the appropriate schema fields.\n\n"
        f"{timebox_note}\n"
        f"task_id={task_id}\n"
        f"codex payload: {json.dumps(codex_payload, ensure_ascii=False)}"
    )


def user_prompt(instruction: str, output_schema_name: str) -> str:
    return (
        "Execute the following task using the codex tool and return JSON only. "
        f"The output must conform to {output_schema_name}.\n\n"
        f"Task: {instruction}"
    )
