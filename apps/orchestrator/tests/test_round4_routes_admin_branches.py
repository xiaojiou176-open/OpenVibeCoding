from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException
from starlette.requests import Request as StarletteRequest

from openvibecoding_orch.api import deps as api_deps
from openvibecoding_orch.api import routes_admin


def _make_request(headers: dict[str, str] | None = None, *, verified: bool = False) -> StarletteRequest:
    raw_headers = []
    for key, value in (headers or {}).items():
        raw_headers.append((key.lower().encode("utf-8"), value.encode("utf-8")))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": raw_headers,
        "state": {},
    }
    request = StarletteRequest(scope)
    if verified:
        request.state.openvibecoding_api_auth_verified = True
    return request


def test_round4_routes_admin_role_helpers_and_rbac(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_APPROVAL_ALLOWED_ROLES", "ops,tech_lead")
    assert routes_admin._approval_roles() == {"OPS", "TECH_LEAD"}

    monkeypatch.setenv("OPENVIBECODING_APPROVAL_ALLOWED_ROLES", " , ")
    assert routes_admin._approval_roles() == routes_admin._DEFAULT_APPROVAL_ROLES

    assert routes_admin._request_role(None) == ""

    assert routes_admin._request_role(_make_request({"x-openvibecoding-role": "OPS"})) == "OPS"

    monkeypatch.setattr(routes_admin, "load_config", lambda: SimpleNamespace(api_auth_required=False))
    assert routes_admin._role_header_is_trusted(None) is True
    assert routes_admin._role_header_is_trusted(_make_request({"x-openvibecoding-role": "OPS"})) is True

    monkeypatch.setattr(routes_admin, "load_config", lambda: SimpleNamespace(api_auth_required=True))
    assert routes_admin._role_header_is_trusted(_make_request({"x-openvibecoding-role": "OPS"}, verified=False)) is False
    assert routes_admin._role_header_is_trusted(_make_request({"x-openvibecoding-role": "OPS"}, verified=True)) is True

    with pytest.raises(HTTPException) as exc_none:
        routes_admin._enforce_approval_rbac(None)
    assert exc_none.value.status_code == 403
    assert exc_none.value.detail["code"] == "ROLE_REQUIRED"

    with pytest.raises(HTTPException) as exc_missing:
        routes_admin._enforce_approval_rbac(_make_request())
    assert exc_missing.value.status_code == 403
    assert exc_missing.value.detail["code"] == "ROLE_REQUIRED"

    with pytest.raises(HTTPException) as exc_untrusted:
        routes_admin._enforce_approval_rbac(_make_request({"x-openvibecoding-role": "TECH_LEAD"}, verified=False))
    assert exc_untrusted.value.status_code == 403
    assert exc_untrusted.value.detail["code"] == "ROLE_HEADER_UNTRUSTED"

    with pytest.raises(HTTPException) as exc_forbidden:
        routes_admin._enforce_approval_rbac(_make_request({"x-openvibecoding-role": "WORKER"}, verified=True))
    assert exc_forbidden.value.status_code == 403
    assert exc_forbidden.value.detail["code"] == "ROLE_FORBIDDEN"

    routes_admin._enforce_approval_rbac(_make_request({"x-openvibecoding-role": "TECH_LEAD"}, verified=True))


def test_round4_routes_admin_pending_collection_and_route_deps(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    run_id = "run-1"
    events_path = runs_root / run_id / "events.jsonl"
    events_path.parent.mkdir(parents=True, exist_ok=True)
    events_path.write_text(
        "\n".join(
            [
                "",
                "{",
                json.dumps(["not-dict"], ensure_ascii=False),
                json.dumps({"event": "HUMAN_APPROVAL_REQUIRED", "context": {"reason": ["x"]}}, ensure_ascii=False),
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(routes_admin, "load_config", lambda: SimpleNamespace(api_auth_required=False, runs_root=runs_root))
    monkeypatch.setattr(routes_admin.api_deps, "resolve_admin_route_deps", lambda _request=None: None)

    parsed_events = routes_admin._read_events_from_store(run_id)
    assert len(parsed_events) == 1
    assert parsed_events[0]["event"] == "HUMAN_APPROVAL_REQUIRED"

    assert routes_admin._has_pending_approval(run_id) is True
    assert routes_admin._has_pending_approval("run-missing") is False

    assert routes_admin._is_pending_after_latest_required([]) is False
    assert (
        routes_admin._is_pending_after_latest_required(
            [
                {"event": "HUMAN_APPROVAL_REQUIRED"},
                {"event": "HUMAN_APPROVAL_COMPLETED"},
            ]
        )
        is False
    )

    pending = routes_admin.collect_pending_approvals(
        runs_root=runs_root,
        read_events_fn=lambda rid: [
            {
                "event": "HUMAN_APPROVAL_REQUIRED",
                "context": {
                    "reason": [f"reason-{rid}"],
                    "actions": ["approve"],
                    "verify_steps": ["check"],
                    "resume_step": "resume",
                },
            }
        ],
    )
    assert len(pending) == 1
    assert pending[0]["run_id"] == run_id
    assert pending[0]["reason"] == [f"reason-{run_id}"]

    deps_error = SimpleNamespace(
        list_pending_approvals=lambda: (_ for _ in ()).throw(api_deps.RouteDepsNotConfiguredError("admin")),
    )
    with pytest.raises(HTTPException) as exc_503:
        routes_admin.list_pending_approvals(admin_deps=deps_error)
    assert exc_503.value.status_code == 503
    assert exc_503.value.detail["code"] == "ROUTE_DEPS_NOT_CONFIGURED"
    assert exc_503.value.detail["operation"] == "list_pending_approvals"

    assert routes_admin.list_pending_approvals(request=None, admin_deps=None) == []

    route_result = routes_admin.list_pending_approvals_route(
        _make_request({"x-openvibecoding-role": "TECH_LEAD"}),
        admin_deps=SimpleNamespace(list_pending_approvals=lambda: [{"run_id": "ok"}]),
    )
    assert route_result == [{"run_id": "ok"}]


def test_round4_routes_admin_approve_and_rum_branches(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    rum_path = tmp_path / "runtime" / "rum.jsonl"
    monkeypatch.setattr(routes_admin, "_RUM_JSONL_PATH", rum_path)
    monkeypatch.setattr(routes_admin, "_RUM_MAX_PAYLOAD_BYTES", 1024)

    assert routes_admin.god_mode_ping() == {"ok": True, "mode": "god"}

    payload_size = routes_admin._json_payload_size_bytes({"x": object()})
    assert payload_size > 0

    ok, reason = routes_admin._append_rum_record(["raw-payload"])
    assert ok is True
    assert reason == ""
    written = json.loads(rum_path.read_text(encoding="utf-8").splitlines()[0])
    assert written["meta"]["payload"]["raw_payload"] == ["raw-payload"]

    with pytest.raises(HTTPException) as exc_payload:
        routes_admin.approve_god_mode(payload=["bad"])  # type: ignore[arg-type]
    assert exc_payload.value.status_code == 400
    assert exc_payload.value.detail["code"] == "PAYLOAD_INVALID"

    monkeypatch.setattr(
        routes_admin,
        "_has_pending_approval",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(api_deps.RouteDepsNotConfiguredError("admin")),
    )
    with pytest.raises(HTTPException) as exc_pending:
        routes_admin.approve_god_mode({"run_id": "run-503"})
    assert exc_pending.value.status_code == 503
    assert exc_pending.value.detail["code"] == "ROUTE_DEPS_NOT_CONFIGURED"
    assert exc_pending.value.detail["operation"] == "approve_god_mode:pending_check"

    monkeypatch.setattr(
        routes_admin,
        "_has_pending_approval",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            HTTPException(
                status_code=503,
                detail={
                    "code": "ROUTE_DEPS_NOT_CONFIGURED",
                    "group": "admin-special",
                    "operation": "legacy-op",
                },
            )
        ),
    )
    with pytest.raises(HTTPException) as exc_pending_http:
        routes_admin.approve_god_mode({"run_id": "run-503-http"})
    assert exc_pending_http.value.status_code == 503
    assert exc_pending_http.value.detail == {
        "code": "ROUTE_DEPS_NOT_CONFIGURED",
        "error": "route dependencies not configured",
        "group": "admin-special",
        "operation": "approve_god_mode:pending_check",
    }

    monkeypatch.setattr(routes_admin, "_has_pending_approval", lambda *_args, **_kwargs: True)
    deps_mutation_error = SimpleNamespace(
        approve_god_mode_mutation=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            api_deps.RouteDepsNotConfiguredError("admin")
        )
    )
    with pytest.raises(HTTPException) as exc_mutation:
        routes_admin.approve_god_mode({"run_id": "run-mutation"}, admin_deps=deps_mutation_error)
    assert exc_mutation.value.status_code == 503
    assert exc_mutation.value.detail["code"] == "ROUTE_DEPS_NOT_CONFIGURED"
    assert exc_mutation.value.detail["operation"] == "approve_god_mode:mutation"

    service_result = routes_admin.approve_god_mode_mutation(
        "run-service",
        {"run_id": "run-service", "api_key": "secret"},
        orchestration_service=SimpleNamespace(
            approve_god_mode=lambda run_id, payload: {"run_id": run_id, "payload": payload}
        ),
    )
    assert service_result["run_id"] == "run-service"
    assert service_result["payload"]["api_key"] == "[REDACTED]"

    appended: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(routes_admin.run_store, "append_event", lambda rid, event: appended.append((rid, event)))
    fallback_result = routes_admin.approve_god_mode_mutation(
        "run-fallback",
        {"run_id": "run-fallback", "token": "sensitive"},
        orchestration_service=SimpleNamespace(),
    )
    assert fallback_result == {"ok": True, "run_id": "run-fallback"}
    assert appended[0][1]["event"] == "HUMAN_APPROVAL_COMPLETED"
    assert appended[0][1]["context"]["payload"]["token"] == "[REDACTED]"
