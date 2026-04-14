#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.ui_full_e2e_gemini_audit_common import (
    INTERACTION_SCREEN_DIR,
    PAGE_SCREEN_DIR,
    ROOT,
    RUNTIME_LOGS,
    RUNTIME_OUT,
    RuntimeBudgetExceeded,
    ensure_dir,
    now_iso,
    write_json_atomic,
)
from scripts.ui_full_e2e_gemini_audit_gemini import GeminiAnalyzer
from scripts.ui_full_e2e_gemini_audit_reports import build_click_inventory_report, build_markdown_report
from scripts.ui_full_e2e_gemini_audit_runner import execute_playwright_audit
from scripts.ui_full_e2e_gemini_audit_runtime import (
    discover_page_routes,
    ensure_playwright_browser_ready,
    http_json,
    http_ok,
    kill_process,
    resolve_free_port,
    route_with_dynamic_ids,
    spawn_process,
    wait_http_ok,
)


def _load_env_var_from_dotenv_if_missing(key: str) -> None:
    if os.environ.get(key, "").strip():
        return
    for env_name in (".env.local", ".env"):
        path = ROOT / env_name
        if not path.exists():
            continue
        try:
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                raw = line.strip()
                if not raw or raw.startswith("#") or "=" not in raw:
                    continue
                lhs, rhs = raw.split("=", 1)
                if lhs.strip() != key:
                    continue
                value = rhs.strip().strip('"').strip("'")
                if value:
                    os.environ[key] = value
                    return
        except Exception:
            continue


def _load_env_var_from_zsh_if_missing(key: str) -> None:
    if str(os.environ.get("OPENVIBECODING_UI_DISABLE_ZSH_ENV", "")).strip().lower() in {"1", "true", "yes", "on"}:
        return
    if os.environ.get(key, "").strip():
        return
    try:
        result = subprocess.run(
            ["zsh", "-lc", f"printenv {key}"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return
    value = (result.stdout or "").strip().splitlines()
    if not value:
        return
    resolved = value[0].strip()
    if resolved:
        os.environ[key] = resolved
        return
    for zsh_name in (".zshenv", ".zprofile", ".zshrc"):
        zsh_path = os.path.expanduser(f"~/{zsh_name}")
        if not os.path.exists(zsh_path):
            continue
        try:
            with open(zsh_path, "r", encoding="utf-8", errors="replace") as zsh_file:
                for line in zsh_file.read().splitlines():
                    raw = line.strip()
                    if not raw or raw.startswith("#") or "=" not in raw:
                        continue
                    raw_no_comment = raw.split("#", 1)[0].strip()
                    if raw_no_comment.startswith("export "):
                        raw_no_comment = raw_no_comment[len("export ") :].strip()
                    if not raw_no_comment.startswith(f"{key}="):
                        continue
                    _, rhs = raw_no_comment.split("=", 1)
                    candidate = rhs.strip().strip('"').strip("'")
                    if candidate:
                        os.environ[key] = candidate
                        return
        except Exception:
            continue


def _prime_llm_keys() -> None:
    for key in ("GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        _load_env_var_from_dotenv_if_missing(key)
        _load_env_var_from_zsh_if_missing(key)


def _parse_args() -> argparse.Namespace:
    def _env_flag(name: str, default: bool = False) -> bool:
        raw = str(os.environ.get(name, "")).strip().lower()
        if not raw:
            return default
        return raw in {"1", "true", "yes", "on"}

    parser = argparse.ArgumentParser(
        description="Headed full-page/full-button E2E audit with Gemini multimodal analysis."
    )
    parser.add_argument("--host", default=os.environ.get("OPENVIBECODING_E2E_HOST", "127.0.0.1"))
    parser.add_argument("--api-port", type=int, default=int(os.environ.get("OPENVIBECODING_UI_FULL_E2E_API_PORT", "19600")))
    parser.add_argument(
        "--dashboard-port", type=int, default=int(os.environ.get("OPENVIBECODING_UI_FULL_E2E_DASHBOARD_PORT", "19700"))
    )
    parser.add_argument("--external-api-base", default=os.environ.get("OPENVIBECODING_UI_FULL_E2E_EXTERNAL_API_BASE", ""))
    parser.add_argument(
        "--external-dashboard-base", default=os.environ.get("OPENVIBECODING_UI_FULL_E2E_EXTERNAL_DASHBOARD_BASE", "")
    )
    parser.add_argument(
        "--api-token",
        default=(
            os.environ.get("OPENVIBECODING_E2E_API_TOKEN")
            or os.environ.get("OPENVIBECODING_API_TOKEN")
            or "openvibecoding-e2e-token"
        ),
    )
    parser.add_argument("--gemini-model", default=os.environ.get("OPENVIBECODING_UI_GEMINI_MODEL", "gemini-3.0-flash"))
    parser.add_argument("--provider", default=os.environ.get("OPENVIBECODING_UI_AUDIT_PROVIDER", "gemini"))
    parser.add_argument("--provider-base-url", default=os.environ.get("OPENVIBECODING_UI_PROVIDER_BASE_URL", ""))
    parser.add_argument("--provider-model", default=os.environ.get("OPENVIBECODING_UI_PROVIDER_MODEL", ""))
    parser.add_argument("--thinking-level", default=os.environ.get("OPENVIBECODING_UI_GEMINI_THINKING_LEVEL", "high"))
    parser.add_argument("--gemini-key-env", default=os.environ.get("OPENVIBECODING_UI_GEMINI_KEY_ENV", "GEMINI_API_KEY"))
    parser.add_argument(
        "--gemini-request-timeout-sec",
        type=int,
        default=int(os.environ.get("OPENVIBECODING_UI_GEMINI_REQUEST_TIMEOUT_SEC", "75")),
    )
    parser.add_argument(
        "--gemini-max-attempts",
        type=int,
        default=int(os.environ.get("OPENVIBECODING_UI_GEMINI_MAX_ATTEMPTS", "5")),
    )
    parser.add_argument("--max-pages", type=int, default=int(os.environ.get("OPENVIBECODING_UI_FULL_E2E_MAX_PAGES", "0")))
    parser.add_argument(
        "--max-buttons-per-page",
        type=int,
        default=int(os.environ.get("OPENVIBECODING_UI_FULL_E2E_MAX_BUTTONS_PER_PAGE", "120")),
    )
    parser.add_argument(
        "--max-interactions",
        type=int,
        default=int(os.environ.get("OPENVIBECODING_UI_FULL_E2E_MAX_INTERACTIONS", "504")),
        help="Global interaction budget across all routes; 0 disables cap.",
    )
    parser.add_argument(
        "--max-duplicate-targets",
        type=int,
        default=int(os.environ.get("OPENVIBECODING_UI_FULL_E2E_MAX_DUPLICATE_TARGETS", "3")),
        help="Maximum number of targets retained per semantic signature on each route.",
    )
    parser.add_argument(
        "--navigation-timeout-ms", type=int, default=int(os.environ.get("OPENVIBECODING_UI_FULL_E2E_NAV_TIMEOUT_MS", "30000"))
    )
    parser.add_argument(
        "--action-timeout-ms", type=int, default=int(os.environ.get("OPENVIBECODING_UI_FULL_E2E_ACTION_TIMEOUT_MS", "10000"))
    )
    parser.add_argument("--page-settle-ms", type=int, default=int(os.environ.get("OPENVIBECODING_UI_FULL_E2E_PAGE_SETTLE_MS", "1500")))
    parser.add_argument(
        "--interaction-settle-ms",
        type=int,
        default=int(os.environ.get("OPENVIBECODING_UI_FULL_E2E_INTERACTION_SETTLE_MS", "1200")),
    )
    parser.add_argument(
        "--max-runtime-sec",
        type=int,
        default=int(os.environ.get("OPENVIBECODING_UI_FULL_E2E_MAX_RUNTIME_SEC", "0")),
        help="Hard runtime budget for one shard; 0 means no explicit runtime cap.",
    )
    parser.add_argument(
        "--heartbeat-interval-sec",
        type=int,
        default=int(os.environ.get("OPENVIBECODING_UI_FULL_E2E_HEARTBEAT_INTERVAL_SEC", "20")),
        help="Emit and persist heartbeat every N seconds while this shard is running.",
    )
    parser.add_argument("--run-id", default=os.environ.get("OPENVIBECODING_UI_FULL_E2E_RUN_ID", "").strip())
    parser.add_argument(
        "--route-shard-total",
        type=int,
        default=int(os.environ.get("OPENVIBECODING_UI_FULL_E2E_ROUTE_SHARD_TOTAL", "1")),
        help="Total shard count for route-level parallel execution.",
    )
    parser.add_argument(
        "--route-shard-index",
        type=int,
        default=int(os.environ.get("OPENVIBECODING_UI_FULL_E2E_ROUTE_SHARD_INDEX", "0")),
        help="Current shard index (0-based).",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        default=_env_flag("OPENVIBECODING_UI_FULL_E2E_HEADED", False),
        help="Run visible browser (headed). Default is headless to avoid focus stealing.",
    )
    return parser.parse_args()


def _validate_args(args: argparse.Namespace) -> int:
    if args.route_shard_total < 1:
        print("❌ --route-shard-total must be >= 1", file=sys.stderr)
        return 2
    if args.route_shard_index < 0 or args.route_shard_index >= args.route_shard_total:
        print("❌ --route-shard-index must be within [0, route-shard-total)", file=sys.stderr)
        return 2
    provider = str(args.provider or "").strip().lower()
    if provider == "gemini" and not os.environ.get(args.gemini_key_env, "").strip():
        print(f"❌ missing Gemini API key env: {args.gemini_key_env}", file=sys.stderr)
        return 2
    if provider != "gemini":
        print(f"❌ unsupported --provider: {provider}. currently supported: gemini", file=sys.stderr)
        return 2
    return 0


def _resolve_git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:  # noqa: BLE001
        return ""
    return (result.stdout or "").strip()


def _resolve_server_mode(args: argparse.Namespace) -> tuple[bool, str, str, int, int, int]:
    external_api_base = str(args.external_api_base or "").strip()
    external_dashboard_base = str(args.external_dashboard_base or "").strip()
    use_external_servers = bool(external_api_base or external_dashboard_base)
    if use_external_servers and not (external_api_base and external_dashboard_base):
        print("❌ both --external-api-base and --external-dashboard-base are required together", file=sys.stderr)
        return False, "", "", 0, 0, 2

    if not use_external_servers:
        requested_api_base = f"http://{args.host}:{args.api_port}"
        requested_dashboard_base = f"http://{args.host}:{args.dashboard_port}"
        if http_ok(f"{requested_api_base}/health", timeout_sec=2) and http_ok(
            f"{requested_dashboard_base}/pm",
            timeout_sec=3,
        ):
            external_api_base = requested_api_base
            external_dashboard_base = requested_dashboard_base
            use_external_servers = True
            print(
                "⚠️ [ui-full-e2e] detected healthy existing api/dashboard, "
                f"reusing: api={external_api_base} dashboard={external_dashboard_base}"
            )

    resolved_api_port = int(args.api_port)
    resolved_dashboard_port = int(args.dashboard_port)
    if not use_external_servers:
        resolved_api_port = resolve_free_port(args.host, args.api_port)
        resolved_dashboard_port = resolve_free_port(
            args.host,
            args.dashboard_port,
            avoid_port=resolved_api_port,
        )
        if resolved_api_port != int(args.api_port):
            print(f"⚠️ [ui-full-e2e] api port in use, shifted: {args.api_port} -> {resolved_api_port}")
        if resolved_dashboard_port != int(args.dashboard_port):
            print(f"⚠️ [ui-full-e2e] dashboard port in use, shifted: {args.dashboard_port} -> {resolved_dashboard_port}")

    return use_external_servers, external_api_base, external_dashboard_base, resolved_api_port, resolved_dashboard_port, 0


def _build_paths(run_id: str) -> dict[str, Any]:
    out_dir = RUNTIME_OUT / run_id
    page_dir = out_dir / PAGE_SCREEN_DIR
    interaction_dir = out_dir / INTERACTION_SCREEN_DIR
    ensure_dir(out_dir)
    ensure_dir(page_dir)
    ensure_dir(interaction_dir)
    ensure_dir(RUNTIME_LOGS)

    api_log = RUNTIME_LOGS / f"ui_full_e2e_api_{run_id}.log"
    dashboard_log = RUNTIME_LOGS / f"ui_full_e2e_dashboard_{run_id}.log"
    return {
        "out_dir": out_dir,
        "page_dir": page_dir,
        "interaction_dir": interaction_dir,
        "api_log": api_log,
        "dashboard_log": dashboard_log,
        "report_json": out_dir / "report.json",
        "report_md": out_dir / "report.md",
        "click_inventory_report_json": out_dir / "click_inventory_report.json",
        "heartbeat_json": out_dir / "heartbeat.json",
        "failure_snapshot_json": out_dir / "failure_snapshot.json",
    }


def _seed_ids(base_api: str, api_token: str, payload: dict[str, Any]) -> dict[str, str]:
    intake_id = ""
    intake_ready = False
    try:
        intake = http_json(
            base_api,
            "/api/pm/intake",
            method="POST",
            token=api_token,
            payload={
                "objective": "UI full e2e audit seed",
                "allowed_paths": ["apps/dashboard"],
                "constraints": ["ui_full_e2e_seed"],
                "acceptance_tests": [{"name": "seed", "cmd": "echo seed", "must_pass": False}],
                "mcp_tool_set": ["codex"],
                "requester_role": "PM",
                "browser_policy_preset": "safe",
            },
            timeout_sec=20,
        )
        if isinstance(intake, dict):
            intake_id = str(intake.get("intake_id") or "").strip()
    except Exception as exc:
        payload["errors"].append(f"seed intake create failed: {exc}")

    if intake_id:
        try:
            http_json(
                base_api,
                f"/api/pm/intake/{urllib.parse.quote(intake_id)}/answer",
                method="POST",
                token=api_token,
                payload={
                    "answers": ["继续，保持最小变更，优先保证 UI 审计链路可运行。"],
                    "auto_run_chain": False,
                    "mock_chain": False,
                },
                timeout_sec=25,
            )
            intake_ready = True
        except Exception as exc:
            payload["errors"].append(f"seed intake answer failed: {exc}")
        if intake_ready:
            try:
                http_json(
                    base_api,
                    f"/api/pm/intake/{urllib.parse.quote(intake_id)}/run",
                    method="POST",
                    token=api_token,
                    payload={"runner": "agents", "mock": True, "strict_acceptance": False},
                    timeout_sec=25,
                )
            except Exception as exc:
                payload["errors"].append(f"seed run intake failed: {exc}")
        else:
            payload["errors"].append("seed intake skipped run readiness: answer stage did not succeed")

    sessions: list[Any] | dict[str, Any] = []
    runs: list[Any] | dict[str, Any] = []
    workflows: list[Any] | dict[str, Any] = []
    try:
        sessions = http_json(base_api, "/api/pm/sessions?limit=20", token=api_token, timeout_sec=20)
    except Exception as exc:
        payload["errors"].append(f"fetch pm sessions failed: {exc}")
    try:
        runs = http_json(base_api, "/api/runs", token=api_token, timeout_sec=20)
    except Exception as exc:
        payload["errors"].append(f"fetch runs failed: {exc}")
    try:
        workflows = http_json(base_api, "/api/workflows", token=api_token, timeout_sec=20)
    except Exception as exc:
        payload["errors"].append(f"fetch workflows failed: {exc}")

    session_id = ""
    if isinstance(sessions, list) and sessions:
        first = sessions[0]
        if isinstance(first, dict):
            session_id = str(first.get("pm_session_id") or first.get("intake_id") or "").strip()

    run_id_val = ""
    if isinstance(runs, list) and runs:
        first = runs[0]
        if isinstance(first, dict):
            run_id_val = str(first.get("run_id") or "").strip()

    workflow_id = ""
    if isinstance(workflows, list) and workflows:
        first = workflows[0]
        if isinstance(first, dict):
            workflow_id = str(first.get("workflow_id") or "").strip()

    return {
        "pm_session_id": session_id,
        "run_id": run_id_val,
        "workflow_id": workflow_id,
    }


def _merge_click_inventory_summary(payload: dict[str, Any], click_inventory_payload: dict[str, Any]) -> None:
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        summary = {}
        payload["summary"] = summary
    click_summary = click_inventory_payload.get("summary")
    if not isinstance(click_summary, dict):
        click_summary = {}
    payload["click_inventory_summary"] = click_summary
    summary["interaction_click_failures"] = int(click_summary.get("click_failures", 0) or 0)
    summary["gemini_warn_or_fail"] = int(click_summary.get("analysis_warn_or_fail_count", 0) or 0)
    summary.update(
        {
            "click_inventory_entries": int(click_summary.get("total_entries", 0) or 0),
            "click_inventory_blocking_failures": int(click_summary.get("blocking_failures", 0) or 0),
            "click_inventory_missing_target_refs": int(click_summary.get("missing_target_ref_count", 0) or 0),
            "click_inventory_overall_passed": bool(click_summary.get("overall_passed", False)),
        }
    )


def main() -> int:
    _prime_llm_keys()
    args = _parse_args()
    provider = str(args.provider or "").strip().lower() or "gemini"
    provider_base_url = str(args.provider_base_url or "").strip()
    provider_model = str(args.provider_model or "").strip()
    if provider == "gemini" and not provider_model:
        provider_model = str(args.gemini_model or "").strip()
    thinking_level = str(args.thinking_level or "").strip() or "high"
    git_sha = _resolve_git_sha()
    command = shlex.join(sys.argv)
    code = _validate_args(args)
    if code != 0:
        return code

    ensure_playwright_browser_ready(python_executable=sys.executable, logger=print)

    use_external_servers, external_api_base, external_dashboard_base, resolved_api_port, resolved_dashboard_port, code = (
        _resolve_server_mode(args)
    )
    if code != 0:
        return code

    run_id = args.run_id or f"ui_full_e2e_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    paths = _build_paths(run_id)

    api_proc: subprocess.Popen[str] | None = None
    ui_proc: subprocess.Popen[str] | None = None

    base_api = external_api_base or f"http://{args.host}:{resolved_api_port}"
    base_dashboard = external_dashboard_base or f"http://{args.host}:{resolved_dashboard_port}"

    payload: dict[str, Any] = {
        "run_id": run_id,
        "started_at": now_iso(),
        "dashboard_base_url": base_dashboard,
        "api_base_url": base_api,
        "route_shard_total": args.route_shard_total,
        "route_shard_index": args.route_shard_index,
        "api_log": str(paths["api_log"]),
        "dashboard_log": str(paths["dashboard_log"]),
        "heartbeat_path": str(paths["heartbeat_json"]),
        "failure_snapshot_path": str(paths["failure_snapshot_json"]),
        "provider": provider,
        "provider_base_url": provider_base_url,
        "provider_model": provider_model,
        "thinking_level": thinking_level,
        "git_sha": git_sha,
        "command": command,
        "routes": [],
        "summary": {},
        "errors": [],
    }

    heartbeat_interval_sec = max(1, int(args.heartbeat_interval_sec))
    heartbeat_last_emit_monotonic = 0.0
    heartbeat_state: dict[str, Any] = {
        "run_id": run_id,
        "pid": os.getpid(),
        "started_at": payload["started_at"],
        "route_shard_total": int(args.route_shard_total),
        "route_shard_index": int(args.route_shard_index),
        "max_runtime_sec": int(args.max_runtime_sec),
        "stage": "init",
        "updated_at": now_iso(),
    }

    def update_heartbeat(stage: str, force: bool = False, **extra: Any) -> None:
        nonlocal heartbeat_last_emit_monotonic
        now_iso_val = now_iso()
        now_mono = time.monotonic()
        heartbeat_state.update(extra)
        heartbeat_state["stage"] = str(stage)
        heartbeat_state["updated_at"] = now_iso_val
        write_json_atomic(paths["heartbeat_json"], heartbeat_state)
        if force or (now_mono - heartbeat_last_emit_monotonic) >= float(heartbeat_interval_sec):
            print(
                "💓 [ui-full-e2e] "
                f"run_id={run_id} stage={heartbeat_state.get('stage')} "
                f"routes_done={heartbeat_state.get('routes_done', 0)} "
                f"interactions_done={heartbeat_state.get('interactions_done', 0)}"
            )
            heartbeat_last_emit_monotonic = now_mono

    previous_alarm_handler = None
    timer_armed = False
    if int(args.max_runtime_sec) > 0 and hasattr(signal, "SIGALRM") and hasattr(signal, "setitimer"):

        def _runtime_timeout_handler(_signum: int, _frame: Any) -> None:
            raise RuntimeBudgetExceeded(
                f"run_id={run_id} exceeded max runtime {int(args.max_runtime_sec)}s"
            )

        previous_alarm_handler = signal.getsignal(signal.SIGALRM)
        signal.signal(signal.SIGALRM, _runtime_timeout_handler)
        signal.setitimer(signal.ITIMER_REAL, float(int(args.max_runtime_sec)))
        timer_armed = True

    total_routes_planned = 0
    total_interactions = 0
    click_failures = 0
    gemini_warn_or_fail = 0
    routed_completed = 0

    try:
        update_heartbeat("starting", force=True)
        print(f"🚀 [ui-full-e2e] run_id={run_id}")
        if use_external_servers:
            print(f"🚀 [ui-full-e2e] using external servers api={base_api} dashboard={base_dashboard}")
        else:
            update_heartbeat("starting_local_services")
            print("🚀 [ui-full-e2e] starting orchestrator api")
            api_env = os.environ.copy()
            api_env["PYTHONPATH"] = "apps/orchestrator/src"
            api_env["OPENVIBECODING_API_AUTH_REQUIRED"] = str(
                os.environ.get("OPENVIBECODING_UI_FULL_E2E_API_AUTH_REQUIRED", "false")
            ).strip().lower()
            api_env["OPENVIBECODING_API_TOKEN"] = args.api_token
            api_env["OPENVIBECODING_DASHBOARD_PORT"] = str(resolved_dashboard_port)
            api_python = sys.executable or str(ROOT / ".venv" / "bin" / "python")
            api_proc = spawn_process(
                [
                    api_python,
                    "-m",
                    "openvibecoding_orch.cli",
                    "serve",
                    "--host",
                    args.host,
                    "--port",
                    str(resolved_api_port),
                ],
                paths["api_log"],
                env=api_env,
            )

            print("🚀 [ui-full-e2e] starting dashboard dev server")
            dashboard_env = os.environ.copy()
            dashboard_env["NEXT_PUBLIC_OPENVIBECODING_API_BASE"] = base_api
            dashboard_env["NEXT_PUBLIC_OPENVIBECODING_API_TOKEN"] = args.api_token
            dashboard_env["PORT"] = str(resolved_dashboard_port)
            dashboard_env["NEXT_DIST_DIR"] = f".next-e2e-{resolved_dashboard_port}"
            ui_proc = spawn_process(
                [
                    "npm",
                    "--prefix",
                    "apps/dashboard",
                    "run",
                    "dev",
                    "--",
                    "--hostname",
                    args.host,
                    "--port",
                    str(resolved_dashboard_port),
                ],
                paths["dashboard_log"],
                env=dashboard_env,
            )

        update_heartbeat("waiting_services")
        print("⏳ [ui-full-e2e] waiting for api/dashboard ready")
        wait_http_ok(f"{base_api}/health", 120)
        wait_http_ok(f"{base_dashboard}/pm", 180)

        update_heartbeat("seeding")
        print("🧪 [ui-full-e2e] seeding runtime data")
        dynamic_ids = _seed_ids(base_api, args.api_token, payload)
        payload["seed_ids"] = dynamic_ids

        routes_raw = discover_page_routes()
        resolved_routes: list[str] = []
        skipped_dynamic: list[str] = []
        for route in routes_raw:
            mapped = route_with_dynamic_ids(route, dynamic_ids)
            if mapped is None:
                skipped_dynamic.append(route)
                continue
            resolved_routes.append(mapped)
        if args.route_shard_total > 1:
            resolved_routes = [
                route for idx, route in enumerate(resolved_routes) if idx % args.route_shard_total == args.route_shard_index
            ]
        if args.max_pages > 0:
            resolved_routes = resolved_routes[: args.max_pages]
        total_routes_planned = len(resolved_routes)
        payload["skipped_dynamic_routes"] = skipped_dynamic
        update_heartbeat(
            "routes_ready",
            force=True,
            routes_total=total_routes_planned,
            routes_done=0,
            interactions_done=0,
            click_failures=0,
            gemini_warn_or_fail=0,
        )
        print(
            "🧩 [ui-full-e2e] route shard"
            f" {args.route_shard_index + 1}/{args.route_shard_total}, routes={len(resolved_routes)}"
        )

        analyzer: GeminiAnalyzer = GeminiAnalyzer(
            api_key=os.environ[args.gemini_key_env],
            model=provider_model,
            request_timeout_sec=max(1, int(args.gemini_request_timeout_sec)),
            max_attempts=max(1, int(args.gemini_max_attempts)),
            base_url=provider_base_url,
            thinking_level=thinking_level,
        )

        total_interactions, click_failures, gemini_warn_or_fail, routed_completed = execute_playwright_audit(
            resolved_routes=resolved_routes,
            base_dashboard=base_dashboard,
            page_dir=paths["page_dir"],
            interaction_dir=paths["interaction_dir"],
            payload=payload,
            analyzer=analyzer,
            update_heartbeat=update_heartbeat,
            args=args,
        )

        payload["finished_at"] = now_iso()
        payload["summary"] = {
            "total_routes": len(payload.get("routes", [])),
            "total_interactions": total_interactions,
            "interaction_click_failures": click_failures,
            "gemini_warn_or_fail": gemini_warn_or_fail,
            "mode": "headed_playwright_full_interaction",
        }
        click_inventory_payload = build_click_inventory_report(payload, source_report=str(paths["report_json"]))
        paths["click_inventory_report_json"].write_text(
            json.dumps(click_inventory_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        payload.setdefault("artifacts", {})
        payload["artifacts"]["click_inventory_report"] = str(paths["click_inventory_report_json"])
        _merge_click_inventory_summary(payload, click_inventory_payload)
        click_failures = int(payload.get("summary", {}).get("interaction_click_failures", 0) or 0)
        gemini_warn_or_fail = int(payload.get("summary", {}).get("gemini_warn_or_fail", 0) or 0)
        paths["report_json"].write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        paths["report_md"].write_text(build_markdown_report(payload), encoding="utf-8")
        update_heartbeat(
            "completed",
            force=True,
            routes_total=total_routes_planned,
            routes_done=routed_completed,
            interactions_done=total_interactions,
            click_failures=click_failures,
            gemini_warn_or_fail=gemini_warn_or_fail,
            report_json=str(paths["report_json"]),
            report_md=str(paths["report_md"]),
            click_inventory_report=str(paths["click_inventory_report_json"]),
            done=True,
        )

        print("✅ [ui-full-e2e] completed")
        print(f"📄 report_json={paths['report_json']}")
        print(f"📄 report_md={paths['report_md']}")
        print(f"📁 out_dir={paths['out_dir']}")
        return 0
    except RuntimeBudgetExceeded as exc:
        payload["errors"].append(f"runtime timeout: {exc}")
    except urllib.error.HTTPError as exc:
        payload["errors"].append(f"http error: {exc}")
    except Exception as exc:
        payload["errors"].append(str(exc))
    finally:
        kill_process(ui_proc)
        kill_process(api_proc)
        if timer_armed and hasattr(signal, "SIGALRM") and hasattr(signal, "setitimer"):
            signal.setitimer(signal.ITIMER_REAL, 0.0)
            if previous_alarm_handler is not None:
                signal.signal(signal.SIGALRM, previous_alarm_handler)

    payload["finished_at"] = now_iso()
    failure_snapshot = {
        "captured_at": now_iso(),
        "run_id": run_id,
        "errors": list(payload.get("errors", [])),
        "heartbeat": heartbeat_state,
        "report_json": str(paths["report_json"]),
        "report_md": str(paths["report_md"]),
    }
    write_json_atomic(paths["failure_snapshot_json"], failure_snapshot)
    update_heartbeat(
        "failed",
        force=True,
        routes_total=total_routes_planned,
        routes_done=routed_completed,
        interactions_done=total_interactions,
        click_failures=click_failures,
        gemini_warn_or_fail=gemini_warn_or_fail,
        done=False,
        failure_snapshot=str(paths["failure_snapshot_json"]),
    )
    try:
        click_inventory_payload = build_click_inventory_report(payload, source_report=str(paths["report_json"]))
        paths["click_inventory_report_json"].write_text(
            json.dumps(click_inventory_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        payload.setdefault("artifacts", {})
        payload["artifacts"]["click_inventory_report"] = str(paths["click_inventory_report_json"])
        _merge_click_inventory_summary(payload, click_inventory_payload)
    except Exception as exc:  # noqa: BLE001
        payload.setdefault("errors", []).append(f"click inventory write failed: {exc}")
    paths["report_json"].write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    paths["report_md"].write_text(build_markdown_report(payload), encoding="utf-8")
    print(f"❌ [ui-full-e2e] failed, see {paths['report_json']}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
