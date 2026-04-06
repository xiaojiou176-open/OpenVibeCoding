from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable

from fastapi import HTTPException


_logger = logging.getLogger(__name__)
_ReadPmSessionFilesFn = Callable[[str], tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]]
_SessionIndexServiceFn = Callable[[], Any]
_ReadRunManifestFn = Callable[[str], dict[str, Any]]
_LoadContractFn = Callable[[str], dict[str, Any]]
_ReadEventsFn = Callable[[str], list[dict[str, Any]]]
_LastEventTsFn = Callable[[str], str]
_ParseIsoFn = Callable[[str], datetime]
_EventCursorFn = Callable[[dict[str, Any]], str]
_ErrorDetailFn = Callable[[str], dict[str, str]]


def _extract_pm_session_run_ids(response: dict[str, Any], intake_events: list[dict[str, Any]]) -> list[str]:
    run_ids: list[str] = []

    def _add(run_id: Any) -> None:
        if not isinstance(run_id, str):
            return
        cleaned = run_id.strip()
        if not cleaned or cleaned in run_ids:
            return
        run_ids.append(cleaned)

    for event in intake_events:
        if not isinstance(event, dict):
            continue
        event_name = str(event.get("event") or "").strip().upper()
        if event_name not in {"INTAKE_RUN", "INTAKE_CHAIN_RUN"}:
            continue
        _add(event.get("run_id"))
        context = event.get("context") if isinstance(event.get("context"), dict) else {}
        _add(context.get("run_id"))

    _add(response.get("chain_run_id"))

    raw_chain_ids = response.get("chain_run_ids")
    if isinstance(raw_chain_ids, list):
        for item in raw_chain_ids:
            _add(item)

    return run_ids


def _run_status_bucket(
    status: str,
    *,
    running_statuses: set[str],
    success_statuses: set[str],
    failed_statuses: set[str],
) -> str:
    normalized = status.strip().upper()
    if normalized in failed_statuses:
        return "failed"
    if normalized in success_statuses:
        return "success"
    if normalized in running_statuses:
        return "running"
    return "paused"


def _run_is_blocked(events: list[dict[str, Any]]) -> bool:
    has_required = False
    has_completed = False
    for event in events:
        if not isinstance(event, dict):
            continue
        event_name = str(event.get("event") or "").strip().upper()
        if event_name == "HUMAN_APPROVAL_REQUIRED":
            has_required = True
        elif event_name == "HUMAN_APPROVAL_COMPLETED":
            has_completed = True
    return has_required and not has_completed


def _run_is_blocked_lightweight(manifest: dict[str, Any]) -> bool:
    blocked_raw = manifest.get("blocked")
    if isinstance(blocked_raw, bool):
        return blocked_raw
    if isinstance(blocked_raw, str) and blocked_raw.strip().lower() in {"1", "true", "yes", "blocked"}:
        return True

    stage = str(manifest.get("stage") or manifest.get("current_step") or "").strip().upper()
    if stage in {"WAITING_APPROVAL", "BLOCKED"}:
        return True

    status_reason = str(manifest.get("status_reason") or manifest.get("failure_reason") or "").strip().upper()
    if status_reason in {"WAITING_APPROVAL", "HUMAN_APPROVAL_REQUIRED", "BLOCKED"}:
        return True

    return False


def _run_is_potentially_blocked_lightweight(*, bucket: str, blocked: bool) -> bool:
    # Lightweight mode intentionally avoids run-level events. Active runs can only be treated as potential blockers.
    return not blocked and bucket == "running"


def _extract_role_step_from_events(
    events: list[dict[str, Any]],
    fallback_role: str,
    *,
    event_cursor_fn: _EventCursorFn,
) -> tuple[str, str, str]:
    for event in reversed(events):
        if not isinstance(event, dict):
            continue
        context = event.get("context") if isinstance(event.get("context"), dict) else {}

        role_candidates = [
            context.get("to_role"),
            context.get("role"),
            context.get("from_role"),
            context.get("to"),
            context.get("from"),
        ]
        role = ""
        for candidate in role_candidates:
            if isinstance(candidate, str) and candidate.strip():
                role = candidate.strip()
                break

        step_candidates = [context.get("step"), context.get("task_id"), event.get("event")]
        step = ""
        for candidate in step_candidates:
            if isinstance(candidate, str) and candidate.strip():
                step = candidate.strip()
                break

        ts = event_cursor_fn(event)
        if role or step:
            return role or fallback_role, step or "UNKNOWN", ts
    return fallback_role, "PENDING", ""


def _parse_ts_or_none(value: Any, *, parse_iso_ts_fn: _ParseIsoFn) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return parse_iso_ts_fn(value)
    except Exception as exc:  # noqa: BLE001
        _logger.debug("pm_session_aggregation_context: _parse_ts_or_none failed: %s", exc)
        return None


def _max_ts(values: list[Any], *, parse_iso_ts_fn: _ParseIsoFn) -> str:
    parsed: list[datetime] = []
    for value in values:
        dt = _parse_ts_or_none(value, parse_iso_ts_fn=parse_iso_ts_fn)
        if dt is not None:
            parsed.append(dt)
    if not parsed:
        return ""
    return max(parsed).isoformat()


def _avg_seconds(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 3)


def _compute_recovery_seconds(
    events: list[dict[str, Any]],
    *,
    event_cursor_fn: _EventCursorFn,
    parse_iso_ts_fn: _ParseIsoFn,
) -> list[float]:
    durations: list[float] = []
    pending_required: datetime | None = None

    for event in events:
        if not isinstance(event, dict):
            continue
        event_name = str(event.get("event") or "").strip().upper()
        cursor = event_cursor_fn(event)
        dt = _parse_ts_or_none(cursor, parse_iso_ts_fn=parse_iso_ts_fn)
        if dt is None:
            continue
        if event_name == "HUMAN_APPROVAL_REQUIRED":
            pending_required = dt
        elif event_name == "HUMAN_APPROVAL_COMPLETED" and pending_required is not None:
            durations.append(max((dt - pending_required).total_seconds(), 0.0))
            pending_required = None

    return durations


def _run_sort_key(item: dict[str, Any], *, parse_iso_ts_fn: _ParseIsoFn) -> tuple[int, str]:
    ts = _parse_ts_or_none(item.get("last_event_ts") or item.get("created_at") or "", parse_iso_ts_fn=parse_iso_ts_fn)
    if ts is None:
        return (0, str(item.get("run_id") or ""))
    return (int(ts.timestamp()), str(item.get("run_id") or ""))


def resolve_pm_session_context(
    pm_session_id: str,
    *,
    strict: bool,
    read_pm_session_files_fn: _ReadPmSessionFilesFn,
    session_index_service_fn: _SessionIndexServiceFn,
    read_run_manifest_fn: _ReadRunManifestFn,
    load_contract_fn: _LoadContractFn,
    read_events_fn: _ReadEventsFn,
    last_event_ts_fn: _LastEventTsFn,
    parse_iso_ts_fn: _ParseIsoFn,
    event_cursor_fn: _EventCursorFn,
    error_detail_fn: _ErrorDetailFn,
    running_statuses: set[str],
    success_statuses: set[str],
    failed_statuses: set[str],
    include_run_events: bool = True,
    include_runs: bool = True,
) -> dict[str, Any]:
    intake, response, intake_events = read_pm_session_files_fn(pm_session_id)
    if strict and not intake and not response and not intake_events:
        raise HTTPException(status_code=404, detail=error_detail_fn("PM_SESSION_NOT_FOUND"))

    index_service = session_index_service_fn()
    bindings = index_service.derive_bindings(pm_session_id, response, intake_events)
    run_ids = [item.run_id for item in bindings]
    if not run_ids:
        run_ids = _extract_pm_session_run_ids(response, intake_events)
    binding_map = {item.run_id: item for item in bindings}

    runs: list[dict[str, Any]] = []
    events_by_run: dict[str, list[dict[str, Any]]] = {}

    running_runs = 0
    failed_runs = 0
    success_runs = 0
    blocked_runs = 0
    potential_blocked_runs = 0

    current_role = ""
    current_step = ""
    current_ts = ""

    duration_seconds: list[float] = []
    recovery_seconds: list[float] = []
    run_created_at_values: list[Any] = []
    run_finished_at_values: list[Any] = []
    run_last_event_ts_values: list[Any] = []

    latest_run_sort_key: tuple[int, str] = (0, "")
    latest_run_id = ""

    for run_id in run_ids:
        manifest = read_run_manifest_fn(run_id)
        status = str(manifest.get("status") or "").strip().upper()
        bucket = _run_status_bucket(
            status,
            running_statuses=running_statuses,
            success_statuses=success_statuses,
            failed_statuses=failed_statuses,
        )
        if bucket == "running":
            running_runs += 1
        elif bucket == "failed":
            failed_runs += 1
        elif bucket == "success":
            success_runs += 1

        role = str(manifest.get("current_role") or "").strip()
        step = str(manifest.get("current_step") or "").strip() or "PENDING"
        role_ts = ""

        contract: dict[str, Any] = {}
        if include_run_events:
            contract = load_contract_fn(run_id)
            assigned = contract.get("assigned_agent") if isinstance(contract.get("assigned_agent"), dict) else {}
            fallback_role = str(assigned.get("role") or "").strip()

            run_events = read_events_fn(run_id)
            events_by_run[run_id] = [item for item in run_events if isinstance(item, dict)]
            role, step, role_ts = _extract_role_step_from_events(
                events_by_run[run_id],
                fallback_role,
                event_cursor_fn=event_cursor_fn,
            )
            blocked = _run_is_blocked(events_by_run[run_id])
            potential_blocked = False
        else:
            events_by_run[run_id] = []
            blocked = _run_is_blocked_lightweight(manifest)
            potential_blocked = _run_is_potentially_blocked_lightweight(bucket=bucket, blocked=blocked)

        if role_ts:
            previous_ts = _parse_ts_or_none(current_ts, parse_iso_ts_fn=parse_iso_ts_fn)
            candidate_ts = _parse_ts_or_none(role_ts, parse_iso_ts_fn=parse_iso_ts_fn)
            if candidate_ts and (previous_ts is None or candidate_ts >= previous_ts):
                current_role = role
                current_step = step
                current_ts = role_ts

        if blocked:
            blocked_runs += 1
        if potential_blocked:
            potential_blocked_runs += 1

        created_at = manifest.get("created_at") or manifest.get("start_ts") or ""
        finished_at = manifest.get("finished_at") or manifest.get("end_ts") or ""
        last_event_ts = role_ts
        if not last_event_ts and (include_runs or include_run_events):
            last_event_ts = last_event_ts_fn(run_id)

        run_created_at_values.append(created_at)
        run_finished_at_values.append(finished_at)
        run_last_event_ts_values.append(last_event_ts)

        start_dt = _parse_ts_or_none(created_at, parse_iso_ts_fn=parse_iso_ts_fn)
        end_dt = _parse_ts_or_none(finished_at, parse_iso_ts_fn=parse_iso_ts_fn)
        if start_dt and end_dt:
            duration_seconds.append(max((end_dt - start_dt).total_seconds(), 0.0))

        if include_run_events:
            recovery_seconds.extend(
                _compute_recovery_seconds(
                    events_by_run[run_id],
                    event_cursor_fn=event_cursor_fn,
                    parse_iso_ts_fn=parse_iso_ts_fn,
                )
            )

        run_sort_key = _run_sort_key(
            {
                "run_id": run_id,
                "last_event_ts": last_event_ts,
                "created_at": created_at,
            },
            parse_iso_ts_fn=parse_iso_ts_fn,
        )
        if run_sort_key > latest_run_sort_key:
            latest_run_sort_key = run_sort_key
            latest_run_id = run_id

        if include_runs:
            binding = binding_map.get(run_id)
            runs.append(
                {
                    "run_id": run_id,
                    "task_id": manifest.get("task_id", ""),
                    "status": status,
                    "failure_reason": str(manifest.get("failure_reason") or "").strip(),
                    "workflow_id": (manifest.get("workflow") or {}).get("workflow_id", "")
                    if isinstance(manifest.get("workflow"), dict)
                    else "",
                    "created_at": created_at,
                    "finished_at": finished_at,
                    "last_event_ts": last_event_ts,
                    "blocked": blocked,
                    "potential_blocked": potential_blocked,
                    "current_role": role,
                    "current_step": step,
                    "binding_type": binding.binding_type if binding else "",
                    "bound_at": binding.bound_at if binding else "",
                }
            )
        elif include_run_events:
            runs.append(
                {
                    "run_id": run_id,
                    "status": status,
                    "created_at": created_at,
                    "finished_at": finished_at,
                    "last_event_ts": last_event_ts,
                }
            )

    if include_runs:
        runs.sort(key=lambda item: _run_sort_key(item, parse_iso_ts_fn=parse_iso_ts_fn), reverse=True)

    run_count = len(run_ids)
    declared_status = ""
    for source in [intake.get("status"), response.get("status")]:
        if isinstance(source, str) and source.strip():
            declared_status = source.strip().lower()
            break

    if declared_status == "archived":
        session_status = "archived"
    elif running_runs > 0:
        session_status = "active"
    elif failed_runs > 0:
        session_status = "failed"
    elif run_count > 0 and success_runs == run_count:
        session_status = "done"
    else:
        session_status = "paused"

    owner_pm = ""
    owner_agent = intake.get("owner_agent") if isinstance(intake.get("owner_agent"), dict) else {}
    if isinstance(owner_agent.get("agent_id"), str):
        owner_pm = owner_agent.get("agent_id", "").strip()
    if not owner_pm and isinstance(intake.get("owner_pm"), str):
        owner_pm = intake.get("owner_pm", "").strip()
    owner_missing_count = 0
    if not owner_pm:
        owner_missing_count = 1
        owner_pm = "unassigned" if owner_agent else "unknown"

    project_key = ""
    for key in ["project_key", "project", "repo", "workspace"]:
        value = intake.get(key)
        if isinstance(value, str) and value.strip():
            project_key = value.strip()
            break

    session_source = index_service.derive_session_source(intake, response)

    if include_runs:
        latest_run_id = runs[0]["run_id"] if runs else ""

    created_at = intake.get("created_at") if isinstance(intake.get("created_at"), str) else ""
    updated_at = _max_ts(
        [
            created_at,
            response.get("updated_at"),
            response.get("created_at"),
            *run_created_at_values,
            *run_finished_at_values,
            *run_last_event_ts_values,
        ],
        parse_iso_ts_fn=parse_iso_ts_fn,
    )

    closed_at = ""
    if session_status in {"done", "failed", "archived"}:
        closed_at = _max_ts(
            [
                response.get("closed_at"),
                response.get("finished_at"),
                *run_finished_at_values,
                updated_at,
            ],
            parse_iso_ts_fn=parse_iso_ts_fn,
        )

    objective = ""
    if isinstance(intake.get("objective"), str) and intake.get("objective", "").strip():
        objective = intake.get("objective", "").strip()
    elif isinstance(response.get("plan"), dict):
        plan_spec = response["plan"].get("spec")
        if isinstance(plan_spec, str) and plan_spec.strip():
            objective = plan_spec.strip()

    failure_rate = round((failed_runs / run_count), 4) if run_count else 0.0
    blocked_ratio = round((blocked_runs / run_count), 4) if run_count else 0.0
    potential_blocked_ratio = round((potential_blocked_runs / run_count), 4) if run_count else 0.0
    avg_duration_seconds = _avg_seconds(duration_seconds)
    avg_recovery_seconds = _avg_seconds(recovery_seconds)

    summary = {
        "pm_session_id": pm_session_id,
        "objective": objective,
        "owner_pm": owner_pm,
        "project_key": project_key,
        "session_source": session_source,
        "status": session_status,
        "created_at": created_at,
        "updated_at": updated_at or created_at,
        "closed_at": closed_at,
        "run_count": run_count,
        "running_runs": running_runs,
        "failed_runs": failed_runs,
        "success_runs": success_runs,
        "latest_run_id": latest_run_id,
        "current_role": current_role,
        "current_step": current_step,
        "blocked_runs": blocked_runs,
        "potential_blocked_runs": potential_blocked_runs,
        "owner_missing_count": owner_missing_count,
    }

    metrics = {
        "pm_session_id": pm_session_id,
        "run_count": run_count,
        "running_runs": running_runs,
        "failed_runs": failed_runs,
        "success_runs": success_runs,
        "blocked_runs": blocked_runs,
        "potential_blocked_runs": potential_blocked_runs,
        "failure_rate": failure_rate,
        "blocked_ratio": blocked_ratio,
        "potential_blocked_ratio": potential_blocked_ratio,
        "avg_duration_seconds": avg_duration_seconds,
        "avg_recovery_seconds": avg_recovery_seconds,
        "cycle_time_seconds": avg_duration_seconds,
        "mttr_seconds": avg_recovery_seconds,
        "owner_missing_count": owner_missing_count,
    }

    return {
        "pm_session_id": pm_session_id,
        "intake": intake,
        "response": response,
        "intake_events": intake_events,
        "run_ids": run_ids,
        "bindings": [
            {
                "pm_session_id": item.pm_session_id,
                "run_id": item.run_id,
                "binding_type": item.binding_type,
                "bound_at": item.bound_at,
            }
            for item in bindings
        ],
        "runs": runs,
        "events_by_run": events_by_run,
        "summary": summary,
        "metrics": metrics,
    }
