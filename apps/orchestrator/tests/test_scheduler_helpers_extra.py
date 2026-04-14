import json
import subprocess
import sys
from pathlib import Path

import pytest

from openvibecoding_orch.scheduler import scheduler as sched


def _git(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(["git", "init"], repo)
    _git(["git", "config", "user.email", "test@example.com"], repo)
    _git(["git", "config", "user.name", "tester"], repo)
    (repo / "README.md").write_text("hello", encoding="utf-8")
    _git(["git", "add", "README.md"], repo)
    _git(["git", "commit", "-m", "init"], repo)


def test_hash_events_filters_replay(tmp_path: Path) -> None:
    events = tmp_path / "events.jsonl"
    payloads = [
        json.dumps({"event": "REPLAY_START"}),
        "not-json",
        json.dumps({"event": "CUSTOM", "ts": "2024-01-01T00:00:00Z"}),
    ]
    events.write_text("\n".join(payloads) + "\n", encoding="utf-8")
    digest = sched._hash_events(events)
    assert digest


def test_git_helpers_error_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    with pytest.raises(RuntimeError):
        sched._git(["git", "definitely-not-a-command"], cwd=tmp_path)
    with pytest.raises(RuntimeError):
        sched._git_allow_nonzero(["git", "definitely-not-a-command"], cwd=tmp_path, allowed=(0,))


def test_collect_diff_text_untracked(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "new.txt").write_text("new", encoding="utf-8")
    diff_text = sched._collect_diff_text(repo)
    assert "new.txt" in diff_text


def test_collect_diff_text_ignores_runtime_artifacts(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "patch.diff").write_text("mock", encoding="utf-8")
    (repo / "diff_name_only.txt").write_text("mock", encoding="utf-8")
    diff_text = sched._collect_diff_text(repo)
    assert "patch.diff" not in diff_text
    assert "diff_name_only.txt" not in diff_text


def test_collect_diff_text_uses_no_index_path_separator(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: list[list[str]] = []

    def _fake_git(args: list[str], cwd: Path) -> str:
        if args[:3] == ["git", "status", "--porcelain"]:
            return "?? --danger.txt\n"
        return ""

    def _fake_git_allow_nonzero(args: list[str], cwd: Path, allowed: tuple[int, ...] = (0, 1)) -> str:
        captured.append(list(args))
        return ""

    monkeypatch.setattr(sched.runtime_utils, "git", _fake_git)
    monkeypatch.setattr(sched.runtime_utils, "git_allow_nonzero", _fake_git_allow_nonzero)

    sched._collect_diff_text(tmp_path)

    assert any(
        cmd[:6] == ["git", "diff", "--no-index", "/dev/null", "--", "--danger.txt"]
        for cmd in captured
    )


def test_apply_rollback_paths(tmp_path: Path, monkeypatch) -> None:
    unknown = sched._apply_rollback(tmp_path, {"strategy": "nope"})
    assert unknown["ok"] is False

    def _raise(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(sched.rollback_pipeline, "_git", _raise)
    result = sched._apply_rollback(tmp_path, {"strategy": "git_reset_hard", "baseline_ref": "HEAD"})
    assert result["ok"] is False
    assert "error" in result


def test_retry_config_values_are_clamped_non_negative() -> None:
    assert sched._max_retries({"timeout_retry": {"max_retries": -3}}) == 0
    assert sched._retry_backoff({"timeout_retry": {"retry_backoff_sec": -5}}) == 0
    assert sched._max_retries({"timeout_retry": {"max_retries": "2"}}) == 2
    assert sched._retry_backoff({"timeout_retry": {"retry_backoff_sec": "3"}}) == 3


def test_tool_version_success() -> None:
    version = sched._tool_version([sys.executable, "--version"])
    assert version != "unknown"
