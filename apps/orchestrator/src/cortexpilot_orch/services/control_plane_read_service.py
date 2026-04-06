from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
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
