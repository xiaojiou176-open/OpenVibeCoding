import json
import os
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from .helpers.api_main_test_io import (
    _write_contract,
    _write_events,
    _write_manifest,
    _write_report,
)
from cortexpilot_orch.api import main as api_main
from cortexpilot_orch.store.intake_store import IntakeStore


def test_api_misc_collections_and_pm_wrappers(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    contracts_root = tmp_path / "contracts"
    repo_root = tmp_path / "repo"
    policies_dir = repo_root / "policies"
    tools_dir = repo_root / "tooling"
    policies_dir.mkdir(parents=True, exist_ok=True)
    tools_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("CORTEXPILOT_CONTRACT_ROOT", str(contracts_root))
    monkeypatch.setenv("CORTEXPILOT_REPO_ROOT", str(repo_root))

    (policies_dir / "agent_registry.json").write_text(json.dumps({"version": "v1", "agents": []}), encoding="utf-8")
    (policies_dir / "command_allowlist.json").write_text(
        json.dumps({"version": "v1", "allow": [], "deny_substrings": []}),
        encoding="utf-8",
    )
    (policies_dir / "forbidden_actions.json").write_text(
        json.dumps({"version": "v1", "forbidden_actions": ["rm -rf"]}),
        encoding="utf-8",
    )
    (tools_dir / "registry.json").write_text(json.dumps({"installed": ["codex"], "integrated": ["codex"]}), encoding="utf-8")

    run_a = runs_root / "run_a"
    run_b = runs_root / "run_b"
    _write_manifest(run_a, {"run_id": "run_a", "task_id": "task_a", "status": "RUNNING", "created_at": "2024-01-01T00:00:00Z"})
    _write_manifest(run_b, {"run_id": "run_b", "task_id": "task_b", "status": "SUCCESS", "created_at": "2024-01-02T00:00:00Z"})
    _write_contract(run_a, {"allowed_paths": ["apps/"], "assigned_agent": {"agent_id": "agent-1", "role": "WORKER"}})
    _write_contract(run_b, {"allowed_paths": ["docs/"], "assigned_agent": {"agent_id": "agent-2", "role": "REVIEWER"}})
    _write_events(
        run_a,
        [
            json.dumps({"event": "DIFF_GATE_RESULT", "context": {"ok": True}, "ts": "2024-01-01T00:00:01Z"}),
            json.dumps({"event": "TEST_RESULT", "ts": "2024-01-01T00:00:02Z"}),
        ],
    )
    _write_events(run_b, [json.dumps({"event": "REVIEW_RESULT", "ts": "2024-01-02T00:00:02Z"})])

    _write_report(run_a, "review_report.json", {"verdict": "PASS"})
    _write_report(run_a, "test_report.json", {"status": "PASS"})
    _write_report(run_b, "review_report.json", "not-json")
    _write_report(run_b, "test_report.json", "not-json")

    client = TestClient(api_main.app)

    events = client.get("/api/events", params={"limit": 1})
    assert events.status_code == 200
    assert len(events.json()) == 1

    diff_gate = client.get("/api/diff-gate")
    assert diff_gate.status_code == 200
    assert {item["run_id"] for item in diff_gate.json()} == {"run_a"}

    reviews = client.get("/api/reviews")
    assert reviews.status_code == 200
    tests = client.get("/api/tests")
    assert tests.status_code == 200

    policies = client.get("/api/policies")
    assert policies.status_code == 200
    assert "tool_registry" in policies.json()

    lock_dir = runtime_root / "locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    (lock_dir / "lock-1.lock").write_text("run_id=run_a\npath=apps/file.py\nts=2024-01-01T00:00:00Z", encoding="utf-8")
    locks = client.get("/api/locks")
    assert locks.status_code == 200
    assert locks.json()[0]["run_id"] == "run_a"

    # PM wrappers should dispatch to base handlers.
    monkeypatch.setattr(api_main, "create_intake", lambda payload: {"ok": True, "kind": "create", "payload": payload})
    monkeypatch.setattr(api_main, "list_task_packs", lambda: [{"pack_id": "news_digest"}])
    monkeypatch.setattr(api_main, "answer_intake", lambda intake_id, payload: {"ok": True, "kind": "answer", "intake_id": intake_id, "payload": payload})
    monkeypatch.setattr(api_main, "run_intake", lambda intake_id, payload=None: {"ok": True, "kind": "run", "intake_id": intake_id, "payload": payload})

    assert client.post("/api/pm/intake", json={"objective": "x"}).json()["kind"] == "create"
    assert client.get("/api/pm/task-packs").json()[0]["pack_id"] == "news_digest"
    assert client.post("/api/pm/intake/i1/answer", json={"answers": ["a"]}).json()["kind"] == "answer"
    assert client.post("/api/pm/intake/i1/run", json={"mock": True}).json()["kind"] == "run"


def test_api_intake_and_request_guard_error_paths(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    repo_root = tmp_path / "repo"
    contracts_root = tmp_path / "contracts"
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("CORTEXPILOT_REPO_ROOT", str(repo_root))
    monkeypatch.setenv("CORTEXPILOT_CONTRACT_ROOT", str(contracts_root))

    run_dir = runs_root / "run_guard"
    _write_manifest(run_dir, {"run_id": "run_guard", "task_id": "task", "status": "SUCCESS"})

    class FailingIntakeService:
        def create(self, payload):
            raise RuntimeError("create failed")

        def answer(self, intake_id, payload):
            raise RuntimeError("answer failed")

        def build_contract(self, intake_id):
            raise RuntimeError("build failed")

    monkeypatch.setattr(api_main, "IntakeService", FailingIntakeService)
    client = TestClient(api_main.app)

    create_resp = client.post("/api/intake", json={"objective": "x"})
    assert create_resp.status_code == 500

    answer_resp = client.post("/api/intake/abc/answers", json={"answers": ["x"]})
    assert answer_resp.status_code == 500

    run_resp = client.post("/api/intake/abc/run", json={"mock": True})
    assert run_resp.status_code == 500

    class EmptyContractService:
        def build_contract(self, intake_id):
            return None

    monkeypatch.setattr(api_main, "IntakeService", EmptyContractService)
    no_plan = client.post("/api/intake/abc/run", json={"mock": True})
    assert no_plan.status_code == 400
    assert no_plan.json()["detail"]["code"] == "INTAKE_PLAN_MISSING"

    class SuccessService:
        def build_contract(self, intake_id):
            return {
                "task_id": "task_from_intake",
                "owner_agent": {"role": "WORKER", "agent_id": "agent-1"},
                "assigned_agent": {"role": "WORKER", "agent_id": "agent-1"},
                "inputs": {"spec": "mock", "artifacts": []},
                "required_outputs": [{"name": "out.txt", "type": "file", "acceptance": "ok"}],
                "allowed_paths": ["out.txt"],
                "forbidden_actions": [],
                "acceptance_tests": [{"name": "noop", "cmd": "echo ok", "must_pass": True}],
                "tool_permissions": {"filesystem": "workspace-write", "shell": "on-request", "network": "deny", "mcp_tools": ["codex"]},
                "mcp_tool_set": ["01-filesystem"],
                "timeout_retry": {"timeout_sec": 1, "max_retries": 0, "retry_backoff_sec": 0},
                "rollback": {"strategy": "git_reset_hard", "baseline_ref": "HEAD"},
                "evidence_links": [],
                "log_refs": {"run_id": "", "paths": {}},
            }

    monkeypatch.setattr(api_main, "IntakeService", SuccessService)

    captured: dict[str, str] = {}

    class Svc:
        @staticmethod
        def execute_task(contract_path, mock_mode=False):
            captured["contract_path"] = str(contract_path)
            captured["mock_mode"] = str(bool(mock_mode))
            return "run-new"

    monkeypatch.setattr(api_main, "_orchestration_service", Svc())
    success = client.post("/api/intake/abc/run", json={"runner": "agents", "mock": True})
    assert success.status_code == 200
    assert success.json()["run_id"] == "run-new"
    contract_json = json.loads(Path(captured["contract_path"]).read_text(encoding="utf-8"))
    assert contract_json.get("audit_only") is True

    # request guard: missing configured token when auth required -> 503
    monkeypatch.setenv("CORTEXPILOT_API_AUTH_REQUIRED", "1")
    monkeypatch.setenv("CORTEXPILOT_API_TOKEN", "")
    unavailable = client.get("/api/runs")
    assert unavailable.status_code == 503

    # request guard: unhandled endpoint exception -> 500 with request id payload.
    monkeypatch.setenv("CORTEXPILOT_API_AUTH_REQUIRED", "0")
    monkeypatch.setattr(api_main, "_runs_root", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    crashed = client.get("/api/runs")
    assert crashed.status_code == 500
    assert crashed.json()["detail"]["code"] == "INTERNAL_SERVER_ERROR"


def test_api_run_intake_strict_acceptance_and_reexec_routes(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    contracts_root = tmp_path / "contracts"
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("CORTEXPILOT_CONTRACT_ROOT", str(contracts_root))

    class SuccessService:
        def build_contract(self, intake_id):
            return {
                "task_id": "task_strict_acceptance",
                "owner_agent": {"role": "WORKER", "agent_id": "agent-1"},
                "assigned_agent": {"role": "WORKER", "agent_id": "agent-1"},
                "inputs": {"spec": "strict", "artifacts": []},
                "required_outputs": [{"name": "out.txt", "type": "file", "acceptance": "ok"}],
                "allowed_paths": ["out.txt"],
                "forbidden_actions": [],
                "acceptance_tests": [
                    {
                        "name": "hygiene",
                        "cmd": "bash scripts/check_repo_hygiene.sh",
                        "must_pass": True,
                    }
                ],
                "tool_permissions": {"filesystem": "workspace-write", "shell": "on-request", "network": "deny", "mcp_tools": ["codex"]},
                "mcp_tool_set": ["codex"],
                "timeout_retry": {"timeout_sec": 1, "max_retries": 0, "retry_backoff_sec": 0},
                "rollback": {"strategy": "git_reset_hard", "baseline_ref": "HEAD"},
                "evidence_links": [],
                "log_refs": {"run_id": "", "paths": {}},
            }

    monkeypatch.setattr(api_main, "IntakeService", SuccessService)

    captured: dict[str, str] = {}

    class Svc:
        @staticmethod
        def execute_task(contract_path, mock_mode=False):
            captured["contract_path"] = str(contract_path)
            payload = json.loads(Path(contract_path).read_text(encoding="utf-8"))
            runtime_options = payload.get("runtime_options") if isinstance(payload.get("runtime_options"), dict) else {}
            captured["strict_runtime"] = str(bool(runtime_options.get("strict_acceptance", False)))
            captured["runner_runtime"] = str(runtime_options.get("runner", ""))
            captured["provider_runtime"] = str(runtime_options.get("provider", ""))
            return "run-strict"

        @staticmethod
        def replay_verify(run_id, strict=False):
            return {"mode": "verify", "run_id": run_id, "strict": bool(strict)}

        @staticmethod
        def replay_reexec(run_id, strict=True):
            return {"mode": "reexec", "run_id": run_id, "strict": bool(strict)}

    monkeypatch.setattr(api_main, "_orchestration_service", Svc())

    client = TestClient(api_main.app)
    response = client.post(
        "/api/intake/i-strict/run",
        json={
            "runner": "agents",
            "mock": False,
            "strict_acceptance": True,
            "runtime_options": {"provider": "cliproxyapi"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == "run-strict"
    assert payload["strict_acceptance"] is True
    assert captured["strict_runtime"] == "True"
    assert captured["runner_runtime"] == "agents"
    assert captured["provider_runtime"] == "cliproxyapi"
    assert os.getenv("CORTEXPILOT_ACCEPTANCE_STRICT_NONTRIVIAL", "") == ""

    replay_headers = {"x-cortexpilot-role": "TECH_LEAD"}
    verify = client.post("/api/runs/run-strict/verify", params={"strict": "true"}, headers=replay_headers)
    assert verify.status_code == 200
    assert verify.json() == {"mode": "verify", "run_id": "run-strict", "strict": True}

    reexec = client.post("/api/runs/run-strict/reexec", params={"strict": "false"}, headers=replay_headers)
    assert reexec.status_code == 200
    assert reexec.json() == {"mode": "reexec", "run_id": "run-strict", "strict": False}

    response_string_false = client.post(
        "/api/intake/i-strict/run",
        json={"runner": "agents", "mock": "false", "strict_acceptance": "false"},
    )
    assert response_string_false.status_code == 200
    payload_string_false = response_string_false.json()
    assert payload_string_false["strict_acceptance"] is False
    assert captured["strict_runtime"] == "False"


def test_api_run_intake_generates_unique_contract_path_per_run(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    contracts_root = tmp_path / "contracts"
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("CORTEXPILOT_CONTRACT_ROOT", str(contracts_root))

    class SuccessService:
        def build_contract(self, intake_id):
            return {
                "task_id": "task_same_id",
                "owner_agent": {"role": "WORKER", "agent_id": "agent-1"},
                "assigned_agent": {"role": "WORKER", "agent_id": "agent-1"},
                "inputs": {"spec": "strict", "artifacts": []},
                "required_outputs": [{"name": "out.txt", "type": "file", "acceptance": "ok"}],
                "allowed_paths": ["out.txt"],
                "forbidden_actions": [],
                "acceptance_tests": [{"name": "noop", "cmd": "echo ok", "must_pass": True}],
                "tool_permissions": {"filesystem": "workspace-write", "shell": "on-request", "network": "deny", "mcp_tools": ["codex"]},
                "mcp_tool_set": ["codex"],
                "timeout_retry": {"timeout_sec": 1, "max_retries": 0, "retry_backoff_sec": 0},
                "rollback": {"strategy": "git_reset_hard", "baseline_ref": "HEAD"},
                "evidence_links": [],
                "log_refs": {"run_id": "", "paths": {}},
            }

    monkeypatch.setattr(api_main, "IntakeService", SuccessService)

    captured_paths: list[str] = []

    class Svc:
        @staticmethod
        def execute_task(contract_path, mock_mode=False):
            del mock_mode
            captured_paths.append(str(contract_path))
            return f"run-{len(captured_paths)}"

    monkeypatch.setattr(api_main, "_orchestration_service", Svc())
    client = TestClient(api_main.app)

    run1 = client.post("/api/intake/i-unique/run", json={"mock": True})
    run2 = client.post("/api/intake/i-unique/run", json={"mock": True})

    assert run1.status_code == 200
    assert run2.status_code == 200
    path1 = run1.json()["contract_path"]
    path2 = run2.json()["contract_path"]
    assert path1 != path2
    assert Path(path1).exists()
    assert Path(path2).exists()
    assert Path(path1).name.startswith("task_same_id-")
    assert Path(path2).name.startswith("task_same_id-")


def test_api_intake_listing_and_fetch(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runs_root))

    store = IntakeStore()
    intake_id = store.create({"objective": "deep review"})
    store.write_response(intake_id, {"status": "READY"})

    client = TestClient(api_main.app)
    listed = client.get("/api/intakes")
    assert listed.status_code == 200
    assert any(item["intake_id"] == intake_id for item in listed.json())

    detail = client.get(f"/api/intake/{intake_id}")
    assert detail.status_code == 200
    assert detail.json()["response"]["status"] == "READY"

    missing = client.get("/api/intake/missing-id")
    assert missing.status_code == 404
    assert not (runtime_root / "intakes" / "missing-id").exists()


def test_api_internal_helpers_branches(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    contract_root = tmp_path / "contracts"
    repo_root = tmp_path / "repo"
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("CORTEXPILOT_CONTRACT_ROOT", str(contract_root))
    monkeypatch.setenv("CORTEXPILOT_REPO_ROOT", str(repo_root))

    run_dir = runs_root / "run_helpers"
    _write_manifest(run_dir, {"run_id": "run_helpers", "task_id": "task", "status": "RUNNING"})

    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    (artifacts_dir / "rows.jsonl").write_text('{"a":1}\nnot-json\n', encoding="utf-8")
    (artifacts_dir / "item.json").write_text('{"ok":true}', encoding="utf-8")
    (artifacts_dir / "note.txt").write_text("hello", encoding="utf-8")

    reports_dir = run_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "plain.json").write_text("not-json", encoding="utf-8")

    assert api_main._read_artifact_file("run_helpers", "rows.jsonl")[1]["raw"] == "not-json"
    assert api_main._read_artifact_file("run_helpers", "item.json") == {"ok": True}
    assert api_main._read_artifact_file("run_helpers", "note.txt") == "hello"
    assert api_main._read_artifact_file("run_helpers", "../escape") is None

    assert api_main._read_report_file("run_helpers", "plain.json") == "not-json"

    query_file = tmp_path / "query.json"
    query_file.write_text(json.dumps({"queries": ["q1", "q2"]}), encoding="utf-8")
    contract = {"inputs": {"artifacts": [{"name": "search_requests.json", "uri": str(query_file)}]}}
    assert api_main._extract_search_queries(contract) == ["q1", "q2"]

    assert api_main._derive_stage([], {"status": "FAILURE"}) == "FAILED"
    assert api_main._derive_stage([], {"status": "SUCCESS"}) == "DONE"
    assert api_main._derive_stage([{"event": "HUMAN_APPROVAL_REQUIRED"}], {"status": "RUNNING"}) == "WAITING_APPROVAL"
    assert api_main._derive_stage([{"event": "TEST_RESULT"}], {"status": "RUNNING"}) == "TESTING"
    assert api_main._derive_stage([{"event": "REVIEW_RESULT"}], {"status": "RUNNING"}) == "REVIEW"
    assert api_main._derive_stage([{"event": "DIFF_GATE_RESULT"}], {"status": "RUNNING"}) == "DIFF_GATE"
    assert api_main._derive_stage([{"event": "STEP_STARTED"}], {"status": "RUNNING"}) == "EXECUTING"
    assert api_main._derive_stage([], {"status": "RUNNING"}) == "PENDING"

    # list_contracts fallback branch for invalid json payload
    examples_dir = contract_root / "examples"
    tasks_dir = contract_root / "tasks"
    examples_dir.mkdir(parents=True, exist_ok=True)
    tasks_dir.mkdir(parents=True, exist_ok=True)
    (examples_dir / "ok.json").write_text(json.dumps({"task_id": "ok"}), encoding="utf-8")
    (tasks_dir / "bad.json").write_text("{", encoding="utf-8")

    contracts = api_main.list_contracts()
    assert any(item.get("_source") == "examples" for item in contracts)
    assert any(item.get("_source") == "tasks" and "raw" in item for item in contracts)


def test_api_write_side_delegates_to_service(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runs_root))

    run_id = "run_delegate"
    run_dir = runs_root / run_id
    _write_manifest(run_dir, {"run_id": run_id, "task_id": "task", "status": "RUNNING"})
    _write_contract(
        run_dir,
        {
            "assigned_agent": {"role": "SEARCHER", "agent_id": "agent-1"},
            "inputs": {"artifacts": []},
        },
    )

    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    (artifacts_dir / "search_results.json").write_text(
        json.dumps({"results": [{"title": "example", "href": "https://example.com"}]}),
        encoding="utf-8",
    )

    captured: dict[str, object] = {}

    class DummyService:
        def promote_evidence(self, run_id: str, bundle: dict, source: str = "search_ui") -> dict:
            captured["promote"] = {"run_id": run_id, "bundle": bundle, "source": source}
            return {"ok": True, "bundle": bundle, "source": source}

        def reject_run(self, run_id: str, reason: str = "diff gate rejected") -> dict:
            captured["reject"] = {"run_id": run_id, "reason": reason}
            return {"ok": True, "reason": reason}

        def approve_god_mode(self, run_id: str, payload: dict) -> dict:
            captured["approve"] = {"run_id": run_id, "payload": payload}
            return {"ok": True, "run_id": run_id}

    monkeypatch.setattr(api_main, "_orchestration_service", DummyService())
    _write_events(run_dir, [json.dumps({"event": "HUMAN_APPROVAL_REQUIRED"})])
    client = TestClient(api_main.app)

    headers = {"x-cortexpilot-role": "TECH_LEAD"}
    promote_resp = client.post(f"/api/runs/{run_id}/evidence/promote", headers=headers)
    assert promote_resp.status_code == 200
    assert promote_resp.json()["ok"] is True
    assert captured["promote"]

    reject_resp = client.post(f"/api/runs/{run_id}/reject", headers=headers)
    assert reject_resp.status_code == 200
    assert reject_resp.json() == {"ok": True, "reason": "diff gate rejected"}
    assert captured["reject"] == {"run_id": run_id, "reason": "diff gate rejected"}

    approve_payload = {"run_id": run_id, "approved_by": "ops"}
    approve_resp = client.post(
        "/api/god-mode/approve",
        json=approve_payload,
        headers={"x-cortexpilot-role": "TECH_LEAD"},
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json() == {"ok": True, "run_id": run_id}
    assert captured["approve"] == {"run_id": run_id, "payload": approve_payload}


def test_api_reject_service_run_not_found_maps_404(monkeypatch) -> None:
    class DummyService:
        def reject_run(self, run_id: str, reason: str = "diff gate rejected") -> dict:
            return {"ok": False, "error": "RUN_NOT_FOUND"}

    monkeypatch.setattr(api_main, "_orchestration_service", DummyService())
    client = TestClient(api_main.app)

    resp = client.post("/api/runs/missing/reject", headers={"x-cortexpilot-role": "TECH_LEAD"})
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "RUN_NOT_FOUND"


def test_api_write_helpers_service_and_fallback_paths(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runs_root))

    run_id = "run_helper_paths"
    run_dir = runs_root / run_id
    _write_manifest(run_dir, {"run_id": run_id, "task_id": "task", "status": "RUNNING"})

    captured: dict[str, object] = {}

    class ServiceDouble:
        def append_event(self, run_id: str, payload: dict) -> None:
            captured["append_event"] = {"run_id": run_id, "payload": payload}

        def write_manifest(self, run_id: str, manifest_data: dict) -> None:
            captured["write_manifest"] = {"run_id": run_id, "manifest_data": manifest_data}

        def write_evidence_bundle(self, run_id: str, bundle: dict) -> None:
            captured["write_evidence_bundle"] = {"run_id": run_id, "bundle": bundle}

        def promote_evidence(self, run_id: str, bundle: dict, source: str = "search_ui") -> dict:
            captured["promote"] = {"run_id": run_id, "bundle": bundle, "source": source}
            return {"ok": True, "bundle": bundle}

        def reject_run(self, run_id: str, reason: str = "diff gate rejected") -> dict:
            captured["reject"] = {"run_id": run_id, "reason": reason}
            return {"ok": True, "reason": reason}

        def approve_god_mode(self, run_id: str, payload: dict) -> dict:
            captured["approve"] = {"run_id": run_id, "payload": payload}
            return {"ok": True, "run_id": run_id}

    monkeypatch.setattr(api_main, "_orchestration_service", ServiceDouble())

    api_main._append_run_event(run_id, {"event": "X"})
    api_main._write_manifest(run_id, {"status": "SUCCESS"})
    api_main._write_evidence_bundle(run_id, {"items": []})

    assert api_main._promote_evidence(run_id, {"items": [1]})["ok"] is True
    assert api_main._reject_run_mutation(run_id)["ok"] is True
    assert api_main._approve_god_mode_mutation(run_id, {"run_id": run_id})["ok"] is True
    assert "append_event" in captured
    assert "write_manifest" in captured
    assert "write_evidence_bundle" in captured

    monkeypatch.setattr(api_main, "_orchestration_service", object())

    api_main._append_run_event(
        run_id,
        {
            "level": "INFO",
            "event": "UNIT_TEST_EVENT",
            "run_id": run_id,
            "payload": {"source": "fallback"},
        },
    )
    api_main._write_manifest(run_id, {"run_id": run_id, "status": "RUNNING"})
    api_main._write_evidence_bundle(run_id, {"summary": "ok"})

    promoted = api_main._promote_evidence(run_id, {"summary": "fallback"})
    assert promoted["ok"] is True

    rejected = api_main._reject_run_mutation(run_id)
    assert rejected == {"ok": True, "reason": "diff gate rejected"}

    approved = api_main._approve_god_mode_mutation(run_id, {"run_id": run_id, "source": "fallback"})
    assert approved == {"ok": True, "run_id": run_id}

    with pytest.raises(HTTPException) as exc_info:
        api_main._reject_run_mutation("run_missing_helper")
    assert exc_info.value.status_code == 404
