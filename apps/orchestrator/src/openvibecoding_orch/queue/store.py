from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from contextlib import contextmanager

try:
    import fcntl
except Exception:  # noqa: BLE001
    fcntl = None


def _now_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso_ts(raw: Any) -> datetime | None:
    value = str(raw or "").strip()
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _coerce_priority(raw: Any) -> int:
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        return 0
    return max(-100, min(parsed, 100))


class QueueStore:
    def __init__(self, queue_path: Path | None = None, *, ensure_storage: bool = True) -> None:
        runtime_root = Path(os.getenv("OPENVIBECODING_RUNTIME_ROOT", ".runtime-cache/openvibecoding"))
        self._queue_path = queue_path or (runtime_root / "queue.jsonl")
        if ensure_storage:
            self._queue_path.parent.mkdir(parents=True, exist_ok=True)
            self._queue_path.touch(exist_ok=True)

    def _append(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = dict(payload)
        data.setdefault("ts", _now_ts())
        data.setdefault("queue_id", uuid.uuid4().hex)
        line = json.dumps(data, ensure_ascii=False)
        with self._locked_handle("a+") as handle:
            handle.seek(0, os.SEEK_END)
            handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return data

    @contextmanager
    def _locked_handle(self, mode: str):
        with self._queue_path.open(mode, encoding="utf-8") as handle:
            if fcntl is None:
                raise RuntimeError("QueueStore requires fcntl for fail-closed file locking")
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield handle
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def enqueue(
        self,
        contract_path: Path,
        task_id: str,
        owner: str = "",
        *,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "event": "QUEUE_ENQUEUE",
            "status": "PENDING",
            "task_id": task_id,
            "owner": owner,
            "contract_path": str(contract_path),
            "priority": 0,
        }
        if isinstance(metadata, dict):
            payload.update(metadata)
            payload["priority"] = _coerce_priority(payload.get("priority"))
        return self._append(payload)

    def preview_enqueue(
        self,
        contract_path: Path,
        task_id: str,
        owner: str = "",
        *,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "event": "QUEUE_PREVIEW",
            "status": "PENDING",
            "task_id": task_id,
            "owner": owner,
            "contract_path": str(contract_path),
            "priority": 0,
            "queue_id": uuid.uuid4().hex,
            "ts": _now_ts(),
        }
        if isinstance(metadata, dict):
            payload.update(metadata)
            payload["priority"] = _coerce_priority(payload.get("priority"))
        return self._queue_item_view(payload)

    def mark_claimed(self, task_id: str, run_id: str, *, queue_id: str = "") -> dict[str, Any]:
        payload = {
            "event": "QUEUE_CLAIM",
            "status": "CLAIMED",
            "task_id": task_id,
            "run_id": run_id,
            "claimed_at": _now_ts(),
        }
        if queue_id:
            payload["queue_id"] = queue_id
        return self._append(payload)

    def mark_done(self, task_id: str, run_id: str, status: str, *, queue_id: str = "") -> dict[str, Any]:
        payload = {
            "event": "QUEUE_DONE",
            "status": status,
            "task_id": task_id,
            "run_id": run_id,
            "completed_at": _now_ts(),
        }
        if queue_id:
            payload["queue_id"] = queue_id
        return self._append(payload)

    def cancel(self, queue_id: str, *, reason: str = "", cancelled_by: str = "") -> dict[str, Any]:
        normalized_queue_id = str(queue_id or "").strip()
        if not normalized_queue_id:
            raise ValueError("queue_id is required")
        with self._locked_handle("a+") as handle:
            handle.seek(0)
            order, state = self._load_state_from_lines(handle.read().splitlines())
            matched_task_id = ""
            matched_item: dict[str, Any] | None = None
            for task_id in order:
                item = state.get(task_id, {})
                if str(item.get("queue_id") or "").strip() == normalized_queue_id:
                    matched_task_id = task_id
                    matched_item = dict(item)
                    break
            if matched_item is None:
                raise KeyError(f"queue item `{normalized_queue_id}` not found")
            if str(matched_item.get("status") or "").strip().upper() != "PENDING":
                raise ValueError(f"queue item `{normalized_queue_id}` is not pending")
            cancel_payload = {
                "event": "QUEUE_CANCEL",
                "status": "CANCELLED",
                "task_id": matched_task_id,
                "queue_id": normalized_queue_id,
                "cancelled_at": _now_ts(),
            }
            if reason:
                cancel_payload["reason"] = str(reason).strip()
            if cancelled_by:
                cancel_payload["cancelled_by"] = str(cancelled_by).strip()
            handle.seek(0, os.SEEK_END)
            handle.write(json.dumps(cancel_payload, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
            merged = dict(matched_item)
            merged.update(cancel_payload)
            return self._queue_item_view(merged)

    def _load_state_from_lines(self, lines: list[str]) -> tuple[list[str], dict[str, dict[str, Any]]]:
        order: list[str] = []
        state: dict[str, dict[str, Any]] = {}
        for line in lines:
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            task_id = payload.get("task_id")
            if not isinstance(task_id, str) or not task_id:
                continue
            if task_id not in state:
                order.append(task_id)
                state[task_id] = {}
            merged = dict(state[task_id])
            merged.update(payload)
            state[task_id] = merged
        return order, state

    def _load_state(self) -> tuple[list[str], dict[str, dict[str, Any]]]:
        if not self._queue_path.exists():
            return [], {}
        return self._load_state_from_lines(self._queue_path.read_text(encoding="utf-8").splitlines())

    def _queue_item_view(self, item: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        status = str(item.get("status") or "").strip().upper()
        scheduled_at = _parse_iso_ts(item.get("scheduled_at"))
        deadline_at = _parse_iso_ts(item.get("deadline_at"))
        eligible = status == "PENDING" and (scheduled_at is None or scheduled_at <= now)

        if status == "CLAIMED":
            sla_state = "in_progress"
        elif status in {"SUCCESS", "DONE", "COMPLETED"}:
            sla_state = "completed"
        elif status in {"FAILURE", "FAILED", "ERROR", "REJECTED", "CANCELLED"}:
            sla_state = "ended"
        elif scheduled_at and scheduled_at > now:
            sla_state = "scheduled"
        elif deadline_at and deadline_at <= now:
            sla_state = "breached"
        elif deadline_at and deadline_at <= now + timedelta(hours=1):
            sla_state = "at_risk"
        else:
            sla_state = "on_track"

        queue_state = "eligible" if eligible else "waiting"
        if status == "CLAIMED":
            queue_state = "claimed"
        elif status not in {"PENDING", "CLAIMED"}:
            queue_state = "closed"

        next_wait_reason = ""
        if status == "PENDING" and not eligible and scheduled_at is not None:
            next_wait_reason = "scheduled_for_future"

        view = {
            "queue_id": str(item.get("queue_id") or ""),
            "task_id": str(item.get("task_id") or ""),
            "owner": str(item.get("owner") or ""),
            "contract_path": str(item.get("contract_path") or ""),
            "workflow_id": str(item.get("workflow_id") or ""),
            "source_run_id": str(item.get("source_run_id") or ""),
            "status": str(item.get("status") or ""),
            "priority": _coerce_priority(item.get("priority")),
            "scheduled_at": str(item.get("scheduled_at") or ""),
            "deadline_at": str(item.get("deadline_at") or ""),
            "run_id": str(item.get("run_id") or ""),
            "claimed_at": str(item.get("claimed_at") or ""),
            "completed_at": str(item.get("completed_at") or ""),
        }
        view["sla_state"] = sla_state
        view["queue_state"] = queue_state
        view["eligible"] = eligible
        view["waiting_reason"] = next_wait_reason
        view["created_at"] = str(item.get("created_at") or item.get("ts") or "")
        view["cancelled_at"] = str(item.get("cancelled_at") or "")
        if item.get("reason"):
            view["reason"] = str(item.get("reason") or "")
        if item.get("cancelled_by"):
            view["cancelled_by"] = str(item.get("cancelled_by") or "")
        return view

    def _next_pending_candidate(self, order: list[str], state: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
        candidates: list[dict[str, Any]] = []
        for task_id in order:
            item = state.get(task_id, {})
            if item.get("status") != "PENDING":
                continue
            view = self._queue_item_view(item)
            if not view.get("eligible"):
                continue
            candidates.append(view)
        if not candidates:
            return None

        def _sort_key(item: dict[str, Any]) -> tuple[int, str, str]:
            scheduled_at = str(item.get("scheduled_at") or "")
            created_at = str(item.get("created_at") or item.get("ts") or "")
            return (-_coerce_priority(item.get("priority")), scheduled_at, created_at)

        candidates.sort(key=_sort_key)
        return candidates[0]

    def next_pending(self) -> dict[str, Any] | None:
        order, state = self._load_state()
        return self._next_pending_candidate(order, state)

    def claim_next(self, run_id: str = "") -> dict[str, Any] | None:
        with self._locked_handle("a+") as handle:
            handle.seek(0)
            order, state = self._load_state_from_lines(handle.read().splitlines())
            item = self._next_pending_candidate(order, state)
            if item is not None:
                claim_payload = {
                    "event": "QUEUE_CLAIM",
                    "status": "CLAIMED",
                    "task_id": item["task_id"],
                    "run_id": run_id,
                    "ts": _now_ts(),
                    "queue_id": str(item.get("queue_id") or uuid.uuid4().hex),
                    "claimed_at": _now_ts(),
                }
                handle.seek(0, os.SEEK_END)
                handle.write(json.dumps(claim_payload, ensure_ascii=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
                claimed = dict(item)
                claimed.update(claim_payload)
                return claimed
        return None

    def list_items(self) -> list[dict[str, Any]]:
        order, state = self._load_state()
        return [self._queue_item_view(state[task_id]) for task_id in order if task_id in state]
