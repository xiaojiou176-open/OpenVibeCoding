import json
import threading
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from openvibecoding_orch import cli
from openvibecoding_orch.cli import app


class _DummyConsole:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def print(self, message, _style=None) -> None:  # noqa: ANN001
        self.lines.append(str(message))


def test_cli_event_helpers_and_parser() -> None:
    assert cli._event_level({"level": "warning"}) == "WARN"
    assert cli._event_level({"level": "error"}) == "ERROR"
    assert cli._event_level({"level": "weird"}) == "INFO"

    assert cli._parse_event_line("{\"event\":\"X\"}") == {"event": "X"}
    assert cli._parse_event_line("not-json") is None

    context_text = cli._compact_context(
        {
            "context": {
                "task_id": "t1",
                "reason": "r" * 150,
                "status": "RUNNING",
                "path": "src/main.py",
                "attempt": 2,
            }
        }
    )
    assert "task_id=t1" in context_text
    assert "..." in context_text


def test_cli_format_and_tail_events(tmp_path: Path, monkeypatch) -> None:
    dummy_console = _DummyConsole()
    monkeypatch.setattr(cli, "console", dummy_console)

    pretty = cli._format_pretty_event(
        {
            "ts": "2024-01-01T00:00:00Z",
            "level": "INFO",
            "event": "TASK_STARTED",
            "context": {"task_id": "task_1", "status": "RUNNING"},
        }
    )
    assert "TASK_STARTED" in pretty
    assert "task=task_1" in pretty

    dummy_console.lines.clear()

    events_path = tmp_path / "events.jsonl"
    events_path.write_text(
        "\n".join(
            [
                json.dumps({"ts": "2024-01-01T00:00:00Z", "level": "INFO", "event": "A"}),
                json.dumps({"ts": "2024-01-01T00:00:01Z", "level": "WARN", "event": "B"}),
                "not-json",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    done = threading.Event()
    timer = threading.Timer(0.2, done.set)
    timer.start()
    cli._tail_events(events_path, done, idle_sec=0.01, tail_format="pretty", min_level="WARN")
    timer.cancel()

    assert any(" B task=" in line for line in dummy_console.lines)
    assert not any(" A task=" in line for line in dummy_console.lines)


def test_cli_wait_run_and_manifest_and_hooks(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)

    run_dir = runs_root / "run_1"
    run_dir.mkdir(parents=True, exist_ok=True)

    found = cli._wait_for_latest_run_id(runs_root, start_ts=time.time() - 1, timeout_sec=0.2)
    assert found == "run_1"

    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runtime_root / "runs"))

    run_manifest_dir = runtime_root / "runs" / "run_manifest"
    run_manifest_dir.mkdir(parents=True, exist_ok=True)
    (run_manifest_dir / "manifest.json").write_text("{", encoding="utf-8")
    assert cli._read_manifest_status("run_manifest") == "UNKNOWN"

    monkeypatch.setenv("OPENVIBECODING_HOOKS_AUTO_INSTALL", "yes")
    assert cli._hooks_auto_install_enabled() is True
    monkeypatch.setenv("OPENVIBECODING_HOOKS_AUTO_INSTALL", "0")
    assert cli._hooks_auto_install_enabled() is False

    repo_root = tmp_path / "repo"
    hooks_dir = repo_root / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    (hooks_dir / "pre-commit").write_text("allowed_paths_gate.sh", encoding="utf-8")
    (hooks_dir / "pre-push").write_text("allowed_paths_gate.sh", encoding="utf-8")
    assert cli._hooks_status(repo_root) is True

    (hooks_dir / "pre-push").write_text("other", encoding="utf-8")
    assert cli._hooks_status(repo_root) is False

    install_script = repo_root / "scripts" / "hooks" / "install.sh"
    install_script.parent.mkdir(parents=True, exist_ok=True)
    install_script.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    install_script.chmod(0o755)
    ok, _ = cli._install_hooks(repo_root)
    assert ok is True

    install_script.write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
    fail_ok, _ = cli._install_hooks(repo_root)
    assert fail_ok is False


def test_cli_cleanup_runtime_guard(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runtime_root / "runs"))

    runner = CliRunner()
    result = runner.invoke(app, ["cleanup", "runtime", "--dry-run", "--apply"])
    assert result.exit_code != 0
    assert "mutually exclusive" in result.output


def test_cli_temporal_worker_and_serve(monkeypatch) -> None:
    called: dict[str, object] = {}

    def _fake_run_worker() -> None:
        called["worker"] = True

    class _FakeTemporalWorkerModule:
        @staticmethod
        def run_worker() -> None:
            _fake_run_worker()

    monkeypatch.setitem(__import__("sys").modules, "openvibecoding_orch.temporal.worker", _FakeTemporalWorkerModule)

    def _fake_uvicorn_run(_app_obj, host: str, port: int, reload: bool) -> None:  # noqa: ANN001
        called["serve"] = {"host": host, "port": port, "reload": reload}

    monkeypatch.setattr(cli.uvicorn, "run", _fake_uvicorn_run)

    runner = CliRunner()

    worker_result = runner.invoke(app, ["temporal-worker"])
    assert worker_result.exit_code == 0
    assert called.get("worker") is True

    serve_result = runner.invoke(app, ["serve", "--host", "0.0.0.0", "--port", "9000"])
    assert serve_result.exit_code == 0
    assert called["serve"] == {"host": "0.0.0.0", "port": 9000, "reload": False}


@pytest.mark.parametrize(
    "tail_format,min_level,include_events,expected",
    [
        ("jsonl", "INFO", {"E1"}, True),
        ("pretty", "ERROR", None, False),
    ],
)
def test_tail_events_filter_matrix(
    tmp_path: Path,
    monkeypatch,
    tail_format: str,
    min_level: str,
    include_events: set[str] | None,
    expected: bool,
) -> None:
    dummy_console = _DummyConsole()
    monkeypatch.setattr(cli, "console", dummy_console)

    events_path = tmp_path / "events_filter.jsonl"
    events_path.write_text(json.dumps({"level": "INFO", "event": "E1"}) + "\n", encoding="utf-8")

    done = threading.Event()
    timer = threading.Timer(0.2, done.set)
    timer.start()
    cli._tail_events(
        events_path,
        done,
        idle_sec=0.01,
        tail_format=tail_format,
        min_level=min_level,
        include_events=include_events,
    )
    timer.cancel()

    assert (len(dummy_console.lines) > 0) is expected


def test_cli_run_follow_and_run_chain_follow(tmp_path: Path, monkeypatch) -> None:
    calls: dict[str, object] = {}

    class _FakeOrchestrator:
        def __init__(self, repo_root: Path) -> None:
            calls["repo_root"] = str(repo_root)

        def execute_task(self, contract_path: Path, mock_mode: bool = False) -> str:
            calls["execute_task"] = {"contract_path": str(contract_path), "mock_mode": mock_mode}
            return "run_follow_1"

        def execute_chain(self, chain_path: Path, mock_mode: bool = False) -> dict:
            calls["execute_chain"] = {"chain_path": str(chain_path), "mock_mode": mock_mode}
            return {"status": "SUCCESS", "chain_id": "chain_follow_1"}

    def _fake_tail_events(path: Path, done, idle_sec=1.0, tail_format="pretty", min_level="INFO", include_events=None):  # noqa: ANN001
        calls["tail"] = {
            "path": str(path),
            "tail_format": tail_format,
            "min_level": min_level,
            "include_events": sorted(include_events) if include_events else [],
            "done": done.is_set(),
        }

    monkeypatch.setattr(cli, "Orchestrator", _FakeOrchestrator)
    monkeypatch.setattr(cli, "_wait_for_latest_run_id", lambda runs_root, start_ts, timeout_sec=30.0: "run_follow_1")
    monkeypatch.setattr(cli, "_tail_events", _fake_tail_events)

    contract_path = tmp_path / "contract.json"
    contract_path.write_text("{}", encoding="utf-8")

    chain_path = tmp_path / "chain.json"
    chain_path.write_text("{}", encoding="utf-8")

    runner = CliRunner()

    run_result = runner.invoke(
        app,
        [
            "run",
            str(contract_path),
            "--mock",
            "--follow",
            "--tail-format",
            "jsonl",
            "--tail-level",
            "WARN",
            "--tail-event",
            "E1,E2",
        ],
    )
    assert run_result.exit_code == 0
    assert "run_id=run_follow_1" in run_result.output
    assert calls["execute_task"] == {"contract_path": str(contract_path.resolve()), "mock_mode": True}
    assert calls["tail"]["tail_format"] == "jsonl"
    assert calls["tail"]["min_level"] == "WARN"
    assert calls["tail"]["include_events"] == ["E1", "E2"]

    chain_result = runner.invoke(
        app,
        [
            "run-chain",
            str(chain_path),
            "--mock",
            "--follow",
            "--tail-format",
            "pretty",
            "--tail-level",
            "ERROR",
            "--tail-event",
            "CHAIN_DONE",
        ],
    )
    assert chain_result.exit_code == 0
    assert '"status": "SUCCESS"' in chain_result.output
    assert calls["execute_chain"] == {"chain_path": str(chain_path.resolve()), "mock_mode": True}
