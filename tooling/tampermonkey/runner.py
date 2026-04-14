from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from openvibecoding_orch.store.run_store import RunStore
from tooling.browser.playwright_runner import BrowserRunner


def _safe_slug(value: str) -> str:
    if not value:
        return "task"
    cleaned = []
    for ch in value:
        if ch.isalnum() or ch in {"-", "_"}:
            cleaned.append(ch)
        else:
            cleaned.append("_")
    slug = "".join(cleaned).strip("_")
    return slug[:40] or "task"


def run_tampermonkey(
    run_id: str,
    script_name: str,
    raw_output: str,
    parsed: dict | None = None,
    task_id: str | None = None,
    url: str | None = None,
    script_content: str | None = None,
    browser_policy: dict[str, Any] | None = None,
) -> dict:
    store = RunStore()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    suffix = uuid.uuid4().hex[:8]
    slug = _safe_slug(script_name or task_id or "tampermonkey")
    prefix = f"tampermonkey/{slug}_{stamp}_{suffix}"
    try:
        raw_ref = store.write_artifact(run_id, f"{prefix}/raw.txt", raw_output)
        parsed_ref = None
        if parsed is not None:
            parsed_ref = store.write_artifact(
                run_id,
                f"{prefix}/parsed.json",
                json.dumps(parsed, ensure_ascii=False, indent=2),
            )
        exec_ref = None
        exec_result = None
        if isinstance(url, str) and url.strip() and isinstance(script_content, str) and script_content.strip():
            artifacts_dir = store._run_dir(run_id) / "artifacts" / prefix
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            runner = BrowserRunner(artifacts_dir, browser_policy=browser_policy)
            exec_result = runner.run_script(script_content, url.strip())
            exec_ref = store.write_artifact(
                run_id,
                f"{prefix}/execution.json",
                json.dumps(exec_result, ensure_ascii=False, indent=2),
            )
        exec_failed = isinstance(exec_result, dict) and exec_result.get("ok") is False
        store.append_event(
            run_id,
            {
                "level": "INFO",
                "event": "TAMPERMONKEY_OUTPUT",
                "run_id": run_id,
                "task_id": task_id or "",
                "context": {
                    "script": script_name,
                    "raw_ref": str(raw_ref),
                    "parsed_ref": str(parsed_ref) if parsed_ref else None,
                    "execution_ref": str(exec_ref) if exec_ref else None,
                    "execution_mode": exec_result.get("mode") if isinstance(exec_result, dict) else None,
                },
            },
        )
        return {
            "ok": not exec_failed,
            "execution": exec_result,
            "error": exec_result.get("error") if exec_failed else None,
        }
    except Exception as exc:
        raise RuntimeError(f"tampermonkey_write_failed: {exc}") from exc
