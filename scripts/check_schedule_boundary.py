#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
ORCH_SRC = ROOT_DIR / "apps" / "orchestrator" / "src"
if str(ORCH_SRC) not in sys.path:
    sys.path.insert(0, str(ORCH_SRC))

from cortexpilot_orch.contract.validator import ContractValidator
from cortexpilot_orch.queue import QueueStore


def _queue_path() -> Path:
    runtime_root = Path(os.getenv("CORTEXPILOT_RUNTIME_ROOT", ".runtime-cache/cortexpilot"))
    return runtime_root / "queue.jsonl"


def _load_latest_items(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return QueueStore(queue_path=path).list_items()


def main() -> int:
    path = _queue_path()
    items = _load_latest_items(path)
    validator = ContractValidator()
    violations: list[str] = []

    for index, item in enumerate(items):
        if not isinstance(item, dict):
            violations.append(f"queue item #{index} is not an object")
            continue
        required = {"priority", "eligible", "queue_state", "sla_state"}
        missing = sorted(key for key in required if key not in item)
        if missing:
            violations.append(f"queue item {item.get('task_id', index)} missing fields: {', '.join(missing)}")
            continue
        try:
            validator.validate_report(item, "queue_item.v1.json")
        except Exception as exc:  # noqa: BLE001
            violations.append(f"queue item {item.get('task_id', index)} schema invalid: {exc}")
        scheduled_at = item.get("scheduled_at")
        if scheduled_at:
            try:
                validator.validate_report(
                    {
                        "task_id": item.get("task_id"),
                        "workflow_id": item.get("workflow_id", ""),
                        "source_run_id": item.get("source_run_id", ""),
                        "scheduled_at": scheduled_at,
                        "deadline_at": item.get("deadline_at", ""),
                        "priority": item.get("priority", 0),
                    },
                    "scheduled_run.v1.json",
                )
            except Exception as exc:  # noqa: BLE001
                violations.append(f"scheduled run {item.get('task_id', index)} invalid: {exc}")

    if violations:
        print("schedule-boundary failed")
        for violation in violations:
            print(f"- {violation}")
        return 1

    print("schedule-boundary ok")
    print(f"items={len(items)} path={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
