from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .run_store_primitives import now_ts, sha256_bytes, sha256_text, write_atomic


def events_summary_path(run_dir: Path) -> Path:
    return run_dir / "reports" / "events_summary.json"


def update_events_summary(run_id: str, payload: dict[str, Any], summary_path: Path) -> None:
    event_name = str(payload.get("event_type") or payload.get("event") or "UNKNOWN_EVENT")
    level = str(payload.get("level") or "INFO").upper()
    now = str(payload.get("ts") or now_ts())
    summary: dict[str, Any]
    if summary_path.exists():
        try:
            raw = json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            raw = {}
        summary = raw if isinstance(raw, dict) else {}
    else:
        summary = {}

    counts = summary.get("event_counts")
    if not isinstance(counts, dict):
        counts = {}
    counts[event_name] = int(counts.get(event_name, 0)) + 1

    level_counts = summary.get("level_counts")
    if not isinstance(level_counts, dict):
        level_counts = {}
    level_counts[level] = int(level_counts.get(level, 0)) + 1

    total = int(summary.get("total_events", 0)) + 1
    first_ts = str(summary.get("first_ts") or now)
    last_ts = now

    top_events = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:10]
    top_payload = [{"event": key, "count": value} for key, value in top_events]

    summary.update(
        {
            "run_id": run_id,
            "total_events": total,
            "first_ts": first_ts,
            "last_ts": last_ts,
            "event_counts": counts,
            "level_counts": level_counts,
            "top_events": top_payload,
            "error_events": int(level_counts.get("ERROR", 0)),
            "warn_events": int(level_counts.get("WARN", 0)),
        }
    )
    payload_bytes = json.dumps(summary, ensure_ascii=False, indent=2).encode("utf-8")
    write_atomic(summary_path, payload_bytes)


def rebuild_events_summary(run_id: str, events_path: Path, summary_path: Path) -> None:
    counts: dict[str, int] = {}
    level_counts: dict[str, int] = {}
    first_ts: str | None = None
    last_ts: str | None = None
    total = 0

    if events_path.exists():
        with events_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(payload, dict):
                    continue
                event_name = str(payload.get("event_type") or payload.get("event") or "UNKNOWN_EVENT")
                level = str(payload.get("level") or "INFO").upper()
                ts_value = str(payload.get("ts") or now_ts())
                counts[event_name] = int(counts.get(event_name, 0)) + 1
                level_counts[level] = int(level_counts.get(level, 0)) + 1
                total += 1
                if first_ts is None:
                    first_ts = ts_value
                last_ts = ts_value

    top_events = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:10]
    summary = {
        "run_id": run_id,
        "total_events": total,
        "first_ts": first_ts or now_ts(),
        "last_ts": last_ts or now_ts(),
        "event_counts": counts,
        "level_counts": level_counts,
        "top_events": [{"event": key, "count": value} for key, value in top_events],
        "error_events": int(level_counts.get("ERROR", 0)),
        "warn_events": int(level_counts.get("WARN", 0)),
        "rebuilt_at": now_ts(),
        "rebuilt": True,
    }
    write_atomic(summary_path, json.dumps(summary, ensure_ascii=False, indent=2).encode("utf-8"))


def hashchain_path(run_dir: Path) -> Path:
    return run_dir / "events.hashchain.jsonl"


def read_hashchain_tail(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:  # noqa: BLE001
        return None
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def append_hashchain_entry(path: Path, event_line: str) -> Path:
    tail = read_hashchain_tail(path) or {}
    last_index = tail.get("index") if isinstance(tail, dict) else None
    try:
        next_index = int(last_index) + 1 if last_index is not None else 1
    except (TypeError, ValueError):
        next_index = 1
    prev_hash = ""
    if isinstance(tail, dict):
        prev_hash = str(tail.get("hash") or "")
    event_sha256 = sha256_text(event_line)
    chain_material = f"{next_index}:{prev_hash}:{event_sha256}".encode("utf-8")
    chain_hash = sha256_bytes(chain_material)
    entry = {
        "index": next_index,
        "event_sha256": event_sha256,
        "prev_hash": prev_hash,
        "hash": chain_hash,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return path
