from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
import inspect
from pathlib import Path
import re
import time
from typing import Any, Callable
import uuid

from fastapi import FastAPI, HTTPException, Query, Request

from cortexpilot_orch.api import pm_session_aggregation
from cortexpilot_orch.cli_runtime_helpers import runs_root as resolve_runs_root
from cortexpilot_orch.config import load_config
from cortexpilot_orch.contract.compiler import build_role_binding_summary, sync_role_contract
from cortexpilot_orch.observability.logger import log_event
from cortexpilot_orch.planning.intake import (
    IntakeService,
    _build_unblock_tasks_from_worker_contracts,
    _build_wave_plan,
    _build_worker_prompt_contracts,
)
from cortexpilot_orch.store.intake_store import IntakeStore
from cortexpilot_orch.store.run_store import RunStore


_TRUTHY_VALUES = {"1", "true", "yes", "y", "on"}
_ALLOWED_RUNTIME_RUNNERS = {"agents", "app-server", "app_server", "codex"}
_RUN_SUBMISSION_WAIT_SEC = 15.0
_INTAKE_ONLY_CONTRACT_FIELDS = {"task_template", "template_payload"}


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in _TRUTHY_VALUES
    if isinstance(value, (int, float)):
        return bool(value)
    return False


def _normalize_runner(value: Any) -> str:
    candidate = str(value or "").strip().lower()
    if not candidate:
        return ""
    if candidate not in _ALLOWED_RUNTIME_RUNNERS:
        allowed = ", ".join(sorted(_ALLOWED_RUNTIME_RUNNERS))
        raise ValueError(f"invalid runner '{candidate}', allowed: {allowed}")
    return candidate


def _read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _discover_submitted_run_id(
    *,
    repo_root: Path,
    baseline_run_ids: set[str],
    task_id: str,
    timeout_sec: float = _RUN_SUBMISSION_WAIT_SEC,
) -> str:
    runs_root = resolve_runs_root(repo_root)
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if not runs_root.exists():
            time.sleep(0.2)
            continue
        candidates: list[tuple[float, str]] = []
        for entry in runs_root.iterdir():
            if not entry.is_dir():
                continue
            run_id = entry.name.strip()
            if not run_id or run_id in baseline_run_ids:
                continue
            manifest = _read_json_file(entry / "manifest.json")
            manifest_task_id = str(manifest.get("task_id") or "").strip()
            if manifest_task_id != task_id:
                continue
            try:
                stat = entry.stat()
            except OSError:
                continue
            candidates.append((stat.st_mtime, run_id))
        if candidates:
            candidates.sort()
            return candidates[-1][1]
        time.sleep(0.2)
    return ""


def _resolve_repo_root(cfg: Any) -> Path:
    candidate = getattr(cfg, "repo_root", None)
    if isinstance(candidate, Path):
        return candidate.resolve()
    if isinstance(candidate, str) and candidate.strip():
        return Path(candidate).resolve()
    return Path(__file__).resolve().parents[5]


def _resolve_runs_root(cfg: Any) -> Path:
    candidate = getattr(cfg, "runs_root", None)
    if isinstance(candidate, Path):
        return candidate.resolve()
    if isinstance(candidate, str) and candidate.strip():
        return Path(candidate).resolve()
    return resolve_runs_root(_resolve_repo_root(cfg))


def _strip_intake_only_contract_fields(contract: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(contract)
    for key in _INTAKE_ONLY_CONTRACT_FIELDS:
        sanitized.pop(key, None)
    return sanitized


def _artifact_ref_for_path(path: Path, *, rel_path: str, name: str, media_type: str = "application/json") -> dict[str, Any]:
    payload = path.read_bytes()
    return {
        "name": name,
        "path": rel_path,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "media_type": media_type,
        "size_bytes": len(payload),
    }


def _append_manifest_artifact(manifest: dict[str, Any], ref: dict[str, Any]) -> None:
    artifacts = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), list) else []
    key = (str(ref.get("name") or ""), str(ref.get("path") or ""))
    for item in artifacts:
        if not isinstance(item, dict):
            continue
        if (str(item.get("name") or ""), str(item.get("path") or "")) == key:
            return
    artifacts.append(ref)
    manifest["artifacts"] = artifacts


def _safe_read_intake_store_payload(store: object, method_name: str, intake_id: str) -> dict[str, Any]:
    reader = getattr(store, method_name, None)
    if not callable(reader):
        return {}
    try:
        payload = reader(intake_id)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _persist_planning_artifacts_for_run(
    *,
    intake_id: str,
    run_id: str,
    runs_root: Path,
) -> list[str]:
    intake_store = IntakeStore()
    intake_payload = _safe_read_intake_store_payload(intake_store, "read_intake", intake_id)
    response_payload = _safe_read_intake_store_payload(intake_store, "read_response", intake_id)
    plan_bundle = response_payload.get("plan_bundle") if isinstance(response_payload.get("plan_bundle"), dict) else None
    if not intake_payload or not isinstance(plan_bundle, dict):
        return []

    run_store = RunStore(runs_root=runs_root)
    run_dir = run_store.run_dir(run_id)
    worker_prompt_contracts = _build_worker_prompt_contracts(plan_bundle, intake_payload)
    artifacts_to_write: list[tuple[str, Any]] = [
        ("planning_wave_plan.json", _build_wave_plan(plan_bundle)),
        ("planning_worker_prompt_contracts.json", worker_prompt_contracts),
        ("planning_unblock_tasks.json", _build_unblock_tasks_from_worker_contracts(worker_prompt_contracts)),
    ]
    written: list[str] = []
    artifact_refs: list[dict[str, Any]] = []
    for filename, payload in artifacts_to_write:
        if payload in ({}, [], None):
            continue
        artifact_path = run_store.write_artifact(run_id, filename, json.dumps(payload, ensure_ascii=False, indent=2))
        written.append(filename)
        artifact_refs.append(
            _artifact_ref_for_path(
                artifact_path,
                rel_path=f"artifacts/{filename}",
                name=filename.removesuffix(".json"),
            )
        )

    if written:
        manifest_path = run_dir / "manifest.json"
        manifest = _read_json_file(manifest_path)
        if manifest:
            for ref in artifact_refs:
                _append_manifest_artifact(manifest, ref)
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        run_store.append_event(
            run_id,
            {
                "level": "INFO",
                "event": "PLANNING_ARTIFACTS_WRITTEN",
                "run_id": run_id,
                "meta": {"intake_id": intake_id, "artifacts": written},
            },
        )
    return written


def configure_pm_session_aggregation(
    *,
    runs_root_fn: Callable[[], Path],
    runtime_root_fn: Callable[[], Path],
    read_json_fn: Callable[[Path, object], object],
    load_contract_fn: Callable[[str], dict],
    read_events_fn: Callable[[str], list[dict]],
    last_event_ts_fn: Callable[[str], str],
    filter_events_fn: Callable[..., list[dict]],
    event_cursor_fn: Callable[[dict[str, Any]], str],
    parse_iso_fn: Callable[[str], datetime],
    error_detail_fn: Callable[[str], dict[str, str]],
) -> None:
    pm_session_aggregation.configure(
        runs_root_fn=runs_root_fn,
        runtime_root_fn=runtime_root_fn,
        read_json_fn=read_json_fn,
        load_contract_fn=load_contract_fn,
        read_events_fn=read_events_fn,
        last_event_ts_fn=last_event_ts_fn,
        filter_events_fn=filter_events_fn,
        event_cursor_fn=event_cursor_fn,
        parse_iso_fn=parse_iso_fn,
        error_detail_fn=error_detail_fn,
    )


def configure_routes(
    *,
    app: FastAPI,
    list_pm_sessions_accessor: Callable[[], Callable[..., list[dict[str, Any]]]],
    get_pm_session_accessor: Callable[[], Callable[[str], dict[str, Any]]],
    get_pm_session_events_accessor: Callable[[], Callable[..., list[dict[str, Any]]]],
    get_pm_session_graph_accessor: Callable[[], Callable[..., dict[str, Any]]],
    get_pm_session_metrics_accessor: Callable[[], Callable[[str], dict[str, Any]]],
    post_pm_session_message_accessor: Callable[[], Callable[[str, dict[str, Any]], dict[str, Any]]],
    get_command_tower_overview_accessor: Callable[[], Callable[[], dict[str, Any]]],
    get_command_tower_alerts_accessor: Callable[[], Callable[[], dict[str, Any]]],
    list_intakes_accessor: Callable[[], Callable[[], list[dict]]],
    list_task_packs_accessor: Callable[[], Callable[[], list[dict[str, Any]]]] | None = None,
    get_intake_accessor: Callable[[], Callable[[str], dict]],
    create_intake_accessor: Callable[[], Callable[[dict], dict]],
    answer_intake_accessor: Callable[[], Callable[[str, dict], dict]],
    run_intake_accessor: Callable[[], Callable[[str, dict | None], dict]],
    preview_intake_accessor: Callable[[], Callable[[dict], dict]] | None = None,
    preview_intake_copilot_brief_accessor: Callable[[], Callable[[dict], dict]] | None = None,
) -> None:
    app.state.routes_pm_handlers = {
        "list_pm_sessions": lambda request, status, status_filters, owner_pm, project_key, sort, limit, offset: list_pm_sessions_accessor()(
            request, status, status_filters, owner_pm, project_key, sort, limit, offset
        ),
        "get_pm_session": lambda pm_session_id: get_pm_session_accessor()(pm_session_id),
        "get_pm_session_events": lambda pm_session_id, request, since, limit, tail, event_types, run_ids: get_pm_session_events_accessor()(
            pm_session_id, request, since, limit, tail, event_types, run_ids
        ),
        "get_pm_session_graph": lambda pm_session_id, window, group_by_role: get_pm_session_graph_accessor()(
            pm_session_id, window, group_by_role
        ),
        "get_pm_session_metrics": lambda pm_session_id: get_pm_session_metrics_accessor()(pm_session_id),
        "post_pm_session_message": lambda pm_session_id, payload: post_pm_session_message_accessor()(
            pm_session_id, payload
        ),
        "get_command_tower_overview": lambda: get_command_tower_overview_accessor()(),
        "get_command_tower_alerts": lambda: get_command_tower_alerts_accessor()(),
    }
    app.state.routes_intake_handlers = {
        "list_intakes": lambda: list_intakes_accessor()(),
        "list_task_packs": lambda: list_task_packs_accessor()() if callable(list_task_packs_accessor) else [],
        "get_intake": lambda intake_id: get_intake_accessor()(intake_id),
        "create_intake": lambda payload: create_intake_accessor()(payload),
        "preview_intake": lambda payload: (preview_intake_accessor or create_intake_accessor)()(payload),
        "preview_intake_copilot_brief": lambda payload: (preview_intake_copilot_brief_accessor or preview_intake_accessor or create_intake_accessor)()(payload),
        "answer_intake": lambda intake_id, payload: answer_intake_accessor()(intake_id, payload),
        "run_intake": lambda intake_id, payload=None: run_intake_accessor()(intake_id, payload),
    }


def list_pm_sessions(
    request: Request,
    status: str | None = None,
    status_filters: list[str] | None = None,
    owner_pm: str | None = None,
    project_key: str | None = None,
    sort: str = "updated_desc",
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    list_fn = pm_session_aggregation.list_pm_sessions
    kwargs: dict[str, Any] = {
        "status": status,
        "owner_pm": owner_pm,
        "project_key": project_key,
        "sort": sort,
        "limit": limit,
        "offset": offset,
    }
    if "status_filters" in inspect.signature(list_fn).parameters:
        kwargs["status_filters"] = status_filters
    return list_fn(request, **kwargs)


def get_pm_session(pm_session_id: str) -> dict[str, Any]:
    return pm_session_aggregation.get_pm_session(pm_session_id)


def post_pm_session_message(
    pm_session_id: str,
    payload: dict[str, Any],
    *,
    error_detail_fn: Callable[[str], dict[str, str]],
    ensure_pm_session_fn: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    ensure_pm_session_fn(pm_session_id)

    message = str(payload.get("message") or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail=error_detail_fn("PM_SESSION_MESSAGE_INVALID"))

    from_role = str(payload.get("from_role") or payload.get("role") or "PM").strip().upper() or "PM"
    to_role = str(payload.get("to_role") or "TECH_LEAD").strip().upper() or "TECH_LEAD"
    event_name = str(payload.get("event") or "PM_MESSAGE").strip().upper() or "PM_MESSAGE"
    event_kind = str(payload.get("kind") or "chat").strip().lower() or "chat"
    author = str(payload.get("author") or "pm-ui").strip() or "pm-ui"
    ts = datetime.now(timezone.utc).isoformat()
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}

    event_payload = {
        "event": event_name,
        "ts": ts,
        "context": {
            "from_role": from_role,
            "to_role": to_role,
            "message": message,
            "kind": event_kind,
            "author": author,
            "metadata": metadata,
        },
    }
    IntakeStore().append_event(pm_session_id, event_payload)
    return {"ok": True, "pm_session_id": pm_session_id, "event": event_payload}


def get_pm_session_events(
    pm_session_id: str,
    request: Request,
    since: str | None = None,
    limit: int | None = Query(default=None, ge=1, le=5000),
    tail: bool = False,
    event_types: list[str] | None = None,
    run_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    return pm_session_aggregation.get_pm_session_events(
        pm_session_id,
        request,
        since=since,
        limit=limit,
        tail=tail,
        event_types=event_types,
        run_ids=run_ids,
    )


def get_pm_session_conversation_graph(
    pm_session_id: str,
    window: str = "30m",
    group_by_role: bool = False,
) -> dict[str, Any]:
    return pm_session_aggregation.get_pm_session_conversation_graph(
        pm_session_id,
        window=window,
        group_by_role=group_by_role,
    )


def get_pm_session_metrics(pm_session_id: str) -> dict[str, Any]:
    return pm_session_aggregation.get_pm_session_metrics(pm_session_id)


def get_command_tower_overview() -> dict[str, Any]:
    return pm_session_aggregation.get_command_tower_overview()


def get_command_tower_alerts() -> dict[str, Any]:
    return pm_session_aggregation.get_command_tower_alerts()


def list_intakes() -> list[dict]:
    return IntakeStore().list_intakes()


def get_intake(intake_id: str, *, error_detail_fn: Callable[[str], dict[str, str]]) -> dict:
    store = IntakeStore()
    if not store.intake_exists(intake_id):
        raise HTTPException(status_code=404, detail=error_detail_fn("INTAKE_NOT_FOUND"))
    intake = store.read_intake(intake_id)
    response = store.read_response(intake_id)
    if not intake and not response:
        raise HTTPException(status_code=404, detail=error_detail_fn("INTAKE_NOT_FOUND"))
    return {"intake_id": intake_id, "intake": intake, "response": response}


def create_intake(
    payload: dict,
    *,
    intake_service_cls: type[Any] = IntakeService,
    error_detail_fn: Callable[[str], dict[str, str]],
    current_request_id_fn: Callable[[], str],
) -> dict:
    service = intake_service_cls()
    try:
        return service.create(payload)
    except HTTPException:
        raise
    except ValueError as exc:
        log_event(
            "WARN",
            "api",
            "INTAKE_CREATE_FAILED",
            meta={"request_id": current_request_id_fn(), "error": str(exc)},
        )
        detail = {**error_detail_fn("INTAKE_CREATE_FAILED"), "reason": str(exc)}
        raise HTTPException(status_code=400, detail=detail) from exc
    except Exception as exc:  # noqa: BLE001
        log_event(
            "ERROR",
            "api",
            "INTAKE_CREATE_FAILED",
            meta={"request_id": current_request_id_fn(), "error": str(exc)},
        )
        raise HTTPException(status_code=500, detail=error_detail_fn("INTAKE_CREATE_FAILED")) from exc


def preview_intake(
    payload: dict,
    *,
    intake_service_cls: type[Any] = IntakeService,
    error_detail_fn: Callable[[str], dict[str, str]],
    current_request_id_fn: Callable[[], str],
) -> dict:
    service = intake_service_cls()
    try:
        return service.preview(payload)
    except HTTPException:
        raise
    except ValueError as exc:
        log_event(
            "WARN",
            "api",
            "INTAKE_PREVIEW_FAILED",
            meta={"request_id": current_request_id_fn(), "error": str(exc)},
        )
        detail = {**error_detail_fn("INTAKE_PREVIEW_FAILED"), "reason": str(exc)}
        raise HTTPException(status_code=400, detail=detail) from exc
    except Exception as exc:  # noqa: BLE001
        log_event(
            "ERROR",
            "api",
            "INTAKE_PREVIEW_FAILED",
            meta={"request_id": current_request_id_fn(), "error": str(exc)},
        )
        raise HTTPException(status_code=500, detail=error_detail_fn("INTAKE_PREVIEW_FAILED")) from exc


def preview_intake_copilot_brief(
    payload: dict,
    *,
    error_detail_fn: Callable[[str], dict[str, str]],
    current_request_id_fn: Callable[[], str],
) -> dict:
    from cortexpilot_orch.services.operator_copilot import generate_execution_plan_copilot_brief

    try:
        preview_payload = payload
        if isinstance(payload, dict) and isinstance(payload.get("preview"), dict):
            preview_payload = payload.get("preview")  # type: ignore[assignment]
        if not isinstance(preview_payload, dict):
            raise ValueError("`preview` must be an object")
        preview_payload = dict(preview_payload)
        preview_payload.pop("intake_id", None)
        return generate_execution_plan_copilot_brief(preview_payload)
    except HTTPException:
        raise
    except ValueError as exc:
        log_event(
            "WARN",
            "api",
            "INTAKE_PREVIEW_COPILOT_FAILED",
            meta={"request_id": current_request_id_fn(), "error": str(exc)},
        )
        detail = {**error_detail_fn("INTAKE_PREVIEW_FAILED"), "reason": str(exc)}
        raise HTTPException(status_code=400, detail=detail) from exc
    except Exception as exc:  # noqa: BLE001
        log_event(
            "ERROR",
            "api",
            "INTAKE_PREVIEW_COPILOT_FAILED",
            meta={"request_id": current_request_id_fn(), "error": str(exc)},
        )
        raise HTTPException(status_code=500, detail=error_detail_fn("INTAKE_PREVIEW_FAILED")) from exc


def answer_intake(
    intake_id: str,
    payload: dict,
    *,
    intake_service_cls: type[Any] = IntakeService,
    error_detail_fn: Callable[[str], dict[str, str]],
    current_request_id_fn: Callable[[], str],
) -> dict:
    service = intake_service_cls()
    try:
        return service.answer(intake_id, payload)
    except HTTPException:
        raise
    except ValueError as exc:
        log_event(
            "WARN",
            "api",
            "INTAKE_ANSWER_FAILED",
            meta={"request_id": current_request_id_fn(), "intake_id": intake_id, "error": str(exc)},
        )
        detail = {**error_detail_fn("INTAKE_ANSWER_FAILED"), "reason": str(exc)}
        raise HTTPException(status_code=400, detail=detail) from exc
    except Exception as exc:  # noqa: BLE001
        log_event(
            "ERROR",
            "api",
            "INTAKE_ANSWER_FAILED",
            meta={"request_id": current_request_id_fn(), "intake_id": intake_id, "error": str(exc)},
        )
        raise HTTPException(status_code=500, detail=error_detail_fn("INTAKE_ANSWER_FAILED")) from exc


def run_intake(
    intake_id: str,
    payload: dict | None = None,
    *,
    intake_service_cls: type[Any] = IntakeService,
    orchestration_service: Any,
    error_detail_fn: Callable[[str], dict[str, str]],
    current_request_id_fn: Callable[[], str],
) -> dict:
    service = intake_service_cls()
    try:
        contract = service.build_contract(intake_id)
    except HTTPException:
        raise
    except ValueError as exc:
        log_event(
            "WARN",
            "api",
            "INTAKE_BUILD_CONTRACT_FAILED",
            meta={"request_id": current_request_id_fn(), "intake_id": intake_id, "error": str(exc)},
        )
        detail = {**error_detail_fn("INTAKE_BUILD_CONTRACT_FAILED"), "reason": str(exc)}
        raise HTTPException(status_code=400, detail=detail) from exc
    except Exception as exc:  # noqa: BLE001
        log_event(
            "ERROR",
            "api",
            "INTAKE_BUILD_CONTRACT_FAILED",
            meta={"request_id": current_request_id_fn(), "intake_id": intake_id, "error": str(exc)},
        )
        raise HTTPException(status_code=500, detail=error_detail_fn("INTAKE_BUILD_CONTRACT_FAILED")) from exc
    if not contract:
        raise HTTPException(status_code=400, detail=error_detail_fn("INTAKE_PLAN_MISSING"))
    contract = _strip_intake_only_contract_fields(contract)

    runner = ""
    mock = False
    strict_acceptance: bool | None = None
    runtime_provider = ""
    try:
        if isinstance(payload, dict):
            runner = _normalize_runner(payload.get("runner"))
            mock = _coerce_bool(payload.get("mock", False))
            if "strict_acceptance" in payload:
                strict_acceptance = _coerce_bool(payload.get("strict_acceptance"))
            runtime_payload = payload.get("runtime_options")
            if isinstance(runtime_payload, dict):
                runtime_provider = str(runtime_payload.get("provider") or "").strip()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={**error_detail_fn("RUNTIME_RUNNER_INVALID"), "reason": str(exc)}) from exc
    if mock and contract.get("audit_only") is not True:
        contract["audit_only"] = True
    runtime_options = contract.get("runtime_options")
    if not isinstance(runtime_options, dict):
        runtime_options = {}
    if runner:
        runtime_options["runner"] = runner
    if strict_acceptance is not None:
        runtime_options["strict_acceptance"] = strict_acceptance
    if runtime_provider:
        runtime_options["provider"] = runtime_provider
    contract["runtime_options"] = runtime_options
    sync_role_contract(contract)

    cfg = load_config()
    contract_dir = cfg.runtime_contract_root / "tasks"
    contract_dir.mkdir(parents=True, exist_ok=True)
    task_stem = str(contract.get("task_id") or intake_id).strip() or str(intake_id)
    safe_task_stem = re.sub(r"[^a-zA-Z0-9._-]+", "_", task_stem).strip("._-") or "task"
    contract_path = contract_dir / f"{safe_task_stem}-{uuid.uuid4().hex[:10]}.json"
    contract_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")

    runs_root = _resolve_runs_root(cfg)
    baseline_run_ids: set[str] = set()
    if runs_root.exists():
        try:
            baseline_run_ids = {entry.name for entry in runs_root.iterdir() if entry.is_dir()}
        except OSError:
            baseline_run_ids = set()

    execution_result: dict[str, Any] = {"run_id": "", "error": None}
    done = threading.Event()

    def _execute_in_background() -> None:
        try:
            execution_result["run_id"] = orchestration_service.execute_task(contract_path, mock_mode=mock)
        except Exception as exc:  # noqa: BLE001
            execution_result["error"] = exc
            log_event(
                "ERROR",
                "api",
                "INTAKE_RUN_BACKGROUND_FAILED",
                meta={
                    "request_id": current_request_id_fn(),
                    "intake_id": intake_id,
                    "task_id": task_stem,
                    "error": str(exc),
                },
            )
        finally:
            done.set()

    worker = threading.Thread(target=_execute_in_background, daemon=True)
    worker.start()

    run_id = ""
    if done.wait(timeout=0.2):
        background_error = execution_result.get("error")
        if background_error is not None:
            raise HTTPException(status_code=500, detail=error_detail_fn("INTAKE_RUN_FAILED")) from background_error
        run_id = str(execution_result.get("run_id") or "").strip()

    if not run_id:
        run_id = _discover_submitted_run_id(
            repo_root=runs_root.parents[2],
            baseline_run_ids=baseline_run_ids,
            task_id=task_stem,
        )

    if not run_id and done.is_set():
        background_error = execution_result.get("error")
        if background_error is not None:
            raise HTTPException(status_code=500, detail=error_detail_fn("INTAKE_RUN_FAILED")) from background_error
        run_id = str(execution_result.get("run_id") or "").strip()

    if not run_id:
        snapshot = {
            "request_id": current_request_id_fn(),
            "intake_id": intake_id,
            "task_id": task_stem,
            "contract_path": str(contract_path),
            "baseline_run_count": len(baseline_run_ids),
            "background_done": done.is_set(),
        }
        log_event(
            "ERROR",
            "api",
            "INTAKE_RUN_SUBMISSION_TIMEOUT",
            meta=snapshot,
        )
        raise HTTPException(
            status_code=504,
            detail={**error_detail_fn("INTAKE_RUN_SUBMISSION_TIMEOUT"), "reason": "run_id not observed after submission"},
        )

    IntakeStore().append_event(intake_id, {"event": "INTAKE_RUN", "run_id": run_id})
    planning_artifacts = _persist_planning_artifacts_for_run(
        intake_id=intake_id,
        run_id=run_id,
        runs_root=runs_root,
    )
    return {
        "ok": True,
        "run_id": run_id,
        "contract_path": str(contract_path),
        "strict_acceptance": bool(runtime_options.get("strict_acceptance", False)),
        "role_binding_summary": build_role_binding_summary(contract),
        "planning_artifacts": planning_artifacts,
    }
