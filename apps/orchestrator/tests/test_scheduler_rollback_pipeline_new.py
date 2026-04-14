from __future__ import annotations

import subprocess
from pathlib import Path

from openvibecoding_orch.scheduler import rollback_pipeline


def test_timeout_retry_and_retry_helpers() -> None:
    assert rollback_pipeline.timeout_retry({"timeout_retry": {"max_retries": 2}}) == {"max_retries": 2}
    assert rollback_pipeline.timeout_retry({"timeout_retry": "bad"}) == {}

    assert rollback_pipeline.max_retries({"timeout_retry": {"max_retries": "3"}}) == 3
    assert rollback_pipeline.max_retries({"timeout_retry": {"max_retries": "bad"}}) == 0

    assert rollback_pipeline.retry_backoff({"timeout_retry": {"retry_backoff_sec": "4"}}) == 4
    assert rollback_pipeline.retry_backoff({"timeout_retry": {"retry_backoff_sec": "bad"}}) == 0


def test_apply_rollback_strategy_matrix(tmp_path: Path, monkeypatch) -> None:
    worktree = tmp_path

    missing = rollback_pipeline.apply_rollback(worktree, rollback=[])  # type: ignore[arg-type]
    assert missing["ok"] is False
    assert missing["reason"] == "rollback config missing"

    dropped = rollback_pipeline.apply_rollback(worktree, {"strategy": "worktree_drop", "baseline_ref": "abc"})
    assert dropped == {"ok": True, "strategy": "worktree_drop", "baseline_ref": "abc"}

    monkeypatch.setattr(rollback_pipeline, "_git", lambda args, cwd: "ok")
    reset_ok = rollback_pipeline.apply_rollback(worktree, {"strategy": "git_reset_hard", "baseline_ref": "base"})
    assert reset_ok["ok"] is True

    def _raise_git(*args, **kwargs):
        raise RuntimeError("git failed")

    monkeypatch.setattr(rollback_pipeline, "_git", _raise_git)
    reset_fail = rollback_pipeline.apply_rollback(worktree, {"strategy": "git_reset_hard", "baseline_ref": "base"})
    assert reset_fail["ok"] is False
    assert "git failed" in reset_fail["error"]

    monkeypatch.setattr(rollback_pipeline, "_git", lambda args, cwd: "ok")
    revert_ok = rollback_pipeline.apply_rollback(
        worktree,
        {"strategy": "git_revert_commit", "baseline_ref": "base", "target_ref": "target"},
    )
    assert revert_ok["ok"] is True
    assert revert_ok["target_ref"] == "target"

    monkeypatch.setattr(rollback_pipeline, "_git", _raise_git)
    revert_fail = rollback_pipeline.apply_rollback(
        worktree,
        {"strategy": "git_revert_commit", "baseline_ref": "base", "target_ref": "target"},
    )
    assert revert_fail["ok"] is False
    assert revert_fail["target_ref"] == "target"

    unknown = rollback_pipeline.apply_rollback(worktree, {"strategy": "unknown"})
    assert unknown["ok"] is False
    assert unknown["reason"] == "unknown rollback strategy"


def test_git_helper_success_and_failure(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        rollback_pipeline.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=args[0], returncode=0, stdout="  out  ", stderr=""),
    )
    assert rollback_pipeline._git(["git", "status"], cwd=tmp_path) == "out"

    monkeypatch.setattr(
        rollback_pipeline.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=args[0], returncode=1, stdout="", stderr="bad"),
    )
    try:
        rollback_pipeline._git(["git", "status"], cwd=tmp_path)
    except RuntimeError as exc:
        assert "bad" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected RuntimeError")


def test_scoped_revert_branches(tmp_path: Path, monkeypatch) -> None:
    worktree = tmp_path

    empty = rollback_pipeline.scoped_revert(worktree, [])
    assert empty == {"ok": True, "reverted": []}

    monkeypatch.setattr(
        rollback_pipeline.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=args[0], returncode=0, stdout=" done ", stderr=""),
    )
    ok = rollback_pipeline.scoped_revert(worktree, ["a.py"])
    assert ok["ok"] is True
    assert ok["stdout"] == "done"

    monkeypatch.setattr(
        rollback_pipeline.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=args[0], returncode=1, stdout="", stderr=" err "),
    )
    failed = rollback_pipeline.scoped_revert(worktree, ["b.py"])
    assert failed["ok"] is False
    assert failed["stderr"] == "err"

    def _raise(*args, **kwargs):
        raise OSError("explode")

    monkeypatch.setattr(rollback_pipeline.subprocess, "run", _raise)
    error = rollback_pipeline.scoped_revert(worktree, ["c.py"])
    assert error["ok"] is False
    assert "explode" in error["error"]
