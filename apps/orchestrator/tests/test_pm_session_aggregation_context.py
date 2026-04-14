from __future__ import annotations

from datetime import datetime, timezone

from openvibecoding_orch.api.pm_session_aggregation_context import resolve_pm_session_context


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_pm_session_context_owner_missing_defaults_to_unknown_and_counts() -> None:
    created_at = datetime.now(timezone.utc).isoformat()

    context = resolve_pm_session_context(
        "session-missing-owner",
        strict=False,
        read_pm_session_files_fn=lambda _pm_session_id: (
            {"intake_id": "session-missing-owner", "created_at": created_at},
            {"chain_run_id": "run-1", "updated_at": created_at},
            [],
        ),
        session_index_service_fn=lambda: type(
            "IndexServiceStub",
            (),
            {
                "derive_bindings": staticmethod(lambda *_args, **_kwargs: []),
                "derive_session_source": staticmethod(lambda *_args, **_kwargs: "intake"),
            },
        )(),
        read_run_manifest_fn=lambda _run_id: {"status": "RUNNING", "created_at": created_at},
        load_contract_fn=lambda _run_id: {},
        read_events_fn=lambda _run_id: [],
        last_event_ts_fn=lambda _run_id: created_at,
        parse_iso_ts_fn=_parse_iso,
        event_cursor_fn=lambda event: str(event.get("ts") or ""),
        error_detail_fn=lambda code: {"code": code},
        running_statuses={"RUNNING"},
        success_statuses={"SUCCESS"},
        failed_statuses={"FAILURE"},
        include_run_events=False,
    )

    assert context["summary"]["owner_pm"] == "unknown"
    assert context["summary"]["owner_missing_count"] == 1
    assert context["summary"]["blocked_runs"] == 0
    assert context["summary"]["potential_blocked_runs"] == 1
    assert context["metrics"]["owner_missing_count"] == 1
    assert context["metrics"]["blocked_runs"] == 0
    assert context["metrics"]["potential_blocked_runs"] == 1
    assert context["metrics"]["potential_blocked_ratio"] == 1.0


def test_pm_session_context_owner_agent_without_id_defaults_to_unassigned() -> None:
    created_at = datetime.now(timezone.utc).isoformat()

    context = resolve_pm_session_context(
        "session-unassigned-owner",
        strict=False,
        read_pm_session_files_fn=lambda _pm_session_id: (
            {"intake_id": "session-unassigned-owner", "owner_agent": {"role": "PM"}, "created_at": created_at},
            {"chain_run_id": "run-2", "updated_at": created_at},
            [],
        ),
        session_index_service_fn=lambda: type(
            "IndexServiceStub",
            (),
            {
                "derive_bindings": staticmethod(lambda *_args, **_kwargs: []),
                "derive_session_source": staticmethod(lambda *_args, **_kwargs: "intake"),
            },
        )(),
        read_run_manifest_fn=lambda _run_id: {"status": "RUNNING", "created_at": created_at},
        load_contract_fn=lambda _run_id: {},
        read_events_fn=lambda _run_id: [],
        last_event_ts_fn=lambda _run_id: created_at,
        parse_iso_ts_fn=_parse_iso,
        event_cursor_fn=lambda event: str(event.get("ts") or ""),
        error_detail_fn=lambda code: {"code": code},
        running_statuses={"RUNNING"},
        success_statuses={"SUCCESS"},
        failed_statuses={"FAILURE"},
        include_run_events=False,
    )

    assert context["summary"]["owner_pm"] == "unassigned"
    assert context["summary"]["owner_missing_count"] == 1


def test_pm_session_context_lightweight_blocked_requires_explicit_manifest_signal() -> None:
    created_at = datetime.now(timezone.utc).isoformat()

    context = resolve_pm_session_context(
        "session-lightweight-blocked",
        strict=False,
        read_pm_session_files_fn=lambda _pm_session_id: (
            {"intake_id": "session-lightweight-blocked", "created_at": created_at},
            {"chain_run_id": "run-3", "updated_at": created_at},
            [],
        ),
        session_index_service_fn=lambda: type(
            "IndexServiceStub",
            (),
            {
                "derive_bindings": staticmethod(lambda *_args, **_kwargs: []),
                "derive_session_source": staticmethod(lambda *_args, **_kwargs: "intake"),
            },
        )(),
        read_run_manifest_fn=lambda _run_id: {
            "status": "RUNNING",
            "created_at": created_at,
            "status_reason": "WAITING_APPROVAL",
        },
        load_contract_fn=lambda _run_id: {},
        read_events_fn=lambda _run_id: [],
        last_event_ts_fn=lambda _run_id: created_at,
        parse_iso_ts_fn=_parse_iso,
        event_cursor_fn=lambda event: str(event.get("ts") or ""),
        error_detail_fn=lambda code: {"code": code},
        running_statuses={"RUNNING"},
        success_statuses={"SUCCESS"},
        failed_statuses={"FAILURE"},
        include_run_events=False,
    )

    assert context["summary"]["blocked_runs"] == 1
    assert context["summary"]["potential_blocked_runs"] == 0
    assert context["metrics"]["blocked_ratio"] == 1.0
    assert context["metrics"]["potential_blocked_ratio"] == 0.0


def test_pm_session_context_summary_only_skips_run_detail_callbacks() -> None:
    created_at = datetime.now(timezone.utc).isoformat()
    load_contract_calls = 0
    read_events_calls = 0
    last_event_ts_calls = 0

    def _load_contract(_run_id: str) -> dict[str, object]:
        nonlocal load_contract_calls
        load_contract_calls += 1
        return {}

    def _read_events(_run_id: str) -> list[dict[str, object]]:
        nonlocal read_events_calls
        read_events_calls += 1
        return []

    def _last_event_ts(_run_id: str) -> str:
        nonlocal last_event_ts_calls
        last_event_ts_calls += 1
        return created_at

    context = resolve_pm_session_context(
        "session-summary-only",
        strict=False,
        read_pm_session_files_fn=lambda _pm_session_id: (
            {"intake_id": "session-summary-only", "created_at": created_at},
            {
                "chain_run_ids": ["run-1", "run-2", "run-3"],
                "updated_at": created_at,
            },
            [],
        ),
        session_index_service_fn=lambda: type(
            "IndexServiceStub",
            (),
            {
                "derive_bindings": staticmethod(lambda *_args, **_kwargs: []),
                "derive_session_source": staticmethod(lambda *_args, **_kwargs: "intake"),
            },
        )(),
        read_run_manifest_fn=lambda _run_id: {"status": "RUNNING", "created_at": created_at},
        load_contract_fn=_load_contract,
        read_events_fn=_read_events,
        last_event_ts_fn=_last_event_ts,
        parse_iso_ts_fn=_parse_iso,
        event_cursor_fn=lambda event: str(event.get("ts") or ""),
        error_detail_fn=lambda code: {"code": code},
        running_statuses={"RUNNING"},
        success_statuses={"SUCCESS"},
        failed_statuses={"FAILURE"},
        include_run_events=False,
        include_runs=False,
    )

    assert context["summary"]["run_count"] == 3
    assert context["summary"]["latest_run_id"] == "run-3"
    assert context["runs"] == []
    assert load_contract_calls == 0
    assert read_events_calls == 0
    assert last_event_ts_calls == 0
