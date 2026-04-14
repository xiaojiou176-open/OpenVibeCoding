import hashlib
import json
from pathlib import Path

import pytest

from openvibecoding_orch.contract.validator import ContractValidator, resolve_agent_registry_path


def _output_schema_artifacts(role: str = "worker") -> list[dict]:
    schema_root = Path(__file__).resolve().parents[3] / "schemas"
    schema_name = "agent_task_result.v1.json"
    if role.lower() in {"reviewer"}:
        schema_name = "review_report.v1.json"
    if role.lower() in {"test", "test_runner"}:
        schema_name = "test_report.v1.json"
    schema_path = schema_root / schema_name
    sha = hashlib.sha256(schema_path.read_bytes()).hexdigest()
    return [
        {
            "name": f"output_schema.{role.lower()}",
            "uri": f"schemas/{schema_name}",
            "sha256": sha,
        }
    ]


def _valid_contract() -> dict:
    return {
        "task_id": "task_test_01",
        "owner_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "assigned_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "inputs": {"spec": "test", "artifacts": _output_schema_artifacts("worker")},
        "required_outputs": [{"name": "out.txt", "type": "file", "acceptance": "ok"}],
        "allowed_paths": ["openvibecoding"],
        "forbidden_actions": ["rm -rf"],
        "acceptance_tests": [{"name": "noop", "cmd": "echo hello", "must_pass": True}],
        "tool_permissions": {
            "filesystem": "read-only",
            "shell": "on-request",
            "network": "deny",
            "mcp_tools": ["codex"],
        },
        "mcp_tool_set": ["01-filesystem"],
        "timeout_retry": {"timeout_sec": 1, "max_retries": 1, "retry_backoff_sec": 0},
        "rollback": {"strategy": "git_reset_hard", "baseline_ref": "HEAD"},
        "evidence_links": [],
        "log_refs": {"run_id": "", "paths": {}},
    }


def test_contract_schema_pass(tmp_path: Path):
    validator = ContractValidator()
    contract = _valid_contract()
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(contract), encoding="utf-8")
    assert validator.validate_contract_file(path)["task_id"] == "task_test_01"


def test_contract_schema_missing_required_field():
    validator = ContractValidator()
    contract = _valid_contract()
    contract.pop("task_id")
    with pytest.raises(ValueError):
        validator.validate_contract(contract)


def test_contract_schema_unknown_field():
    validator = ContractValidator()
    contract = _valid_contract()
    contract["unknown_field"] = "nope"
    with pytest.raises(ValueError):
        validator.validate_contract(contract)


def test_contract_schema_runtime_provider_valid_values_pass():
    validator = ContractValidator()
    for provider in ("gemini", "openai", "anthropic", "cliproxyapi"):
        contract = _valid_contract()
        contract["runtime_options"] = {"provider": provider}
        validated = validator.validate_contract(contract)
        assert validated["runtime_options"]["provider"] == provider


def test_contract_schema_runtime_provider_invalid_value_fails():
    validator = ContractValidator()
    contract = _valid_contract()
    contract["runtime_options"] = {"provider": ""}
    with pytest.raises(ValueError):
        validator.validate_contract(contract)


def test_contract_schema_runner_claude_with_mcp_first_pass():
    validator = ContractValidator()
    contract = _valid_contract()
    contract["runtime_options"] = {"runner": "claude", "execution": {"mcp_first": True}}
    validated = validator.validate_contract(contract)
    assert validated["runtime_options"]["runner"] == "claude"
    assert validated["runtime_options"]["execution"]["mcp_first"] is True


def test_review_report_schema_pass():
    validator = ContractValidator()
    payload = {
        "run_id": "run-0001",
        "task_id": "task_test_01",
        "reviewer": {"role": "REVIEWER", "agent_id": "reviewer-1"},
        "reviewed_at": "2024-01-01T00:00:00Z",
        "verdict": "PASS",
        "summary": "ok",
        "scope_check": {"passed": True, "violations": []},
        "evidence": [],
        "produced_diff": False,
    }
    assert validator.validate_report(payload, "review_report.v1.json")["verdict"] == "PASS"


def test_test_report_schema_pass():
    validator = ContractValidator()
    payload = {
        "run_id": "run-0001",
        "task_id": "task_test_01",
        "runner": {"role": "TEST_RUNNER", "agent_id": "runner-1"},
        "started_at": "2024-01-01T00:00:00Z",
        "finished_at": "2024-01-01T00:01:00Z",
        "status": "PASS",
        "commands": [
            {
                "name": "echo",
                "cmd_argv": ["echo", "hello"],
                "must_pass": True,
                "timeout_sec": 600,
                "exit_code": 0,
                "duration_sec": 0.1,
                "stdout": {
                    "name": "stdout",
                    "path": "tests/stdout.log",
                    "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                },
                "stderr": {
                    "name": "stderr",
                    "path": "tests/stderr.log",
                    "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                },
            }
        ],
        "artifacts": [],
    }
    assert validator.validate_report(payload, "test_report.v1.json")["status"] == "PASS"


def test_new_operator_report_and_task_pack_schemas_pass() -> None:
    validator = ContractValidator()
    execution_plan = {
        "report_type": "execution_plan_report",
        "generated_at": "2026-03-29T00:00:00Z",
        "task_template": "news_digest",
        "objective": "Build a public-read-only digest.",
        "summary": "news_digest will compile into a worker-owned execution contract.",
        "questions": [],
        "warnings": [],
        "notes": [],
        "assigned_role": "WORKER",
        "allowed_paths": ["apps/dashboard"],
        "acceptance_tests": [],
        "search_queries": ["Seattle tech and AI"],
        "predicted_reports": ["news_digest_result.json"],
        "predicted_artifacts": ["search_requests.json"],
        "requires_human_approval": False,
        "contract_preview": {"allowed_paths": ["apps/dashboard"]},
    }
    assert validator.validate_report(execution_plan, "execution_plan_report.v1.json")["report_type"] == "execution_plan_report"

    approval_pack = {
        "report_type": "approval_pack",
        "run_id": "run-approval-1",
        "status": "pending",
        "summary": "Manual approval required before execution can continue.",
        "reasons": ["network access requested"],
        "actions": ["Approve", "Reject"],
        "verify_steps": ["Review the contract preview"],
        "resume_step": "resume_execution",
    }
    assert validator.validate_report(approval_pack, "approval_pack.v1.json")["report_type"] == "approval_pack"

    incident_pack = {
        "report_type": "incident_pack",
        "run_id": "run-incident-1",
        "status": "failed",
        "summary": "The run failed during verification.",
        "failure_class": "verification_failed",
        "failure_code": "VERIFY_001",
        "failure_stage": "verify",
        "failure_reason": "Tests failed",
        "root_event": "TEST_FAILED",
        "next_action": "Inspect the failing test output.",
        "blocking_events": ["TEST_FAILED"],
    }
    assert validator.validate_report(incident_pack, "incident_pack.v1.json")["report_type"] == "incident_pack"

    proof_pack = {
        "report_type": "proof_pack",
        "run_id": "run-proof-1",
        "task_template": "news_digest",
        "primary_report": "news_digest_result.json",
        "summary": "This public task slice completed successfully and produced reusable proof artifacts.",
        "result_status": "SUCCESS",
        "proof_ready": True,
        "evidence_refs": {"raw": "raw.json", "verification": "verification.json"},
        "next_action": "Review the primary report and evidence bundle before sharing the public proof output.",
    }
    assert validator.validate_report(proof_pack, "proof_pack.v1.json")["report_type"] == "proof_pack"

    run_compare_report = {
        "report_type": "run_compare_report",
        "run_id": "run-current-1",
        "baseline_run_id": "run-baseline-1",
        "status": "ok",
        "compare_summary": {
            "mismatched_count": 0,
            "missing_count": 0,
            "extra_count": 0,
            "missing_reports_count": 0,
            "failed_report_checks_count": 0,
            "evidence_ok": True,
            "llm_params_ok": True,
            "llm_snapshot_ok": True,
        },
    }
    assert validator.validate_report(run_compare_report, "run_compare_report.v1.json")["report_type"] == "run_compare_report"

    wave_plan = {
        "version": "v1",
        "wave_id": "wave-1",
        "objective": "Ship the L0 command tower preview.",
        "owner_agent": {"role": "PM", "agent_id": "agent-1"},
        "execution_mode": "long_running",
        "wake_policy_ref": "policies/control_plane_runtime_policy.json#/wake_policy",
        "completion_policy_ref": "policies/control_plane_runtime_policy.json#/wave_completion_policy",
        "worker_count": 1,
        "worker_plans": [
            {
                "prompt_contract_id": "worker-prompt-1",
                "assigned_role": "WORKER",
                "spec": "Implement the preview artifact.",
                "allowed_paths": ["apps/orchestrator/src"],
                "acceptance_checks": ["repo_hygiene"],
                "mcp_tools": ["codex"],
            }
        ],
    }
    assert validator.validate_report(wave_plan, "wave_plan.v1.json")["wave_id"] == "wave-1"

    worker_prompt_contract = {
        "version": "v1",
        "prompt_contract_id": "worker-prompt-1",
        "objective": "Ship the preview artifact.",
        "scope": "Implement the preview artifact inside apps/orchestrator/src.",
        "assigned_agent": {"role": "WORKER", "agent_id": "agent-1"},
        "reading_list": {"required": ["contract_preview"], "optional": ["search query"]},
        "done_definition": {
            "summary": "Finish the scoped worker assignment and satisfy acceptance checks.",
            "acceptance_checks": ["repo_hygiene"],
        },
        "constraints": ["public-read-only-sources"],
        "allowed_actions": ["filesystem:workspace-write", "mcp:codex"],
        "blocked_when": ["scope evidence is insufficient"],
        "deliverables": [{"name": "task_result.json", "type": "report"}],
        "escalation_policy": {"owner": "L0", "trigger": "scope blocker or authority mismatch"},
        "continuation_policy": {
            "on_incomplete": "reply_auditor_reprompt_and_continue_same_session",
            "on_blocked": "spawn_independent_temporary_unblock_task",
        },
        "verification_requirements": ["repo_hygiene"],
        "forbidden_actions": ["git push"],
    }
    assert validator.validate_report(worker_prompt_contract, "worker_prompt_contract.v1.json")["prompt_contract_id"] == "worker-prompt-1"

    unblock_task = {
        "version": "v1",
        "unblock_task_id": "unblock-worker-prompt-1",
        "source_prompt_contract_id": "worker-prompt-1",
        "objective": "Unblock the scoped worker assignment for Ship the preview artifact.",
        "scope_hint": "Implement the preview artifact inside apps/orchestrator/src.",
        "assigned_agent": {"role": "WORKER", "agent_id": "agent-1"},
        "owner": "L0",
        "mode": "independent_temporary_task",
        "status": "proposed",
        "trigger": "spawn_independent_temporary_unblock_task",
        "reason": "an external blocker requires an L0-managed unblock task",
        "verification_requirements": ["repo_hygiene"],
    }
    assert validator.validate_report(unblock_task, "unblock_task.v1.json")["unblock_task_id"] == "unblock-worker-prompt-1"

    context_pack = {
        "version": "v1",
        "pack_id": "ctx-pack-1",
        "role_scope": "L1",
        "source_session_id": "session-1",
        "source_role": "L1-Worker",
        "trigger_reason": "context_pressure",
        "global_state_summary": "The worker is 80 percent done and needs a clean handoff.",
        "actor_handoff_summary": "Continue the same scope and keep the queue posture stable.",
        "required_reads": ["contract_preview", "latest workflow case"],
        "optional_reads": ["incident notes"],
        "conversation_exports": ["transcript.md"],
        "artifact_refs": ["task_result.json"],
    }
    assert validator.validate_report(context_pack, "context_pack.v1.json")["pack_id"] == "ctx-pack-1"

    harness_request = {
        "version": "v1",
        "request_id": "harness-1",
        "scope": "project-local",
        "requested_by": {"role": "WORKER", "agent_id": "agent-1"},
        "reason": "Need an MCP to unblock the queue inspection path.",
        "requested_capabilities": {
            "skills": ["queue-inspector"],
            "mcp_servers": ["queue-control"],
            "permission_changes": ["github.merge"],
            "runtime_bindings": ["codex"],
        },
        "risk_level": "medium",
        "approval_required": True,
        "rollback_plan": "Remove the MCP server and restore the previous runtime binding.",
        "validation_plan": "Run repo hygiene and a queue-focused smoke test after apply.",
    }
    assert validator.validate_report(harness_request, "harness_request.v1.json")["request_id"] == "harness-1"

    completion_governance_report = {
        "report_type": "completion_governance_report",
        "generated_at": "2026-04-12T21:00:00Z",
        "authority": "completion-governance-runtime",
        "source": "finalize_run",
        "execution_authority": "task_contract",
        "overall_verdict": "queue_unblock_task",
        "dod_checker": {
            "status": "failed",
            "summary": "Required completion checks are still missing or failed.",
            "required_checks": ["repo_hygiene", "test_report"],
            "unmet_checks": ["test_report", "run_status"],
        },
        "reply_auditor": {
            "status": "blocked",
            "summary": "The run ended with blocker signals and an unblock path is available.",
            "signals": ["run_status_not_success", "dod_unmet"],
        },
        "continuation_decision": {
            "status": "selected",
            "selected_action": "spawn_independent_temporary_unblock_task",
            "action_source": "continuation_policy.on_blocked",
            "unblock_task_id": "unblock-worker-prompt-1",
            "summary": "The run is blocked. Queue the L0-managed unblock task before continuing.",
        },
        "context_pack": {
            "status": "not_wired",
            "summary": "Context Pack remains fallback-only, but no runtime producer/consumer is wired into finalize_run yet.",
        },
        "harness_request": {
            "status": "not_wired",
            "summary": "Harness Request has a schema home, but no request/apply lifecycle is wired into this run finalizer yet.",
        },
    }
    assert (
        validator.validate_report(
            completion_governance_report,
            "completion_governance_report.v1.json",
        )["overall_verdict"]
        == "queue_unblock_task"
    )

    control_plane_runtime_policy = {
        "version": "v1",
        "product_identity": {
            "title": "OpenVibeCoding L0 Command Tower",
            "one_sentence": "OpenVibeCoding is the command tower for AI engineering.",
            "primary_execution_bases": ["Codex", "Claude Code"],
            "reference_only_systems": ["OpenClaw"],
        },
        "hierarchy_axis": ["L0", "L1", "L2"],
        "role_axis": {"model": "work_type", "examples": ["Planner"], "customizable": True},
        "session_policy": {
            "default_mode": "long_running",
            "context_pack_mode": "fallback_only",
            "degradation_signals": ["repetition", "half_done_report", "context_contamination"],
            "degradation_responses": {
                "repetition": "corrective_reprompt",
                "half_done_report": "structured_self_check",
                "context_contamination": "handoff_or_new_session",
            },
            "context_pack_triggers": ["context_pressure", "contamination", "role_switch", "phase_switch", "repetition", "distortion"],
        },
        "wake_policy": {
            "primary_mode": "event_driven",
            "fallback_mode": "polling",
            "active_wave_interval_seconds": 60,
            "idle_interval_min_seconds": 300,
            "idle_interval_max_seconds": 600,
        },
        "wave_completion_policy": {
            "requires_all_workers_complete": True,
            "requires_no_open_blockers": True,
            "final_closeout_authority": "upper_layer_verdict",
        },
        "planner_artifacts": {"tier_1": "wave_plan", "tier_2": "worker_prompt_contract"},
        "completion_governance": {
            "components": ["dod_checker", "reply_auditor", "continuation_policy"],
            "task_type_layered": True,
        },
        "unblock_policy": {"mode": "independent_temporary_task", "owner": "L0"},
        "harness_evolution": {
            "session_local_auto": True,
            "project_local_requires_approval": True,
            "global_requires_approval": True,
            "project_local_approval_mode": "human_or_rule",
            "global_approval_mode": "high_barrier",
        },
        "external_write_policy": {
            "whitelist_systems": ["GitHub"],
            "github_whitelist_actions": ["comment", "issue", "branch", "pull_request", "merge"],
            "non_whitelist_requires_approval": True,
        },
        "portfolio_priority_formula": ["user_priority", "blocker_risk", "deadline", "resource_fairness"],
        "first_class_entities": [
            "Objective",
            "Wave",
            "Role",
            "Session",
            "Run",
            "Workflow Case",
            "Context Pack",
            "Prompt Artifact",
            "Harness Request",
            "Unblock Task",
            "Approval",
        ],
        "front_door_story": {
            "title": "The command tower for AI engineering",
            "subtitle_actions": ["plan", "delegate", "track", "resume", "prove"],
            "pain_statement": "Stop babysitting AI coding work.",
            "philosophy": ["Prompt Engineering", "Context Engineering", "Harness Engineering"],
        },
    }
    assert validator.validate_report(control_plane_runtime_policy, "control_plane_runtime_policy.v1.json")["version"] == "v1"

    manifest_path = Path(__file__).resolve().parents[3] / "contracts" / "packs" / "news_digest" / "manifest.json"
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert validator.validate_report(manifest_payload, "task_pack_manifest.v1.json")["pack_id"] == "news_digest"

    queue_item = {
        "queue_id": "queue-1",
        "task_id": "task-queue",
        "status": "PENDING",
        "priority": 5,
        "eligible": True,
        "queue_state": "eligible",
        "sla_state": "on_track",
    }
    assert validator.validate_report(queue_item, "queue_item.v1.json")["queue_id"] == "queue-1"

    scheduled_run = {
        "task_id": "task-queue",
        "workflow_id": "wf-queue",
        "source_run_id": "run-1",
        "scheduled_at": "2026-03-29T00:00:00Z",
        "deadline_at": "2026-03-29T01:00:00Z",
        "priority": 5,
    }
    assert validator.validate_report(scheduled_run, "scheduled_run.v1.json")["task_id"] == "task-queue"
    assert validator.validate_report("on_track", "sla_state.v1.json") == "on_track"

    workflow_case = {
        "workflow_id": "wf-alpha",
        "namespace": "default",
        "task_queue": "openvibecoding-orch",
        "status": "RUNNING",
        "objective": "Ship workflow case persistence",
        "owner_pm": "pm-owner",
        "project_key": "cortex-case",
        "verdict": "active",
        "summary": "Workflow case is still active and linked runs are moving.",
        "pm_session_ids": ["pm-alpha"],
        "run_ids": ["run-a", "run-b"],
        "case_source": "persisted",
        "updated_at": "2026-03-30T00:00:00Z",
    }
    assert validator.validate_report(workflow_case, "workflow_case.v1.json")["workflow_id"] == "wf-alpha"


def test_resolve_agent_registry_path_prefers_policies(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    policies_dir = repo_root / "policies"
    policies_dir.mkdir(parents=True, exist_ok=True)
    preferred = policies_dir / "agent_registry.json"
    preferred.write_text("{}", encoding="utf-8")

    assert resolve_agent_registry_path(repo_root) == preferred

    override = repo_root / "custom" / "agents.json"
    override.parent.mkdir(parents=True, exist_ok=True)
    override.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("OPENVIBECODING_AGENT_REGISTRY", "custom/agents.json")
    assert resolve_agent_registry_path(repo_root) == override
