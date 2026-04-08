from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable


def _as_record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_array(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _find_report(reports: list[dict[str, Any]], name: str) -> dict[str, Any]:
    for item in reports:
        if _as_text(item.get("name")) == name:
            return _as_record(item.get("data"))
    return {}


@dataclass(frozen=True)
class ControlPlaneReadService:
    list_runs_fn: Callable[[], list[dict[str, Any]]]
    get_run_fn: Callable[[str], dict[str, Any]]
    get_events_fn: Callable[[str], list[dict[str, Any]]]
    get_reports_fn: Callable[[str], list[dict[str, Any]]]
    list_workflows_fn: Callable[[], list[dict[str, Any]]]
    get_workflow_fn: Callable[[str], dict[str, Any]]
    list_queue_fn: Callable[..., list[dict[str, Any]]]
    list_pending_approvals_fn: Callable[[], list[dict[str, Any]]]
    list_diff_gate_fn: Callable[[], list[dict[str, Any]]]

    @classmethod
    def from_api_main(cls) -> "ControlPlaneReadService":
        from cortexpilot_orch.api import main as api_main
        from cortexpilot_orch.api import main_state_store_helpers
        from cortexpilot_orch.queue import QueueStore

        def _list_workflows_readonly() -> list[dict[str, Any]]:
            workflows = list(
                main_state_store_helpers.collect_workflows(
                    runs_root=api_main.load_config().runs_root,
                    runtime_root=api_main.load_config().runtime_root,
                    read_events_fn=api_main._read_events,
                    persist_case_snapshot=False,
                ).values()
            )

            def _latest_ts(entry: dict[str, Any]) -> datetime:
                latest = None
                for run in _as_array(entry.get("runs")):
                    created_at = _as_text(_as_record(run).get("created_at"))
                    if not created_at:
                        continue
                    try:
                        timestamp = api_main._parse_iso_ts(created_at)
                    except Exception:
                        continue
                    if latest is None or timestamp > latest:
                        latest = timestamp
                return latest or datetime.fromtimestamp(0, tz=timezone.utc)

            workflows.sort(key=_latest_ts, reverse=True)
            return workflows

        def _get_workflow_readonly(workflow_id: str) -> dict[str, Any]:
            workflows = {
                entry["workflow_id"]: entry
                for entry in _list_workflows_readonly()
                if _as_text(_as_record(entry).get("workflow_id"))
            }
            entry = _as_record(workflows.get(workflow_id))
            if not entry:
                raise KeyError(f"workflow `{workflow_id}` not found")

            events: list[dict[str, Any]] = []
            for run in _as_array(entry.get("runs")):
                run_id = _as_text(_as_record(run).get("run_id"))
                if not run_id:
                    continue
                for item in _as_array(api_main._read_events(run_id)):
                    event = _as_record(item)
                    context = _as_record(event.get("context"))
                    workflow_match = _as_text(context.get("workflow_id")) == workflow_id
                    if _as_text(event.get("event")) in {
                        "WORKFLOW_BOUND",
                        "WORKFLOW_STATUS",
                        "TEMPORAL_NOTIFY_START",
                        "TEMPORAL_NOTIFY_DONE",
                    } or workflow_match:
                        event["_run_id"] = run_id
                        events.append(event)

            events.sort(key=lambda event: _as_text(event.get("ts") or event.get("_ts")), reverse=True)
            return {
                "workflow": entry,
                "runs": _as_array(entry.get("runs")),
                "events": events,
            }

        def _list_queue_readonly(*, workflow_id: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
            store = QueueStore(ensure_storage=False)
            items = store.list_items()
            normalized_workflow = _as_text(workflow_id)
            normalized_status = _as_text(status).upper()
            filtered: list[dict[str, Any]] = []
            for item in items:
                record = _as_record(item)
                if normalized_workflow and _as_text(record.get("workflow_id")) != normalized_workflow:
                    continue
                if normalized_status and _as_text(record.get("status")).upper() != normalized_status:
                    continue
                filtered.append(record)
            return filtered

        return cls(
            list_runs_fn=api_main.list_runs,
            get_run_fn=api_main.get_run,
            get_events_fn=api_main.get_events,
            get_reports_fn=api_main.get_reports,
            list_workflows_fn=_list_workflows_readonly,
            get_workflow_fn=_get_workflow_readonly,
            list_queue_fn=_list_queue_readonly,
            list_pending_approvals_fn=api_main.list_pending_approvals,
            list_diff_gate_fn=api_main.list_diff_gate,
        )

    @classmethod
    def from_runtime(cls) -> "ControlPlaneReadService":
        from cortexpilot_orch.api import main_run_views_helpers
        from cortexpilot_orch.api import main_state_store_helpers
        from cortexpilot_orch.config import load_config
        from cortexpilot_orch.contract.compiler import build_role_binding_summary
        from cortexpilot_orch.queue import QueueStore

        cfg = load_config()
        runs_root = cfg.runs_root
        runtime_root = cfg.runtime_root

        def _read_json(path: Path, default: object) -> object:
            if not path.exists():
                return default
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return default

        def _parse_iso_ts(value: str) -> datetime:
            normalized = str(value or "").strip()
            if not normalized:
                return datetime.fromtimestamp(0, tz=timezone.utc)
            if normalized.endswith("Z"):
                normalized = normalized[:-1] + "+00:00"
            return datetime.fromisoformat(normalized)

        def _load_contract(run_id: str) -> dict[str, Any]:
            payload = _read_json(runs_root / run_id / "contract.json", {})
            return payload if isinstance(payload, dict) else {}

        def _read_events(run_id: str) -> list[dict[str, Any]]:
            return main_state_store_helpers.read_events(run_id=run_id, runs_root=runs_root)

        def _last_event_ts(run_id: str) -> str:
            events = _read_events(run_id)
            for event in reversed(events):
                if isinstance(event, dict):
                    value = str(event.get("ts") or event.get("_ts") or "").strip()
                    if value:
                        return value
            return ""

        def _list_runs_runtime() -> list[dict[str, Any]]:
            results: list[dict[str, Any]] = []
            for run_dir in sorted(runs_root.glob("*"), key=lambda item: item.stat().st_mtime, reverse=True):
                manifest = _read_json(run_dir / "manifest.json", {})
                manifest_record = _as_record(manifest)
                if not manifest_record:
                    continue
                run_id = _as_text(manifest_record.get("run_id")) or run_dir.name
                payload = dict(manifest_record)
                payload["run_id"] = run_id
                payload["status"] = _as_text(manifest_record.get("status")) or "UNKNOWN"
                payload["last_event_ts"] = _last_event_ts(run_id)
                results.append(payload)
            return results

        def _get_run_runtime(run_id: str) -> dict[str, Any]:
            run_dir = runs_root / run_id
            manifest = _as_record(_read_json(run_dir / "manifest.json", {}))
            if not manifest:
                raise KeyError(f"run `{run_id}` not found")
            contract = _load_contract(run_id)
            normalized_contract = contract if isinstance(contract, dict) else {}
            persisted_role_binding = _as_record(manifest.get("role_binding_summary"))
            allowed_paths = _as_array(normalized_contract.get("allowed_paths"))
            return {
                "run_id": run_id,
                "task_id": manifest.get("task_id") or normalized_contract.get("task_id"),
                "allowed_paths": allowed_paths,
                "role_binding_read_model": persisted_role_binding
                or build_role_binding_summary(normalized_contract),
                "manifest": manifest,
                "contract": normalized_contract,
                "status": _as_text(manifest.get("status")) or "UNKNOWN",
                "last_event_ts": _last_event_ts(run_id),
            }

        def _get_reports_runtime(run_id: str) -> list[dict[str, Any]]:
            reports_dir = runs_root / run_id / "reports"
            if not reports_dir.exists():
                return []
            results: list[dict[str, Any]] = []
            for report_path in sorted(reports_dir.glob("*.json")):
                payload = _read_json(report_path, {})
                results.append({"name": report_path.name, "data": payload})
            return results

        def _list_workflows_runtime() -> list[dict[str, Any]]:
            workflows = list(
                main_state_store_helpers.collect_workflows(
                    runs_root=runs_root,
                    runtime_root=runtime_root,
                    read_events_fn=_read_events,
                    persist_case_snapshot=False,
                ).values()
            )

            def _latest_ts(entry: dict[str, Any]) -> datetime:
                latest = None
                for run in _as_array(entry.get("runs")):
                    created_at = _as_text(_as_record(run).get("created_at"))
                    if not created_at:
                        continue
                    try:
                        timestamp = _parse_iso_ts(created_at)
                    except Exception:
                        continue
                    if latest is None or timestamp > latest:
                        latest = timestamp
                return latest or datetime.fromtimestamp(0, tz=timezone.utc)

            workflows.sort(key=_latest_ts, reverse=True)
            return workflows

        def _get_workflow_runtime(workflow_id: str) -> dict[str, Any]:
            workflows = {
                entry["workflow_id"]: entry
                for entry in _list_workflows_runtime()
                if _as_text(_as_record(entry).get("workflow_id"))
            }
            entry = _as_record(workflows.get(workflow_id))
            if not entry:
                raise KeyError(f"workflow `{workflow_id}` not found")

            events: list[dict[str, Any]] = []
            for run in _as_array(entry.get("runs")):
                run_id = _as_text(_as_record(run).get("run_id"))
                if not run_id:
                    continue
                for item in _as_array(_read_events(run_id)):
                    event = _as_record(item)
                    context = _as_record(event.get("context"))
                    workflow_match = _as_text(context.get("workflow_id")) == workflow_id
                    if _as_text(event.get("event")) in {
                        "WORKFLOW_BOUND",
                        "WORKFLOW_STATUS",
                        "TEMPORAL_NOTIFY_START",
                        "TEMPORAL_NOTIFY_DONE",
                    } or workflow_match:
                        event["_run_id"] = run_id
                        events.append(event)

            events.sort(key=lambda event: _as_text(event.get("ts") or event.get("_ts")), reverse=True)
            return {
                "workflow": entry,
                "runs": _as_array(entry.get("runs")),
                "events": events,
            }

        def _list_queue_runtime(*, workflow_id: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
            store = QueueStore(ensure_storage=False)
            items = store.list_items()
            normalized_workflow = _as_text(workflow_id)
            normalized_status = _as_text(status).upper()
            filtered: list[dict[str, Any]] = []
            for item in items:
                record = _as_record(item)
                if normalized_workflow and _as_text(record.get("workflow_id")) != normalized_workflow:
                    continue
                if normalized_status and _as_text(record.get("status")).upper() != normalized_status:
                    continue
                filtered.append(record)
            return filtered

        def _list_pending_approvals_runtime() -> list[dict[str, Any]]:
            pending: list[dict[str, Any]] = []
            for run_dir in runs_root.glob("*"):
                run_id = run_dir.name
                events = _read_events(run_id)
                required_events = [ev for ev in events if isinstance(ev, dict) and ev.get("event") == "HUMAN_APPROVAL_REQUIRED"]
                if not required_events:
                    continue
                latest_index = max(i for i, ev in enumerate(events) if isinstance(ev, dict) and ev.get("event") == "HUMAN_APPROVAL_REQUIRED")
                completed = any(
                    isinstance(ev, dict) and ev.get("event") == "HUMAN_APPROVAL_COMPLETED"
                    for ev in events[latest_index + 1 :]
                )
                if completed:
                    continue
                latest = _as_record(required_events[-1])
                context = _as_record(latest.get("context") or latest.get("meta"))
                manifest_payload = _as_record(_read_json(run_dir / "manifest.json", {}))
                contract_payload = _as_record(_read_json(run_dir / "contract.json", {}))
                task_id = _as_text(manifest_payload.get("task_id")) or _as_text(contract_payload.get("task_id"))
                failure_reason = _as_text(manifest_payload.get("failure_reason"))
                pending.append(
                    {
                        "run_id": run_id,
                        "status": "pending",
                        "task_id": task_id,
                        "failure_reason": failure_reason,
                        "reason": _as_array(context.get("reason")),
                        "actions": _as_array(context.get("actions")),
                        "verify_steps": _as_array(context.get("verify_steps")),
                        "resume_step": _as_text(context.get("resume_step")),
                    }
                )
            return pending

        def _list_diff_gate_runtime() -> list[dict[str, Any]]:
            return main_run_views_helpers.list_diff_gate(
                runs_root=runs_root,
                read_events_fn=_read_events,
                read_json_fn=_read_json,
            )

        return cls(
            list_runs_fn=_list_runs_runtime,
            get_run_fn=_get_run_runtime,
            get_events_fn=_read_events,
            get_reports_fn=_get_reports_runtime,
            list_workflows_fn=_list_workflows_runtime,
            get_workflow_fn=_get_workflow_runtime,
            list_queue_fn=_list_queue_runtime,
            list_pending_approvals_fn=_list_pending_approvals_runtime,
            list_diff_gate_fn=_list_diff_gate_runtime,
        )

    def list_runs(self) -> list[dict[str, Any]]:
        return self.list_runs_fn()

    def get_run(self, run_id: str) -> dict[str, Any]:
        return self.get_run_fn(run_id)

    def get_run_events(self, run_id: str) -> list[dict[str, Any]]:
        return self.get_events_fn(run_id)

    def get_run_reports(self, run_id: str) -> list[dict[str, Any]]:
        reports = self.get_reports_fn(run_id)
        return reports if isinstance(reports, list) else []

    def list_workflows(self) -> list[dict[str, Any]]:
        return self.list_workflows_fn()

    def get_workflow(self, workflow_id: str) -> dict[str, Any]:
        return self.get_workflow_fn(workflow_id)

    def list_queue(self, *, workflow_id: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        return self.list_queue_fn(workflow_id=workflow_id, status=status)

    def get_pending_approvals(self, *, run_id: str | None = None) -> list[dict[str, Any]]:
        approvals = self.list_pending_approvals_fn()
        if not run_id:
            return approvals if isinstance(approvals, list) else []
        return [
            item
            for item in _as_array(approvals)
            if _as_text(_as_record(item).get("run_id")) == run_id
        ]

    def get_diff_gate_state(self, *, run_id: str | None = None) -> list[dict[str, Any]]:
        items = self.list_diff_gate_fn()
        if not run_id:
            return items if isinstance(items, list) else []
        return [
            item
            for item in _as_array(items)
            if _as_text(_as_record(item).get("run_id")) == run_id
        ]

    def get_compare_summary(self, run_id: str) -> dict[str, Any]:
        report = _find_report(self.get_run_reports(run_id), "run_compare_report.json")
        return _as_record(report.get("compare_summary"))

    def get_proof_summary(self, run_id: str) -> dict[str, Any]:
        return _find_report(self.get_run_reports(run_id), "proof_pack.json")

    def get_incident_summary(self, run_id: str) -> dict[str, Any]:
        return _find_report(self.get_run_reports(run_id), "incident_pack.json")
