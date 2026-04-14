import subprocess
from pathlib import Path

import pytest

from openvibecoding_orch.worktrees import manager as worktree_manager


def _init_repo(repo: Path) -> str:
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "tester"], cwd=repo, check=True, capture_output=True, text=True)
    (repo / "README.md").write_text("hello", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True, text=True)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()
    return sha


def test_worktree_manager_create_and_remove(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    baseline = _init_repo(repo)

    worktree_root = tmp_path / "worktrees"
    monkeypatch.setenv("OPENVIBECODING_WORKTREE_ROOT", str(worktree_root))
    monkeypatch.chdir(repo)

    worktree_path = worktree_manager.create_worktree("run-1", "task-1", baseline)
    assert worktree_path.exists()

    listed = worktree_manager.list_worktrees()
    assert any(str(worktree_path) in entry for entry in listed)

    worktree_manager.remove_worktree("run-1", "task-1")
    assert not worktree_path.exists()


def test_worktree_manager_error_paths() -> None:
    result = subprocess.CompletedProcess(["git"], 1, "", "boom")
    with pytest.raises(RuntimeError, match="git command failed"):
        worktree_manager._ensure_git_ok(result, ["git", "status"])


def test_worktree_manager_remove_branch_failure(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo_err"
    baseline = _init_repo(repo)
    monkeypatch.chdir(repo)

    def _fake_run_git(args, repo_root):
        if args[:2] == ["git", "branch"]:
            return subprocess.CompletedProcess(args, 1, "", "boom")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(worktree_manager, "_run_git", _fake_run_git)

    with pytest.raises(RuntimeError):
        worktree_manager.remove_worktree("missing", "task-1")


def test_worktree_manager_remove_branch_retries_after_prune_on_stale_metadata(
    tmp_path: Path, monkeypatch
) -> None:
    repo = tmp_path / "repo_retry"
    _init_repo(repo)
    monkeypatch.chdir(repo)

    calls: list[list[str]] = []

    def _fake_run_git(args, repo_root):
        calls.append(list(args))
        if args[:3] == ["git", "branch", "-D"]:
            branch_attempts = sum(1 for call in calls if call[:3] == ["git", "branch", "-D"])
            if branch_attempts == 1:
                return subprocess.CompletedProcess(
                    args,
                    128,
                    "",
                    "fatal: failed to read .git/worktrees/worker_frontend_01/commondir: No such file or directory\n",
                )
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(worktree_manager, "_run_git", _fake_run_git)

    worktree_manager.remove_worktree("missing", "task-1")

    prune_calls = [call for call in calls if call[:3] == ["git", "worktree", "prune"]]
    branch_calls = [call for call in calls if call[:3] == ["git", "branch", "-D"]]
    assert len(prune_calls) >= 2
    assert len(branch_calls) == 2
