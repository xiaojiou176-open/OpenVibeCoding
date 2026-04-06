from __future__ import annotations

import json
import os
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
import typer
from typer.testing import CliRunner

from cortexpilot_orch import cli, cli_command_helpers
from cortexpilot_orch.chain import runtime_helpers
from cortexpilot_orch.cli import app
from cortexpilot_orch.store.run_store import RunStore


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1B\[[0-?]*[ -/]*[@-~]", "", text)


def test_runtime_helpers_core_and_cache_branches(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    assert runtime_helpers.load_manifest(runs_root, "missing") == {}
    run_dir = runs_root / "run-1"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text(json.dumps({"status": "ok"}), encoding="utf-8")
    assert runtime_helpers.load_manifest(runs_root, "run-1")["status"] == "ok"

    payload = {"artifacts": "bad"}
    merged = runtime_helpers.merge_artifacts(payload, [{"name": "a"}])
    assert merged["artifacts"] == [{"name": "a"}]
    assert runtime_helpers.merge_artifacts(payload, []) is payload

    schema_root = tmp_path / "schemas"
    schema_root.mkdir(parents=True, exist_ok=True)
    schema_path = schema_root / "task.schema.json"
    schema_path.write_text(json.dumps({"properties": {"a": {}, "b": {}}}), encoding="utf-8")
    runtime_helpers._SCHEMA_KEYS_CACHE.clear()
    first = runtime_helpers.schema_allowed_keys(schema_root, "task.schema.json")
    schema_path.write_text(json.dumps({"properties": {"x": {}}}), encoding="utf-8")
    second = runtime_helpers.schema_allowed_keys(schema_root, "task.schema.json")
    assert first == {"a", "b"}
    assert second == {"a", "b"}

    deep_merged = runtime_helpers.deep_merge_payload(
        {"a": {"b": 1, "c": 2}, "d": 9},
        {"a": {"b": 3}, "e": 10},
    )
    assert deep_merged["a"] == {"b": 3, "c": 2}
    assert deep_merged["e"] == 10
    assert runtime_helpers.deep_merge_payload({"x": 1}, {}) == {"x": 1}

    assert runtime_helpers.filter_payload_keys({"a": 1, "b": 2}, set()) == {"a": 1, "b": 2}
    assert runtime_helpers.filter_payload_keys({"a": 1, "b": 2}, {"a"}) == {"a": 1}

    assert runtime_helpers.output_schema_name_for_role("reviewer") == "review_report.v1.json"
    assert runtime_helpers.output_schema_name_for_role("test") == "test_report.v1.json"
    assert runtime_helpers.output_schema_name_for_role("worker") == "agent_task_result.v1.json"
    assert runtime_helpers.output_schema_role_key("  ") == "worker"

    assert runtime_helpers.resolve_contract_from_dependency({"evidence_refs": {"contracts": [{}]}}, "bad") == {}
    assert runtime_helpers.resolve_contract_from_dependency({"evidence_refs": {"contracts": ["bad"]}}, 0) is None
    assert runtime_helpers.resolve_contract_from_dependency({"evidence_refs": {"contracts": [{}]}}, -1) is None
    assert runtime_helpers.resolve_contract_from_dependency({"evidence_refs": {"contracts": [{}]}}, 9) is None

    assert runtime_helpers.merge_contract_overrides({"a": 1}, None) == {"a": 1}
    assert runtime_helpers.merge_contract_overrides({"a": 1}, {"a": 2, "b": 3}) == {"a": 2, "b": 3}

    assert runtime_helpers.artifact_names("not-dict") == []
    assert runtime_helpers.artifact_names({"inputs": {"artifacts": [{"name": " x "}, {"name": ""}, "bad"]}}) == ["x"]


def test_runtime_helpers_dependency_and_fanin_normalization(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path / "runs")
    dep_run_id = store.create_run("dep_task")
    dep_dir = store._run_dir(dep_run_id)
    (dep_dir / "reports").mkdir(parents=True, exist_ok=True)
    (dep_dir / "reports" / "task_result.json").write_text("{\"ok\":true}", encoding="utf-8")
    (dep_dir / "patch.diff").write_text("diff --git a/a b/b", encoding="utf-8")

    dep_artifact = runtime_helpers.dependency_artifact(store, "dep", dep_run_id)
    dep_patch_artifact = runtime_helpers.dependency_patch_artifact(store, "dep", dep_run_id)
    assert dep_artifact is not None and dep_artifact["name"].endswith("task_result.json")
    assert dep_patch_artifact is not None and dep_patch_artifact["name"].endswith("patch.diff")
    assert runtime_helpers.dependency_artifact(store, "dep", "") is None
    assert runtime_helpers.dependency_patch_artifact(store, "dep", "") is None

    assert runtime_helpers.should_propagate_dependency_patch({"kind": "plan"}) is False
    assert runtime_helpers.should_propagate_dependency_patch(
        {"kind": "contract", "payload": {"assigned_agent": {"role": "REVIEWER"}, "task_type": "IMPLEMENT"}}
    ) is False
    assert runtime_helpers.should_propagate_dependency_patch(
        {"kind": "contract", "payload": {"assigned_agent": {"role": "WORKER"}, "task_type": "TEST"}}
    ) is False

    normalized = json.loads(runtime_helpers.normalize_fanin_summary(json.dumps(["issue-a"]), [" dep-1 ", ""]))
    assert normalized["stats"]["total"] == 1
    assert normalized["dependency_run_ids"] == ["dep-1"]

    normalized_empty = json.loads(
        runtime_helpers.normalize_fanin_summary(
            json.dumps({"dependency_run_ids": ["dep-2"], "inconsistencies": "bad"}),
            ["dep-fallback"],
        )
    )
    assert normalized_empty["inconsistencies"] == []
    assert normalized_empty["dependency_run_ids"] == ["dep-2"]

    normalized_from_artifact_run = store.create_run("fanin_step")
    normalized_from_artifact_dir = store._run_dir(normalized_from_artifact_run)
    (normalized_from_artifact_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    (normalized_from_artifact_dir / "artifacts" / "agent_task_result.json").write_text(
        json.dumps({"summary": "plain-summary", "evidence_refs": {}, "task_id": "fanin-task"}),
        encoding="utf-8",
    )
    chain_run_id = store.create_run("chain_parent")
    runtime_helpers.normalize_fanin_task_result(
        store,
        chain_run_id=chain_run_id,
        step_name="fan_in",
        step_run_id=normalized_from_artifact_run,
        dep_runs=[" dep-a ", "", "dep-b"],
    )
    saved_payload = json.loads(
        (store._run_dir(normalized_from_artifact_run) / "reports" / "task_result.json").read_text(
            encoding="utf-8"
        )
    )
    saved_summary = json.loads(saved_payload["summary"])
    assert saved_summary["dependency_run_ids"] == ["dep-a", "dep-b"]
    assert saved_payload["evidence_refs"]["dependency_run_ids"] == ["dep-a", "dep-b"]
    events_text = (store._run_dir(chain_run_id) / "events.jsonl").read_text(encoding="utf-8")
    assert "CHAIN_FANIN_SUMMARY_NORMALIZED" in events_text

    runtime_helpers.normalize_fanin_task_result(
        store,
        chain_run_id=chain_run_id,
        step_name="fan_in",
        step_run_id="",
        dep_runs=["dep-x"],
    )


def test_runtime_helpers_apply_context_policy_fail_closed_branches() -> None:
    contract = {"inputs": {"spec": "abcdef", "artifacts": [{"name": "raw_dump"}]}}
    updated, violations, truncations = runtime_helpers.apply_context_policy(
        contract,
        {
            "mode": "isolated",
            "allow_artifact_names": ["allowed_only"],
            "deny_artifact_substrings": "raw",
            "require_summary": True,
            "max_artifacts": "bad",
            "max_spec_chars": "bad",
        },
        owner_role="WORKER",
        step_name="step-a",
    )
    assert updated["inputs"]["artifacts"] == [{"name": "raw_dump"}]
    assert any("context isolated: artifacts must be empty" in item for item in violations)
    assert any("artifact not allowed: raw_dump" in item for item in violations)
    assert any("artifact denied by policy: raw_dump" in item for item in violations)
    assert any("summary required: raw_dump" in item for item in violations)
    assert truncations == []

    pm_contract = {"inputs": {"spec": "long-text", "artifacts": [{"name": "output_schema.worker"}]}}
    _, pm_violations, pm_truncations = runtime_helpers.apply_context_policy(
        pm_contract,
        {"mode": "inherit", "max_artifacts": 0, "max_spec_chars": 3},
        owner_role="PM",
        step_name="step-b",
    )
    assert any("requires dependency summary artifacts" in item for item in pm_violations)
    assert any("artifacts truncated to 0" in item for item in pm_truncations)
    assert any("spec truncated to 3 chars" in item for item in pm_truncations)

    _, unknown_mode_violations, _ = runtime_helpers.apply_context_policy(
        {"inputs": {"spec": "", "artifacts": []}},
        {"mode": "unexpected"},
        owner_role="WORKER",
        step_name="step-c",
    )
    assert any("unknown context_policy mode" in item for item in unknown_mode_violations)


def test_cli_wrapper_helpers_and_worker_batch_resolution(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli.cli_coverage_helpers, "equilibrium_healthcheck", lambda base_url, timeout_sec=1.5: base_url == "ok" and timeout_sec == 2.0)
    monkeypatch.setattr(cli.cli_coverage_helpers, "enable_lock_auto_cleanup_for_coverage", lambda: {"enabled": True})
    monkeypatch.setattr(cli.cli_coverage_helpers, "enable_chain_subprocess_timeout_for_coverage", lambda: {"mode": "subprocess"})
    monkeypatch.setattr(cli.cli_coverage_helpers, "ensure_coverage_python_env", lambda _root: {"python": "ok"})
    monkeypatch.setattr(cli, "_repo_root", lambda: tmp_path)

    assert cli._equilibrium_healthcheck("ok", timeout_sec=2.0) is True
    assert cli._enable_lock_auto_cleanup_for_coverage() == {"enabled": True}
    assert cli._enable_chain_subprocess_timeout_for_coverage() == {"mode": "subprocess"}
    assert cli._ensure_coverage_python_env() == {"python": "ok"}

    with pytest.raises(typer.BadParameter):
        cli._resolve_coverage_worker_batch_size(-1, execute=False, mock_mode=False)
    assert cli._resolve_coverage_worker_batch_size(3, execute=False, mock_mode=False) == (3, "cli")


def test_cli_force_unlock_fail_closed_and_env_restore(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    contract_path = tmp_path / "contract.json"
    contract_path.write_text("{}", encoding="utf-8")
    runner = CliRunner()

    class _BadValidatorListType:
        def validate_contract_file(self, _path: Path) -> dict:
            return {"allowed_paths": "bad"}

    monkeypatch.setattr(cli, "ContractValidator", lambda: _BadValidatorListType())
    bad_list_result = runner.invoke(app, ["run", str(contract_path), "--mock", "--force-unlock"])
    assert bad_list_result.exit_code != 0
    assert isinstance(bad_list_result.exception, ValueError)
    assert "force unlock requires list[str] allowed_paths" in str(bad_list_result.exception)

    class _BadValidatorEmptyList:
        def validate_contract_file(self, _path: Path) -> dict:
            return {"allowed_paths": ["", "  "]}

    monkeypatch.setattr(cli, "ContractValidator", lambda: _BadValidatorEmptyList())
    bad_empty_result = runner.invoke(app, ["run", str(contract_path), "--mock", "--force-unlock"])
    assert bad_empty_result.exit_code != 0
    assert isinstance(bad_empty_result.exception, ValueError)
    assert "force unlock requires non-empty allowed_paths" in str(bad_empty_result.exception)

    class _FakeOrchestrator:
        def __init__(self, _repo_root: Path) -> None:
            pass

        def execute_task(self, _contract_path: Path, mock_mode: bool = False) -> str:
            assert mock_mode is True
            return "run_env_restore"

    monkeypatch.setattr(cli, "Orchestrator", _FakeOrchestrator)
    monkeypatch.setenv("CORTEXPILOT_RUNNER", "previous-runner")
    monkeypatch.setenv("CORTEXPILOT_FORCE_UNLOCK", "previous-unlock")
    run_result = runner.invoke(app, ["run", str(contract_path), "--mock", "--runner", "codex"])
    assert run_result.exit_code == 0
    assert "run_id=run_env_restore" in run_result.output
    assert os.getenv("CORTEXPILOT_RUNNER") == "previous-runner"
    assert os.getenv("CORTEXPILOT_FORCE_UNLOCK") == "previous-unlock"


def test_cli_run_chain_restores_existing_force_unlock_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    chain_path = tmp_path / "chain.json"
    chain_path.write_text("{}", encoding="utf-8")
    runner = CliRunner()

    class _FakeOrchestrator:
        def __init__(self, _repo_root: Path) -> None:
            pass

        def execute_chain(self, _chain_path: Path, mock_mode: bool = False) -> dict:
            assert mock_mode is True
            return {"status": "SUCCESS"}

    monkeypatch.setattr(cli, "Orchestrator", _FakeOrchestrator)
    monkeypatch.setenv("CORTEXPILOT_FORCE_UNLOCK", "keep-me")
    result = runner.invoke(app, ["run-chain", str(chain_path), "--mock"])
    assert result.exit_code == 0
    assert os.getenv("CORTEXPILOT_FORCE_UNLOCK") == "keep-me"


def test_cli_coverage_self_heal_chain_fail_closed_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CliRunner()
    coverage_path = tmp_path / "coverage.json"
    coverage_path.write_text(json.dumps({"files": {}}), encoding="utf-8")
    monkeypatch.setattr(cli, "_repo_root", lambda: tmp_path)

    invalid_metric = runner.invoke(
        app,
        ["coverage-self-heal-chain", "--coverage-json", str(coverage_path), "--coverage-metric", "bad"],
    )
    assert invalid_metric.exit_code != 0
    invalid_metric_text = "\n".join(
        part
        for part in [
            invalid_metric.output,
            str(invalid_metric.exception) if invalid_metric.exception is not None else "",
        ]
        if part
    )
    normalized_invalid_metric_text = _strip_ansi(invalid_metric_text)
    assert "coverage-self-heal-chain" in normalized_invalid_metric_text
    assert "branches" in normalized_invalid_metric_text
    assert "statements" in normalized_invalid_metric_text
    assert "overall" in normalized_invalid_metric_text

    missing_no_refresh = runner.invoke(
        app,
        [
            "coverage-self-heal-chain",
            "--coverage-json",
            str(tmp_path / "missing.json"),
            "--no-auto-refresh-if-missing",
        ],
    )
    assert missing_no_refresh.exit_code != 0
    assert "coverage json not found" in missing_no_refresh.output

    refreshed: dict[str, bool] = {"called": False}

    def _fake_refresh(_repo_root: Path, out_path: Path) -> None:
        refreshed["called"] = True
        out_path.write_text(json.dumps({"files": {"x.py": {"summary": {"percent_branches_covered": 70}}}}), encoding="utf-8")

    monkeypatch.setattr(cli, "run_coverage_scan", _fake_refresh)
    monkeypatch.setattr(cli, "load_coverage_targets", lambda **_kwargs: [])
    no_targets = runner.invoke(
        app,
        [
            "coverage-self-heal-chain",
            "--coverage-json",
            str(tmp_path / "missing-needs-refresh.json"),
            "--refresh-coverage",
        ],
    )
    assert no_targets.exit_code == 1
    assert refreshed["called"] is True
    assert "no low coverage modules found under threshold" in no_targets.output


def test_cli_coverage_self_heal_chain_relative_output_no_execute(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CliRunner()
    coverage_path = tmp_path / "coverage.json"
    coverage_path.write_text(json.dumps({"files": {}}), encoding="utf-8")
    monkeypatch.setattr(cli, "_repo_root", lambda: tmp_path)

    fake_target = SimpleNamespace(module_name="mod.a", module_path="apps/orchestrator/src/mod/a.py", coverage=50.123)
    monkeypatch.setattr(cli, "load_coverage_targets", lambda **_kwargs: [fake_target])
    monkeypatch.setattr(cli, "build_coverage_self_heal_chain", lambda *args, **kwargs: {"chain_id": "chain-rel", "steps": []})

    captured_output_path: dict[str, str] = {}

    def _fake_write_chain(chain: dict[str, object], output_path: Path) -> Path:
        del chain
        captured_output_path["path"] = str(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("{}", encoding="utf-8")
        return output_path

    monkeypatch.setattr(cli, "write_chain", _fake_write_chain)
    result = runner.invoke(
        app,
        [
            "coverage-self-heal-chain",
            "--coverage-json",
            str(coverage_path),
            "--output",
            "contracts/relative-chain.json",
        ],
    )
    assert result.exit_code == 0
    assert captured_output_path["path"] == str(tmp_path / "contracts" / "relative-chain.json")
    assert '"coverage_refreshed": false' in result.output


def test_cli_command_helpers_additional_branches(tmp_path: Path) -> None:
    contract_path = tmp_path / "contract.json"
    contract_path.write_text("{}", encoding="utf-8")

    class _Validator:
        def validate_contract_file(self, _resolved_path: Path) -> dict:
            return {"task_id": "task-1", "owner_agent": "bad-type"}

    class _QueueStore:
        def __init__(self) -> None:
            self.calls: list[tuple] = []

        def enqueue(self, resolved_path: Path, task_id: str, owner: str = "") -> dict:
            self.calls.append((str(resolved_path), task_id, owner))
            return {"task_id": task_id, "owner": owner}

    queued = cli_command_helpers.enqueue_contract(
        contract_path,
        validator_cls=lambda: _Validator(),
        queue_store_cls=lambda: _QueueStore(),
    )
    assert queued["owner"] == ""

    class _RunQueueStore:
        def __init__(self, item: dict | None) -> None:
            self.item = item
            self.claimed: list[tuple[str, str]] = []
            self.done: list[tuple[str, str, str]] = []

        def next_pending(self) -> dict | None:
            return self.item

        def mark_claimed(self, task_id: str, run_id: str) -> None:
            self.claimed.append((task_id, run_id))

        def mark_done(self, task_id: str, run_id: str, status: str) -> None:
            self.done.append((task_id, run_id, status))

    class _Orchestrator:
        def __init__(self, _repo_root: Path) -> None:
            pass

        def execute_task(self, _contract_path: Path, mock_mode: bool = False) -> str:
            assert mock_mode is True
            return "run-next-1"

    store_with_item = _RunQueueStore({"contract_path": str(contract_path), "task_id": "task-1"})
    run_id = cli_command_helpers.run_next_task(
        mock=True,
        queue_store_cls=lambda: store_with_item,
        orchestrator_cls=_Orchestrator,
        repo_root=tmp_path,
        read_manifest_status_fn=lambda _rid: "SUCCESS",
    )
    assert run_id == "run-next-1"
    assert store_with_item.claimed == [("task-1", "")]
    assert store_with_item.done == [("task-1", "run-next-1", "SUCCESS")]

    store_empty = _RunQueueStore(None)
    assert (
        cli_command_helpers.run_next_task(
            mock=False,
            queue_store_cls=lambda: store_empty,
            orchestrator_cls=_Orchestrator,
            repo_root=tmp_path,
            read_manifest_status_fn=lambda _rid: "UNKNOWN",
        )
        is None
    )

    tail_calls: dict[str, int] = {"task": 0, "chain": 0}

    class _FollowOrchestrator:
        def execute_task(self, _contract_path: Path, mock_mode: bool = False) -> str:
            return "run-follow-task"

        def execute_chain(self, _chain_path: Path, mock_mode: bool = False) -> dict:
            return {"status": "SUCCESS", "run_id": "run-follow-chain"}

    task_follow = cli_command_helpers.execute_task_with_follow(
        orchestrator=_FollowOrchestrator(),
        contract_path=contract_path,
        mock=True,
        runs_root=tmp_path / "runs",
        tail_event="",
        tail_format="pretty",
        tail_level="INFO",
        wait_for_latest_run_id_fn=lambda _runs_root, _start_ts: "",
        tail_events_fn=lambda *args, **kwargs: tail_calls.__setitem__("task", tail_calls["task"] + 1),
    )
    assert task_follow == "run-follow-task"
    assert tail_calls["task"] == 0

    chain_follow = cli_command_helpers.execute_chain_with_follow(
        orchestrator=_FollowOrchestrator(),
        chain_path=tmp_path / "chain.json",
        mock=True,
        runs_root=tmp_path / "runs",
        tail_event="",
        tail_format="pretty",
        tail_level="INFO",
        wait_for_latest_run_id_fn=lambda _runs_root, _start_ts: "",
        tail_events_fn=lambda *args, **kwargs: tail_calls.__setitem__("chain", tail_calls["chain"] + 1),
    )
    assert chain_follow["status"] == "SUCCESS"
    assert tail_calls["chain"] == 0
