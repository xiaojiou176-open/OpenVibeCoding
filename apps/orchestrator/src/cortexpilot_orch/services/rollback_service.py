from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cortexpilot_orch.config import load_config
from cortexpilot_orch.scheduler.rollback_pipeline import apply_rollback
from cortexpilot_orch.store import run_store


class RollbackService:
    def __init__(self, runs_root: Path | None = None) -> None:
        self._runs_root = runs_root

    def _resolve_runs_root(self) -> Path:
        return self._runs_root or load_config().runs_root

    @staticmethod
    def _read_json(path: Path, default: object) -> object:
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return default

    def apply(self, run_id: str) -> dict[str, Any]:
        run_dir = self._resolve_runs_root() / run_id
        manifest_path = run_dir / "manifest.json"
        if not manifest_path.exists():
            return {"ok": False, "error_code": "RUN_NOT_FOUND"}

        worktree_ref = run_dir / "worktree_ref.txt"
        if not worktree_ref.exists():
            result = {"ok": False, "reason": "worktree_ref missing"}
            manifest = self._read_json(manifest_path, {})
            manifest_dict = manifest if isinstance(manifest, dict) else {}
            manifest_dict["status"] = "FAILURE"
            manifest_dict["failure_reason"] = result["reason"]
            manifest_dict["failure_class"] = "env"
            manifest_dict["failure_code"] = "ROLLBACK_WORKTREE_REF_MISSING"
            manifest_dict["failure_stage"] = "rollback"
            manifest_dict["failure_summary_zh"] = "Rollback failed: missing worktree_ref reference."
            manifest_dict["action_hint_zh"] = "Confirm that worktree_ref.txt exists in the run directory and points to a valid path."
            manifest_dict["root_event"] = "ROLLBACK_APPLIED"
            manifest_dict["outcome_type"] = "env"
            manifest_dict["outcome_label_zh"] = "Environment issue"
            run_store.write_manifest(run_id, manifest_dict)
            run_store.append_event(
                run_id,
                {
                    "level": "ERROR",
                    "event": "ROLLBACK_APPLIED",
                    "run_id": run_id,
                    "meta": result,
                },
            )
            return result

        worktree_path = Path(worktree_ref.read_text(encoding="utf-8").strip())
        contract_path = run_dir / "contract.json"
        contract = self._read_json(contract_path, {}) if contract_path.exists() else {}
        rollback = contract.get("rollback", {}) if isinstance(contract, dict) else {}
        result = apply_rollback(worktree_path, rollback)
        if not result.get("ok"):
            manifest = self._read_json(manifest_path, {})
            manifest_dict = manifest if isinstance(manifest, dict) else {}
            reason = str(result.get("reason") or result.get("error") or "rollback failed")
            manifest_dict["status"] = "FAILURE"
            manifest_dict["failure_reason"] = reason
            manifest_dict["failure_class"] = "env"
            manifest_dict["failure_code"] = "ROLLBACK_FAILED"
            manifest_dict["failure_stage"] = "rollback"
            manifest_dict["failure_summary_zh"] = f"Rollback failed: {reason}"
            manifest_dict["action_hint_zh"] = "Review the rollback configuration and worktree state, then retry."
            manifest_dict["root_event"] = "ROLLBACK_APPLIED"
            manifest_dict["outcome_type"] = "env"
            manifest_dict["outcome_label_zh"] = "Environment issue"
            run_store.write_manifest(run_id, manifest_dict)

        run_store.append_event(
            run_id,
            {
                "level": "INFO" if result.get("ok") else "ERROR",
                "event": "ROLLBACK_APPLIED",
                "run_id": run_id,
                "meta": result,
            },
        )
        return result
