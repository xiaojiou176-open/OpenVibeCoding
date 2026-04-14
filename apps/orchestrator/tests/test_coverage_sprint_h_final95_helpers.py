from __future__ import annotations

import json
from pathlib import Path
import types

import pytest
from fastapi import HTTPException

from openvibecoding_orch.api import event_cursor
from openvibecoding_orch.api import main_pm_intake_helpers as pm_helpers
from openvibecoding_orch.api import run_state_helpers
from openvibecoding_orch.chain import runtime_helpers
from openvibecoding_orch.store.run_store import RunStore


def _err(code: str) -> dict[str, str]:
    return {"code": code}


def test_event_cursor_and_run_state_remaining_edges(tmp_path: Path) -> None:
    # Force ISO parse failure for `since` so string fallback branch is exercised.
    assert (
        event_cursor.is_event_after_cursor(
            {"ts": "2026-01-01T00:00:00Z"},
            "!bad-cursor",
        )
        is True
    )
    assert event_cursor.is_event_after_cursor({"ts": "   ", "_ts": ""}, "2026-01-01T00:00:00Z") is False

    runs_root = tmp_path / "runs"
    run_id = "run-ts"
    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "events.jsonl").write_text(
        '{"event":"A","_ts":"2026-01-01T00:00:00Z"}\n{"event":"B","ts":"2026-01-02T00:00:00Z"}\n',
        encoding="utf-8",
    )
    assert run_state_helpers.last_event_ts(run_id, runs_root=runs_root) == "2026-01-02T00:00:00Z"

    empty_run_id = "run-empty"
    empty_run_dir = runs_root / empty_run_id
    empty_run_dir.mkdir(parents=True, exist_ok=True)
    (empty_run_dir / "events.jsonl").write_text("\n", encoding="utf-8")
    assert run_state_helpers.last_event_ts(empty_run_id, runs_root=runs_root) == ""


def test_pm_intake_bool_runner_and_http_exception_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert pm_helpers._coerce_bool(True) is True
    assert pm_helpers._coerce_bool(" YES ") is True
    assert pm_helpers._coerce_bool(0) is False
    assert pm_helpers._coerce_bool(1.2) is True
    assert pm_helpers._coerce_bool(object()) is False

    assert pm_helpers._normalize_runner(None) == ""
    assert pm_helpers._normalize_runner(" CoDeX ") == "codex"
    with pytest.raises(ValueError):
        pm_helpers._normalize_runner("unknown-runner")

    class _BuildRaisesHTTP:
        def build_contract(self, _intake_id: str) -> dict[str, object]:
            raise HTTPException(status_code=418, detail={"code": "teapot"})

    with pytest.raises(HTTPException) as exc_http:
        pm_helpers.run_intake(
            "i-http",
            payload={"runner": "agents"},
            intake_service_cls=_BuildRaisesHTTP,
            orchestration_service=types.SimpleNamespace(execute_task=lambda *_a, **_k: "run-unused"),
            error_detail_fn=_err,
            current_request_id_fn=lambda: "req-http",
        )
    assert exc_http.value.status_code == 418

    monkeypatch.setattr(
        pm_helpers,
        "load_config",
        lambda: types.SimpleNamespace(
            contract_root=tmp_path / "contracts",
            runtime_contract_root=tmp_path / ".runtime-cache" / "openvibecoding" / "contracts",
        ),
    )
    appended: list[tuple[str, dict[str, object]]] = []

    class _Store:
        def append_event(self, intake_id: str, payload: dict[str, object]) -> None:
            appended.append((intake_id, payload))

    monkeypatch.setattr(pm_helpers, "IntakeStore", _Store)

    class _BuildReady:
        def build_contract(self, intake_id: str) -> dict[str, object]:
            return {
                "task_id": f"task-{intake_id}",
                "audit_only": True,
                "runtime_options": {"existing": 1},
            }

    class _Orch:
        @staticmethod
        def execute_task(contract_path: Path, mock_mode: bool = False) -> str:
            payload = json.loads(contract_path.read_text(encoding="utf-8"))
            assert payload["runtime_options"] == {"existing": 1}
            assert mock_mode is False
            return "run-ok"

    result = pm_helpers.run_intake(
        "i-ok",
        payload=None,
        intake_service_cls=_BuildReady,
        orchestration_service=_Orch(),
        error_detail_fn=_err,
        current_request_id_fn=lambda: "req-ok",
    )
    assert result["run_id"] == "run-ok"
    assert result["strict_acceptance"] is False
    assert appended[-1][0] == "i-ok"

    # payload is a dict but omits `strict_acceptance` key.
    result_no_strict = pm_helpers.run_intake(
        "i-ok-2",
        payload={"mock": False},
        intake_service_cls=_BuildReady,
        orchestration_service=_Orch(),
        error_detail_fn=_err,
        current_request_id_fn=lambda: "req-ok-2",
    )
    assert result_no_strict["strict_acceptance"] is False


def test_runtime_helpers_remaining_fail_closed_branches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # ensure_output_schema_artifact: return early when artifact already present
    contract_existing = {
        "assigned_agent": {"role": "WORKER"},
        "inputs": {"artifacts": [{"name": " output_schema.worker "}]},
    }
    before = list(contract_existing["inputs"]["artifacts"])
    out = runtime_helpers.ensure_output_schema_artifact(contract_existing)
    assert out["inputs"]["artifacts"] == before

    # ensure_output_schema_artifact: schema file missing branch
    monkeypatch.setattr(runtime_helpers, "output_schema_name_for_role", lambda _role: "missing.schema.json")
    missing_schema_contract = {"assigned_agent": {"role": "WORKER"}, "inputs": {"artifacts": []}}
    out_missing = runtime_helpers.ensure_output_schema_artifact(missing_schema_contract)
    assert out_missing["inputs"]["artifacts"] == []

    assert runtime_helpers.normalize_run_status("  ") == "UNKNOWN"
    assert runtime_helpers.normalize_run_status("pass") == "PASS"

    assert runtime_helpers.is_fanin_step({"name": "FAN_IN"}) is True
    assert runtime_helpers.is_fanin_step({"labels": ["x", " fan_in "]}) is True
    assert runtime_helpers.is_fanin_step({"name": "worker", "labels": ["x"]}) is False

    assert runtime_helpers.is_purified_name("dependency_summary.json") is True
    assert runtime_helpers.is_purified_name("raw_dump.json") is False
    assert runtime_helpers.is_raw_name("browser_results_snapshot.json") is True
    assert runtime_helpers.is_raw_name("summary.json") is False

    store = RunStore(runs_root=tmp_path / "runs")
    chain_run_id = store.create_run("chain")

    # step_run_id missing -> immediate return
    runtime_helpers.normalize_fanin_task_result(store, chain_run_id, "fan_in", "", ["dep-1"])

    # JSON decode fail + non-dict payload -> fail-closed return
    bad_run_id = store.create_run("bad")
    bad_dir = store._run_dir(bad_run_id)
    (bad_dir / "reports").mkdir(parents=True, exist_ok=True)
    (bad_dir / "reports" / "task_result.json").write_text("{bad-json", encoding="utf-8")
    (bad_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    (bad_dir / "artifacts" / "agent_task_result.json").write_text("[]", encoding="utf-8")
    runtime_helpers.normalize_fanin_task_result(store, chain_run_id, "fan_in", bad_run_id, ["dep-a"])

    # valid dict without task_id -> fallback to step_name path
    ok_run_id = store.create_run("ok")
    ok_dir = store._run_dir(ok_run_id)
    (ok_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    (ok_dir / "artifacts" / "agent_task_result.json").write_text(
        json.dumps(
            {
                "summary": json.dumps([{"severity": "high", "title": "x"}]),
                "evidence_refs": "bad",
            }
        ),
        encoding="utf-8",
    )
    runtime_helpers.normalize_fanin_task_result(store, chain_run_id, "fan_in", ok_run_id, [" dep-x ", ""])
    saved = json.loads((ok_dir / "reports" / "task_result.json").read_text(encoding="utf-8"))
    saved_summary = json.loads(saved["summary"])
    assert saved_summary["stats"]["high"] == 1
    assert saved["evidence_refs"]["dependency_run_ids"] == ["dep-x"]

    # apply_context_policy with non-dict inputs (bootstraps defaults), and max_artifacts path.
    policy_contract = {"inputs": "bad"}
    updated, violations, truncations = runtime_helpers.apply_context_policy(
        policy_contract,
        {"mode": "isolated", "max_artifacts": 0, "max_spec_chars": 2},
        owner_role="WORKER",
        step_name="step-z",
    )
    assert updated["inputs"] == {"spec": "", "artifacts": []}
    assert violations == []
    assert truncations == []

    # explicit allow/deny + summary requirement across artifact loop.
    contract_loop = {"inputs": {"spec": "abcdef", "artifacts": [{"name": "raw_data.json"}, {"name": "summary.json"}]}}
    _, loop_violations, loop_trunc = runtime_helpers.apply_context_policy(
        contract_loop,
        {
            "mode": "inherit",
            "allow_artifact_names": "summary.json",
            "deny_artifact_substrings": ["raw"],
            "require_summary": True,
            "max_artifacts": 1,
            "max_spec_chars": 3,
        },
        owner_role="WORKER",
        step_name="step-loop",
    )
    assert any("artifact not allowed: raw_data.json" in item for item in loop_violations)
    assert any("artifact denied by policy: raw_data.json" in item for item in loop_violations)
    assert any("summary required: raw_data.json" in item for item in loop_violations)
    assert any("artifacts truncated to 1" in item for item in loop_trunc)
    assert any("spec truncated to 3 chars" in item for item in loop_trunc)
