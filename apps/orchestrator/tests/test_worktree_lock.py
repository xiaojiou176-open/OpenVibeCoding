import os
import subprocess
from pathlib import Path

from cortexpilot_orch.locks import locker
from cortexpilot_orch.worktrees import manager


def _git_output(args: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    return result.stdout


def _git(args: list[str], cwd: Path) -> None:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def _init_repo(repo: Path) -> None:
    _git(["git", "init"], cwd=repo)
    _git(["git", "config", "user.email", "test@example.com"], cwd=repo)
    _git(["git", "config", "user.name", "tester"], cwd=repo)


def test_worktree_create_and_remove(tmp_path: Path):
    os.environ["CORTEXPILOT_WORKTREE_ROOT"] = str(tmp_path)
    run_id = "run_test_worktree"
    task_id = "task-worktree"
    baseline = "HEAD"

    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    _init_repo(repo)
    (repo / "README.md").write_text("hello", encoding="utf-8")
    _git(["git", "add", "README.md"], cwd=repo)
    _git(["git", "commit", "-m", "init"], cwd=repo)

    cwd = Path.cwd()
    try:
        os.chdir(repo)
        path = manager.create_worktree(run_id, task_id, baseline)
        assert path.exists()

        worktree_list = _git_output(["git", "worktree", "list"], cwd=repo)
        assert str(path) in worktree_list

        manager.remove_worktree(run_id, task_id)
        worktree_list = _git_output(["git", "worktree", "list"], cwd=repo)
        assert str(path) not in worktree_list
    finally:
        os.chdir(cwd)


def test_locks_atomic(tmp_path: Path):
    os.environ["CORTEXPILOT_RUNTIME_ROOT"] = str(tmp_path)
    os.environ["CORTEXPILOT_RUN_ID"] = "run_a"
    target = ["src/main.py"]

    assert locker.acquire_lock(target) is True

    os.environ["CORTEXPILOT_RUN_ID"] = "run_b"
    assert locker.acquire_lock(target) is False

    locker.release_lock(target)
    assert locker.acquire_lock(target) is False
    os.environ["CORTEXPILOT_RUN_ID"] = "run_a"
    locker.release_lock(target)
    os.environ["CORTEXPILOT_RUN_ID"] = "run_b"
    assert locker.acquire_lock(target) is True
    locker.release_lock(target)
