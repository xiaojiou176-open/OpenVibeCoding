from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Callable


def enqueue_contract(
    contract_path: Path,
    *,
    validator_cls: Callable[[], Any],
    queue_store_cls: Callable[[], Any],
) -> dict[str, Any]:
    resolved_path = contract_path.resolve()
    validator = validator_cls()
    contract = validator.validate_contract_file(resolved_path)
    task_id = contract.get("task_id", "task")
    owner = ""
    owner_agent = contract.get("owner_agent", {})
    if isinstance(owner_agent, dict):
        owner = owner_agent.get("agent_id", "") or ""
    store = queue_store_cls()
    return store.enqueue(resolved_path, task_id, owner=owner)


def session_alias_set_record(
    alias: str,
    session_id: str,
    *,
    thread_id: str,
    note: str,
    session_alias_store_cls: Callable[[], Any],
) -> dict[str, Any]:
    store = session_alias_store_cls()
    record = store.set_alias(alias, session_id, thread_id=thread_id, note=note)
    return dict(record.__dict__)


def session_alias_get_record(alias: str, *, session_alias_store_cls: Callable[[], Any]) -> dict[str, Any] | None:
    store = session_alias_store_cls()
    record = store.resolve(alias)
    if record is None:
        return None
    return dict(record.__dict__)


def session_alias_list_records(*, session_alias_store_cls: Callable[[], Any]) -> list[dict[str, Any]]:
    store = session_alias_store_cls()
    return [dict(record.__dict__) for record in store.list_aliases()]


def session_alias_delete_record(alias: str, *, session_alias_store_cls: Callable[[], Any]) -> bool:
    store = session_alias_store_cls()
    return bool(store.delete(alias))


def cleanup_runtime_summary(
    *,
    dry_run: bool,
    apply: bool,
    load_config_fn: Callable[[], Any],
    build_retention_plan_fn: Callable[[Any], Any],
    apply_retention_plan_fn: Callable[[Any, Any], dict[str, Any]],
    write_retention_report_fn: Callable[..., Path],
) -> dict[str, Any]:
    if dry_run and apply:
        raise ValueError("--dry-run and --apply are mutually exclusive")
    cfg = load_config_fn()
    plan = build_retention_plan_fn(cfg)
    apply_result = None
    will_apply = apply and not dry_run
    if will_apply:
        apply_result = apply_retention_plan_fn(cfg, plan)
    report_path = write_retention_report_fn(cfg, plan, applied=will_apply, apply_result=apply_result)
    summary: dict[str, Any] = {
        "dry_run": not will_apply,
        "applied": will_apply,
        "candidates_total": plan.total_candidates,
        "runs": len(plan.run_candidates),
        "worktrees": len(plan.worktree_candidates),
        "logs": len(plan.log_candidates),
        "cache": len(plan.cache_candidates),
        "machine_cache": len(plan.machine_cache_candidates),
        "report": str(report_path),
    }
    if apply_result:
        summary["removed_total"] = apply_result.get("removed_total", 0)
    return summary


def compile_plan_to_contract(
    plan_path: Path,
    output_path: Path | None,
    *,
    compile_plan_fn: Callable[[dict[str, Any]], dict[str, Any]],
    repo_root: Path,
) -> Path:
    resolved_plan_path = plan_path.resolve()
    plan = json.loads(resolved_plan_path.read_text(encoding="utf-8"))
    if not isinstance(plan, dict):
        raise ValueError("plan must be a JSON object")

    contract = compile_plan_fn(plan)
    if output_path is None:
        out_dir = repo_root / "contracts" / "tasks"
        out_dir.mkdir(parents=True, exist_ok=True)
        resolved_output_path = out_dir / f"{contract.get('task_id', 'task')}.json"
    else:
        resolved_output_path = output_path.resolve()
        resolved_output_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_output_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")
    return resolved_output_path


def run_next_task(
    *,
    mock: bool,
    queue_store_cls: Callable[[], Any],
    orchestrator_cls: Callable[[Path], Any],
    repo_root: Path,
    read_manifest_status_fn: Callable[[str], str],
) -> str | None:
    store = queue_store_cls()
    item = store.next_pending()
    if not item:
        return None
    contract_path = Path(item.get("contract_path", "")).resolve()
    task_id = item.get("task_id", "task")
    store.mark_claimed(task_id, run_id="")
    orch = orchestrator_cls(repo_root)
    run_id = orch.execute_task(contract_path, mock_mode=mock)
    store.mark_done(task_id, run_id, read_manifest_status_fn(run_id))
    return run_id


def replay_report(
    *,
    run_id: str,
    baseline_run_id: str | None,
    verify: bool,
    strict: bool,
    reexec: bool,
    orchestrator: Any,
) -> dict[str, Any]:
    if reexec and verify:
        raise ValueError("--reexec and --verify cannot be used together")
    if reexec:
        return orchestrator.replay_reexec(run_id, strict=strict)
    if verify:
        return orchestrator.replay_verify(run_id, strict=strict)
    return orchestrator.replay_run(run_id, baseline_run_id=baseline_run_id)


def execute_task_with_follow(
    *,
    orchestrator: Any,
    contract_path: Path,
    mock: bool,
    runs_root: Path,
    tail_event: str,
    tail_format: str,
    tail_level: str,
    wait_for_latest_run_id_fn: Callable[..., str],
    tail_events_fn: Callable[..., None],
) -> str:
    run_id_holder: dict[str, str] = {"value": ""}
    done = threading.Event()

    def _run_task() -> None:
        try:
            run_id_holder["value"] = orchestrator.execute_task(contract_path, mock_mode=mock)
        finally:
            done.set()

    worker = threading.Thread(target=_run_task, daemon=True)
    worker.start()

    run_id = wait_for_latest_run_id_fn(runs_root, time.time())
    include_events = {item.strip() for item in tail_event.split(",") if item.strip()} if tail_event else set()
    if run_id:
        tail_events_fn(
            runs_root / run_id / "events.jsonl",
            done,
            tail_format=tail_format,
            min_level=tail_level,
            include_events=include_events,
        )
    worker.join()
    return run_id_holder["value"] or run_id


def execute_chain_with_follow(
    *,
    orchestrator: Any,
    chain_path: Path,
    mock: bool,
    runs_root: Path,
    tail_event: str,
    tail_format: str,
    tail_level: str,
    wait_for_latest_run_id_fn: Callable[..., str],
    tail_events_fn: Callable[..., None],
) -> dict[str, Any]:
    report_holder: dict[str, dict[str, Any]] = {}
    done = threading.Event()

    def _run_chain() -> None:
        try:
            report_holder["report"] = orchestrator.execute_chain(chain_path, mock_mode=mock)
        finally:
            done.set()

    worker = threading.Thread(target=_run_chain, daemon=True)
    worker.start()

    run_id = wait_for_latest_run_id_fn(runs_root, time.time())
    include_events = {item.strip() for item in tail_event.split(",") if item.strip()} if tail_event else set()
    if run_id:
        tail_events_fn(
            runs_root / run_id / "events.jsonl",
            done,
            tail_format=tail_format,
            min_level=tail_level,
            include_events=include_events,
        )
    worker.join()
    return report_holder.get("report", {})


def run_temporal_worker() -> None:
    from cortexpilot_orch.temporal.worker import run_worker

    run_worker()


def serve_api(*, api_app: Any, uvicorn_module: Any, host: str, port: int) -> None:
    uvicorn_module.run(api_app, host=host, port=port, reload=False)
