import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from openvibecoding_orch.contract.compiler import build_role_binding_summary

from .helpers.api_main_test_io import (
    _output_schema_artifacts,
    _write_artifact,
    _write_contract,
    _write_events,
    _write_intake_bundle,
    _write_manifest,
    _write_report,
)
from openvibecoding_orch.api import main as api_main
from openvibecoding_orch.api import routes_admin, routes_runs
from openvibecoding_orch.store import run_store as run_store_module
from openvibecoding_orch.store.run_store import RunStore


_TEST_HELPER_EXPORTS = (_write_intake_bundle,)


def test_api_list_runs_and_get_run(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    contracts_root = tmp_path / "contracts"
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("OPENVIBECODING_CONTRACT_ROOT", str(contracts_root))

    now = datetime.now(timezone.utc)
    run_a = runs_root / "run_a"
    run_b = runs_root / "run_b"
    (runs_root / "run_empty").mkdir(parents=True, exist_ok=True)
    contract_payload = {
        "allowed_paths": ["README.md"],
        "task_id": "task_a",
        "role_contract": {
            "skills_bundle_ref": "policies/skills_bundle_registry.json#bundles.worker_delivery_core_v1",
            "mcp_bundle_ref": "policies/agent_registry.json#agents(role=SEARCHER).capabilities.mcp_tools",
            "runtime_binding": {"runner": "agents", "provider": "cliproxyapi", "model": "gpt-5.4"},
            "resolved_mcp_tool_set": ["search-01-tavily"],
        },
    }
    _write_manifest(
        run_a,
        {
            "run_id": "run_a",
            "task_id": "task_a",
            "status": "SUCCESS",
            "created_at": (now - timedelta(minutes=5)).isoformat(),
            "role_binding_summary": build_role_binding_summary(contract_payload),
        },
    )
    _write_manifest(run_b, {"run_id": "run_b", "task_id": "task_b", "status": "FAILURE", "created_at": now.isoformat()})
    _write_contract(run_a, contract_payload)

    client = TestClient(api_main.app)
    resp = client.get("/api/runs")
    assert resp.status_code == 200
    payload = resp.json()
    assert [item["run_id"] for item in payload] == ["run_b", "run_a"]

    resp = client.get("/api/runs/run_a")
    assert resp.status_code == 200
    data = resp.json()
    assert data["run_id"] == "run_a"
    assert data["allowed_paths"] == ["README.md"]
    assert data["role_binding_read_model"] == data["manifest"]["role_binding_summary"]

    missing = client.get("/api/runs/missing")
    assert missing.status_code == 404


def test_api_list_runs_handles_mixed_sort_key_types(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    contracts_root = tmp_path / "contracts"
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("OPENVIBECODING_CONTRACT_ROOT", str(contracts_root))

    run_iso = runs_root / "run_iso"
    run_mtime = runs_root / "run_mtime"
    _write_manifest(
        run_iso,
        {
            "run_id": "run_iso",
            "task_id": "task_iso",
            "status": "SUCCESS",
            "created_at": "2026-02-09T07:00:00Z",
        },
    )
    _write_manifest(
        run_mtime,
        {
            "run_id": "run_mtime",
            "task_id": "task_mtime",
            "status": "SUCCESS",
        },
    )

    client = TestClient(api_main.app)
    resp = client.get("/api/runs")

    assert resp.status_code == 200
    payload = resp.json()
    assert {item["run_id"] for item in payload} == {"run_iso", "run_mtime"}


def test_api_get_run_falls_back_when_persisted_role_binding_summary_is_incomplete(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    contracts_root = tmp_path / "contracts"
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("OPENVIBECODING_CONTRACT_ROOT", str(contracts_root))

    run_dir = runs_root / "run_role_binding_fallback"
    contract_payload = {
        "allowed_paths": ["README.md"],
        "task_id": "task_role_binding_fallback",
        "role_contract": {
            "skills_bundle_ref": "policies/skills_bundle_registry.json#bundles.worker_delivery_core_v1",
            "mcp_bundle_ref": "policies/agent_registry.json#agents(role=SEARCHER).capabilities.mcp_tools",
            "runtime_binding": {"runner": "agents", "provider": "cliproxyapi", "model": "gpt-5.4"},
            "resolved_mcp_tool_set": ["search-01-tavily"],
        },
    }
    _write_manifest(
        run_dir,
        {
            "run_id": "run_role_binding_fallback",
            "task_id": "task_role_binding_fallback",
            "status": "SUCCESS",
            "role_binding_summary": {"authority": "broken-only"},
        },
    )
    _write_contract(run_dir, contract_payload)

    client = TestClient(api_main.app)
    resp = client.get("/api/runs/run_role_binding_fallback")
    assert resp.status_code == 200
    data = resp.json()
    assert data["role_binding_read_model"] == build_role_binding_summary(data["contract"])


def test_api_list_runs_skips_bad_manifest_and_normalizes_non_dict_contract(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    contracts_root = tmp_path / "contracts"
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("OPENVIBECODING_CONTRACT_ROOT", str(contracts_root))

    run_good = runs_root / "run_good"
    run_bad = runs_root / "run_bad"
    run_weird = runs_root / "run_weird"
    _write_manifest(run_good, {"run_id": "run_good", "task_id": "task_good", "status": "SUCCESS"})
    _write_manifest(run_weird, {"run_id": "run_weird", "task_id": "task_weird", "status": "SUCCESS"})
    run_bad.mkdir(parents=True, exist_ok=True)
    (run_bad / "manifest.json").write_text("{", encoding="utf-8")

    _write_contract(run_weird, ["not", "a", "dict"])  # type: ignore[arg-type]

    client = TestClient(api_main.app)
    runs_resp = client.get("/api/runs")
    assert runs_resp.status_code == 200
    run_ids = {item["run_id"] for item in runs_resp.json()}
    assert "run_good" in run_ids
    assert "run_weird" in run_ids
    assert "run_bad" not in run_ids

    weird_resp = client.get("/api/runs/run_weird")
    assert weird_resp.status_code == 200
    weird_payload = weird_resp.json()
    assert weird_payload["contract"] == {}
    assert weird_payload["allowed_paths"] == []


def test_api_events_diff_reports_artifacts(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    run_id = "run_events"
    run_dir = runs_root / run_id
    _write_manifest(run_dir, {"run_id": run_id, "task_id": "task", "status": "SUCCESS"})
    _write_events(run_dir, [json.dumps({"event": "TEST_RESULT", "ts": "2024-01-01T00:00:00Z"}), "not-json"])
    (run_dir / "patch.diff").write_text("diff --git a/a b/a\n", encoding="utf-8")
    _write_report(
        run_dir,
        "test_report.json",
        {
            "run_id": run_id,
            "task_id": "task",
            "runner": {"role": "TEST_RUNNER", "agent_id": "tests"},
            "started_at": "2024-01-01T00:00:00Z",
            "finished_at": "2024-01-01T00:00:01Z",
            "status": "PASS",
            "commands": [],
            "artifacts": [],
        },
    )
    _write_report(run_dir, "raw_report.json", "not-json")
    bad_reports_dir = run_dir / "reports" / "bad.json"
    bad_reports_dir.mkdir(parents=True, exist_ok=True)

    _write_artifact(run_dir, "note.txt", "hello")
    _write_artifact(run_dir, "payload.json", {"ok": True})
    bad_artifact_dir = run_dir / "artifacts" / "bad"
    bad_artifact_dir.mkdir(parents=True, exist_ok=True)

    client = TestClient(api_main.app)

    events = client.get(f"/api/runs/{run_id}/events")
    assert events.status_code == 200
    events_payload = events.json()
    assert events_payload[0]["event"] == "TEST_RESULT"
    assert events_payload[1]["raw"] == "not-json"

    diff = client.get(f"/api/runs/{run_id}/diff")
    assert diff.status_code == 200
    assert "diff --git" in diff.json()["diff"]

    reports = client.get(f"/api/runs/{run_id}/reports")
    assert reports.status_code == 500

    artifacts = client.get(f"/api/runs/{run_id}/artifacts")
    assert artifacts.status_code == 200
    items = artifacts.json()["items"]
    assert "note.txt" in items
    assert "payload.json" in items
    assert "bad" not in items

    artifact_json = client.get(f"/api/runs/{run_id}/artifacts", params={"name": "payload.json"})
    assert artifact_json.status_code == 200
    assert artifact_json.json()["data"] == {"ok": True}

    artifact_text = client.get(f"/api/runs/{run_id}/artifacts", params={"name": "note.txt"})
    assert artifact_text.status_code == 200
    assert artifact_text.json()["data"] == "hello"

    artifact_missing = client.get(f"/api/runs/{run_id}/artifacts", params={"name": "missing.txt"})
    assert artifact_missing.status_code == 200
    assert artifact_missing.json()["data"] is None

    artifact_error = client.get(f"/api/runs/{run_id}/artifacts", params={"name": "bad"})
    assert artifact_error.status_code == 400


def test_api_events_incremental_query_options(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    run_id = "run_events_incremental"
    run_dir = runs_root / run_id
    _write_manifest(run_dir, {"run_id": run_id, "task_id": "task", "status": "RUNNING"})
    _write_events(
        run_dir,
        [
            json.dumps({"event": "STEP_1", "ts": "2024-01-01T00:00:00Z"}),
            json.dumps({"event": "STEP_2", "ts": "2024-01-01T00:00:01Z"}),
            json.dumps({"event": "STEP_3", "ts": "2024-01-01T00:00:02Z"}),
            "not-json",
        ],
    )

    client = TestClient(api_main.app)

    all_events = client.get(f"/api/runs/{run_id}/events")
    assert all_events.status_code == 200
    assert len(all_events.json()) == 4

    since_events = client.get(f"/api/runs/{run_id}/events", params={"since": "2024-01-01T00:00:00Z"})
    assert since_events.status_code == 200
    assert [item.get("event") for item in since_events.json()] == ["STEP_2", "STEP_3"]

    head_limited = client.get(f"/api/runs/{run_id}/events", params={"limit": 2})
    assert head_limited.status_code == 200
    assert [item.get("event") for item in head_limited.json()] == ["STEP_1", "STEP_2"]

    tail_limited = client.get(f"/api/runs/{run_id}/events", params={"limit": 2, "tail": "1"})
    assert tail_limited.status_code == 200
    assert tail_limited.json()[0].get("event") == "STEP_3"
    assert tail_limited.json()[1].get("raw") == "not-json"


def test_api_events_stream_accepts_header_or_cookie_token_only(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("OPENVIBECODING_API_AUTH_REQUIRED", "1")
    monkeypatch.setenv("OPENVIBECODING_API_TOKEN", "stream-token")

    run_id = "run_stream"
    run_dir = runs_root / run_id
    _write_manifest(run_dir, {"run_id": run_id, "task_id": "task", "status": "RUNNING"})
    _write_events(run_dir, [json.dumps({"event": "STEP_STREAM", "ts": "2024-01-01T00:00:00Z"})])

    client = TestClient(api_main.app)

    missing = client.get(f"/api/runs/{run_id}/events/stream")
    assert missing.status_code == 401

    query_only = client.get(
        f"/api/runs/{run_id}/events/stream?access_token=stream-token&tail=1&limit=1&follow=0"
    )
    assert query_only.status_code == 401

    with client.stream(
        "GET",
        f"/api/runs/{run_id}/events/stream?tail=1&limit=1&follow=0",
        headers={"Authorization": "Bearer stream-token"},
    ) as stream_resp:
        assert stream_resp.status_code == 200
        assert stream_resp.headers["content-type"].startswith("text/event-stream")
        lines = []
        for raw in stream_resp.iter_lines():
            line = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
            if line:
                lines.append(line)
            if any(item.startswith("data: ") for item in lines):
                break
    assert any('"STEP_STREAM"' in item for item in lines)

    with client.stream(
        "GET",
        f"/api/runs/{run_id}/events/stream?tail=1&limit=1&follow=0",
        cookies={"openvibecoding_api_token": "stream-token"},
    ) as stream_resp:
        assert stream_resp.status_code == 200
        assert stream_resp.headers["content-type"].startswith("text/event-stream")


def test_api_rum_web_vitals_ingest_sanitizes_sensitive_fields(tmp_path: Path, monkeypatch) -> None:
    rum_path = tmp_path / "runtime" / "logs" / "runtime" / "rum_web_vitals.jsonl"
    monkeypatch.setattr(routes_admin, "_RUM_JSONL_PATH", rum_path)
    client = TestClient(api_main.app)

    response = client.post(
        "/api/rum/web-vitals",
        json={
            "name": "LCP",
            "value": 1234,
            "api_key": "secret-key",
            "nested": {"token": "token-value", "safe": "yes"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["ingested"] is True
    assert payload["artifact_kind"] == "rum_web_vitals"
    assert "reason" not in payload

    lines = rum_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    written = json.loads(lines[0])
    assert written["level"] == "INFO"
    assert written["domain"] == "ui"
    assert written["surface"] == "dashboard"
    assert written["service"] == "openvibecoding-dashboard"
    assert written["component"] == "api.routes_admin"
    assert written["lane"] == "runtime"
    assert written["artifact_kind"] == "rum_web_vitals"
    assert written["schema_version"] == "log_event.v2"
    assert written["redaction_version"] == "redaction.v1"
    assert written["event"] == "RUM_WEB_VITAL_RECEIVED"
    assert written["meta"]["payload_size_bytes"] > 0
    assert written["meta"]["payload"]["api_key"] == "[REDACTED]"
    assert written["meta"]["payload"]["nested"]["token"] == "[REDACTED]"
    assert written["meta"]["payload"]["nested"]["safe"] == "yes"


def test_api_rum_web_vitals_ingest_write_failure_reports_reason(tmp_path: Path, monkeypatch) -> None:
    broken_parent = tmp_path / "broken_parent"
    broken_parent.write_text("not-a-dir", encoding="utf-8")
    monkeypatch.setattr(routes_admin, "_RUM_JSONL_PATH", broken_parent / "rum_web_vitals.jsonl")
    client = TestClient(api_main.app)

    response = client.post("/api/rum/web-vitals", json={"name": "CLS", "value": 0.01})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["ingested"] is False
    assert isinstance(payload.get("reason"), str) and payload["reason"].strip()


def test_api_rum_web_vitals_ingest_rejects_oversized_payload(tmp_path: Path, monkeypatch) -> None:
    rum_path = tmp_path / "runtime" / "logs" / "runtime" / "rum_web_vitals.jsonl"
    monkeypatch.setattr(routes_admin, "_RUM_JSONL_PATH", rum_path)
    monkeypatch.setattr(routes_admin, "_RUM_MAX_PAYLOAD_BYTES", 64)
    client = TestClient(api_main.app)

    response = client.post("/api/rum/web-vitals", json={"name": "LCP", "value": "x" * 512})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["ingested"] is False
    assert payload["reason"] == "PAYLOAD_TOO_LARGE"
    assert not rum_path.exists()


def test_api_artifact_path_traversal_blocked(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    run_id = "run_safe"
    run_dir = runs_root / run_id
    _write_manifest(run_dir, {"run_id": run_id, "task_id": "task", "status": "SUCCESS"})
    _write_artifact(run_dir, "ok.json", {"ok": True})

    client = TestClient(api_main.app)

    ok_resp = client.get(f"/api/runs/{run_id}/artifacts", params={"name": "ok.json"})
    assert ok_resp.status_code == 200
    assert ok_resp.json()["data"] == {"ok": True}

    traversal_resp = client.get(f"/api/runs/{run_id}/artifacts", params={"name": "../contract.json"})
    assert traversal_resp.status_code == 400
    assert traversal_resp.json()["detail"]["code"] == "ARTIFACT_PATH_ESCAPE"

    abs_resp = client.get(f"/api/runs/{run_id}/artifacts", params={"name": "/etc/passwd"})
    assert abs_resp.status_code == 400
    assert abs_resp.json()["detail"]["code"] == "ARTIFACT_PATH_INVALID"


def test_api_run_id_traversal_blocked_in_events_route(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))

    # Parent file exists to prove traversal would leak data without validation.
    (tmp_path / "events.jsonl").write_text(json.dumps({"event": "LEAK"}) + "\n", encoding="utf-8")

    client = TestClient(api_main.app)
    response = client.get("/api/runs/%2E%2E/events")

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "RUN_ID_INVALID"


def test_api_auth_required_for_api_routes(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("OPENVIBECODING_API_AUTH_REQUIRED", "1")
    monkeypatch.setenv("OPENVIBECODING_API_TOKEN", "test-token")

    run_dir = runs_root / "run_auth"
    _write_manifest(run_dir, {"run_id": "run_auth", "task_id": "task", "status": "SUCCESS"})

    client = TestClient(api_main.app)

    health = client.get("/health")
    assert health.status_code == 200
    api_health = client.get("/api/health")
    assert api_health.status_code == 200

    missing = client.get("/api/runs")
    assert missing.status_code == 401
    assert missing.json()["detail"]["code"] == "AUTH_MISSING_BEARER"

    invalid = client.get("/api/runs", headers={"Authorization": "Bearer wrong"})
    assert invalid.status_code == 401
    assert invalid.json()["detail"]["code"] == "AUTH_INVALID_TOKEN"

    ok = client.get("/api/runs", headers={"Authorization": "Bearer test-token"})
    assert ok.status_code == 200


def test_api_auth_uses_compare_digest_for_equivalent_token_paths(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("OPENVIBECODING_API_AUTH_REQUIRED", "1")
    monkeypatch.setenv("OPENVIBECODING_API_TOKEN", "cmp-token")

    run_dir = runs_root / "run_cmp"
    _write_manifest(run_dir, {"run_id": "run_cmp", "task_id": "task", "status": "SUCCESS"})

    calls: list[tuple[str, str]] = []

    def _compare_digest(left: str, right: str) -> bool:
        calls.append((left, right))
        return left == right

    monkeypatch.setattr(api_main.hmac, "compare_digest", _compare_digest)
    client = TestClient(api_main.app)

    header_ok = client.get("/api/runs", headers={"Authorization": "Bearer cmp-token"})
    cookie_ok = client.get("/api/runs", cookies={"openvibecoding_api_token": "cmp-token"})
    invalid = client.get("/api/runs", headers={"Authorization": "Bearer wrong"})

    assert header_ok.status_code == 200
    assert cookie_ok.status_code == 200
    assert invalid.status_code == 401
    assert invalid.json()["detail"]["code"] == "AUTH_INVALID_TOKEN"
    assert calls[-1] == ("wrong", "cmp-token")
    assert ("cmp-token", "cmp-token") in calls


def test_api_auth_skips_options_preflight(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("OPENVIBECODING_API_AUTH_REQUIRED", "1")
    monkeypatch.setenv("OPENVIBECODING_API_TOKEN", "test-token")

    client = TestClient(api_main.app)

    preflight = client.options(
        "/api/command-tower/overview",
        headers={
            "Origin": "http://localhost:3100",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert preflight.status_code in {200, 204}
    assert preflight.headers.get("access-control-allow-origin") == "http://localhost:3100"

    blocked = client.options(
        "/api/command-tower/overview",
        headers={
            "Origin": "http://192.168.1.10:3100",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert blocked.headers.get("access-control-allow-origin") is None


def test_resolve_allow_origins_includes_configured_public_origins() -> None:
    resolved = api_main._resolve_allow_origins(  # noqa: SLF001
        "3100",
        (
            "https://dashboard.example.com/",
            "https://dashboard.example.com",
            "https://ops.example.com",
        ),
    )
    assert "http://localhost:3100" in resolved
    assert "http://127.0.0.1:3100" in resolved
    resolved_https_hosts = {
        (parts.scheme, parts.netloc)
        for item in resolved
        if (parts := urlsplit(item)).scheme == "https"
    }
    assert ("https", "dashboard.example.com") in resolved_https_hosts
    assert ("https", "ops.example.com") in resolved_https_hosts
    assert len([item for item in resolved_https_hosts if item == ("https", "dashboard.example.com")]) == 1


def test_api_runs_role_header_requires_trusted_auth_context(monkeypatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_API_AUTH_REQUIRED", "1")
    app = FastAPI()
    app.include_router(routes_runs.router)
    app.state.routes_runs_handlers = {}

    client = TestClient(app)
    response = client.post("/api/runs/run_guard/reject", headers={"x-openvibecoding-role": "TECH_LEAD"})
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "ROLE_HEADER_UNTRUSTED"


def test_api_admin_role_header_requires_trusted_auth_context(monkeypatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_API_AUTH_REQUIRED", "1")
    app = FastAPI()
    app.include_router(routes_admin.router)
    app.state.routes_admin_handlers = {}

    client = TestClient(app)
    response = client.post(
        "/api/god-mode/approve",
        json={"run_id": "run_guard"},
        headers={"x-openvibecoding-role": "TECH_LEAD"},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "ROLE_HEADER_UNTRUSTED"


def test_api_admin_approve_requestless_path_is_fail_closed() -> None:
    with pytest.raises(HTTPException) as exc_info:
        routes_admin.approve_god_mode({"run_id": "run_guard"})
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "APPROVAL_NOT_PENDING"


def test_api_replay_and_contracts_and_god_mode(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    contracts_root = tmp_path / "contracts"
    examples = contracts_root / "examples"
    examples.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("OPENVIBECODING_CONTRACT_ROOT", str(contracts_root))

    now = datetime.now(timezone.utc)
    run_current = runs_root / "run_current"
    run_baseline = runs_root / "run_baseline"
    _write_manifest(run_current, {"run_id": "run_current", "task_id": "task", "status": "SUCCESS", "created_at": now.isoformat()})
    _write_manifest(run_baseline, {"run_id": "run_baseline", "task_id": "task", "status": "SUCCESS", "created_at": (now - timedelta(minutes=1)).isoformat()})

    (examples / "contract.json").write_text(
        json.dumps({"task_id": "example", "assigned_agent": {"agent_id": "agent-1", "role": "WORKER"}}),
        encoding="utf-8",
    )

    class DummyOrchestrationService:
        def replay_run(self, run_id: str, baseline_run_id: str | None = None) -> dict:
            return {"run_id": run_id, "baseline_run_id": baseline_run_id}

    monkeypatch.setattr(api_main, "_orchestration_service", DummyOrchestrationService())

    client = TestClient(api_main.app)

    payload = {
        "baseline_window": {
            "created_at": (now - timedelta(minutes=2)).isoformat(),
            "finished_at": now.isoformat(),
        }
    }
    replay_headers = {"x-openvibecoding-role": "TECH_LEAD"}
    resp = client.post("/api/runs/run_current/replay", json=payload, headers=replay_headers)
    assert resp.status_code == 200
    assert resp.json()["baseline_run_id"] == "run_baseline"

    contracts = client.get("/api/contracts")
    assert contracts.status_code == 200
    assert contracts.json()[0]["task_id"] == "example"
    assert contracts.json()[0]["source"] == "examples"
    assert contracts.json()[0]["execution_authority"] == "task_contract"

    store = RunStore(runs_root=runs_root)
    monkeypatch.setattr(run_store_module, "_default_store", store)
    _write_events(run_current, [json.dumps({"event": "HUMAN_APPROVAL_REQUIRED"})])
    god = client.post(
        "/api/god-mode/approve",
        json={"run_id": "run_current"},
        headers={"x-openvibecoding-role": "TECH_LEAD"},
    )
    assert god.status_code == 200
    events_text = (runs_root / "run_current" / "events.jsonl").read_text(encoding="utf-8")
    assert "HUMAN_APPROVAL_COMPLETED" in events_text

    missing = client.post("/api/god-mode/approve", json={}, headers={"x-openvibecoding-role": "TECH_LEAD"})
    assert missing.status_code == 400
    assert missing.json()["detail"]["code"] == "RUN_ID_REQUIRED"


def test_api_god_mode_approve_requires_role_and_pending(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    run_dir = runs_root / "run_gate"
    _write_manifest(run_dir, {"run_id": "run_gate", "task_id": "task", "status": "RUNNING"})

    client = TestClient(api_main.app)

    missing_role = client.post("/api/god-mode/approve", json={"run_id": "run_gate"})
    assert missing_role.status_code == 403
    assert missing_role.json()["detail"]["code"] == "ROLE_REQUIRED"

    forbidden_role = client.post(
        "/api/god-mode/approve",
        json={"run_id": "run_gate"},
        headers={"x-openvibecoding-role": "WORKER"},
    )
    assert forbidden_role.status_code == 403
    assert forbidden_role.json()["detail"]["code"] == "ROLE_FORBIDDEN"

    not_pending = client.post(
        "/api/god-mode/approve",
        json={"run_id": "run_gate"},
        headers={"x-openvibecoding-role": "TECH_LEAD"},
    )
    assert not_pending.status_code == 409
    assert not_pending.json()["detail"]["code"] == "APPROVAL_NOT_PENDING"


def test_api_baseline_window_and_empty_artifacts(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))

    run_current = runs_root / "run_current"
    _write_manifest(run_current, {"run_id": "run_current", "task_id": "task", "status": "SUCCESS", "created_at": "2024-01-02T00:00:00Z"})
    run_candidate = runs_root / "run_candidate"
    _write_manifest(run_candidate, {"run_id": "run_candidate", "task_id": "task", "status": "SUCCESS", "created_at": "2024-01-01T00:00:00"})
    run_bad_ts = runs_root / "run_bad_ts"
    _write_manifest(run_bad_ts, {"run_id": "run_bad_ts", "task_id": "task", "status": "SUCCESS", "created_at": "bad"})

    client = TestClient(api_main.app)

    class DummyOrchestrationService:
        def replay_run(self, run_id: str, baseline_run_id: str | None = None) -> dict:
            return {"run_id": run_id, "baseline_run_id": baseline_run_id}

    monkeypatch.setattr(api_main, "_orchestration_service", DummyOrchestrationService())

    assert api_main._parse_iso_ts("2024-01-01T00:00:00").tzinfo is not None
    assert api_main._parse_iso_ts("2024-01-01T00:00:00Z").tzinfo is not None

    replay_headers = {"x-openvibecoding-role": "TECH_LEAD"}
    resp = client.post("/api/runs/run_current/replay", json={"baseline_window": "bad"}, headers=replay_headers)
    assert resp.status_code == 400

    replay = client.post(
        "/api/runs/run_current/replay",
        json={"baseline_window": {"created_at": "2024-01-01T00:00:00Z", "finished_at": "2024-01-03T00:00:00Z"}},
        headers=replay_headers,
    )
    assert replay.status_code == 200
    assert replay.json()["baseline_run_id"] == "run_candidate"


def test_api_baseline_window_invalid_manifest(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))

    run_current = runs_root / "run_current"
    _write_manifest(run_current, {"run_id": "run_current", "task_id": "task", "status": "SUCCESS", "created_at": "2024-01-02T00:00:00Z"})
    bad_manifest = runs_root / "run_bad"
    bad_manifest.mkdir(parents=True, exist_ok=True)
    (bad_manifest / "manifest.json").write_text("{", encoding="utf-8")

    client = TestClient(api_main.app)

    class DummyOrchestrationService:
        def replay_run(self, run_id: str, baseline_run_id: str | None = None) -> dict:
            return {"run_id": run_id, "baseline_run_id": baseline_run_id}

    monkeypatch.setattr(api_main, "_orchestration_service", DummyOrchestrationService())

    replay = client.post(
        "/api/runs/run_current/replay",
        json={"baseline_window": {"created_at": "2024-01-01T00:00:00Z", "finished_at": "2024-01-03T00:00:00Z"}},
        headers={"x-openvibecoding-role": "TECH_LEAD"},
    )
    assert replay.status_code == 400

    empty_events = client.get("/api/runs/run_missing/events")
    assert empty_events.status_code == 200
    assert empty_events.json() == []

    empty_reports = client.get("/api/runs/run_missing/reports")
    assert empty_reports.status_code == 200
    assert empty_reports.json() == []

    empty_artifacts = client.get("/api/runs/run_missing/artifacts")
    assert empty_artifacts.status_code == 200
    assert empty_artifacts.json()["items"] == []


def test_api_rollback_and_reject(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    run_id = "run_reject"
    run_dir = runs_root / run_id
    _write_manifest(run_dir, {"run_id": run_id, "task_id": "task", "status": "SUCCESS"})
    _write_contract(run_dir, {"rollback": {"strategy": "git_reset_hard", "baseline_ref": "HEAD"}})

    store = RunStore(runs_root=runs_root)
    monkeypatch.setattr(run_store_module, "_default_store", store)

    client = TestClient(api_main.app)
    headers = {"x-openvibecoding-role": "TECH_LEAD"}
    rollback = client.post(f"/api/runs/{run_id}/rollback", headers=headers)
    assert rollback.status_code == 422
    rollback_detail = rollback.json()["detail"]
    assert rollback_detail["code"] == "ROLLBACK_FAILED"
    assert isinstance(rollback_detail["request_id"], str)
    assert isinstance(rollback_detail["trace_id"], str)
    assert rollback_detail["reason"]

    reject = client.post(f"/api/runs/{run_id}/reject", headers=headers)
    assert reject.status_code == 200
    assert reject.json()["ok"] is True
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "FAILURE"
    assert manifest["failure_reason"] == "diff gate rejected"


def test_api_reject_failures_are_not_returned_as_http_200(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    run_id = "run_reject_fail"
    run_dir = runs_root / run_id
    _write_manifest(run_dir, {"run_id": run_id, "task_id": "task", "status": "RUNNING"})

    class DummyRejectService:
        def reject_run(self, _run_id: str, reason: str = "diff gate rejected") -> dict[str, object]:
            return {"ok": False, "reason": f"reject denied: {reason}"}

    monkeypatch.setattr(api_main, "_orchestration_service", DummyRejectService())

    client = TestClient(api_main.app)
    reject = client.post(f"/api/runs/{run_id}/reject", headers={"x-openvibecoding-role": "TECH_LEAD"})
    assert reject.status_code == 422
    detail = reject.json()["detail"]
    assert detail["code"] == "REJECT_FAILED"
    assert detail["reason"] == "reject denied: diff gate rejected"


def test_api_runs_mutation_routes_require_role(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    run_id = "run_role_guard"
    run_dir = runs_root / run_id
    _write_manifest(run_dir, {"run_id": run_id, "task_id": "task", "status": "RUNNING"})
    _write_contract(run_dir, {"assigned_agent": {"role": "SEARCHER", "agent_id": "agent-1"}, "inputs": {"artifacts": []}})
    _write_artifact(run_dir, "search_results.json", {"results": [{"title": "x"}]})

    client = TestClient(api_main.app)
    targets = [
        f"/api/runs/{run_id}/evidence/promote",
        f"/api/runs/{run_id}/rollback",
        f"/api/runs/{run_id}/reject",
        f"/api/runs/{run_id}/replay",
        f"/api/runs/{run_id}/verify",
        f"/api/runs/{run_id}/reexec",
    ]
    for target in targets:
        missing_role = client.post(target)
        assert missing_role.status_code == 403
        assert missing_role.json()["detail"]["code"] == "ROLE_REQUIRED"

        forbidden_role = client.post(target, headers={"x-openvibecoding-role": "WORKER"})
        assert forbidden_role.status_code == 403
        assert forbidden_role.json()["detail"]["code"] == "ROLE_FORBIDDEN"


def test_api_locks_release_requires_mutation_role_and_releases_paths(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    locks_dir = runtime_root / "locks"
    locks_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_FORCE_UNLOCK", "1")

    target_path = "apps/orchestrator/src/example.py"
    lock_name = hashlib.sha256(target_path.encode("utf-8")).hexdigest()
    lock_path = locks_dir / f"{lock_name}.lock"
    lock_path.write_text(
        "\n".join(
            [
                "run_id=run-lock",
                f"path={target_path}",
                "ts=2024-01-01T00:00:00Z",
            ]
        ),
        encoding="utf-8",
    )

    client = TestClient(api_main.app)
    payload = {"paths": [target_path]}

    missing_role = client.post("/api/locks/release", json=payload)
    assert missing_role.status_code == 403
    assert missing_role.json()["detail"]["code"] == "ROLE_REQUIRED"

    forbidden_role = client.post("/api/locks/release", json=payload, headers={"x-openvibecoding-role": "WORKER"})
    assert forbidden_role.status_code == 403
    assert forbidden_role.json()["detail"]["code"] == "ROLE_FORBIDDEN"

    invalid_payload = client.post(
        "/api/locks/release",
        json={"paths": "not-an-array"},
        headers={"x-openvibecoding-role": "TECH_LEAD"},
    )
    assert invalid_payload.status_code == 422

    released = client.post("/api/locks/release", json=payload, headers={"x-openvibecoding-role": "TECH_LEAD"})
    assert released.status_code == 200
    assert released.json() == {"ok": True, "released_paths": [target_path]}
    assert not lock_path.exists()


def test_api_runs_mutation_routes_accept_role_after_token_auth(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("OPENVIBECODING_API_AUTH_REQUIRED", "1")
    monkeypatch.setenv("OPENVIBECODING_API_TOKEN", "secure-token")
    run_id = "run_auth_role"
    run_dir = runs_root / run_id
    _write_manifest(run_dir, {"run_id": run_id, "task_id": "task", "status": "RUNNING"})

    client = TestClient(api_main.app)
    base_headers = {"Authorization": "Bearer secure-token"}
    target = f"/api/runs/{run_id}/reject"

    missing_role = client.post(target, headers=base_headers)
    assert missing_role.status_code == 403
    assert missing_role.json()["detail"]["code"] == "ROLE_REQUIRED"

    forbidden_role = client.post(target, headers={**base_headers, "x-openvibecoding-role": "WORKER"})
    assert forbidden_role.status_code == 403
    assert forbidden_role.json()["detail"]["code"] == "ROLE_FORBIDDEN"

    approved_role = client.post(target, headers={**base_headers, "x-openvibecoding-role": "TECH_LEAD"})
    assert approved_role.status_code == 200
    assert approved_role.json()["ok"] is True


def test_api_validation_error_body_uses_standard_detail_shape() -> None:
    client = TestClient(api_main.app)
    response = client.get("/api/pm/sessions", params={"limit": 0})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "REQUEST_VALIDATION_ERROR"
    assert detail["reason"] == "request validation failed"
    assert isinstance(detail["request_id"], str)
    assert isinstance(detail["trace_id"], str)
