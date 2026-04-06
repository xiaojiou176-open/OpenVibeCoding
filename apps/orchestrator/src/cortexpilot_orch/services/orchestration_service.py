from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cortexpilot_orch.config import load_config
from cortexpilot_orch.replay.reexec_flow import reexecute_run
from cortexpilot_orch.replay.replayer import ReplayRunner
from cortexpilot_orch.replay.verify_flow import verify_run
from cortexpilot_orch.scheduler import execute_flow
from cortexpilot_orch.scheduler.scheduler import Orchestrator
from cortexpilot_orch.store import run_store
from cortexpilot_orch.store.run_store import RunStore

_REDACTED_VALUE = "[REDACTED]"
_SENSITIVE_KEY_RE = re.compile(r"(token|secret|key|password|credential|auth|private|cert)", re.IGNORECASE)


def sanitize_approval_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        sanitized: dict[str, Any] = {}
        for key, value in payload.items():
            key_text = str(key)
            if _SENSITIVE_KEY_RE.search(key_text):
                sanitized[key_text] = _REDACTED_VALUE
            else:
                sanitized[key_text] = sanitize_approval_payload(value)
        return sanitized
    if isinstance(payload, list):
        return [sanitize_approval_payload(item) for item in payload]
    return payload


class OrchestrationService:
    def __init__(self, repo_root: Path | None = None) -> None:
        self._repo_root = repo_root

    def _resolve_repo_root(self) -> Path:
        if self._repo_root is not None:
            return self._repo_root.resolve()
        return load_config().repo_root.resolve()

    def _orchestrator(self) -> Orchestrator:
        return Orchestrator(self._resolve_repo_root())

    def _run_store(self) -> RunStore:
        return RunStore(runs_root=load_config().runs_root)

    def _replayer(self) -> ReplayRunner:
        return ReplayRunner(self._run_store())

    def execute_task(self, contract_path: Path, mock_mode: bool) -> str:
        return execute_flow.execute_task_flow(self._orchestrator(), contract_path, mock_mode=mock_mode)

    def replay_run(self, run_id: str, baseline_run_id: str | None = None) -> dict[str, Any]:
        return self._orchestrator().replay_run(run_id, baseline_run_id=baseline_run_id)

    def replay_verify(self, run_id: str, strict: bool = True) -> dict[str, Any]:
        return verify_run(self._replayer(), run_id, strict=strict)

    def replay_reexec(self, run_id: str, strict: bool = True) -> dict[str, Any]:
        return reexecute_run(self._replayer(), run_id, strict=strict)

    def promote_evidence(self, run_id: str, bundle: dict[str, Any], source: str = "search_ui") -> dict[str, Any]:
        self.write_evidence_bundle(run_id, bundle)
        self.append_event(
            run_id,
            {
                "level": "INFO",
                "event": "SEARCH_PROMOTED",
                "run_id": run_id,
                "context": {"source": source},
            },
        )
        return {"ok": True, "bundle": bundle}

    def reject_run(self, run_id: str, reason: str = "diff gate rejected") -> dict[str, Any]:
        manifest_path = self._run_store().run_dir(run_id) / "manifest.json"
        if not manifest_path.exists():
            return {"ok": False, "error": "RUN_NOT_FOUND"}
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest = {}
        if not isinstance(manifest, dict):
            manifest = {}
        manifest["status"] = "FAILURE"
        manifest["failure_reason"] = reason
        manifest["failure_class"] = "gate"
        manifest["failure_code"] = "DIFF_GATE_REJECTED"
        manifest["failure_stage"] = "diff_gate"
        manifest["failure_summary_zh"] = "Rule blocked: the diff gate rejected the change and the run was denied."
        manifest["action_hint_zh"] = "Review the diff-gate rule and evidence, then resubmit."
        manifest["root_event"] = "DIFF_GATE_REJECTED"
        manifest["outcome_type"] = "gate"
        manifest["outcome_label_zh"] = "Rule blocked"
        manifest["end_ts"] = manifest.get("end_ts") or datetime.now(timezone.utc).isoformat()
        self.write_manifest(run_id, manifest)
        self.append_event(
            run_id,
            {
                "level": "WARN",
                "event": "DIFF_GATE_REJECTED",
                "run_id": run_id,
                "context": {"reason": reason},
            },
        )
        return {"ok": True, "reason": reason}

    def approve_god_mode(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        sanitized_payload = sanitize_approval_payload(payload)
        self.append_event(
            run_id,
            {
                "level": "INFO",
                "event": "HUMAN_APPROVAL_COMPLETED",
                "run_id": run_id,
                "context": {"payload": sanitized_payload},
            },
        )
        return {"ok": True, "run_id": run_id}

    def write_evidence_bundle(self, run_id: str, bundle: dict[str, Any]) -> None:
        self._run_store().write_report(run_id, "evidence_bundle", bundle)

    def write_manifest(self, run_id: str, manifest_data: dict[str, Any]) -> None:
        run_store.write_manifest(run_id, manifest_data)

    def append_event(self, run_id: str, event_payload: dict[str, Any]) -> None:
        run_store.append_event(run_id, event_payload)
