from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def repo_root() -> Path:
    try:
        cwd = Path.cwd().resolve()
    except (FileNotFoundError, RuntimeError):
        cwd = None
    if cwd is not None and (cwd / ".git").exists():
        return cwd
    return Path(__file__).resolve().parents[4]


def runs_root(current_repo_root: Path) -> Path:
    return current_repo_root / ".runtime-cache" / "cortexpilot" / "runs"


def wait_for_latest_run_id(runs_root_path: Path, start_ts: float, timeout_sec: float = 30.0) -> str:
    deadline = time.time() + timeout_sec
    last_seen = ""
    while time.time() < deadline:
        if not runs_root_path.exists():
            time.sleep(0.2)
            continue
        candidates = []
        for entry in runs_root_path.iterdir():
            if not entry.is_dir():
                continue
            try:
                stat = entry.stat()
            except OSError:
                continue
            if stat.st_mtime >= start_ts - 1:
                candidates.append((stat.st_mtime, entry.name))
        if candidates:
            candidates.sort()
            last_seen = candidates[-1][1]
            break
        time.sleep(0.2)
    return last_seen


def event_level(payload: dict[str, Any]) -> str:
    level = str(payload.get("level") or "INFO").upper()
    if level == "WARNING":
        return "WARN"
    if level in {"DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"}:
        return level
    return "INFO"


def parse_event_line(line: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def compact_context(payload: dict[str, Any]) -> str:
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    merged = {**context, **meta}
    if not merged:
        return ""
    keys = ["task_id", "tool", "status", "reason", "error", "path", "attempt", "run_id", "request_id"]
    parts: list[str] = []
    for key in keys:
        value = merged.get(key)
        if value in (None, "", []):
            continue
        if isinstance(value, (dict, list)):
            text = json.dumps(value, ensure_ascii=False)
        else:
            text = str(value)
        if len(text) > 120:
            text = f"{text[:117]}..."
        parts.append(f"{key}={text}")
    return " | ".join(parts)


def format_pretty_event(payload: dict[str, Any]) -> str:
    ts_raw = str(payload.get("ts") or payload.get("_ts") or "")
    if ts_raw:
        try:
            dt = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            ts = dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:  # noqa: BLE001
            ts = ts_raw
    else:
        ts = "-"
    level = event_level(payload)
    event_name = str(payload.get("event") or payload.get("event_type") or "UNKNOWN")
    payload_meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    payload_context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    task_id = str(payload.get("task_id") or payload_meta.get("task_id") or payload_context.get("task_id") or "-")
    summary = compact_context(payload)
    if summary:
        return f"[{ts}] {level:<5} {event_name} task={task_id} | {summary}"
    return f"[{ts}] {level:<5} {event_name} task={task_id}"


def tail_events(
    path: Path,
    done: Any,
    *,
    console_obj: Any,
    idle_sec: float = 1.0,
    tail_format: str = "pretty",
    min_level: str = "INFO",
    include_events: set[str] | None = None,
) -> None:
    severity = {"DEBUG": 10, "INFO": 20, "WARN": 30, "ERROR": 40, "CRITICAL": 50}
    min_score = severity.get(min_level.upper(), 20)
    last_size = 0
    while not done.is_set():
        if not path.exists():
            time.sleep(0.2)
            continue
        with path.open("r", encoding="utf-8") as handle:
            handle.seek(last_size)
            while True:
                line = handle.readline()
                if not line:
                    break
                last_size = handle.tell()
                payload = parse_event_line(line)
                if payload is None:
                    if tail_format == "jsonl":
                        console_obj.print(line.rstrip())
                    continue
                level = event_level(payload)
                if severity.get(level, 20) < min_score:
                    continue
                event_name = str(payload.get("event") or payload.get("event_type") or "")
                if include_events and event_name not in include_events:
                    continue
                if tail_format == "jsonl":
                    console_obj.print(json.dumps(payload, ensure_ascii=False))
                else:
                    console_obj.print(format_pretty_event(payload))
        time.sleep(idle_sec)


def read_manifest_status(run_id: str, runs_root_path: Path) -> str:
    manifest_path = runs_root_path / run_id / "manifest.json"
    if not manifest_path.exists():
        return "UNKNOWN"
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "UNKNOWN"
    return str(payload.get("status", "UNKNOWN"))


def hooks_auto_install_enabled() -> bool:
    raw = os.getenv("CORTEXPILOT_HOOKS_AUTO_INSTALL", "1").strip().lower()
    return raw in {"1", "true", "yes"}


def install_hooks(repo_root_path: Path) -> tuple[bool, str]:
    script = repo_root_path / "scripts" / "hooks" / "install.sh"
    if not script.exists():
        return False, f"missing hook installer: {script}"
    try:
        subprocess.run([str(script)], check=True, capture_output=True, text=True)
        return True, "hooks installed"
    except Exception as exc:  # noqa: BLE001
        return False, f"hook install failed: {exc}"


def hooks_status(repo_root_path: Path) -> bool:
    hooks_dir = repo_root_path / ".git" / "hooks"
    if not hooks_dir.exists():
        return False
    required = ["pre-commit", "pre-push"]
    for name in required:
        hook = hooks_dir / name
        if not hook.exists():
            return False
        try:
            content = hook.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            return False
        if "allowed_paths_gate.sh" not in content:
            return False
    return True
