import json
from pathlib import Path

from fastapi.testclient import TestClient

from .helpers.api_main_test_io import (
    _output_schema_artifacts,
    _write_artifact,
    _write_contract,
    _write_events,
    _write_lock,
    _write_manifest,
    _write_report,
)
from openvibecoding_orch.api import main as api_main


def test_api_workflows_list_and_detail(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))

    run_a = runs_root / "run_a"
    run_b = runs_root / "run_b"
    run_c = runs_root / "run_c"
    _write_manifest(
        run_a,
        {
            "run_id": "run_a",
            "task_id": "task_a",
            "status": "RUNNING",
            "created_at": "2024-01-01T00:00:00Z",
            "workflow": {
                "workflow_id": "wf-alpha",
                "task_queue": "openvibecoding-orch",
                "namespace": "default",
                "status": "RUNNING",
            },
        },
    )
    _write_manifest(
        run_b,
        {
            "run_id": "run_b",
            "task_id": "task_b",
            "status": "SUCCESS",
            "created_at": "2024-01-02T00:00:00Z",
            "workflow": {
                "workflow_id": "wf-alpha",
                "task_queue": "openvibecoding-orch",
                "namespace": "default",
                "status": "SUCCESS",
            },
        },
    )
    _write_manifest(
        run_c,
        {
            "run_id": "run_c",
            "task_id": "task_c",
            "status": "FAILURE",
            "created_at": "2024-01-03T00:00:00Z",
            "workflow": {
                "workflow_id": "wf-beta",
                "task_queue": "openvibecoding-orch",
                "namespace": "default",
                "status": "FAILURE",
            },
        },
    )
    _write_events(run_a, [json.dumps({"event": "WORKFLOW_BOUND", "context": {"workflow_id": "wf-alpha"}})])
    _write_events(
        run_b,
        [json.dumps({"event": "WORKFLOW_STATUS", "context": {"workflow_id": "wf-alpha", "status": "SUCCESS"}})],
    )
    intake_dir = runtime_root / "intakes" / "pm-alpha"
    intake_dir.mkdir(parents=True, exist_ok=True)
    (intake_dir / "intake.json").write_text(
        json.dumps(
            {
                "intake_id": "pm-alpha",
                "objective": "Ship the workflow case metadata layer",
                "owner_pm": "pm-owner",
                "project_key": "cortex-case",
            }
        ),
        encoding="utf-8",
    )
    (intake_dir / "response.json").write_text(
        json.dumps(
            {
                "intake_id": "pm-alpha",
                "status": "READY",
                "questions": [],
                "chain_run_id": "run_a",
            }
        ),
        encoding="utf-8",
    )
    (intake_dir / "events.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"event": "INTAKE_CHAIN_RUN", "run_id": "run_a", "ts": "2024-01-01T00:00:00Z"}),
                json.dumps({"event": "INTAKE_RUN", "run_id": "run_b", "ts": "2024-01-02T00:00:00Z"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    client = TestClient(api_main.app)

    resp = client.get("/api/workflows")
    assert resp.status_code == 200
    payload = resp.json()
    workflow_ids = [item["workflow_id"] for item in payload]
    assert "wf-alpha" in workflow_ids
    assert "wf-beta" in workflow_ids
    wf_alpha = next(item for item in payload if item["workflow_id"] == "wf-alpha")
    assert wf_alpha["objective"] == "Ship the workflow case metadata layer"
    assert wf_alpha["owner_pm"] == "pm-owner"
    assert wf_alpha["project_key"] == "cortex-case"
    assert wf_alpha["pm_session_ids"] == ["pm-alpha"]
    assert wf_alpha["summary"] == "Ship the workflow case metadata layer"
    assert wf_alpha["case_source"] == "persisted"
    assert wf_alpha["case_updated_at"]

    workflow_case_path = runtime_root / "workflow-cases" / "wf-alpha" / "case.json"
    assert workflow_case_path.exists()
    workflow_case_payload = json.loads(workflow_case_path.read_text(encoding="utf-8"))
    assert workflow_case_payload["workflow_id"] == "wf-alpha"
    assert workflow_case_payload["owner_pm"] == "pm-owner"
    assert workflow_case_payload["case_source"] == "persisted"
    assert workflow_case_payload["run_ids"] == ["run_a", "run_b"]

    detail = client.get("/api/workflows/wf-alpha")
    assert detail.status_code == 200
    body = detail.json()
    assert body["workflow"]["workflow_id"] == "wf-alpha"
    assert body["workflow"]["owner_pm"] == "pm-owner"
    assert body["workflow"]["case_source"] == "persisted"
    assert len(body["runs"]) == 2
    assert any(item.get("_run_id") == "run_a" for item in body["events"])

    missing = client.get("/api/workflows/missing")
    assert missing.status_code == 404


def test_api_queue_list_enqueue_and_run_next(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))

    run_dir = runs_root / "run_source"
    _write_manifest(
        run_dir,
        {
            "run_id": "run_source",
            "task_id": "task_source",
            "status": "SUCCESS",
            "workflow": {"workflow_id": "wf-queue", "task_queue": "openvibecoding-orch", "namespace": "default", "status": "SUCCESS"},
        },
    )
    _write_contract(
        run_dir,
        {
            "task_id": "task_source",
            "owner_agent": {"agent_id": "agent-1", "role": "WORKER"},
            "allowed_paths": ["apps/dashboard"],
        },
    )

    class _FakeService:
        def execute_task(self, contract_path: Path, mock_mode: bool = False) -> str:
            queued_run_dir = runs_root / "run_from_queue"
            _write_manifest(
                queued_run_dir,
                {
                    "run_id": "run_from_queue",
                    "task_id": "task_source",
                    "status": "SUCCESS",
                },
            )
            return "run_from_queue"

    monkeypatch.setattr(api_main, "_orchestration_service", _FakeService())

    client = TestClient(api_main.app)

    enqueue = client.post(
        "/api/queue/from-run/run_source",
        json={"priority": 5},
        headers={"x-openvibecoding-role": "OWNER"},
    )
    assert enqueue.status_code == 200
    assert enqueue.json()["workflow_id"] == "wf-queue"
    assert enqueue.json()["priority"] == 5

    queue_items = client.get("/api/queue", params={"workflow_id": "wf-queue"})
    assert queue_items.status_code == 200
    assert queue_items.json()[0]["task_id"] == "task_source"
    assert queue_items.json()[0]["eligible"] is True

    run_next = client.post("/api/queue/run-next", json={"mock": True}, headers={"x-openvibecoding-role": "OWNER"})
    assert run_next.status_code == 200
    assert run_next.json()["ok"] is True
    assert run_next.json()["run_id"] == "run_from_queue"


def test_api_queue_preview_and_cancel_roundtrip(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))

    run_dir = runs_root / "run_source"
    _write_manifest(
        run_dir,
        {
            "run_id": "run_source",
            "task_id": "task_source",
            "status": "SUCCESS",
            "workflow": {"workflow_id": "wf-queue", "task_queue": "openvibecoding-orch", "namespace": "default", "status": "SUCCESS"},
        },
    )
    _write_contract(
        run_dir,
        {
            "task_id": "task_source",
            "owner_agent": {"agent_id": "agent-1", "role": "WORKER"},
            "allowed_paths": ["apps/dashboard"],
        },
    )

    client = TestClient(api_main.app)

    preview = client.post(
        "/api/queue/from-run/run_source/preview",
        json={"priority": 3},
        headers={"x-openvibecoding-role": "OWNER"},
    )
    assert preview.status_code == 200
    preview_payload = preview.json()
    assert preview_payload["run_id"] == "run_source"
    assert preview_payload["preview_item"]["status"] == "PENDING"
    assert preview_payload["pending_matches"] == []

    queue_before = client.get("/api/queue", params={"workflow_id": "wf-queue"})
    assert queue_before.status_code == 200
    assert queue_before.json() == []

    enqueue = client.post(
        "/api/queue/from-run/run_source",
        json={"priority": 3},
        headers={"x-openvibecoding-role": "OWNER"},
    )
    assert enqueue.status_code == 200
    queue_id = enqueue.json()["queue_id"]

    cancel = client.post(
        f"/api/queue/{queue_id}/cancel",
        json={"reason": "operator aborted pilot"},
        headers={"x-openvibecoding-role": "OWNER"},
    )
    assert cancel.status_code == 200
    cancel_payload = cancel.json()
    assert cancel_payload["status"] == "CANCELLED"
    assert cancel_payload["queue_state"] == "closed"
    assert cancel_payload["cancelled_at"]
    assert cancel_payload["reason"] == "operator aborted pilot"
    assert cancel_payload["cancelled_by"] == "OWNER"

    queue_after = client.get("/api/queue", params={"workflow_id": "wf-queue"})
    assert queue_after.status_code == 200
    assert queue_after.json()[0]["status"] == "CANCELLED"
    assert queue_after.json()[0]["cancelled_at"]


def test_api_queue_rejects_naive_schedule_input(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))

    run_dir = runs_root / "run_source"
    _write_manifest(
        run_dir,
        {
            "run_id": "run_source",
            "task_id": "task_source",
            "status": "SUCCESS",
            "workflow": {"workflow_id": "wf-queue", "task_queue": "openvibecoding-orch", "namespace": "default", "status": "SUCCESS"},
        },
    )
    _write_contract(
        run_dir,
        {
            "task_id": "task_source",
            "owner_agent": {"agent_id": "agent-1", "role": "WORKER"},
            "allowed_paths": ["apps/dashboard"],
        },
    )

    client = TestClient(api_main.app)
    enqueue = client.post(
        "/api/queue/from-run/run_source",
        json={"priority": 5, "scheduled_at": "2026-03-30T12:00"},
        headers={"x-openvibecoding-role": "OWNER"},
    )
    assert enqueue.status_code == 422


def test_api_reports_include_proof_pack_for_successful_public_slice(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))

    run_dir = runs_root / "run_news_digest"
    _write_manifest(
        run_dir,
        {
            "run_id": "run_news_digest",
            "task_id": "task_news_digest",
            "status": "SUCCESS",
        },
    )
    _write_report(
        run_dir,
        "news_digest_result.json",
        {
            "task_template": "news_digest",
            "generated_at": "2026-03-30T00:00:00Z",
            "status": "SUCCESS",
            "topic": "AI",
            "time_range": "24h",
            "requested_sources": ["source-a"],
            "max_results": 5,
            "summary": "The public digest completed successfully.",
            "sources": [],
            "evidence_refs": {
                "raw": "search_results.json",
                "purified": "purified_summary.json",
                "verification": "verification.json",
                "evidence_bundle": "evidence_bundle.json",
            },
        },
    )

    client = TestClient(api_main.app)
    response = client.get("/api/runs/run_news_digest/reports")
    assert response.status_code == 200
    reports = response.json()
    by_name = {item["name"]: item["data"] for item in reports}
    assert by_name["proof_pack.json"]["report_type"] == "proof_pack"
    assert by_name["proof_pack.json"]["task_template"] == "news_digest"
    assert by_name["proof_pack.json"]["proof_ready"] is True


def test_api_agents_policies_locks_worktrees(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    locks_dir = runtime_root / "locks"
    worktree_root = runtime_root / "worktrees"
    repo_root = tmp_path / "repo"
    policies_dir = repo_root / "policies"
    tools_dir = repo_root / "tooling"

    policies_dir.mkdir(parents=True, exist_ok=True)
    tools_dir.mkdir(parents=True, exist_ok=True)
    (policies_dir / "agent_registry.json").write_text(
        json.dumps(
            {
                "version": "v1",
                "role_contracts": {
                    "WORKER": {
                        "purpose": "Execute the contracted change inside allowed_paths and produce structured evidence.",
                        "system_prompt_ref": "policies/agents/codex/roles/50_worker_core.md",
                        "skills_bundle_ref": "policies/skills_bundle_registry.json#bundles.worker_delivery_core_v1",
                        "mcp_bundle_ref": "policies/agent_registry.json#agents(role=WORKER).capabilities.mcp_tools",
                        "handoff_eligible": True,
                        "required_downstream_roles": ["REVIEWER", "TEST_RUNNER"],
                        "fail_closed_conditions": ["Writes outside allowed_paths fail closed"],
                    }
                },
                "agents": [{"agent_id": "agent-1", "role": "WORKER", "label": "worker"}],
            }
        ),
        encoding="utf-8",
    )
    (policies_dir / "command_allowlist.json").write_text(
        json.dumps({"version": "v1", "allow": [], "deny_substrings": []}),
        encoding="utf-8",
    )
    (policies_dir / "forbidden_actions.json").write_text(
        json.dumps({"version": "v1", "forbidden_actions": ["rm -rf"]}),
        encoding="utf-8",
    )
    (tools_dir / "registry.json").write_text(
        json.dumps({"installed": ["codex"], "integrated": ["codex"]}),
        encoding="utf-8",
    )

    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("OPENVIBECODING_WORKTREE_ROOT", str(worktree_root))
    monkeypatch.setenv("OPENVIBECODING_REPO_ROOT", str(repo_root))

    run_id = "run_lock"
    run_dir = runs_root / run_id
    _write_manifest(run_dir, {"run_id": run_id, "task_id": "task", "status": "SUCCESS"})
    _write_contract(run_dir, {"assigned_agent": {"agent_id": "agent-1", "role": "WORKER"}})
    _write_lock(locks_dir, "lock-1", run_id, "allowed/file.txt", "2024-01-01T00:00:00Z")

    worktree_path = worktree_root / run_id
    monkeypatch.setattr(
        api_main.worktree_manager,
        "list_worktrees",
        lambda: [
            f"worktree {worktree_path}",
            "HEAD abc123",
            "branch refs/heads/openvibecoding-run-run_lock",
            "locked",
        ],
    )

    client = TestClient(api_main.app)

    agents = client.get("/api/agents")
    assert agents.status_code == 200
    payload = agents.json()
    assert payload["agents"][0]["agent_id"] == "agent-1"
    assert payload["agents"][0]["lock_count"] == 1
    assert payload["role_catalog"][0]["role"] == "WORKER"
    assert payload["role_catalog"][0]["role_binding_read_model"]["execution_authority"] == "task_contract"

    policies = client.get("/api/policies")
    assert policies.status_code == 200
    assert policies.json()["agent_registry"]["version"] == "v1"
    assert policies.json()["control_plane_runtime_policy"]["version"] == "v1"

    locks = client.get("/api/locks")
    assert locks.status_code == 200
    assert locks.json()[0]["run_id"] == run_id

    worktrees = client.get("/api/worktrees")
    assert worktrees.status_code == 200
    assert worktrees.json()[0]["run_id"] == run_id


def test_api_pm_intake_flow(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    repo_root = tmp_path / "repo"
    schema_root = repo_root / "schemas"
    schema_root.mkdir(parents=True, exist_ok=True)
    for name in [
        "pm_intake_request.v1.json",
        "pm_intake_response.v1.json",
        "plan.schema.json",
        "plan_bundle.v1.json",
    ]:
        src = Path(__file__).resolve().parents[3] / "schemas" / name
        (schema_root / name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("OPENVIBECODING_REPO_ROOT", str(repo_root))
    monkeypatch.setenv("GEMINI_API_KEY", "")  # force provider fallback path

    client = TestClient(api_main.app)
    payload = {
        "objective": "add endpoint",
        "allowed_paths": ["apps/orchestrator/src"],
        "mcp_tool_set": ["01-filesystem"],
    }
    created = client.post("/api/intake", json=payload)
    assert created.status_code == 200
    created_payload = created.json()
    assert created_payload["browser_policy_preset"] == "safe"
    assert isinstance(created_payload.get("effective_browser_policy"), dict)
    intake_id = created_payload["intake_id"]
    answered = client.post(f"/api/intake/{intake_id}/answers", json={"answers": ["none"]})
    assert answered.status_code == 200
    assert answered.json()["status"] == "READY"


def test_api_pm_intake_custom_policy_requires_privileged_role(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    repo_root = tmp_path / "repo"
    schema_root = repo_root / "schemas"
    schema_root.mkdir(parents=True, exist_ok=True)
    for name in [
        "pm_intake_request.v1.json",
        "pm_intake_response.v1.json",
        "plan.schema.json",
        "plan_bundle.v1.json",
    ]:
        src = Path(__file__).resolve().parents[3] / "schemas" / name
        (schema_root / name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("OPENVIBECODING_REPO_ROOT", str(repo_root))

    client = TestClient(api_main.app)

    denied = client.post(
        "/api/intake",
        json={
            "objective": "x",
            "allowed_paths": ["apps/orchestrator/src"],
            "mcp_tool_set": ["01-filesystem"],
            "browser_policy_preset": "custom",
            "requester_role": "PM",
            "browser_policy": {
                "profile_mode": "allow_profile",
                "stealth_mode": "plugin",
                "human_behavior": {"enabled": True, "level": "medium"},
            },
        },
    )
    assert denied.status_code == 400

    allowed = client.post(
        "/api/intake",
        json={
            "objective": "x",
            "allowed_paths": ["apps/orchestrator/src"],
            "mcp_tool_set": ["01-filesystem"],
            "browser_policy_preset": "custom",
            "requester_role": "OPS",
            "browser_policy": {
                "profile_mode": "allow_profile",
                "stealth_mode": "plugin",
                "human_behavior": {"enabled": True, "level": "medium"},
            },
        },
    )
    assert allowed.status_code == 200
    payload = allowed.json()
    assert payload["browser_policy_preset"] == "custom"
    assert payload["effective_browser_policy"]["stealth_mode"] == "plugin"


def test_api_search_promote_and_agent_status(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))

    run_id = "run_search"
    run_dir = runs_root / run_id
    _write_manifest(run_dir, {"run_id": run_id, "task_id": "task_search", "status": "RUNNING"})
    _write_contract(
        run_dir,
        {
            "assigned_agent": {"role": "SEARCHER", "agent_id": "agent-1"},
            "allowed_paths": ["docs"],
            "inputs": {"artifacts": _output_schema_artifacts("searcher")},
        },
    )
    _write_events(
        run_dir,
        [
            json.dumps(
                {
                    "event": "HUMAN_APPROVAL_REQUIRED",
                    "context": {
                        "reason": ["network on-request requires approval"],
                        "actions": ["approve network"],
                        "verify_steps": ["click approve"],
                        "resume_step": "policy_gate",
                    },
                }
            )
        ],
    )
    (run_dir / "diff_name_only.txt").write_text("docs/README.md\n", encoding="utf-8")
    _write_artifact(
        run_dir,
        "search_results.json",
        {
            "latest": {
                "results": [
                    {
                        "provider": "chatgpt_web",
                        "results": [{"title": "Example", "href": "https://example.com"}],
                    }
                ]
            }
        },
    )
    _write_artifact(run_dir, "verification.json", {"latest": {"verification": {"ok": True}}})
    _write_artifact(run_dir, "purified_summary.json", {"latest": {"summary": {"consensus_domains": ["example.com"]}}})

    client = TestClient(api_main.app)
    search_resp = client.get(f"/api/runs/{run_id}/search")
    assert search_resp.status_code == 200
    assert search_resp.json()["raw"]["latest"]["results"][0]["provider"] == "chatgpt_web"

    promote_resp = client.post(
        f"/api/runs/{run_id}/evidence/promote",
        headers={"x-openvibecoding-role": "TECH_LEAD"},
    )
    assert promote_resp.status_code == 200
    assert promote_resp.json()["ok"] is True
    assert (run_dir / "reports" / "evidence_bundle.json").exists()

    status_resp = client.get(f"/api/agents/status?run_id={run_id}")
    assert status_resp.status_code == 200
    status_payload = status_resp.json()["agents"][0]
    assert status_payload["stage"] == "WAITING_APPROVAL"

    pending_resp = client.get("/api/god-mode/pending", headers={"x-openvibecoding-role": "TECH_LEAD"})
    assert pending_resp.status_code == 200
    pending_payload = pending_resp.json()[0]
    assert pending_payload["run_id"] == run_id
    assert pending_payload["resume_step"] == "policy_gate"
    assert pending_payload["approval_pack"]["report_type"] == "approval_pack"
    assert pending_payload["approval_pack"]["summary"]

    reports_resp = client.get(f"/api/runs/{run_id}/reports")
    assert reports_resp.status_code == 200
    reports_payload = reports_resp.json()
    incident_pack = next(item for item in reports_payload if item["name"] == "incident_pack.json")
    assert incident_pack["data"]["report_type"] == "incident_pack"
    assert incident_pack["data"]["root_event"] == "HUMAN_APPROVAL_REQUIRED"
