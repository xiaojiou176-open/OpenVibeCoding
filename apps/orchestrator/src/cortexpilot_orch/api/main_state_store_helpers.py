from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any, Callable
from cortexpilot_orch.services.session_index_service import SessionIndexService
from cortexpilot_orch.store.workflow_case_store import WorkflowCaseStore


_logger = logging.getLogger(__name__)


def load_locks(
    *,
    runtime_root: Path,
    load_contract_fn: Callable[[str], dict],
) -> list[dict]:
    locks_dir = runtime_root / "locks"
    if not locks_dir.exists():
        return []
    entries = []
    for lock_path in sorted(locks_dir.glob("*.lock")):
        raw = lock_path.read_text(encoding="utf-8").splitlines()
        record = {"lock_id": lock_path.stem, "run_id": "", "path": "", "ts": ""}
        for line in raw:
            if line.startswith("run_id="):
                record["run_id"] = line.replace("run_id=", "", 1).strip()
            elif line.startswith("path="):
                record["path"] = line.replace("path=", "", 1).strip()
            elif line.startswith("ts="):
                record["ts"] = line.replace("ts=", "", 1).strip()
        if record["run_id"]:
            contract = load_contract_fn(record["run_id"])
            assigned = contract.get("assigned_agent", {}) if isinstance(contract.get("assigned_agent"), dict) else {}
            record["agent_id"] = assigned.get("agent_id", "")
            record["role"] = assigned.get("role", "")
        entries.append(record)
    return entries


def load_worktrees(
    *,
    list_worktrees_lines_fn: Callable[[], list[str]],
    worktree_root: Path,
) -> list[dict]:
    try:
        lines = list_worktrees_lines_fn()
    except Exception as exc:  # noqa: BLE001
        return [{"error": str(exc)}]
    entries: list[dict] = []
    current: dict | None = None
    for line in lines:
        if line.startswith("worktree "):
            if current:
                entries.append(current)
            current = {"path": line.replace("worktree ", "", 1).strip()}
            continue
        if current is None:
            continue
        if line.startswith("HEAD "):
            current["head"] = line.replace("HEAD ", "", 1).strip()
        elif line.startswith("branch "):
            current["branch"] = line.replace("branch ", "", 1).strip()
        elif line.startswith("locked"):
            current["locked"] = True
    if current:
        entries.append(current)
    for entry in entries:
        path = Path(entry.get("path", ""))
        try:
            rel = path.resolve().relative_to(worktree_root)
            entry["run_id"] = rel.parts[0] if rel.parts else ""
            if len(rel.parts) > 1:
                entry["task_id"] = rel.parts[1]
        except Exception as exc:  # noqa: BLE001
            _logger.debug("main_state_store_helpers: worktree path resolution failed: %s", exc)
            entry["run_id"] = entry.get("run_id", "")
    return entries


def select_baseline_by_window(
    *,
    run_id: str,
    window: dict,
    runs_root: Path,
    parse_iso_ts_fn: Callable[[str], datetime],
) -> str | None:
    start_raw = window.get("created_at") or window.get("start_ts")
    end_raw = window.get("finished_at") or window.get("end_ts")
    start_ts = parse_iso_ts_fn(start_raw) if start_raw else None
    end_ts = parse_iso_ts_fn(end_raw) if end_raw else None

    candidates: list[tuple[datetime, str]] = []
    for run_dir in runs_root.glob("*"):
        manifest_path = run_dir / "manifest.json"
        if not manifest_path.exists():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        candidate_id = manifest.get("run_id") or run_dir.name
        if candidate_id == run_id:
            continue
        ts_raw = manifest.get("created_at") or manifest.get("start_ts")
        if ts_raw:
            try:
                ts = parse_iso_ts_fn(ts_raw)
            except Exception as exc:  # noqa: BLE001
                _logger.debug("main_state_store_helpers: parse_iso_ts_fn failed for %s: %s", ts_raw, exc)
                ts = datetime.fromtimestamp(manifest_path.stat().st_mtime, tz=timezone.utc)
        else:
            ts = datetime.fromtimestamp(manifest_path.stat().st_mtime, tz=timezone.utc)
        if start_ts and ts < start_ts:
            continue
        if end_ts and ts > end_ts:
            continue
        candidates.append((ts, candidate_id))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def read_events(*, run_id: str, runs_root: Path) -> list[dict]:
    events_path = runs_root / run_id / "events.jsonl"
    if not events_path.exists():
        return []
    items = []
    for line in events_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            items.append({"raw": line})
    return items


def read_events_incremental(
    *,
    run_id: str,
    runs_root: Path,
    offset: int = 0,
    since: str | None = None,
    limit: int | None = None,
    tail: bool = False,
    filter_events_fn: Callable[..., list[dict[str, Any]]] | None = None,
) -> tuple[list[dict], int]:
    events_path = runs_root / run_id / "events.jsonl"
    if not events_path.exists():
        return [], 0

    next_offset = 0
    items: list[dict] = []
    with events_path.open("r", encoding="utf-8") as handle:
        file_size = events_path.stat().st_size
        safe_offset = 0 if offset is None else max(0, int(offset))
        if safe_offset > file_size:
            safe_offset = 0
        handle.seek(safe_offset)
        for raw_line in handle:
            line = raw_line.rstrip("\n")
            if not line.strip():
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                items.append({"raw": line})
        next_offset = handle.tell()

    if callable(filter_events_fn):
        return filter_events_fn(items, since=since, limit=limit, tail=tail), next_offset

    return items, next_offset


def _session_case_metadata(runtime_root: Path) -> dict[str, list[dict[str, Any]]]:
    service = SessionIndexService(runtime_root)
    by_run: dict[str, list[dict[str, Any]]] = {}
    for pm_session_id in service.list_session_ids():
        intake, response, intake_events = service.read_session_files(pm_session_id)
        bindings = service.derive_bindings(pm_session_id, response, intake_events)
        objective = ""
        if isinstance(intake.get("objective"), str) and intake.get("objective", "").strip():
            objective = intake.get("objective", "").strip()
        elif isinstance(response.get("plan"), dict):
            spec = str((response.get("plan") or {}).get("spec") or "").strip()
            if spec:
                objective = spec
        owner_pm = ""
        if isinstance(intake.get("owner_pm"), str) and intake.get("owner_pm", "").strip():
            owner_pm = intake.get("owner_pm", "").strip()
        else:
            owner_agent = intake.get("owner_agent") if isinstance(intake.get("owner_agent"), dict) else {}
            if str(owner_agent.get("role") or "").strip().upper() == "PM":
                owner_pm = str(owner_agent.get("agent_id") or "").strip()
        project_key = ""
        for key in ["project_key", "project", "repo", "workspace"]:
            value = intake.get(key)
            if isinstance(value, str) and value.strip():
                project_key = value.strip()
                break
        metadata = {
            "pm_session_id": pm_session_id,
            "objective": objective,
            "owner_pm": owner_pm,
            "project_key": project_key,
        }
        for binding in bindings:
            by_run.setdefault(binding.run_id, []).append(metadata)
    return by_run


def collect_workflows(
    *,
    runs_root: Path,
    runtime_root: Path | None = None,
    read_events_fn: Callable[[str], list[dict]] | None = None,
    persist_case_snapshot: bool = True,
) -> dict[str, dict]:
    workflows: dict[str, dict] = {}
    resolved_runtime_root = runtime_root or runs_root.parent
    case_store = WorkflowCaseStore(
        resolved_runtime_root / "workflow-cases",
        ensure_storage=persist_case_snapshot,
    )
    session_meta_by_run = _session_case_metadata(resolved_runtime_root)
    for run_dir in sorted(runs_root.glob("*")):
        manifest_path = run_dir / "manifest.json"
        if not manifest_path.exists():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        workflow = manifest.get("workflow") if isinstance(manifest.get("workflow"), dict) else None
        if not workflow:
            continue
        workflow_id = str(workflow.get("workflow_id", "")).strip()
        if not workflow_id:
            continue
        entry = workflows.setdefault(
            workflow_id,
            {
                "workflow_id": workflow_id,
                "task_queue": workflow.get("task_queue", ""),
                "namespace": workflow.get("namespace", ""),
                "status": workflow.get("status", ""),
                "verdict": "",
                "summary": "",
                "objective": "",
                "owner_pm": "",
                "project_key": "",
                "pm_session_ids": [],
                "case_source": "derived",
                "case_updated_at": "",
                "runs": [],
                "_latest_ts": datetime.min.replace(tzinfo=timezone.utc),
                "_has_failure": False,
                "_has_running": False,
                "_has_pending_approval": False,
                "_latest_role_binding_ts": datetime.min.replace(tzinfo=timezone.utc),
                "_latest_role_binding_key": (datetime.min.replace(tzinfo=timezone.utc), ""),
            },
        )
        created_raw = manifest.get("created_at") or manifest.get("start_ts")
        try:
            created_at = (
                datetime.fromisoformat(str(created_raw).replace("Z", "+00:00"))
                if created_raw
                else datetime.fromtimestamp(manifest_path.stat().st_mtime, tz=timezone.utc)
            )
        except Exception:  # noqa: BLE001
            created_at = datetime.fromtimestamp(manifest_path.stat().st_mtime, tz=timezone.utc)
        entry["runs"].append(
            {
                "run_id": manifest.get("run_id"),
                "task_id": manifest.get("task_id"),
                "status": manifest.get("status"),
                "created_at": manifest.get("created_at") or manifest.get("start_ts"),
            }
        )
        current_run_id = str(manifest.get("run_id") or run_dir.name).strip()
        role_binding_summary = (
            manifest.get("role_binding_summary")
            if isinstance(manifest.get("role_binding_summary"), dict)
            else {}
        )
        latest_role_binding_key = (created_at, current_run_id)
        if role_binding_summary and latest_role_binding_key > entry["_latest_role_binding_key"]:
            entry["_latest_role_binding_ts"] = created_at
            entry["_latest_role_binding_key"] = latest_role_binding_key
            entry["workflow_case_read_model"] = {
                "authority": "workflow-case-read-model",
                "source": "latest linked run manifest.role_binding_summary",
                "execution_authority": "task_contract",
                "workflow_id": workflow_id,
                "source_run_id": current_run_id,
                "role_binding_summary": role_binding_summary,
            }
        for metadata in session_meta_by_run.get(current_run_id, []):
            session_id = str(metadata.get("pm_session_id") or "").strip()
            if session_id and session_id not in entry["pm_session_ids"]:
                entry["pm_session_ids"].append(session_id)
            if not entry["objective"] and str(metadata.get("objective") or "").strip():
                entry["objective"] = str(metadata.get("objective") or "").strip()
            if not entry["owner_pm"] and str(metadata.get("owner_pm") or "").strip():
                entry["owner_pm"] = str(metadata.get("owner_pm") or "").strip()
            if not entry["project_key"] and str(metadata.get("project_key") or "").strip():
                entry["project_key"] = str(metadata.get("project_key") or "").strip()
        status = workflow.get("status")
        if isinstance(status, str) and status.strip() and created_at >= entry["_latest_ts"]:
            entry["status"] = status
            entry["task_queue"] = workflow.get("task_queue", entry["task_queue"])
            entry["namespace"] = workflow.get("namespace", entry["namespace"])
            entry["_latest_ts"] = created_at
        status_upper = str(manifest.get("status") or "").strip().upper()
        if status_upper in {"FAILURE", "FAILED", "ERROR", "REJECTED", "CANCELLED"}:
            entry["_has_failure"] = True
        if status_upper in {"RUNNING", "PENDING", "QUEUED", "IN_PROGRESS"}:
            entry["_has_running"] = True
        if callable(read_events_fn):
            events = read_events_fn(current_run_id)
            last_required_index: int | None = None
            for index, event in enumerate(events):
                if isinstance(event, dict) and str(event.get("event") or "").upper() == "HUMAN_APPROVAL_REQUIRED":
                    last_required_index = index
            if last_required_index is not None:
                completed = False
                for event in events[last_required_index + 1 :]:
                    if isinstance(event, dict) and str(event.get("event") or "").upper() == "HUMAN_APPROVAL_COMPLETED":
                        completed = True
                        break
                if not completed:
                    entry["_has_pending_approval"] = True
    for entry in workflows.values():
        if entry.pop("_has_pending_approval", False):
            entry["verdict"] = "awaiting_approval"
        elif entry.pop("_has_failure", False):
            entry["verdict"] = "attention_required"
        elif entry.pop("_has_running", False):
            entry["verdict"] = "active"
        else:
            entry["verdict"] = "healthy"
        objective = str(entry.get("objective") or "").strip()
        if objective:
            entry["summary"] = objective
        elif entry["verdict"] == "awaiting_approval":
            entry["summary"] = "At least one linked run is waiting for human approval."
        elif entry["verdict"] == "attention_required":
            entry["summary"] = "At least one linked run failed and needs operator attention."
        elif entry["verdict"] == "active":
            entry["summary"] = "Workflow case is still active and linked runs are moving."
        else:
            entry["summary"] = "Workflow case is healthy."
        persisted = case_store.read(str(entry.get("workflow_id") or ""))
        for key in ["objective", "owner_pm", "project_key", "summary", "verdict"]:
            if not entry.get(key) and str(persisted.get(key) or "").strip():
                entry[key] = str(persisted.get(key) or "").strip()
        if not entry.get("workflow_case_read_model") and isinstance(
            persisted.get("workflow_case_read_model"), dict
        ):
            entry["workflow_case_read_model"] = persisted["workflow_case_read_model"]
        merged_case = {
            "workflow_id": entry["workflow_id"],
            "namespace": entry.get("namespace", ""),
            "task_queue": entry.get("task_queue", ""),
            "status": entry.get("status", ""),
            "objective": entry.get("objective", ""),
            "owner_pm": entry.get("owner_pm", ""),
            "project_key": entry.get("project_key", ""),
            "verdict": entry.get("verdict", ""),
            "summary": entry.get("summary", ""),
            "pm_session_ids": list(entry.get("pm_session_ids") or []),
            "run_ids": [str(run.get("run_id") or "") for run in entry.get("runs", []) if str(run.get("run_id") or "").strip()],
        }
        if isinstance(entry.get("workflow_case_read_model"), dict):
            merged_case["workflow_case_read_model"] = entry["workflow_case_read_model"]
        if persist_case_snapshot:
            persisted_case = case_store.write(str(entry["workflow_id"]), merged_case)
            entry["case_source"] = str(persisted_case.get("case_source") or "persisted")
            entry["case_updated_at"] = str(persisted_case.get("updated_at") or "")
        else:
            entry["case_source"] = str(persisted.get("case_source") or "derived")
            entry["case_updated_at"] = str(persisted.get("updated_at") or "")
        entry.pop("_latest_ts", None)
        entry.pop("_latest_role_binding_ts", None)
        entry.pop("_latest_role_binding_key", None)
    return workflows
