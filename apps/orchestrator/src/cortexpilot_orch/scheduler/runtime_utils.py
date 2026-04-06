from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from cortexpilot_orch.store.run_store import RunStore


def git(args: list[str], cwd: Path) -> str:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout.strip()


def git_allow_nonzero(args: list[str], cwd: Path, allowed: tuple[int, ...] = (0, 1)) -> str:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if result.returncode not in allowed:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout


def _is_runtime_artifact_untracked(path: str) -> bool:
    normalized = path.strip().replace("\\", "/").lstrip("./")
    if "/" in normalized:
        return False
    return normalized in {"patch.diff", "diff_name_only.txt", "mock_output.txt"}


def collect_diff_text(worktree_path: Path) -> str:
    base = git_allow_nonzero(["git", "diff"], cwd=worktree_path)
    status = git(["git", "status", "--porcelain", "-uall"], cwd=worktree_path)
    untracked = [
        line[3:]
        for line in status.splitlines()
        if line.startswith("?? ") and not _is_runtime_artifact_untracked(line[3:])
    ]
    if not untracked:
        if base and not base.endswith("\n"):
            base += "\n"
        return base
    chunks = [base] if base else []
    for rel in untracked:
        rel = rel.strip()
        if not rel:
            continue
        diff = git_allow_nonzero(["git", "diff", "--no-index", "/dev/null", "--", rel], cwd=worktree_path)
        if diff.strip():
            chunks.append(diff)
    text = "\n".join(chunks)
    if text and not text.endswith("\n"):
        text += "\n"
    return text


def baseline_commit(repo_root: Path) -> str:
    return git(["git", "rev-parse", "HEAD"], cwd=repo_root)


def tool_version(cmd: list[str]) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return (result.stdout or result.stderr).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def read_contract(contract_path: Path) -> dict[str, Any]:
    return json.loads(contract_path.read_text(encoding="utf-8"))


def schema_path() -> Path:
    return Path(__file__).resolve().parents[5] / "schemas" / "task_result.v1.json"


def schema_root() -> Path:
    return Path(__file__).resolve().parents[5] / "schemas"


def write_manifest(store: RunStore, run_id: str, data: dict[str, Any]) -> None:
    store.write_manifest(run_id, data)


def write_contract_signature(store: RunStore, run_id: str, contract_path: Path) -> tuple[str | None, str | None]:
    try:
        sig_path = store.write_contract_signature(run_id, contract_path)
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)
    if sig_path is None:
        return None, None
    try:
        signature = sig_path.read_text("utf-8").strip()
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)
    return sig_path.as_posix(), signature


def resolve_baseline_ref(contract: dict[str, Any], baseline_commit: str) -> str:
    rollback = contract.get("rollback", {})
    if isinstance(rollback, dict):
        baseline = rollback.get("baseline_ref")
        if isinstance(baseline, str) and baseline.strip():
            if baseline.strip() == "HEAD":
                return baseline_commit
            return baseline.strip()
    return baseline_commit


def build_log_refs(run_id: str, task_id: str, runs_root: Path, trace_id: str) -> dict[str, Any]:
    run_dir = runs_root / run_id
    return {
        "run_id": run_id,
        "paths": {
            "codex_jsonl": str(run_dir / "codex" / task_id / "events.jsonl"),
            "codex_transcript": str(run_dir / "codex" / task_id / "transcript.md"),
            "git_diff": str(run_dir / "git" / "patch.diff"),
            "tests_log": str(run_dir / "tests" / "stdout.log"),
            "trace_id": trace_id,
        },
    }


def llm_params_snapshot(contract: dict[str, Any], runner_name: str, codex_version: str | None) -> dict[str, Any]:
    tool_permissions = contract.get("tool_permissions") if isinstance(contract, dict) else {}
    if not isinstance(tool_permissions, dict):
        tool_permissions = {}
    return {
        "runner": runner_name,
        "model": os.getenv("CORTEXPILOT_CODEX_MODEL", ""),
        "profile": os.getenv("CORTEXPILOT_CODEX_PROFILE", ""),
        "codex_version": codex_version or "",
        "filesystem": tool_permissions.get("filesystem", ""),
        "shell": tool_permissions.get("shell", ""),
        "network": tool_permissions.get("network", ""),
        "mcp_tools": tool_permissions.get("mcp_tools", []),
    }
