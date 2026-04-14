from __future__ import annotations

import time
from typing import Any, Callable

from openvibecoding_orch.contract.validator import ContractValidator
from openvibecoding_orch.store.run_store import RunStore


FailureResult = Callable[[str, dict[str, Any] | None], dict[str, Any]]
TranscriptRecorder = Callable[[dict[str, Any]], None]


def finalize_agents_run_result(
    *,
    module: Any,
    store: RunStore,
    run_id: str,
    task_id: str,
    contract: dict[str, Any],
    result: Any,
    start_monotonic: float,
    tool_name: str,
    tool_payload: dict[str, Any],
    tool_config: dict[str, Any],
    shell_policy: str,
    output_schema_name: str,
    validator: ContractValidator,
    handoff_refs: dict[str, Any],
    record_transcript: TranscriptRecorder,
    flush_transcript: Callable[[], None],
    failure_result: FailureResult,
) -> dict[str, Any]:
    snapshot = module._result_snapshot(result)
    structured = module._extract_structured_content(snapshot)
    structured_thread_id = module._extract_structured_thread_id(structured)
    snapshot_thread_id = structured_thread_id or module._extract_thread_id(snapshot)
    if structured is not None or snapshot_thread_id:
        store.append_event(
            run_id,
            module._build_tool_result_event(
                run_id=run_id,
                tool_name=tool_name,
                snapshot_thread_id=snapshot_thread_id,
                structured=structured,
                safe_json_value=module._safe_json_value,
            ),
        )

    if shell_policy in {"deny", "never"} and module._contains_shell_request(snapshot):
        policy_label = shell_policy or "deny"
        store.append_event(
            run_id,
            {
                "level": "ERROR",
                "event": "policy_violation",
                "run_id": run_id,
                "meta": {"reason": f"shell request detected under shell={policy_label}"},
            },
        )
        record_transcript({"kind": "policy_violation", "text": f"shell request detected under shell={policy_label}"})
        flush_transcript()
        return failure_result(f"shell request detected under {policy_label} policy", None)

    final_output = getattr(result, "final_output", None)
    payload, output_error, transcript_items = module._normalize_final_output(final_output)
    for item in transcript_items:
        record_transcript(item)
    if output_error:
        if output_error.get("emit_tool_call"):
            store.append_tool_call(
                run_id,
                module._build_tool_call(
                    tool_name=tool_name,
                    tool_payload=tool_payload,
                    tool_config=tool_config,
                    status="error",
                    duration_ms=int((time.monotonic() - start_monotonic) * 1000),
                    error=str(output_error.get("tool_error", "")),
                    task_id=task_id,
                ),
            )
        flush_transcript()
        return failure_result(
            str(output_error.get("summary", "agents sdk output invalid")),
            output_error.get("evidence"),
        )

    try:
        validator.validate_report(payload, output_schema_name)
    except Exception as exc:  # noqa: BLE001
        store.append_tool_call(
            run_id,
            module._build_tool_call(
                tool_name=tool_name,
                tool_payload=tool_payload,
                tool_config=tool_config,
                status="error",
                duration_ms=int((time.monotonic() - start_monotonic) * 1000),
                error=f"output_invalid: {exc}",
                task_id=task_id,
            ),
        )
        record_transcript({"kind": "output_invalid", "text": str(exc)})
        flush_transcript()
        return failure_result("agents sdk output invalid", {"error": str(exc)})

    bound_thread_id, bound_session_id = module._extract_binding_from_result(payload)
    assigned = module._resolve_assigned_agent(contract)
    alias = assigned.get("agent_id") if isinstance(assigned.get("agent_id"), str) else ""
    module.agents_session.bind_agent_session(
        store,
        run_id,
        task_id,
        alias,
        bound_thread_id,
        bound_session_id,
    )
    evidence_refs = module._build_evidence_refs(bound_thread_id, bound_session_id)
    if handoff_refs:
        evidence_refs.update(handoff_refs)
    flush_transcript()
    store.append_tool_call(
        run_id,
        module._build_tool_call(
            tool_name=tool_name,
            tool_payload=tool_payload,
            tool_config=tool_config,
            status="ok",
            duration_ms=int((time.monotonic() - start_monotonic) * 1000),
            thread_id=bound_thread_id or "",
            session_id=bound_session_id or "",
            task_id=task_id,
            output_sha256=module._sha256_text(module._final_output_sha_source(final_output)),
        ),
    )
    return module._coerce_task_result(payload, contract, evidence_refs, "SUCCESS")
