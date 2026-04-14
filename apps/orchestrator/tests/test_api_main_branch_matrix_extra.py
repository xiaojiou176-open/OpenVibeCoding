import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest
from fastapi import HTTPException

from openvibecoding_orch.api import main as api_main
from openvibecoding_orch.api import main_state_store_helpers


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _setup_env(monkeypatch, tmp_path: Path) -> tuple[Path, Path, Path]:
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    repo_root = tmp_path / "repo"
    contract_root = tmp_path / "contracts"
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("OPENVIBECODING_REPO_ROOT", str(repo_root))
    monkeypatch.setenv("OPENVIBECODING_CONTRACT_ROOT", str(contract_root))
    return runtime_root, runs_root, contract_root


def test_api_helpers_worktree_baseline_and_last_event(monkeypatch, tmp_path: Path) -> None:
    _, runs_root, _ = _setup_env(monkeypatch, tmp_path)

    run_a = runs_root / "run_a"
    run_b = runs_root / "run_b"
    run_c = runs_root / "run_c"
    _write_json(run_a / "manifest.json", {"run_id": "run_a", "created_at": "2024-01-01T00:00:00Z"})
    _write_json(run_b / "manifest.json", {"run_id": "run_b", "created_at": "invalid-ts"})
    _write_json(run_c / "manifest.json", {"run_id": "run_c"})

    worktree_root = api_main.load_config().worktree_root.resolve()
    inside = worktree_root / "run_a" / "task_1"
    outside = tmp_path / "outside" / "worktree"

    monkeypatch.setattr(
        api_main.worktree_manager,
        "list_worktrees",
        lambda: [
            "noise-before-worktree",
            f"worktree {inside}",
            "HEAD abc123",
            "branch refs/heads/main",
            "locked",
            f"worktree {outside}",
            "branch refs/heads/feature",
        ],
    )

    entries = api_main._load_worktrees()
    assert len(entries) == 2
    assert entries[0]["run_id"] == "run_a"
    assert entries[0]["task_id"] == "task_1"
    assert entries[0]["locked"] is True
    assert entries[1].get("run_id", "") == ""

    selected = api_main._select_baseline_by_window(
        "run_target",
        {"created_at": "2023-12-01T00:00:00Z", "finished_at": "2025-01-01T00:00:00Z"},
    )
    assert selected in {"run_a", "run_b", "run_c"}

    # invalid last line should return empty timestamp branch
    (run_a / "events.jsonl").write_text('{"ts":"2024-01-01T00:00:00Z"}\nnot-json\n', encoding="utf-8")
    assert api_main._last_event_ts("run_a") == ""


def test_api_workflow_and_replay_window_edge_cases(monkeypatch, tmp_path: Path) -> None:
    _, runs_root, _ = _setup_env(monkeypatch, tmp_path)

    run_ok = runs_root / "run_ok"
    run_bad = runs_root / "run_bad"
    run_no_wf = runs_root / "run_no_wf"
    run_empty_wf = runs_root / "run_empty_wf"

    _write_json(
        run_ok / "manifest.json",
        {
            "run_id": "run_ok",
            "task_id": "task_ok",
            "status": "RUNNING",
            "workflow": {"workflow_id": "wf-1", "status": "RUNNING", "task_queue": "q", "namespace": "n"},
            "created_at": "2024-01-02T00:00:00Z",
        },
    )
    _write_json(
        run_no_wf / "manifest.json",
        {"run_id": "run_no_wf", "task_id": "x", "status": "RUNNING", "created_at": "bad-ts"},
    )
    _write_json(
        run_empty_wf / "manifest.json",
        {"run_id": "run_empty_wf", "task_id": "x", "status": "RUNNING", "workflow": {"workflow_id": ""}},
    )
    run_bad.mkdir(parents=True, exist_ok=True)
    (run_bad / "manifest.json").write_text("{", encoding="utf-8")

    (run_ok / "events.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"event": "WORKFLOW_BOUND", "ts": "2024-01-02T00:00:01Z", "context": {"workflow_id": "wf-1"}}),
                json.dumps({"event": "TEMPORAL_NOTIFY_START", "_ts": "2024-01-02T00:00:02Z"}),
                json.dumps({"event": "OTHER", "context": "bad-context"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    workflows = api_main._collect_workflows()
    assert "wf-1" in workflows

    workflow = api_main.get_workflow("wf-1")
    assert workflow["workflow"]["workflow_id"] == "wf-1"
    assert workflow["events"]

    with pytest.raises(HTTPException):
        api_main.get_workflow("missing-workflow")

    with pytest.raises(HTTPException):
        api_main.replay_run("run_ok", {"baseline_window": "not-a-dict"})


def test_api_artifacts_promote_and_approvals_edge_cases(monkeypatch, tmp_path: Path) -> None:
    _, runs_root, _ = _setup_env(monkeypatch, tmp_path)

    run_id = "run_artifacts"
    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(run_dir / "manifest.json", {"run_id": run_id, "task_id": "task", "status": "RUNNING"})
    _write_json(run_dir / "contract.json", {"assigned_agent": {"agent_id": "worker-1", "role": "WORKER"}})

    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "records.jsonl").write_text('{"x":1}\nnot-json\n', encoding="utf-8")
    (artifacts / "trigger.json").write_text("trigger", encoding="utf-8")
    _write_json(artifacts / "search_results.json", {"results": [{"title": "r1"}]})

    reports = run_dir / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "review_report.json").write_text("not-json", encoding="utf-8")
    (reports / "test_report.json").write_text("not-json", encoding="utf-8")

    # jsonl invalid line path
    payload = api_main.get_artifacts(run_id, "records.jsonl")
    assert payload["data"][1]["raw"] == "not-json"

    # json decode generic error -> ARTIFACTS_READ_FAILED
    original_json_loads = api_main.json.loads

    def _faulty_json_loads(raw: str, *args, **kwargs):
        if raw == "trigger":
            raise RuntimeError("forced read failure")
        return original_json_loads(raw, *args, **kwargs)

    monkeypatch.setattr(api_main.json, "loads", _faulty_json_loads)
    with pytest.raises(HTTPException):
        api_main.get_artifacts(run_id, "trigger.json")

    # promote uses raw.results fallback branch
    promoted = api_main.promote_evidence(run_id)
    assert promoted["ok"] is True

    with pytest.raises(HTTPException):
        api_main.promote_evidence("missing-run")

    pending = api_main.list_pending_approvals()
    assert isinstance(pending, list)

    with pytest.raises(HTTPException) as exc_info:
        api_main.approve_god_mode({"x": 1})
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "RUN_ID_REQUIRED"
    (run_dir / "events.jsonl").write_text(json.dumps({"event": "HUMAN_APPROVAL_REQUIRED"}) + "\n", encoding="utf-8")
    approved = api_main.approve_god_mode({"run_id": run_id, "reason": "ok"})
    assert approved["ok"] is True

    # coverage for reviews/tests raw fallback
    reviews = api_main.list_reviews()
    tests = api_main.list_tests()
    assert reviews and "raw" in reviews[0]["report"]
    assert tests and "raw" in tests[0]["report"]


def test_read_events_incremental_reads_new_lines_only(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    run_id = "run_incremental"
    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    events_path = run_dir / "events.jsonl"
    events_path.write_text(
        "\n".join(
            [
                json.dumps({"event": "A", "ts": "2024-01-01T00:00:00Z"}),
                json.dumps({"event": "B", "ts": "2024-01-01T00:00:01Z"}),
                "not-json",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    initial, offset = main_state_store_helpers.read_events_incremental(
        run_id=run_id,
        runs_root=runs_root,
        offset=0,
        limit=2,
        filter_events_fn=api_main._filter_events,
    )
    assert [item.get("event") for item in initial] == ["A", "B"]
    assert offset > 0

    empty_delta, same_offset = main_state_store_helpers.read_events_incremental(
        run_id=run_id,
        runs_root=runs_root,
        offset=offset,
        filter_events_fn=api_main._filter_events,
    )
    assert empty_delta == []
    assert same_offset == offset

    with events_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"event": "C", "ts": "2024-01-01T00:00:02Z"}) + "\n")

    delta, offset_after_append = main_state_store_helpers.read_events_incremental(
        run_id=run_id,
        runs_root=runs_root,
        offset=offset,
        since="2024-01-01T00:00:01Z",
        filter_events_fn=api_main._filter_events,
    )
    assert [item.get("event") for item in delta] == ["C"]
    assert offset_after_append > offset


def test_ui_truth_gate_blocks_on_chain_or_tauri_failure_even_non_strict(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    script_path = repo_root / "scripts" / "ui_e2e_truth_gate.sh"
    matrix_path = tmp_path / "ui_matrix.md"
    p0_report = tmp_path / "p0_flake_report.json"
    p1_report = tmp_path / "p1_flake_report.json"
    chain_report = tmp_path / "chain_report.json"
    missing_tauri_report = tmp_path / "tauri_missing.json"
    out_report = tmp_path / "truth_gate.json"

    matrix_path.write_text(
        "\n".join(
            [
                "| id | name | tier | role | owner | status | note |",
                "|---|---|---|---|---|---|---|",
                "| btn-1 | command tower | P0 | ui | qa | COVERED | ok |",
                "| btn-2 | desktop shell | P1 | ui | qa | COVERED | ok |",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    p0_report.write_text(
        json.dumps({"gate_passed": True, "completed_all_attempts": True, "flake_rate_percent": 0.0}),
        encoding="utf-8",
    )
    p1_report.write_text(
        json.dumps({"gate_passed": True, "completed_all_attempts": True, "flake_rate_percent": 0.0}),
        encoding="utf-8",
    )
    chain_report.write_text(json.dumps({"overall_passed": False}), encoding="utf-8")

    env = dict(os.environ)
    env.update(
        {
            "OPENVIBECODING_UI_MATRIX_FILE": str(matrix_path),
            "OPENVIBECODING_UI_P0_REPORT": str(p0_report),
            "OPENVIBECODING_UI_P1_REPORT": str(p1_report),
            "OPENVIBECODING_UI_CHAIN_REPORT": str(chain_report),
            "OPENVIBECODING_UI_TAURI_REPORT": str(missing_tauri_report),
            "OPENVIBECODING_UI_TRUTH_GATE_REPORT": str(out_report),
            "OPENVIBECODING_UI_TRUTH_GATE_STRICT": "0",
        }
    )
    result = subprocess.run(
        ["bash", str(script_path)],
        cwd=repo_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, result.stderr

    report = json.loads(out_report.read_text(encoding="utf-8"))
    assert report["overall_passed"] is False
    assert report["checks"]["chain_integrity_passed"] is False
    assert report["checks"]["tauri_health_passed"] is False
    failure_checks = {item["check"] for item in report["failure_reasons"]}
    assert "chain_integrity_passed" in failure_checks
    assert "tauri_health_passed" in failure_checks


def _prepare_ui_truth_gate_baseline_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    matrix_path = tmp_path / "ui_matrix.md"
    p0_report = tmp_path / "p0_flake_report.json"
    p1_report = tmp_path / "p1_flake_report.json"
    run_id = "run-baseline"

    def _write_flake_report(path: Path) -> None:
        attempts_path = path.parent / f"{path.stem}.attempts.jsonl"
        attempts_path.write_text('{"attempt":1,"status":"passed"}\n', encoding="utf-8")
        attempts_sha256 = hashlib.sha256(attempts_path.read_bytes()).hexdigest()
        path.write_text(
            json.dumps(
                {
                    "report_type": "openvibecoding_ui_regression_flake_report",
                    "schema_version": 1,
                    "producer_script": "scripts/ui_regression_flake_gate.sh",
                    "run_id": run_id,
                    "gate_passed": True,
                    "completed_all_attempts": True,
                    "flake_rate_percent": 0.0,
                    "artifacts": {
                        "attempts_jsonl": str(attempts_path),
                        "attempts_sha256": attempts_sha256,
                    },
                }
            ),
            encoding="utf-8",
        )

    matrix_path.write_text(
        "\n".join(
            [
                "| id | name | tier | role | owner | status | note |",
                "|---|---|---|---|---|---|---|",
                "| btn-1 | command tower | P0 | ui | qa | COVERED | ok |",
                "| btn-2 | desktop shell | P1 | ui | qa | COVERED | ok |",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    _write_flake_report(p0_report)
    _write_flake_report(p1_report)
    return matrix_path, p0_report, p1_report


def test_ui_truth_gate_auto_click_inventory_does_not_block_when_not_required(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    script_path = repo_root / "scripts" / "ui_e2e_truth_gate.sh"
    matrix_path, p0_report, p1_report = _prepare_ui_truth_gate_baseline_inputs(tmp_path)
    out_report = tmp_path / "truth_gate.json"
    full_audit_root = tmp_path / "ui_full"
    click_inventory_report = full_audit_root / "failed_run" / "click_inventory_report.json"
    source_report = full_audit_root / "failed_run" / "report.json"
    click_inventory_report.parent.mkdir(parents=True, exist_ok=True)
    source_report.write_text(json.dumps({"run_id": "run-baseline"}), encoding="utf-8")
    click_inventory_report.write_text(
        json.dumps(
            {
                "source_report": str(source_report),
                "report_run_id": "run-baseline",
                "summary": {
                    "overall_passed": False,
                    "total_entries": 41,
                    "blocking_failures": 41,
                    "missing_target_ref_count": 41,
                },
                "inventory": [],
            }
        ),
        encoding="utf-8",
    )
    latest_manifest = tmp_path / "latest_manifest.json"
    latest_manifest.write_text(
        json.dumps(
            {
                "ui_regression": {
                    "p0_flake_report": {
                        "path": str(p0_report),
                        "status": "complete",
                        "run_id": "run-baseline",
                    },
                    "p1_flake_report": {
                        "path": str(p1_report),
                        "status": "complete",
                        "run_id": "run-baseline",
                    },
                },
                "ui_full_gemini_audit": {
                    "click_inventory_report": {
                        "path": str(click_inventory_report),
                        "status": "complete",
                        "run_id": "run-baseline",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    env = dict(os.environ)
    env.update(
        {
            "OPENVIBECODING_UI_MATRIX_FILE": str(matrix_path),
            "OPENVIBECODING_UI_FLAKE_REPORT_ROOT": str(tmp_path),
            "OPENVIBECODING_UI_P0_REPORT": str(p0_report),
            "OPENVIBECODING_UI_P1_REPORT": str(p1_report),
            "OPENVIBECODING_UI_TRUTH_GATE_REPORT": str(out_report),
            "OPENVIBECODING_UI_TRUTH_GATE_STRICT": "0",
            "OPENVIBECODING_UI_FULL_AUDIT_REPORT_ROOT": str(full_audit_root),
            "OPENVIBECODING_UI_LATEST_MANIFEST_PATH": str(latest_manifest),
            "OPENVIBECODING_UI_TRUTH_DISABLE_AUTO_LATEST": "0",
            "OPENVIBECODING_UI_TRUTH_BREAK_GLASS": "1",
            "OPENVIBECODING_UI_TRUTH_BREAK_GLASS_REASON": "test-auto-latest",
            "OPENVIBECODING_UI_TRUTH_BREAK_GLASS_TICKET": "TEST-UI-TRUTH-001",
        }
    )
    result = subprocess.run(
        ["bash", str(script_path)],
        cwd=repo_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    report = json.loads(out_report.read_text(encoding="utf-8"))
    assert report["overall_passed"] is True
    assert report["click_inventory_input_resolution"]["provided"] is True
    assert report["click_inventory_input_resolution"]["enforced"] is False
    assert "click_inventory_passed" not in report["checks"]
    assert report["break_glass"]["active"] is True


def test_ui_truth_gate_click_inventory_blocks_when_required(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    script_path = repo_root / "scripts" / "ui_e2e_truth_gate.sh"
    matrix_path, p0_report, p1_report = _prepare_ui_truth_gate_baseline_inputs(tmp_path)
    out_report = tmp_path / "truth_gate_required.json"
    full_audit_root = tmp_path / "ui_full"
    click_inventory_report = full_audit_root / "failed_run" / "click_inventory_report.json"
    source_report = full_audit_root / "failed_run" / "report.json"
    click_inventory_report.parent.mkdir(parents=True, exist_ok=True)
    source_report.write_text(json.dumps({"run_id": "run-baseline"}), encoding="utf-8")
    click_inventory_report.write_text(
        json.dumps(
            {
                "source_report": str(source_report),
                "report_run_id": "run-baseline",
                "summary": {
                    "overall_passed": False,
                    "total_entries": 41,
                    "blocking_failures": 41,
                    "missing_target_ref_count": 41,
                },
                "inventory": [],
            }
        ),
        encoding="utf-8",
    )

    env = dict(os.environ)
    env.update(
        {
            "OPENVIBECODING_UI_MATRIX_FILE": str(matrix_path),
            "OPENVIBECODING_UI_FLAKE_REPORT_ROOT": str(tmp_path),
            "OPENVIBECODING_UI_P0_REPORT": str(p0_report),
            "OPENVIBECODING_UI_P1_REPORT": str(p1_report),
            "OPENVIBECODING_UI_TRUTH_GATE_REPORT": str(out_report),
            "OPENVIBECODING_UI_TRUTH_GATE_STRICT": "1",
            "OPENVIBECODING_UI_FULL_AUDIT_REPORT_ROOT": str(full_audit_root),
            "OPENVIBECODING_UI_CLICK_INVENTORY_REQUIRED": "1",
        }
    )
    result = subprocess.run(
        ["bash", str(script_path)],
        cwd=repo_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, result.stderr

    report = json.loads(out_report.read_text(encoding="utf-8"))
    assert report["overall_passed"] is False
    assert report["click_inventory_input_resolution"]["enforced"] is True
    assert report["checks"]["click_inventory_passed"] is False
    failure_checks = {item["check"] for item in report["failure_reasons"]}
    assert "click_inventory_passed" in failure_checks


def test_ui_truth_gate_blocks_when_flake_policy_is_too_weak(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    script_path = repo_root / "scripts" / "ui_e2e_truth_gate.sh"
    matrix_path, p0_report, p1_report = _prepare_ui_truth_gate_baseline_inputs(tmp_path)
    out_report = tmp_path / "truth_gate_flake_policy.json"

    # Counterfactual setup: reports are "green" on gate_passed, but policy metadata is unsafe.
    p0_report.write_text(
        json.dumps(
            {
                "run_id": "run-policy",
                "gate_passed": True,
                "completed_all_attempts": True,
                "threshold_percent": 99,
                "iterations_per_command": 1,
            }
        ),
        encoding="utf-8",
    )
    p1_report.write_text(
        json.dumps(
            {
                "run_id": "run-policy",
                "gate_passed": True,
                "completed_all_attempts": True,
                "threshold_percent": 99,
                "iterations_per_command": 1,
            }
        ),
        encoding="utf-8",
    )

    env = dict(os.environ)
    env.update(
        {
            "OPENVIBECODING_UI_MATRIX_FILE": str(matrix_path),
            "OPENVIBECODING_UI_FLAKE_REPORT_ROOT": str(tmp_path),
            "OPENVIBECODING_UI_P0_REPORT": str(p0_report),
            "OPENVIBECODING_UI_P1_REPORT": str(p1_report),
            "OPENVIBECODING_UI_TRUTH_GATE_REPORT": str(out_report),
            "OPENVIBECODING_UI_TRUTH_GATE_STRICT": "1",
            "OPENVIBECODING_UI_TRUTH_ENFORCE_FLAKE_POLICY": "1",
            "OPENVIBECODING_UI_TRUTH_P0_MAX_THRESHOLD_PERCENT": "0.5",
            "OPENVIBECODING_UI_TRUTH_P1_MAX_THRESHOLD_PERCENT": "1.0",
            "OPENVIBECODING_UI_TRUTH_P0_MIN_ITERATIONS": "8",
            "OPENVIBECODING_UI_TRUTH_P1_MIN_ITERATIONS": "8",
            "OPENVIBECODING_UI_TRUTH_REQUIRE_RUN_ID_MATCH": "1",
        }
    )
    result = subprocess.run(
        ["bash", str(script_path)],
        cwd=repo_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, result.stderr

    report = json.loads(out_report.read_text(encoding="utf-8"))
    assert report["overall_passed"] is False
    assert report["checks"]["p0_flake_threshold_policy_ok"] is False
    assert report["checks"]["p1_flake_threshold_policy_ok"] is False
    assert report["checks"]["p0_flake_min_iterations_ok"] is False
    assert report["checks"]["p1_flake_min_iterations_ok"] is False
    failure_checks = {item["check"] for item in report["failure_reasons"]}
    assert "p0_flake_threshold_policy_ok" in failure_checks
    assert "p1_flake_threshold_policy_ok" in failure_checks
    assert "p0_flake_min_iterations_ok" in failure_checks
    assert "p1_flake_min_iterations_ok" in failure_checks
