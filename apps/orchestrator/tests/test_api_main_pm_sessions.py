import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from cortexpilot_orch.api import main as api_main
from cortexpilot_orch.api import pm_session_aggregation

from .test_api_main import _write_events, _write_intake_bundle, _write_manifest


def test_api_pm_sessions_and_command_tower_endpoints(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runs_root))

    now = datetime.now(timezone.utc)
    run_a1 = runs_root / "run_a1"
    run_a2 = runs_root / "run_a2"
    run_b1 = runs_root / "run_b1"

    _write_manifest(
        run_a1,
        {
            "run_id": "run_a1",
            "task_id": "task_a1",
            "status": "RUNNING",
            "status_reason": "WAITING_APPROVAL",
            "created_at": (now - timedelta(minutes=11)).isoformat(),
        },
    )
    _write_manifest(
        run_a2,
        {
            "run_id": "run_a2",
            "task_id": "task_a2",
            "status": "SUCCESS",
            "created_at": (now - timedelta(minutes=7)).isoformat(),
            "finished_at": (now - timedelta(minutes=2)).isoformat(),
        },
    )
    _write_manifest(
        run_b1,
        {
            "run_id": "run_b1",
            "task_id": "task_b1",
            "status": "FAILURE",
            "failure_reason": "missing LLM API key (GEMINI_API_KEY)",
            "created_at": (now - timedelta(minutes=3)).isoformat(),
            "finished_at": (now - timedelta(minutes=1)).isoformat(),
        },
    )

    _write_events(
        run_a1,
        [
            json.dumps(
                {
                    "event": "CHAIN_STEP_STARTED",
                    "ts": (now - timedelta(minutes=10)).isoformat(),
                    "context": {"step": "implement", "role": "WORKER"},
                }
            ),
            json.dumps(
                {
                    "event": "CHAIN_HANDOFF",
                    "ts": (now - timedelta(minutes=9)).isoformat(),
                    "context": {"from_role": "PM", "to_role": "TECH_LEAD"},
                }
            ),
            json.dumps({"event": "HUMAN_APPROVAL_REQUIRED", "ts": (now - timedelta(minutes=8)).isoformat()}),
        ],
    )
    _write_events(
        run_a2,
        [
            json.dumps(
                {
                    "event": "CHAIN_HANDOFF",
                    "ts": (now - timedelta(minutes=6)).isoformat(),
                    "context": {"from_role": "TECH_LEAD", "to_role": "WORKER"},
                }
            ),
            json.dumps({"event": "HUMAN_APPROVAL_REQUIRED", "ts": (now - timedelta(minutes=5)).isoformat()}),
            json.dumps({"event": "HUMAN_APPROVAL_COMPLETED", "ts": (now - timedelta(minutes=4)).isoformat()}),
            json.dumps({"event": "CHAIN_STEP_RESULT", "ts": (now - timedelta(minutes=3)).isoformat()}),
        ],
    )
    _write_events(
        run_b1,
        [
            json.dumps(
                {
                    "event": "CHAIN_HANDOFF",
                    "ts": (now - timedelta(minutes=2)).isoformat(),
                    "context": {"from_role": "PM", "to_role": "TECH_LEAD"},
                }
            ),
            json.dumps({"event": "CHAIN_STEP_RESULT", "ts": (now - timedelta(minutes=1)).isoformat()}),
        ],
    )

    _write_intake_bundle(
        runtime_root,
        "session_a",
        {
            "intake_id": "session_a",
            "objective": "Build command tower",
            "owner_agent": {"role": "PM", "agent_id": "pm-alpha"},
            "project_key": "cortexpilot",
            "created_at": (now - timedelta(minutes=15)).isoformat(),
        },
        {
            "intake_id": "session_a",
            "chain_run_id": "run_a2",
            "updated_at": (now - timedelta(minutes=2)).isoformat(),
        },
        [
            {"event": "INTAKE_CREATED", "ts": (now - timedelta(minutes=15)).isoformat()},
            {"event": "INTAKE_RUN", "run_id": "run_a1", "ts": (now - timedelta(minutes=12)).isoformat()},
            {"event": "INTAKE_CHAIN_RUN", "run_id": "run_a2", "ts": (now - timedelta(minutes=7)).isoformat()},
        ],
    )

    _write_intake_bundle(
        runtime_root,
        "session_b",
        {
            "intake_id": "session_b",
            "objective": "Fix pipeline",
            "owner_agent": {"role": "PM", "agent_id": "pm-beta"},
            "created_at": (now - timedelta(minutes=4)).isoformat(),
        },
        {
            "intake_id": "session_b",
            "chain_run_id": "run_b1",
            "updated_at": (now - timedelta(minutes=1)).isoformat(),
        },
        [
            {"event": "INTAKE_CREATED", "ts": (now - timedelta(minutes=4)).isoformat()},
            {"event": "INTAKE_CHAIN_RUN", "run_id": "run_b1", "ts": (now - timedelta(minutes=3)).isoformat()},
        ],
    )

    client = TestClient(api_main.app)

    sessions_resp = client.get("/api/pm/sessions")
    assert sessions_resp.status_code == 200
    sessions_payload = sessions_resp.json()
    assert len(sessions_payload) == 2
    assert {item["pm_session_id"] for item in sessions_payload} == {"session_a", "session_b"}

    active_only = client.get("/api/pm/sessions", params={"status": "active"})
    assert active_only.status_code == 200
    assert [item["pm_session_id"] for item in active_only.json()] == ["session_a"]

    status_array = client.get("/api/pm/sessions", params=[("status[]", "active"), ("status[]", "failed")])
    assert status_array.status_code == 200
    assert {item["pm_session_id"] for item in status_array.json()} == {"session_a", "session_b"}

    owner_filter = client.get("/api/pm/sessions", params={"owner_pm": "pm-beta"})
    assert owner_filter.status_code == 200
    assert [item["pm_session_id"] for item in owner_filter.json()] == ["session_b"]

    project_filter = client.get("/api/pm/sessions", params={"project_key": "cortexpilot"})
    assert project_filter.status_code == 200
    assert [item["pm_session_id"] for item in project_filter.json()] == ["session_a"]

    sorted_by_blockers = client.get("/api/pm/sessions", params={"sort": "blocked_desc"})
    assert sorted_by_blockers.status_code == 200
    assert sorted_by_blockers.json()[0]["pm_session_id"] == "session_a"

    bad_status = client.get("/api/pm/sessions", params={"status": "unknown"})
    assert bad_status.status_code == 400
    assert bad_status.json()["detail"]["code"] == "PM_SESSION_STATUS_INVALID"

    bad_sort = client.get("/api/pm/sessions", params={"sort": "unknown_sort"})
    assert bad_sort.status_code == 400
    assert bad_sort.json()["detail"]["code"] == "PM_SESSION_SORT_INVALID"

    detail = client.get("/api/pm/sessions/session_a")
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["session"]["pm_session_id"] == "session_a"
    assert detail_payload["session"]["status"] == "active"
    assert detail_payload["session"]["session_source"] == "intake"
    assert detail_payload["session"]["blocked_runs"] == 1
    assert set(detail_payload["run_ids"]) == {"run_a1", "run_a2"}
    assert len(detail_payload["bindings"]) >= 2
    assert any(item["run_id"] == "run_a1" for item in detail_payload["bindings"])
    assert len(detail_payload["blockers"]) == 1

    failed_detail = client.get("/api/pm/sessions/session_b")
    assert failed_detail.status_code == 200
    failed_payload = failed_detail.json()
    failed_run = next(item for item in failed_payload["runs"] if item["run_id"] == "run_b1")
    assert "missing LLM API key" in failed_run["failure_reason"]

    post_message = client.post(
        "/api/pm/sessions/session_a/messages",
        json={"message": "Please prioritize flaky tests", "from_role": "PM", "to_role": "TECH_LEAD", "kind": "chat"},
    )
    assert post_message.status_code == 200
    post_payload = post_message.json()
    assert post_payload["ok"] is True
    assert post_payload["event"]["event"] == "PM_MESSAGE"
    assert post_payload["event"]["context"]["message"] == "Please prioritize flaky tests"

    session_events = client.get("/api/pm/sessions/session_a/events")
    assert session_events.status_code == 200
    assert any(
        item.get("event") == "PM_MESSAGE"
        and item.get("_source") == "session"
        and ((item.get("context") or {}).get("message") == "Please prioritize flaky tests")
        for item in session_events.json()
    )

    bad_message = client.post("/api/pm/sessions/session_a/messages", json={"message": "   "})
    assert bad_message.status_code == 400
    assert bad_message.json()["detail"]["code"] == "PM_SESSION_MESSAGE_INVALID"

    missing_session_message = client.post("/api/pm/sessions/session_missing/messages", json={"message": "hi"})
    assert missing_session_message.status_code == 404
    assert missing_session_message.json()["detail"]["code"] == "PM_SESSION_NOT_FOUND"

    events = client.get("/api/pm/sessions/session_a/events", params=[("types[]", "CHAIN_HANDOFF")])
    assert events.status_code == 200
    events_payload = events.json()
    assert len(events_payload) == 2
    assert all(item["event"] == "CHAIN_HANDOFF" for item in events_payload)
    assert all(item.get("_run_id") in {"run_a1", "run_a2"} for item in events_payload)

    scalar_type_filtered = client.get("/api/pm/sessions/session_a/events", params={"types": "HUMAN_APPROVAL_REQUIRED"})
    assert scalar_type_filtered.status_code == 200
    scalar_type_payload = scalar_type_filtered.json()
    assert len(scalar_type_payload) == 2
    assert all(item["event"] == "HUMAN_APPROVAL_REQUIRED" for item in scalar_type_payload)

    run_filtered = client.get("/api/pm/sessions/session_a/events", params=[("run_ids[]", "run_a2")])
    assert run_filtered.status_code == 200
    assert all(item.get("_run_id") == "run_a2" for item in run_filtered.json())

    scalar_run_filtered = client.get("/api/pm/sessions/session_a/events", params={"run_ids": "run_a1"})
    assert scalar_run_filtered.status_code == 200
    assert all(item.get("_run_id") == "run_a1" for item in scalar_run_filtered.json())

    bad_run_filter = client.get("/api/pm/sessions/session_a/events", params=[("run_ids[]", "run_missing")])
    assert bad_run_filter.status_code == 400
    assert bad_run_filter.json()["detail"]["code"] == "PM_SESSION_CURSOR_INVALID"

    graph = client.get("/api/pm/sessions/session_a/conversation-graph", params={"window": "24h"})
    assert graph.status_code == 200
    graph_payload = graph.json()
    assert graph_payload["pm_session_id"] == "session_a"
    assert graph_payload["stats"]["edge_count"] >= 2
    assert "PM" in graph_payload["nodes"]

    grouped_graph = client.get(
        "/api/pm/sessions/session_a/conversation-graph",
        params={"window": "24h", "group_by_role": 1},
    )
    assert grouped_graph.status_code == 200
    grouped_payload = grouped_graph.json()
    assert grouped_payload["group_by_role"] is True
    assert all("count" in item for item in grouped_payload["edges"])

    bad_window = client.get("/api/pm/sessions/session_a/conversation-graph", params={"window": "7d"})
    assert bad_window.status_code == 400
    assert bad_window.json()["detail"]["code"] == "PM_SESSION_WINDOW_INVALID"

    metrics = client.get("/api/pm/sessions/session_a/metrics")
    assert metrics.status_code == 200
    metrics_payload = metrics.json()
    assert metrics_payload["run_count"] == 2
    assert metrics_payload["running_runs"] == 1
    assert metrics_payload["success_runs"] == 1
    assert metrics_payload["blocked_runs"] == 1
    assert metrics_payload["potential_blocked_runs"] == 0
    assert metrics_payload["failure_rate"] == 0.0
    assert metrics_payload["blocked_ratio"] == 0.5
    assert metrics_payload["potential_blocked_ratio"] == 0.0
    assert "cycle_time_seconds" in metrics_payload
    assert "mttr_seconds" in metrics_payload

    overview = client.get("/api/command-tower/overview")
    assert overview.status_code == 200
    overview_payload = overview.json()
    assert overview_payload["total_sessions"] == 2
    assert overview_payload["active_sessions"] == 1
    assert overview_payload["failed_sessions"] == 1
    assert overview_payload["blocked_sessions"] == 1
    assert overview_payload["failed_ratio"] == 0.5
    assert overview_payload["blocked_ratio"] == 0.5
    assert overview_payload["failure_trend_30m"] >= 1
    assert len(overview_payload["top_blockers"]) >= 1
    assert "slo_targets" in overview_payload
    assert overview_payload["meta"]["cache_hit"] is False
    assert overview_payload["meta"]["generated_from"] == "recomputed"

    overview_cached = client.get("/api/command-tower/overview")
    assert overview_cached.status_code == 200
    overview_cached_payload = overview_cached.json()
    assert overview_cached_payload["meta"]["cache_hit"] is True
    assert overview_cached_payload["meta"]["generated_from"] == "cache_snapshot"

    alerts = client.get("/api/command-tower/alerts")
    assert alerts.status_code == 200
    alerts_payload = alerts.json()
    assert alerts_payload["status"] in {"critical", "degraded", "healthy"}
    assert isinstance(alerts_payload["alerts"], list)
    assert "slo_targets" in alerts_payload
    assert alerts_payload["meta"]["overview_cache_hit"] is True

    missing = client.get("/api/pm/sessions/session_missing")
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "PM_SESSION_NOT_FOUND"


def test_api_pm_sessions_openapi_exposes_status_array_filter() -> None:
    client = TestClient(api_main.app)
    response = client.get("/openapi.json")
    assert response.status_code == 200
    payload = response.json()
    parameters = payload["paths"]["/api/pm/sessions"]["get"]["parameters"]
    names = {item["name"] for item in parameters}
    assert "status" in names
    assert "status[]" in names

    event_parameters = payload["paths"]["/api/pm/sessions/{pm_session_id}/events"]["get"]["parameters"]
    event_names = {item["name"] for item in event_parameters}
    assert "types" in event_names
    assert "types[]" in event_names
    assert "run_ids" in event_names
    assert "run_ids[]" in event_names


def test_api_pm_sessions_list_uses_lightweight_context(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runs_root))

    now = datetime.now(timezone.utc)
    run_l1 = runs_root / "run_l1"
    _write_manifest(
        run_l1,
        {
            "run_id": "run_l1",
            "task_id": "task_l1",
            "status": "RUNNING",
            "created_at": (now - timedelta(minutes=2)).isoformat(),
        },
    )
    _write_events(
        run_l1,
        [
            json.dumps({"event": "CHAIN_STEP_STARTED", "ts": (now - timedelta(minutes=1)).isoformat()}),
        ],
    )
    _write_intake_bundle(
        runtime_root,
        "session_lightweight",
        {
            "intake_id": "session_lightweight",
            "objective": "Lightweight list",
            "owner_agent": {"role": "PM", "agent_id": "pm-lite"},
            "created_at": (now - timedelta(minutes=3)).isoformat(),
        },
        {
            "intake_id": "session_lightweight",
            "chain_run_id": "run_l1",
            "updated_at": (now - timedelta(minutes=1)).isoformat(),
        },
        [
            {"event": "INTAKE_CHAIN_RUN", "run_id": "run_l1", "ts": (now - timedelta(minutes=2)).isoformat()},
        ],
    )

    def _unexpected_run_level_read(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("list endpoint should not read run-level events/contracts in lightweight mode")

    monkeypatch.setattr(pm_session_aggregation, "_read_events_fn", _unexpected_run_level_read)
    monkeypatch.setattr(pm_session_aggregation, "_load_contract_fn", _unexpected_run_level_read)

    client = TestClient(api_main.app)
    response = client.get("/api/pm/sessions")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["pm_session_id"] == "session_lightweight"
    assert payload[0]["status"] == "active"
    assert payload[0]["blocked_runs"] == 0
    assert payload[0]["potential_blocked_runs"] == 1
