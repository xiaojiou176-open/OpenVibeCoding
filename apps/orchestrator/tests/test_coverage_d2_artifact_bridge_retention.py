from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import cortexpilot_orch.config as config_module
from cortexpilot_orch.config import load_config
from cortexpilot_orch.runtime import retention as retention_module
from cortexpilot_orch.runtime.retention import RetentionPlan, apply_retention_plan, build_retention_plan
from cortexpilot_orch.scheduler import artifact_pipeline, scheduler_bridge_finalize as bridge_finalize
from cortexpilot_orch.store.run_store import RunStore


def _artifact_contract(name: str, uri: str) -> dict[str, Any]:
    return {"inputs": {"artifacts": [{"name": name, "uri": uri}]}}


def _touch_file(path: Path, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _touch_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _age(path: Path, *, days: int = 0) -> None:
    ts = (datetime.now(timezone.utc) - timedelta(days=days)).timestamp()
    os.utime(path, (ts, ts))


def test_artifact_pipeline_d2_branch_matrix(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    schema_root = tmp_path / "schemas"
    repo_root.mkdir()
    schema_root.mkdir()

    monkeypatch.setattr(artifact_pipeline.ContractValidator, "validate_report", lambda self, report, schema_name: None)

    ok, reason = artifact_pipeline.validate_assigned_agent(
        {
            "agents": [
                {"agent_id": "agent-1", "role": "REVIEWER"},
                {"agent_id": "agent-1", "role": "WORKER"},
            ]
        },
        {"agent_id": "agent-1", "role": "WORKER"},
    )
    assert ok is True
    assert reason == ""

    missing_abs_patch = tmp_path / "missing.diff"
    collected = artifact_pipeline.collect_patch_artifacts([{"name": "abs", "uri": str(missing_abs_patch)}], repo_root, repo_root)
    assert collected == []

    payload, error = artifact_pipeline.load_search_requests(
        {"inputs": {"artifacts": [{"name": "other.json", "uri": "ignored.json"}]}},
        repo_root,
        schema_root,
    )
    assert payload is None
    assert error is None

    payload, error = artifact_pipeline.load_search_requests(
        _artifact_contract("search_requests.json", str(repo_root / "missing_search.json")),
        repo_root,
        schema_root,
    )
    assert payload is None
    assert error == "artifact path invalid"

    search_empty_list = repo_root / "search_empty_list.json"
    search_empty_list.write_text("[]", encoding="utf-8")
    payload, error = artifact_pipeline.load_search_requests(
        _artifact_contract("search_requests.json", str(search_empty_list)),
        repo_root,
        schema_root,
    )
    assert payload is None
    assert error == "search queries empty"

    search_empty_queries = repo_root / "search_empty_queries.json"
    search_empty_queries.write_text(json.dumps({"queries": [" ", ""]}), encoding="utf-8")
    payload, error = artifact_pipeline.load_search_requests(
        _artifact_contract("search_queries.json", str(search_empty_queries)),
        repo_root,
        schema_root,
    )
    assert payload is None
    assert error == "search queries empty"

    search_ok = repo_root / "search_ok.json"
    search_ok.write_text(
        json.dumps(
            {
                "queries": ["query-1"],
                "providers": "chatgpt_web",
                "verify": {},
                "browser_policy": {"mode": "safe"},
            }
        ),
        encoding="utf-8",
    )
    payload, error = artifact_pipeline.load_search_requests(
        _artifact_contract("search_requests.json", str(search_ok)),
        repo_root,
        schema_root,
    )
    assert error is None
    assert payload == {
        "queries": ["query-1"],
        "repeat": 2,
        "parallel": 2,
        "providers": ["chatgpt_web"],
        "verify": {"providers": ["chatgpt_web"], "repeat": 2},
        "verify_ai": {"enabled": True},
        "browser_policy": {"mode": "safe"},
    }

    def _raise_schema(self: Any, report: dict[str, Any], schema_name: str) -> None:  # noqa: ARG001
        raise RuntimeError("schema fail")

    monkeypatch.setattr(artifact_pipeline.ContractValidator, "validate_report", _raise_schema)
    payload, error = artifact_pipeline.load_search_requests(
        _artifact_contract("search_requests.json", str(search_ok)),
        repo_root,
        schema_root,
    )
    assert payload is None
    assert error and error.startswith("search requests schema invalid")

    monkeypatch.setattr(artifact_pipeline.ContractValidator, "validate_report", lambda self, report, schema_name: None)

    payload, error = artifact_pipeline.load_browser_tasks(
        {"inputs": {"artifacts": [{"name": "not-browser.json", "uri": "noop.json"}]}},
        repo_root,
        schema_root,
    )
    assert payload is None
    assert error is None

    payload, error = artifact_pipeline.load_browser_tasks(
        _artifact_contract("browser_tasks.json", str(repo_root / "missing_browser.json")),
        repo_root,
        schema_root,
    )
    assert payload is None
    assert error == "artifact path invalid"

    browser_list = repo_root / "browser_list.json"
    browser_list.write_text(
        json.dumps(
            [
                {"url": "https://example.com", "script": 1, "browser_policy": {"stealth_mode": "none"}},
                "skip-me",
                {"url": "", "script": "ignored"},
            ]
        ),
        encoding="utf-8",
    )
    payload, error = artifact_pipeline.load_browser_tasks(
        _artifact_contract("browser_requests.json", str(browser_list)),
        repo_root,
        schema_root,
    )
    assert error is None
    assert payload == {
        "tasks": [
            {
                "url": "https://example.com",
                "script": "",
                "browser_policy": {"stealth_mode": "none"},
            }
        ]
    }

    payload, error = artifact_pipeline.load_tampermonkey_tasks(
        {"inputs": {"artifacts": [{"name": "not-tamper.json", "uri": "noop.json"}]}},
        repo_root,
        schema_root,
    )
    assert payload is None
    assert error is None

    payload, error = artifact_pipeline.load_tampermonkey_tasks(
        _artifact_contract("tampermonkey_tasks.json", str(repo_root / "missing_tamper.json")),
        repo_root,
        schema_root,
    )
    assert payload is None
    assert error == "artifact path invalid"

    tamper_list = repo_root / "tamper_list.json"
    tamper_list.write_text(
        json.dumps(
            [
                "skip-non-dict",
                {"name": "", "raw_output": "x"},
                {
                    "name": "script-a",
                    "script_content": "console.log('x')",
                    "browser_policy": {"profile_mode": "ephemeral"},
                },
            ]
        ),
        encoding="utf-8",
    )
    payload, error = artifact_pipeline.load_tampermonkey_tasks(
        _artifact_contract("tampermonkey_output.json", str(tamper_list)),
        repo_root,
        schema_root,
    )
    assert error is None
    assert payload == {
        "tasks": [
            {
                "script": "script-a",
                "raw_output": "",
                "parsed": None,
                "url": "",
                "script_content": "console.log('x')",
                "browser_policy": {"profile_mode": "ephemeral"},
            }
        ]
    }

    payload, error = artifact_pipeline.load_sampling_requests(
        {"inputs": {"artifacts": [{"name": "not-sampling.json", "uri": "noop.json"}]}},
        repo_root,
    )
    assert payload is None
    assert error is None

    payload, error = artifact_pipeline.load_sampling_requests(
        _artifact_contract("sampling_requests.json", str(repo_root / "missing_sampling.json")),
        repo_root,
    )
    assert payload is None
    assert error == "artifact path invalid"

    sampling_list = repo_root / "sampling_list.json"
    sampling_list.write_text(
        json.dumps(
            [
                "input-1",
                {"input": "input-2", "tool": "continue"},
                123,
            ]
        ),
        encoding="utf-8",
    )
    payload, error = artifact_pipeline.load_sampling_requests(
        _artifact_contract("sampling_tasks.json", str(sampling_list)),
        repo_root,
    )
    assert error is None
    assert payload is not None
    assert payload["requested_tools"] == ["sampling", "continue"]
    assert payload["requests"] == [
        {"input": "input-1"},
        {"id": "", "input": "input-2", "model": None, "tool": "continue"},
    ]


def test_scheduler_bridge_finalize_d2_schema_failures_and_skip_branches(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path / "runs")
    run_id = store.create_run("task-d2-bridge")

    class _SelectiveFailValidator:
        fail_schemas = {
            "test_report.v1.json",
            "review_report.v1.json",
            "task_result.v1.json",
            "work_report.v1.json",
            "evidence_report.v1.json",
        }

        def __init__(self, schema_root=None) -> None:  # noqa: ANN001
            self.schema_root = schema_root

        def validate_report(self, payload: dict[str, Any], schema_name: str) -> dict[str, Any]:
            if schema_name in self.fail_schemas:
                raise RuntimeError(f"{schema_name} failed")
            return payload

    gate_failures: list[dict[str, Any]] = []
    observed: dict[str, Any] = {}

    bridge_finalize.finalize_run(
        store=store,
        run_id=run_id,
        task_id="task-d2-bridge",
        status="SUCCESS",
        failure_reason="",
        manifest={"run_id": run_id, "task_id": "task-d2-bridge", "status": "RUNNING", "repo": "not-dict", "workflow": "not-dict"},
        attempt=1,
        start_ts="2026-03-01T00:00:00Z",
        tests_result=None,
        test_report=None,
        review_report=None,
        policy_gate_result=None,
        integrated_gate=None,
        network_gate=None,
        mcp_gate=None,
        sampling_gate=None,
        tool_gate=None,
        human_approval_required=False,
        human_approved=None,
        contract={"assigned_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": "fallback-thread"}},
        runner_summary="runner-summary",
        diff_gate_result={"ok": True},
        review_gate_result={"ok": True},
        baseline_ref="base-ref",
        head_ref="head-ref",
        search_request={"queries": ["already-executed"]},
        tamper_request=None,
        task_result={"evidence_refs": []},
        now_ts_fn=lambda: "2026-03-01T00:00:10Z",
        ensure_text_file_fn=lambda path: path.write_text("", encoding="utf-8"),
        contract_validator_cls=_SelectiveFailValidator,
        schema_root_fn=lambda: tmp_path,
        build_test_report_stub_fn=lambda *args: observed.setdefault("test_status", args[5]) or {"status": args[5]},
        build_review_report_stub_fn=lambda *args: {"verdict": args[4]},
        build_policy_gate_fn=lambda *_args, **_kwargs: {"ok": True},
        build_task_result_fn=lambda *_args, **_kwargs: {"status": "FAILED"},
        build_work_report_fn=lambda *_args, **_kwargs: {"status": "FAILED"},
        build_evidence_report_fn=lambda _run_dir, _extra=None: {"status": "ok"},
        append_gate_failed_fn=lambda _store, _rid, _gate, detail, **kwargs: gate_failures.append(
            {"detail": detail, "schema": kwargs.get("schema")}
        ),
        write_evidence_bundle_fn=lambda *_args, **_kwargs: observed.setdefault("write_evidence_bundle_called", True),
        manifest_task_role_fn=lambda _assigned: "WORKER",
        artifact_ref_from_path_fn=lambda name, *_args, **_kwargs: {"name": name},
        collect_evidence_hashes_fn=lambda _run_dir: {},
        artifact_refs_from_hashes_fn=lambda _run_dir, _hashes: [],
        write_manifest_fn=lambda store_obj, rid, data: store_obj.write_manifest(rid, data),
        notify_run_completed_fn=lambda _rid, _payload: {"ok": True},
    )

    manifest_path = store._runs_root / run_id / "manifest.json"
    written = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert observed["test_status"] == "SKIPPED"
    assert "failure_reason" in written
    assert written["status"] == "FAILURE"
    assert written["tasks"][0]["thread_id"] == "fallback-thread"
    assert {item["schema"] for item in gate_failures} == {
        "test_report.v1.json",
        "review_report.v1.json",
        "task_result.v1.json",
        "work_report.v1.json",
        "evidence_report.v1.json",
    }
    assert "write_evidence_bundle_called" not in observed


def test_scheduler_bridge_finalize_d2_prebuilt_reports_and_fallback_bundle(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path / "runs")
    run_id = store.create_run("task-d2-prebuilt")

    class _AlwaysValidValidator:
        def __init__(self, schema_root=None) -> None:  # noqa: ANN001
            self.schema_root = schema_root

        def validate_report(self, payload: dict[str, Any], schema_name: str) -> dict[str, Any]:
            return payload

    bridge_finalize.finalize_run(
        store=store,
        run_id=run_id,
        task_id="task-d2-prebuilt",
        status="SUCCESS",
        failure_reason="",
        manifest={"run_id": run_id, "task_id": "task-d2-prebuilt", "status": "RUNNING", "repo": {}, "workflow": {}},
        attempt=1,
        start_ts="2026-03-01T00:00:00Z",
        tests_result={"ok": True},
        test_report={"status": "PASS"},
        review_report={"verdict": "PASS"},
        policy_gate_result={"ok": True},
        integrated_gate=None,
        network_gate=None,
        mcp_gate=None,
        sampling_gate=None,
        tool_gate=None,
        human_approval_required=False,
        human_approved=None,
        contract={"assigned_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""}},
        runner_summary="runner-summary",
        diff_gate_result={"ok": True},
        review_gate_result={"ok": True},
        baseline_ref="base-ref",
        head_ref="head-ref",
        search_request=None,
        tamper_request=None,
        task_result={"evidence_refs": {"codex_thread_id": "thread-from-refs"}},
        now_ts_fn=lambda: "2026-03-01T00:00:10Z",
        ensure_text_file_fn=lambda path: path.write_text("", encoding="utf-8"),
        contract_validator_cls=_AlwaysValidValidator,
        schema_root_fn=lambda: tmp_path,
        build_test_report_stub_fn=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unexpected test stub")),
        build_review_report_stub_fn=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unexpected review stub")),
        build_policy_gate_fn=lambda *_args, **_kwargs: {"ok": True},
        build_task_result_fn=lambda *_args, **_kwargs: {"status": "SUCCESS"},
        build_work_report_fn=lambda *_args, **_kwargs: {"status": "SUCCESS"},
        build_evidence_report_fn=lambda _run_dir, _extra=None: {"status": "ok"},
        append_gate_failed_fn=lambda *_args, **_kwargs: None,
        write_evidence_bundle_fn=bridge_finalize.write_evidence_bundle,
        manifest_task_role_fn=lambda _assigned: "WORKER",
        artifact_ref_from_path_fn=lambda name, *_args, **_kwargs: {"name": name},
        collect_evidence_hashes_fn=lambda _run_dir: {"manifest.json": "sha256:abc"},
        artifact_refs_from_hashes_fn=lambda _run_dir, hashes: [{"path": key, "sha256": value} for key, value in hashes.items()],
        write_manifest_fn=lambda store_obj, rid, data: store_obj.write_manifest(rid, data),
        notify_run_completed_fn=lambda _rid, _payload: {"ok": True},
    )

    run_dir = store._runs_root / run_id
    assert not (run_dir / "reports" / "test_report.json").exists()
    assert not (run_dir / "reports" / "review_report.json").exists()
    evidence_bundle = json.loads((run_dir / "reports" / "evidence_bundle.json").read_text(encoding="utf-8"))
    query_payload = evidence_bundle["query"]
    if isinstance(query_payload, dict):
        assert query_payload["raw_question"] == "no search executed"
        assert query_payload["refined_prompt"] == "no search executed"
    else:
        assert query_payload == "no search executed"
        assert evidence_bundle["summary"] == "no search executed"
    assert evidence_bundle["limitations"] == ["no search executed"]

    before_reports = sorted((run_dir / "reports").glob("*.json"))
    bridge_finalize.write_evidence_bundle("run-unused", "q", "s", [], store=None)
    after_reports = sorted((run_dir / "reports").glob("*.json"))
    assert before_reports == after_reports


def test_scheduler_bridge_finalize_d2_execute_finalizer_without_lock_or_worktree(monkeypatch, tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path / "runs")
    run_id = store.create_run("task-d2-exec")
    calls = {"release": 0, "remove": 0, "finalize": 0}

    monkeypatch.setattr(bridge_finalize, "release_lock", lambda _allowed: calls.__setitem__("release", calls["release"] + 1))
    monkeypatch.setattr(
        bridge_finalize.worktree_manager,
        "remove_worktree",
        lambda _rid, _tid: calls.__setitem__("remove", calls["remove"] + 1),
    )
    monkeypatch.setattr(bridge_finalize, "finalize_run", lambda **_kwargs: calls.__setitem__("finalize", calls["finalize"] + 1))

    bridge_finalize.finalize_execute_task_run(
        store=store,
        run_id=run_id,
        task_id="task-d2-exec",
        locked=False,
        allowed_paths=[],
        worktree_path=None,
        status="SUCCESS",
        failure_reason="",
        manifest={"run_id": run_id},
        attempt=1,
        start_ts="2026-03-01T00:00:00Z",
        tests_result=None,
        test_report=None,
        review_report=None,
        policy_gate_result=None,
        integrated_gate=None,
        network_gate=None,
        mcp_gate=None,
        sampling_gate=None,
        tool_gate=None,
        human_approval_required=False,
        human_approved=None,
        contract={},
        runner_summary="summary",
        diff_gate_result=None,
        review_gate_result=None,
        baseline_ref="base",
        head_ref="head",
        search_request=None,
        tamper_request=None,
        task_result=None,
    )

    assert calls == {"release": 0, "remove": 0, "finalize": 1}


def test_retention_d2_namespace_contract_overflow_and_apply_edges(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    runtime_root = repo_root / ".runtime-cache" / "cortexpilot"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"
    logs_root = runtime_root / "logs"
    cache_root = runtime_root / "cache"
    contract_root = tmp_path / "contracts"

    monkeypatch.setenv("CORTEXPILOT_REPO_ROOT", str(repo_root))
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("CORTEXPILOT_WORKTREE_ROOT", str(worktree_root))
    monkeypatch.setenv("CORTEXPILOT_LOGS_ROOT", str(logs_root))
    monkeypatch.setenv("CORTEXPILOT_CACHE_ROOT", str(cache_root))
    monkeypatch.setenv("CORTEXPILOT_CONTRACT_ROOT", str(contract_root))
    monkeypatch.setenv("CORTEXPILOT_MACHINE_CACHE_ROOT", str(tmp_path / "machine-cache"))
    monkeypatch.setenv("CORTEXPILOT_RETENTION_RUN_DAYS", "30")
    monkeypatch.setenv("CORTEXPILOT_RETENTION_MAX_RUNS", "10")
    monkeypatch.setenv("CORTEXPILOT_RETENTION_LOG_DAYS", "30")
    monkeypatch.setenv("CORTEXPILOT_RETENTION_WORKTREE_DAYS", "30")
    monkeypatch.setenv("CORTEXPILOT_RETENTION_LOG_MAX_FILES", "10")
    monkeypatch.setenv("CORTEXPILOT_RETENTION_CACHE_HOURS", "48")
    monkeypatch.setenv("CORTEXPILOT_RETENTION_CODEX_HOME_DAYS", "30")
    monkeypatch.setenv("CORTEXPILOT_RETENTION_MAX_CODEX_HOMES", "1")
    monkeypatch.setenv("CORTEXPILOT_RETENTION_INTAKE_DAYS", "30")
    monkeypatch.setenv("CORTEXPILOT_RETENTION_MAX_INTAKES", "1")
    monkeypatch.delenv("CORTEXPILOT_ENV_FILE", raising=False)
    monkeypatch.delenv("CORTEXPILOT_PROVIDER", raising=False)
    monkeypatch.delenv("CORTEXPILOT_PROVIDER_BASE_URL", raising=False)
    monkeypatch.delenv("CORTEXPILOT_PROVIDER_MODEL", raising=False)
    config_module._ENV_LOADED = False
    config_module.reset_cached_config()
    cfg = load_config()

    out_of_scope_path = tmp_path / "outside-cache" / "a.bin"
    _touch_file(out_of_scope_path)
    assert retention_module._cache_namespace(out_of_scope_path, cache_root) == "__out_of_scope__"

    _touch_file(logs_root / "runtime" / "single.log")
    assert retention_module._overflow_log_candidates(logs_root, 1) == []

    _touch_dir(contract_root / "results" / "run_001")
    _touch_file(contract_root / "results" / "task-run-legacy.json")
    _touch_file(contract_root / "reviews" / "task-review-001.json")
    contract_items = retention_module._collect_contract_artifacts(contract_root)
    assert contract_root / "results" / "run_001" in contract_items
    assert contract_root / "reviews" / "task-review-001.json" in contract_items

    _touch_dir(runtime_root / "codex-homes" / "codex-old")
    _touch_dir(runtime_root / "codex-homes" / "codex-new")
    _touch_dir(runtime_root / "intakes" / "intake-old")
    _touch_dir(runtime_root / "intakes" / "intake-new")

    old_ts = (datetime.now(timezone.utc) - timedelta(days=2)).timestamp()
    new_ts = (datetime.now(timezone.utc) - timedelta(days=1)).timestamp()
    for path, ts in (
        (runtime_root / "codex-homes" / "codex-old", old_ts),
        (runtime_root / "codex-homes" / "codex-new", new_ts),
        (runtime_root / "intakes" / "intake-old", old_ts),
        (runtime_root / "intakes" / "intake-new", new_ts),
    ):
        os.utime(path, (ts, ts))

    plan = build_retention_plan(cfg)
    assert len(plan.codex_home_candidates) >= 1
    assert len(plan.intake_candidates) >= 1

    outside_root = tmp_path / "outside"
    _touch_dir(outside_root / "run-out")
    _touch_dir(outside_root / "wt-out")
    _touch_file(outside_root / "log-out.log")
    _touch_file(outside_root / "cache-out.bin")
    _touch_file(outside_root / "contract-out.json")

    inside_codex = runtime_root / "codex-homes" / "codex-remove"
    inside_intake = runtime_root / "intakes" / "intake-remove"
    _touch_dir(inside_codex)
    _touch_dir(inside_intake)

    manual_plan = RetentionPlan(
        run_candidates=[outside_root / "run-out"],
        worktree_candidates=[outside_root / "wt-out"],
        log_candidates=[outside_root / "log-out.log"],
        cache_candidates=[outside_root / "cache-out.bin"],
        codex_home_candidates=[inside_codex],
        intake_candidates=[inside_intake],
        contract_candidates=[outside_root / "contract-out.json"],
    )
    result = apply_retention_plan(cfg, manual_plan)
    assert result["removed"]["runs"] == []
    assert result["removed"]["worktrees"] == []
    assert result["removed"]["logs"] == []
    assert result["removed"]["cache"] == []
    assert result["removed"]["contracts"] == []
    assert result["removed"]["codex_homes"] == [str(inside_codex)]
    assert result["removed"]["intakes"] == [str(inside_intake)]
