from __future__ import annotations

import fnmatch
import hashlib
import os
import subprocess
from pathlib import Path

_CRITICAL_IGNORED_PATTERNS = (
    ".env",
    ".env.*",
    "*secret*",
    "*.pem",
    "*.key",
    "policies/*",
    "tooling/mcp/*",
    "apps/orchestrator/src/openvibecoding_orch/api/*",
    "apps/orchestrator/src/openvibecoding_orch/scheduler/*",
    "apps/orchestrator/src/openvibecoding_orch/runners/*",
)


def _git_status_porcelain(worktree: Path) -> list[str]:
    res = subprocess.run(
        ["git", "status", "--porcelain", "-z"],
        cwd=worktree,
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip() or "git status failed")
    return [line for line in res.stdout.split("\x00") if line]


def _git_ls_files(worktree: Path) -> list[str]:
    res = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=worktree,
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip() or "git ls-files failed")
    return [line for line in res.stdout.split("\x00") if line]


def _list_untracked(worktree: Path) -> list[str]:
    entries = _git_status_porcelain(worktree)
    paths = []
    for entry in entries:
        if entry.startswith("?? "):
            path = entry[3:]
            if path:
                paths.append(path)
    return paths


def _list_ignored_critical(worktree: Path) -> list[str]:
    res = subprocess.run(
        ["git", "status", "--ignored", "--porcelain", "-z", "-uall"],
        cwd=worktree,
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        stderr = (res.stderr or "").strip().lower()
        if "not a git repository" in stderr:
            return []
        raise RuntimeError(res.stderr.strip() or "git status --ignored failed")
    paths: list[str] = []
    for entry in [line for line in res.stdout.split("\x00") if line]:
        if not entry.startswith("!! "):
            continue
        path = entry[3:]
        if not path:
            continue
        if any(fnmatch.fnmatch(path, pattern) for pattern in _CRITICAL_IGNORED_PATTERNS):
            paths.append(path)
    return paths


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _snapshot_files(worktree: Path) -> dict[str, dict]:
    files = set(_git_ls_files(worktree))
    files.update(_list_untracked(worktree))
    files.update(_list_ignored_critical(worktree))
    snapshot: dict[str, dict] = {}
    for rel in sorted(files):
        target = worktree / rel
        try:
            stat = target.lstat()
        except FileNotFoundError:
            snapshot[rel] = {"missing": True}
            continue
        if target.is_dir():
            continue
        fingerprint = {
            "sha256": _hash_file(target),
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
        }
        snapshot[rel] = fingerprint
    return snapshot


def snapshot_worktree(worktree: Path) -> dict:
    return {"files": _snapshot_files(worktree)}


def validate_reviewer_isolation(worktree: Path, snapshot: dict) -> dict:
    before = snapshot.get("files", {}) if isinstance(snapshot, dict) else {}
    after = _snapshot_files(worktree)
    ok = before == after
    changed = []
    before_keys = set(before.keys())
    after_keys = set(after.keys())
    for path in sorted(before_keys | after_keys):
        if path not in before:
            changed.append({"path": path, "change": "added"})
            continue
        if path not in after:
            changed.append({"path": path, "change": "removed"})
            continue
        if before[path] != after[path]:
            changed.append({"path": path, "change": "modified"})
    payload = {
        "ok": ok,
        "before_count": len(before),
        "after_count": len(after),
        "changed": changed,
        "reason": "" if ok else "reviewer modified working tree",
    }
    verbose = os.getenv("OPENVIBECODING_REVIEWER_SNAPSHOT_VERBOSE", "").strip().lower() in {"1", "true", "yes"}
    if verbose:
        payload["before"] = before
        payload["after"] = after
    return payload
