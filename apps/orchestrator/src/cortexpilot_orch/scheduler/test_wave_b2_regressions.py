from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from cortexpilot_orch import cli
from cortexpilot_orch.scheduler.execute_task_pipeline import isolated_execution_env


def test_isolated_execution_env_restores_environment(monkeypatch) -> None:
    monkeypatch.setenv("CORTEXPILOT_RUN_ID", "before-run")
    monkeypatch.delenv("CODEX_HOME", raising=False)

    with isolated_execution_env():
        monkeypatch.setenv("CORTEXPILOT_RUN_ID", "during-run")
        monkeypatch.setenv("CODEX_HOME", "/tmp/codex-home")

    assert cli.os.environ.get("CORTEXPILOT_RUN_ID") == "before-run"
    assert "CODEX_HOME" not in cli.os.environ


def test_cli_force_unlock_scoped_to_allowed_paths(tmp_path: Path, monkeypatch) -> None:
    captured: list[list[str]] = []

    class _FakeValidator:
        def validate_contract_file(self, _path: Path) -> dict[str, object]:
            return {"allowed_paths": ["apps/orchestrator/src/cortexpilot_orch/scheduler/scheduler.py"]}

    class _FakeOrchestrator:
        def __init__(self, _repo_root: Path) -> None:
            pass

        def execute_task(self, _contract_path: Path, mock_mode: bool = False) -> str:
            assert mock_mode is True
            return "run_test"

    def _fake_release(paths):
        captured.append(list(paths))

    monkeypatch.setattr(cli, "ContractValidator", _FakeValidator)
    monkeypatch.setattr(cli, "Orchestrator", _FakeOrchestrator)
    monkeypatch.setattr(cli, "release_lock", _fake_release)

    contract_path = tmp_path / "contract.json"
    contract_path.write_text("{}", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(cli.app, ["run", str(contract_path), "--mock", "--force-unlock"])
    assert result.exit_code == 0
    assert captured == [["apps/orchestrator/src/cortexpilot_orch/scheduler/scheduler.py"]]


def test_cli_force_unlock_rejects_invalid_allowed_paths(tmp_path: Path, monkeypatch) -> None:
    class _FakeValidator:
        def validate_contract_file(self, _path: Path) -> dict[str, object]:
            return {"allowed_paths": "apps/orchestrator/src"}

    monkeypatch.setattr(cli, "ContractValidator", _FakeValidator)

    contract_path = tmp_path / "contract.json"
    contract_path.write_text("{}", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(cli.app, ["run", str(contract_path), "--mock", "--force-unlock"])
    assert result.exit_code != 0
    assert isinstance(result.exception, ValueError)
    assert "force unlock requires list[str] allowed_paths" in str(result.exception)
