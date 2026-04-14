from __future__ import annotations

import json
import sys
import types

from openvibecoding_orch.services.operator_copilot import (
    generate_execution_plan_copilot_brief,
    generate_run_operator_copilot_brief,
    generate_workflow_operator_copilot_brief,
)


def _install_agents_module(monkeypatch, *, final_output: str) -> None:
    class DummyAgent:
        def __init__(self, name: str, instructions: str, model: str, mcp_servers: list) -> None:
            self.name = name
            self.instructions = instructions
            self.model = model
            self.mcp_servers = mcp_servers

    class DummyRunner:
        @staticmethod
        async def run(_agent, _prompt):
            return types.SimpleNamespace(final_output=final_output)

    agents_mod = types.ModuleType("agents")
    agents_mod.Agent = DummyAgent
    agents_mod.Runner = DummyRunner
    agents_mod.set_default_openai_api = lambda *_args, **_kwargs: None
    agents_mod.set_default_openai_client = lambda *_args, **_kwargs: None
    monkeypatch.setitem(sys.modules, "agents", agents_mod)


def test_generate_operator_copilot_brief_returns_structured_report(monkeypatch) -> None:
    _install_agents_module(
        monkeypatch,
        final_output=json.dumps(
            {
                "summary": "The run is blocked by a diff gate and still needs operator review.",
                "likely_cause": "The diff gate is the dominant blocker.",
                "compare_takeaway": "Compare found one material delta against the baseline.",
                "proof_takeaway": "Proof artifacts exist but should not be promoted yet.",
                "incident_takeaway": "Incident summary points to a governance gate.",
                "queue_takeaway": "Queue state is stable and not the immediate blocker.",
                "approval_takeaway": "No human approval is pending right now.",
                "recommended_actions": [
                    "Inspect the diff gate output.",
                    "Replay only after fixing the blocking violation.",
                ],
                "top_risks": ["Diff gate failure"],
                "limitations": ["V1 explains current truth but does not execute recovery actions."],
            }
        ),
    )

    monkeypatch.setattr(
        "openvibecoding_orch.services.operator_copilot.get_runner_config",
        lambda: types.SimpleNamespace(
            agents_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            agents_api="responses",
            agents_model="gemini-2.5-flash",
            gemini_api_key="gemini-key",
            openai_api_key="",
            anthropic_api_key="",
            equilibrium_api_key="",
        ),
    )
    monkeypatch.setattr("openvibecoding_orch.services.operator_copilot.resolve_runtime_provider_from_env", lambda: "gemini")
    monkeypatch.setattr(
        "openvibecoding_orch.services.operator_copilot.resolve_provider_credentials",
        lambda: types.SimpleNamespace(gemini_api_key="gemini-key", openai_api_key="", anthropic_api_key="", equilibrium_api_key=""),
    )
    monkeypatch.setattr("openvibecoding_orch.services.operator_copilot.build_llm_compat_client", lambda **_kwargs: object())

    report = generate_run_operator_copilot_brief(
        "run-1",
        get_run_fn=lambda _run_id: {
            "run_id": "run-1",
            "status": "FAILED",
            "task_id": "task-1",
            "manifest": {"workflow": {"workflow_id": "wf-1"}},
        },
        get_reports_fn=lambda _run_id: [
            {"name": "run_compare_report.json", "data": {"compare_summary": {"mismatched_count": 1}}},
            {"name": "proof_pack.json", "data": {"summary": "proof ready", "next_action": "review proof"}},
            {"name": "incident_pack.json", "data": {"summary": "gate blocked", "next_action": "review gate"}},
        ],
        get_workflow_fn=lambda _workflow_id: {"workflow": {"workflow_id": "wf-1", "status": "blocked", "objective": "Ship Prompt 4"}},
        list_queue_fn=lambda **_kwargs: [{"task_id": "task-queue", "eligible": True, "sla_state": "on_track"}],
        list_pending_approvals_fn=lambda: [],
        list_diff_gate_fn=lambda: [{"run_id": "run-1", "status": "FAILED", "failure_reason": "diff gate rejected"}],
    )

    assert report["report_type"] == "operator_copilot_brief"
    assert report["status"] == "OK"
    assert report["run_id"] == "run-1"
    assert report["workflow_id"] == "wf-1"
    assert "Diff gate" in report["likely_cause"] or "diff gate" in report["likely_cause"].lower()
    assert len(report["recommended_actions"]) == 2
    assert "run reports" in report["used_truth_surfaces"]


def test_generate_operator_copilot_brief_fails_closed_without_agents(monkeypatch) -> None:
    monkeypatch.setattr("openvibecoding_orch.services.operator_copilot._agents_available", lambda: False)

    report = generate_run_operator_copilot_brief(
        "run-2",
        get_run_fn=lambda _run_id: {"run_id": "run-2", "status": "FAILED", "manifest": {}},
        get_reports_fn=lambda _run_id: [],
        get_workflow_fn=lambda _workflow_id: {},
        list_queue_fn=lambda **_kwargs: [],
        list_pending_approvals_fn=lambda: [],
        list_diff_gate_fn=lambda: [],
    )

    assert report["status"] == "UNAVAILABLE"
    assert report["provider"] == "unavailable"


def test_generate_workflow_operator_copilot_brief_returns_structured_report(monkeypatch) -> None:
    _install_agents_module(
        monkeypatch,
        final_output=json.dumps(
            {
                "summary": "The workflow case is blocked by the latest run and still needs operator review.",
                "likely_cause": "The latest linked run is blocked by a gate and proof is incomplete.",
                "compare_takeaway": "The latest run still differs from its baseline.",
                "proof_takeaway": "Proof is present but should not be treated as final yet.",
                "incident_takeaway": "One truth surface is still partial and needs review.",
                "queue_takeaway": "Queue posture is stable, with one eligible item ready now.",
                "approval_takeaway": "No human approval is blocking the workflow at this moment.",
                "recommended_actions": [
                    "Review the latest linked run before moving the workflow forward.",
                ],
                "top_risks": ["Latest run gap"],
                "limitations": ["Workflow brief stays explain-only."],
            }
        ),
    )
    monkeypatch.setattr(
        "openvibecoding_orch.services.operator_copilot.get_runner_config",
        lambda: types.SimpleNamespace(
            agents_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            agents_api="responses",
            agents_model="gemini-2.5-flash",
            gemini_api_key="gemini-key",
            openai_api_key="",
            anthropic_api_key="",
            equilibrium_api_key="",
        ),
    )
    monkeypatch.setattr("openvibecoding_orch.services.operator_copilot.resolve_runtime_provider_from_env", lambda: "gemini")
    monkeypatch.setattr(
        "openvibecoding_orch.services.operator_copilot.resolve_provider_credentials",
        lambda: types.SimpleNamespace(gemini_api_key="gemini-key", openai_api_key="", anthropic_api_key="", equilibrium_api_key=""),
    )
    monkeypatch.setattr("openvibecoding_orch.services.operator_copilot.build_llm_compat_client", lambda **_kwargs: object())

    report = generate_workflow_operator_copilot_brief(
        "wf-1",
        get_workflow_fn=lambda _workflow_id: {
            "workflow": {"workflow_id": "wf-1", "status": "BLOCKED", "objective": "Ship Prompt 7"},
            "runs": [{"run_id": "run-1", "created_at": "2026-03-31T12:00:00Z"}],
        },
        get_run_fn=lambda _run_id: {"run_id": "run-1", "status": "FAILED", "failure_reason": "gate blocked"},
        get_reports_fn=lambda _run_id: [
            {"name": "run_compare_report.json", "data": {"compare_summary": {"mismatched_count": 2}}},
            {"name": "proof_pack.json", "data": {"summary": "proof exists", "next_action": "review proof"}},
            {"name": "incident_pack.json", "data": {"summary": "gate blocked", "next_action": "review gate"}},
        ],
        list_queue_fn=lambda **_kwargs: [{"task_id": "task-queue", "eligible": True, "sla_state": "on_track"}],
        list_pending_approvals_fn=lambda: [],
        list_diff_gate_fn=lambda: [{"run_id": "run-1", "status": "FAILED"}],
    )

    assert report["scope"] == "workflow"
    assert report["workflow_id"] == "wf-1"
    assert report["run_id"] == "run-1"
    assert report["status"] == "OK"


def test_generate_execution_plan_copilot_brief_returns_structured_report(monkeypatch) -> None:
    _install_agents_module(
        monkeypatch,
        final_output=json.dumps(
            {
                "summary": "The current Flight Plan is safe to review but still has one approval gate to confirm.",
                "risk_takeaway": "Manual approval is the main pre-run risk gate.",
                "capability_takeaway": "Search and approval triggers exist because the plan needs external evidence and a protected execution path.",
                "approval_takeaway": "Manual approval is likely before completion.",
                "recommended_actions": ["Confirm the approval expectation before starting execution."],
                "top_risks": ["Manual approval likely"],
                "limitations": ["Flight Plan brief is advisory only."],
                "provider": "gemini",
                "model": "gemini-2.5-flash",
            }
        ),
    )
    monkeypatch.setattr(
        "openvibecoding_orch.services.operator_copilot.get_runner_config",
        lambda: types.SimpleNamespace(
            agents_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            agents_api="responses",
            agents_model="gemini-2.5-flash",
            gemini_api_key="gemini-key",
            openai_api_key="",
            anthropic_api_key="",
            equilibrium_api_key="",
        ),
    )
    monkeypatch.setattr("openvibecoding_orch.services.operator_copilot.resolve_runtime_provider_from_env", lambda: "gemini")
    monkeypatch.setattr(
        "openvibecoding_orch.services.operator_copilot.resolve_provider_credentials",
        lambda: types.SimpleNamespace(gemini_api_key="gemini-key", openai_api_key="", anthropic_api_key="", equilibrium_api_key=""),
    )
    monkeypatch.setattr("openvibecoding_orch.services.operator_copilot.build_llm_compat_client", lambda **_kwargs: object())

    report = generate_execution_plan_copilot_brief(
        {
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
        }
    )

    assert report["report_type"] == "flight_plan_copilot_brief"
    assert report["status"] == "OK"


def test_operator_copilot_switchyard_runtime_forces_chat_mode_and_placeholder_key(monkeypatch) -> None:
    _install_agents_module(
        monkeypatch,
        final_output=json.dumps(
            {
                "summary": "Switchyard adapter works.",
                "likely_cause": "No issue.",
                "compare_takeaway": "Compare clean.",
                "proof_takeaway": "Proof clean.",
                "incident_takeaway": "No incident.",
                "queue_takeaway": "Queue stable.",
                "approval_takeaway": "No approval pending.",
                "recommended_actions": ["Continue."],
                "top_risks": [],
                "limitations": [],
            }
        ),
    )
    records: dict[str, object] = {}

    def _build_client(**kwargs):
        records["client_kwargs"] = kwargs
        return object()

    agents_mod = sys.modules["agents"]
    agents_mod.set_default_openai_api = lambda mode: records.setdefault("api_mode", mode)
    agents_mod.set_default_openai_client = lambda client: records.setdefault("client", client)

    monkeypatch.setattr(
        "openvibecoding_orch.services.operator_copilot.get_runner_config",
        lambda: types.SimpleNamespace(
            agents_base_url="http://127.0.0.1:4010/v1/runtime/invoke",
            agents_api="responses",
            agents_model="chatgpt/gpt-4o",
            gemini_api_key="",
            openai_api_key="",
            anthropic_api_key="",
            equilibrium_api_key="",
        ),
    )
    monkeypatch.setattr("openvibecoding_orch.services.operator_copilot.resolve_runtime_provider_from_env", lambda: "openai")
    monkeypatch.setattr(
        "openvibecoding_orch.services.operator_copilot.resolve_provider_credentials",
        lambda: types.SimpleNamespace(gemini_api_key="", openai_api_key="", anthropic_api_key="", equilibrium_api_key=""),
    )
    monkeypatch.setattr("openvibecoding_orch.services.operator_copilot.build_llm_compat_client", _build_client)

    report = generate_run_operator_copilot_brief(
        "run-1",
        get_run_fn=lambda _run_id: {
            "run_id": "run-1",
            "status": "FAILED",
            "task_id": "task-1",
            "manifest": {"workflow": {"workflow_id": "wf-1"}},
        },
        get_reports_fn=lambda _run_id: [],
        get_workflow_fn=lambda _workflow_id: {"workflow": {"workflow_id": "wf-1", "status": "blocked", "objective": "Switchyard"}},
        list_queue_fn=lambda **_kwargs: [],
        list_pending_approvals_fn=lambda: [],
        list_diff_gate_fn=lambda: [],
    )

    assert report["status"] == "OK"
    assert records["api_mode"] == "chat_completions"
    assert records["client_kwargs"] == {
        "api_key": "switchyard-local",
        "base_url": "http://127.0.0.1:4010/v1/runtime/invoke",
        "provider": "openai",
    }
