from __future__ import annotations

import json
import threading
import time
import types
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException

from cortexpilot_orch.api import main_pm_intake_helpers as helpers
from cortexpilot_orch.contract.compiler import build_role_binding_summary
from cortexpilot_orch.store.run_store import RunStore


def test_configure_pm_session_aggregation_delegates(monkeypatch) -> None:
    seen: dict[str, object] = {}

    def _fake_configure(**kwargs):
        seen.update(kwargs)

    monkeypatch.setattr(helpers.pm_session_aggregation, "configure", _fake_configure)
    helpers.configure_pm_session_aggregation(
        runs_root_fn=lambda: Path("/tmp/runs"),
        runtime_root_fn=lambda: Path("/tmp/runtime"),
        read_json_fn=lambda _p, _d: {},
        load_contract_fn=lambda _rid: {},
        read_events_fn=lambda _rid: [],
        last_event_ts_fn=lambda _rid: "",
        filter_events_fn=lambda *_a, **_k: [],
        event_cursor_fn=lambda _evt: "",
        parse_iso_fn=lambda _ts: helpers.datetime.now(helpers.timezone.utc),
        error_detail_fn=lambda code: {"code": code},
    )
    assert seen["runs_root_fn"]() == Path("/tmp/runs")
    assert callable(seen["error_detail_fn"])


def test_configure_routes_registers_pm_and_intake_handlers() -> None:
    app = FastAPI()
    helpers.configure_routes(
        app=app,
        list_pm_sessions_accessor=lambda: (lambda *args: ["pm", list(args)]),
        get_pm_session_accessor=lambda: (lambda pm_session_id: {"pm_session_id": pm_session_id}),
        get_pm_session_events_accessor=lambda: (lambda *args: [{"args": list(args)}]),
        get_pm_session_graph_accessor=lambda: (lambda *args: {"graph": list(args)}),
        get_pm_session_metrics_accessor=lambda: (lambda pm_session_id: {"metrics": pm_session_id}),
        post_pm_session_message_accessor=lambda: (lambda pm_session_id, payload: {"pm_session_id": pm_session_id, "payload": payload}),
        get_command_tower_overview_accessor=lambda: (lambda: {"overview": True}),
        get_command_tower_alerts_accessor=lambda: (lambda: {"alerts": []}),
        list_intakes_accessor=lambda: (lambda: [{"id": "i1"}]),
        get_intake_accessor=lambda: (lambda intake_id: {"intake_id": intake_id}),
        create_intake_accessor=lambda: (lambda payload: {"payload": payload}),
        answer_intake_accessor=lambda: (lambda intake_id, payload: {"intake_id": intake_id, "payload": payload}),
        run_intake_accessor=lambda: (lambda intake_id, payload=None: {"intake_id": intake_id, "payload": payload}),
    )
    assert app.state.routes_pm_handlers["get_command_tower_overview"]() == {"overview": True}
    assert app.state.routes_intake_handlers["list_intakes"]() == [{"id": "i1"}]
    assert app.state.routes_intake_handlers["run_intake"]("i", {"x": 1})["payload"] == {"x": 1}


def test_list_pm_sessions_signature_aware_status_filters(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def _with_filters(
        request,
        status=None,
        status_filters=None,
        owner_pm=None,
        project_key=None,
        sort="updated_desc",
        limit=50,
        offset=0,
    ):
        del request, status, owner_pm, project_key, sort, limit, offset
        calls.append({"status_filters": status_filters})
        return [{"ok": True}]

    monkeypatch.setattr(helpers.pm_session_aggregation, "list_pm_sessions", _with_filters)
    result = helpers.list_pm_sessions(
        request=types.SimpleNamespace(),
        status="RUNNING",
        status_filters=["RUNNING", "FAILURE"],
        owner_pm="pm-1",
        project_key="proj",
        sort="updated_desc",
        limit=5,
        offset=1,
    )
    assert result == [{"ok": True}]
    assert calls[-1]["status_filters"] == ["RUNNING", "FAILURE"]

    def _without_filters(request, status=None, owner_pm=None, project_key=None, sort="updated_desc", limit=50, offset=0):
        del request, status, owner_pm, project_key, sort, limit, offset
        return [{"ok": False}]

    monkeypatch.setattr(helpers.pm_session_aggregation, "list_pm_sessions", _without_filters)
    assert helpers.list_pm_sessions(request=types.SimpleNamespace(), status_filters=["X"]) == [{"ok": False}]


def test_pm_session_wrapper_functions(monkeypatch) -> None:
    monkeypatch.setattr(helpers.pm_session_aggregation, "get_pm_session", lambda pm_session_id: {"id": pm_session_id})
    monkeypatch.setattr(helpers.pm_session_aggregation, "get_pm_session_events", lambda *args, **kwargs: [{"args": args, "kwargs": kwargs}])
    monkeypatch.setattr(helpers.pm_session_aggregation, "get_pm_session_conversation_graph", lambda *args, **kwargs: {"args": args, "kwargs": kwargs})
    monkeypatch.setattr(helpers.pm_session_aggregation, "get_pm_session_metrics", lambda pm_session_id: {"m": pm_session_id})
    monkeypatch.setattr(helpers.pm_session_aggregation, "get_command_tower_overview", lambda: {"ok": True})
    monkeypatch.setattr(helpers.pm_session_aggregation, "get_command_tower_alerts", lambda: {"alerts": 1})
    monkeypatch.setattr(helpers.IntakeStore, "list_intakes", lambda _self: [{"intake_id": "i"}])

    assert helpers.get_pm_session("pm-1") == {"id": "pm-1"}
    assert helpers.get_pm_session_events("pm-1", request=types.SimpleNamespace())[0]["kwargs"]["since"] is None
    assert helpers.get_pm_session_conversation_graph("pm-1", window="1h", group_by_role=True)["kwargs"]["group_by_role"] is True
    assert helpers.get_pm_session_metrics("pm-1") == {"m": "pm-1"}
    assert helpers.get_command_tower_overview() == {"ok": True}
    assert helpers.get_command_tower_alerts() == {"alerts": 1}
    assert helpers.list_intakes() == [{"intake_id": "i"}]


def test_post_pm_session_message_validation_and_event_append(monkeypatch) -> None:
    events: list[tuple[str, dict[str, object]]] = []

    class _Store:
        def append_event(self, intake_id: str, payload: dict[str, object]) -> None:
            events.append((intake_id, payload))

    monkeypatch.setattr(helpers, "IntakeStore", _Store)
    ensure_calls: list[str] = []

    with pytest.raises(HTTPException) as excinfo:
        helpers.post_pm_session_message(
            "pm-1",
            {"message": "   "},
            error_detail_fn=lambda code: {"code": code},
            ensure_pm_session_fn=lambda sid: ensure_calls.append(sid),
        )
    assert excinfo.value.status_code == 400
    assert ensure_calls == ["pm-1"]

    result = helpers.post_pm_session_message(
        "pm-2",
        {"message": "hello", "role": "pm", "metadata": "not-dict"},
        error_detail_fn=lambda code: {"code": code},
        ensure_pm_session_fn=lambda _sid: None,
    )
    assert result["ok"] is True
    assert events[-1][0] == "pm-2"
    assert events[-1][1]["context"]["metadata"] == {}


def test_get_intake_error_and_success_branches(monkeypatch) -> None:
    class _StoreMissing:
        def intake_exists(self, _intake_id: str) -> bool:
            return False

    monkeypatch.setattr(helpers, "IntakeStore", _StoreMissing)
    with pytest.raises(HTTPException) as excinfo:
        helpers.get_intake("missing", error_detail_fn=lambda code: {"code": code})
    assert excinfo.value.status_code == 404

    class _StoreEmpty:
        def intake_exists(self, _intake_id: str) -> bool:
            return True

        def read_intake(self, _intake_id: str) -> dict:
            return {}

        def read_response(self, _intake_id: str) -> dict:
            return {}

    monkeypatch.setattr(helpers, "IntakeStore", _StoreEmpty)
    with pytest.raises(HTTPException) as excinfo2:
        helpers.get_intake("empty", error_detail_fn=lambda code: {"code": code})
    assert excinfo2.value.status_code == 404

    class _StoreOk(_StoreEmpty):
        def read_intake(self, _intake_id: str) -> dict:
            return {"objective": "ok"}

    monkeypatch.setattr(helpers, "IntakeStore", _StoreOk)
    payload = helpers.get_intake("ok", error_detail_fn=lambda code: {"code": code})
    assert payload["intake"]["objective"] == "ok"


def test_create_and_answer_intake_error_branches(monkeypatch) -> None:
    class _RaiseHTTP:
        def create(self, payload: dict) -> dict:
            del payload
            raise HTTPException(status_code=409, detail={"code": "dup"})

        def answer(self, intake_id: str, payload: dict) -> dict:
            del intake_id, payload
            raise HTTPException(status_code=410, detail={"code": "gone"})

    with pytest.raises(HTTPException) as exc_http_create:
        helpers.create_intake(
            {"a": 1},
            intake_service_cls=_RaiseHTTP,
            error_detail_fn=lambda code: {"code": code},
            current_request_id_fn=lambda: "req-1",
        )
    assert exc_http_create.value.status_code == 409

    with pytest.raises(HTTPException) as exc_http_answer:
        helpers.answer_intake(
            "i1",
            {"a": 1},
            intake_service_cls=_RaiseHTTP,
            error_detail_fn=lambda code: {"code": code},
            current_request_id_fn=lambda: "req-2",
        )
    assert exc_http_answer.value.status_code == 410

    class _RaiseValue:
        def create(self, payload: dict) -> dict:
            del payload
            raise ValueError("invalid create")

        def answer(self, intake_id: str, payload: dict) -> dict:
            del intake_id, payload
            raise ValueError("invalid answer")

    with pytest.raises(HTTPException) as exc_val_create:
        helpers.create_intake(
            {"x": 1},
            intake_service_cls=_RaiseValue,
            error_detail_fn=lambda code: {"code": code},
            current_request_id_fn=lambda: "req-3",
        )
    assert exc_val_create.value.status_code == 400
    assert exc_val_create.value.detail["reason"] == "invalid create"

    with pytest.raises(HTTPException) as exc_val_answer:
        helpers.answer_intake(
            "i2",
            {"x": 1},
            intake_service_cls=_RaiseValue,
            error_detail_fn=lambda code: {"code": code},
            current_request_id_fn=lambda: "req-4",
        )
    assert exc_val_answer.value.status_code == 400
    assert exc_val_answer.value.detail["reason"] == "invalid answer"

    class _RaiseUnknown:
        def create(self, payload: dict) -> dict:
            del payload
            raise RuntimeError("boom create")

        def answer(self, intake_id: str, payload: dict) -> dict:
            del intake_id, payload
            raise RuntimeError("boom answer")

    with pytest.raises(HTTPException) as exc_unknown_create:
        helpers.create_intake(
            {"x": 1},
            intake_service_cls=_RaiseUnknown,
            error_detail_fn=lambda code: {"code": code},
            current_request_id_fn=lambda: "req-5",
        )
    assert exc_unknown_create.value.status_code == 500

    with pytest.raises(HTTPException) as exc_unknown_answer:
        helpers.answer_intake(
            "i3",
            {"x": 1},
            intake_service_cls=_RaiseUnknown,
            error_detail_fn=lambda code: {"code": code},
            current_request_id_fn=lambda: "req-6",
        )
    assert exc_unknown_answer.value.status_code == 500


def test_run_intake_error_branches_and_success(monkeypatch, tmp_path: Path) -> None:
    events: list[tuple[str, dict[str, object]]] = []

    class _Store:
        def append_event(self, intake_id: str, payload: dict[str, object]) -> None:
            events.append((intake_id, payload))

    monkeypatch.setattr(helpers, "IntakeStore", _Store)
    monkeypatch.setattr(
        helpers,
        "load_config",
        lambda: types.SimpleNamespace(
            repo_root=tmp_path,
            contract_root=tmp_path / "contracts",
            runtime_contract_root=tmp_path / ".runtime-cache" / "cortexpilot" / "contracts",
        ),
    )

    class _BuildValue:
        def build_contract(self, intake_id: str) -> dict[str, object]:
            del intake_id
            raise ValueError("invalid build")

    with pytest.raises(HTTPException) as exc_build_value:
        helpers.run_intake(
            "i1",
            intake_service_cls=_BuildValue,
            orchestration_service=types.SimpleNamespace(execute_task=lambda *_a, **_k: "run-1"),
            error_detail_fn=lambda code: {"code": code},
            current_request_id_fn=lambda: "req-1",
        )
    assert exc_build_value.value.status_code == 400

    class _BuildUnknown:
        def build_contract(self, intake_id: str) -> dict[str, object]:
            del intake_id
            raise RuntimeError("boom")

    with pytest.raises(HTTPException) as exc_build_unknown:
        helpers.run_intake(
            "i2",
            intake_service_cls=_BuildUnknown,
            orchestration_service=types.SimpleNamespace(execute_task=lambda *_a, **_k: "run-2"),
            error_detail_fn=lambda code: {"code": code},
            current_request_id_fn=lambda: "req-2",
        )
    assert exc_build_unknown.value.status_code == 500

    class _BuildEmpty:
        def build_contract(self, intake_id: str) -> dict[str, object] | None:
            del intake_id
            return {}

    with pytest.raises(HTTPException) as exc_empty:
        helpers.run_intake(
            "i3",
            intake_service_cls=_BuildEmpty,
            orchestration_service=types.SimpleNamespace(execute_task=lambda *_a, **_k: "run-3"),
            error_detail_fn=lambda code: {"code": code},
            current_request_id_fn=lambda: "req-3",
        )
    assert exc_empty.value.status_code == 400
    assert exc_empty.value.detail["code"] == "INTAKE_PLAN_MISSING"

    class _BuildOK:
        def build_contract(self, intake_id: str) -> dict[str, object]:
            return {"task_id": f"task-{intake_id}", "runtime_options": "bad-type", "audit_only": False}

    with pytest.raises(HTTPException) as exc_runner:
        helpers.run_intake(
            "i4",
            {"runner": "invalid-runner"},
            intake_service_cls=_BuildOK,
            orchestration_service=types.SimpleNamespace(execute_task=lambda *_a, **_k: "run-4"),
            error_detail_fn=lambda code: {"code": code},
            current_request_id_fn=lambda: "req-4",
        )
    assert exc_runner.value.status_code == 400
    assert exc_runner.value.detail["code"] == "RUNTIME_RUNNER_INVALID"

    observed_contract: dict[str, object] = {}

    class _Orchestrator:
        @staticmethod
        def execute_task(contract_path: Path, mock_mode: bool = False) -> str:
            observed_contract.update(json.loads(contract_path.read_text(encoding="utf-8")))
            observed_contract["mock_mode"] = mock_mode
            return "run-ok"

    result = helpers.run_intake(
        "i5",
        {
            "runner": "app_server",
            "mock": "true",
            "strict_acceptance": "off",
            "runtime_options": {"provider": "cliproxyapi"},
        },
        intake_service_cls=_BuildOK,
        orchestration_service=_Orchestrator(),
        error_detail_fn=lambda code: {"code": code},
        current_request_id_fn=lambda: "req-5",
    )
    assert result["ok"] is True
    assert result["run_id"] == "run-ok"
    assert result["strict_acceptance"] is False
    expected_role_contract = observed_contract["role_contract"]
    assert result["role_binding_summary"] == build_role_binding_summary(observed_contract)
    assert observed_contract["runtime_options"]["runner"] == "app_server"
    assert observed_contract["runtime_options"]["strict_acceptance"] is False
    assert observed_contract["runtime_options"]["provider"] == "cliproxyapi"
    assert observed_contract["audit_only"] is True
    assert observed_contract["mock_mode"] is True
    assert events[-1][1]["event"] == "INTAKE_RUN"


def test_run_intake_strips_intake_only_template_fields_before_execution(monkeypatch, tmp_path: Path) -> None:
    from cortexpilot_orch.contract.validator import ContractValidator

    monkeypatch.setattr(helpers, "IntakeStore", lambda: types.SimpleNamespace(append_event=lambda *_a, **_k: None))
    monkeypatch.setattr(
        helpers,
        "load_config",
        lambda: types.SimpleNamespace(
            repo_root=tmp_path,
            runs_root=tmp_path / "runs",
            contract_root=tmp_path / "contracts",
            runtime_contract_root=tmp_path / ".runtime-cache" / "cortexpilot" / "contracts",
        ),
    )

    class _BuildTemplateContract:
        def build_contract(self, intake_id: str) -> dict[str, object]:
            return {
                "task_id": f"task-{intake_id}",
                    "owner_agent": {"role": "PM", "agent_id": "agent-1"},
                    "assigned_agent": {"role": "TECH_LEAD", "agent_id": "agent-1"},
                "inputs": {"spec": "repro", "artifacts": []},
                "required_outputs": [{"name": "report.json", "type": "json", "acceptance": "ok"}],
                "allowed_paths": ["apps/dashboard"],
                "forbidden_actions": [],
                "acceptance_tests": [
                    {
                        "name": "pytest",
                        "cmd": "python3 -m pytest apps/orchestrator/tests/test_schema_validation.py -q",
                        "must_pass": True,
                    }
                ],
                "tool_permissions": {
                    "filesystem": "workspace-write",
                    "shell": "on-request",
                    "network": "deny",
                    "mcp_tools": ["01-filesystem"],
                },
                "mcp_tool_set": ["01-filesystem"],
                "timeout_retry": {"timeout_sec": 60, "max_retries": 0, "retry_backoff_sec": 0},
                "rollback": {"strategy": "git_reset_hard", "baseline_ref": "HEAD"},
                "evidence_links": [],
                "log_refs": {"run_id": "", "paths": {}},
                "browser_policy": {"profile_mode": "ephemeral"},
                "task_template": "news_digest",
                "template_payload": {"topic": "Seattle AI"},
            }

    observed_contract: dict[str, object] = {}

    class _SchemaValidatingOrchestrator:
        @staticmethod
        def execute_task(contract_path: Path, mock_mode: bool = False) -> str:
            del mock_mode
            payload = json.loads(contract_path.read_text(encoding="utf-8"))
            observed_contract.update(payload)
            ContractValidator().validate_contract(payload)
            return "run-template-ok"

    result = helpers.run_intake(
        "template",
        {"runner": "agents", "strict_acceptance": True},
        intake_service_cls=_BuildTemplateContract,
        orchestration_service=_SchemaValidatingOrchestrator(),
        error_detail_fn=lambda code: {"code": code},
        current_request_id_fn=lambda: "req-template",
    )

    assert result["ok"] is True
    assert result["run_id"] == "run-template-ok"
    expected_role_contract = observed_contract["role_contract"]
    assert result["role_binding_summary"] == build_role_binding_summary(observed_contract)
    assert "task_template" not in observed_contract
    assert "template_payload" not in observed_contract
    assert observed_contract["browser_policy"] == {"profile_mode": "ephemeral"}
    assert observed_contract["runtime_options"]["strict_acceptance"] is True


def test_run_intake_persists_planning_artifacts_into_run_bundle(monkeypatch, tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    runtime_contract_root = tmp_path / ".runtime-cache" / "cortexpilot" / "contracts"
    intake_payload = {
        "objective": "Ship one planning artifact bridge",
        "constraints": ["truthful-public-surface"],
        "search_queries": ["command tower planning artifact"],
    }
    response_payload = {
        "plan_bundle": {
            "bundle_id": "bundle-1",
            "objective": "Ship one planning artifact bridge",
            "owner_agent": {"role": "PM", "agent_id": "pm-1"},
            "plans": [
                {
                    "plan_id": "worker-1",
                    "assigned_agent": {"role": "WORKER", "agent_id": "worker-1"},
                    "spec": "Persist the planning artifact into the run bundle.",
                    "allowed_paths": ["apps/orchestrator"],
                    "acceptance_tests": [{"name": "pytest", "cmd": "python3 -m pytest -q", "must_pass": True}],
                    "mcp_tool_set": ["codex"],
                    "required_outputs": [{"name": "task_result.json", "type": "report"}],
                }
            ],
        }
    }
    intake_events: list[tuple[str, dict[str, object]]] = []

    class _Store:
        def append_event(self, intake_id: str, payload: dict[str, object]) -> None:
            intake_events.append((intake_id, payload))

        def read_intake(self, intake_id: str) -> dict[str, object]:
            assert intake_id == "persist"
            return intake_payload

        def read_response(self, intake_id: str) -> dict[str, object]:
            assert intake_id == "persist"
            return response_payload

    monkeypatch.setattr(helpers, "IntakeStore", lambda: _Store())
    monkeypatch.setattr(
        helpers,
        "load_config",
        lambda: types.SimpleNamespace(
            repo_root=tmp_path,
            runs_root=runs_root,
            contract_root=tmp_path / "contracts",
            runtime_contract_root=runtime_contract_root,
        ),
    )

    class _BuildOK:
        def build_contract(self, intake_id: str) -> dict[str, object]:
            assert intake_id == "persist"
            return {
                "task_id": "task-persist",
                "owner_agent": {"role": "PM", "agent_id": "pm-1"},
                "assigned_agent": {"role": "WORKER", "agent_id": "worker-1"},
                "inputs": {"spec": "repro", "artifacts": []},
                "required_outputs": [{"name": "task_result.json", "type": "json", "acceptance": "ok"}],
                "allowed_paths": ["apps/orchestrator"],
                "forbidden_actions": [],
                "acceptance_tests": [{"name": "pytest", "cmd": "python3 -m pytest -q", "must_pass": True}],
                "tool_permissions": {
                    "filesystem": "workspace-write",
                    "shell": "on-request",
                    "network": "deny",
                    "mcp_tools": ["codex"],
                },
                "mcp_tool_set": ["codex"],
                "timeout_retry": {"timeout_sec": 60, "max_retries": 0, "retry_backoff_sec": 0},
                "rollback": {"strategy": "git_reset_hard", "baseline_ref": "HEAD"},
                "evidence_links": [],
                "log_refs": {"run_id": "", "paths": {}},
            }

    class _Orchestrator:
        @staticmethod
        def execute_task(contract_path: Path, mock_mode: bool = False) -> str:
            del mock_mode
            payload = json.loads(contract_path.read_text(encoding="utf-8"))
            store = RunStore(runs_root=runs_root)
            run_id = store.create_run(str(payload.get("task_id") or "task"))
            store.write_manifest(run_id, {"run_id": run_id, "task_id": payload.get("task_id"), "status": "RUNNING", "repo": {}})
            return run_id

    result = helpers.run_intake(
        "persist",
        {"mock": True},
        intake_service_cls=_BuildOK,
        orchestration_service=_Orchestrator(),
        error_detail_fn=lambda code: {"code": code},
        current_request_id_fn=lambda: "req-persist",
    )

    run_id = result["run_id"]
    wave_plan = json.loads((runs_root / run_id / "artifacts" / "planning_wave_plan.json").read_text(encoding="utf-8"))
    worker_contracts = json.loads(
        (runs_root / run_id / "artifacts" / "planning_worker_prompt_contracts.json").read_text(encoding="utf-8")
    )

    assert result["planning_artifacts"] == ["planning_wave_plan.json", "planning_worker_prompt_contracts.json"]
    assert wave_plan["wave_id"] == "bundle-1"
    assert wave_plan["objective"] == "Ship one planning artifact bridge"
    assert worker_contracts[0]["prompt_contract_id"] == "worker-1"
    assert worker_contracts[0]["continuation_policy"]["on_blocked"] == "spawn_independent_temporary_unblock_task"
    assert intake_events[-1] == ("persist", {"event": "INTAKE_RUN", "run_id": run_id})


def test_build_role_binding_summary_marks_skills_and_mcp_registry_refs_as_registry_backed() -> None:
    summary = build_role_binding_summary(
        {
            "runtime_options": {"provider": "cliproxyapi"},
            "role_contract": {
                "skills_bundle_ref": "policies/skills_bundle_registry.json#bundles.worker_delivery_core_v1",
                "mcp_bundle_ref": "policies/agent_registry.json#agents(role=SEARCHER).capabilities.mcp_tools",
                "runtime_binding": {"runner": None, "provider": "cliproxyapi", "model": None},
            }
        }
    )

    assert summary["skills_bundle_ref"] == {
        "status": "registry-backed",
        "ref": "policies/skills_bundle_registry.json#bundles.worker_delivery_core_v1",
        "bundle_id": "worker_delivery_core_v1",
        "resolved_skill_set": [
            "contract_alignment",
            "bounded_change_execution",
            "artifact_hygiene",
            "verification_evidence",
        ],
        "validation": "fail-closed",
    }
    assert summary["mcp_bundle_ref"] == {
        "status": "registry-backed",
        "ref": "policies/agent_registry.json#agents(role=SEARCHER).capabilities.mcp_tools",
        "resolved_mcp_tool_set": ["codex", "search"],
        "validation": "fail-closed",
    }
    assert summary["execution_authority"] == "task_contract"
    assert summary["runtime_binding"] == {
        "status": "partially-resolved",
        "authority_scope": "contract-derived-read-model",
        "source": {
            "runner": "unresolved",
            "provider": "runtime_options.provider",
            "model": "unresolved",
        },
        "summary": {"runner": None, "provider": "cliproxyapi", "model": None},
        "capability": {
            "status": "previewable",
            "lane": "standard-provider-path",
            "compat_api_mode": "responses",
            "provider_status": "allowlisted",
            "provider_inventory_id": "cliproxyapi",
            "tool_execution": "provider-path-required",
            "notes": [
                "Chat-style compatibility may differ from tool-execution capability.",
                "Execution authority remains task_contract even when role defaults change.",
            ],
        },
    }


def test_run_intake_returns_run_id_before_background_execution_finishes(monkeypatch, tmp_path: Path) -> None:
    events: list[tuple[str, dict[str, object]]] = []

    class _Store:
        def append_event(self, intake_id: str, payload: dict[str, object]) -> None:
            events.append((intake_id, payload))

    monkeypatch.setattr(helpers, "IntakeStore", _Store)
    monkeypatch.setattr(
        helpers,
        "load_config",
        lambda: types.SimpleNamespace(
            repo_root=tmp_path,
            contract_root=tmp_path / "contracts",
            runtime_contract_root=tmp_path / ".runtime-cache" / "cortexpilot" / "contracts",
        ),
    )

    runs_root = tmp_path / ".runtime-cache" / "cortexpilot" / "runs"
    started = threading.Event()
    release = threading.Event()

    class _BuildOK:
        def build_contract(self, intake_id: str) -> dict[str, object]:
            return {"task_id": f"task-{intake_id}", "runtime_options": {}}

    class _SlowOrchestrator:
        @staticmethod
        def execute_task(contract_path: Path, mock_mode: bool = False) -> str:
            del mock_mode
            payload = json.loads(contract_path.read_text(encoding="utf-8"))
            task_id = str(payload.get("task_id") or "task")
            store = RunStore(runs_root=runs_root)
            run_id = store.create_run(task_id)
            store.write_manifest(run_id, {"run_id": run_id, "task_id": task_id, "status": "RUNNING"})
            started.set()
            release.wait(timeout=2.0)
            return run_id

    start = time.perf_counter()
    result = helpers.run_intake(
        "slow",
        intake_service_cls=_BuildOK,
        orchestration_service=_SlowOrchestrator(),
        error_detail_fn=lambda code: {"code": code},
        current_request_id_fn=lambda: "req-slow",
    )
    elapsed = time.perf_counter() - start
    release.set()

    assert started.is_set()
    assert elapsed < 1.0
    assert result["ok"] is True
    assert result["run_id"].startswith("run_")
    assert events[-1] == ("slow", {"event": "INTAKE_RUN", "run_id": result["run_id"]})


def test_run_intake_surfaces_background_error_when_no_run_id_observed(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(helpers, "IntakeStore", lambda: types.SimpleNamespace(append_event=lambda *_a, **_k: None))
    monkeypatch.setattr(
        helpers,
        "load_config",
        lambda: types.SimpleNamespace(
            repo_root=tmp_path,
            contract_root=tmp_path / "contracts",
            runtime_contract_root=tmp_path / ".runtime-cache" / "cortexpilot" / "contracts",
        ),
    )

    class _BuildOK:
        def build_contract(self, intake_id: str) -> dict[str, object]:
            return {"task_id": f"task-{intake_id}", "runtime_options": {}}

    class _FailingOrchestrator:
        @staticmethod
        def execute_task(contract_path: Path, mock_mode: bool = False) -> str:
            del contract_path, mock_mode
            raise RuntimeError("background failed")

    with pytest.raises(HTTPException) as exc:
        helpers.run_intake(
            "fail",
            intake_service_cls=_BuildOK,
            orchestration_service=_FailingOrchestrator(),
            error_detail_fn=lambda code: {"code": code},
            current_request_id_fn=lambda: "req-fail",
        )
    assert exc.value.status_code == 500
    assert exc.value.detail["code"] == "INTAKE_RUN_FAILED"


def test_run_intake_prefers_configured_runs_root_for_run_discovery(monkeypatch, tmp_path: Path) -> None:
    events: list[tuple[str, dict[str, object]]] = []

    class _Store:
        def append_event(self, intake_id: str, payload: dict[str, object]) -> None:
            events.append((intake_id, payload))

    runs_root = tmp_path / "custom-runs-root"
    monkeypatch.setattr(helpers, "IntakeStore", _Store)
    monkeypatch.setattr(
        helpers,
        "load_config",
        lambda: types.SimpleNamespace(
            repo_root=tmp_path / "wrong-repo-root",
            runs_root=runs_root,
            contract_root=tmp_path / "contracts",
            runtime_contract_root=tmp_path / ".runtime-cache" / "cortexpilot" / "contracts",
        ),
    )

    started = threading.Event()
    release = threading.Event()

    class _BuildOK:
        def build_contract(self, intake_id: str) -> dict[str, object]:
            return {"task_id": f"task-{intake_id}", "runtime_options": {}}

    class _SlowOrchestrator:
        @staticmethod
        def execute_task(contract_path: Path, mock_mode: bool = False) -> str:
            del mock_mode
            payload = json.loads(contract_path.read_text(encoding="utf-8"))
            task_id = str(payload.get("task_id") or "task")
            store = RunStore(runs_root=runs_root)
            run_id = store.create_run(task_id)
            store.write_manifest(run_id, {"run_id": run_id, "task_id": task_id, "status": "RUNNING"})
            started.set()
            release.wait(timeout=2.0)
            return run_id

    result = helpers.run_intake(
        "configured-runs-root",
        intake_service_cls=_BuildOK,
        orchestration_service=_SlowOrchestrator(),
        error_detail_fn=lambda code: {"code": code},
        current_request_id_fn=lambda: "req-configured-runs-root",
    )
    release.set()

    assert started.is_set()
    assert result["ok"] is True
    assert result["run_id"].startswith("run_")
    assert events[-1] == ("configured-runs-root", {"event": "INTAKE_RUN", "run_id": result["run_id"]})
