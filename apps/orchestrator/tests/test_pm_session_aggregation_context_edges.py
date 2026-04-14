from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import openvibecoding_orch.api.pm_session_aggregation_context as context_mod


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _event_cursor(event: dict[str, object]) -> str:
    raw = event.get("ts")
    return str(raw) if raw is not None else ""


def test_helper_branches_for_run_id_status_and_blocked() -> None:
    intake_events = [
        "invalid-event",
        {"event": "NOOP", "run_id": "ignored"},
        {"event": "INTAKE_RUN", "run_id": " run-1 ", "context": {"run_id": "run-ctx"}},
        {"event": "INTAKE_CHAIN_RUN", "context": {"run_id": "run-2"}},
    ]
    run_ids = context_mod._extract_pm_session_run_ids(
        {"chain_run_id": "run-1", "chain_run_ids": ["run-3", " run-2 ", 100]},
        intake_events,
    )
    assert run_ids == ["run-1", "run-ctx", "run-2", "run-3"]

    assert (
        context_mod._run_status_bucket(
            "failure",
            running_statuses={"RUNNING"},
            success_statuses={"SUCCESS"},
            failed_statuses={"FAILURE"},
        )
        == "failed"
    )
    assert (
        context_mod._run_status_bucket(
            "success",
            running_statuses={"RUNNING"},
            success_statuses={"SUCCESS"},
            failed_statuses={"FAILURE"},
        )
        == "success"
    )
    assert (
        context_mod._run_status_bucket(
            "running",
            running_statuses={"RUNNING"},
            success_statuses={"SUCCESS"},
            failed_statuses={"FAILURE"},
        )
        == "running"
    )
    assert (
        context_mod._run_status_bucket(
            "unknown",
            running_statuses={"RUNNING"},
            success_statuses={"SUCCESS"},
            failed_statuses={"FAILURE"},
        )
        == "paused"
    )

    assert context_mod._run_is_blocked(["bad", {"event": "HUMAN_APPROVAL_REQUIRED"}]) is True
    assert context_mod._run_is_blocked(
        [{"event": "HUMAN_APPROVAL_REQUIRED"}, {"event": "HUMAN_APPROVAL_COMPLETED"}]
    ) is False
    assert context_mod._run_is_blocked_lightweight({"blocked": True}) is True
    assert context_mod._run_is_blocked_lightweight({"blocked": "yes"}) is True
    assert context_mod._run_is_blocked_lightweight({"current_step": "BLOCKED"}) is True
    assert context_mod._run_is_blocked_lightweight({"failure_reason": "HUMAN_APPROVAL_REQUIRED"}) is True
    assert context_mod._run_is_blocked_lightweight({"blocked": "no"}) is False
    assert context_mod._run_is_potentially_blocked_lightweight(bucket="running", blocked=False) is True
    assert context_mod._run_is_potentially_blocked_lightweight(bucket="running", blocked=True) is False


def test_time_role_and_recovery_helpers_cover_exception_and_empty_paths() -> None:
    role, step, ts = context_mod._extract_role_step_from_events(
        [{"context": {"from": "TL"}, "event": "STEP_A", "ts": "2026-01-01T00:00:00+00:00"}],
        "PM",
        event_cursor_fn=_event_cursor,
    )
    assert (role, step, ts) == ("TL", "STEP_A", "2026-01-01T00:00:00+00:00")

    role, step, ts = context_mod._extract_role_step_from_events(
        [{"context": {"noop": "x"}, "event": " ", "ts": ""}],
        "PM",
        event_cursor_fn=_event_cursor,
    )
    assert (role, step, ts) == ("PM", "PENDING", "")

    assert context_mod._parse_ts_or_none("", parse_iso_ts_fn=_parse_iso) is None
    assert (
        context_mod._parse_ts_or_none(
            "bad-ts",
            parse_iso_ts_fn=lambda _value: (_ for _ in ()).throw(ValueError("bad")),
        )
        is None
    )
    assert context_mod._max_ts(["bad", "", None], parse_iso_ts_fn=_parse_iso) == ""

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    future = now + timedelta(seconds=1)
    assert context_mod._max_ts([now.isoformat(), future.isoformat()], parse_iso_ts_fn=_parse_iso) == future.isoformat()
    assert context_mod._avg_seconds([]) == 0.0
    assert context_mod._avg_seconds([1.0, 2.0, 2.0]) == 1.667

    recovery_events = [
        {"event": "HUMAN_APPROVAL_REQUIRED", "ts": now.isoformat()},
        {"event": "HUMAN_APPROVAL_COMPLETED", "ts": (now - timedelta(seconds=5)).isoformat()},
        {"event": "HUMAN_APPROVAL_REQUIRED", "ts": future.isoformat()},
        {"event": "HUMAN_APPROVAL_COMPLETED", "ts": (future + timedelta(seconds=8)).isoformat()},
        {"event": "OTHER", "ts": "invalid"},
    ]
    assert context_mod._compute_recovery_seconds(
        recovery_events,
        event_cursor_fn=_event_cursor,
        parse_iso_ts_fn=_parse_iso,
    ) == [0.0, 8.0]

    assert context_mod._run_sort_key({"run_id": "run-x", "last_event_ts": "bad"}, parse_iso_ts_fn=_parse_iso) == (0, "run-x")
    assert context_mod._run_sort_key(
        {"run_id": "run-y", "last_event_ts": future.isoformat()},
        parse_iso_ts_fn=_parse_iso,
    )[0] == int(future.timestamp())


def test_resolve_pm_session_context_strict_not_found_fail_closed() -> None:
    with pytest.raises(HTTPException) as excinfo:
        context_mod.resolve_pm_session_context(
            "missing-session",
            strict=True,
            read_pm_session_files_fn=lambda _sid: ({}, {}, []),
            session_index_service_fn=lambda: SimpleNamespace(
                derive_bindings=lambda *_args, **_kwargs: [],
                derive_session_source=lambda *_args, **_kwargs: "unknown",
            ),
            read_run_manifest_fn=lambda _run_id: {},
            load_contract_fn=lambda _run_id: {},
            read_events_fn=lambda _run_id: [],
            last_event_ts_fn=lambda _run_id: "",
            parse_iso_ts_fn=_parse_iso,
            event_cursor_fn=_event_cursor,
            error_detail_fn=lambda code: {"code": code},
            running_statuses={"RUNNING"},
            success_statuses={"SUCCESS"},
            failed_statuses={"FAILURE"},
        )
    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == {"code": "PM_SESSION_NOT_FOUND"}


def test_resolve_pm_session_context_include_run_events_and_summary_only_runs() -> None:
    base = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    t0 = base.isoformat()
    t1 = (base + timedelta(seconds=10)).isoformat()
    t2 = (base + timedelta(seconds=20)).isoformat()
    t3 = (base + timedelta(seconds=30)).isoformat()

    bindings = [
        SimpleNamespace(pm_session_id="pm-1", run_id="run-1", binding_type="primary", bound_at=t0),
        SimpleNamespace(pm_session_id="pm-1", run_id="run-2", binding_type="fallback", bound_at=t1),
        SimpleNamespace(pm_session_id="pm-1", run_id="run-3", binding_type="fallback", bound_at=t2),
    ]
    manifests = {
        "run-1": {"status": "SUCCESS", "created_at": t0, "finished_at": t1},
        "run-2": {"status": "FAILURE", "created_at": t1, "finished_at": t2},
        "run-3": {"status": "RUNNING", "created_at": t2},
    }
    events = {
        "run-1": [
            {"event": "HUMAN_APPROVAL_REQUIRED", "ts": t0, "context": {"to_role": "REVIEWER", "step": "REVIEW"}},
            {"event": "HUMAN_APPROVAL_COMPLETED", "ts": t1},
        ],
        "run-2": [
            {"event": "HUMAN_APPROVAL_REQUIRED", "ts": t0, "context": {"to_role": "WORKER", "step": "EXECUTE"}},
        ],
        "run-3": [],
    }
    contracts = {
        "run-1": {"assigned_agent": {"role": "PM"}},
        "run-2": {"assigned_agent": {"role": "TL"}},
        "run-3": {"assigned_agent": {"role": "WORKER"}},
    }
    last_ts_calls: list[str] = []

    context = context_mod.resolve_pm_session_context(
        "pm-1",
        strict=False,
        read_pm_session_files_fn=lambda _sid: (
            {"intake_id": "pm-1", "workspace": "demo-ws", "owner_pm": "owner-a", "created_at": t0},
            {"status": "archived", "plan": {"spec": "plan-objective"}, "updated_at": t3},
            [],
        ),
        session_index_service_fn=lambda: SimpleNamespace(
            derive_bindings=lambda *_args, **_kwargs: bindings,
            derive_session_source=lambda *_args, **_kwargs: "response",
        ),
        read_run_manifest_fn=lambda run_id: manifests[run_id],
        load_contract_fn=lambda run_id: contracts[run_id],
        read_events_fn=lambda run_id: events[run_id],
        last_event_ts_fn=lambda run_id: (last_ts_calls.append(run_id) or t3),
        parse_iso_ts_fn=_parse_iso,
        event_cursor_fn=_event_cursor,
        error_detail_fn=lambda code: {"code": code},
        running_statuses={"RUNNING"},
        success_statuses={"SUCCESS"},
        failed_statuses={"FAILURE"},
        include_run_events=True,
        include_runs=False,
    )

    assert context["summary"]["status"] == "archived"
    assert context["summary"]["project_key"] == "demo-ws"
    assert context["summary"]["objective"] == "plan-objective"
    assert context["summary"]["blocked_runs"] == 1
    assert context["summary"]["potential_blocked_runs"] == 0
    assert context["summary"]["owner_pm"] == "owner-a"
    assert context["metrics"]["failure_rate"] == round(1 / 3, 4)
    assert context["metrics"]["blocked_ratio"] == round(1 / 3, 4)
    assert context["summary"]["closed_at"] != ""
    assert context["summary"]["current_role"] == "PM"
    assert context["summary"]["current_step"] == "HUMAN_APPROVAL_COMPLETED"
    assert context["runs"][0]["run_id"] == "run-1"
    assert set(context["runs"][0].keys()) == {"run_id", "status", "created_at", "finished_at", "last_event_ts"}
    assert context["bindings"][0]["binding_type"] == "primary"
    assert "run-3" in last_ts_calls
