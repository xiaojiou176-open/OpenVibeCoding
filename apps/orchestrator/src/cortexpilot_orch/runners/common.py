from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from cortexpilot_orch.contract.validator import ContractValidator


def resolve_run_id(contract: dict[str, Any]) -> str:
    return (
        contract.get("run_id")
        or os.getenv("CORTEXPILOT_RUN_ID", "")
        or contract.get("task_id", "unknown")
    )


def dummy_result(contract: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": contract.get("task_id", "mock"),
        "status": "SUCCESS",
        "summary": "mock",
        "evidence_refs": {},
        "failure": None,
    }


def failure_result(
    contract: dict[str, Any],
    reason: str,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "task_id": contract.get("task_id", ""),
        "status": "FAILED",
        "summary": reason,
        "evidence_refs": evidence or {},
        "failure": {"message": reason},
    }


def normalize_status(value: Any, fallback: str) -> str:
    if not isinstance(value, str) or not value.strip():
        return fallback
    normalized = value.strip().upper()
    mapping = {
        "SUCCESS": "SUCCESS",
        "SUCCEEDED": "SUCCESS",
        "OK": "SUCCESS",
        "FAIL": "FAILED",
        "FAILED": "FAILED",
        "ERROR": "FAILED",
        "BLOCKED": "BLOCKED",
        "SKIPPED": "SKIPPED",
    }
    return mapping.get(normalized, fallback)


def build_evidence_refs(thread_id: str | None, session_id: str | None = None) -> dict[str, Any]:
    refs: dict[str, Any] = {}
    if thread_id:
        refs["thread_id"] = thread_id
        refs["codex_thread_id"] = thread_id
    if session_id:
        refs["session_id"] = session_id
        refs["codex_session_id"] = session_id
    return refs


def coerce_task_result(
    payload: dict[str, Any] | None,
    contract: dict[str, Any],
    evidence_refs: dict[str, Any] | None,
    fallback_status: str,
    failure_reason: str | None = None,
) -> dict[str, Any]:
    payload = payload or {}
    task_id = payload.get("task_id") or contract.get("task_id", "")
    summary = payload.get("summary") or payload.get("diff_summary") or ""
    if failure_reason:
        summary = failure_reason
    status = normalize_status(payload.get("status"), fallback_status)
    refs: dict[str, Any] = {}
    if isinstance(payload.get("evidence_refs"), dict):
        refs.update(payload.get("evidence_refs", {}))
    if evidence_refs:
        refs.update(evidence_refs)
    failure = payload.get("failure")
    if failure_reason and not isinstance(failure, dict):
        failure = {"message": failure_reason}
    result = {
        "task_id": task_id,
        "status": status,
        "summary": summary,
        "evidence_refs": refs,
        "failure": failure if failure_reason else failure or None,
    }
    contracts = payload.get("contracts")
    if isinstance(contracts, list):
        result["contracts"] = [item for item in contracts if isinstance(item, dict)]
    handoff_payload = payload.get("handoff_payload")
    if isinstance(handoff_payload, dict):
        result["handoff_payload"] = handoff_payload
    return result


def extract_instruction(contract: dict[str, Any]) -> str:
    inputs = contract.get("inputs")
    if isinstance(inputs, dict):
        spec = inputs.get("spec")
        if isinstance(spec, str) and spec.strip():
            return spec
    fallback = contract.get("instruction") or contract.get("objective") or ""
    return fallback


def extract_required_output(contract: dict[str, Any]) -> str | None:
    outputs = contract.get("required_outputs") or []
    if not outputs:
        return None
    first = outputs[0]
    if isinstance(first, dict):
        name = first.get("name")
        return name if isinstance(name, str) and name.strip() else None
    if isinstance(first, str):
        return first
    return None


def mcp_tool_allowed(contract: dict[str, Any], tool_name: str) -> bool:
    tool_permissions = contract.get("tool_permissions")
    if not isinstance(tool_permissions, dict):
        return False
    tools = tool_permissions.get("mcp_tools", [])
    if not isinstance(tools, list):
        return False
    return tool_name in {str(item).strip() for item in tools if str(item).strip()}


def resolve_assigned_agent(contract: dict[str, Any]) -> dict[str, Any]:
    assigned = contract.get("assigned_agent", {})
    return assigned if isinstance(assigned, dict) else {}


def resolve_assigned_thread_id(contract: dict[str, Any], field_name: str = "codex_thread_id") -> str | None:
    assigned = resolve_assigned_agent(contract)
    value = assigned.get(field_name)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def validate_contract_schema(
    contract: dict[str, Any],
    schema_path: Path,
    run_store: Any,
    run_id: str,
    validator_cls: Any | None = None,
) -> tuple[Path | None, dict[str, Any] | None]:
    resolved_schema_path = schema_path.resolve()
    if not resolved_schema_path.exists():
        return None, failure_result(contract, "schema path missing", {"schema_path": str(resolved_schema_path)})

    validator_type = validator_cls or ContractValidator
    validator = validator_type(schema_root=resolved_schema_path.parent)
    try:
        validator.validate_contract(contract)
    except Exception as exc:  # noqa: BLE001
        run_store.append_event(
            run_id,
            {
                "level": "ERROR",
                "event": "CONTRACT_SCHEMA_INVALID",
                "run_id": run_id,
                "meta": {"error": str(exc)},
            },
        )
        return None, failure_result(contract, "contract schema validation failed", {"error": str(exc)})

    return resolved_schema_path, None


def execute_mock_contract(
    contract: dict[str, Any],
    tool_permissions: dict[str, Any],
    instruction: str,
    worktree_path: Path,
    run_store: Any,
    run_id: str,
    event_name: str,
) -> dict[str, Any]:
    filesystem = str(tool_permissions.get("filesystem", "")).strip().lower()
    if filesystem == "read-only":
        run_store.append_event(
            run_id,
            {
                "level": "INFO",
                "event": event_name,
                "run_id": run_id,
                "meta": {
                    "path": "",
                    "instruction": instruction,
                    "read_only": True,
                    "note": "mock mode skips file writes under read-only sandbox",
                },
            },
        )
        return dummy_result(contract)

    rel_path = extract_required_output(contract) or "mock_output.txt"
    target = worktree_path / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("mock", encoding="utf-8")
    run_store.append_event(
        run_id,
        {
            "level": "INFO",
            "event": event_name,
            "run_id": run_id,
            "meta": {"path": str(target), "instruction": instruction},
        },
    )
    return dummy_result(contract)
