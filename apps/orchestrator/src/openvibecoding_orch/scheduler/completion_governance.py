from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _load_json_artifact(run_dir: Path, filename: str) -> Any:
    path = run_dir / "artifacts" / filename
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _normalize_records(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in payload:
        if isinstance(item, dict):
            normalized.append(dict(item))
    return normalized


def _coerce_gate_passed(task_result: dict[str, Any] | None, gate_name: str) -> bool:
    if not isinstance(task_result, dict):
        return False
    gates = task_result.get("gates")
    if not isinstance(gates, dict):
        return False
    gate = gates.get(gate_name)
    return bool(isinstance(gate, dict) and gate.get("passed"))


def _collect_required_checks(
    planning_contracts: list[dict[str, Any]],
    *,
    contract: dict[str, Any],
) -> list[str]:
    required_checks: list[str] = []
    for planning_contract in planning_contracts:
        done_definition = planning_contract.get("done_definition")
        if not isinstance(done_definition, dict):
            continue
        checks = done_definition.get("acceptance_checks")
        if not isinstance(checks, list):
            continue
        for item in checks:
            value = str(item).strip()
            if value and value not in required_checks:
                required_checks.append(value)
    if required_checks:
        return required_checks
    acceptance_tests = contract.get("acceptance_tests")
    if isinstance(acceptance_tests, list) and acceptance_tests:
        required_checks.extend(["test_report"])
    return required_checks or ["diff_gate", "policy_gate", "review_report", "test_report"]


def _check_required_item(
    check_name: str,
    *,
    task_result: dict[str, Any] | None,
    test_report: dict[str, Any] | None,
    review_report: dict[str, Any] | None,
    run_dir: Path,
    status: str,
) -> tuple[bool, str]:
    normalized = check_name.strip().lower()
    if normalized in {"diff_gate"}:
        return _coerce_gate_passed(task_result, "diff_gate"), check_name
    if normalized in {"policy_gate", "repo_hygiene"}:
        return _coerce_gate_passed(task_result, "policy_gate"), check_name
    if normalized in {"review_gate", "review_report"}:
        review_pass = _coerce_gate_passed(task_result, "review_gate")
        verdict_pass = isinstance(review_report, dict) and str(review_report.get("verdict") or "").upper() == "PASS"
        return review_pass and verdict_pass, check_name
    if normalized in {"tests_gate", "test_report"}:
        tests_pass = _coerce_gate_passed(task_result, "tests_gate")
        report_pass = isinstance(test_report, dict) and str(test_report.get("status") or "").upper() == "PASS"
        return tests_pass and report_pass, check_name
    if normalized == "task_result":
        return str(status).upper() == "SUCCESS", check_name
    if normalized == "evidence_report":
        return (run_dir / "reports" / "evidence_report.json").exists(), check_name
    if normalized == "prompt_artifact":
        return (run_dir / "artifacts" / "prompt_artifact.json").exists(), check_name
    return False, f"unknown:{check_name}"


def _collect_policy_action(
    planning_contracts: list[dict[str, Any]],
    field_name: str,
) -> str:
    for planning_contract in planning_contracts:
        continuation_policy = planning_contract.get("continuation_policy")
        if not isinstance(continuation_policy, dict):
            continue
        value = str(continuation_policy.get(field_name) or "").strip()
        if value:
            return value
    return ""


def _extract_thread_id(
    *,
    contract: dict[str, Any],
    task_result: dict[str, Any] | None,
    run_dir: Path,
) -> str:
    if isinstance(task_result, dict):
        evidence_refs = task_result.get("evidence_refs")
        if isinstance(evidence_refs, dict):
            thread_id = str(evidence_refs.get("thread_id") or evidence_refs.get("codex_thread_id") or "").strip()
            if thread_id:
                return thread_id
    assigned_agent = contract.get("assigned_agent")
    if isinstance(assigned_agent, dict):
        thread_id = str(assigned_agent.get("codex_thread_id") or "").strip()
        if thread_id:
            return thread_id
    return run_dir.name


def _detect_context_pack_trigger(
    *,
    failure_reason: str,
    reply_auditor: dict[str, Any],
) -> str:
    normalized_reason = failure_reason.lower()
    trigger_pairs = [
        ("context_pressure", ["context pressure", "context limit", "token limit"]),
        ("contamination", ["contamination", "context contamination", "poisoned context"]),
        ("role_switch", ["role switch", "handoff to another role"]),
        ("phase_switch", ["phase switch", "stage switch", "next phase"]),
        ("repetition", ["repetition", "repeat", "looping reply"]),
        ("distortion", ["distortion", "garbled", "misread"]),
    ]
    for trigger, phrases in trigger_pairs:
        if any(phrase in normalized_reason for phrase in phrases):
            return trigger
    signals = reply_auditor.get("signals")
    if isinstance(signals, list):
        normalized_signals = [str(item).strip().lower() for item in signals if str(item).strip()]
        if any("repetition" in item for item in normalized_signals):
            return "repetition"
        if any("contamination" in item for item in normalized_signals):
            return "contamination"
    return ""


def _build_context_pack_artifact(
    *,
    contract: dict[str, Any],
    run_dir: Path,
    failure_reason: str,
    continuation_summary: str,
    reply_auditor: dict[str, Any],
) -> dict[str, Any] | None:
    trigger_reason = _detect_context_pack_trigger(
        failure_reason=failure_reason,
        reply_auditor=reply_auditor,
    )
    if not trigger_reason:
        return None
    assigned_agent = contract.get("assigned_agent") if isinstance(contract.get("assigned_agent"), dict) else {}
    objective = str(contract.get("objective") or "").strip() or "Continue the current scope safely."
    source_role = str(assigned_agent.get("role") or "WORKER").strip() or "WORKER"
    thread_id = _extract_thread_id(contract=contract, task_result=None, run_dir=run_dir)
    return {
        "version": "v1",
        "pack_id": f"ctx-pack-{run_dir.name}",
        "role_scope": "L1",
        "source_session_id": thread_id,
        "source_role": source_role,
        "trigger_reason": trigger_reason,
        "global_state_summary": (
            f"The current run for '{objective}' hit a {trigger_reason} fallback condition and needs an explicit handoff."
        ),
        "actor_handoff_summary": continuation_summary,
        "required_reads": [
            "contract.json",
            "reports/task_result.json",
            "reports/completion_governance_report.json",
        ],
        "optional_reads": [
            "reports/review_report.json",
            "reports/test_report.json",
            "events.jsonl",
        ],
        "conversation_exports": ["events.jsonl"],
        "artifact_refs": [
            "reports/task_result.json",
            "reports/completion_governance_report.json",
        ],
    }


def _derive_harness_request_artifact(
    *,
    contract: dict[str, Any],
    task_result: dict[str, Any] | None,
    run_dir: Path,
) -> tuple[dict[str, Any] | None, str]:
    if not isinstance(task_result, dict):
        return None, "not_requested"
    gates = task_result.get("gates")
    if not isinstance(gates, dict):
        return None, "not_requested"
    policy_gate = gates.get("policy_gate")
    if not isinstance(policy_gate, dict):
        return None, "not_requested"
    violations = policy_gate.get("violations")
    if not isinstance(violations, list) or not violations:
        return None, "not_requested"
    normalized_violations = [str(item).strip() for item in violations if str(item).strip()]
    if not normalized_violations:
        return None, "not_requested"

    project_level_signals = {"network_gate", "mcp_gate", "human_approval_required"}
    scope = "project-local" if any(item in project_level_signals for item in normalized_violations) else "session-local"
    approval_state = "approval_required" if scope == "project-local" else "auto_approved"
    assigned_agent = contract.get("assigned_agent") if isinstance(contract.get("assigned_agent"), dict) else {}
    runtime_options = contract.get("runtime_options") if isinstance(contract.get("runtime_options"), dict) else {}

    requested_capabilities = {
        "skills": ["continuation-hardening"],
        "mcp_servers": ["runtime-governance"] if "mcp_gate" in normalized_violations else [],
        "permission_changes": [],
        "runtime_bindings": [str(runtime_options.get("provider") or runtime_options.get("runner") or "codex")],
    }
    if "network_gate" in normalized_violations:
        requested_capabilities["permission_changes"].append("network.allow")
    if "tool_gate" in normalized_violations:
        requested_capabilities["permission_changes"].append("tool.allow")
    if "sampling_gate" in normalized_violations:
        requested_capabilities["permission_changes"].append("sampling.allow")
    if "human_approval_required" in normalized_violations:
        requested_capabilities["permission_changes"].append("approval.resume")

    request = {
        "version": "v1",
        "request_id": f"harness-{run_dir.name}",
        "scope": scope,
        "requested_by": {
            "role": str(assigned_agent.get("role") or "WORKER").strip() or "WORKER",
            "agent_id": str(assigned_agent.get("agent_id") or "agent-1").strip() or "agent-1",
        },
        "reason": (
            "Runtime completion governance detected policy-gate blockers and generated a harness evolution request "
            f"for {', '.join(normalized_violations)}."
        ),
        "requested_capabilities": requested_capabilities,
        "risk_level": "medium" if scope == "project-local" else "low",
        "approval_required": scope != "session-local",
        "rollback_plan": "Remove the temporary capability request and restore the current runtime/tool permission posture.",
        "validation_plan": "Rerun repo hygiene, targeted runtime tests, and the affected operator read-back after apply.",
    }
    return request, approval_state


def _build_dod_checker(
    *,
    required_checks: list[str],
    task_result: dict[str, Any] | None,
    test_report: dict[str, Any] | None,
    review_report: dict[str, Any] | None,
    run_dir: Path,
    status: str,
) -> dict[str, Any]:
    unmet_checks: list[str] = []
    for check_name in required_checks:
        ok, label = _check_required_item(
            check_name,
            task_result=task_result,
            test_report=test_report,
            review_report=review_report,
            run_dir=run_dir,
            status=status,
        )
        if not ok:
            unmet_checks.append(label)
    if str(status).upper() != "SUCCESS" and "run_status" not in unmet_checks:
        unmet_checks.append("run_status")
    if unmet_checks:
        return {
            "status": "failed",
            "summary": "Required completion checks are still missing or failed.",
            "required_checks": required_checks,
            "unmet_checks": unmet_checks,
        }
    return {
        "status": "passed",
        "summary": "All completion checks required by the current run passed.",
        "required_checks": required_checks,
        "unmet_checks": [],
    }


def _build_reply_auditor(
    *,
    status: str,
    failure_reason: str,
    dod_checker: dict[str, Any],
    unblock_tasks: list[dict[str, Any]],
) -> dict[str, Any]:
    signals: list[str] = []
    if str(status).upper() != "SUCCESS":
        signals.append("run_status_not_success")
    if failure_reason:
        signals.append("failure_reason_present")
    if dod_checker.get("status") != "passed":
        signals.append("dod_unmet")
    if unblock_tasks and signals:
        return {
            "status": "blocked",
            "summary": "The run ended with blocker signals and an unblock path is available.",
            "signals": signals,
        }
    if signals:
        return {
            "status": "needs_follow_up",
            "summary": "The run still needs follow-up before it can be treated as complete.",
            "signals": signals,
        }
    return {
        "status": "accepted",
        "summary": "The run result passed the current reply audit checks.",
        "signals": [],
    }


def _queue_unblock_tasks(
    unblock_tasks: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]] | None, str]:
    if not unblock_tasks:
        return None, ""
    updated: list[dict[str, Any]] = []
    selected_id = ""
    for index, task in enumerate(unblock_tasks):
        task_copy = dict(task)
        if index == 0:
            task_copy["status"] = "queued"
            selected_id = str(task_copy.get("unblock_task_id") or "")
        updated.append(task_copy)
    return updated, selected_id


def evaluate_completion_governance(
    *,
    contract: dict[str, Any],
    run_dir: Path,
    task_result: dict[str, Any] | None,
    test_report: dict[str, Any] | None,
    review_report: dict[str, Any] | None,
    status: str,
    failure_reason: str,
    generated_at: str,
) -> tuple[dict[str, Any], list[dict[str, Any]] | None]:
    planning_contracts = _normalize_records(_load_json_artifact(run_dir, "planning_worker_prompt_contracts.json"))
    unblock_tasks = _normalize_records(_load_json_artifact(run_dir, "planning_unblock_tasks.json"))
    required_checks = _collect_required_checks(planning_contracts, contract=contract)
    dod_checker = _build_dod_checker(
        required_checks=required_checks,
        task_result=task_result,
        test_report=test_report,
        review_report=review_report,
        run_dir=run_dir,
        status=status,
    )
    reply_auditor = _build_reply_auditor(
        status=status,
        failure_reason=failure_reason,
        dod_checker=dod_checker,
        unblock_tasks=unblock_tasks,
    )
    on_incomplete = _collect_policy_action(planning_contracts, "on_incomplete")
    on_blocked = _collect_policy_action(planning_contracts, "on_blocked")

    updated_unblock_tasks: list[dict[str, Any]] | None = None
    unblock_task_id = ""
    selected_action = "none"
    action_source = "none"
    overall_verdict: str
    continuation_summary: str

    if reply_auditor["status"] == "blocked" and on_blocked:
        selected_action = on_blocked
        action_source = "continuation_policy.on_blocked"
        updated_unblock_tasks, unblock_task_id = _queue_unblock_tasks(unblock_tasks)
        if updated_unblock_tasks:
            overall_verdict = "queue_unblock_task"
            continuation_summary = "The run is blocked. Queue the L0-managed unblock task before continuing."
        else:
            overall_verdict = "manual_triage"
            continuation_summary = "The run is blocked, but no persisted unblock task is available. Manual triage is required."
    elif reply_auditor["status"] == "needs_follow_up" and on_incomplete:
        selected_action = on_incomplete
        action_source = "continuation_policy.on_incomplete"
        overall_verdict = "continue_same_session"
        continuation_summary = "The run still needs follow-up. Continue the same session under the reply-auditor policy."
    elif reply_auditor["status"] == "accepted" and dod_checker["status"] == "passed":
        overall_verdict = "complete"
        continuation_summary = "All completion governance checks passed. No continuation is required."
    else:
        overall_verdict = "manual_triage"
        continuation_summary = "Completion governance could not select a safe automatic continuation path."

    context_pack_artifact = _build_context_pack_artifact(
        contract=contract,
        run_dir=run_dir,
        failure_reason=failure_reason,
        continuation_summary=continuation_summary,
        reply_auditor=reply_auditor,
    )
    harness_request_artifact, harness_policy_state = _derive_harness_request_artifact(
        contract=contract,
        task_result=task_result,
        run_dir=run_dir,
    )

    report = {
        "report_type": "completion_governance_report",
        "generated_at": generated_at,
        "authority": "completion-governance-runtime",
        "source": "finalize_run",
        "execution_authority": "task_contract",
        "overall_verdict": overall_verdict,
        "dod_checker": dod_checker,
        "reply_auditor": reply_auditor,
        "continuation_decision": {
            "status": "selected" if selected_action != "none" else "none",
            "selected_action": selected_action,
            "action_source": action_source,
            "unblock_task_id": unblock_task_id,
            "summary": continuation_summary,
        },
        "context_pack": {
            "status": "generated" if context_pack_artifact else "not_requested",
            "summary": (
                f"Generated {context_pack_artifact['pack_id']} for fallback handoff."
                if context_pack_artifact
                else "No fallback Context Pack was requested for this run."
            ),
        },
        "harness_request": {
            "status": harness_policy_state,
            "summary": (
                f"Generated {harness_request_artifact['request_id']} with {harness_policy_state} policy verdict."
                if harness_request_artifact
                else "No harness evolution request was needed for this run."
            ),
        },
    }
    return report, updated_unblock_tasks, context_pack_artifact, harness_request_artifact
