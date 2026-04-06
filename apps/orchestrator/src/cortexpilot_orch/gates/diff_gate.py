from __future__ import annotations

import fnmatch
import os
import subprocess
from pathlib import Path
from typing import Iterable

from cortexpilot_orch.gates.path_match import is_allowed_path, normalize_path
from cortexpilot_orch.observability.tracer import trace_span


def _git(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def _normalize(path: str) -> str:
    return normalize_path(path)


def _is_allowed(path: str, allowed_paths: Iterable[str]) -> bool:
    return is_allowed_path(path, allowed_paths)


def _default_protected_paths() -> list[str]:
    raw = os.getenv("CORTEXPILOT_PROTECTED_PATHS", "")
    if raw.strip():
        return [item.strip() for item in raw.split(",") if item.strip()]
    return [".git/", ".gitignore", "pytest.ini", ".runtime-cache/cortexpilot/", ".env*"]


def _is_internal_memory_file(path: str) -> bool:
    name = Path(path.strip()).name
    if name in {".codex-memory.jsonl", "codex-memory.jsonl"}:
        return True
    if fnmatch.fnmatch(name, ".codex-memory.*.jsonl"):
        return True
    if fnmatch.fnmatch(name, ".codex-memory.*.jsonl.bak"):
        return True
    if fnmatch.fnmatch(name, "codex-memory.*.jsonl"):
        return True
    if fnmatch.fnmatch(name, "codex-memory.*.jsonl.bak"):
        return True
    return False


def _is_runtime_artifact_file(path: str) -> bool:
    normalized = _normalize(path).lstrip("./")
    if "/" in normalized:
        return False
    return normalized in {"patch.diff", "diff_name_only.txt", "mock_output.txt"}


def _is_protected(path: str, protected_paths: Iterable[str]) -> bool:
    target = _normalize(path)
    # Allow committed environment templates while still protecting real secrets.
    if target in {".env.example", "env.example"}:
        return False
    for raw in protected_paths:
        protected = _normalize(raw.rstrip("*"))
        if not protected:
            continue
        if raw.endswith("*") and target.startswith(protected):
            return True
        if target == protected:
            return True
        if target.startswith(protected.rstrip("/") + "/"):
            return True
    return False


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _split_z_output(output: str) -> list[str]:
    return [part for part in output.split("\0") if part]


def _parse_name_status(output: str) -> list[str]:
    parts = _split_z_output(output)
    paths: list[str] = []
    idx = 0
    while idx < len(parts):
        status = parts[idx]
        idx += 1
        if status.startswith("R") or status.startswith("C"):
            if idx + 1 >= len(parts):
                break
            old_path = parts[idx]
            new_path = parts[idx + 1]
            idx += 2
            paths.extend([old_path, new_path])
            continue
        if idx >= len(parts):
            break
        path = parts[idx]
        idx += 1
        paths.append(path)
    return paths


def _parse_raw(output: str) -> tuple[list[str], list[str]]:
    parts = _split_z_output(output)
    symlinks: list[str] = []
    submodules: list[str] = []
    idx = 0
    while idx < len(parts):
        header = parts[idx]
        idx += 1
        if not header.startswith(":"):
            continue
        header_fields = header.split()
        if len(header_fields) < 5:
            continue
        old_mode, new_mode, _, _, status = header_fields[:5]
        paths: list[str] = []
        if status.startswith("R") or status.startswith("C"):
            if idx + 1 >= len(parts):
                break
            paths.extend([parts[idx], parts[idx + 1]])
            idx += 2
        else:
            if idx >= len(parts):
                break
            paths.append(parts[idx])
            idx += 1
        if old_mode == "120000" or new_mode == "120000":
            symlinks.extend(paths)
        if old_mode == "160000" or new_mode == "160000":
            submodules.extend(paths)
    return symlinks, submodules


def _looks_like_numstat_value(value: str) -> bool:
    return value.isdigit() or value == "-"


def _parse_numstat(output: str) -> list[str]:
    parts = _split_z_output(output)
    binary_paths: list[str] = []
    idx = 0
    while idx + 2 < len(parts):
        insertions = parts[idx]
        deletions = parts[idx + 1]
        path = parts[idx + 2]
        idx += 3
        if insertions == "-" or deletions == "-":
            binary_paths.append(path)
        if idx < len(parts) and not _looks_like_numstat_value(parts[idx]):
            alt_path = parts[idx]
            idx += 1
            if insertions == "-" or deletions == "-":
                binary_paths.append(alt_path)
    return binary_paths


@trace_span("diff_gate.validate")
def validate_diff(
    worktree_path: Path,
    allowed_paths: list[str],
    baseline_ref: str = "HEAD",
    protected_paths: list[str] | None = None,
) -> dict:
    baseline = baseline_ref if isinstance(baseline_ref, str) and baseline_ref.strip() else "HEAD"

    name_res = _git(["git", "diff", "--name-status", "-z", baseline], cwd=worktree_path)
    if name_res.returncode != 0:
        return {
            "ok": False,
            "changed_files": [],
            "violations": [],
            "baseline_ref": baseline,
            "reason": name_res.stderr.strip() or "git diff failed",
        }

    raw_res = _git(["git", "diff", "--raw", "-z", baseline], cwd=worktree_path)
    if raw_res.returncode != 0:
        return {
            "ok": False,
            "changed_files": [],
            "violations": [],
            "baseline_ref": baseline,
            "reason": raw_res.stderr.strip() or "git diff raw failed",
        }

    numstat_res = _git(["git", "diff", "--numstat", "-z", baseline], cwd=worktree_path)
    if numstat_res.returncode != 0:
        return {
            "ok": False,
            "changed_files": [],
            "violations": [],
            "baseline_ref": baseline,
            "reason": numstat_res.stderr.strip() or "git diff numstat failed",
        }

    status_res = _git(["git", "status", "--porcelain", "-z", "-uall"], cwd=worktree_path)
    if status_res.returncode != 0:
        return {
            "ok": False,
            "changed_files": [],
            "violations": [],
            "baseline_ref": baseline,
            "reason": status_res.stderr.strip() or "git status failed",
        }

    diff_names = _parse_name_status(name_res.stdout)
    untracked = [
        entry[3:]
        for entry in _split_z_output(status_res.stdout)
        if entry.startswith("?? ")
    ]
    names = [
        n
        for n in diff_names + untracked
        if n and not _is_internal_memory_file(n) and not _is_runtime_artifact_file(n)
    ]

    protected = protected_paths if protected_paths is not None else _default_protected_paths()
    protected_hits = [n for n in names if _is_protected(n, protected)]
    if protected_hits:
        return {
            "ok": False,
            "changed_files": names,
            "violations": protected_hits,
            "baseline_ref": baseline,
            "reason": "protected files modified",
        }

    symlink_paths, submodule_paths = _parse_raw(raw_res.stdout)
    if symlink_paths:
        return {
            "ok": False,
            "changed_files": names,
            "violations": symlink_paths,
            "baseline_ref": baseline,
            "reason": "symlink changes are not allowed",
        }
    if submodule_paths:
        return {
            "ok": False,
            "changed_files": names,
            "violations": submodule_paths,
            "baseline_ref": baseline,
            "reason": "submodule changes are not allowed",
        }

    binary_paths = _parse_numstat(numstat_res.stdout)
    if binary_paths:
        return {
            "ok": False,
            "changed_files": names,
            "violations": binary_paths,
            "baseline_ref": baseline,
            "reason": "binary changes are not allowed",
        }

    violations: list[str] = []
    for name in names:
        candidate = (worktree_path / name).resolve()
        if not _is_within(candidate, worktree_path):
            violations.append(name)
            continue
        if not _is_allowed(name, allowed_paths):
            violations.append(name)

    if violations and names:
        normalized_allowed = [normalize_path(path) for path in allowed_paths if path]
        normalized_names = [normalize_path(name) for name in names]
        if normalized_allowed and all(name in normalized_allowed for name in normalized_names):
            violations = []
        else:
            def _prefix_allowed(target: str) -> bool:
                for allowed in normalized_allowed:
                    if not allowed:
                        continue
                    if target == allowed or target.startswith(allowed.rstrip("/") + "/"):
                        return True
                return False

            if normalized_allowed and all(_prefix_allowed(name) for name in normalized_names):
                violations = []

    ok = len(violations) == 0
    reason = "" if ok else "changed files outside allowed_paths"

    return {
        "ok": ok,
        "changed_files": names,
        "violations": violations,
        "baseline_ref": baseline,
        "reason": reason,
    }


def run_diff_gate(worktree: Path, allowed_paths: list[str], baseline_ref: str = "HEAD") -> dict:
    return validate_diff(worktree, allowed_paths, baseline_ref=baseline_ref)
