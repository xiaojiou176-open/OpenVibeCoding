from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from fastapi import HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from openvibecoding_orch.api import search_payload_helpers
from openvibecoding_orch.contract.compiler import build_role_binding_summary
from openvibecoding_orch.contract.role_config_registry import (
    apply_role_config_entry,
    build_role_config_surface,
    preview_role_config_entry,
)
from tooling.search_pipeline import build_evidence_bundle


_logger = logging.getLogger(__name__)


class _NoOpQueueStore:
    def list_items(self) -> list[dict[str, Any]]:
        return []

    def enqueue(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {}

    def claim_next(self, **_kwargs: Any) -> dict[str, Any] | None:
        return None

    def mark_done(self, *_args: Any, **_kwargs: Any) -> None:
        return None


def _is_valid_role_binding_summary_payload(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    required = {
        "authority",
        "source",
        "execution_authority",
        "skills_bundle_ref",
        "mcp_bundle_ref",
        "runtime_binding",
    }
    return required.issubset(payload.keys())


def build_runs_handlers(
    *,
    runs_root_fn: Callable[[], Path],
    load_contract_fn: Callable[[str], dict],
    parse_iso_ts_fn: Callable[[str], datetime],
    select_baseline_by_window_fn: Callable[[str, dict], str | None],
    last_event_ts_fn: Callable[[str], str],
    collect_workflows_fn: Callable[[], dict[str, dict]],
    queue_store_cls: Callable[[], Any] = _NoOpQueueStore,
    read_events_fn: Callable[[str], list[dict]],
    filter_events_fn: Callable[..., list[dict]],
    event_cursor_value_fn: Callable[[dict[str, Any]], str],
    safe_artifact_target_fn: Callable[[str, str], Path],
    read_artifact_fn: Callable[[str, str], object | None],
    read_report_fn: Callable[[str, str], object | None],
    extract_search_queries_fn: Callable[[dict], list[str]],
    list_pending_approvals_fn: Callable[[], list[dict[str, Any]]] = lambda: [],
    promote_evidence_fn: Callable[[str, dict[str, Any]], dict[str, Any]],
    orchestration_service_fn: Callable[[], Any],
    load_config_fn: Callable[[], Any],
    error_detail_fn: Callable[[str], dict[str, str]],
    current_request_id_fn: Callable[[], str],
    log_event_fn: Callable[..., None],
    json_loads_fn: Callable[[str], object],
    json_decode_error_cls: type[Exception],
    list_diff_gate_fn: Callable[[], list[dict]],
    rollback_run_fn: Callable[[str], dict],
    reject_run_fn: Callable[[str], dict],
    list_reviews_fn: Callable[[], list[dict]],
    list_tests_fn: Callable[[], list[dict]],
    list_agents_fn: Callable[[], dict],
    list_agents_status_fn: Callable[[str | None], dict],
    list_policies_fn: Callable[[], dict],
    list_locks_fn: Callable[[], list[dict]],
    list_worktrees_fn: Callable[[], list[dict]],
    read_manifest_status_fn: Callable[[str], str] = lambda _run_id: "UNKNOWN",
    read_events_incremental_fn: Callable[..., tuple[list[dict[str, Any]], int]] | None = None,
) -> dict[str, Callable[..., Any]]:
    def _read_events_light(run_dir: Path) -> list[dict[str, Any]]:
        events_path = run_dir / "events.jsonl"
        if not events_path.exists():
            return []
        items: list[dict[str, Any]] = []
        for raw in events_path.read_text(encoding="utf-8").splitlines():
            text = raw.strip()
            if not text:
                continue
            try:
                payload = json_loads_fn(text)
            except Exception as exc:  # noqa: BLE001
                _logger.debug("main_runs_handlers: skip invalid event line: %s", exc)
                continue
            if isinstance(payload, dict):
                items.append(payload)
        return items

    def _as_dict(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    def _safe_load_json(path: Path) -> dict[str, Any] | None:
        try:
            payload = json_loads_fn(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            _logger.debug("main_runs_handlers: _safe_load_json failed for %s: %s", path, exc)
            return None
        return payload if isinstance(payload, dict) else None

    def _normalize_contract(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    def _normalize_optional_text(value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

    def _normalize_string_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in value:
            text = str(raw or "").strip()
            if not text or text in seen:
                continue
            normalized.append(text)
            seen.add(text)
        return normalized

    def _normalize_acceptance_tests(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        normalized: list[str] = []
        for raw in value:
            if isinstance(raw, str):
                text = raw.strip()
            else:
                text = json.dumps(raw, ensure_ascii=False, sort_keys=True)
            if text:
                normalized.append(text)
        return normalized

    def _normalize_role(role: Any) -> str:
        normalized = str(role or "").strip().upper()
        if not normalized:
            raise HTTPException(status_code=400, detail={"code": "ROLE_CONFIG_ROLE_REQUIRED"})
        return normalized

    def _role_config_error(status_code: int, code: str, reason: str) -> HTTPException:
        return HTTPException(status_code=status_code, detail={"code": code, "reason": reason})

    def _is_rejected_diff_gate(event: dict[str, Any]) -> bool:
        name = str(event.get("event") or "")
        if name in {"DIFF_GATE_REJECTED", "DIFF_GATE_FAIL"}:
            return True
        if name != "DIFF_GATE_RESULT":
            return False
        context = _as_dict(event.get("context"))
        meta = _as_dict(event.get("meta"))
        candidates = [
            str(context.get("result") or ""),
            str(context.get("status") or ""),
            str(meta.get("result") or ""),
            str(meta.get("status") or ""),
        ]
        return any(item.upper() == "REJECTED" for item in candidates)

    def _infer_failure_fields(
        *,
        status: str,
        manifest: dict[str, Any],
        events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        existing = {
            "failure_class": manifest.get("failure_class"),
            "failure_code": manifest.get("failure_code"),
            "failure_stage": manifest.get("failure_stage"),
            "failure_summary_zh": manifest.get("failure_summary_zh"),
            "action_hint_zh": manifest.get("action_hint_zh"),
            "root_event": manifest.get("root_event"),
        }

        for event in reversed(events):
            name = str(event.get("event") or "")
            meta = _as_dict(event.get("meta"))
            if _is_rejected_diff_gate(event):
                existing.update(
                    {
                        "failure_class": "gate",
                        "failure_code": "DIFF_GATE_REJECTED",
                        "failure_stage": "diff_gate",
                        "failure_summary_zh": "Rule blocked: the diff gate rejected the change and the run was denied.",
                        "action_hint_zh": "Review the diff-gate rule and evidence, then resubmit.",
                        "root_event": name or "DIFF_GATE_RESULT",
                    }
                )
                break
            if name == "HUMAN_APPROVAL_REQUIRED":
                existing.update(
                    {
                        "failure_class": "manual",
                        "failure_code": "HUMAN_APPROVAL_REQUIRED",
                        "failure_stage": "approval",
                        "failure_summary_zh": "Manual confirmation required: the run is waiting for human approval and did not continue automatically.",
                        "action_hint_zh": "Complete the approval in the control panel, then retry.",
                        "root_event": name,
                    }
                )
                break
            if name == "ROLLBACK_APPLIED" and str(meta.get("reason") or "") == "worktree_ref missing":
                existing.update(
                    {
                        "failure_class": "env",
                        "failure_code": "ROLLBACK_WORKTREE_REF_MISSING",
                        "failure_stage": "rollback",
                        "failure_summary_zh": "Rollback failed: missing worktree_ref reference.",
                        "action_hint_zh": "Confirm that worktree_ref.txt exists in the run directory and points to a valid path.",
                        "root_event": name,
                    }
                )
                break

        if str(status).upper() == "FAILURE":
            failure_reason = str(manifest.get("failure_reason") or "").strip()
            if "diff gate" in failure_reason.lower() and not existing.get("failure_class"):
                existing.update(
                    {
                        "failure_class": "gate",
                        "failure_code": "DIFF_GATE_REJECTED",
                        "failure_stage": "diff_gate",
                        "failure_summary_zh": "Rule blocked: the diff gate rejected the change and the run was denied.",
                        "action_hint_zh": "Review the diff-gate rule and evidence, then resubmit.",
                        "root_event": existing.get("root_event") or "DIFF_GATE_RESULT",
                    }
                )
            if not existing.get("failure_class"):
                existing["failure_class"] = "product"
            if not existing.get("failure_code"):
                existing["failure_code"] = "FAILURE_REASON" if failure_reason else "FAILURE_UNKNOWN"
            if not existing.get("failure_stage"):
                existing["failure_stage"] = "runtime"
            if not existing.get("failure_summary_zh"):
                existing["failure_summary_zh"] = (
                    f"Run failed: {failure_reason}" if failure_reason else "Run failed with no explicit reason provided."
                )
            if not existing.get("action_hint_zh"):
                existing["action_hint_zh"] = "Review events.jsonl and logs, identify the root cause, then retry."
            if not existing.get("root_event"):
                existing["root_event"] = manifest.get("root_event") or "UNKNOWN"

        return {
            "failure_class": existing.get("failure_class") or "",
            "failure_code": existing.get("failure_code") or "",
            "failure_stage": existing.get("failure_stage") or "",
            "failure_summary_zh": existing.get("failure_summary_zh") or "",
            "action_hint_zh": existing.get("action_hint_zh") or "",
            "root_event": existing.get("root_event") or "",
        }

    def _resolve_outcome(status: str, failure_class: str) -> dict[str, str]:
        status_upper = str(status or "").upper()
        if status_upper in {"SUCCESS", "SUCCEEDED", "COMPLETED", "DONE"}:
            return {"outcome_type": "success", "outcome_label_zh": "Success"}
        if status_upper in {"FAILURE", "FAILED", "REJECTED", "ERROR"}:
            class_token = str(failure_class or "").strip().lower()
            if class_token == "gate":
                return {"outcome_type": "gate", "outcome_label_zh": "Rule blocked"}
            if class_token == "manual":
                return {"outcome_type": "manual", "outcome_label_zh": "Manual confirmation required"}
            if class_token == "env":
                return {"outcome_type": "env", "outcome_label_zh": "Environment issue"}
            if class_token == "product":
                return {"outcome_type": "product", "outcome_label_zh": "Functional anomaly"}
            if class_token == "unknown":
                return {"outcome_type": "product", "outcome_label_zh": "Functional anomaly"}
            return {"outcome_type": "failure", "outcome_label_zh": "Functional anomaly"}
        if status_upper in {"RUNNING", "PENDING", "QUEUED", "IN_PROGRESS", "PAUSED"}:
            return {"outcome_type": "in_progress", "outcome_label_zh": "In progress"}
        return {"outcome_type": "unknown", "outcome_label_zh": "Unknown"}

    def _has_pending_approval(events: list[dict[str, Any]]) -> bool:
        last_required_index: int | None = None
        for index, event in enumerate(events):
            if isinstance(event, dict) and str(event.get("event") or "").upper() == "HUMAN_APPROVAL_REQUIRED":
                last_required_index = index
        if last_required_index is None:
            return False
        for event in events[last_required_index + 1 :]:
            if isinstance(event, dict) and str(event.get("event") or "").upper() == "HUMAN_APPROVAL_COMPLETED":
                return False
        return True

    def _build_incident_pack(run_id: str, manifest: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any] | None:
        status = str(manifest.get("status") or "").strip()
        failure_attrs = _infer_failure_fields(status=status, manifest=manifest, events=events)
        failure_reason = str(manifest.get("failure_reason") or "").strip()
        pending_approval = _has_pending_approval(events)
        failure_class = str(failure_attrs.get("failure_class") or "").strip()
        if not failure_class and not pending_approval and str(status).upper() not in {"FAILURE", "FAILED", "ERROR", "REJECTED"}:
            return None

        blocking_events: list[str] = []
        for event in reversed(events):
            event_name = str(event.get("event") or event.get("event_type") or "").strip()
            if not event_name:
                continue
            if event_name in {
                "HUMAN_APPROVAL_REQUIRED",
                "HUMAN_APPROVAL_TIMEOUT",
                "DIFF_GATE_REJECTED",
                "DIFF_GATE_RESULT",
                "ROLLBACK_APPLIED",
                "GATE_FAILED",
                "POLICY_VIOLATION",
            }:
                blocking_events.append(event_name)
            if len(blocking_events) >= 3:
                break

        if pending_approval:
            summary = "This run is waiting for human approval before execution can continue."
            next_action = "Open the manual approvals surface, review the required steps, and approve the run when the blocking checks are complete."
        elif failure_class == "gate":
            summary = failure_reason or "This run was blocked by a governance gate."
            next_action = str(failure_attrs.get("action_hint_zh") or "Review the blocking gate and rerun after fixing the violation.")
        else:
            summary = failure_reason or str(failure_attrs.get("failure_summary_zh") or "This run failed without an explicit summary.")
            next_action = str(failure_attrs.get("action_hint_zh") or "Review events, reports, and logs to identify the root cause before retrying.")

        return {
            "report_type": "incident_pack",
            "run_id": run_id,
            "status": status,
            "summary": summary,
            "failure_class": "manual" if pending_approval and not failure_class else failure_class,
            "failure_code": str(failure_attrs.get("failure_code") or ""),
            "failure_stage": "approval" if pending_approval and not failure_attrs.get("failure_stage") else str(failure_attrs.get("failure_stage") or ""),
            "failure_reason": failure_reason,
            "root_event": "HUMAN_APPROVAL_REQUIRED" if pending_approval and not failure_attrs.get("root_event") else str(failure_attrs.get("root_event") or ""),
            "next_action": next_action,
            "blocking_events": blocking_events,
        }

    def _build_proof_pack(
        run_id: str,
        manifest: dict[str, Any],
        reports: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        status = str(manifest.get("status") or "").strip().upper()
        if status not in {"SUCCESS", "SUCCEEDED", "COMPLETED", "DONE"}:
            return None

        public_reports = [
            ("news_digest_result.json", "news_digest"),
            ("topic_brief_result.json", "topic_brief"),
            ("page_brief_result.json", "page_brief"),
        ]
        report_lookup: dict[str, dict[str, Any]] = {}
        for item in reports:
            name = str(item.get("name") or "").strip()
            data = item.get("data")
            if name and isinstance(data, dict):
                report_lookup[name] = data

        for report_name, task_template in public_reports:
            payload = report_lookup.get(report_name)
            if not payload:
                continue
            result_status = str(payload.get("status") or "").strip().upper()
            if result_status != "SUCCESS":
                continue
            summary = str(payload.get("summary") or "").strip()
            evidence_refs = payload.get("evidence_refs") if isinstance(payload.get("evidence_refs"), dict) else {}
            proof_ready = bool(evidence_refs)
            return {
                "report_type": "proof_pack",
                "run_id": run_id,
                "task_template": task_template,
                "primary_report": report_name,
                "summary": summary or "This public task slice completed successfully and produced reusable proof artifacts.",
                "result_status": result_status,
                "proof_ready": proof_ready,
                "evidence_refs": evidence_refs,
                "next_action": (
                    "Review the primary report and evidence bundle before sharing the public proof output."
                    if proof_ready
                    else "Generate or refresh evidence artifacts before sharing this proof."
                ),
            }
        return None

    def list_runs() -> list[dict]:
        runs: list[dict[str, Any]] = []
        for run_dir in runs_root_fn().glob("*"):
            manifest_path = run_dir / "manifest.json"
            if not manifest_path.exists():
                continue
            manifest = _safe_load_json(manifest_path)
            if manifest is None:
                continue
            workflow = manifest.get("workflow", {}) if isinstance(manifest.get("workflow"), dict) else {}
            created_at = manifest.get("created_at") or manifest.get("start_ts")
            finished_at = manifest.get("finished_at") or manifest.get("end_ts")
            mtime = manifest_path.stat().st_mtime
            try:
                contract = _normalize_contract(load_contract_fn(run_dir.name))
            except Exception as exc:  # noqa: BLE001
                _logger.debug("main_runs_handlers: load_contract_fn failed for %s: %s", run_dir.name, exc)
                contract = {}
            owner = contract.get("owner_agent", {}) if isinstance(contract.get("owner_agent"), dict) else {}
            assigned = contract.get("assigned_agent", {}) if isinstance(contract.get("assigned_agent"), dict) else {}
            failure_reason = manifest.get("failure_reason", "")
            status = str(manifest.get("status") or "")
            events = _read_events_light(run_dir)
            failure_attrs = _infer_failure_fields(status=status, manifest=manifest, events=events)
            outcome = _resolve_outcome(status, str(failure_attrs.get("failure_class") or ""))
            sort_ts = mtime
            if isinstance(created_at, str) and created_at.strip():
                try:
                    sort_ts = parse_iso_ts_fn(created_at).timestamp()
                except Exception as exc:  # noqa: BLE001
                    _logger.debug("main_runs_handlers: parse_iso_ts_fn failed for %s: %s", created_at, exc)
                    sort_ts = mtime
            runs.append(
                {
                    "run_id": manifest.get("run_id"),
                    "task_id": manifest.get("task_id"),
                    "status": manifest.get("status"),
                    "workflow_id": workflow.get("workflow_id", ""),
                    "workflow_status": workflow.get("status", ""),
                    "created_at": created_at,
                    "finished_at": finished_at,
                    "start_ts": created_at,
                    "end_ts": finished_at,
                    "owner_agent_id": owner.get("agent_id", ""),
                    "owner_role": owner.get("role", ""),
                    "assigned_agent_id": assigned.get("agent_id", ""),
                    "assigned_role": assigned.get("role", ""),
                    "failure_reason": failure_reason,
                    "last_event_ts": last_event_ts_fn(run_dir.name),
                    **failure_attrs,
                    **outcome,
                    "_sort": sort_ts,
                }
            )
        runs.sort(key=lambda item: item.get("_sort", 0), reverse=True)
        for item in runs:
            item.pop("_sort", None)
        return runs

    def list_workflows() -> list[dict]:
        workflows = list(collect_workflows_fn().values())

        def _latest_ts(entry: dict) -> datetime:
            latest = None
            for run in entry.get("runs", []):
                created_at = run.get("created_at")
                if not created_at:
                    continue
                try:
                    ts = parse_iso_ts_fn(str(created_at))
                except Exception as exc:  # noqa: BLE001
                    _logger.debug("main_runs_handlers: _latest_ts parse failed: %s", exc)
                    continue
                if latest is None or ts > latest:
                    latest = ts
            return latest or datetime.fromtimestamp(0, tz=timezone.utc)

        workflows.sort(key=_latest_ts, reverse=True)
        return workflows

    def list_queue(workflow_id: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        store = queue_store_cls()
        items = store.list_items()
        normalized_workflow = str(workflow_id or "").strip()
        normalized_status = str(status or "").strip().upper()
        filtered: list[dict[str, Any]] = []
        for item in items:
            if normalized_workflow and str(item.get("workflow_id") or "").strip() != normalized_workflow:
                continue
            if normalized_status and str(item.get("status") or "").strip().upper() != normalized_status:
                continue
            filtered.append(item)
        return filtered

    def enqueue_run_queue(run_id: str, payload: dict | None = None) -> dict[str, Any]:
        run_dir = runs_root_fn() / run_id
        manifest_path = run_dir / "manifest.json"
        contract_path = run_dir / "contract.json"
        if not manifest_path.exists() or not contract_path.exists():
            raise HTTPException(status_code=404, detail=error_detail_fn("RUN_NOT_FOUND"))
        manifest = _safe_load_json(manifest_path) or {}
        contract = _safe_load_json(contract_path) or {}
        owner_agent = contract.get("owner_agent") if isinstance(contract.get("owner_agent"), dict) else {}
        workflow_meta = manifest.get("workflow") if isinstance(manifest.get("workflow"), dict) else {}
        queue_options = payload if isinstance(payload, dict) else {}
        task_id = str(contract.get("task_id") or manifest.get("task_id") or run_id).strip() or run_id
        owner = str(owner_agent.get("agent_id") or manifest.get("owner_agent_id") or "").strip()
        queue_item = queue_store_cls().enqueue(
            contract_path.resolve(),
            task_id,
            owner=owner,
            metadata={
                "workflow_id": str(workflow_meta.get("workflow_id") or "").strip(),
                "source_run_id": run_id,
                "priority": queue_options.get("priority", 0),
                "scheduled_at": queue_options.get("scheduled_at"),
                "deadline_at": queue_options.get("deadline_at"),
            },
        )
        return queue_item

    def preview_enqueue_run_queue(run_id: str, payload: dict | None = None) -> dict[str, Any]:
        run_dir = runs_root_fn() / run_id
        manifest_path = run_dir / "manifest.json"
        contract_path = run_dir / "contract.json"
        if not manifest_path.exists() or not contract_path.exists():
            raise HTTPException(status_code=404, detail=error_detail_fn("RUN_NOT_FOUND"))
        manifest = _safe_load_json(manifest_path) or {}
        contract = _safe_load_json(contract_path) or {}
        owner_agent = contract.get("owner_agent") if isinstance(contract.get("owner_agent"), dict) else {}
        workflow_meta = manifest.get("workflow") if isinstance(manifest.get("workflow"), dict) else {}
        queue_options = payload if isinstance(payload, dict) else {}
        task_id = str(contract.get("task_id") or manifest.get("task_id") or run_id).strip() or run_id
        owner = str(owner_agent.get("agent_id") or manifest.get("owner_agent_id") or "").strip()
        queue_store = queue_store_cls()
        preview_item = queue_store.preview_enqueue(
            contract_path.resolve(),
            task_id,
            owner=owner,
            metadata={
                "workflow_id": str(workflow_meta.get("workflow_id") or "").strip(),
                "source_run_id": run_id,
                "priority": queue_options.get("priority", 0),
                "scheduled_at": queue_options.get("scheduled_at"),
                "deadline_at": queue_options.get("deadline_at"),
            },
        )
        pending_matches = [
            item
            for item in queue_store.list_items()
            if str(item.get("source_run_id") or "").strip() == run_id
            and str(item.get("status") or "").strip().upper() == "PENDING"
        ]
        return {
            "run_id": run_id,
            "validation": "fail-closed",
            "can_apply": True,
            "preview_item": preview_item,
            "pending_matches": pending_matches,
            "changes": [
                {
                    "field": "queue",
                    "current": "already-pending" if pending_matches else "not-enqueued",
                    "next": "pending",
                }
            ],
            "boundary": {
                "pilot": "queue-enqueue-from-run-only",
                "execution_authority": "task_contract",
                "approval_mode": "manual-owner-default-off",
            },
        }

    def run_next_queue(payload: dict | None = None) -> dict[str, Any]:
        options = payload if isinstance(payload, dict) else {}
        mock_mode = bool(options.get("mock"))
        store = queue_store_cls()
        item = store.claim_next(run_id="")
        if not item:
            return {"ok": False, "reason": "queue empty"}
        contract_path = Path(str(item.get("contract_path") or "")).resolve()
        task_id = str(item.get("task_id") or "").strip() or "task"
        run_id = orchestration_service_fn().execute_task(contract_path, mock_mode=mock_mode)
        final_status = read_manifest_status_fn(run_id)
        store.mark_done(task_id, run_id, final_status, queue_id=str(item.get("queue_id") or ""))
        return {"ok": True, "run_id": run_id, "status": final_status, "queue_item": item}

    def cancel_queue_item(queue_id: str, payload: dict | None = None) -> dict[str, Any]:
        options = payload if isinstance(payload, dict) else {}
        reason = str(options.get("reason") or "").strip()
        cancelled_by = str(options.get("cancelled_by") or "").strip()
        try:
            return queue_store_cls().cancel(queue_id, reason=reason, cancelled_by=cancelled_by)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"code": "QUEUE_ITEM_NOT_FOUND"}) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail={"code": "QUEUE_ITEM_NOT_CANCELLABLE", "reason": str(exc)}) from exc

    def get_workflow(workflow_id: str) -> dict:
        workflows = collect_workflows_fn()
        entry = workflows.get(workflow_id)
        if not entry:
            raise HTTPException(status_code=404, detail=error_detail_fn("WORKFLOW_NOT_FOUND"))

        events: list[dict] = []
        for run in entry.get("runs", []):
            run_id = run.get("run_id")
            if not run_id:
                continue
            for ev in read_events_fn(str(run_id)):
                if not isinstance(ev, dict):
                    continue
                context = ev.get("context") if isinstance(ev.get("context"), dict) else {}
                workflow_match = context.get("workflow_id") == workflow_id
                if ev.get("event") in {
                    "WORKFLOW_BOUND",
                    "WORKFLOW_STATUS",
                    "TEMPORAL_NOTIFY_START",
                    "TEMPORAL_NOTIFY_DONE",
                } or workflow_match:
                    ev["_run_id"] = run_id
                    events.append(ev)

        def _event_key(ev: dict) -> str:
            return str(ev.get("ts") or ev.get("_ts") or "")

        events.sort(key=_event_key, reverse=True)
        return {
            "workflow": entry,
            "runs": entry.get("runs", []),
            "events": events,
        }

    def get_run(run_id: str) -> dict:
        run_dir = runs_root_fn() / run_id
        manifest_path = run_dir / "manifest.json"
        if not manifest_path.exists():
            raise HTTPException(status_code=404, detail=error_detail_fn("RUN_NOT_FOUND"))
        manifest = _safe_load_json(manifest_path) or {}
        contract_path = run_dir / "contract.json"
        contract = _safe_load_json(contract_path) if contract_path.exists() else {}
        normalized_contract = _normalize_contract(contract)
        persisted_role_binding = (
            manifest.get("role_binding_summary")
            if _is_valid_role_binding_summary_payload(manifest.get("role_binding_summary"))
            else {}
        )
        status = str(manifest.get("status") or "")
        events = _read_events_light(run_dir)
        failure_attrs = _infer_failure_fields(
            status=status,
            manifest=manifest,
            events=events,
        )
        outcome = _resolve_outcome(status, str(failure_attrs.get("failure_class") or ""))
        allowed_paths = normalized_contract.get("allowed_paths")
        if not isinstance(allowed_paths, list):
            allowed_paths = []
        return {
            "run_id": run_id,
            "task_id": manifest.get("task_id"),
            "status": manifest.get("status"),
            "allowed_paths": allowed_paths,
            "contract": normalized_contract,
            "manifest": manifest,
            "role_binding_read_model": persisted_role_binding
            or build_role_binding_summary(normalized_contract),
            **failure_attrs,
            **outcome,
        }

    def get_events(
        run_id: str,
        since: str | None = None,
        limit: int | None = Query(default=None, ge=1, le=5000),
        tail: bool = False,
    ) -> list[dict]:
        events = read_events_fn(run_id)
        return filter_events_fn(events, since=since, limit=limit, tail=tail)

    async def stream_events(
        run_id: str,
        request: Request,
        since: str | None = None,
        limit: int = Query(default=200, ge=1, le=5000),
        tail: bool = True,
        follow: bool = True,
    ) -> StreamingResponse:
        run_dir = runs_root_fn() / run_id
        if not run_dir.exists():
            raise HTTPException(status_code=404, detail=error_detail_fn("RUN_NOT_FOUND"))

        async def _event_stream():
            nonlocal since

            stream_offset = 0
            if callable(read_events_incremental_fn):
                initial_events, stream_offset = read_events_incremental_fn(
                    run_id=run_id,
                    offset=0,
                    since=since,
                    limit=limit,
                    tail=tail,
                )
            else:
                initial_events = filter_events_fn(read_events_fn(run_id), since=since, limit=limit, tail=tail)
            for item in initial_events:
                cursor = event_cursor_value_fn(item)
                payload = json.dumps(item, ensure_ascii=False)
                if cursor:
                    since = cursor
                    yield f"id: {cursor}\n"
                yield "event: run_event\n"
                yield f"data: {payload}\n\n"

            if not follow:
                return

            while True:
                if await request.is_disconnected():
                    break
                await asyncio.sleep(1.5)
                if callable(read_events_incremental_fn):
                    delta_events, stream_offset = read_events_incremental_fn(
                        run_id=run_id,
                        offset=stream_offset,
                        since=since,
                        limit=limit,
                        tail=False,
                    )
                else:
                    delta_events = filter_events_fn(read_events_fn(run_id), since=since, limit=limit, tail=False)
                if not delta_events:
                    yield ": keep-alive\n\n"
                    continue

                for item in delta_events:
                    cursor = event_cursor_value_fn(item)
                    payload = json.dumps(item, ensure_ascii=False)
                    if cursor:
                        since = cursor
                        yield f"id: {cursor}\n"
                    yield "event: run_event\n"
                    yield f"data: {payload}\n\n"

        return StreamingResponse(
            _event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    def get_diff(run_id: str) -> dict:
        diff_path = runs_root_fn() / run_id / "patch.diff"
        diff_text = diff_path.read_text(encoding="utf-8") if diff_path.exists() else ""
        return {"diff": diff_text}

    def get_reports(run_id: str) -> list[dict]:
        reports_dir = runs_root_fn() / run_id / "reports"
        reports: list[dict[str, Any]] = []
        if reports_dir.exists():
            for path in reports_dir.glob("*.json"):
                try:
                    data = json_loads_fn(path.read_text(encoding="utf-8"))
                except json_decode_error_cls:
                    data = {"raw": path.read_text(encoding="utf-8")}
                except Exception as exc:
                    log_event_fn(
                        "ERROR",
                        "api",
                        "REPORTS_READ_FAILED",
                        run_id=run_id,
                        meta={"request_id": current_request_id_fn(), "error": str(exc), "report": path.name},
                    )
                    raise HTTPException(status_code=500, detail=error_detail_fn("REPORTS_READ_FAILED")) from exc
                reports.append({"name": path.name, "data": data})

        run_dir = runs_root_fn() / run_id
        manifest_path = run_dir / "manifest.json"
        manifest = _safe_load_json(manifest_path) if manifest_path.exists() else {}
        incident_pack = _build_incident_pack(run_id, manifest or {}, read_events_fn(run_id))
        if incident_pack is not None:
            reports.append({"name": "incident_pack.json", "data": incident_pack})
        proof_pack = _build_proof_pack(run_id, manifest or {}, reports)
        if proof_pack is not None:
            reports.append({"name": "proof_pack.json", "data": proof_pack})
        return reports

    def get_artifacts(run_id: str, name: str | None = None) -> dict:
        artifacts_dir = runs_root_fn() / run_id / "artifacts"
        if not artifacts_dir.exists():
            return {"items": []}
        if name:
            target = safe_artifact_target_fn(run_id, name)
            if not target.exists():
                return {"name": name, "data": None}
            if target.is_dir():
                raise HTTPException(status_code=400, detail=error_detail_fn("ARTIFACT_PATH_IS_DIRECTORY"))
            try:
                if target.suffix == ".json":
                    return {"name": name, "data": json_loads_fn(target.read_text(encoding="utf-8"))}
                if target.suffix == ".jsonl":
                    lines: list[dict] = []
                    for raw in target.read_text(encoding="utf-8").splitlines():
                        if not raw.strip():
                            continue
                        try:
                            lines.append(json_loads_fn(raw))
                        except json_decode_error_cls:
                            lines.append({"raw": raw})
                    return {"name": name, "data": lines}
                return {"name": name, "data": target.read_text(encoding="utf-8")}
            except Exception as exc:
                log_event_fn(
                    "ERROR",
                    "api",
                    "ARTIFACTS_READ_FAILED",
                    run_id=run_id,
                    meta={"request_id": current_request_id_fn(), "error": str(exc), "artifact": name},
                )
                raise HTTPException(status_code=500, detail=error_detail_fn("ARTIFACTS_READ_FAILED")) from exc
        return {"items": [p.name for p in artifacts_dir.iterdir() if p.is_file()]}

    def get_search(run_id: str) -> dict:
        run_dir = runs_root_fn() / run_id
        if not run_dir.exists():
            raise HTTPException(status_code=404, detail=error_detail_fn("RUN_NOT_FOUND"))
        return search_payload_helpers.build_search_payload(
            run_id,
            read_artifact_fn=read_artifact_fn,
            read_report_fn=read_report_fn,
        )

    def get_operator_copilot_brief(run_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        from openvibecoding_orch.services.operator_copilot import generate_run_operator_copilot_brief

        _ = payload
        run_id = str(run_id).strip()
        if not run_id:
            raise HTTPException(status_code=404, detail=error_detail_fn("RUN_NOT_FOUND"))
        return generate_run_operator_copilot_brief(
            run_id,
            get_run_fn=get_run,
            get_reports_fn=get_reports,
            get_workflow_fn=get_workflow,
            list_queue_fn=list_queue,
            list_pending_approvals_fn=list_pending_approvals_fn,
            list_diff_gate_fn=list_diff_gate_fn,
        )

    def get_workflow_operator_copilot_brief(workflow_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        from openvibecoding_orch.services.operator_copilot import generate_workflow_operator_copilot_brief

        _ = payload
        workflow_id = str(workflow_id).strip()
        if not workflow_id:
            raise HTTPException(status_code=404, detail=error_detail_fn("WORKFLOW_NOT_FOUND"))
        return generate_workflow_operator_copilot_brief(
            workflow_id,
            get_workflow_fn=get_workflow,
            get_run_fn=get_run,
            get_reports_fn=get_reports,
            list_queue_fn=list_queue,
            list_pending_approvals_fn=list_pending_approvals_fn,
            list_diff_gate_fn=list_diff_gate_fn,
        )

    def promote_evidence(run_id: str) -> dict:
        run_dir = runs_root_fn() / run_id
        if not run_dir.exists():
            raise HTTPException(status_code=404, detail=error_detail_fn("RUN_NOT_FOUND"))
        contract = load_contract_fn(run_id)
        raw = read_artifact_fn(run_id, "search_results.json")
        results: list[dict] = []
        if isinstance(raw, dict):
            latest = raw.get("latest") if isinstance(raw.get("latest"), dict) else None
            if isinstance(latest, dict) and isinstance(latest.get("results"), list):
                results = latest.get("results", [])
            elif isinstance(raw.get("results"), list):
                results = raw.get("results", [])
        queries = extract_search_queries_fn(contract)
        raw_question = "; ".join(queries) if queries else "search"
        refined_prompt = raw_question
        requested_by = contract.get("assigned_agent", {}) if isinstance(contract, dict) else {}
        bundle = build_evidence_bundle(
            raw_question=raw_question,
            refined_prompt=refined_prompt,
            results=results,
            requested_by=requested_by,
            limitations=["promoted manually from search ui"],
        )
        return promote_evidence_fn(run_id, bundle)

    def replay_run(run_id: str, payload: dict | None = None) -> dict:
        if payload is not None and not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail=error_detail_fn("PAYLOAD_INVALID"))
        baseline_run_id = payload.get("baseline_run_id") if payload else None
        baseline_window = payload.get("baseline_window") if payload else None
        if not baseline_run_id and baseline_window:
            if not isinstance(baseline_window, dict):
                raise HTTPException(status_code=400, detail=error_detail_fn("BASELINE_WINDOW_INVALID"))
            try:
                baseline_run_id = select_baseline_by_window_fn(run_id, baseline_window)
            except Exception as exc:
                log_event_fn(
                    "WARN",
                    "api",
                    "BASELINE_WINDOW_INVALID",
                    run_id=run_id,
                    meta={"request_id": current_request_id_fn(), "error": str(exc)},
                )
                raise HTTPException(status_code=400, detail=error_detail_fn("BASELINE_WINDOW_INVALID")) from exc
        return orchestration_service_fn().replay_run(run_id, baseline_run_id=baseline_run_id)

    def verify_run(run_id: str, strict: bool = True) -> dict:
        return orchestration_service_fn().replay_verify(run_id, strict=strict)

    def reexec_run(run_id: str, strict: bool = True) -> dict:
        return orchestration_service_fn().replay_reexec(run_id, strict=strict)

    def list_contracts() -> list[dict]:
        cfg = load_config_fn()
        contracts = []

        def _read_contract_item(path: Path) -> dict[str, Any]:
            payload: dict[str, Any] | None = None
            record_status = "structured"
            raw_preview: str | None = None
            try:
                raw_text = path.read_text(encoding="utf-8")
            except Exception:  # noqa: BLE001
                record_status = "read-failed"
                raw_text = ""
            if record_status != "read-failed":
                try:
                    loaded = json_loads_fn(raw_text)
                except json_decode_error_cls:
                    record_status = "raw"
                    raw_preview = raw_text
                except Exception:  # noqa: BLE001
                    record_status = "raw"
                    raw_preview = raw_text
                else:
                    if isinstance(loaded, dict):
                        payload = _normalize_contract(loaded)
                    else:
                        record_status = "raw"
                        raw_preview = raw_text
            normalized_contract = payload or {}
            assigned_agent = _as_dict(normalized_contract.get("assigned_agent"))
            owner_agent = _as_dict(normalized_contract.get("owner_agent"))
            role_binding = None
            if normalized_contract and (
                isinstance(normalized_contract.get("role_contract"), dict)
                or _normalize_optional_text(assigned_agent.get("role"))
            ):
                role_binding = build_role_binding_summary(normalized_contract)
            tool_permissions = _as_dict(normalized_contract.get("tool_permissions"))
            return {
                "source": None,
                "_source": None,
                "path": str(path),
                "_path": str(path),
                "record_status": record_status,
                "task_id": _normalize_optional_text(normalized_contract.get("task_id")),
                "run_id": _normalize_optional_text(normalized_contract.get("run_id")),
                "allowed_paths": _normalize_string_list(normalized_contract.get("allowed_paths")),
                "acceptance_tests": _normalize_acceptance_tests(normalized_contract.get("acceptance_tests")),
                "tool_permissions": tool_permissions or None,
                "owner_agent_id": _normalize_optional_text(owner_agent.get("agent_id")),
                "owner_role": _normalize_optional_text(owner_agent.get("role")),
                "assigned_agent_id": _normalize_optional_text(assigned_agent.get("agent_id")),
                "assigned_role": _normalize_optional_text(assigned_agent.get("role")),
                "execution_authority": role_binding.get("execution_authority") if isinstance(role_binding, dict) else None,
                "role_binding_read_model": role_binding,
                "payload": normalized_contract or None,
                "raw": raw_preview,
                "raw_preview": raw_preview,
            }

        for path in (cfg.contract_root / "examples").glob("*.json"):
            item = _read_contract_item(path)
            item["source"] = "examples"
            item["_source"] = "examples"
            contracts.append(item)
        for bucket in ["tasks", "reviews", "results"]:
            root = cfg.contract_root / bucket
            if not root.exists():
                continue
            for path in root.glob("**/*.json"):
                item = _read_contract_item(path)
                item["source"] = bucket
                item["_source"] = bucket
                contracts.append(item)
        return contracts

    def get_role_config(role: str) -> dict[str, Any]:
        role_key = _normalize_role(role)
        try:
            return build_role_config_surface(role_key)
        except ValueError as exc:
            raise _role_config_error(404, "ROLE_CONFIG_ROLE_UNKNOWN", str(exc)) from exc

    def preview_role_config(role: str, payload: dict[str, Any]) -> dict[str, Any]:
        role_key = _normalize_role(role)
        try:
            return preview_role_config_entry(role_key, payload)
        except ValueError as exc:
            raise _role_config_error(400, "ROLE_CONFIG_PREVIEW_INVALID", str(exc)) from exc

    def apply_role_config(role: str, payload: dict[str, Any]) -> dict[str, Any]:
        role_key = _normalize_role(role)
        try:
            return apply_role_config_entry(role_key, payload)
        except ValueError as exc:
            error_text = str(exc)
            if "unknown role" in error_text.lower():
                raise _role_config_error(404, "ROLE_CONFIG_ROLE_UNKNOWN", error_text) from exc
            raise _role_config_error(400, "ROLE_CONFIG_APPLY_INVALID", error_text) from exc

    def list_events(limit: int = 200) -> list[dict]:
        items: list[dict] = []
        for run_dir in runs_root_fn().glob("*"):
            run_id = run_dir.name
            for item in read_events_fn(run_id):
                item["_run_id"] = run_id
                items.append(item)

        def _key(ev: dict) -> str:
            return str(ev.get("ts") or ev.get("_ts") or "")

        items.sort(key=_key, reverse=True)
        return items[: max(1, min(2000, limit))]

    def list_agents_status(run_id: str | None = None) -> dict:
        return list_agents_status_fn(run_id)

    return {
        "list_runs": list_runs,
        "list_queue": list_queue,
        "preview_enqueue_run_queue": preview_enqueue_run_queue,
        "enqueue_run_queue": enqueue_run_queue,
        "cancel_queue_item": cancel_queue_item,
        "run_next_queue": run_next_queue,
        "list_workflows": list_workflows,
        "get_workflow": get_workflow,
        "get_workflow_operator_copilot_brief": get_workflow_operator_copilot_brief,
        "get_run": get_run,
        "get_events": get_events,
        "stream_events": stream_events,
        "get_diff": get_diff,
        "get_reports": get_reports,
        "get_artifacts": get_artifacts,
        "get_search": get_search,
        "get_operator_copilot_brief": get_operator_copilot_brief,
        "promote_evidence": promote_evidence,
        "replay_run": replay_run,
        "verify_run": verify_run,
        "reexec_run": reexec_run,
        "list_contracts": list_contracts,
        "list_events": list_events,
        "list_diff_gate": list_diff_gate_fn,
        "rollback_run": rollback_run_fn,
        "reject_run": reject_run_fn,
        "list_reviews": list_reviews_fn,
        "list_tests": list_tests_fn,
        "list_agents": list_agents_fn,
        "list_agents_status": list_agents_status,
        "get_role_config": get_role_config,
        "preview_role_config": preview_role_config,
        "apply_role_config": apply_role_config,
        "list_policies": list_policies_fn,
        "list_locks": list_locks_fn,
        "list_worktrees": list_worktrees_fn,
    }
