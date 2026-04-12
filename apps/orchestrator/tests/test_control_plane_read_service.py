from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from types import ModuleType

import pytest

from cortexpilot_orch.services.control_plane_read_service import (
    ControlPlaneReadService,
    _as_array,
    _as_record,
    _as_text,
    _find_report,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_control_plane_read_service_wrapper_filters_and_summary_helpers() -> None:
    service = ControlPlaneReadService(
        list_runs_fn=lambda: [{"run_id": "run-1"}],
        get_run_fn=lambda run_id: {"run_id": run_id},
        get_events_fn=lambda run_id: [{"run_id": run_id, "event": "RUN_UPDATED"}],
        get_reports_fn=lambda run_id: [
            {"name": "run_compare_report.json", "data": {"compare_summary": {"mismatched_count": 2}}},
            {"name": "proof_pack.json", "data": {"summary": "proof-ready"}},
            {"name": "incident_pack.json", "data": "not-a-record"},
        ]
        if run_id == "run-1"
        else "not-a-list",
        list_workflows_fn=lambda: [{"workflow_id": "wf-1"}],
        get_workflow_fn=lambda workflow_id: {"workflow": {"workflow_id": workflow_id}, "runs": [], "events": []},
        list_queue_fn=lambda **_: [{"queue_id": "queue-1"}],
        list_pending_approvals_fn=lambda: [
            {"run_id": "run-1", "status": "pending"},
            {"run_id": "run-2", "status": "pending"},
        ],
        list_diff_gate_fn=lambda: [
            {"run_id": "run-1", "status": "FAILED"},
            {"run_id": "run-2", "status": "PASS"},
        ],
    )

    assert _as_record({"ok": True}) == {"ok": True}
    assert _as_record("bad") == {}
    assert _as_array([1, 2]) == [1, 2]
    assert _as_array("bad") == []
    assert _as_text("  run-1  ") == "run-1"
    assert _find_report([{"name": "proof_pack.json", "data": {"summary": "ready"}}], "proof_pack.json") == {
        "summary": "ready"
    }
    assert _find_report([{"name": "proof_pack.json", "data": "bad"}], "proof_pack.json") == {}

    assert service.list_runs() == [{"run_id": "run-1"}]
    assert service.get_run("run-9") == {"run_id": "run-9"}
    assert service.get_run_events("run-9") == [{"run_id": "run-9", "event": "RUN_UPDATED"}]
    assert service.get_run_reports("run-2") == []
    assert service.list_workflows() == [{"workflow_id": "wf-1"}]
    assert service.get_workflow("wf-1") == {"workflow": {"workflow_id": "wf-1"}, "runs": [], "events": []}
    assert service.list_queue(workflow_id="wf-1", status="pending") == [{"queue_id": "queue-1"}]
    assert service.get_pending_approvals() == [
        {"run_id": "run-1", "status": "pending"},
        {"run_id": "run-2", "status": "pending"},
    ]
    assert service.get_pending_approvals(run_id="run-1") == [{"run_id": "run-1", "status": "pending"}]
    assert service.get_diff_gate_state() == [
        {"run_id": "run-1", "status": "FAILED"},
        {"run_id": "run-2", "status": "PASS"},
    ]
    assert service.get_diff_gate_state(run_id="run-2") == [{"run_id": "run-2", "status": "PASS"}]
    assert service.get_compare_summary("run-1") == {"mismatched_count": 2}
    assert service.get_proof_summary("run-1") == {"summary": "proof-ready"}
    assert service.get_incident_summary("run-1") == {}


def test_control_plane_read_service_from_api_main_builds_workflows_and_queue_filters(monkeypatch) -> None:
    event_map = {
        "run-b": [
            {"event": "WORKFLOW_STATUS", "ts": "2026-04-12T10:00:00Z", "context": {"workflow_id": "wf-1"}},
            {"event": "IGNORED", "context": {"workflow_id": "wf-2"}},
        ],
        "run-a": [
            {"event": "WORKFLOW_BOUND", "ts": "2026-04-11T10:00:00Z"},
            {"event": "CUSTOM", "_ts": "2026-04-11T09:00:00Z", "context": {"workflow_id": "wf-1"}},
        ],
    }

    workflows = {
        "wf-1": {
            "workflow_id": "wf-1",
            "runs": [
                {"run_id": "run-a", "created_at": "2026-04-11T08:00:00Z"},
                {"run_id": "run-b", "created_at": "2026-04-12T08:00:00Z"},
            ],
        },
        "wf-2": {"workflow_id": "wf-2", "runs": [{"run_id": "run-z", "created_at": "broken-ts"}]},
    }

    class _FakeQueueStore:
        def __init__(self, *, ensure_storage: bool = False) -> None:
            self.ensure_storage = ensure_storage

        def list_items(self) -> list[dict[str, str]]:
            return [
                {"queue_id": "queue-1", "workflow_id": "wf-1", "status": "PENDING"},
                {"queue_id": "queue-2", "workflow_id": "wf-2", "status": "DONE"},
            ]

    api_main = ModuleType("cortexpilot_orch.api.main")
    api_main.load_config = lambda: SimpleNamespace(runs_root=Path("/tmp/runs"), runtime_root=Path("/tmp/runtime"))
    api_main._read_events = lambda run_id: event_map.get(run_id, [])
    api_main._parse_iso_ts = lambda value: datetime.fromisoformat(value.replace("Z", "+00:00"))
    api_main.list_runs = lambda: [{"run_id": "api-run"}]
    api_main.get_run = lambda run_id: {"run_id": run_id, "source": "api"}
    api_main.get_events = lambda run_id: event_map.get(run_id, [])
    api_main.get_reports = lambda run_id: [{"name": "proof_pack.json", "data": {"run_id": run_id}}]
    api_main.list_pending_approvals = lambda: [{"run_id": "run-a"}]
    api_main.list_diff_gate = lambda: [{"run_id": "run-b", "status": "FAILED"}]

    main_state_store_helpers = ModuleType("cortexpilot_orch.api.main_state_store_helpers")
    main_state_store_helpers.collect_workflows = lambda **_: workflows

    queue_module = ModuleType("cortexpilot_orch.queue")
    queue_module.QueueStore = _FakeQueueStore

    monkeypatch.setitem(sys.modules, "cortexpilot_orch.api.main", api_main)
    monkeypatch.setitem(sys.modules, "cortexpilot_orch.api.main_state_store_helpers", main_state_store_helpers)
    monkeypatch.setitem(sys.modules, "cortexpilot_orch.queue", queue_module)

    service = ControlPlaneReadService.from_api_main()

    assert service.list_runs() == [{"run_id": "api-run"}]
    assert service.get_run("run-a") == {"run_id": "run-a", "source": "api"}
    assert [item["workflow_id"] for item in service.list_workflows()] == ["wf-1", "wf-2"]

    workflow_payload = service.get_workflow("wf-1")
    assert [event["_run_id"] for event in workflow_payload["events"]] == ["run-b", "run-a", "run-a"]
    assert workflow_payload["runs"][0]["run_id"] == "run-a"
    with pytest.raises(KeyError, match="workflow `missing` not found"):
        service.get_workflow("missing")

    assert service.list_queue(workflow_id="wf-1") == [{"queue_id": "queue-1", "workflow_id": "wf-1", "status": "PENDING"}]
    assert service.list_queue(status="done") == [{"queue_id": "queue-2", "workflow_id": "wf-2", "status": "DONE"}]
    assert service.get_pending_approvals() == [{"run_id": "run-a"}]
    assert service.get_diff_gate_state(run_id="run-b") == [{"run_id": "run-b", "status": "FAILED"}]


def test_control_plane_read_service_from_runtime_builds_runtime_views_and_pending_approvals(
    monkeypatch, tmp_path: Path
) -> None:
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    run_a = runs_root / "run-a"
    run_b = runs_root / "run-b"
    run_skip = runs_root / "run-skip"

    _write_json(
        run_a / "manifest.json",
        {
            "run_id": "run-a",
            "task_id": "task-a",
            "status": "",
            "role_binding_summary": {"source": "persisted"},
        },
    )
    _write_json(
        run_a / "contract.json",
        {
            "task_id": "contract-task-a",
            "allowed_paths": ["apps/orchestrator"],
        },
    )
    _write_json(run_a / "reports" / "proof_pack.json", {"summary": "proof-a"})
    _write_json(run_a / "reports" / "run_compare_report.json", {"compare_summary": {"mismatched_count": 3}})

    _write_json(
        run_b / "manifest.json",
        {
            "status": "SUCCESS",
        },
    )
    _write_json(
        run_b / "contract.json",
        {
            "task_id": "contract-task-b",
            "allowed_paths": "not-a-list",
        },
    )
    _write_json(run_b / "reports" / "incident_pack.json", {"summary": "incident-b"})

    run_skip.mkdir(parents=True, exist_ok=True)
    (run_skip / "manifest.json").write_text("{bad json", encoding="utf-8")

    run_a.touch()
    run_b.touch()
    run_skip.touch()
    (run_a / "manifest.json").touch()
    (run_b / "manifest.json").touch()
    (run_skip / "manifest.json").touch()

    event_map = {
        "run-a": [
            {"event": "WORKFLOW_BOUND", "ts": "2026-04-12T10:00:00Z"},
            {
                "event": "HUMAN_APPROVAL_REQUIRED",
                "ts": "2026-04-12T10:01:00Z",
                "context": {
                    "reason": ["owner review"],
                    "actions": ["approve"],
                    "verify_steps": ["pytest"],
                    "resume_step": "resume-from-review",
                    "workflow_id": "wf-1",
                },
            },
            {"event": "CUSTOM", "_ts": "2026-04-12T10:02:00Z", "context": {"workflow_id": "wf-1"}},
        ],
        "run-b": [
            {"event": "HUMAN_APPROVAL_REQUIRED", "ts": "2026-04-11T09:00:00Z", "meta": {"workflow_id": "wf-2"}},
            {"event": "HUMAN_APPROVAL_COMPLETED", "ts": "2026-04-11T09:05:00Z"},
            {"event": "TEMPORAL_NOTIFY_DONE", "ts": "2026-04-11T09:10:00Z"},
        ],
        "run-skip": [],
    }

    workflows = {
        "wf-1": {
            "workflow_id": "wf-1",
            "runs": [
                {"run_id": "run-b", "created_at": "2026-04-11T08:00:00Z"},
                {"run_id": "run-a", "created_at": "2026-04-12T08:00:00Z"},
            ],
        },
        "wf-2": {"workflow_id": "wf-2", "runs": [{"run_id": "run-b", "created_at": "invalid"}]},
    }

    class _FakeQueueStore:
        def __init__(self, *, ensure_storage: bool = False) -> None:
            self.ensure_storage = ensure_storage

        def list_items(self) -> list[dict[str, str]]:
            return [
                {"queue_id": "queue-1", "workflow_id": "wf-1", "status": "PENDING"},
                {"queue_id": "queue-2", "workflow_id": "wf-2", "status": "DONE"},
            ]

    config_module = ModuleType("cortexpilot_orch.config")
    config_module.load_config = lambda: SimpleNamespace(runs_root=runs_root, runtime_root=runtime_root)

    main_state_store_helpers = ModuleType("cortexpilot_orch.api.main_state_store_helpers")
    main_state_store_helpers.read_events = lambda *, run_id, runs_root: event_map.get(run_id, [])
    main_state_store_helpers.collect_workflows = lambda **_: workflows

    main_run_views_helpers = ModuleType("cortexpilot_orch.api.main_run_views_helpers")
    main_run_views_helpers.list_diff_gate = lambda **_: [
        {"run_id": "run-a", "status": "FAILED"},
        {"run_id": "run-b", "status": "PASS"},
    ]

    compiler_module = ModuleType("cortexpilot_orch.contract.compiler")
    compiler_module.build_role_binding_summary = lambda contract: {
        "source": "generated",
        "task_id": contract.get("task_id"),
    }

    queue_module = ModuleType("cortexpilot_orch.queue")
    queue_module.QueueStore = _FakeQueueStore

    monkeypatch.setitem(sys.modules, "cortexpilot_orch.config", config_module)
    monkeypatch.setitem(sys.modules, "cortexpilot_orch.api.main_state_store_helpers", main_state_store_helpers)
    monkeypatch.setitem(sys.modules, "cortexpilot_orch.api.main_run_views_helpers", main_run_views_helpers)
    monkeypatch.setitem(sys.modules, "cortexpilot_orch.contract.compiler", compiler_module)
    monkeypatch.setitem(sys.modules, "cortexpilot_orch.queue", queue_module)

    service = ControlPlaneReadService.from_runtime()

    listed_runs = service.list_runs()
    assert [item["run_id"] for item in listed_runs] == ["run-b", "run-a"]
    assert listed_runs[1]["status"] == "UNKNOWN"
    assert listed_runs[1]["last_event_ts"] == "2026-04-12T10:02:00Z"

    runtime_run = service.get_run("run-a")
    assert runtime_run["task_id"] == "task-a"
    assert runtime_run["allowed_paths"] == ["apps/orchestrator"]
    assert runtime_run["role_binding_read_model"] == {"source": "persisted"}

    generated_run = service.get_run("run-b")
    assert generated_run["task_id"] == "contract-task-b"
    assert generated_run["allowed_paths"] == []
    assert generated_run["role_binding_read_model"] == {"source": "generated", "task_id": "contract-task-b"}
    with pytest.raises(KeyError, match="run `missing` not found"):
        service.get_run("missing")

    assert service.get_run_reports("run-a") == [
        {"name": "proof_pack.json", "data": {"summary": "proof-a"}},
        {"name": "run_compare_report.json", "data": {"compare_summary": {"mismatched_count": 3}}},
    ]
    assert [item["workflow_id"] for item in service.list_workflows()] == ["wf-1", "wf-2"]

    workflow_payload = service.get_workflow("wf-1")
    assert [event["_run_id"] for event in workflow_payload["events"]] == ["run-a", "run-a", "run-a", "run-b"]
    with pytest.raises(KeyError, match="workflow `missing` not found"):
        service.get_workflow("missing")

    assert service.list_queue(workflow_id="wf-1", status="pending") == [
        {"queue_id": "queue-1", "workflow_id": "wf-1", "status": "PENDING"}
    ]
    assert service.get_pending_approvals() == [
        {
            "run_id": "run-a",
            "status": "pending",
            "task_id": "task-a",
            "failure_reason": "",
            "reason": ["owner review"],
            "actions": ["approve"],
            "verify_steps": ["pytest"],
            "resume_step": "resume-from-review",
        }
    ]
    assert service.get_pending_approvals(run_id="run-a")[0]["run_id"] == "run-a"
    assert service.get_diff_gate_state(run_id="run-a") == [{"run_id": "run-a", "status": "FAILED"}]
    assert service.get_compare_summary("run-a") == {"mismatched_count": 3}
    assert service.get_proof_summary("run-a") == {"summary": "proof-a"}
    assert service.get_incident_summary("run-b") == {"summary": "incident-b"}
