import json
import os
from pathlib import Path

from typer.testing import CliRunner

from cortexpilot_orch import cli
from cortexpilot_orch.cli import app
from cortexpilot_orch.contract.validator import ContractValidator
from cortexpilot_orch.planning.coverage_chain import CoverageTarget, _assigned_role, build_coverage_self_heal_chain, load_coverage_targets


def _write_coverage_json(path: Path) -> None:
    payload = {
        "meta": {"version": "1"},
        "files": {
            "apps/orchestrator/src/cortexpilot_orch/runners/agents_runner.py": {
                "summary": {
                    "percent_covered": 81.2,
                    "percent_statements_covered": 82.1,
                    "percent_branches_covered": 72.0,
                }
            },
            "apps/orchestrator/src/cortexpilot_orch/scheduler/scheduler.py": {
                "summary": {
                    "percent_covered": 86.7,
                    "percent_statements_covered": 88.0,
                    "percent_branches_covered": 91.0,
                }
            },
            "apps/orchestrator/src/cortexpilot_orch/runners/codex_runner.py": {
                "summary": {
                    "percent_covered": 97.0,
                    "percent_statements_covered": 97.0,
                    "percent_branches_covered": 96.0,
                }
            },
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_coverage_json_many(path: Path) -> None:
    payload = {
        "meta": {"version": "1"},
        "files": {
            "apps/orchestrator/src/cortexpilot_orch/runners/agents_runner.py": {
                "summary": {
                    "percent_covered": 71.0,
                    "percent_statements_covered": 72.1,
                    "percent_branches_covered": 68.0,
                }
            },
            "apps/orchestrator/src/cortexpilot_orch/scheduler/scheduler.py": {
                "summary": {
                    "percent_covered": 73.0,
                    "percent_statements_covered": 74.0,
                    "percent_branches_covered": 69.0,
                }
            },
            "apps/orchestrator/src/cortexpilot_orch/chain/runner.py": {
                "summary": {
                    "percent_covered": 74.0,
                    "percent_statements_covered": 75.0,
                    "percent_branches_covered": 70.0,
                }
            },
            "apps/orchestrator/src/cortexpilot_orch/planning/intake.py": {
                "summary": {
                    "percent_covered": 75.0,
                    "percent_statements_covered": 76.0,
                    "percent_branches_covered": 71.0,
                }
            },
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_assigned_role_prefers_worker_for_coverage_self_heal_targets() -> None:
    assert _assigned_role("apps/orchestrator/src/cortexpilot_orch/api/routes_admin.py") == "WORKER"
    assert _assigned_role("apps/orchestrator/src/cortexpilot_orch/scheduler/scheduler.py") == "WORKER"


def test_worker_timeout_uses_env_override(monkeypatch) -> None:
    targets = [
        CoverageTarget(
            module_path="apps/orchestrator/src/cortexpilot_orch/api/routes_admin.py",
            module_name="cortexpilot_orch.api.routes_admin",
            coverage=50.0,
        )
    ]

    monkeypatch.setenv("CORTEXPILOT_COVERAGE_WORKER_TIMEOUT_SEC", "123")
    chain = build_coverage_self_heal_chain(targets, chain_id="task_chain_timeout_override")
    worker_step = next(step for step in chain["steps"] if step["name"] == "worker_cov_01")
    assert worker_step["payload"]["timeout_retry"]["timeout_sec"] == 123

    monkeypatch.setenv("CORTEXPILOT_COVERAGE_WORKER_TIMEOUT_SEC", "5")
    chain_min = build_coverage_self_heal_chain(targets, chain_id="task_chain_timeout_floor")
    worker_step_min = next(step for step in chain_min["steps"] if step["name"] == "worker_cov_01")
    assert worker_step_min["payload"]["timeout_retry"]["timeout_sec"] == 60


def test_coverage_targets_and_chain_schema_validation(tmp_path: Path) -> None:
    coverage_path = tmp_path / "coverage.json"
    _write_coverage_json(coverage_path)

    targets = load_coverage_targets(
        coverage_path,
        threshold=90.0,
        max_workers=2,
        coverage_metric="overall",
    )
    assert [item.module_name for item in targets] == [
        "cortexpilot_orch.runners.agents_runner",
        "cortexpilot_orch.scheduler.scheduler",
    ]

    branch_targets = load_coverage_targets(
        coverage_path,
        threshold=90.0,
        max_workers=3,
        coverage_metric="branches",
    )
    assert [item.module_name for item in branch_targets] == ["cortexpilot_orch.runners.agents_runner"]

    chain = build_coverage_self_heal_chain(
        targets,
        chain_id="task_chain_cov_test",
        coverage_metric="overall",
        enable_commit_stage=True,
        commit_message="test: coverage self-heal commit",
    )
    ContractValidator().validate_report(chain, "task_chain.v1.json")

    worker_steps = [step for step in chain["steps"] if step["name"].startswith("worker_cov_")]
    assert len(worker_steps) == 2
    assert all(step.get("parallel_group") == "coverage_workers" for step in worker_steps)
    assert chain["strategy"]["lifecycle"]["min_workers"] == 2
    worker_cmd = worker_steps[0]["payload"]["acceptance_tests"][0]["cmd"]
    assert worker_cmd.startswith("bash scripts/coverage_self_heal_verify_test.sh ")
    assert "apps/orchestrator/tests/self_heal/test_cov_" in worker_cmd
    required_output_names = [item["name"] for item in worker_steps[0]["payload"]["required_outputs"]]
    assert any(name.startswith("apps/orchestrator/tests/self_heal/test_cov_") for name in required_output_names)
    assert worker_steps[0]["payload"]["task_type"] == "TEST"
    assert all(path.startswith((".runtime-cache/test_output/worker_markers/self_heal/", "apps/orchestrator/tests/self_heal/test_cov_")) for path in worker_steps[0]["payload"]["allowed_paths"])
    assert "apps/orchestrator/tests/self_heal/" not in worker_steps[0]["payload"]["allowed_paths"]

    test_gate = next(step for step in chain["steps"] if step["name"] == "test_gate")
    gate_cmd = test_gate["payload"]["acceptance_tests"][0]["cmd"]
    assert gate_cmd.startswith("bash scripts/coverage_self_heal_gate.sh ")
    assert "test_cov_apps_orchestrator_src_cortexpilot_orch_runners_agents_runner.py" in gate_cmd
    assert "test_cov_apps_orchestrator_src_cortexpilot_orch_scheduler_scheduler.py" in gate_cmd
    assert "worker_cov_01" in test_gate["depends_on"]
    assert "review_a" in test_gate["depends_on"]
    assert test_gate["payload"]["tool_permissions"]["shell"] == "never"

    commit_step = next(step for step in chain["steps"] if step["name"] == "commit_changes")
    assert commit_step["payload"]["acceptance_tests"][0]["name"] == "commit-local"
    assert "scripts/coverage_self_heal_commit.sh" in commit_step["payload"]["acceptance_tests"][0]["cmd"]
    assert commit_step["payload"]["policy_pack"] == "medium"
    assert worker_steps[0]["payload"]["tool_permissions"]["shell"] == "never"
    assert worker_steps[0]["payload"]["tool_permissions"]["network"] == "deny"
    assert worker_steps[0]["payload"]["policy_pack"] == "medium"
    assert commit_step["payload"]["tool_permissions"]["shell"] == "never"
    tl_to_pm = next(step for step in chain["steps"] if step["name"] == "tl_to_pm")
    assert tl_to_pm["depends_on"] == ["commit_changes"]


def test_shell_permissions_switch_to_on_request_for_codex_runner(monkeypatch) -> None:
    targets = [
        CoverageTarget(
            module_path="apps/orchestrator/src/cortexpilot_orch/api/routes_admin.py",
            module_name="cortexpilot_orch.api.routes_admin",
            coverage=50.0,
        )
    ]

    monkeypatch.setenv("CORTEXPILOT_RUNNER", "codex")
    chain = build_coverage_self_heal_chain(
        targets,
        chain_id="task_chain_codex_shell_permissions",
        enable_commit_stage=True,
    )

    worker_step = next(step for step in chain["steps"] if step["name"] == "worker_cov_01")
    test_gate = next(step for step in chain["steps"] if step["name"] == "test_gate")
    commit_step = next(step for step in chain["steps"] if step["name"] == "commit_changes")

    assert worker_step["payload"]["tool_permissions"]["shell"] == "on-request"
    assert test_gate["payload"]["tool_permissions"]["shell"] == "on-request"
    assert commit_step["payload"]["tool_permissions"]["shell"] == "on-request"


def test_cli_coverage_self_heal_chain_build_and_execute(tmp_path: Path, monkeypatch) -> None:
    coverage_path = tmp_path / "coverage.json"
    _write_coverage_json(coverage_path)

    calls: dict[str, object] = {}

    class _FakeOrchestrator:
        def __init__(self, repo_root: Path) -> None:
            calls["repo_root"] = str(repo_root)

        def execute_chain(self, chain_path: Path, mock_mode: bool = False) -> dict:
            calls["execute_chain"] = {"path": str(chain_path), "mock": mock_mode}
            return {"run_id": "run_cov_chain_1", "status": "SUCCESS"}

    monkeypatch.setattr(cli, "Orchestrator", _FakeOrchestrator)
    monkeypatch.setattr(cli, "_repo_root", lambda: tmp_path)

    output_path = tmp_path / "contracts" / "tasks" / "task_chain_cov_cli.json"

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "coverage-self-heal-chain",
            "--coverage-json",
            str(coverage_path),
            "--coverage-metric",
            "overall",
            "--threshold",
            "90",
            "--max-workers",
            "2",
            "--chain-id",
            "task_chain_cov_cli",
            "--enable-commit-stage",
            "--output",
            str(output_path),
            "--execute",
            "--mock",
        ],
    )

    assert result.exit_code == 0
    assert output_path.exists()
    assert "run_cov_chain_1" in result.output
    assert calls["execute_chain"] == {"path": str(output_path), "mock": True}

    chain_payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert chain_payload["chain_id"] == "task_chain_cov_cli"
    test_gate = next(step for step in chain_payload["steps"] if step["name"] == "test_gate")
    assert test_gate["payload"]["acceptance_tests"][0]["cmd"] == "echo mock test gate passed"
    assert "worker_cov_01" in test_gate["depends_on"]
    worker_step = next(step for step in chain_payload["steps"] if step["name"] == "worker_cov_01")
    assert worker_step["payload"]["acceptance_tests"][0]["cmd"] == "echo worker ready"
    assert worker_step["payload"]["policy_pack"] == "medium"
    commit_step = next(step for step in chain_payload["steps"] if step["name"] == "commit_changes")
    assert commit_step["payload"]["acceptance_tests"][0]["name"] == "commit-local"
    assert "scripts/coverage_self_heal_commit.sh" in commit_step["payload"]["acceptance_tests"][0]["cmd"]
    assert commit_step["payload"]["policy_pack"] == "medium"


def test_cli_coverage_self_heal_chain_execute_fallback_to_equilibrium(tmp_path: Path, monkeypatch) -> None:
    coverage_path = tmp_path / "coverage.json"
    _write_coverage_json(coverage_path)

    calls: dict[str, object] = {}

    class _FakeOrchestrator:
        def __init__(self, repo_root: Path) -> None:
            calls["repo_root"] = str(repo_root)

        def execute_chain(self, chain_path: Path, mock_mode: bool = False) -> dict:
            calls["execute_chain"] = {"path": str(chain_path), "mock": mock_mode}
            calls["runner"] = os.getenv("CORTEXPILOT_RUNNER", "")
            calls["base_url"] = os.getenv("CORTEXPILOT_PROVIDER_BASE_URL", "")
            calls["lock_auto_cleanup"] = os.getenv("CORTEXPILOT_LOCK_AUTO_CLEANUP", "")
            calls["chain_exec_mode"] = os.getenv("CORTEXPILOT_CHAIN_EXEC_MODE", "")
            calls["chain_subprocess_timeout"] = os.getenv("CORTEXPILOT_CHAIN_SUBPROCESS_TIMEOUT_SEC", "")
            return {"run_id": "run_cov_chain_eq", "status": "SUCCESS"}

    monkeypatch.setattr(cli, "Orchestrator", _FakeOrchestrator)
    monkeypatch.setattr(cli, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(cli, "_equilibrium_healthcheck", lambda *_args, **_kwargs: True)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("CORTEXPILOT_PROVIDER_BASE_URL", raising=False)
    monkeypatch.delenv("CORTEXPILOT_RUNNER", raising=False)
    monkeypatch.delenv("CORTEXPILOT_LOCK_AUTO_CLEANUP", raising=False)
    monkeypatch.delenv("CORTEXPILOT_CHAIN_EXEC_MODE", raising=False)
    monkeypatch.delenv("CORTEXPILOT_CHAIN_SUBPROCESS_TIMEOUT_SEC", raising=False)
    monkeypatch.delenv("CORTEXPILOT_ALLOW_CODEX_EXEC", raising=False)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "coverage-self-heal-chain",
            "--coverage-json",
            str(coverage_path),
            "--coverage-metric",
            "overall",
            "--threshold",
            "90",
            "--max-workers",
            "2",
            "--chain-id",
            "task_chain_cov_cli_eq",
            "--execute",
        ],
    )

    assert result.exit_code == 0
    assert '"mode": "equilibrium_fallback"' in result.output
    assert calls["execute_chain"] == {
        "path": str(tmp_path / "contracts" / "tasks" / "task_chain_cov_cli_eq.json"),
        "mock": False,
    }
    assert calls["runner"] == ""
    assert calls["base_url"] == "http://127.0.0.1:1456/v1"
    assert calls["lock_auto_cleanup"] == "1"
    assert calls["chain_exec_mode"] == "subprocess"
    assert calls["chain_subprocess_timeout"] == "300"

    payload = json.loads((tmp_path / "contracts" / "tasks" / "task_chain_cov_cli_eq.json").read_text(encoding="utf-8"))
    test_gate = next(step for step in payload["steps"] if step["name"] == "test_gate")
    gate_cmd = test_gate["payload"]["acceptance_tests"][0]["cmd"]
    assert gate_cmd.startswith("bash scripts/coverage_self_heal_gate.sh ")


def test_build_coverage_self_heal_chain_worker_batching_groups() -> None:
    targets = [
        CoverageTarget(
            module_path=f"apps/orchestrator/src/cortexpilot_orch/module_{idx}.py",
            module_name=f"cortexpilot_orch.module_{idx}",
            coverage=70.0 + idx,
        )
        for idx in range(1, 5)
    ]

    chain = build_coverage_self_heal_chain(
        targets,
        chain_id="task_chain_cov_batching",
        coverage_metric="branches",
        worker_batch_size=2,
    )

    worker_steps = [step for step in chain["steps"] if step["name"].startswith("worker_cov_")]
    groups = [step["parallel_group"] for step in worker_steps]
    assert groups == [
        "coverage_workers_batch_01",
        "coverage_workers_batch_01",
        "coverage_workers_batch_02",
        "coverage_workers_batch_02",
    ]


def test_cli_coverage_self_heal_chain_execute_auto_batching_default(tmp_path: Path, monkeypatch) -> None:
    coverage_path = tmp_path / "coverage_many.json"
    _write_coverage_json_many(coverage_path)

    class _FakeOrchestrator:
        def __init__(self, repo_root: Path) -> None:
            self.repo_root = repo_root

        def execute_chain(self, chain_path: Path, mock_mode: bool = False) -> dict:
            return {"run_id": "run_cov_chain_auto_batch", "status": "SUCCESS"}

    monkeypatch.setattr(cli, "Orchestrator", _FakeOrchestrator)
    monkeypatch.setattr(cli, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(cli, "_equilibrium_healthcheck", lambda *_args, **_kwargs: False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("CORTEXPILOT_PROVIDER_BASE_URL", raising=False)
    monkeypatch.delenv("CORTEXPILOT_RUNNER", raising=False)
    monkeypatch.delenv("CORTEXPILOT_CHAIN_EXEC_MODE", raising=False)
    monkeypatch.delenv("CORTEXPILOT_CHAIN_SUBPROCESS_TIMEOUT_SEC", raising=False)
    monkeypatch.delenv("CORTEXPILOT_ALLOW_CODEX_EXEC", raising=False)

    output_path = tmp_path / "contracts" / "tasks" / "task_chain_cov_cli_auto_batch.json"
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "coverage-self-heal-chain",
            "--coverage-json",
            str(coverage_path),
            "--coverage-metric",
            "overall",
            "--threshold",
            "90",
            "--max-workers",
            "4",
            "--chain-id",
            "task_chain_cov_cli_auto_batch",
            "--output",
            str(output_path),
            "--execute",
        ],
    )

    assert result.exit_code == 0
    assert '"worker_batch_size": 2' in result.output
    assert '"worker_batch_source": "coverage_execute_default"' in result.output

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    worker_steps = [step for step in payload["steps"] if step["name"].startswith("worker_cov_")]
    worker_groups = [step["parallel_group"] for step in worker_steps]
    assert worker_groups == [
        "coverage_workers_batch_01",
        "coverage_workers_batch_01",
        "coverage_workers_batch_02",
        "coverage_workers_batch_02",
    ]


def test_cli_coverage_self_heal_chain_execute_with_codex_fallback(tmp_path: Path, monkeypatch) -> None:
    coverage_path = tmp_path / "coverage.json"
    _write_coverage_json(coverage_path)

    calls: dict[str, object] = {}

    class _FakeOrchestrator:
        def __init__(self, repo_root: Path) -> None:
            calls["repo_root"] = str(repo_root)

        def execute_chain(self, chain_path: Path, mock_mode: bool = False) -> dict:
            calls["execute_chain"] = {"path": str(chain_path), "mock": mock_mode}
            calls["runner"] = os.getenv("CORTEXPILOT_RUNNER", "")
            calls["base_url"] = os.getenv("CORTEXPILOT_PROVIDER_BASE_URL", "")
            calls["lock_auto_cleanup"] = os.getenv("CORTEXPILOT_LOCK_AUTO_CLEANUP", "")
            calls["chain_exec_mode"] = os.getenv("CORTEXPILOT_CHAIN_EXEC_MODE", "")
            calls["chain_subprocess_timeout"] = os.getenv("CORTEXPILOT_CHAIN_SUBPROCESS_TIMEOUT_SEC", "")
            calls["allow_codex_exec"] = os.getenv("CORTEXPILOT_ALLOW_CODEX_EXEC", "")
            return {"run_id": "run_cov_chain_codex", "status": "SUCCESS"}

    monkeypatch.setattr(cli, "Orchestrator", _FakeOrchestrator)
    monkeypatch.setattr(cli, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(cli, "_equilibrium_healthcheck", lambda *_args, **_kwargs: False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("CORTEXPILOT_PROVIDER_BASE_URL", raising=False)
    monkeypatch.delenv("CORTEXPILOT_RUNNER", raising=False)
    monkeypatch.delenv("CORTEXPILOT_LOCK_AUTO_CLEANUP", raising=False)
    monkeypatch.delenv("CORTEXPILOT_CHAIN_EXEC_MODE", raising=False)
    monkeypatch.delenv("CORTEXPILOT_CHAIN_SUBPROCESS_TIMEOUT_SEC", raising=False)
    monkeypatch.delenv("CORTEXPILOT_ALLOW_CODEX_EXEC", raising=False)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "coverage-self-heal-chain",
            "--coverage-json",
            str(coverage_path),
            "--coverage-metric",
            "overall",
            "--threshold",
            "90",
            "--max-workers",
            "2",
            "--chain-id",
            "task_chain_cov_cli_codex",
            "--execute",
        ],
    )

    assert result.exit_code == 0
    assert calls["execute_chain"] == {
        "path": str(tmp_path / "contracts" / "tasks" / "task_chain_cov_cli_codex.json"),
        "mock": False,
    }
    assert '"mode": "codex_runner_fallback"' in result.output
    assert calls["runner"] == "codex"
    assert calls["base_url"] == ""
    assert calls["lock_auto_cleanup"] == "1"
    assert calls["chain_exec_mode"] == "subprocess"
    assert calls["chain_subprocess_timeout"] == "300"
    assert calls["allow_codex_exec"] == "1"

    payload = json.loads((tmp_path / "contracts" / "tasks" / "task_chain_cov_cli_codex.json").read_text(encoding="utf-8"))
    test_gate = next(step for step in payload["steps"] if step["name"] == "test_gate")
    gate_cmd = test_gate["payload"]["acceptance_tests"][0]["cmd"]
    assert gate_cmd.startswith("bash scripts/coverage_self_heal_gate.sh ")


def test_cli_coverage_self_heal_chain_execute_prefers_gemini_key(tmp_path: Path, monkeypatch) -> None:
    coverage_path = tmp_path / "coverage.json"
    _write_coverage_json(coverage_path)

    calls: dict[str, object] = {}

    class _FakeOrchestrator:
        def __init__(self, repo_root: Path) -> None:
            calls["repo_root"] = str(repo_root)

        def execute_chain(self, chain_path: Path, mock_mode: bool = False) -> dict:
            calls["execute_chain"] = {"path": str(chain_path), "mock": mock_mode}
            calls["runner"] = os.getenv("CORTEXPILOT_RUNNER", "")
            calls["base_url"] = os.getenv("CORTEXPILOT_PROVIDER_BASE_URL", "")
            return {"run_id": "run_cov_chain_gemini", "status": "SUCCESS"}

    monkeypatch.setattr(cli, "Orchestrator", _FakeOrchestrator)
    monkeypatch.setattr(cli, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(cli, "_equilibrium_healthcheck", lambda *_args, **_kwargs: False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.delenv("CORTEXPILOT_PROVIDER_BASE_URL", raising=False)
    monkeypatch.delenv("CORTEXPILOT_RUNNER", raising=False)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "coverage-self-heal-chain",
            "--coverage-json",
            str(coverage_path),
            "--coverage-metric",
            "overall",
            "--threshold",
            "90",
            "--max-workers",
            "2",
            "--chain-id",
            "task_chain_cov_cli_gemini",
            "--execute",
        ],
    )

    assert result.exit_code == 0
    assert '"mode": "llm_key_present"' in result.output
    assert calls["execute_chain"] == {
        "path": str(tmp_path / "contracts" / "tasks" / "task_chain_cov_cli_gemini.json"),
        "mock": False,
    }
    assert calls["runner"] == ""
    assert calls["base_url"] == ""


def test_cli_coverage_self_heal_chain_execute_restores_temporary_env(monkeypatch, tmp_path: Path) -> None:
    coverage_path = tmp_path / "coverage.json"
    _write_coverage_json(coverage_path)

    observed: dict[str, str] = {}

    class _FakeOrchestrator:
        def __init__(self, repo_root: Path) -> None:
            observed["repo_root"] = str(repo_root)

        def execute_chain(self, chain_path: Path, mock_mode: bool = False) -> dict:
            del chain_path, mock_mode
            observed["runner_during_execute"] = os.getenv("CORTEXPILOT_RUNNER", "")
            return {"run_id": "run_cov_chain_env_restore", "status": "SUCCESS"}

    def _fake_prepare(mock_mode: bool) -> dict[str, object]:
        del mock_mode
        os.environ["CORTEXPILOT_RUNNER"] = "codex"
        return {"mode": "test_env_override"}

    def _fake_print(*_args, **_kwargs) -> None:
        observed["runner_at_print"] = os.getenv("CORTEXPILOT_RUNNER", "")

    monkeypatch.setattr(cli, "Orchestrator", _FakeOrchestrator)
    monkeypatch.setattr(cli, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(cli, "_prepare_coverage_execute_env", _fake_prepare)
    monkeypatch.setattr(cli.console, "print", _fake_print)
    monkeypatch.delenv("CORTEXPILOT_RUNNER", raising=False)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "coverage-self-heal-chain",
            "--coverage-json",
            str(coverage_path),
            "--coverage-metric",
            "overall",
            "--threshold",
            "90",
            "--max-workers",
            "2",
            "--chain-id",
            "task_chain_cov_cli_env_restore",
            "--execute",
        ],
    )

    assert result.exit_code == 0
    assert observed["runner_during_execute"] == "codex"
    assert observed["runner_at_print"] == ""
    assert os.getenv("CORTEXPILOT_RUNNER", "") == ""
