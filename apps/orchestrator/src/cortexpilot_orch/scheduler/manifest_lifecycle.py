from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from cortexpilot_orch.store.run_store import RunStore


def load_manifest(store: RunStore, run_id: str) -> dict[str, Any]:
    return store.read_manifest(run_id)


def write_manifest(store: RunStore, run_id: str, manifest: dict[str, Any]) -> None:
    store.write_manifest(run_id, manifest)


def _now_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_status(raw_status: Any) -> str:
    status = str(raw_status or "").strip().upper()
    return status if status else "UNKNOWN"


def _normalize_subgraph_capability(raw: dict[str, Any] | None, *, source: str) -> dict[str, Any]:
    payload = raw if isinstance(raw, dict) else {}
    enabled = bool(payload.get("enabled", False))
    strict_gate = bool(payload.get("strict_gate", payload.get("enforce", False)))
    fallback_to_legacy = bool(payload.get("fallback_to_legacy", True))
    return {
        "enabled": enabled,
        "strict_gate": strict_gate if enabled else False,
        "fallback_to_legacy": fallback_to_legacy,
        "source": source,
    }


def _read_task_chain_subgraph_capability(task_chain: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(task_chain, dict):
        return None
    strategy = task_chain.get("strategy") if isinstance(task_chain.get("strategy"), dict) else {}
    lifecycle_cfg = strategy.get("lifecycle") if isinstance(strategy.get("lifecycle"), dict) else {}
    raw = lifecycle_cfg.get("subgraph")
    return raw if isinstance(raw, dict) else None


def resolve_subgraph_capability(
    *,
    task_chain: dict[str, Any] | None = None,
    capability_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if isinstance(capability_override, dict):
        return _normalize_subgraph_capability(capability_override, source="override")

    from_task_chain = _read_task_chain_subgraph_capability(task_chain)
    if isinstance(from_task_chain, dict):
        return _normalize_subgraph_capability(from_task_chain, source="task_chain")

    return _normalize_subgraph_capability(None, source="default")


def _append_event_if_supported(store: RunStore, run_id: str, payload: dict[str, Any]) -> None:
    append_event = getattr(store, "append_event", None)
    if callable(append_event):
        append_event(run_id, payload)


def _write_report_if_supported(store: RunStore, run_id: str, name: str, payload: dict[str, Any]) -> None:
    write_report = getattr(store, "write_report", None)
    if callable(write_report):
        write_report(run_id, name, payload)


def evaluate_subgraph_lifecycle_gate(
    store: RunStore,
    run_id: str,
    manifest_snapshot: dict[str, Any],
    *,
    execution_meta: dict[str, Any] | None = None,
    task_chain: dict[str, Any] | None = None,
    capability_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    capability = resolve_subgraph_capability(task_chain=task_chain, capability_override=capability_override)
    meta = dict(execution_meta) if isinstance(execution_meta, dict) else {}

    status = _normalize_status(meta.get("status"))
    failure_reason = str(meta.get("failure_reason") or meta.get("error") or "").strip()
    failed_statuses = {"FAIL", "FAILED", "FAILURE", "ERROR", "TIMEOUT", "BLOCKED", "CANCELLED"}
    failed = status in failed_statuses

    gate_blocked = bool(capability["enabled"] and capability["strict_gate"] and failed)
    fallback_applied = bool(
        capability["enabled"]
        and failed
        and not gate_blocked
        and capability["fallback_to_legacy"]
    )

    rollback_applied = False
    manifest_after_status = _normalize_status(manifest_snapshot.get("status"))

    if gate_blocked:
        blocked_manifest = dict(manifest_snapshot)
        blocked_manifest["status"] = "FAILURE"
        if failure_reason:
            blocked_manifest["failure_reason"] = f"subgraph lifecycle gate blocked: {failure_reason}"
        write_manifest(store, run_id, blocked_manifest)
        manifest_after_status = "FAILURE"
        rollback_applied = False
    elif fallback_applied:
        rollback_manifest = meta.get("rollback_manifest")
        manifest_to_restore = (
            dict(rollback_manifest)
            if isinstance(rollback_manifest, dict)
            else dict(manifest_snapshot)
        )
        write_manifest(store, run_id, manifest_to_restore)
        rollback_applied = True
        manifest_after_status = _normalize_status(manifest_to_restore.get("status"))

    decision = {
        "enabled": capability["enabled"],
        "strict_gate": capability["strict_gate"],
        "fallback_to_legacy": capability["fallback_to_legacy"],
        "status": status,
        "failed": failed,
        "gate_blocked": gate_blocked,
        "fallback_applied": fallback_applied,
        "rollback_applied": rollback_applied,
        "compatibility_mode": "legacy" if not capability["enabled"] else "subgraph",
        "failure_reason": failure_reason,
    }

    audit_payload = {
        "timestamp": _now_ts(),
        "run_id": run_id,
        "scope": "subgraph_lifecycle",
        "capability": capability,
        "execution": {
            "chain_id": str(meta.get("chain_id", "")).strip(),
            "step_name": str(meta.get("step_name", "")).strip(),
            "step_index": meta.get("step_index"),
            "subgraph_id": str(meta.get("subgraph_id", "")).strip(),
            "subgraph_run_id": str(meta.get("subgraph_run_id", "")).strip(),
            "attempt": meta.get("attempt"),
            "status": status,
            "error": failure_reason,
        },
        "manifest": {
            "before_status": _normalize_status(manifest_snapshot.get("status")),
            "after_status": manifest_after_status,
        },
        "decision": decision,
    }
    _write_report_if_supported(store, run_id, "subgraph_lifecycle", audit_payload)

    transition_level = "ERROR" if gate_blocked else "WARN" if failed else "INFO"
    _append_event_if_supported(
        store,
        run_id,
        {
            "level": transition_level,
            "event": "STATE_TRANSITION",
            "run_id": run_id,
            "meta": {
                "scope": "subgraph_lifecycle",
                "from_status": audit_payload["manifest"]["before_status"],
                "to_status": audit_payload["manifest"]["after_status"],
                "gate_blocked": gate_blocked,
                "fallback_applied": fallback_applied,
                "rollback_applied": rollback_applied,
                "strict_gate": capability["strict_gate"],
                "enabled": capability["enabled"],
                "status": status,
            },
        },
    )

    if fallback_applied and rollback_applied:
        _append_event_if_supported(
            store,
            run_id,
            {
                "level": "WARN",
                "event": "ROLLBACK_APPLIED",
                "run_id": run_id,
                "meta": {
                    "scope": "subgraph_lifecycle",
                    "reason": failure_reason or "subgraph_failed_fallback_to_legacy",
                    "status": status,
                },
            },
        )

    if gate_blocked:
        _append_event_if_supported(
            store,
            run_id,
            {
                "level": "ERROR",
                "event": "gate_failed",
                "run_id": run_id,
                "meta": {
                    "gate": "subgraph_lifecycle",
                    "reason": failure_reason or "subgraph_failed_under_strict_gate",
                    "status": status,
                },
            },
        )

    return decision
