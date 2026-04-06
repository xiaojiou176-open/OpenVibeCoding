import json
import threading
import time
from pathlib import Path

from cortexpilot_orch import cli_runtime_helpers


class _Console:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def print(self, message: str) -> None:
        self.lines.append(str(message))


def test_wait_for_latest_run_id_fail_closed_matrix(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli_runtime_helpers.time, "sleep", lambda _seconds: None)

    missing_root = tmp_path / "missing"
    assert cli_runtime_helpers.wait_for_latest_run_id(missing_root, start_ts=time.time(), timeout_sec=0.01) == ""
    assert cli_runtime_helpers.wait_for_latest_run_id(missing_root, start_ts=time.time(), timeout_sec=0.0) == ""

    runs_root = tmp_path / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    (runs_root / "not-a-dir.txt").write_text("x", encoding="utf-8")

    old_run = runs_root / "run-old"
    old_run.mkdir(parents=True, exist_ok=True)
    old_ts = time.time() - 3600
    old_run.touch()
    old_run.chmod(0o755)
    import os

    os.utime(old_run, (old_ts, old_ts))
    assert cli_runtime_helpers.wait_for_latest_run_id(runs_root, start_ts=time.time(), timeout_sec=0.01) == ""

    bad_is_dir = runs_root / "run-bad-is-dir"
    bad_is_dir.mkdir(parents=True, exist_ok=True)
    original_stat = Path.stat
    stat_calls: dict[str, int] = {}

    def _patched_stat(self: Path, *args, **kwargs):  # type: ignore[override]
        if self.name == "run-bad-is-dir":
            stat_calls[self.name] = stat_calls.get(self.name, 0) + 1
            raise OSError("synthetic stat failure via is_dir()")
        return original_stat(self, *args, **kwargs)

    with monkeypatch.context() as scoped_patch:
        scoped_patch.setattr(Path, "stat", _patched_stat)
        try:
            result = cli_runtime_helpers.wait_for_latest_run_id(runs_root, start_ts=time.time(), timeout_sec=0.01)
        except OSError as exc:
            assert "synthetic stat failure via is_dir()" in str(exc)
            result = ""
    assert result == ""
    assert stat_calls.get("run-bad-is-dir", 0) >= 1
    os.utime(bad_is_dir, (old_ts, old_ts))

    bad_entry_stat = runs_root / "run-bad-entry-stat"
    bad_entry_stat.mkdir(parents=True, exist_ok=True)
    original_is_dir = Path.is_dir
    entry_stat_calls = 0

    def _patched_is_dir(self: Path) -> bool:  # type: ignore[override]
        if self.name == "run-bad-entry-stat":
            return True
        return original_is_dir(self)

    def _patched_stat_entry(self: Path, *args, **kwargs):  # type: ignore[override]
        nonlocal entry_stat_calls
        if self.name == "run-bad-entry-stat":
            entry_stat_calls += 1
            raise OSError("synthetic stat failure via entry.stat()")
        return original_stat(self, *args, **kwargs)

    with monkeypatch.context() as scoped_patch:
        scoped_patch.setattr(Path, "is_dir", _patched_is_dir)
        scoped_patch.setattr(Path, "stat", _patched_stat_entry)
        result = cli_runtime_helpers.wait_for_latest_run_id(runs_root, start_ts=time.time(), timeout_sec=0.01)
    assert result == ""
    assert entry_stat_calls >= 1


def test_repo_root_falls_back_to_source_anchor_when_cwd_is_deleted(monkeypatch) -> None:
    def _missing_cwd(_cls: type[Path]) -> Path:
        raise FileNotFoundError("cwd no longer exists")

    monkeypatch.setattr(Path, "cwd", classmethod(_missing_cwd))

    expected = Path(cli_runtime_helpers.__file__).resolve().parents[4]
    assert cli_runtime_helpers.repo_root() == expected


def test_parse_compact_and_format_event_branches() -> None:
    assert cli_runtime_helpers.parse_event_line("[]") is None

    compact = cli_runtime_helpers.compact_context(
        {
            "context": {"task_id": "task-1", "status": ["RUNNING"], "tool": {"name": "x"}},
            "meta": {"request_id": "req-1"},
        }
    )
    assert "status=[\"RUNNING\"]" in compact
    assert "tool={\"name\": \"x\"}" in compact

    pretty_naive = cli_runtime_helpers.format_pretty_event({"ts": "2024-01-01T00:00:00", "event": "E", "task_id": "t1"})
    assert "[2024-01-01 00:00:00]" in pretty_naive

    pretty_bad_ts = cli_runtime_helpers.format_pretty_event({"ts": "bad-ts", "event": "E2"})
    assert "[bad-ts]" in pretty_bad_ts

    pretty_no_ts = cli_runtime_helpers.format_pretty_event({"event_type": "E3"})
    assert "[-]" in pretty_no_ts


def test_tail_events_manifest_and_hooks_fail_closed(monkeypatch, tmp_path: Path) -> None:
    console = _Console()

    done_missing = threading.Event()
    timer_missing = threading.Timer(0.05, done_missing.set)
    timer_missing.start()
    cli_runtime_helpers.tail_events(
        tmp_path / "does-not-exist.jsonl",
        done_missing,
        console_obj=console,
        idle_sec=0.01,
        tail_format="pretty",
    )
    timer_missing.cancel()

    events_path = tmp_path / "events.jsonl"
    events_path.write_text(
        "\n".join(
            [
                "not-json",
                json.dumps({"level": "INFO", "event": "SKIP_ME"}),
                json.dumps({"level": "INFO", "event": "KEEP_ME", "task_id": "task-1"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    done = threading.Event()
    timer = threading.Timer(0.05, done.set)
    timer.start()
    cli_runtime_helpers.tail_events(
        events_path,
        done,
        console_obj=console,
        idle_sec=0.01,
        tail_format="jsonl",
        min_level="INFO",
        include_events={"KEEP_ME"},
    )
    timer.cancel()
    assert "not-json" in console.lines
    assert any("KEEP_ME" in line for line in console.lines)
    assert not any("SKIP_ME" in line for line in console.lines)

    runs_root = tmp_path / "runs"
    assert cli_runtime_helpers.read_manifest_status("missing", runs_root) == "UNKNOWN"
    run_dir = runs_root / "run-1"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text("{}", encoding="utf-8")
    assert cli_runtime_helpers.read_manifest_status("run-1", runs_root) == "UNKNOWN"

    ok, message = cli_runtime_helpers.install_hooks(tmp_path / "repo")
    assert ok is False
    assert "missing hook installer" in message

    repo_root = tmp_path / "repo-hooks"
    assert cli_runtime_helpers.hooks_status(repo_root) is False

    hooks_dir = repo_root / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    (hooks_dir / "pre-commit").write_text("allowed_paths_gate.sh", encoding="utf-8")
    assert cli_runtime_helpers.hooks_status(repo_root) is False

    (hooks_dir / "pre-push").write_text("allowed_paths_gate.sh", encoding="utf-8")
    original_read_text = Path.read_text

    def _patched_read_text(self: Path, *args, **kwargs):  # type: ignore[override]
        if self.name == "pre-push":
            raise OSError("cannot read hook")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _patched_read_text)
    assert cli_runtime_helpers.hooks_status(repo_root) is False
