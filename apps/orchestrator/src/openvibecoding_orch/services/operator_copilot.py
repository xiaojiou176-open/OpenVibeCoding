from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Callable

from openvibecoding_orch.contract.validator import ContractValidator
from openvibecoding_orch.config import get_runner_config
from openvibecoding_orch.services.control_plane_read_service import ControlPlaneReadService
from openvibecoding_orch.runners.provider_resolution import (
    build_llm_compat_client,
    merge_provider_credentials,
    ProviderCredentials,
    resolve_compat_api_key,
    resolve_compat_api_mode,
    resolve_provider_credentials,
    resolve_runtime_provider_from_env,
)


def _now_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _agents_available() -> bool:
    try:
        import agents  # noqa: F401

        return True
    except Exception:  # noqa: BLE001
        return False


def _as_record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_array(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _valid_list_items(value: Any) -> list[str]:
    return [str(item).strip() for item in _as_array(value) if str(item).strip()]


def _find_report(reports: list[dict[str, Any]], name: str) -> dict[str, Any]:
    for item in reports:
        if _as_text(item.get("name")) == name:
            return _as_record(item.get("data"))
    return {}


def _latest_run_id_from_workflow_runs(runs: list[dict[str, Any]]) -> str:
    sorted_runs = list(runs)

    def _run_ts(item: dict[str, Any]) -> datetime:
        raw = _as_text(item.get("created_at"))
        if not raw:
            return datetime.fromtimestamp(0, tz=timezone.utc)
        normalized = raw.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return datetime.fromtimestamp(0, tz=timezone.utc)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed

    sorted_runs.sort(key=_run_ts, reverse=True)
    return _as_text(_as_record(sorted_runs[0] if sorted_runs else {}).get("run_id"))


def _pending_approval_for_run(run_id: str, approvals: list[dict[str, Any]]) -> dict[str, Any]:
    for item in approvals:
        if _as_text(item.get("run_id")) == run_id:
            return item
    return {}


def _diff_gate_for_run(run_id: str, diff_gate_rows: list[dict[str, Any]]) -> dict[str, Any]:
    for item in diff_gate_rows:
        if _as_text(item.get("run_id")) == run_id:
            return item
    return {}


def _compact_truth_context(
    *,
    run: dict[str, Any],
    workflow: dict[str, Any],
    queue_items: list[dict[str, Any]],
    compare_summary: dict[str, Any],
    proof_pack: dict[str, Any],
    incident_pack: dict[str, Any],
    pending_approval: dict[str, Any],
    diff_gate: dict[str, Any],
) -> dict[str, Any]:
    return {
        "run": {
            "run_id": _as_text(run.get("run_id")),
            "status": _as_text(run.get("status")),
            "task_id": _as_text(run.get("task_id")),
            "failure_reason": _as_text(run.get("failure_reason")),
            "failure_class": _as_text(run.get("failure_class")),
            "failure_code": _as_text(run.get("failure_code")),
            "workflow_id": _as_text(_as_record(_as_record(run.get("manifest")).get("workflow")).get("workflow_id")),
        },
        "workflow": {
            "workflow_id": _as_text(workflow.get("workflow_id")),
            "status": _as_text(workflow.get("status")),
            "verdict": _as_text(workflow.get("verdict")),
            "objective": _as_text(workflow.get("objective")),
        },
        "queue": {
            "count": len(queue_items),
            "eligible_count": sum(1 for item in queue_items if bool(item.get("eligible"))),
            "sla_states": [_as_text(item.get("sla_state")) for item in queue_items[:5] if _as_text(item.get("sla_state"))],
        },
        "compare_summary": compare_summary,
        "proof_pack": {
            "summary": _as_text(proof_pack.get("summary")),
            "next_action": _as_text(proof_pack.get("next_action")),
            "proof_ready": bool(proof_pack.get("proof_ready")),
        },
        "incident_pack": {
            "summary": _as_text(incident_pack.get("summary")),
            "next_action": _as_text(incident_pack.get("next_action")),
            "root_event": _as_text(incident_pack.get("root_event")),
            "failure_class": _as_text(incident_pack.get("failure_class")),
        },
        "pending_approval": {
            "summary": _as_text(_as_record(pending_approval.get("approval_pack")).get("summary")),
            "resume_step": _as_text(pending_approval.get("resume_step")),
        },
        "diff_gate": {
            "status": _as_text(diff_gate.get("status")),
            "failure_reason": _as_text(diff_gate.get("failure_reason")),
        },
    }


def _latest_run_id(runs: list[dict[str, Any]]) -> str:
    latest_run_id = ""
    latest_ts = float("-inf")
    for item in runs:
        run = _as_record(item)
        run_id = _as_text(run.get("run_id"))
        if not run_id:
            continue
        created_at = _as_text(run.get("created_at"))
        parsed_ts = datetime.fromtimestamp(0, tz=timezone.utc).timestamp()
        if created_at:
            try:
                parsed_ts = datetime.fromisoformat(created_at.replace("Z", "+00:00")).timestamp()
            except ValueError:
                parsed_ts = datetime.fromtimestamp(0, tz=timezone.utc).timestamp()
        if parsed_ts >= latest_ts:
            latest_ts = parsed_ts
            latest_run_id = run_id
    return latest_run_id


def _build_structured_brief(
    *,
    ai_payload: dict[str, Any],
    scope: str,
    run_id: str = "",
    workflow_id: str = "",
    intake_id: str = "",
    questions_answered: list[str],
    used_truth_surfaces: list[str],
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "report_type": "operator_copilot_brief",
        "generated_at": _now_ts(),
        "scope": scope,
        "subject_id": _as_text(intake_id or workflow_id or run_id, "unknown-subject"),
        "status": "OK",
        "summary": _as_text(ai_payload.get("summary"), "No operator summary was generated."),
        "likely_cause": _as_text(ai_payload.get("likely_cause"), "Cause not identified."),
        "compare_takeaway": _as_text(ai_payload.get("compare_takeaway"), "No compare takeaway was generated."),
        "proof_takeaway": _as_text(ai_payload.get("proof_takeaway"), "No proof takeaway was generated."),
        "incident_takeaway": _as_text(ai_payload.get("incident_takeaway"), "No incident takeaway was generated."),
        "queue_takeaway": _as_text(ai_payload.get("queue_takeaway"), "No queue takeaway was generated."),
        "approval_takeaway": _as_text(ai_payload.get("approval_takeaway"), "No approval takeaway was generated."),
        "recommended_actions": _valid_list_items(ai_payload.get("recommended_actions")),
        "top_risks": _valid_list_items(ai_payload.get("top_risks")),
        "questions_answered": questions_answered,
        "used_truth_surfaces": used_truth_surfaces,
        "limitations": _valid_list_items(ai_payload.get("limitations")),
        "provider": _as_text(ai_payload.get("provider"), "unknown"),
        "model": _as_text(ai_payload.get("model"), "unknown"),
    }
    if run_id:
        report["run_id"] = run_id
    if workflow_id:
        report["workflow_id"] = workflow_id
    if intake_id:
        report["intake_id"] = intake_id
    return report


def _unavailable_brief(
    *,
    scope: str,
    reason: str,
    run_id: str = "",
    workflow_id: str = "",
    intake_id: str = "",
    questions_answered: list[str],
    used_truth_surfaces: list[str],
    compare_takeaway: str,
    proof_takeaway: str,
    incident_takeaway: str,
    queue_takeaway: str,
    approval_takeaway: str,
) -> dict[str, Any]:
    return {
        "report_type": "operator_copilot_brief",
        "generated_at": _now_ts(),
        "scope": scope,
        "subject_id": _as_text(intake_id or workflow_id or run_id, "unknown-subject"),
        **({"run_id": run_id} if run_id else {}),
        **({"workflow_id": workflow_id} if workflow_id else {}),
        **({"intake_id": intake_id} if intake_id else {}),
        "status": "UNAVAILABLE",
        "summary": "AI operator copilot is unavailable in the current environment.",
        "likely_cause": reason,
        "compare_takeaway": compare_takeaway,
        "proof_takeaway": proof_takeaway,
        "incident_takeaway": incident_takeaway,
        "queue_takeaway": queue_takeaway,
        "approval_takeaway": approval_takeaway,
        "recommended_actions": [
            "Review the visible truth surfaces directly.",
            "Confirm provider credentials and retry the operator copilot request.",
        ],
        "top_risks": [reason],
        "questions_answered": questions_answered,
        "used_truth_surfaces": used_truth_surfaces,
        "limitations": [
            "No LLM response was generated.",
            "This fallback does not replace the underlying truth surfaces.",
        ],
        "provider": "unavailable",
        "model": "unavailable",
    }


def _build_ai_brief(prompt: str) -> dict[str, Any]:
    if not _agents_available():
        raise RuntimeError("agents sdk unavailable")

    from agents import Agent, Runner, set_default_openai_api

    set_default_openai_client = None
    try:
        from agents import set_default_openai_client as _set_default_openai_client

        set_default_openai_client = _set_default_openai_client
    except Exception:  # noqa: BLE001
        set_default_openai_client = None

    runner_cfg = get_runner_config()
    provider = resolve_runtime_provider_from_env()
    provider_credentials = merge_provider_credentials(
        ProviderCredentials(
            gemini_api_key=str(getattr(runner_cfg, "gemini_api_key", "") or "").strip(),
            openai_api_key=str(getattr(runner_cfg, "openai_api_key", "") or "").strip(),
            anthropic_api_key=str(getattr(runner_cfg, "anthropic_api_key", "") or "").strip(),
            equilibrium_api_key=str(getattr(runner_cfg, "equilibrium_api_key", "") or "").strip(),
        ),
        resolve_provider_credentials(),
    )
    base_url = str(getattr(runner_cfg, "agents_base_url", "") or "").strip() or None
    api_key = resolve_compat_api_key(provider_credentials, provider, base_url=base_url)
    if not api_key:
        raise RuntimeError(f"missing LLM API key for provider `{provider}`")
    compat_client = build_llm_compat_client(api_key=api_key, base_url=base_url, provider=provider)
    try:
        set_default_openai_api(
            resolve_compat_api_mode(
                str(getattr(runner_cfg, "agents_api", "") or "responses"),
                base_url=base_url,
            )
        )
    except Exception:  # noqa: BLE001
        pass
    if callable(set_default_openai_client) and compat_client is not None:
        try:
            set_default_openai_client(compat_client)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"copilot client setup failed: {exc}") from exc

    model_name = str(getattr(runner_cfg, "agents_model", "") or "").strip() or "gemini-2.5-flash"
    instructions = (
        "You are OpenVibeCoding Operator Copilot v1. "
        "You explain current run, workflow, or pre-run planning state to an operator using only the provided truth surfaces. "
        "Return JSON only with fields: "
        "summary, likely_cause, compare_takeaway, proof_takeaway, incident_takeaway, queue_takeaway, "
        "approval_takeaway, recommended_actions (array), top_risks (array), limitations (array). "
        "Do not invent facts beyond the provided context."
    )
    agent = Agent(
        name="OpenVibeCodingOperatorCopilot",
        instructions=instructions,
        model=model_name,
        mcp_servers=[],
    )

    async def _run() -> Any:
        return await Runner.run(agent, prompt)

    result = asyncio.run(_run())
    output = getattr(result, "final_output", None)
    if not isinstance(output, str) or not output.strip():
        raise RuntimeError("copilot output missing")
    payload = json.loads(output)
    if not isinstance(payload, dict):
        raise RuntimeError("copilot output not object")
    payload.setdefault("provider", provider)
    payload.setdefault("model", model_name)
    return payload


def _build_ai_flight_plan_brief(prompt: str) -> dict[str, Any]:
    if not _agents_available():
        raise RuntimeError("agents sdk unavailable")

    from agents import Agent, Runner, set_default_openai_api

    set_default_openai_client = None
    try:
        from agents import set_default_openai_client as _set_default_openai_client

        set_default_openai_client = _set_default_openai_client
    except Exception:  # noqa: BLE001
        set_default_openai_client = None

    runner_cfg = get_runner_config()
    provider = resolve_runtime_provider_from_env()
    provider_credentials = merge_provider_credentials(
        ProviderCredentials(
            gemini_api_key=str(getattr(runner_cfg, "gemini_api_key", "") or "").strip(),
            openai_api_key=str(getattr(runner_cfg, "openai_api_key", "") or "").strip(),
            anthropic_api_key=str(getattr(runner_cfg, "anthropic_api_key", "") or "").strip(),
            equilibrium_api_key=str(getattr(runner_cfg, "equilibrium_api_key", "") or "").strip(),
        ),
        resolve_provider_credentials(),
    )
    base_url = str(getattr(runner_cfg, "agents_base_url", "") or "").strip() or None
    api_key = resolve_compat_api_key(provider_credentials, provider, base_url=base_url)
    if not api_key:
        raise RuntimeError(f"missing LLM API key for provider `{provider}`")
    compat_client = build_llm_compat_client(api_key=api_key, base_url=base_url, provider=provider)
    try:
        set_default_openai_api(
            resolve_compat_api_mode(
                str(getattr(runner_cfg, "agents_api", "") or "responses"),
                base_url=base_url,
            )
        )
    except Exception:  # noqa: BLE001
        pass
    if callable(set_default_openai_client) and compat_client is not None:
        try:
            set_default_openai_client(compat_client)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"flight-plan copilot client setup failed: {exc}") from exc

    model_name = str(getattr(runner_cfg, "agents_model", "") or "").strip() or "gemini-2.5-flash"
    instructions = (
        "You are OpenVibeCoding Flight Plan Copilot. "
        "You explain pre-run execution plans using only the provided execution-plan truth. "
        "Return JSON only with fields: "
        "summary, risk_takeaway, capability_takeaway, approval_takeaway, "
        "recommended_actions (array), top_risks (array), limitations (array). "
        "Do not invent run results, compare results, or post-run proof."
    )
    agent = Agent(
        name="OpenVibeCodingFlightPlanCopilot",
        instructions=instructions,
        model=model_name,
        mcp_servers=[],
    )

    async def _run() -> Any:
        return await Runner.run(agent, prompt)

    result = asyncio.run(_run())
    output = getattr(result, "final_output", None)
    if not isinstance(output, str) or not output.strip():
        raise RuntimeError("flight-plan copilot output missing")
    payload = json.loads(output)
    if not isinstance(payload, dict):
        raise RuntimeError("flight-plan copilot output not object")
    payload.setdefault("provider", provider)
    payload.setdefault("model", model_name)
    return payload


def generate_run_operator_copilot_brief(
    run_id: str,
    *,
    get_run_fn: Callable[[str], dict[str, Any]],
    get_reports_fn: Callable[[str], list[dict[str, Any]]],
    get_workflow_fn: Callable[[str], dict[str, Any]],
    list_queue_fn: Callable[..., list[dict[str, Any]]],
    list_pending_approvals_fn: Callable[[], list[dict[str, Any]]],
    list_diff_gate_fn: Callable[[], list[dict[str, Any]]],
) -> dict[str, Any]:
    run = get_run_fn(run_id)
    reports = get_reports_fn(run_id)
    workflow_id = _as_text(_as_record(_as_record(run.get("manifest")).get("workflow")).get("workflow_id"))
    workflow_payload = get_workflow_fn(workflow_id) if workflow_id else {}
    workflow = _as_record(workflow_payload.get("workflow") if isinstance(workflow_payload, dict) else {})
    queue_items = list_queue_fn(workflow_id=workflow_id, status=None) if workflow_id else []
    pending_approval = _pending_approval_for_run(run_id, list_pending_approvals_fn())
    diff_gate = _diff_gate_for_run(run_id, list_diff_gate_fn())
    compare_summary = _as_record(_find_report(reports, "run_compare_report.json").get("compare_summary"))
    proof_pack = _find_report(reports, "proof_pack.json")
    incident_pack = _find_report(reports, "incident_pack.json")

    questions_answered = [
        "Why did this run fail or get blocked?",
        "What is the most important difference from the baseline?",
        "What should the operator do next?",
        "Where is the workflow/queue risk right now?",
    ]
    used_truth_surfaces = [
        "run detail",
        "run events",
        "run reports",
        "workflow case",
        "queue / SLA",
        "pending approvals",
        "diff gate state",
    ]
    compact_context = _compact_truth_context(
        run=run,
        workflow=workflow,
        queue_items=queue_items,
        compare_summary=compare_summary,
        proof_pack=proof_pack,
        incident_pack=incident_pack,
        pending_approval=pending_approval,
        diff_gate=diff_gate,
    )
    prompt_payload = {
        "run_id": run_id,
        "workflow_id": workflow_id,
        "questions_answered": questions_answered,
        "used_truth_surfaces": used_truth_surfaces,
        "context": compact_context,
    }

    try:
        ai_payload = _build_ai_brief(json.dumps(prompt_payload, ensure_ascii=False))
        report = _build_structured_brief(
            ai_payload=ai_payload,
            scope="run",
            run_id=run_id,
            workflow_id=workflow_id,
            questions_answered=questions_answered,
            used_truth_surfaces=used_truth_surfaces,
        )
    except Exception as exc:  # noqa: BLE001
        report = _unavailable_brief(
            scope="run",
            reason=str(exc),
            run_id=run_id,
            workflow_id=workflow_id,
            questions_answered=questions_answered,
            used_truth_surfaces=used_truth_surfaces,
            compare_takeaway="No AI explanation was generated for the current compare state.",
            proof_takeaway="Review the proof and replay surfaces directly until copilot is available.",
            incident_takeaway="Review the incident surface directly until copilot is available.",
            queue_takeaway="Review workflow queue and SLA state directly until copilot is available.",
            approval_takeaway="Review approval and gate surfaces directly until copilot is available.",
        )

    ContractValidator().validate_report(report, "operator_copilot_brief.v1.json")
    return report


def _legacy_generate_workflow_operator_copilot_brief_shadow(
    workflow_id: str,
    *,
    get_workflow_fn: Callable[[str], dict[str, Any]],
    get_run_fn: Callable[[str], dict[str, Any]],
    get_reports_fn: Callable[[str], list[dict[str, Any]]],
    list_queue_fn: Callable[..., list[dict[str, Any]]],
    list_pending_approvals_fn: Callable[[], list[dict[str, Any]]],
    list_diff_gate_fn: Callable[[], list[dict[str, Any]]],
) -> dict[str, Any]:
    workflow_payload = get_workflow_fn(workflow_id)
    workflow = _as_record(workflow_payload.get("workflow") if isinstance(workflow_payload, dict) else {})
    runs = _as_array(workflow_payload.get("runs") if isinstance(workflow_payload, dict) else [])
    latest_run_id = _latest_run_id_from_workflow_runs([_as_record(item) for item in runs if isinstance(item, dict)])
    queue_items = list_queue_fn(workflow_id=workflow_id, status=None)
    questions_answered = [
        "What is the highest workflow risk right now?",
        "What does the queue or SLA posture say?",
        "What is the biggest gap between the latest run and the current workflow state?",
        "What should the operator do next?",
        "Which workflow truth is still missing before this case can be trusted?",
    ]
    used_truth_surfaces = [
        "workflow case",
        "workflow run list",
        "queue / SLA",
        "pending approvals",
        "diff gate state",
    ]

    if not latest_run_id:
        report = {
            "report_type": "operator_copilot_brief",
            "generated_at": _now_ts(),
            "run_id": f"workflow:{workflow_id}",
            "workflow_id": workflow_id,
            "status": "UNAVAILABLE",
            "summary": "Workflow operator copilot needs at least one related run before it can explain the current case state.",
            "likely_cause": "No related run is attached to this workflow case yet.",
            "compare_takeaway": "No compare truth exists yet because this workflow case has no latest run.",
            "proof_takeaway": "No proof pack is attached yet because this workflow case has no latest run.",
            "incident_takeaway": "No incident pack is attached yet because this workflow case has no latest run.",
            "queue_takeaway": (
                f"Queue currently has {len(queue_items)} item(s), but run-scoped comparison and proof truth are not available yet."
            ),
            "approval_takeaway": "Review approval and queue posture directly until at least one run exists for this workflow case.",
            "recommended_actions": [
                "Create or resume a run before asking for a workflow-level explanation.",
                "Review queue posture and workflow summary directly until run truth exists.",
            ],
            "top_risks": ["Workflow case has no attached run truth yet."],
            "questions_answered": questions_answered,
            "used_truth_surfaces": used_truth_surfaces,
            "limitations": [
                "Workflow copilot stays bounded to existing workflow and queue truth.",
                "No run-level compare, proof, or incident truth exists yet for this workflow case.",
            ],
            "provider": "unavailable",
            "model": "unavailable",
        }
        ContractValidator().validate_report(report, "operator_copilot_brief.v1.json")
        return report

    run = get_run_fn(latest_run_id)
    reports = get_reports_fn(latest_run_id)
    pending_approval = _pending_approval_for_run(latest_run_id, list_pending_approvals_fn())
    diff_gate = _diff_gate_for_run(latest_run_id, list_diff_gate_fn())
    compare_summary = _as_record(_find_report(reports, "run_compare_report.json").get("compare_summary"))
    proof_pack = _find_report(reports, "proof_pack.json")
    incident_pack = _find_report(reports, "incident_pack.json")
    compact_context = _compact_truth_context(
        run=run,
        workflow=workflow,
        queue_items=queue_items,
        compare_summary=compare_summary,
        proof_pack=proof_pack,
        incident_pack=incident_pack,
        pending_approval=pending_approval,
        diff_gate=diff_gate,
    )
    prompt_payload = {
        "workflow_id": workflow_id,
        "latest_run_id": latest_run_id,
        "questions_answered": questions_answered,
        "used_truth_surfaces": used_truth_surfaces + ["latest run detail", "latest run reports"],
        "context": compact_context,
    }

    try:
        ai_payload = _build_ai_brief(json.dumps(prompt_payload, ensure_ascii=False))
        report = {
            "report_type": "operator_copilot_brief",
            "generated_at": _now_ts(),
            "run_id": latest_run_id,
            "workflow_id": workflow_id,
            "status": "OK",
            "summary": _as_text(ai_payload.get("summary"), "No workflow summary was generated."),
            "likely_cause": _as_text(ai_payload.get("likely_cause"), "Workflow cause not identified."),
            "compare_takeaway": _as_text(ai_payload.get("compare_takeaway"), "No compare takeaway was generated."),
            "proof_takeaway": _as_text(ai_payload.get("proof_takeaway"), "No proof takeaway was generated."),
            "incident_takeaway": _as_text(ai_payload.get("incident_takeaway"), "No incident takeaway was generated."),
            "queue_takeaway": _as_text(ai_payload.get("queue_takeaway"), "No queue takeaway was generated."),
            "approval_takeaway": _as_text(ai_payload.get("approval_takeaway"), "No approval takeaway was generated."),
            "recommended_actions": [str(item).strip() for item in _as_array(ai_payload.get("recommended_actions")) if str(item).strip()],
            "top_risks": [str(item).strip() for item in _as_array(ai_payload.get("top_risks")) if str(item).strip()],
            "questions_answered": questions_answered,
            "used_truth_surfaces": used_truth_surfaces + ["latest run detail", "latest run reports"],
            "limitations": [str(item).strip() for item in _as_array(ai_payload.get("limitations")) if str(item).strip()],
            "provider": _as_text(ai_payload.get("provider"), "unknown"),
            "model": _as_text(ai_payload.get("model"), "unknown"),
        }
    except Exception as exc:  # noqa: BLE001
        report = _unavailable_brief(latest_run_id, workflow_id, reason=str(exc))

    ContractValidator().validate_report(report, "operator_copilot_brief.v1.json")
    return report


def _unavailable_flight_plan_brief(*, reason: str) -> dict[str, Any]:
    return {
        "report_type": "flight_plan_copilot_brief",
        "generated_at": _now_ts(),
        "status": "UNAVAILABLE",
        "summary": "Flight Plan copilot is unavailable in the current environment.",
        "risk_takeaway": reason,
        "capability_takeaway": "Review the capability triggers directly from the Flight Plan preview.",
        "approval_takeaway": "Review approval gates directly from the Flight Plan preview.",
        "recommended_actions": [
            "Review the Flight Plan checklist directly.",
            "Confirm provider credentials and retry the advisory brief request.",
        ],
        "top_risks": [reason],
        "questions_answered": [
            "What is the most important risk gate before execution starts?",
            "Why are these capabilities triggered?",
            "What should the operator confirm before starting?",
        ],
        "used_truth_surfaces": ["execution plan report", "contract preview"],
        "limitations": [
            "This brief is pre-run advisory only.",
            "It does not replace the post-run compare, proof, or incident truth surfaces.",
        ],
        "provider": "unavailable",
        "model": "unavailable",
    }


def generate_execution_plan_copilot_brief(plan_report: dict[str, Any]) -> dict[str, Any]:
    ContractValidator().validate_report(plan_report, "execution_plan_report.v1.json")
    questions_answered = [
        "What is the most important risk gate before execution starts?",
        "Why are these capabilities triggered?",
        "What should the operator confirm before starting?",
        "Where is this plan most likely to fail?",
        "If only one prevention step is taken, what should it be?",
    ]
    used_truth_surfaces = [
        "execution plan report",
        "contract preview",
        "acceptance checks",
        "predicted reports",
        "predicted artifacts",
    ]
    prompt_payload = {
        "questions_answered": questions_answered,
        "used_truth_surfaces": used_truth_surfaces,
        "context": {
            "objective": _as_text(plan_report.get("objective")),
            "summary": _as_text(plan_report.get("summary")),
            "assigned_role": _as_text(plan_report.get("assigned_role")),
            "allowed_paths": _as_array(plan_report.get("allowed_paths")),
            "warnings": _as_array(plan_report.get("warnings")),
            "notes": _as_array(plan_report.get("notes")),
            "search_queries": _as_array(plan_report.get("search_queries")),
            "predicted_reports": _as_array(plan_report.get("predicted_reports")),
            "predicted_artifacts": _as_array(plan_report.get("predicted_artifacts")),
            "requires_human_approval": bool(plan_report.get("requires_human_approval")),
            "browser_policy_preset": _as_text(plan_report.get("browser_policy_preset")),
            "contract_preview": _as_record(plan_report.get("contract_preview")),
        },
    }

    try:
        ai_payload = _build_ai_flight_plan_brief(json.dumps(prompt_payload, ensure_ascii=False))
        report = {
            "report_type": "flight_plan_copilot_brief",
            "generated_at": _now_ts(),
            "status": "OK",
            "summary": _as_text(ai_payload.get("summary"), "No Flight Plan summary was generated."),
            "risk_takeaway": _as_text(ai_payload.get("risk_takeaway"), "No Flight Plan risk takeaway was generated."),
            "capability_takeaway": _as_text(ai_payload.get("capability_takeaway"), "No capability takeaway was generated."),
            "approval_takeaway": _as_text(ai_payload.get("approval_takeaway"), "No approval takeaway was generated."),
            "recommended_actions": [str(item).strip() for item in _as_array(ai_payload.get("recommended_actions")) if str(item).strip()],
            "top_risks": [str(item).strip() for item in _as_array(ai_payload.get("top_risks")) if str(item).strip()],
            "questions_answered": questions_answered,
            "used_truth_surfaces": used_truth_surfaces,
            "limitations": [str(item).strip() for item in _as_array(ai_payload.get("limitations")) if str(item).strip()],
            "provider": _as_text(ai_payload.get("provider"), "unknown"),
            "model": _as_text(ai_payload.get("model"), "unknown"),
        }
    except Exception as exc:  # noqa: BLE001
        report = _unavailable_flight_plan_brief(reason=str(exc))

    ContractValidator().validate_report(report, "flight_plan_copilot_brief.v1.json")
    return report


def generate_run_operator_copilot_brief_from_service(
    run_id: str,
    *,
    read_service: ControlPlaneReadService,
) -> dict[str, Any]:
    return generate_run_operator_copilot_brief(
        run_id,
        get_run_fn=read_service.get_run,
        get_reports_fn=read_service.get_run_reports,
        get_workflow_fn=read_service.get_workflow,
        list_queue_fn=read_service.list_queue,
        list_pending_approvals_fn=lambda: read_service.get_pending_approvals(),
        list_diff_gate_fn=lambda: read_service.get_diff_gate_state(),
    )


def generate_workflow_operator_copilot_brief_from_service(
    workflow_id: str,
    *,
    read_service: ControlPlaneReadService,
) -> dict[str, Any]:
    return generate_workflow_operator_copilot_brief(
        workflow_id,
        get_workflow_fn=read_service.get_workflow,
        get_run_fn=read_service.get_run,
        get_reports_fn=read_service.get_run_reports,
        list_queue_fn=read_service.list_queue,
        list_pending_approvals_fn=lambda: read_service.get_pending_approvals(),
        list_diff_gate_fn=lambda: read_service.get_diff_gate_state(),
    )


def generate_workflow_operator_copilot_brief(
    workflow_id: str,
    *,
    get_workflow_fn: Callable[[str], dict[str, Any]],
    get_run_fn: Callable[[str], dict[str, Any]],
    get_reports_fn: Callable[[str], list[dict[str, Any]]],
    list_queue_fn: Callable[..., list[dict[str, Any]]],
    list_pending_approvals_fn: Callable[[], list[dict[str, Any]]],
    list_diff_gate_fn: Callable[[], list[dict[str, Any]]],
) -> dict[str, Any]:
    workflow_payload = get_workflow_fn(workflow_id)
    workflow = _as_record(workflow_payload.get("workflow") if isinstance(workflow_payload, dict) else {})
    runs = [_as_record(item) for item in _as_array(workflow_payload.get("runs") if isinstance(workflow_payload, dict) else [])]
    latest_run_id = _latest_run_id(runs)
    latest_run = get_run_fn(latest_run_id) if latest_run_id else {}
    latest_reports = get_reports_fn(latest_run_id) if latest_run_id else []
    queue_items = list_queue_fn(workflow_id=workflow_id, status=None)
    pending_approval = _pending_approval_for_run(latest_run_id, list_pending_approvals_fn()) if latest_run_id else {}
    diff_gate = _diff_gate_for_run(latest_run_id, list_diff_gate_fn()) if latest_run_id else {}
    compare_summary = _as_record(_find_report(latest_reports, "run_compare_report.json").get("compare_summary"))
    proof_pack = _find_report(latest_reports, "proof_pack.json")
    incident_pack = _find_report(latest_reports, "incident_pack.json")
    missing_truth: list[str] = []
    if not latest_run_id:
        missing_truth.append("No linked run is attached to the current workflow case.")
    if not compare_summary:
        missing_truth.append("Compare truth is missing for the latest workflow run.")
    if not proof_pack:
        missing_truth.append("Proof truth is missing for the latest workflow run.")
    if not incident_pack:
        missing_truth.append("Incident truth is missing for the latest workflow run.")

    questions_answered = [
        "What is the most important workflow case risk right now?",
        "What is the queue and SLA posture for this workflow case?",
        "What is the biggest gap between the latest run and the current workflow state?",
        "What should the operator do first to move this workflow case forward?",
        "Which truth surfaces are still missing or partial?",
    ]
    used_truth_surfaces = [
        "workflow case",
        "queue / SLA",
        "latest linked run",
        "latest run reports",
        "pending approvals",
        "diff gate state",
    ]
    prompt_payload = {
        "scope": "workflow",
        "workflow_id": workflow_id,
        "questions_answered": questions_answered,
        "used_truth_surfaces": used_truth_surfaces,
        "context": {
            "workflow": {
                "workflow_id": _as_text(workflow.get("workflow_id"), workflow_id),
                "status": _as_text(workflow.get("status")),
                "verdict": _as_text(workflow.get("verdict")),
                "objective": _as_text(workflow.get("objective")),
                "summary": _as_text(workflow.get("summary")),
                "owner_pm": _as_text(workflow.get("owner_pm")),
                "project_key": _as_text(workflow.get("project_key")),
            },
            "latest_run": {
                "run_id": latest_run_id,
                "status": _as_text(_as_record(latest_run).get("status")),
                "failure_reason": _as_text(_as_record(latest_run).get("failure_reason")),
            },
            "queue": {
                "count": len(queue_items),
                "eligible_count": sum(1 for item in queue_items if bool(_as_record(item).get("eligible"))),
                "sla_states": [_as_text(_as_record(item).get("sla_state")) for item in queue_items[:5] if _as_text(_as_record(item).get("sla_state"))],
            },
            "compare_summary": compare_summary,
            "proof_pack": {
                "summary": _as_text(proof_pack.get("summary")),
                "next_action": _as_text(proof_pack.get("next_action")),
                "proof_ready": bool(proof_pack.get("proof_ready")),
            },
            "incident_pack": {
                "summary": _as_text(incident_pack.get("summary")),
                "next_action": _as_text(incident_pack.get("next_action")),
            },
            "pending_approval": {
                "summary": _as_text(_as_record(pending_approval.get("approval_pack")).get("summary")),
                "resume_step": _as_text(pending_approval.get("resume_step")),
            },
            "diff_gate": {
                "status": _as_text(diff_gate.get("status")),
                "failure_reason": _as_text(diff_gate.get("failure_reason")),
            },
            "missing_truth": missing_truth,
        },
    }

    try:
        ai_payload = _build_ai_brief(json.dumps(prompt_payload, ensure_ascii=False))
        report = _build_structured_brief(
            ai_payload=ai_payload,
            scope="workflow",
            run_id=latest_run_id,
            workflow_id=workflow_id,
            questions_answered=questions_answered,
            used_truth_surfaces=used_truth_surfaces,
        )
    except Exception as exc:  # noqa: BLE001
        report = _unavailable_brief(
            scope="workflow",
            reason=str(exc),
            run_id=latest_run_id,
            workflow_id=workflow_id,
            questions_answered=questions_answered,
            used_truth_surfaces=used_truth_surfaces,
            compare_takeaway="Review the latest run delta and workflow summary directly until copilot is available.",
            proof_takeaway="Review proof and incident packs directly for the latest linked run.",
            incident_takeaway="Check which workflow truth surfaces are still missing or partial.",
            queue_takeaway="Inspect queue posture and SLA directly on the workflow detail surface.",
            approval_takeaway="Inspect approval and diff gate posture directly until copilot is available.",
        )

    ContractValidator().validate_report(report, "operator_copilot_brief.v1.json")
    return report


def generate_execution_plan_operator_copilot_brief(
    execution_plan_report: dict[str, Any],
    *,
    intake_id: str = "",
) -> dict[str, Any]:
    report_payload = _as_record(execution_plan_report)
    questions_answered = [
        "What is the most important pre-run risk gate in this Flight Plan?",
        "Why does this plan trigger search, browser, provider, or approval capabilities?",
        "What should a human confirm before starting execution?",
        "Where is this plan most likely to fail first?",
        "If the operator only does one prevention step, what should it be?",
    ]
    used_truth_surfaces = [
        "execution plan preview",
        "contract preview",
        "runtime capability summary",
        "predicted reports",
        "predicted artifacts",
        "acceptance checks",
        "warnings / notes",
    ]
    acceptance_checks = []
    for index, item in enumerate(_as_array(report_payload.get("acceptance_tests"))):
        record = _as_record(item)
        label = _as_text(record.get("name")) or _as_text(record.get("cmd")) or _as_text(record.get("command")) or f"check {index + 1}"
        acceptance_checks.append(label)

    prompt_payload = {
        "scope": "flight_plan",
        "intake_id": intake_id,
        "questions_answered": questions_answered,
        "used_truth_surfaces": used_truth_surfaces,
        "context": {
            "objective": _as_text(report_payload.get("objective")),
            "summary": _as_text(report_payload.get("summary")),
            "assigned_role": _as_text(report_payload.get("assigned_role")),
            "allowed_paths": _valid_list_items(report_payload.get("allowed_paths")),
            "search_queries": _valid_list_items(report_payload.get("search_queries")),
            "predicted_reports": _valid_list_items(report_payload.get("predicted_reports")),
            "predicted_artifacts": _valid_list_items(report_payload.get("predicted_artifacts")),
            "runtime_capability_summary": _as_record(report_payload.get("runtime_capability_summary")),
            "warnings": _valid_list_items(report_payload.get("warnings")),
            "notes": _valid_list_items(report_payload.get("notes")),
            "requires_human_approval": bool(report_payload.get("requires_human_approval")),
            "acceptance_checks": acceptance_checks,
            "browser_policy_preset": _as_text(report_payload.get("browser_policy_preset")),
            "contract_preview": _as_record(report_payload.get("contract_preview")),
        },
    }
    try:
        ai_payload = _build_ai_brief(json.dumps(prompt_payload, ensure_ascii=False))
        report = _build_structured_brief(
            ai_payload=ai_payload,
            scope="flight_plan",
            intake_id=intake_id,
            questions_answered=questions_answered,
            used_truth_surfaces=used_truth_surfaces,
        )
    except Exception as exc:  # noqa: BLE001
        report = _unavailable_brief(
            scope="flight_plan",
            reason=str(exc),
            intake_id=intake_id,
            questions_answered=questions_answered,
            used_truth_surfaces=used_truth_surfaces,
            compare_takeaway="Review capability triggers and predicted outputs directly until copilot is available.",
            proof_takeaway="Review expected reports, artifacts, and acceptance checks directly before the first run.",
            incident_takeaway="Review current warnings to see where the plan is most likely to fail first.",
            queue_takeaway="Review scope boundaries and assigned role directly from the Flight Plan preview.",
            approval_takeaway="Review manual approval posture directly from the Flight Plan preview.",
        )

    ContractValidator().validate_report(report, "operator_copilot_brief.v1.json")
    return report
