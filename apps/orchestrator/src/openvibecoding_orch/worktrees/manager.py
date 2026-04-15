from __future__ import annotations

from contextlib import contextmanager
import re
import subprocess
import threading
from pathlib import Path

from openvibecoding_orch.config import load_config

try:
    import fcntl
except Exception:  # pragma: no cover - non-posix fallback
    fcntl = None


_PROCESS_LOCK_GUARD = threading.Lock()
_PROCESS_LOCKS: dict[str, threading.RLock] = {}


def _run_git(args: list[str], repo_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=repo_root,
        capture_output=True,
        text=True,
    )


def _ensure_git_ok(result: subprocess.CompletedProcess[str], cmd: list[str]) -> None:
    if result.returncode != 0:
        raise RuntimeError(f"git command failed: {' '.join(cmd)}\n{result.stderr}")


def _repo_root() -> Path:
    result = _run_git(["git", "rev-parse", "--show-toplevel"], Path("."))
    _ensure_git_ok(result, ["git", "rev-parse", "--show-toplevel"])
    return Path(result.stdout.strip())


def _process_lock_for(path: Path) -> threading.RLock:
    key = str(path.resolve(strict=False))
    with _PROCESS_LOCK_GUARD:
        lock = _PROCESS_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _PROCESS_LOCKS[key] = lock
        return lock


@contextmanager
def _worktree_file_lock(repo_root: Path):
    lock_path = repo_root / ".git" / "openvibecoding-worktrees.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    process_lock = _process_lock_for(lock_path)
    with process_lock:
        if fcntl is None:
            yield None
            return
        with lock_path.open("a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield lock_file
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _safe_segment(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    return cleaned or "task"


def _branch_name(run_id: str, task_id: str) -> str:
    safe_task = _safe_segment(task_id)
    return f"openvibecoding-run-{run_id}-{safe_task}"


def _is_stale_worktree_metadata_error(stderr: str) -> bool:
    normalized = str(stderr or "").lower()
    return "failed to read" in normalized and "/commondir" in normalized


def create_worktree(run_id: str, task_id: str, baseline_commit: str) -> Path:
    cfg = load_config()
    repo_root = _repo_root()
    with _worktree_file_lock(repo_root):
        prune = _run_git(["git", "worktree", "prune"], repo_root)
        _ensure_git_ok(prune, ["git", "worktree", "prune"])

        check = _run_git(["git", "cat-file", "-e", baseline_commit], repo_root)
        _ensure_git_ok(check, ["git", "cat-file", "-e", baseline_commit])

        safe_task = _safe_segment(task_id)
        worktree_path = cfg.worktree_root / run_id / safe_task
        worktree_path.parent.mkdir(parents=True, exist_ok=True)
        branch = _branch_name(run_id, task_id)

        cmd = [
            "git",
            "worktree",
            "add",
            "-b",
            branch,
            str(worktree_path),
            baseline_commit,
        ]
        result = _run_git(cmd, repo_root)
        _ensure_git_ok(result, cmd)
        return worktree_path


def remove_worktree(run_id: str, task_id: str) -> None:
    cfg = load_config()
    repo_root = _repo_root()
    with _worktree_file_lock(repo_root):
        safe_task = _safe_segment(task_id)
        worktree_path = cfg.worktree_root / run_id / safe_task
        branch = _branch_name(run_id, task_id)

        if worktree_path.exists():
            cmd_remove = ["git", "worktree", "remove", "--force", str(worktree_path)]
            result = _run_git(cmd_remove, repo_root)
            _ensure_git_ok(result, cmd_remove)

        prune = _run_git(["git", "worktree", "prune"], repo_root)
        _ensure_git_ok(prune, ["git", "worktree", "prune"])

        parent = worktree_path.parent
        if parent.exists() and parent.is_dir():
            try:
                parent.rmdir()
            except OSError:
                # Best-effort cleanup only; parent may still hold other task worktrees.
                pass

        cmd_branch = ["git", "branch", "-D", branch]
        result = _run_git(cmd_branch, repo_root)
        if result.returncode != 0 and _is_stale_worktree_metadata_error(result.stderr):
            prune = _run_git(["git", "worktree", "prune"], repo_root)
            _ensure_git_ok(prune, ["git", "worktree", "prune"])
            result = _run_git(cmd_branch, repo_root)
        if result.returncode != 0 and "not found" not in result.stderr:
            _ensure_git_ok(result, cmd_branch)


def list_worktrees() -> list[str]:
    repo_root = _repo_root()
    with _worktree_file_lock(repo_root):
        result = _run_git(["git", "worktree", "list", "--porcelain"], repo_root)
        _ensure_git_ok(result, ["git", "worktree", "list", "--porcelain"])
        return [line for line in result.stdout.splitlines() if line.startswith("worktree ")]
