from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import parse_qs

from starlette.requests import Request

from openvibecoding_orch.api.pm_session_aggregation_views import list_pm_sessions_view


def _request(query: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/pm/sessions",
            "query_string": query.encode("utf-8"),
            "headers": [],
        }
    )


def _normalize_status_filters(
    request: Request,
    status: str | None,
    status_filters: list[str] | None = None,
) -> set[str]:
    values: list[str] = []
    if status:
        values.append(status)
    if isinstance(status_filters, list):
        values.extend(status_filters)
    values.extend(parse_qs(request.scope.get("query_string", b"").decode("utf-8")).get("status", []))
    return {item.strip().lower() for item in values if item.strip()}


def test_list_pm_sessions_view_filters_before_sorting_work() -> None:
    total_sessions = 200
    parse_calls = 0

    def _list_ids() -> list[str]:
        return [f"session-{idx}" for idx in range(total_sessions)]

    def _resolve_context(session_id: str) -> dict[str, object]:
        idx = int(session_id.rsplit("-", 1)[1])
        return {
            "summary": {
                "pm_session_id": session_id,
                "status": "active",
                "owner_pm": "target-owner" if idx == total_sessions - 1 else "other-owner",
                "project_key": "openvibecoding",
                "updated_at": f"2026-02-25T00:{idx % 60:02d}:00+00:00",
                "created_at": "2026-02-25T00:00:00+00:00",
                "blocked_runs": idx % 3,
                "failed_runs": 0,
                "running_runs": 1,
            }
        }

    def _parse_ts(value: object) -> datetime | None:
        nonlocal parse_calls
        parse_calls += 1
        if not isinstance(value, str) or not value:
            return None
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    payload = list_pm_sessions_view(
        _request("owner_pm=target-owner"),
        status=None,
        status_filters=None,
        owner_pm="target-owner",
        project_key=None,
        sort="updated_desc",
        limit=10,
        offset=0,
        status_values={"active", "paused", "done", "failed", "archived"},
        sort_values={"updated_desc", "created_desc", "failed_desc", "blocked_desc"},
        normalize_status_filters_fn=_normalize_status_filters,
        error_detail_fn=lambda code: {"code": code},
        list_pm_session_ids_fn=_list_ids,
        resolve_pm_session_context_fn=_resolve_context,
        parse_ts_or_none_fn=_parse_ts,
    )

    assert len(payload) == 1
    assert payload[0]["owner_pm"] == "target-owner"
    assert payload[0]["pm_session_id"] == "session-199"
    # Regression guard: sort key parsing should scale with filtered page candidates, not all 200 sessions.
    assert parse_calls < 20


def test_list_pm_sessions_view_topk_pagination_matches_expected_order() -> None:
    def _list_ids() -> list[str]:
        return ["a", "b", "c", "d", "e"]

    scores = {
        "a": "2026-02-25T00:00:01+00:00",
        "b": "2026-02-25T00:00:05+00:00",
        "c": "2026-02-25T00:00:03+00:00",
        "d": "2026-02-25T00:00:04+00:00",
        "e": "2026-02-25T00:00:02+00:00",
    }

    def _resolve_context(session_id: str) -> dict[str, object]:
        return {
            "summary": {
                "pm_session_id": session_id,
                "status": "active",
                "owner_pm": "pm",
                "project_key": "openvibecoding",
                "updated_at": scores[session_id],
                "created_at": "2026-02-25T00:00:00+00:00",
                "blocked_runs": 0,
                "failed_runs": 0,
                "running_runs": 1,
            }
        }

    payload = list_pm_sessions_view(
        _request(""),
        status=None,
        status_filters=None,
        owner_pm=None,
        project_key=None,
        sort="updated_desc",
        limit=2,
        offset=1,
        status_values={"active", "paused", "done", "failed", "archived"},
        sort_values={"updated_desc", "created_desc", "failed_desc", "blocked_desc"},
        normalize_status_filters_fn=_normalize_status_filters,
        error_detail_fn=lambda code: {"code": code},
        list_pm_session_ids_fn=_list_ids,
        resolve_pm_session_context_fn=_resolve_context,
        parse_ts_or_none_fn=lambda value: datetime.fromisoformat(str(value)).astimezone(timezone.utc),
    )

    assert [item["pm_session_id"] for item in payload] == ["d", "c"]


def test_list_pm_sessions_view_uses_precomputed_sort_keys_and_hides_internal_fields() -> None:
    parse_calls = 0

    def _parse_ts(value: object) -> datetime | None:
        nonlocal parse_calls
        parse_calls += 1
        if not isinstance(value, str):
            return None
        return datetime.fromisoformat(value).astimezone(timezone.utc)

    payload = list_pm_sessions_view(
        _request(""),
        status=None,
        status_filters=None,
        owner_pm=None,
        project_key=None,
        sort="updated_desc",
        limit=1,
        offset=0,
        status_values={"active", "paused", "done", "failed", "archived"},
        sort_values={"updated_desc", "created_desc", "failed_desc", "blocked_desc"},
        normalize_status_filters_fn=_normalize_status_filters,
        error_detail_fn=lambda code: {"code": code},
        list_pm_session_ids_fn=lambda: [],
        resolve_pm_session_context_fn=lambda _session_id: {},
        parse_ts_or_none_fn=_parse_ts,
        session_summaries=[
            {
                "pm_session_id": "session-new",
                "status": "active",
                "owner_pm": "pm",
                "project_key": "openvibecoding",
                "updated_at": "2026-02-25T00:00:10+00:00",
                "created_at": "2026-02-25T00:00:00+00:00",
                "_sort_updated_ts": 10.0,
                "_sort_created_ts": 0.0,
            },
            {
                "pm_session_id": "session-old",
                "status": "active",
                "owner_pm": "pm",
                "project_key": "openvibecoding",
                "updated_at": "2026-02-25T00:00:01+00:00",
                "created_at": "2026-02-25T00:00:00+00:00",
                "_sort_updated_ts": 1.0,
                "_sort_created_ts": 0.0,
            },
        ],
    )

    assert parse_calls == 0
    assert payload[0]["pm_session_id"] == "session-new"
    assert "_sort_updated_ts" not in payload[0]
    assert "_sort_created_ts" not in payload[0]
