from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from cortexpilot_orch.api import pm_session_aggregation


_BASE_OVERVIEW_PAYLOAD = {
    "generated_at": "2026-01-01T00:00:00+00:00",
    "total_sessions": 2,
    "active_sessions": 1,
    "failed_sessions": 1,
    "blocked_sessions": 1,
    "failed_ratio": 0.5,
    "blocked_ratio": 0.5,
    "failure_trend_30m": 1,
    "slo_targets": {
        "sessions_api_p95_ms": 450,
        "sessions_api_p99_ms": 900,
        "overview_api_p95_ms": 350,
        "event_ingest_lag_ms": 5000,
    },
    "top_blockers": [],
}


def test_command_tower_overview_uses_ttl_cache(monkeypatch, tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_COMMAND_TOWER_OVERVIEW_TTL_SEC", "0.05")

    call_count = 0

    def _fake_build_overview_snapshot() -> dict[str, object]:
        nonlocal call_count
        call_count += 1
        payload = dict(_BASE_OVERVIEW_PAYLOAD)
        payload["generated_at"] = f"call-{call_count}"
        return payload

    monkeypatch.setattr(pm_session_aggregation, "_overview_cache_entry", None)
    monkeypatch.setattr(pm_session_aggregation, "_runtime_root_fn", lambda: runtime_root)
    monkeypatch.setattr(pm_session_aggregation, "_build_overview_snapshot", _fake_build_overview_snapshot)

    first = pm_session_aggregation.get_command_tower_overview()
    second = pm_session_aggregation.get_command_tower_overview()

    assert call_count == 1
    assert first["meta"]["cache_hit"] is False
    assert first["meta"]["generated_from"] == "recomputed"
    assert second["meta"]["cache_hit"] is True
    assert second["meta"]["generated_from"] == "cache_snapshot"

    pm_session_aggregation._overview_cache_entry["expires_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    third = pm_session_aggregation.get_command_tower_overview()
    assert call_count == 2
    assert third["meta"]["cache_hit"] is False
    assert third["meta"]["generated_from"] == "recomputed"


def test_command_tower_alerts_reuses_overview_snapshot(monkeypatch, tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_COMMAND_TOWER_OVERVIEW_TTL_SEC", "2")

    call_count = 0

    def _fake_build_overview_snapshot() -> dict[str, object]:
        nonlocal call_count
        call_count += 1
        payload = dict(_BASE_OVERVIEW_PAYLOAD)
        payload["generated_at"] = f"call-{call_count}"
        return payload

    monkeypatch.setattr(pm_session_aggregation, "_overview_cache_entry", None)
    monkeypatch.setattr(pm_session_aggregation, "_runtime_root_fn", lambda: runtime_root)
    monkeypatch.setattr(pm_session_aggregation, "_build_overview_snapshot", _fake_build_overview_snapshot)

    first_alerts = pm_session_aggregation.get_command_tower_alerts()
    second_alerts = pm_session_aggregation.get_command_tower_alerts()

    assert call_count == 1
    assert first_alerts["meta"]["overview_cache_hit"] is False
    assert second_alerts["meta"]["overview_cache_hit"] is True
    assert first_alerts["status"] in {"healthy", "degraded", "critical"}
    assert isinstance(first_alerts["alerts"], list)
    assert "slo_targets" in first_alerts


def test_pm_sessions_summary_snapshot_uses_ttl_cache(monkeypatch, tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_COMMAND_TOWER_OVERVIEW_TTL_SEC", "0.05")

    call_count = 0

    def _fake_build_pm_sessions_summary_snapshot() -> list[dict[str, object]]:
        nonlocal call_count
        call_count += 1
        return [
            {
                "pm_session_id": f"session-{call_count}",
                "_sort_updated_ts": float(call_count),
                "_sort_created_ts": float(call_count),
            }
        ]

    monkeypatch.setattr(pm_session_aggregation, "_session_summaries_cache_entry", None)
    monkeypatch.setattr(pm_session_aggregation, "_runtime_root_fn", lambda: runtime_root)
    monkeypatch.setattr(
        pm_session_aggregation,
        "_build_pm_session_summaries_snapshot",
        _fake_build_pm_sessions_summary_snapshot,
    )

    first, first_hit = pm_session_aggregation._get_pm_session_summaries_snapshot()
    second, second_hit = pm_session_aggregation._get_pm_session_summaries_snapshot()

    assert call_count == 1
    assert first_hit is False
    assert second_hit is True
    assert first[0]["pm_session_id"] == "session-1"
    assert second[0]["pm_session_id"] == "session-1"

    first.append({"pm_session_id": "tamper"})
    third, third_hit = pm_session_aggregation._get_pm_session_summaries_snapshot()
    assert third_hit is True
    assert [item["pm_session_id"] for item in third] == ["session-1"]

    pm_session_aggregation._session_summaries_cache_entry["expires_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    fourth, fourth_hit = pm_session_aggregation._get_pm_session_summaries_snapshot()
    assert call_count == 2
    assert fourth_hit is False
    assert fourth[0]["pm_session_id"] == "session-2"
