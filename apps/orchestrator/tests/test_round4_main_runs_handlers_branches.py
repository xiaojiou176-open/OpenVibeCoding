from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

from cortexpilot_orch.api.main_runs_handlers import build_runs_handlers


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(rows), encoding="utf-8")


def _build_handlers(runs_root: Path, **overrides: Any):
    state: dict[str, Any] = {
        "logged": [],
        "promoted": [],
        "service_calls": [],
    }

    class _Service:
        def replay_run(self, run_id: str, baseline_run_id: str | None = None) -> dict[str, Any]:
            state["service_calls"].append(("replay", run_id, baseline_run_id))
            return {"run_id": run_id, "baseline_run_id": baseline_run_id}

        def replay_verify(self, run_id: str, strict: bool = True) -> dict[str, Any]:
            state["service_calls"].append(("verify", run_id, strict))
            return {"ok": True, "run_id": run_id, "strict": strict}

        def replay_reexec(self, run_id: str, strict: bool = True) -> dict[str, Any]:
            state["service_calls"].append(("reexec", run_id, strict))
            return {"ok": True, "run_id": run_id, "strict": strict}

    def _promote(run_id: str, bundle: dict[str, Any]) -> dict[str, Any]:
        state["promoted"].append((run_id, bundle))
        return {"ok": True, "run_id": run_id, "bundle": bundle}

    def _log_event(*args: Any, **kwargs: Any) -> None:
        state["logged"].append((args, kwargs))

    defaults = {
        "runs_root_fn": lambda: runs_root,
        "load_contract_fn": lambda _run_id: {},
        "parse_iso_ts_fn": lambda value: datetime.fromisoformat(value.replace("Z", "+00:00")),
        "select_baseline_by_window_fn": lambda _run_id, _window: None,
        "last_event_ts_fn": lambda _run_id: "",
        "collect_workflows_fn": lambda: {},
        "read_events_fn": lambda _run_id: [],
        "filter_events_fn": lambda events, **_kwargs: events,
        "event_cursor_value_fn": lambda item: str(item.get("cursor") or item.get("ts") or ""),
        "safe_artifact_target_fn": lambda run_id, name: runs_root / run_id / "artifacts" / name,
        "read_artifact_fn": lambda _run_id, _name: None,
        "read_report_fn": lambda _run_id, _name: None,
        "extract_search_queries_fn": lambda _contract: [],
        "promote_evidence_fn": _promote,
        "orchestration_service_fn": lambda: _Service(),
        "load_config_fn": lambda: SimpleNamespace(contract_root=runs_root.parent / "contracts"),
        "error_detail_fn": lambda code: {"code": code},
        "current_request_id_fn": lambda: "req-round4",
        "log_event_fn": _log_event,
        "json_loads_fn": json.loads,
        "json_decode_error_cls": json.JSONDecodeError,
        "list_diff_gate_fn": lambda: [],
        "rollback_run_fn": lambda run_id: {"ok": False, "run_id": run_id},
        "reject_run_fn": lambda run_id: {"ok": False, "run_id": run_id},
        "list_reviews_fn": lambda: [],
        "list_tests_fn": lambda: [],
        "list_agents_fn": lambda: {"ok": True},
        "list_agents_status_fn": lambda run_id: {"run_id": run_id, "status": "ok"},
        "list_policies_fn": lambda: {},
        "list_locks_fn": lambda: [],
        "list_worktrees_fn": lambda: [],
        "read_events_incremental_fn": None,
    }
    defaults.update(overrides)
    return build_runs_handlers(**defaults), state


def test_round4_list_runs_branch_matrix(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"

    _write_json(
        runs_root / "run_event_gate" / "manifest.json",
        {
            "run_id": "run_event_gate",
            "task_id": "task-event-gate",
            "status": "FAILURE",
            "created_at": "not-iso",
            "failure_reason": "",
        },
    )
    _write_jsonl(
        runs_root / "run_event_gate" / "events.jsonl",
        [
            "",
            "bad-json-line",
            json.dumps(["not", "dict"], ensure_ascii=False),
            json.dumps({"event": "DIFF_GATE_RESULT", "context": {"result": "REJECTED"}}, ensure_ascii=False),
        ],
    )

    _write_json(
        runs_root / "run_reason_gate" / "manifest.json",
        {
            "run_id": "run_reason_gate",
            "task_id": "task-reason-gate",
            "status": "FAILURE",
            "failure_reason": "diff gate blocked by policy",
        },
    )
    _write_jsonl(runs_root / "run_reason_gate" / "events.jsonl", [])

    _write_json(
        runs_root / "run_unknown_class" / "manifest.json",
        {
            "run_id": "run_unknown_class",
            "task_id": "task-unknown",
            "status": "FAILED",
            "failure_class": "unknown",
            "failure_code": "X",
            "failure_stage": "Y",
            "failure_summary_zh": "未知",
            "action_hint_zh": "提示",
            "root_event": "ROOT",
        },
    )

    _write_json(
        runs_root / "run_running" / "manifest.json",
        {
            "run_id": "run_running",
            "task_id": "task-running",
            "status": "RUNNING",
        },
    )

    _write_json(
        runs_root / "run_weird" / "manifest.json",
        {
            "run_id": "run_weird",
            "task_id": "task-weird",
            "status": "WAITING_EXTERNAL",
        },
    )

    (runs_root / "run_bad_manifest").mkdir(parents=True, exist_ok=True)
    (runs_root / "run_bad_manifest" / "manifest.json").write_text("{", encoding="utf-8")

    def _json_loads(raw: str) -> Any:
        if raw == "bad-json-line":
            raise ValueError("bad json")
        return json.loads(raw)

    def _load_contract(run_id: str) -> dict[str, Any]:
        if run_id == "run_event_gate":
            raise RuntimeError("contract-read-failed")
        return {}

    handlers, _state = _build_handlers(
        runs_root,
        json_loads_fn=_json_loads,
        load_contract_fn=_load_contract,
    )
    runs = handlers["list_runs"]()
    by_id = {item["run_id"]: item for item in runs}

    assert by_id["run_event_gate"]["failure_class"] == "gate"
    assert by_id["run_event_gate"]["outcome_type"] == "gate"

    assert by_id["run_reason_gate"]["failure_class"] == "gate"
    assert by_id["run_reason_gate"]["failure_code"] == "DIFF_GATE_REJECTED"

    assert by_id["run_unknown_class"]["outcome_type"] == "product"
    assert by_id["run_unknown_class"]["outcome_label_zh"] == "Functional anomaly"

    assert by_id["run_running"]["outcome_type"] == "in_progress"
    assert by_id["run_running"]["outcome_label_zh"] == "In progress"

    assert by_id["run_weird"]["outcome_type"] == "unknown"
    assert by_id["run_weird"]["outcome_label_zh"] == "Unknown"
    assert "run_bad_manifest" not in by_id


def test_round4_workflow_listing_and_detail_branches(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"

    workflows = {
        "wf-recent": {
            "workflow_id": "wf-recent",
            "workflow_case_read_model": {
                "authority": "workflow-case-read-model",
                "source": "latest linked run manifest.role_binding_summary",
                "execution_authority": "task_contract",
                "workflow_id": "wf-recent",
                "source_run_id": "run-a",
                "role_binding_summary": {"authority": "contract-derived-read-model"},
            },
            "runs": [
                {"run_id": "run-a", "created_at": "2026-03-08T02:00:00Z"},
                {"run_id": "run-b", "created_at": "bad-ts"},
            ],
        },
        "wf-old": {
            "workflow_id": "wf-old",
            "runs": [{"run_id": "run-c", "created_at": "2020-01-01T00:00:00Z"}],
        },
    }

    def _read_events(run_id: str) -> list[Any]:
        if run_id == "run-a":
            return [
                {"event": "WORKFLOW_BOUND", "ts": "2026-03-08T02:00:00Z"},
                {"event": "OTHER", "context": {"workflow_id": "wf-recent"}, "_ts": "2026-03-08T02:00:01Z"},
                {"event": "IGNORED", "context": {"workflow_id": "other"}},
                "not-a-dict",
            ]
        if run_id == "run-b":
            return [{"event": "TEMPORAL_NOTIFY_START", "ts": "2026-03-08T01:59:00Z"}]
        return [{"event": "UNRELATED", "ts": "2020-01-01T00:00:00Z"}]

    handlers, _state = _build_handlers(
        runs_root,
        collect_workflows_fn=lambda: workflows,
        read_events_fn=_read_events,
    )

    listed = handlers["list_workflows"]()
    assert [item["workflow_id"] for item in listed] == ["wf-recent", "wf-old"]

    detail = handlers["get_workflow"]("wf-recent")
    assert detail["workflow"]["workflow_id"] == "wf-recent"
    assert detail["workflow"]["workflow_case_read_model"]["source_run_id"] == "run-a"
    assert all(isinstance(item, dict) for item in detail["events"])
    assert any(item.get("_run_id") == "run-a" for item in detail["events"])

    with pytest.raises(HTTPException) as exc_info:
        handlers["get_workflow"]("wf-missing")
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["code"] == "WORKFLOW_NOT_FOUND"


def test_round4_stream_events_and_follow_keepalive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runs_root = tmp_path / "runs"
    run_id = "run-stream"
    (runs_root / run_id).mkdir(parents=True, exist_ok=True)

    class _Req:
        def __init__(self, disconnect_after: int) -> None:
            self.calls = 0
            self.disconnect_after = disconnect_after

        async def is_disconnected(self) -> bool:
            self.calls += 1
            return self.calls > self.disconnect_after

    async def _run() -> None:
        handlers_missing, _state = _build_handlers(runs_root)
        with pytest.raises(HTTPException) as exc_info:
            await handlers_missing["stream_events"]("missing-run", _Req(disconnect_after=1), follow=False)
        assert exc_info.value.status_code == 404

        handlers_once, _state = _build_handlers(
            runs_root,
            read_events_fn=lambda _rid: [
                {"event": "FIRST", "ts": "2026-03-08T00:00:00Z", "cursor": "c-first"},
                {"event": "SECOND", "ts": "2026-03-08T00:00:01Z", "cursor": ""},
            ],
            filter_events_fn=lambda events, **_kwargs: events,
            event_cursor_value_fn=lambda item: str(item.get("cursor") or ""),
        )

        response = await handlers_once["stream_events"](run_id, _Req(disconnect_after=1), follow=False)
        chunks: list[str] = []
        async for chunk in response.body_iterator:
            chunks.append(chunk if isinstance(chunk, str) else chunk.decode("utf-8"))

        joined = "".join(chunks)
        assert "event: run_event" in joined
        assert '"FIRST"' in joined and '"SECOND"' in joined
        assert "id: c-first" in joined

        async def _no_sleep(_seconds: float) -> None:
            return None

        monkeypatch.setattr("cortexpilot_orch.api.main_runs_handlers.asyncio.sleep", _no_sleep)

        def _read_events_incremental(**kwargs: Any) -> tuple[list[dict[str, Any]], int]:
            if kwargs["offset"] == 0:
                return ([{"event": "INIT", "cursor": "c-init"}], 1)
            return ([], kwargs["offset"])

        handlers_follow, _state = _build_handlers(
            runs_root,
            read_events_incremental_fn=_read_events_incremental,
            event_cursor_value_fn=lambda item: str(item.get("cursor") or ""),
        )

        response_follow = await handlers_follow["stream_events"](run_id, _Req(disconnect_after=1), follow=True)
        follow_chunks: list[str] = []
        async for chunk in response_follow.body_iterator:
            follow_chunks.append(chunk if isinstance(chunk, str) else chunk.decode("utf-8"))

        assert any("keep-alive" in item for item in follow_chunks)

    asyncio.run(_run())


def test_round4_reports_and_artifacts_branches(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    run_id = "run-files"
    reports_dir = runs_root / run_id / "reports"
    artifacts_dir = runs_root / run_id / "artifacts"
    reports_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    _write_json(reports_dir / "ok.json", {"ok": True})
    (reports_dir / "bad.json").write_text("{", encoding="utf-8")

    _write_json(artifacts_dir / "ok.json", {"hello": "world"})
    _write_jsonl(
        artifacts_dir / "lines.jsonl",
        [
            json.dumps({"n": 1}, ensure_ascii=False),
            "{",
            "",
        ],
    )
    (artifacts_dir / "plain.txt").write_text("plain-data", encoding="utf-8")
    (artifacts_dir / "dir.json").mkdir(parents=True, exist_ok=True)

    handlers, _state = _build_handlers(runs_root)

    reports = handlers["get_reports"](run_id)
    assert {item["name"] for item in reports} == {"ok.json", "bad.json"}
    assert any("raw" in item["data"] for item in reports if item["name"] == "bad.json")

    missing_artifacts = handlers["get_artifacts"]("missing-run")
    assert missing_artifacts == {"items": []}

    missing_named = handlers["get_artifacts"](run_id, name="absent.json")
    assert missing_named == {"name": "absent.json", "data": None}

    with pytest.raises(HTTPException) as exc_dir:
        handlers["get_artifacts"](run_id, name="dir.json")
    assert exc_dir.value.status_code == 400
    assert exc_dir.value.detail["code"] == "ARTIFACT_PATH_IS_DIRECTORY"

    parsed_jsonl = handlers["get_artifacts"](run_id, name="lines.jsonl")
    assert isinstance(parsed_jsonl["data"], list)
    assert any(item.get("raw") == "{" for item in parsed_jsonl["data"] if isinstance(item, dict))

    plain = handlers["get_artifacts"](run_id, name="plain.txt")
    assert plain["data"] == "plain-data"

    def _json_loads_boom(raw: str) -> Any:
        if raw == (artifacts_dir / "ok.json").read_text(encoding="utf-8"):
            raise RuntimeError("json parse boom")
        return json.loads(raw)

    handlers_err, state_err = _build_handlers(
        runs_root,
        json_loads_fn=_json_loads_boom,
        safe_artifact_target_fn=lambda rid, name: runs_root / rid / "artifacts" / name,
    )

    with pytest.raises(HTTPException) as exc_artifact:
        handlers_err["get_artifacts"](run_id, name="ok.json")
    assert exc_artifact.value.status_code == 500
    assert exc_artifact.value.detail["code"] == "ARTIFACTS_READ_FAILED"
    assert any(args[2] == "ARTIFACTS_READ_FAILED" for args, _kwargs in state_err["logged"])


def test_round4_search_promote_replay_and_contract_branches(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    contract_root = tmp_path / "contracts"
    run_id = "run-promote"
    (runs_root / run_id).mkdir(parents=True, exist_ok=True)
    (contract_root / "examples").mkdir(parents=True, exist_ok=True)
    (contract_root / "tasks").mkdir(parents=True, exist_ok=True)
    (contract_root / "examples" / "broken.json").mkdir(parents=True, exist_ok=True)
    (contract_root / "tasks" / "raw.json").write_text("RAW", encoding="utf-8")

    def _json_loads_contract(raw: str) -> Any:
        if raw == "RAW":
            raise RuntimeError("decode failure")
        return json.loads(raw)

    handlers, state = _build_handlers(
        runs_root,
        load_contract_fn=lambda _rid: {"assigned_agent": {"agent_id": "A-1", "role": "SEARCHER"}},
        read_artifact_fn=lambda _rid, _name: {"latest": {"results": [{"title": "Result"}]}},
        extract_search_queries_fn=lambda _contract: ["alpha", "beta"],
        load_config_fn=lambda: SimpleNamespace(contract_root=contract_root),
        json_loads_fn=_json_loads_contract,
    )

    with pytest.raises(HTTPException) as exc_search:
        handlers["get_search"]("run-missing")
    assert exc_search.value.status_code == 404
    assert exc_search.value.detail["code"] == "RUN_NOT_FOUND"

    promoted = handlers["promote_evidence"](run_id)
    assert promoted["ok"] is True
    promoted_bundle = state["promoted"][0][1]
    assert promoted_bundle["query"]["raw_question"] == "alpha; beta"

    with pytest.raises(HTTPException) as exc_payload:
        handlers["replay_run"](run_id, payload=["bad"])  # type: ignore[arg-type]
    assert exc_payload.value.status_code == 400
    assert exc_payload.value.detail["code"] == "PAYLOAD_INVALID"

    with pytest.raises(HTTPException) as exc_window_type:
        handlers["replay_run"](run_id, payload={"baseline_window": "bad-window"})
    assert exc_window_type.value.status_code == 400
    assert exc_window_type.value.detail["code"] == "BASELINE_WINDOW_INVALID"

    handlers_window_error, state_window_error = _build_handlers(
        runs_root,
        select_baseline_by_window_fn=lambda _rid, _window: (_ for _ in ()).throw(ValueError("bad window")),
    )
    with pytest.raises(HTTPException) as exc_window:
        handlers_window_error["replay_run"](run_id, payload={"baseline_window": {"from": "x", "to": "y"}})
    assert exc_window.value.status_code == 400
    assert exc_window.value.detail["code"] == "BASELINE_WINDOW_INVALID"
    assert any(args[2] == "BASELINE_WINDOW_INVALID" for args, _kwargs in state_window_error["logged"])

    replay = handlers["replay_run"](run_id, payload={"baseline_run_id": "base-1"})
    assert replay["baseline_run_id"] == "base-1"

    verify = handlers["verify_run"](run_id, strict=False)
    reexec = handlers["reexec_run"](run_id, strict=True)
    assert verify == {"ok": True, "run_id": run_id, "strict": False}
    assert reexec == {"ok": True, "run_id": run_id, "strict": True}

    events_by_run = {
        "run-a": [{"event": "E1", "ts": "2026-01-02T00:00:00Z"}],
        "run-b": [{"event": "E2", "_ts": "2026-01-03T00:00:00Z"}],
    }
    handlers_events, _state_events = _build_handlers(
        runs_root,
        read_events_fn=lambda rid: events_by_run.get(rid, []),
    )
    (runs_root / "run-a").mkdir(parents=True, exist_ok=True)
    (runs_root / "run-b").mkdir(parents=True, exist_ok=True)

    listed_events = handlers_events["list_events"](limit=0)
    assert len(listed_events) == 1
    assert listed_events[0]["event"] == "E2"

    status_payload = handlers["list_agents_status"]("run-x")
    assert status_payload == {"run_id": "run-x", "status": "ok"}

    contracts = handlers["list_contracts"]()
    by_source = {item["source"]: item for item in contracts}
    assert by_source["examples"]["record_status"] == "read-failed"
    assert by_source["tasks"]["record_status"] == "raw"
    assert by_source["tasks"]["raw_preview"] == "RAW"
