from __future__ import annotations

import json
import threading
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table
import uvicorn

from cortexpilot_orch.api.main import app as api_app
from cortexpilot_orch.contract.compiler import compile_plan
from cortexpilot_orch.contract.validator import ContractValidator
from cortexpilot_orch.config import load_config
from cortexpilot_orch.mcp_queue_pilot_server import serve_queue_pilot_mcp
from cortexpilot_orch.mcp_readonly_server import serve_readonly_mcp
from cortexpilot_orch.planning.coverage_chain import (
    DEFAULT_COVERAGE_JSON,
    build_coverage_self_heal_chain,
    load_coverage_targets,
    run_coverage_scan,
    write_chain,
)
from cortexpilot_orch.queue import QueueStore
from cortexpilot_orch.scheduler.scheduler import Orchestrator
from cortexpilot_orch.store.session_map import SessionAliasStore
from cortexpilot_orch.locks.locker import release_lock
from cortexpilot_orch.runtime.retention import (
    apply_retention_plan,
    build_retention_plan,
    write_retention_report,
)
from cortexpilot_orch import cli_command_helpers, cli_coverage_helpers, cli_runtime_helpers

app = typer.Typer()
session_app = typer.Typer()
cleanup_app = typer.Typer()
console = Console()
app.add_typer(session_app, name="session-alias")
app.add_typer(cleanup_app, name="cleanup")
def _repo_root() -> Path:
    return cli_runtime_helpers.repo_root()
def _runs_root() -> Path:
    return cli_runtime_helpers.runs_root(_repo_root())
def _equilibrium_health_url(base_url: str) -> str:
    return cli_coverage_helpers.equilibrium_health_url(base_url)
def _equilibrium_healthcheck(base_url: str, timeout_sec: float = 1.5) -> bool:
    return cli_coverage_helpers.equilibrium_healthcheck(base_url, timeout_sec=timeout_sec)
def _enable_lock_auto_cleanup_for_coverage() -> dict[str, Any]:
    return cli_coverage_helpers.enable_lock_auto_cleanup_for_coverage()
def _enable_chain_subprocess_timeout_for_coverage() -> dict[str, Any]:
    return cli_coverage_helpers.enable_chain_subprocess_timeout_for_coverage()
def _ensure_coverage_python_env() -> dict[str, Any]:
    return cli_coverage_helpers.ensure_coverage_python_env(_repo_root())
def _resolve_coverage_worker_batch_size(
    worker_batch_size: int,
    *,
    execute: bool,
    mock_mode: bool,
) -> tuple[int | None, str]:
    if worker_batch_size < 0:
        raise typer.BadParameter("--worker-batch-size must be >= 0")
    if worker_batch_size > 0:
        return worker_batch_size, "cli"
    if execute and not mock_mode:
        return 2, "coverage_execute_default"
    return None, "no_batch"
def _prepare_coverage_execute_env(mock_mode: bool) -> dict[str, Any]:
    return cli_coverage_helpers.prepare_coverage_execute_env(
        mock_mode,
        load_config_fn=load_config,
        repo_root=_repo_root(),
        equilibrium_healthcheck_fn=_equilibrium_healthcheck,
        equilibrium_health_url_fn=_equilibrium_health_url,
    )
_wait_for_latest_run_id = cli_runtime_helpers.wait_for_latest_run_id
_event_level = cli_runtime_helpers.event_level
_parse_event_line = cli_runtime_helpers.parse_event_line
_compact_context = cli_runtime_helpers.compact_context
_format_pretty_event = cli_runtime_helpers.format_pretty_event
def _tail_events(
    path: Path,
    done: threading.Event,
    idle_sec: float = 1.0,
    tail_format: str = "pretty",
    min_level: str = "INFO",
    include_events: set[str] | None = None,
) -> None:
    cli_runtime_helpers.tail_events(
        path,
        done,
        console_obj=console,
        idle_sec=idle_sec,
        tail_format=tail_format,
        min_level=min_level,
        include_events=include_events,
    )
def _read_manifest_status(run_id: str) -> str:
    return cli_runtime_helpers.read_manifest_status(run_id, load_config().runs_root)
_hooks_auto_install_enabled = cli_runtime_helpers.hooks_auto_install_enabled
_install_hooks = cli_runtime_helpers.install_hooks
_hooks_status = cli_runtime_helpers.hooks_status


@app.command()
def init() -> None:
    cfg = load_config()
    cfg.runtime_root.mkdir(parents=True, exist_ok=True)
    cfg.runs_root.mkdir(parents=True, exist_ok=True)
    cfg.worktree_root.mkdir(parents=True, exist_ok=True)
    (cfg.runtime_root / "locks").mkdir(parents=True, exist_ok=True)
    if _hooks_auto_install_enabled():
        ok, message = _install_hooks(_repo_root())
        if ok:
            console.print(message, style="green")
        else:
            console.print(message, style="yellow")
    console.print("init complete", style="green")


@app.command()
def doctor() -> None:
    table = Table(title="cortexpilot doctor")
    table.add_column("tool")
    table.add_column("status")

    for tool in ["git", "codex", sys.executable]:
        name = tool
        if tool == sys.executable:
            name = "python"
        ok = shutil.which(tool) is not None if tool != sys.executable else True
        table.add_row(name, "ok" if ok else "missing")

    git_head_ok = False
    try:
        subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True)
        git_head_ok = True
    except Exception:  # noqa: BLE001
        git_head_ok = False
    table.add_row("git_head", "ok" if git_head_ok else "missing")
    table.add_row("hooks", "ok" if _hooks_status(_repo_root()) else "missing")

    console.print(table)


@app.command()
def run(
    contract_path: Path,
    mock: bool = typer.Option(False, "--mock"),
    force_unlock: bool = typer.Option(False, "--force-unlock"),
    runner: str = typer.Option("", "--runner"),
    follow: bool = typer.Option(False, "--follow"),
    tail_format: str = typer.Option("pretty", "--tail-format"),
    tail_level: str = typer.Option("INFO", "--tail-level"),
    tail_event: str = typer.Option("", "--tail-event"),
) -> None:
    contract_path = contract_path.resolve()
    prev_force_unlock = os.environ.get("CORTEXPILOT_FORCE_UNLOCK")
    prev_runner = os.environ.get("CORTEXPILOT_RUNNER")
    try:
        if force_unlock:
            os.environ["CORTEXPILOT_FORCE_UNLOCK"] = "1"
            validated_contract = ContractValidator().validate_contract_file(contract_path)
            allowed_paths = validated_contract.get("allowed_paths", [])
            if not isinstance(allowed_paths, list):
                raise ValueError("force unlock requires list[str] allowed_paths")
            scoped_paths = [path.strip() for path in allowed_paths if isinstance(path, str) and path.strip()]
            if not scoped_paths:
                raise ValueError("force unlock requires non-empty allowed_paths")
            release_lock(scoped_paths)
        else:
            os.environ.pop("CORTEXPILOT_FORCE_UNLOCK", None)
        if runner:
            os.environ["CORTEXPILOT_RUNNER"] = runner
        orch = Orchestrator(_repo_root())
        if not follow:
            run_id = orch.execute_task(contract_path, mock_mode=mock)
            console.print(f"run_id={run_id}")
            return
        run_id = cli_command_helpers.execute_task_with_follow(
            orchestrator=orch,
            contract_path=contract_path,
            mock=mock,
            runs_root=_runs_root(),
            tail_event=tail_event,
            tail_format=tail_format,
            tail_level=tail_level,
            wait_for_latest_run_id_fn=_wait_for_latest_run_id,
            tail_events_fn=_tail_events,
        )
        console.print(f"run_id={run_id}")
    finally:
        if prev_force_unlock is None:
            os.environ.pop("CORTEXPILOT_FORCE_UNLOCK", None)
        else:
            os.environ["CORTEXPILOT_FORCE_UNLOCK"] = prev_force_unlock
        if runner:
            if prev_runner is None:
                os.environ.pop("CORTEXPILOT_RUNNER", None)
            else:
                os.environ["CORTEXPILOT_RUNNER"] = prev_runner


@app.command("run-chain")
def run_chain(
    chain_path: Path,
    mock: bool = typer.Option(False, "--mock"),
    follow: bool = typer.Option(False, "--follow"),
    tail_format: str = typer.Option("pretty", "--tail-format"),
    tail_level: str = typer.Option("INFO", "--tail-level"),
    tail_event: str = typer.Option("", "--tail-event"),
) -> None:
    chain_path = chain_path.resolve()
    prev_force_unlock = os.environ.get("CORTEXPILOT_FORCE_UNLOCK")
    try:
        os.environ.pop("CORTEXPILOT_FORCE_UNLOCK", None)
        orch = Orchestrator(_repo_root())
        if not follow:
            report = orch.execute_chain(chain_path, mock_mode=mock)
            console.print(json.dumps(report, ensure_ascii=False, indent=2))
            return
        report = cli_command_helpers.execute_chain_with_follow(
            orchestrator=orch,
            chain_path=chain_path,
            mock=mock,
            runs_root=_runs_root(),
            tail_event=tail_event,
            tail_format=tail_format,
            tail_level=tail_level,
            wait_for_latest_run_id_fn=_wait_for_latest_run_id,
            tail_events_fn=_tail_events,
        )
        console.print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        if prev_force_unlock is None:
            os.environ.pop("CORTEXPILOT_FORCE_UNLOCK", None)
        else:
            os.environ["CORTEXPILOT_FORCE_UNLOCK"] = prev_force_unlock


@app.command("coverage-self-heal-chain")
def coverage_self_heal_chain(
    threshold: float = typer.Option(90.0, "--threshold", help="Select modules below this coverage percent."),
    max_workers: int = typer.Option(4, "--max-workers", help="Maximum parallel worker contracts in chain."),
    worker_batch_size: int = typer.Option(
        0,
        "--worker-batch-size",
        help=(
            "Worker batch size for staged parallel execution. "
            "0 means auto (execute non-mock defaults to 2; otherwise no batching)."
        ),
    ),
    coverage_json: Path = typer.Option(DEFAULT_COVERAGE_JSON, "--coverage-json", help="Coverage JSON report path."),
    coverage_metric: str = typer.Option(
        "branches",
        "--coverage-metric",
        help="Coverage metric used for low-coverage selection: branches | statements | overall.",
    ),
    refresh_coverage: bool = typer.Option(False, "--refresh-coverage", help="Run pytest coverage scan before building chain."),
    auto_refresh_if_missing: bool = typer.Option(
        True,
        "--auto-refresh-if-missing/--no-auto-refresh-if-missing",
        help="Auto-run coverage scan when --coverage-json is missing.",
    ),
    output: Path | None = typer.Option(None, "--output", help="Output task_chain path."),
    chain_id: str | None = typer.Option(None, "--chain-id", help="Explicit task_chain id override."),
    execute: bool = typer.Option(False, "--execute", help="Execute chain immediately after generation."),
    mock: bool = typer.Option(False, "--mock", help="Execute chain in mock mode when --execute is set."),
    enable_commit_stage: bool = typer.Option(
        False,
        "--enable-commit-stage",
        help="Append TL local commit stage after test gate (never pushes).",
    ),
    commit_message: str = typer.Option(
        "chore(coverage): self-heal low coverage modules",
        "--commit-message",
        help="Commit message used when --enable-commit-stage is enabled.",
    ),
) -> None:
    repo_root = _repo_root()
    coverage_path = coverage_json if coverage_json.is_absolute() else (repo_root / coverage_json)
    metric = coverage_metric.strip().lower()
    if metric not in {"branches", "statements", "overall"}:
        raise typer.BadParameter("--coverage-metric must be one of: branches, statements, overall")

    coverage_refreshed = False
    if refresh_coverage or (auto_refresh_if_missing and not coverage_path.exists()):
        run_coverage_scan(repo_root, coverage_path)
        coverage_refreshed = True

    if not coverage_path.exists():
        raise typer.BadParameter(f"coverage json not found: {coverage_path}")

    targets = load_coverage_targets(
        coverage_report_path=coverage_path,
        threshold=threshold,
        max_workers=max_workers,
        coverage_metric=metric,
    )
    if not targets:
        console.print("no low coverage modules found under threshold")
        raise typer.Exit(code=1)

    effective_worker_batch_size, worker_batch_source = _resolve_coverage_worker_batch_size(
        worker_batch_size,
        execute=execute,
        mock_mode=mock,
    )

    test_gate_cmd = "echo mock test gate passed" if mock else None
    chain = build_coverage_self_heal_chain(
        targets,
        chain_id=chain_id,
        test_gate_cmd=test_gate_cmd,
        coverage_metric=metric,
        enable_commit_stage=enable_commit_stage,
        commit_message=commit_message,
        strict_worker_tests=not mock,
        worker_batch_size=effective_worker_batch_size,
    )
    output_path = output
    if output_path is None:
        output_path = repo_root / "contracts" / "tasks" / f"{chain['chain_id']}.json"
    elif not output_path.is_absolute():
        output_path = repo_root / output_path
    written = write_chain(chain, output_path)

    summary: dict[str, Any] = {
        "chain_id": chain["chain_id"],
        "output_path": str(written),
        "coverage_json": str(coverage_path),
        "coverage_metric": metric,
        "coverage_refreshed": coverage_refreshed,
        "threshold": threshold,
        "max_workers": max_workers,
        "worker_batch_size": effective_worker_batch_size,
        "worker_batch_source": worker_batch_source,
        "enable_commit_stage": enable_commit_stage,
        "workers": [
            {
                "module": target.module_name,
                "path": target.module_path,
                "coverage": round(target.coverage, 2),
            }
            for target in targets
        ],
    }

    if execute:
        snapshot_env = dict(os.environ)
        try:
            execution_fallback = _prepare_coverage_execute_env(mock)
            orch = Orchestrator(repo_root)
            report = orch.execute_chain(written, mock_mode=mock)
            summary["execution"] = {
                "run_id": report.get("run_id", ""),
                "status": report.get("status", "UNKNOWN"),
                "mock": mock,
                "fallback": execution_fallback,
            }
        finally:
            os.environ.clear()
            os.environ.update(snapshot_env)

    console.print(json.dumps(summary, ensure_ascii=False, indent=2))


@app.command()
def enqueue(contract_path: Path) -> None:
    item = cli_command_helpers.enqueue_contract(
        contract_path,
        validator_cls=ContractValidator,
        queue_store_cls=QueueStore,
    )
    console.print(json.dumps(item, ensure_ascii=False, indent=2))


@session_app.command("set")
def session_alias_set(
    alias: str,
    session_id: str,
    thread_id: str = typer.Option("", "--thread-id"),
    note: str = typer.Option("", "--note"),
) -> None:
    payload = cli_command_helpers.session_alias_set_record(
        alias,
        session_id,
        thread_id=thread_id,
        note=note,
        session_alias_store_cls=SessionAliasStore,
    )
    console.print(json.dumps(payload, ensure_ascii=False, indent=2))


@session_app.command("get")
def session_alias_get(alias: str) -> None:
    payload = cli_command_helpers.session_alias_get_record(alias, session_alias_store_cls=SessionAliasStore)
    if payload is None:
        console.print("alias not found")
        raise typer.Exit(code=1)
    console.print(json.dumps(payload, ensure_ascii=False, indent=2))


@session_app.command("list")
def session_alias_list() -> None:
    records = cli_command_helpers.session_alias_list_records(session_alias_store_cls=SessionAliasStore)
    console.print(json.dumps(records, ensure_ascii=False, indent=2))


@session_app.command("delete")
def session_alias_delete(alias: str) -> None:
    deleted = cli_command_helpers.session_alias_delete_record(alias, session_alias_store_cls=SessionAliasStore)
    if deleted:
        console.print("alias deleted")
        return
    console.print("alias not found")
    raise typer.Exit(code=1)


@cleanup_app.command("runtime")
def cleanup_runtime(
    dry_run: bool = typer.Option(False, "--dry-run"),
    apply: bool = typer.Option(False, "--apply"),
) -> None:
    os.chdir(_repo_root())
    try:
        summary = cli_command_helpers.cleanup_runtime_summary(
            dry_run=dry_run,
            apply=apply,
            load_config_fn=load_config,
            build_retention_plan_fn=build_retention_plan,
            apply_retention_plan_fn=apply_retention_plan,
            write_retention_report_fn=write_retention_report,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(json.dumps(summary, ensure_ascii=False, indent=2))


@app.command("compile-plan")
def compile_plan_cmd(plan_path: Path, output_path: Path | None = None) -> None:
    try:
        written_path = cli_command_helpers.compile_plan_to_contract(
            plan_path,
            output_path,
            compile_plan_fn=compile_plan,
            repo_root=_repo_root(),
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(f"contract_written={written_path}")


@app.command("run-next")
def run_next(mock: bool = typer.Option(False, "--mock")) -> None:
    queue_store = QueueStore()
    item = queue_store.claim_next(run_id="")
    if not item:
        console.print("queue empty")
        return
    contract_path = Path(str(item.get("contract_path", ""))).resolve()
    task_id = str(item.get("task_id", "task"))
    run_id = Orchestrator(_repo_root()).execute_task(contract_path, mock_mode=mock)
    queue_store.mark_done(task_id, run_id, _read_manifest_status(run_id))
    console.print(f"run_id={run_id}")


@app.command()
def replay(
    run_id: str,
    baseline_run_id: str | None = typer.Option(None, "--baseline-run-id"),
    verify: bool = typer.Option(False, "--verify"),
    strict: bool = typer.Option(False, "--strict"),
    reexec: bool = typer.Option(False, "--reexec"),
) -> None:
    try:
        report = cli_command_helpers.replay_report(
            run_id=run_id,
            baseline_run_id=baseline_run_id,
            verify=verify,
            strict=strict,
            reexec=reexec,
            orchestrator=Orchestrator(_repo_root()),
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(json.dumps(report, ensure_ascii=False, indent=2))


@app.command("temporal-worker")
def temporal_worker() -> None:
    cli_command_helpers.run_temporal_worker()


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    cli_command_helpers.serve_api(api_app=api_app, uvicorn_module=uvicorn, host=host, port=port)


@app.command("mcp-readonly-server")
def mcp_readonly_server() -> None:
    serve_readonly_mcp()


@app.command("mcp-queue-pilot-server")
def mcp_queue_pilot_server() -> None:
    serve_queue_pilot_mcp()


if __name__ == "__main__":
    app()
