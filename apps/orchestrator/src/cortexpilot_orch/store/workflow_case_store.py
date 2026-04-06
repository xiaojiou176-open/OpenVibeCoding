from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cortexpilot_orch.config import load_config
from cortexpilot_orch.store.run_store_primitives import now_ts, safe_component, write_atomic


class WorkflowCaseStore:
    def __init__(self, root: Path | None = None, *, ensure_storage: bool = True) -> None:
        cfg = load_config()
        self._root = root or (cfg.runtime_root / "workflow-cases")
        if ensure_storage:
            self._root.mkdir(parents=True, exist_ok=True)

    def _case_dir(self, workflow_id: str) -> Path:
        case_id = safe_component(workflow_id, "workflow_id")
        return self._root / case_id

    def _case_path(self, workflow_id: str) -> Path:
        return self._case_dir(workflow_id) / "case.json"

    def read(self, workflow_id: str) -> dict[str, Any]:
        path = self._case_path(workflow_id)
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def write(self, workflow_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        path = self._case_path(workflow_id)
        case_dir = path.parent
        case_dir.mkdir(parents=True, exist_ok=True)
        stored = dict(payload)
        stored.setdefault("workflow_id", workflow_id)
        stored["case_source"] = "persisted"
        stored["updated_at"] = now_ts()
        write_atomic(path, json.dumps(stored, ensure_ascii=False, indent=2).encode("utf-8"))
        return stored
