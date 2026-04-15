import os
import subprocess
import threading
import time
from pathlib import Path

from openvibecoding_orch.locks import locker
from openvibecoding_orch.worktrees import manager


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
    os.environ["OPENVIBECODING_WORKTREE_ROOT"] = str(tmp_path)
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
    os.environ["OPENVIBECODING_RUNTIME_ROOT"] = str(tmp_path)
    os.environ["OPENVIBECODING_RUN_ID"] = "run_a"
    target = ["src/main.py"]

    assert locker.acquire_lock(target) is True

    os.environ["OPENVIBECODING_RUN_ID"] = "run_b"
    assert locker.acquire_lock(target) is False

    locker.release_lock(target)
    assert locker.acquire_lock(target) is False
    os.environ["OPENVIBECODING_RUN_ID"] = "run_a"
    locker.release_lock(target)
    os.environ["OPENVIBECODING_RUN_ID"] = "run_b"
    assert locker.acquire_lock(target) is True
    locker.release_lock(target)


def test_worktree_create_serializes_parallel_mutations(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo_lock"
    repo.mkdir(parents=True)
    _init_repo(repo)
    (repo / "README.md").write_text("hello", encoding="utf-8")
    _git(["git", "add", "README.md"], cwd=repo)
    _git(["git", "commit", "-m", "init"], cwd=repo)
    baseline = _git_output(["git", "rev-parse", "HEAD"], cwd=repo).strip()

    os.environ["OPENVIBECODING_WORKTREE_ROOT"] = str(tmp_path / "worktrees")
    cwd = Path.cwd()
    active_mutation_calls = 0
    overlap_detected = False
    call_guard = threading.Lock()

    def _fake_run_git(args: list[str], repo_root: Path):
        nonlocal active_mutation_calls, overlap_detected
        if args[:3] == ["git", "rev-parse", "--show-toplevel"]:
            return subprocess.CompletedProcess(args, 0, str(repo) + "\n", "")
        if args[:3] == ["git", "cat-file", "-e"]:
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[:3] == ["git", "worktree", "prune"] or args[:3] == ["git", "worktree", "add"]:
            with call_guard:
                active_mutation_calls += 1
                if active_mutation_calls > 1:
                    overlap_detected = True
            try:
                time.sleep(0.05)
                if args[:3] == ["git", "worktree", "add"]:
                    Path(args[5]).mkdir(parents=True, exist_ok=True)
                return subprocess.CompletedProcess(args, 0, "", "")
            finally:
                with call_guard:
                    active_mutation_calls -= 1
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(manager, "_run_git", _fake_run_git)

    try:
        os.chdir(repo)
        threads = [
            threading.Thread(target=manager.create_worktree, args=("run-a", "worker_core_01", baseline)),
            threading.Thread(target=manager.create_worktree, args=("run-b", "worker_frontend_01", baseline)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    finally:
        os.chdir(cwd)

    assert overlap_detected is False
