from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def timeout_retry(contract: dict[str, Any]) -> dict[str, Any]:
    payload = contract.get("timeout_retry", {})
    return payload if isinstance(payload, dict) else {}


def _git(args: list[str], cwd: Path) -> str:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout.strip()


def apply_rollback(worktree: Path, rollback: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(rollback, dict):
        return {"ok": False, "reason": "rollback config missing"}
    strategy = rollback.get("strategy")
    baseline = rollback.get("baseline_ref") or "HEAD"
    if strategy == "worktree_drop":
        return {"ok": True, "strategy": strategy, "baseline_ref": baseline}
    if strategy == "git_reset_hard":
        try:
            _git(["git", "reset", "--hard", str(baseline)], cwd=worktree)
            return {"ok": True, "strategy": strategy, "baseline_ref": baseline}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "strategy": strategy, "baseline_ref": baseline, "error": str(exc)}
    if strategy == "git_revert_commit":
        try:
            target_ref = rollback.get("target_ref") or baseline
            _git(["git", "revert", "--no-edit", str(target_ref)], cwd=worktree)
            return {
                "ok": True,
                "strategy": strategy,
                "baseline_ref": baseline,
                "target_ref": target_ref,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "strategy": strategy,
                "baseline_ref": baseline,
                "target_ref": rollback.get("target_ref") or baseline,
                "error": str(exc),
            }
    return {"ok": False, "reason": "unknown rollback strategy", "strategy": strategy}


def scoped_revert(worktree: Path, paths: list[str]) -> dict[str, Any]:
    if not paths:
        return {"ok": True, "reverted": []}
    try:
        cmd = ["git", "checkout", "--", *paths]
        result = subprocess.run(cmd, cwd=worktree, capture_output=True, text=True)
        return {
            "ok": result.returncode == 0,
            "reverted": paths,
            "stdout": (result.stdout or "").strip(),
            "stderr": (result.stderr or "").strip(),
            "exit_code": result.returncode,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reverted": [], "error": str(exc)}


def max_retries(contract: dict[str, Any]) -> int:
    retries = timeout_retry(contract).get("max_retries", 0)
    try:
        return max(0, int(retries))
    except (TypeError, ValueError):
        return 0


def retry_backoff(contract: dict[str, Any]) -> int:
    backoff = timeout_retry(contract).get("retry_backoff_sec", 0)
    try:
        return max(0, int(backoff))
    except (TypeError, ValueError):
        return 0
