from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .run_store_primitives import exclusive_file_lock, now_ts, safe_component, write_atomic


def codex_task_dir(run_dir: Path, task_id: str) -> Path:
    safe_task_id = safe_component(task_id, "task_id")
    task_dir = run_dir / "codex" / safe_task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    return task_dir


def append_codex_event(task_dir: Path, event_line: str) -> Path:
    events_path = task_dir / "events.jsonl"
    with events_path.open("a", encoding="utf-8") as handle:
        handle.write(event_line.rstrip("\n") + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return events_path


def write_codex_transcript(task_dir: Path, transcript: str) -> Path:
    path = task_dir / "transcript.md"
    path.write_text(transcript, encoding="utf-8")
    return path


def write_codex_thread_id(task_dir: Path, thread_id: str) -> Path:
    path = task_dir / "thread_id.txt"
    path.write_text(thread_id, encoding="utf-8")
    return path


def write_codex_session_map(run_dir: Path, mapping: dict[str, Any]) -> Path:
    path = run_dir / "codex" / "session_map.json"
    lock_path = run_dir / "codex" / "session_map.lock"
    with exclusive_file_lock(lock_path):
        existing: dict[str, Any] = {}
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                raw = {}
            if isinstance(raw, dict):
                existing = raw

        merged = dict(existing)
        merged.update(mapping)
        merged["updated_at"] = now_ts()

        tasks = existing.get("tasks")
        if not isinstance(tasks, dict):
            tasks = {}
        task_id = str(mapping.get("task_id") or "").strip()
        if task_id:
            task_entry = tasks.get(task_id)
            if not isinstance(task_entry, dict):
                task_entry = {}
            task_entry.update(mapping)
            task_entry["updated_at"] = now_ts()
            tasks[task_id] = task_entry
            merged["tasks"] = tasks

        payload = json.dumps(merged, ensure_ascii=False, indent=2).encode("utf-8")
        write_atomic(path, payload)
    return path
