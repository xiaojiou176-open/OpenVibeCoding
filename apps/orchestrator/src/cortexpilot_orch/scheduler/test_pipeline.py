from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any


def _resolve_safe_artifact_path(worktree_path: Path, rel_path: object) -> Path | None:
    if not isinstance(rel_path, str) or not rel_path.strip():
        return None
    rel = Path(rel_path.strip())
    if rel.is_absolute() or rel.drive:
        return None
    if any(part == ".." for part in rel.parts):
        return None
    base = worktree_path.resolve(strict=False)
    target = (base / rel).resolve(strict=False)
    try:
        target.relative_to(base)
    except ValueError:
        return None
    return target


def _open_parent_dir_fd(path: Path) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    return os.open(str(path), flags)


def _safe_read_text(path: Path) -> str:
    parent_fd: int | None = None
    file_fd: int | None = None
    try:
        parent_fd = _open_parent_dir_fd(path.parent)
        file_fd = os.open(
            path.name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_fd,
        )
        st = os.fstat(file_fd)
        if not stat.S_ISREG(st.st_mode):
            return ""
        with os.fdopen(file_fd, "r", encoding="utf-8") as handle:
            file_fd = None
            return handle.read()
    except (FileNotFoundError, NotADirectoryError, PermissionError, OSError, UnicodeDecodeError):
        return ""
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if parent_fd is not None:
            os.close(parent_fd)


def read_artifact_text(worktree_path: Path, artifact: object) -> str:
    if not isinstance(artifact, dict):
        return ""
    path = _resolve_safe_artifact_path(worktree_path, artifact.get("path"))
    if path is None:
        return ""
    return _safe_read_text(path)


def extract_test_logs(test_report: dict[str, Any], worktree_path: Path) -> tuple[str, str, str]:
    commands = test_report.get("commands")
    if not isinstance(commands, list) or not commands:
        return "", "", ""
    first = commands[0] if isinstance(commands[0], dict) else {}
    cmd_argv = first.get("cmd_argv") if isinstance(first, dict) else None
    cmd_str = " ".join(cmd_argv) if isinstance(cmd_argv, list) else ""
    stdout_text = read_artifact_text(worktree_path, first.get("stdout") if isinstance(first, dict) else None)
    stderr_text = read_artifact_text(worktree_path, first.get("stderr") if isinstance(first, dict) else None)
    return cmd_str, stdout_text, stderr_text


def cleanup_test_artifacts(test_report: dict[str, Any], worktree_path: Path) -> None:
    commands = test_report.get("commands")
    if not isinstance(commands, list):
        return
    for item in commands:
        if not isinstance(item, dict):
            continue
        for key in ("stdout", "stderr"):
            artifact = item.get(key)
            if not isinstance(artifact, dict):
                continue
            rel_path = artifact.get("path")
            target = _resolve_safe_artifact_path(worktree_path, rel_path)
            if target is None:
                continue
            parent_fd: int | None = None
            try:
                parent_fd = _open_parent_dir_fd(target.parent)
                st = os.stat(target.name, dir_fd=parent_fd, follow_symlinks=False)
                if not stat.S_ISREG(st.st_mode):
                    continue
                os.unlink(target.name, dir_fd=parent_fd)
            except (FileNotFoundError, NotADirectoryError, PermissionError, OSError):
                continue
            finally:
                if parent_fd is not None:
                    os.close(parent_fd)


def build_test_report_stub(
    run_id: str,
    task_id: str,
    attempt: int,
    started_at: str,
    finished_at: str,
    status: str,
    reason: str,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "run_id": run_id,
        "task_id": task_id,
        "attempt": attempt,
        "runner": {"role": "ORCHESTRATOR", "agent_id": "tests_gate"},
        "started_at": started_at,
        "finished_at": finished_at,
        "status": status,
        "commands": [],
        "artifacts": [],
    }
    if reason:
        report["failure"] = {"message": reason}
    return report


def build_review_report_stub(
    run_id: str,
    task_id: str,
    attempt: int,
    reviewed_at: str,
    verdict: str,
    reason: str,
) -> dict[str, Any]:
    violations = [reason] if reason else []
    report: dict[str, Any] = {
        "run_id": run_id,
        "task_id": task_id,
        "attempt": attempt,
        "reviewer": {"role": "REVIEWER", "agent_id": "reviewer"},
        "reviewed_at": reviewed_at,
        "verdict": verdict,
        "summary": reason or "review skipped",
        "scope_check": {"passed": False if violations else True, "violations": violations},
        "evidence": [],
        "produced_diff": False,
    }
    if reason:
        report["notes"] = reason
    return report
