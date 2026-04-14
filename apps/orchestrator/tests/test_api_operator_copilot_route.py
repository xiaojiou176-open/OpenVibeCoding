from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from openvibecoding_orch.api import main as api_main

from .helpers.api_main_test_io import _write_contract, _write_events, _write_manifest, _write_report


def test_api_operator_copilot_brief_route_returns_grounded_brief(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))

    run_dir = runs_root / "run_operator"
    _write_manifest(
        run_dir,
        {
            "run_id": "run_operator",
            "task_id": "task_operator",
            "status": "FAILURE",
            "created_at": "2026-03-31T12:00:00Z",
            "failure_reason": "diff gate rejected",
            "workflow": {
                "workflow_id": "wf-operator",
                "task_queue": "openvibecoding-orch",
                "namespace": "default",
                "status": "FAILED",
            },
        },
    )
    _write_contract(run_dir, {"task_id": "task_operator", "allowed_paths": ["apps/dashboard"]})
    _write_events(
        run_dir,
        [
            json.dumps({"event": "WORKFLOW_BOUND", "context": {"workflow_id": "wf-operator"}}),
            json.dumps({"event": "DIFF_GATE_RESULT", "context": {"result": "REJECTED"}}),
        ],
    )
    _write_report(run_dir, "run_compare_report.json", {"compare_summary": {"mismatched_count": 1}})
    _write_report(run_dir, "proof_pack.json", {"summary": "Proof exists", "next_action": "Review proof"})
    _write_report(run_dir, "incident_pack.json", {"summary": "Gate blocked", "next_action": "Review gate"})

    monkeypatch.setattr(
        "openvibecoding_orch.services.operator_copilot._build_ai_brief",
        lambda _prompt: {
            "summary": "The run is blocked by a diff gate and needs operator review.",
            "likely_cause": "Diff gate rejection is the current blocker.",
            "compare_takeaway": "One material delta remains against the baseline.",
            "proof_takeaway": "Proof exists but should not be promoted yet.",
            "incident_takeaway": "Incident context points to a governance gate.",
            "queue_takeaway": "Queue posture is stable and not the main issue.",
            "approval_takeaway": "No pending approval is attached right now.",
            "recommended_actions": ["Review the diff gate output.", "Replay only after fixing the violation."],
            "top_risks": ["Diff gate rejection"],
            "limitations": ["V1 is explain-only and does not execute recovery actions."],
            "provider": "gemini",
            "model": "gemini-2.5-flash",
        },
    )

    client = TestClient(api_main.app)
    response = client.post("/api/runs/run_operator/copilot-brief", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["report_type"] == "operator_copilot_brief"
    assert payload["subject_id"] == "wf-operator"
    assert payload["run_id"] == "run_operator"
    assert payload["workflow_id"] == "wf-operator"
    assert payload["status"] == "OK"
    assert payload["provider"] == "gemini"


def test_api_workflow_operator_copilot_brief_route_returns_grounded_brief(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))

    run_dir = runs_root / "run_workflow_operator"
    _write_manifest(
        run_dir,
        {
            "run_id": "run_workflow_operator",
            "task_id": "task_operator",
            "status": "FAILURE",
            "created_at": "2026-03-31T12:00:00Z",
            "failure_reason": "diff gate rejected",
            "workflow": {
                "workflow_id": "wf-operator",
                "task_queue": "openvibecoding-orch",
                "namespace": "default",
                "status": "FAILED",
            },
        },
    )
    _write_contract(run_dir, {"task_id": "task_operator", "allowed_paths": ["apps/dashboard"]})
    _write_events(run_dir, [json.dumps({"event": "WORKFLOW_BOUND", "context": {"workflow_id": "wf-operator"}})])
    _write_report(run_dir, "run_compare_report.json", {"compare_summary": {"mismatched_count": 1}})
    _write_report(run_dir, "proof_pack.json", {"summary": "Proof exists", "next_action": "Review proof"})
    _write_report(run_dir, "incident_pack.json", {"summary": "Gate blocked", "next_action": "Review gate"})

    monkeypatch.setattr(
        "openvibecoding_orch.services.operator_copilot._build_ai_brief",
        lambda _prompt: {
            "summary": "The workflow case is blocked by its latest linked run.",
            "likely_cause": "The latest run is still blocked by the diff gate.",
            "compare_takeaway": "The latest run still differs from its baseline.",
            "proof_takeaway": "Proof exists but should not be shared yet.",
            "incident_takeaway": "One operator review step is still open.",
            "queue_takeaway": "Queue posture is stable and not the main issue.",
            "approval_takeaway": "No pending approval is attached right now.",
            "recommended_actions": ["Inspect the latest run before moving the workflow forward."],
            "top_risks": ["Latest run gap"],
            "limitations": ["Workflow brief is explain-only."],
            "provider": "gemini",
            "model": "gemini-2.5-flash",
        },
    )

    client = TestClient(api_main.app)
    response = client.post("/api/workflows/wf-operator/copilot-brief", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["scope"] == "workflow"
    assert payload["subject_id"] == "wf-operator"
    assert payload["workflow_id"] == "wf-operator"
    assert payload["status"] == "OK"


def test_api_preview_intake_copilot_brief_route_returns_advisory_brief(monkeypatch) -> None:
    monkeypatch.setattr(
        "openvibecoding_orch.services.operator_copilot._build_ai_flight_plan_brief",
        lambda _prompt: {
            "summary": "The current Flight Plan is safe to review but still has one approval gate to confirm.",
            "risk_takeaway": "Manual approval is the main pre-run risk gate.",
            "capability_takeaway": "Search and approval triggers exist because this plan needs external evidence and a protected execution path.",
            "approval_takeaway": "Manual approval is likely before completion.",
            "recommended_actions": ["Confirm the approval expectation before starting execution."],
            "top_risks": ["Manual approval likely"],
            "limitations": ["Flight Plan brief is advisory only."],
            "provider": "gemini",
            "model": "gemini-2.5-flash",
        },
    )

    client = TestClient(api_main.app)
    response = client.post(
        "/api/intake/preview/copilot-brief",
        json={
            "report_type": "execution_plan_report",
            "generated_at": "2026-03-31T12:00:00Z",
            "objective": "Queue the latest workflow case run",
            "summary": "The next run will stay inside apps/dashboard.",
            "questions": [],
            "warnings": ["Manual approval may be required"],
            "notes": ["This preview is advisory only."],
            "assigned_role": "TECH_LEAD",
            "allowed_paths": ["apps/dashboard"],
            "acceptance_tests": [{"cmd": "pnpm --dir apps/dashboard typecheck"}],
            "search_queries": ["workflow queue mutation"],
            "predicted_reports": ["task_result.json"],
            "predicted_artifacts": ["patch.diff"],
            "requires_human_approval": True,
            "contract_preview": {"assigned_agent": {"role": "WORKER"}},
            "intake_id": "pm-1",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["report_type"] == "flight_plan_copilot_brief"
    assert payload["risk_takeaway"] == "Manual approval is the main pre-run risk gate."
    assert payload["capability_takeaway"].startswith("Search and approval triggers exist")
    assert payload["status"] == "OK"


def test_api_preview_operator_copilot_brief_route_returns_advisory_brief(monkeypatch) -> None:
    monkeypatch.setattr(
        "openvibecoding_orch.services.operator_copilot._build_ai_flight_plan_brief",
        lambda _prompt: {
            "summary": "The Flight Plan is ready for review but still has one approval gate before execution.",
            "risk_takeaway": "Manual approval is the main pre-run risk gate.",
            "capability_takeaway": "Search and browser triggers exist because the plan needs evidence collection.",
            "approval_takeaway": "A human should confirm approval posture before starting execution.",
            "recommended_actions": ["Confirm the highest-risk gate before the first run."],
            "top_risks": ["Manual approval likely"],
            "limitations": ["This brief is advisory only and does not replace run truth."],
            "provider": "gemini",
            "model": "gemini-2.5-flash",
        },
    )

    client = TestClient(api_main.app)
    response = client.post(
        "/api/pm/intake/preview/copilot-brief",
        json={
            "report_type": "execution_plan_report",
            "generated_at": "2026-03-31T12:00:00Z",
            "objective": "Queue the latest workflow case run",
            "summary": "The next run will stay inside apps/dashboard.",
            "questions": [],
            "warnings": ["Manual approval may be required"],
            "notes": ["This preview is advisory only."],
            "assigned_role": "TECH_LEAD",
            "allowed_paths": ["apps/dashboard"],
            "acceptance_tests": [{"cmd": "pnpm --dir apps/dashboard typecheck"}],
            "search_queries": ["workflow queue mutation"],
            "predicted_reports": ["task_result.json"],
            "predicted_artifacts": ["patch.diff"],
            "requires_human_approval": True,
            "contract_preview": {"assigned_agent": {"role": "WORKER"}},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["report_type"] == "flight_plan_copilot_brief"
    assert payload["risk_takeaway"] == "Manual approval is the main pre-run risk gate."
    assert payload["capability_takeaway"].startswith("Search and browser triggers exist")
    assert payload["status"] == "OK"
