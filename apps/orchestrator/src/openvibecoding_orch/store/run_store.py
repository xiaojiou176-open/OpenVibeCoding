from __future__ import annotations

import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openvibecoding_orch.config import get_logging_config, get_runtime_config
from openvibecoding_orch.contract.validator import ContractValidator
from .run_store_archive_helpers import (
    append_hashchain_entry,
    events_summary_path,
    hashchain_path,
    read_hashchain_tail,
    rebuild_events_summary,
    update_events_summary,
)
from .run_store_codex_helpers import (
    append_codex_event as append_codex_event_file,
    codex_task_dir,
    write_codex_session_map as write_codex_session_map_file,
    write_codex_thread_id as write_codex_thread_id_file,
    write_codex_transcript as write_codex_transcript_file,
)
from .run_store_event_types import KNOWN_EVENT_TYPES
from .run_store_primitives import (
    exclusive_file_lock,
    hmac_sha256,
    load_hmac_key,
    now_ts,
    write_atomic,
)
from .run_store_tool_call_helpers import normalize_tool_call, tool_call_fallback
from .run_store_write_helpers import (
    append_artifact_jsonl as append_artifact_jsonl_file,
    write_artifact as write_artifact_file,
    write_artifact_bytes as write_artifact_bytes_file,
    write_ci_report as write_ci_report_file,
    write_contract as write_contract_file,
    write_diff as write_diff_file,
    write_diff_names as write_diff_names_file,
    write_git_baseline as write_git_baseline_file,
    write_git_patch as write_git_patch_file,
    write_llm_snapshot as write_llm_snapshot_file,
    write_manifest as write_manifest_file,
    write_meta as write_meta_file,
    write_report as write_report_file,
    write_review_report as write_review_report_file,
    write_task_contract as write_task_contract_file,
    write_task_result as write_task_result_file,
    write_tests_logs as write_tests_logs_file,
    write_trace_id as write_trace_id_file,
    write_worktree_ref as write_worktree_ref_file,
)


class RunStore:
    _RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

    def __init__(self, runs_root: Path | None = None) -> None:
        if runs_root is None:
            runs_root = get_runtime_config().runs_root
        self._runs_root = runs_root
        self._runs_root_resolved = self._runs_root.resolve()
        self._event_validator = ContractValidator()
        self._events_lock = threading.RLock()
        self._codex_lock = threading.RLock()

    def _validate_run_id(self, run_id: str) -> str:
        if not isinstance(run_id, str):
            raise ValueError("run_id must be a string")
        normalized = run_id.strip()
        if not normalized:
            raise ValueError("run_id must not be empty")
        if not self._RUN_ID_RE.fullmatch(normalized) or ".." in normalized:
            raise ValueError("run_id contains illegal path characters")
        return normalized

    def _run_dir(self, run_id: str) -> Path:
        safe_run_id = self._validate_run_id(run_id)
        candidate = self._runs_root / safe_run_id
        resolved = candidate.resolve(strict=False)
        try:
            resolved.relative_to(self._runs_root_resolved)
        except ValueError as exc:
            raise ValueError("run_id escapes runs_root boundary") from exc
        return candidate

    @property
    def runs_root(self) -> Path:
        return self._runs_root

    def run_dir(self, run_id: str) -> Path:
        return self._run_dir(run_id)

    def events_path(self, run_id: str) -> Path:
        return self._run_dir(run_id) / "events.jsonl"

    def _events_summary_path(self, run_id: str) -> Path:
        return events_summary_path(self._run_dir(run_id))

    def _update_events_summary(self, run_id: str, payload: dict[str, Any]) -> None:
        update_events_summary(run_id, payload, self._events_summary_path(run_id))

    def _events_summary_rebuild_marker_path(self, run_id: str) -> Path:
        return self._run_dir(run_id) / "reports" / "events_summary.rebuild_required.json"

    def _mark_events_summary_rebuild_required(
        self, run_id: str, payload: dict[str, Any], error: str
    ) -> None:
        marker = {
            "run_id": run_id,
            "error": error,
            "ts": now_ts(),
            "event_type": str(payload.get("event_type") or payload.get("event") or "UNKNOWN_EVENT"),
        }
        marker_path = self._events_summary_rebuild_marker_path(run_id)
        write_atomic(
            marker_path,
            json.dumps(marker, ensure_ascii=False, indent=2).encode("utf-8"),
        )

    def _ensure_bundle(self, run_id: str) -> None:
        run_dir = self._run_dir(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        for name in [
            "reports",
            "artifacts",
            "tasks",
            "results",
            "reviews",
            "ci",
            "patches",
            "codex",
            "git",
            "tests",
            "trace",
        ]:
            (run_dir / name).mkdir(exist_ok=True)

    def _hashchain_path(self, run_id: str) -> Path:
        return hashchain_path(self._run_dir(run_id))

    def _read_hashchain_tail(self, run_id: str) -> dict[str, Any] | None:
        return read_hashchain_tail(self._hashchain_path(run_id))

    def _append_hashchain_entry(self, run_id: str, event_line: str) -> Path:
        try:
            self._ensure_bundle(run_id)
            return append_hashchain_entry(self._hashchain_path(run_id), event_line)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"hashchain append failed: {exc}") from exc

    def _codex_task_dir(self, run_id: str, task_id: str) -> Path:
        self._ensure_bundle(run_id)
        return codex_task_dir(self._run_dir(run_id), task_id)

    def _active_dir(self) -> Path:
        return get_runtime_config().runtime_root / "active"

    def _active_contract_path(self, run_id: str) -> Path:
        safe_run_id = self._validate_run_id(run_id)
        return self._active_dir() / "runs" / safe_run_id / "contract.json"

    def _contract_root(self) -> Path | None:
        runtime_cfg = get_runtime_config()
        return runtime_cfg.runtime_contract_root

    def _mirror_contract(self, bucket: str, run_id: str, task_id: str, data: dict[str, Any]) -> None:
        contract_root = self._contract_root()
        if contract_root is None:
            return
        safe_run_id = self._validate_run_id(run_id)
        target_dir = contract_root / bucket / safe_run_id
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"{task_id}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def create_run(self, task_id: str) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        run_id = f"run_{timestamp}_{uuid.uuid4().hex}"
        self._ensure_bundle(run_id)
        events_path = self._run_dir(run_id) / "events.jsonl"
        events_path.touch(exist_ok=True)
        (self._run_dir(run_id) / "events.hashchain.jsonl").touch(exist_ok=True)
        return run_id

    def write_manifest(self, run_id: str, manifest_data: dict[str, Any]) -> Path:
        self._ensure_bundle(run_id)
        return write_manifest_file(self._run_dir(run_id), manifest_data)

    def write_contract(self, run_id: str, contract_data: dict[str, Any]) -> Path:
        self._ensure_bundle(run_id)
        return write_contract_file(self._run_dir(run_id), contract_data)

    def write_contract_signature(self, run_id: str, contract_path: Path) -> Path | None:
        key = load_hmac_key()
        if not key:
            return None
        try:
            payload = contract_path.read_bytes()
            signature = hmac_sha256(key, payload)
            sig_path = self._run_dir(run_id) / "contract.sig"
            sig_path.write_text(signature, encoding="utf-8")
            return sig_path
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"contract signature failed: {exc}") from exc

    def write_active_contract(self, run_id: str, contract_data: dict[str, Any]) -> Path:
        active_dir = self._active_dir()
        active_dir.mkdir(parents=True, exist_ok=True)
        contract_path = self._active_contract_path(run_id)
        contract_path.parent.mkdir(parents=True, exist_ok=True)
        contract_path.write_text(
            json.dumps(contract_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (active_dir / "run_id.txt").write_text(run_id, encoding="utf-8")
        return contract_path

    def clear_active_contract(self, run_id: str) -> None:
        active_dir = self._active_dir()
        run_id_path = active_dir / "run_id.txt"
        contract_path = self._active_contract_path(run_id)
        if contract_path.exists():
            contract_path.unlink()
        run_dir = contract_path.parent
        if run_dir.exists() and not any(run_dir.iterdir()):
            run_dir.rmdir()

        if not run_id_path.exists():
            return
        current = run_id_path.read_text(encoding="utf-8").strip()
        if current and current != run_id:
            return
        legacy_contract_path = active_dir / "contract.json"
        if legacy_contract_path.exists():
            legacy_contract_path.unlink()
        if run_id_path.exists():
            run_id_path.unlink()

    def read_active_contract(self, run_id: str | None = None) -> dict[str, Any] | None:
        active_dir = self._active_dir()
        run_id_path = active_dir / "run_id.txt"
        if run_id is not None:
            contract_path = self._active_contract_path(run_id)
        else:
            selected_run_id = ""
            if run_id_path.exists():
                selected_run_id = run_id_path.read_text(encoding="utf-8").strip()
            if selected_run_id:
                contract_path = self._active_contract_path(selected_run_id)
            else:
                contract_path = active_dir / "contract.json"
        if not contract_path.exists():
            return None
        try:
            return json.loads(contract_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def append_event(self, run_id: str, event_dict: dict[str, Any]) -> Path:
        return self._append_event_line(run_id, event_dict, skip_drift=False)

    def _append_event_line(self, run_id: str, event_dict: dict[str, Any], skip_drift: bool) -> Path:
        drift_payload: dict[str, Any] | None = None
        with self._events_lock:
            self._ensure_bundle(run_id)
            run_dir = self._run_dir(run_id)
            with exclusive_file_lock(run_dir / "events.lock"):
                events_path = run_dir / "events.jsonl"
                hashchain_path = self._hashchain_path(run_id)
                event_file_size = events_path.stat().st_size if events_path.exists() else 0
                hashchain_file_size = hashchain_path.stat().st_size if hashchain_path.exists() else 0

                payload = dict(event_dict)
                if "ts" not in payload:
                    payload["ts"] = now_ts()

                if "run_id" not in payload:
                    payload["run_id"] = run_id
                elif payload["run_id"] != run_id:
                    raise ValueError("Schema validation failed: event run_id mismatch")

                meta = payload.get("meta")
                if not isinstance(meta, dict):
                    meta = {}

                context = payload.get("context")
                if not isinstance(context, dict):
                    context = dict(meta)
                if not meta and isinstance(context, dict):
                    meta = dict(context)

                payload["meta"] = meta
                payload["context"] = context

                event_type = payload.get("event_type") or payload.get("event") or "UNKNOWN_EVENT"
                payload["event_type"] = event_type
                payload.setdefault("event", event_type)
                payload.setdefault("payload", context if isinstance(context, dict) else meta)

                if "task_id" not in payload:
                    payload["task_id"] = (
                        context.get("task_id")
                        if isinstance(context, dict)
                        else meta.get("task_id") if isinstance(meta, dict) else ""
                    )
                if payload["task_id"] is None:
                    payload["task_id"] = ""

                if "attempt" not in payload:
                    payload["attempt"] = (
                        context.get("attempt")
                        if isinstance(context, dict)
                        else meta.get("attempt") if isinstance(meta, dict) else None
                    )
                if "trace_id" not in payload or not str(payload.get("trace_id") or "").strip():
                    payload["trace_id"] = get_logging_config().trace_id or uuid.uuid4().hex

                self._event_validator.validate_event(payload)

                event_line = json.dumps(payload, ensure_ascii=False)
                with events_path.open("a", encoding="utf-8") as handle:
                    handle.write(event_line + "\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                try:
                    self._append_hashchain_entry(run_id, event_line)
                except Exception:
                    with events_path.open("rb+") as handle:
                        handle.truncate(event_file_size)
                        handle.flush()
                        os.fsync(handle.fileno())
                    with hashchain_path.open("rb+") as handle:
                        handle.truncate(hashchain_file_size)
                        handle.flush()
                        os.fsync(handle.fileno())
                    raise
                try:
                    self._update_events_summary(run_id, payload)
                except Exception as exc:
                    # events summary is derivable from events.jsonl; do not fail append_event for summary-only issues.
                    self._mark_events_summary_rebuild_required(run_id, payload, str(exc))

                if not skip_drift and event_type not in KNOWN_EVENT_TYPES:
                    drift_payload = {
                        "level": "WARN",
                        "event": "SCHEMA_DRIFT_DETECTED",
                        "event_type": "SCHEMA_DRIFT_DETECTED",
                        "run_id": run_id,
                        "task_id": payload.get("task_id", ""),
                        "attempt": payload.get("attempt"),
                        "context": {"unknown_event_type": event_type},
                        "payload": {"unknown_event_type": event_type},
                    }
        if drift_payload is not None:
            self._append_event_line(run_id, drift_payload, skip_drift=True)
        return events_path

    def rebuild_events_summary(self, run_id: str) -> Path:
        self._ensure_bundle(run_id)
        run_dir = self._run_dir(run_id)
        summary_path = self._events_summary_path(run_id)
        rebuild_events_summary(run_id, run_dir / "events.jsonl", summary_path)
        marker_path = self._events_summary_rebuild_marker_path(run_id)
        if marker_path.exists():
            marker_path.unlink()
        return summary_path

    def write_diff(self, run_id: str, diff_text: str) -> Path:
        self._ensure_bundle(run_id)
        return write_diff_file(self._run_dir(run_id), diff_text)

    def write_diff_names(self, run_id: str, names: list[str]) -> Path:
        self._ensure_bundle(run_id)
        return write_diff_names_file(self._run_dir(run_id), names)

    def write_report(self, run_id: str, report_type: str, data: dict[str, Any]) -> Path:
        self._ensure_bundle(run_id)
        return write_report_file(self._run_dir(run_id), report_type, data)

    def append_artifact_jsonl(self, run_id: str, filename: str, payload: dict[str, Any]) -> Path:
        self._ensure_bundle(run_id)
        return append_artifact_jsonl_file(self._run_dir(run_id), filename, payload)

    def write_task_contract(self, run_id: str, task_id: str, contract_data: dict[str, Any]) -> Path:
        self._ensure_bundle(run_id)
        path, safe_task_id = write_task_contract_file(self._run_dir(run_id), task_id, contract_data)
        self._mirror_contract("tasks", run_id, safe_task_id, contract_data)
        return path

    def write_task_result(self, run_id: str, task_id: str, data: dict[str, Any]) -> Path:
        self._ensure_bundle(run_id)
        path, safe_task_id = write_task_result_file(self._run_dir(run_id), task_id, data)
        self._mirror_contract("results", run_id, safe_task_id, data)
        return path

    def append_codex_event(self, run_id: str, task_id: str, event_line: str) -> Path:
        task_dir = self._codex_task_dir(run_id, task_id)
        with self._codex_lock:
            return append_codex_event_file(task_dir, event_line)

    def write_codex_transcript(self, run_id: str, task_id: str, transcript: str) -> Path:
        task_dir = self._codex_task_dir(run_id, task_id)
        return write_codex_transcript_file(task_dir, transcript)

    def write_codex_thread_id(self, run_id: str, task_id: str, thread_id: str) -> Path:
        task_dir = self._codex_task_dir(run_id, task_id)
        return write_codex_thread_id_file(task_dir, thread_id)

    def write_codex_session_map(self, run_id: str, mapping: dict[str, Any]) -> Path:
        return write_codex_session_map_file(self._run_dir(run_id), mapping)

    def write_review_report(self, run_id: str, task_id: str, data: dict[str, Any]) -> Path:
        self._ensure_bundle(run_id)
        path, safe_task_id = write_review_report_file(self._run_dir(run_id), task_id, data)
        self._mirror_contract("reviews", run_id, safe_task_id, data)
        return path

    def write_ci_report(self, run_id: str, task_id: str, data: dict[str, Any]) -> Path:
        self._ensure_bundle(run_id)
        return write_ci_report_file(self._run_dir(run_id), task_id, data)

    def write_git_baseline(self, run_id: str, commit: str) -> Path:
        self._ensure_bundle(run_id)
        return write_git_baseline_file(self._run_dir(run_id), commit)

    def write_worktree_ref(self, run_id: str, worktree: Path) -> Path:
        self._ensure_bundle(run_id)
        return write_worktree_ref_file(self._run_dir(run_id), worktree)

    def write_git_patch(self, run_id: str, task_id: str, diff_text: str) -> Path:
        self._ensure_bundle(run_id)
        return write_git_patch_file(self._run_dir(run_id), task_id, diff_text)

    def write_tests_logs(self, run_id: str, command: str, stdout: str, stderr: str) -> None:
        self._ensure_bundle(run_id)
        write_tests_logs_file(self._run_dir(run_id), command, stdout, stderr)

    def write_trace_id(self, run_id: str, trace_id: str) -> Path:
        self._ensure_bundle(run_id)
        return write_trace_id_file(self._run_dir(run_id), trace_id)

    def write_llm_snapshot(self, run_id: str, snapshot: dict[str, Any]) -> Path:
        self._ensure_bundle(run_id)
        return write_llm_snapshot_file(self._run_dir(run_id), snapshot)

    def write_meta(self, run_id: str, data: dict[str, Any]) -> Path:
        self._ensure_bundle(run_id)
        return write_meta_file(self._run_dir(run_id), data)

    def write_artifact(self, run_id: str, filename: str, content: str) -> Path:
        self._ensure_bundle(run_id)
        return write_artifact_file(self._run_dir(run_id), filename, content)

    def write_artifact_bytes(self, run_id: str, filename: str, content: bytes) -> Path:
        self._ensure_bundle(run_id)
        return write_artifact_bytes_file(self._run_dir(run_id), filename, content)

    def append_tool_call(self, run_id: str, payload: dict[str, Any]) -> Path:
        self._ensure_bundle(run_id)
        entry = normalize_tool_call(run_id, payload)
        validator = ContractValidator()
        try:
            validator.validate_report(entry, "tool_call.v1.json")
        except Exception as exc:  # noqa: BLE001
            self.append_event(
                run_id,
                {
                    "level": "ERROR",
                    "event": "TOOL_CALL_SCHEMA_INVALID",
                    "run_id": run_id,
                    "context": {"error": str(exc), "tool": entry.get("tool", "")},
                },
            )
            entry = tool_call_fallback(run_id, str(entry.get("tool") or "unknown"), str(exc))
        return self.append_artifact_jsonl(run_id, "tool_calls.jsonl", entry)


_default_store = RunStore()


def create_run_dir(run_id: str) -> Path:
    run_dir = _default_store._run_dir(run_id)
    _default_store._ensure_bundle(run_id)
    (run_dir / "events.jsonl").touch(exist_ok=True)
    (run_dir / "events.hashchain.jsonl").touch(exist_ok=True)
    return run_dir


def write_manifest(run_id: str, data: dict[str, Any]) -> Path:
    return _default_store.write_manifest(run_id, data)


def write_contract(run_id: str, data: dict[str, Any]) -> Path:
    return _default_store.write_contract(run_id, data)


def write_contract_signature(run_id: str, contract_path: Path) -> Path | None:
    return _default_store.write_contract_signature(run_id, contract_path)


def append_event(run_id: str, event: dict[str, Any]) -> Path:
    return _default_store.append_event(run_id, event)


def write_diff(run_id: str, diff_text: str) -> Path:
    return _default_store.write_diff(run_id, diff_text)


def write_diff_names(run_id: str, names: list[str]) -> Path:
    return _default_store.write_diff_names(run_id, names)


def write_report(run_id: str, report_type: str, data: dict[str, Any]) -> Path:
    return _default_store.write_report(run_id, report_type, data)


def write_task_contract(run_id: str, task_id: str, data: dict[str, Any]) -> Path:
    return _default_store.write_task_contract(run_id, task_id, data)


def write_task_result(run_id: str, task_id: str, data: dict[str, Any]) -> Path:
    return _default_store.write_task_result(run_id, task_id, data)


def append_codex_event(run_id: str, task_id: str, event_line: str) -> Path:
    return _default_store.append_codex_event(run_id, task_id, event_line)


def write_codex_transcript(run_id: str, task_id: str, transcript: str) -> Path:
    return _default_store.write_codex_transcript(run_id, task_id, transcript)


def write_codex_thread_id(run_id: str, task_id: str, thread_id: str) -> Path:
    return _default_store.write_codex_thread_id(run_id, task_id, thread_id)


def write_codex_session_map(run_id: str, mapping: dict[str, Any]) -> Path:
    return _default_store.write_codex_session_map(run_id, mapping)


def write_review_report(run_id: str, task_id: str, data: dict[str, Any]) -> Path:
    return _default_store.write_review_report(run_id, task_id, data)


def write_ci_report(run_id: str, task_id: str, data: dict[str, Any]) -> Path:
    return _default_store.write_ci_report(run_id, task_id, data)


def write_git_baseline(run_id: str, commit: str) -> Path:
    return _default_store.write_git_baseline(run_id, commit)


def write_worktree_ref(run_id: str, worktree: Path) -> Path:
    return _default_store.write_worktree_ref(run_id, worktree)


def write_git_patch(run_id: str, task_id: str, diff_text: str) -> Path:
    return _default_store.write_git_patch(run_id, task_id, diff_text)


def write_tests_logs(run_id: str, command: str, stdout: str, stderr: str) -> None:
    _default_store.write_tests_logs(run_id, command, stdout, stderr)


def write_trace_id(run_id: str, trace_id: str) -> Path:
    return _default_store.write_trace_id(run_id, trace_id)


def write_meta(run_id: str, data: dict[str, Any]) -> Path:
    return _default_store.write_meta(run_id, data)


def write_artifact(run_id: str, filename: str, content: str) -> Path:
    return _default_store.write_artifact(run_id, filename, content)


def write_artifact_bytes(run_id: str, filename: str, content: bytes) -> Path:
    return _default_store.write_artifact_bytes(run_id, filename, content)


def append_tool_call(run_id: str, payload: dict[str, Any]) -> Path:
    return _default_store.append_tool_call(run_id, payload)


def rebuild_events_summary_for_run(run_id: str) -> Path:
    return _default_store.rebuild_events_summary(run_id)
