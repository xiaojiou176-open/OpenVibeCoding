#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.request
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.host_process_safety import terminate_tracked_child
from scripts.ui_full_e2e_gemini_audit import _prime_llm_keys
from scripts.ui_full_e2e_gemini_audit_runtime import discover_page_routes

ROOT = Path(__file__).resolve().parents[2]
AUDIT_SCRIPT = ROOT / "scripts" / "ui_full_e2e_gemini_audit.py"
REPORT_ROOT = ROOT / ".runtime-cache" / "test_output" / "ui_full_gemini_audit"
PARALLEL_OUT_ROOT = ROOT / ".runtime-cache" / "test_output" / "ui_full_gemini_audit_parallel"
PORT_STRIDE = 20


def _sanitize_label(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(value or "").strip())
    return normalized.strip("_") or "run"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    items = sorted(float(v) for v in values)
    if len(items) == 1:
        return round(items[0], 3)
    position = (len(items) - 1) * max(0.0, min(1.0, float(q)))
    low = int(position)
    high = min(low + 1, len(items) - 1)
    weight = position - low
    return round(items[low] * (1.0 - weight) + items[high] * weight, 3)


def _duration_summary(values: list[float]) -> dict[str, Any]:
    cleaned = [max(0.0, float(v)) for v in values]
    if not cleaned:
        return {
            "count": 0,
            "sum_sec": 0.0,
            "min_sec": 0.0,
            "max_sec": 0.0,
            "avg_sec": 0.0,
            "p50_sec": 0.0,
            "p95_sec": 0.0,
        }
    total = sum(cleaned)
    return {
        "count": len(cleaned),
        "sum_sec": round(total, 3),
        "min_sec": round(min(cleaned), 3),
        "max_sec": round(max(cleaned), 3),
        "avg_sec": round(total / len(cleaned), 3),
        "p50_sec": _percentile(cleaned, 0.5),
        "p95_sec": _percentile(cleaned, 0.95),
    }


def _shard_strict_ok(stats: Any, *, require_gemini_clean: bool) -> bool:
    if not isinstance(stats, dict):
        return False
    base_ok = (
        _to_int(stats.get("route_count"), 0) > 0
        and _to_int(stats.get("reported_total_routes"), 0) == _to_int(stats.get("route_count"), 0)
        and _to_int(stats.get("total_interactions"), 0) > 0
        and _to_int(stats.get("interaction_entry_count"), 0) > 0
        and _to_int(stats.get("total_interactions"), 0) == _to_int(stats.get("interaction_entry_count"), 0)
        and _to_int(stats.get("click_failures"), 0) == 0
        and _to_int(stats.get("click_failures"), 0) == _to_int(stats.get("derived_click_failures"), 0)
        and _to_int(stats.get("summary_warn_or_fail"), 0) == _to_int(stats.get("derived_warn_or_fail"), 0)
        and _to_int(stats.get("navigation_failures"), 0) == 0
        and _to_int(stats.get("missing_page_analysis_count"), 0) == 0
        and _to_int(stats.get("missing_interaction_analysis_count"), 0) == 0
        and _to_int(stats.get("click_inventory_consistency_error_count"), 0) == 0
        and _to_int(stats.get("summary_consistency_error_count"), 0) == 0
        and _to_int(stats.get("reported_click_inventory_entries"), 0) > 0
        and _to_int(stats.get("reported_click_inventory_blocking_failures"), 0) == 0
        and _to_int(stats.get("reported_click_inventory_missing_target_refs"), 0) == 0
        and _to_int(stats.get("reported_click_inventory_overall_passed_false_count"), 0) == 0
    )
    if not base_ok:
        return False
    if not require_gemini_clean:
        return True
    return (
        _to_int(stats.get("blocking_route_error_count"), 0) == 0
        and _to_int(stats.get("gemini_skipped_count"), 0) == 0
        and _to_int(stats.get("page_warn"), 0) == 0
        and _to_int(stats.get("page_fail"), 0) == 0
        and _to_int(stats.get("inter_warn"), 0) == 0
        and _to_int(stats.get("inter_fail"), 0) == 0
    )


def _build_timing_summary(shard_results: list[dict[str, Any]], *, require_gemini_clean: bool) -> dict[str, Any]:
    shard_durations = [max(0.0, _to_float(item.get("duration_sec"), 0.0)) for item in shard_results]
    shard_success = sum(1 for item in shard_results if _to_int(item.get("exit_code"), 1) == 0)
    report_success = sum(1 for item in shard_results if bool(item.get("report_exists", False)))
    strict_success = sum(
        1 for item in shard_results if _shard_strict_ok(item.get("strict_stats"), require_gemini_clean=require_gemini_clean)
    )
    details = [
        {
            "index": _to_int(item.get("index"), 0),
            "run_id": str(item.get("run_id") or ""),
            "duration_sec": round(max(0.0, _to_float(item.get("duration_sec"), 0.0)), 3),
            "exit_code": _to_int(item.get("exit_code"), 1),
            "report_exists": bool(item.get("report_exists", False)),
            "strict_ok": _shard_strict_ok(item.get("strict_stats"), require_gemini_clean=require_gemini_clean),
        }
        for item in shard_results
    ]
    details.sort(key=lambda x: x["index"])
    return {
        "shard_duration_sec": _duration_summary(shard_durations),
        "shard_success_count": shard_success,
        "shard_fail_count": max(0, len(shard_results) - shard_success),
        "report_success_count": report_success,
        "report_fail_count": max(0, len(shard_results) - report_success),
        "strict_success_count": strict_success,
        "strict_fail_count": max(0, len(shard_results) - strict_success),
        "shard_durations": details,
    }


def _count_verdict(value: Any, pass_count: int, warn_count: int, fail_count: int) -> tuple[int, int, int]:
    verdict = str((value or {}).get("verdict", "")).strip().lower()
    if verdict == "pass":
        return pass_count + 1, warn_count, fail_count
    if verdict == "warn":
        return pass_count, warn_count + 1, fail_count
    if verdict == "fail":
        return pass_count, warn_count, fail_count + 1
    return pass_count, warn_count, fail_count


def _text_indicates_recovered(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return False
    if re.search(r"\b(?:retry[_ ]succeeded|recovered)\b(?:\s*(?:=|:)\s*|\s+)(?:false|0|no)\b", normalized):
        return False
    negative_markers = (
        "not recovered",
        "still not recovered",
        "unrecovered",
        "failed to recover",
        "recovery failed",
        "retry failed",
        "unable to recover",
    )
    if any(marker in normalized for marker in negative_markers):
        return False
    positive_markers = (
        "retry recovered",
        "retry_recovered",
        "retry succeeded",
        "retry_succeeded",
        "recovered after retry",
        "recovered on retry",
        "recovered via retry",
    )
    return any(marker in normalized for marker in positive_markers)


def _is_recovered_route_error(message: Any) -> bool:
    if isinstance(message, dict):
        recovered = message.get("recovered")
        if isinstance(recovered, bool):
            return recovered
        structured_states = [
            str(message.get("status") or "").strip().lower(),
            str(message.get("code") or "").strip().lower(),
            str(message.get("phase") or "").strip().lower(),
        ]
        if any(state in {"recovered", "retry_succeeded", "retry_recovered"} for state in structured_states):
            return True
        if any(state in {"failed", "error", "retry_failed"} for state in structured_states):
            return False
        detail_text = " ".join(
            str(message.get(key) or "").strip().lower()
            for key in ("message", "error", "detail")
        )
        return _text_indicates_recovered(detail_text)

    return _text_indicates_recovered(str(message or ""))


def _target_label(target: Any) -> str:
    if not isinstance(target, dict):
        return "unknown"
    return (
        str(target.get("text") or "").strip()
        or str(target.get("aria_label") or "").strip()
        or str(target.get("data_testid") or "").strip()
        or str(target.get("id_attr") or "").strip()
        or str(target.get("tag") or "").strip()
        or "unknown"
    )


def _target_ref(target: Any, *, route: str = "", interaction_index: int = 0) -> str:
    if not isinstance(target, dict):
        return ""
    selector = str(target.get("selector") or "").strip()
    if selector:
        return selector
    id_attr = str(target.get("id_attr") or "").strip()
    if id_attr:
        return f"#{id_attr}"
    data_testid = str(target.get("data_testid") or "").strip()
    if data_testid:
        return f"[data-testid={data_testid}]"
    instance_id = str(target.get("instance_id") or "").strip()
    if instance_id:
        return instance_id
    href = str(target.get("href") or "").strip()
    if href:
        return f"href:{href}"
    name_attr = str(target.get("name_attr") or "").strip()
    if name_attr:
        return f"name:{name_attr}"
    aria_label = str(target.get("aria_label") or "").strip()
    if aria_label:
        return f"aria:{aria_label}"
    text = str(target.get("text") or "").strip()
    if text:
        return f"text:{text}"
    return ""


def _collect_stats(payload: dict[str, Any], *, report_path: Path | None = None) -> dict[str, Any]:
    route_count = 0
    page_pass = page_warn = page_fail = 0
    inter_pass = inter_warn = inter_fail = 0
    interaction_entry_count = 0
    derived_click_failures = 0
    derived_warn_or_fail = 0
    derived_click_inventory_entries = 0
    derived_click_inventory_blocking_failures = 0
    derived_click_inventory_missing_target_refs = 0
    route_error_count = 0
    blocking_route_error_count = 0
    recovered_route_error_count = 0
    navigation_failures = 0
    missing_page_analysis_count = 0
    missing_page_analysis_routes: list[str] = []
    missing_interaction_analysis_count = 0
    missing_interaction_analysis_entries: list[dict[str, Any]] = []
    gemini_skipped_count = 0

    routes = payload.get("routes", []) or []
    if isinstance(routes, list):
        for route in routes:
            if not isinstance(route, dict):
                continue
            route_count += 1
            route_path = str(route.get("route") or "")
            route_errors = route.get("errors", []) or []
            if isinstance(route_errors, list):
                route_error_count += len(route_errors)
                for err in route_errors:
                    err_text = str(err).lower()
                    if _is_recovered_route_error(err):
                        recovered_route_error_count += 1
                        continue
                    blocking_route_error_count += 1
                    if "navigate failed" in err_text:
                        navigation_failures += 1
            page_analysis = route.get("page_analysis")
            if not isinstance(page_analysis, dict) or not str(page_analysis.get("verdict", "")).strip():
                missing_page_analysis_count += 1
                missing_page_analysis_routes.append(route_path)
            if (
                isinstance(page_analysis, dict)
                and str(page_analysis.get("_degrade_reason", "")).strip().lower() == "gemini_skipped"
            ):
                gemini_skipped_count += 1
            page_verdict = str((page_analysis or {}).get("verdict", "")).strip().lower()
            if page_verdict in {"warn", "fail"}:
                derived_warn_or_fail += 1
            page_pass, page_warn, page_fail = _count_verdict(
                page_analysis,
                page_pass,
                page_warn,
                page_fail,
            )
            interactions = route.get("interactions", []) or []
            if not isinstance(interactions, list):
                continue
            for interaction in interactions:
                if not isinstance(interaction, dict):
                    continue
                interaction_index = _to_int(interaction.get("index"), 0)
                interaction_entry_count += 1
                derived_click_inventory_entries += 1
                analysis = interaction.get("analysis")
                if not isinstance(analysis, dict) or not str(analysis.get("verdict", "")).strip():
                    missing_interaction_analysis_count += 1
                    missing_interaction_analysis_entries.append(
                        {
                            "route": route_path,
                            "interaction_index": interaction_index,
                            "target_label": _target_label(interaction.get("target")),
                        }
                    )
                if isinstance(analysis, dict) and str(analysis.get("_degrade_reason", "")).strip().lower() == "gemini_skipped":
                    gemini_skipped_count += 1
                inter_verdict = str((analysis or {}).get("verdict", "")).strip().lower()
                if inter_verdict in {"warn", "fail"}:
                    derived_warn_or_fail += 1
                inter_pass, inter_warn, inter_fail = _count_verdict(
                    analysis,
                    inter_pass,
                    inter_warn,
                    inter_fail,
                )
                click_ok = interaction.get("click_ok") is True
                if not click_ok:
                    derived_click_failures += 1
                    derived_click_inventory_blocking_failures += 1
                if not _target_ref(
                    interaction.get("target"),
                    route=route_path,
                    interaction_index=interaction_index,
                ):
                    derived_click_inventory_missing_target_refs += 1

    summary = payload.get("summary") or {}
    click_inventory_summary = payload.get("click_inventory_summary") or {}
    reported_total_routes = _to_int(summary.get("total_routes", 0), 0)
    click_failures = _to_int(summary.get("interaction_click_failures", 0), 0)
    total_interactions = _to_int(summary.get("total_interactions", 0), 0)
    summary_warn_or_fail = _to_int(summary.get("gemini_warn_or_fail", 0), 0)
    reported_click_inventory_entries = _to_int(
        summary.get("click_inventory_entries", click_inventory_summary.get("total_entries", 0)),
        0,
    )
    reported_click_inventory_blocking_failures = _to_int(
        summary.get(
            "click_inventory_blocking_failures",
            click_inventory_summary.get("blocking_failures", 0),
        ),
        0,
    )
    reported_click_inventory_missing_target_refs = _to_int(
        summary.get(
            "click_inventory_missing_target_refs",
            click_inventory_summary.get("missing_target_ref_count", 0),
        ),
        0,
    )
    reported_click_inventory_overall_passed = bool(
        summary.get("click_inventory_overall_passed", click_inventory_summary.get("overall_passed", False))
    )
    if reported_click_inventory_entries <= 0:
        reported_click_inventory_overall_passed = True
    reported_click_inventory_overall_passed_false_count = 0 if reported_click_inventory_overall_passed else 1

    click_inventory_report_path = ""
    click_inventory_report_exists = False
    click_inventory_report_entries = 0
    click_inventory_report_blocking_failures = 0
    click_inventory_report_missing_target_refs = 0
    click_inventory_report_overall_passed = False
    artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), dict) else {}
    raw_click_inventory_path = str((artifacts or {}).get("click_inventory_report") or "").strip()
    if raw_click_inventory_path:
        candidate = Path(raw_click_inventory_path).expanduser()
        if not candidate.is_absolute() and report_path is not None:
            candidate = (report_path.parent / candidate).resolve()
        else:
            candidate = candidate.resolve()
        click_inventory_report_path = str(candidate)
        if candidate.exists():
            click_inventory_report_exists = True
            try:
                click_inventory_payload = json.loads(candidate.read_text(encoding="utf-8"))
                if isinstance(click_inventory_payload, dict):
                    report_summary = click_inventory_payload.get("summary") or {}
                    click_inventory_report_entries = _to_int(report_summary.get("total_entries", 0), 0)
                    click_inventory_report_blocking_failures = _to_int(
                        report_summary.get("blocking_failures", 0),
                        0,
                    )
                    click_inventory_report_missing_target_refs = _to_int(
                        report_summary.get("missing_target_ref_count", 0),
                        0,
                    )
                    click_inventory_report_overall_passed = bool(report_summary.get("overall_passed", False))
                    if click_inventory_report_entries <= 0:
                        click_inventory_report_overall_passed = True
            except Exception:
                click_inventory_report_exists = False

    click_inventory_consistency_error_count = 0
    if reported_click_inventory_entries > 0 and reported_click_inventory_entries != derived_click_inventory_entries:
        click_inventory_consistency_error_count += 1
    if reported_click_inventory_blocking_failures != derived_click_inventory_blocking_failures:
        click_inventory_consistency_error_count += 1
    if reported_click_inventory_missing_target_refs != derived_click_inventory_missing_target_refs:
        click_inventory_consistency_error_count += 1
    if reported_click_inventory_entries > 0 and not reported_click_inventory_overall_passed:
        click_inventory_consistency_error_count += 1
    if not click_inventory_report_path:
        click_inventory_consistency_error_count += 1
    if not click_inventory_report_exists:
        click_inventory_consistency_error_count += 1
    else:
        if click_inventory_report_entries != reported_click_inventory_entries:
            click_inventory_consistency_error_count += 1
        if click_inventory_report_blocking_failures != reported_click_inventory_blocking_failures:
            click_inventory_consistency_error_count += 1
        if click_inventory_report_missing_target_refs != reported_click_inventory_missing_target_refs:
            click_inventory_consistency_error_count += 1
        if click_inventory_report_overall_passed != reported_click_inventory_overall_passed:
            click_inventory_consistency_error_count += 1

    summary_consistency_error_count = 0
    if reported_total_routes != route_count:
        summary_consistency_error_count += 1
    if total_interactions != interaction_entry_count:
        summary_consistency_error_count += 1
    if click_failures != derived_click_failures:
        summary_consistency_error_count += 1
    if summary_warn_or_fail != derived_warn_or_fail:
        summary_consistency_error_count += 1

    return {
        "route_count": route_count,
        "reported_total_routes": reported_total_routes,
        "page_pass": page_pass,
        "page_warn": page_warn,
        "page_fail": page_fail,
        "inter_pass": inter_pass,
        "inter_warn": inter_warn,
        "inter_fail": inter_fail,
        "total_interactions": total_interactions,
        "interaction_entry_count": interaction_entry_count,
        "click_failures": click_failures,
        "derived_click_failures": derived_click_failures,
        "summary_warn_or_fail": summary_warn_or_fail,
        "derived_warn_or_fail": derived_warn_or_fail,
        "reported_click_inventory_entries": reported_click_inventory_entries,
        "reported_click_inventory_blocking_failures": reported_click_inventory_blocking_failures,
        "reported_click_inventory_missing_target_refs": reported_click_inventory_missing_target_refs,
        "reported_click_inventory_overall_passed_false_count": reported_click_inventory_overall_passed_false_count,
        "derived_click_inventory_entries": derived_click_inventory_entries,
        "derived_click_inventory_blocking_failures": derived_click_inventory_blocking_failures,
        "derived_click_inventory_missing_target_refs": derived_click_inventory_missing_target_refs,
        "click_inventory_report_exists_count": 1 if click_inventory_report_exists else 0,
        "click_inventory_report_missing_count": 0 if click_inventory_report_exists else 1,
        "click_inventory_report_entries": click_inventory_report_entries,
        "click_inventory_report_blocking_failures": click_inventory_report_blocking_failures,
        "click_inventory_report_missing_target_refs": click_inventory_report_missing_target_refs,
        "click_inventory_report_overall_passed_false_count": 0 if click_inventory_report_overall_passed else 1,
        "click_inventory_consistency_error_count": click_inventory_consistency_error_count,
        "summary_consistency_error_count": summary_consistency_error_count,
        "route_error_count": route_error_count,
        "blocking_route_error_count": blocking_route_error_count,
        "recovered_route_error_count": recovered_route_error_count,
        "navigation_failures": navigation_failures,
        "missing_page_analysis_count": missing_page_analysis_count,
        "missing_page_analysis_routes": sorted(set(missing_page_analysis_routes)),
        "missing_interaction_analysis_count": missing_interaction_analysis_count,
        "missing_interaction_analysis_entries": missing_interaction_analysis_entries,
        "gemini_skipped_count": gemini_skipped_count,
    }


def _resolve_python() -> str:
    venv_python = ROOT / ".venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def _http_ok(url: str, timeout_sec: int = 3, *, auth: bool = False) -> bool:
    try:
        req = urllib.request.Request(url, method="GET")
        if auth:
            api_token = (
                os.environ.get("CORTEXPILOT_API_TOKEN", "").strip()
                or os.environ.get("CORTEXPILOT_E2E_API_TOKEN", "").strip()
                or "cortexpilot-e2e-token"
            )
            if api_token:
                req.add_header("Authorization", f"Bearer {api_token}")
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            return 200 <= int(resp.status) < 500
    except Exception:
        return False


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(payload, ensure_ascii=True) + "\n")


def _read_json_object(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
    except Exception:
        return None
    return None


def _read_log_tail(path: Path, max_lines: int) -> list[str]:
    limit = max(1, int(max_lines))
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        if len(lines) <= limit:
            return lines
        return lines[-limit:]
    except Exception:
        return []


def _close_log_fp(item: dict[str, Any]) -> None:
    fp = item.get("log_fp")
    if fp is None:
        return
    try:
        fp.flush()
    except Exception:
        pass
    try:
        fp.close()
    except Exception:
        pass


def _terminate_proc(proc: subprocess.Popen[str], graceful_timeout_sec: int = 5) -> str:
    return terminate_tracked_child(
        proc,
        term_timeout_sec=max(1, int(graceful_timeout_sec)),
        kill_timeout_sec=3,
    )


def _write_failure_snapshot(
    *,
    run_dir: Path,
    item: dict[str, Any],
    reason: str,
    tail_lines: int,
) -> Path:
    log_path = Path(str(item.get("log_path", "")))
    report_path = Path(str(item.get("report_path", "")))
    shard_heartbeat_path = REPORT_ROOT / str(item.get("run_id", "")) / "heartbeat.json"
    shard_failure_snapshot_path = REPORT_ROOT / str(item.get("run_id", "")) / "failure_snapshot.json"
    now_monotonic = time.monotonic()
    elapsed_sec = max(0.0, now_monotonic - float(item.get("started_monotonic", now_monotonic)))
    snapshot = {
        "captured_at": _now_iso(),
        "reason": str(reason),
        "index": item.get("index"),
        "run_id": item.get("run_id"),
        "pid": item.get("pid"),
        "started_at": item.get("started_at"),
        "elapsed_sec": round(elapsed_sec, 3),
        "cmd": item.get("cmd"),
        "log_path": str(log_path),
        "log_exists": log_path.exists(),
        "log_size_bytes": int(log_path.stat().st_size) if log_path.exists() else 0,
        "log_tail": _read_log_tail(log_path, max_lines=tail_lines),
        "report_path": str(report_path),
        "report_exists": report_path.exists(),
        "shard_heartbeat_path": str(shard_heartbeat_path),
        "shard_heartbeat": _read_json_object(shard_heartbeat_path),
        "shard_failure_snapshot_path": str(shard_failure_snapshot_path),
        "shard_failure_snapshot": _read_json_object(shard_failure_snapshot_path),
    }
    snapshot_path = run_dir / f"shard_{item.get('index')}.failure_snapshot.json"
    snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return snapshot_path


def _spawn_shard(
    *,
    python_bin: str,
    execution_index: int,
    route_shard_total: int,
    route_shard_index: int,
    route_path: str,
    model: str,
    gemini_key_env: str,
    host: str,
    api_port: int,
    dashboard_port: int,
    parent_run_id: str,
    run_dir: Path,
    audit_max_runtime_sec: int = 0,
    audit_heartbeat_interval_sec: int = 20,
    external_api_base: str = "",
    external_dashboard_base: str = "",
    headed: bool = False,
    max_pages: int = 0,
    max_buttons_per_page: int = 120,
    max_interactions: int = 0,
    max_duplicate_targets: int = 3,
) -> dict[str, Any]:
    shard_run_id = f"{parent_run_id}_task_{execution_index}"
    shard_log = run_dir / f"task_{execution_index}.log"
    shard_report = REPORT_ROOT / shard_run_id / "report.json"
    cmd = [
        python_bin,
        str(AUDIT_SCRIPT),
        "--route-shard-total",
        str(route_shard_total),
        "--route-shard-index",
        str(route_shard_index),
        "--gemini-model",
        model,
        "--gemini-key-env",
        gemini_key_env,
        "--host",
        host,
        "--run-id",
        shard_run_id,
        "--max-pages",
        str(max(0, int(max_pages))),
        "--max-buttons-per-page",
        str(max(1, int(max_buttons_per_page))),
        "--max-interactions",
        str(max(0, int(max_interactions))),
        "--max-duplicate-targets",
        str(max(1, int(max_duplicate_targets))),
    ]
    if int(audit_max_runtime_sec) > 0:
        cmd.extend(["--max-runtime-sec", str(int(audit_max_runtime_sec))])
    if int(audit_heartbeat_interval_sec) > 0:
        cmd.extend(["--heartbeat-interval-sec", str(int(audit_heartbeat_interval_sec))])
    if headed:
        cmd.append("--headed")
    if external_api_base and external_dashboard_base:
        cmd.extend(
            [
                "--external-api-base",
                external_api_base,
                "--external-dashboard-base",
                external_dashboard_base,
            ]
        )
    else:
        cmd.extend(
            [
                "--api-port",
                str(api_port),
                "--dashboard-port",
                str(dashboard_port),
            ]
        )
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    log_fp = shard_log.open("w", encoding="utf-8", buffering=1)
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        env=env,
        stdout=log_fp,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return {
        "index": execution_index,
        "run_id": shard_run_id,
        "route_catalog_index": int(route_shard_index),
        "route_catalog_route": str(route_path),
        "api_port": api_port,
        "dashboard_port": dashboard_port,
        "report_path": str(shard_report),
        "log_path": str(shard_log),
        "cmd": cmd,
        "started_at": _now_iso(),
        "started_monotonic": time.monotonic(),
        "process": proc,
        "pid": proc.pid,
        "log_fp": log_fp,
    }


def _terminate_shards(shards: list[dict[str, Any]]) -> None:
    for item in shards:
        proc = item.get("process")
        if not isinstance(proc, subprocess.Popen):
            continue
        if proc.poll() is not None:
            continue
        _terminate_proc(proc)
        item["finished_at"] = _now_iso()
        item["finished_monotonic"] = time.monotonic()
        item["exit_code"] = int(proc.poll() if proc.poll() is not None else 130)
        _close_log_fp(item)


def _resolve_fail_reasons(
    *,
    failed_shards: list[int],
    report_errors: list[dict[str, Any]],
    strict_metrics: dict[str, Any],
    strict_ok: bool,
    require_gemini_clean: bool,
) -> list[str]:
    reasons: list[str] = []
    if failed_shards:
        reasons.append("shard_exit_non_zero")
    if report_errors:
        reasons.append("shard_report_error")
    if not strict_ok:
        reasons.append("strict_gate_failed")
        if require_gemini_clean and _to_int(strict_metrics.get("page_warn"), 0) > 0:
            reasons.append("strict_page_warn_non_zero")
        if require_gemini_clean and _to_int(strict_metrics.get("page_fail"), 0) > 0:
            reasons.append("strict_page_fail_non_zero")
        if require_gemini_clean and _to_int(strict_metrics.get("inter_warn"), 0) > 0:
            reasons.append("strict_inter_warn_non_zero")
        if require_gemini_clean and _to_int(strict_metrics.get("inter_fail"), 0) > 0:
            reasons.append("strict_inter_fail_non_zero")
        if _to_int(strict_metrics.get("click_failures"), 0) > 0:
            reasons.append("strict_click_failures_non_zero")
        if _to_int(strict_metrics.get("reported_click_inventory_blocking_failures"), 0) > 0:
            reasons.append("strict_click_inventory_blocking_failures_non_zero")
        if _to_int(strict_metrics.get("reported_click_inventory_missing_target_refs"), 0) > 0:
            reasons.append("strict_click_inventory_missing_target_refs_non_zero")
        if _to_int(strict_metrics.get("reported_click_inventory_overall_passed_false_count"), 0) > 0:
            reasons.append("strict_click_inventory_overall_passed_false")
        if _to_int(strict_metrics.get("click_inventory_consistency_error_count"), 0) > 0:
            reasons.append("strict_click_inventory_consistency_error_non_zero")
        if _to_int(strict_metrics.get("summary_consistency_error_count"), 0) > 0:
            reasons.append("strict_summary_consistency_error_non_zero")
        if _to_int(strict_metrics.get("reported_total_routes"), 0) != _to_int(strict_metrics.get("route_count"), 0):
            reasons.append("strict_total_routes_mismatch")
        if _to_int(strict_metrics.get("total_interactions"), 0) != _to_int(
            strict_metrics.get("interaction_entry_count"),
            0,
        ):
            reasons.append("strict_total_interactions_mismatch")
        if require_gemini_clean and _to_int(strict_metrics.get("blocking_route_error_count"), 0) > 0:
            reasons.append("strict_blocking_route_error_count_non_zero")
        if _to_int(strict_metrics.get("navigation_failures"), 0) > 0:
            reasons.append("strict_navigation_failures_non_zero")
        if _to_int(strict_metrics.get("missing_page_analysis_count"), 0) > 0:
            reasons.append("strict_missing_page_analysis_non_zero")
        if _to_int(strict_metrics.get("missing_interaction_analysis_count"), 0) > 0:
            reasons.append("strict_missing_interaction_analysis_non_zero")
        if require_gemini_clean and _to_int(strict_metrics.get("gemini_skipped_count"), 0) > 0:
            reasons.append("strict_gemini_skipped_non_zero")
        if _to_int(strict_metrics.get("route_count"), 0) <= 0:
            reasons.append("strict_route_count_zero")
        if _to_int(strict_metrics.get("total_interactions"), 0) <= 0:
            reasons.append("strict_total_interactions_zero")
    if not reasons:
        reasons.append("passed")
    deduped: list[str] = []
    for reason in reasons:
        if reason not in deduped:
            deduped.append(reason)
    return deduped


def _parse_ab_profiles(raw: str) -> list[dict[str, str]]:
    specs: list[dict[str, str]] = []
    for chunk in (raw or "").split(";"):
        block = chunk.strip()
        if not block:
            continue
        item: dict[str, str] = {}
        for pair in block.split(","):
            token = pair.strip()
            if not token or "=" not in token:
                continue
            key, value = token.split("=", 1)
            item[key.strip().lower()] = value.strip()
        if item:
            specs.append(item)
    return specs


def _build_default_ab_profiles(args: argparse.Namespace) -> list[dict[str, Any]]:
    b_shards = max(1, int(args.shards) + 1)
    b_max_interactions = int(args.max_interactions) * 2 if int(args.max_interactions) > 0 else 0
    b_max_runtime = int(args.audit_max_runtime_sec) * 2 if int(args.audit_max_runtime_sec) > 0 else 0
    return [
        {
            "label": f"{args.run_label}_A",
            "profile": f"{args.run_profile}_A",
            "shards": int(args.shards),
            "max_pages": int(args.max_pages),
            "max_interactions": int(args.max_interactions),
            "max_buttons_per_page": int(args.max_buttons_per_page),
            "max_duplicate_targets": int(args.max_duplicate_targets),
            "audit_max_runtime_sec": int(args.audit_max_runtime_sec),
            "shard_timeout_sec": int(args.shard_timeout_sec),
        },
        {
            "label": f"{args.run_label}_B",
            "profile": f"{args.run_profile}_B",
            "shards": b_shards,
            "max_pages": int(args.max_pages),
            "max_interactions": b_max_interactions,
            "max_buttons_per_page": int(args.max_buttons_per_page),
            "max_duplicate_targets": int(args.max_duplicate_targets),
            "audit_max_runtime_sec": b_max_runtime,
            "shard_timeout_sec": int(args.shard_timeout_sec),
        },
    ]


def _build_ab_profiles_from_args(args: argparse.Namespace) -> list[dict[str, Any]]:
    parsed = _parse_ab_profiles(str(args.ab_profiles or ""))
    if not parsed:
        return _build_default_ab_profiles(args)
    profiles: list[dict[str, Any]] = []
    for idx, item in enumerate(parsed):
        label = item.get("label") or item.get("run_label") or f"{args.run_label}_P{idx + 1}"
        profile = (
            item.get("profile")
            or item.get("run_profile")
            or item.get("budget_profile")
            or f"{args.run_profile}_P{idx + 1}"
        )
        profiles.append(
            {
                "label": str(label),
                "profile": str(profile),
                "shards": _to_int(item.get("shards"), int(args.shards)),
                "max_pages": _to_int(item.get("max_pages"), int(args.max_pages)),
                "max_interactions": _to_int(item.get("max_interactions"), int(args.max_interactions)),
                "max_buttons_per_page": _to_int(item.get("max_buttons_per_page"), int(args.max_buttons_per_page)),
                "max_duplicate_targets": _to_int(item.get("max_duplicate_targets"), int(args.max_duplicate_targets)),
                "audit_max_runtime_sec": _to_int(
                    item.get("audit_max_runtime_sec", item.get("max_runtime_sec")),
                    int(args.audit_max_runtime_sec),
                ),
                "shard_timeout_sec": _to_int(item.get("shard_timeout_sec"), int(args.shard_timeout_sec)),
            }
        )
    return profiles


def _normalize_route(route: str) -> str:
    raw = str(route or "").strip()
    if not raw:
        return ""
    if not raw.startswith("/"):
        raw = "/" + raw
    if raw != "/" and raw.endswith("/"):
        raw = raw.rstrip("/")
    return raw


def _builtin_route_score(route: str) -> tuple[int, str]:
    score = 10
    tier = "low"
    normalized = _normalize_route(route).lower()
    if normalized in {"/", "/pm", "/command-tower"}:
        return 120, "high"
    if normalized.startswith("/command-tower/sessions"):
        return 115, "high"
    if "god-mode" in normalized or "diff" in normalized:
        return 110, "high"
    if "command-tower" in normalized or normalized.startswith("/pm"):
        return 95, "high"
    if "run" in normalized or "workflow" in normalized:
        score = 70
        tier = "medium"
    elif "dashboard" in normalized or "settings" in normalized:
        score = 55
        tier = "medium"
    return score, tier


def _tier_rank(value: str) -> int:
    normalized = str(value or "").strip().lower()
    if normalized == "high":
        return 0
    if normalized == "medium":
        return 1
    return 2


def _resolve_priority_entry(value: Any, default_score: int, default_tier: str) -> tuple[int, str]:
    if isinstance(value, (int, float)):
        score = max(0, int(value))
        tier = "high" if score >= 100 else ("medium" if score >= 50 else "low")
        return score, tier
    if not isinstance(value, dict):
        return default_score, default_tier
    tier = str(value.get("tier") or value.get("risk") or default_tier).strip().lower()
    if tier not in {"high", "medium", "low"}:
        tier = default_tier
    raw_score = value.get("score", value.get("weight", default_score))
    score = _to_int(raw_score, default_score)
    score = max(0, score)
    return score, tier


def _profiles_match(value: Any, profile: str) -> bool:
    target = str(profile or "").strip().lower()
    if not target:
        return True
    if isinstance(value, str):
        token = value.strip().lower()
        return (not token) or token == target or token == "all"
    if isinstance(value, list):
        for item in value:
            token = str(item or "").strip().lower()
            if token in {"", "all", target}:
                return True
    return False


def _load_route_priority_file(path_value: str, profile: str) -> tuple[dict[str, dict[str, Any]], str]:
    path_text = str(path_value or "").strip()
    if not path_text:
        return {}, ""
    raw_path = Path(path_text).expanduser()
    resolved_path = raw_path if raw_path.is_absolute() else (ROOT / raw_path).resolve()
    if not resolved_path.exists():
        raise FileNotFoundError(f"route priority file not found: {resolved_path}")
    payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    overrides: dict[str, dict[str, Any]] = {}

    def put_route(route_key: str, value: Any) -> None:
        route = _normalize_route(route_key)
        if not route:
            return
        if isinstance(value, dict):
            profile_value = value.get("profile", value.get("profiles"))
            if profile_value is not None and not _profiles_match(profile_value, profile):
                return
        score, tier = _resolve_priority_entry(value, default_score=0, default_tier="low")
        overrides[route] = {"score": score, "tier": tier, "source": "file"}

    if isinstance(payload, dict):
        routes_map = payload.get("routes")
        if isinstance(routes_map, dict):
            for route_key, value in routes_map.items():
                put_route(str(route_key), value)
        else:
            for route_key, value in payload.items():
                if route_key in {"routes", "profiles"}:
                    continue
                put_route(str(route_key), value)
    elif isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            route = str(item.get("route") or "").strip()
            if not route:
                continue
            if not _profiles_match(item.get("profile", item.get("profiles")), profile):
                continue
            put_route(route, item)
    else:
        raise ValueError("route priority file must be a JSON object or JSON array")
    return overrides, str(resolved_path)


def _pick_counts(total: int, profile: str) -> tuple[int, int, int]:
    if total <= 0:
        return 0, 0, 0
    normalized_profile = str(profile or "").strip().lower()
    high_ratio = 0.7 if normalized_profile.startswith("pr") else 0.5
    medium_ratio = 0.25 if normalized_profile.startswith("pr") else 0.3
    high = int(total * high_ratio)
    medium = int(total * medium_ratio)
    low = max(0, total - high - medium)
    if high <= 0:
        high = 1
    assigned = high + medium + low
    if assigned > total:
        overflow = assigned - total
        low = max(0, low - overflow)
    elif assigned < total:
        high += total - assigned
    return high, medium, low


def _build_route_sampling_plan(
    *,
    mode: str,
    budget_profile: str,
    sample_size: int,
    priority_file: str,
    priority_profile: str,
) -> dict[str, Any]:
    catalog = [_normalize_route(route) for route in discover_page_routes()]
    catalog = [route for route in catalog if route]
    catalog_size = len(catalog)
    if catalog_size == 0:
        return {
            "mode": str(mode),
            "budget_profile": str(budget_profile),
            "priority_profile": str(priority_profile),
            "catalog_size": 0,
            "sample_size_requested": int(sample_size),
            "selected_route_count": 0,
            "selected_route_indices": [],
            "selected_routes": [],
            "priority_file": "",
            "tier_counts": {"high": 0, "medium": 0, "low": 0},
        }
    file_overrides, resolved_priority_file = _load_route_priority_file(priority_file, priority_profile)
    entries: list[dict[str, Any]] = []
    for index, route in enumerate(catalog):
        base_score, base_tier = _builtin_route_score(route)
        override = file_overrides.get(route)
        if isinstance(override, dict):
            score = _to_int(override.get("score"), base_score)
            tier = str(override.get("tier") or base_tier).strip().lower()
            source = "file"
        else:
            score = base_score
            tier = base_tier
            source = "builtin"
        if tier not in {"high", "medium", "low"}:
            tier = base_tier
        entries.append(
            {
                "index": index,
                "route": route,
                "score": max(0, int(score)),
                "tier": tier,
                "source": source,
            }
        )
    ranked = sorted(entries, key=lambda item: (_tier_rank(str(item["tier"])), -int(item["score"]), str(item["route"])))
    effective_sample_size = catalog_size if int(sample_size) <= 0 else min(int(sample_size), catalog_size)
    selected: list[dict[str, Any]]
    normalized_mode = str(mode or "").strip().lower()
    if normalized_mode == "stratified":
        pools: dict[str, list[dict[str, Any]]] = {
            "high": [item for item in ranked if item.get("tier") == "high"],
            "medium": [item for item in ranked if item.get("tier") == "medium"],
            "low": [item for item in ranked if item.get("tier") == "low"],
        }
        high_quota, medium_quota, low_quota = _pick_counts(effective_sample_size, budget_profile)
        selected = pools["high"][:high_quota] + pools["medium"][:medium_quota] + pools["low"][:low_quota]
        if len(selected) < effective_sample_size:
            selected_ids = {int(item["index"]) for item in selected}
            for item in ranked:
                if int(item["index"]) in selected_ids:
                    continue
                selected.append(item)
                selected_ids.add(int(item["index"]))
                if len(selected) >= effective_sample_size:
                    break
    else:
        ordered = sorted(entries, key=lambda item: int(item["index"]))
        selected = ordered[:effective_sample_size]
    selected.sort(key=lambda item: int(item["index"]))
    tier_counts = {"high": 0, "medium": 0, "low": 0}
    for item in selected:
        tier = str(item.get("tier") or "low").lower()
        tier_counts[tier if tier in tier_counts else "low"] += 1
    return {
        "mode": normalized_mode,
        "budget_profile": str(budget_profile),
        "priority_profile": str(priority_profile),
        "catalog_size": catalog_size,
        "sample_size_requested": int(sample_size),
        "selected_route_count": len(selected),
        "selected_route_indices": [int(item["index"]) for item in selected],
        "selected_routes": [str(item["route"]) for item in selected],
        "selected_route_tiers": [
            {
                "index": int(item["index"]),
                "route": str(item["route"]),
                "tier": str(item["tier"]),
                "score": int(item["score"]),
                "source": str(item["source"]),
            }
            for item in selected
        ],
        "priority_file": resolved_priority_file,
        "tier_counts": tier_counts,
    }


def main() -> int:
    def _env_flag(name: str, default: bool = False) -> bool:
        raw = str(os.environ.get(name, "")).strip().lower()
        if not raw:
            return default
        return raw in {"1", "true", "yes", "on"}

    parser = argparse.ArgumentParser(description="Run full Gemini UI audit in parallel shards and enforce strict gate.")
    parser.add_argument(
        "--shards",
        type=int,
        default=int(os.environ.get("CORTEXPILOT_CI_UI_FULL_AUDIT_SHARDS", "6")),
        help="Total shard count. Default: 6.",
    )
    parser.add_argument(
        "--model",
        default=(
            os.environ.get("CORTEXPILOT_CI_UI_FULL_AUDIT_MODEL")
            or os.environ.get("CORTEXPILOT_UI_GEMINI_MODEL")
            or "gemini-3.0-flash"
        ),
    )
    parser.add_argument("--gemini-key-env", default=os.environ.get("CORTEXPILOT_UI_GEMINI_KEY_ENV", "GEMINI_API_KEY"))
    parser.add_argument("--host", default=os.environ.get("CORTEXPILOT_E2E_HOST", "127.0.0.1"))
    parser.add_argument("--api-port", type=int, default=int(os.environ.get("CORTEXPILOT_UI_FULL_E2E_API_PORT", "19600")))
    parser.add_argument(
        "--dashboard-port",
        type=int,
        default=int(os.environ.get("CORTEXPILOT_UI_FULL_E2E_DASHBOARD_PORT", "19700")),
    )
    parser.add_argument(
        "--reuse-running-services",
        action="store_true",
        help="Reuse a single existing api/dashboard pair for all shards via external-base mode.",
    )
    parser.add_argument(
        "--shard-timeout-sec",
        type=int,
        default=int(os.environ.get("CORTEXPILOT_UI_FULL_E2E_PARALLEL_SHARD_TIMEOUT_SEC", "2400")),
        help="Hard timeout per shard process in seconds. 0 disables timeout.",
    )
    parser.add_argument(
        "--heartbeat-interval-sec",
        type=int,
        default=int(os.environ.get("CORTEXPILOT_UI_FULL_E2E_PARALLEL_HEARTBEAT_INTERVAL_SEC", "20")),
        help="Heartbeat interval for shard liveness logs.",
    )
    parser.add_argument(
        "--snapshot-tail-lines",
        type=int,
        default=int(os.environ.get("CORTEXPILOT_UI_FULL_E2E_PARALLEL_SNAPSHOT_TAIL_LINES", "80")),
        help="How many log tail lines are captured in timeout/interrupt snapshots.",
    )
    parser.add_argument(
        "--audit-max-runtime-sec",
        type=int,
        default=int(os.environ.get("CORTEXPILOT_UI_FULL_E2E_MAX_RUNTIME_SEC", "0")),
        help="Optional per-shard runtime budget forwarded to ui_full_e2e_gemini_audit.py.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        default=_env_flag("CORTEXPILOT_UI_FULL_E2E_HEADED", False),
        help="Run visible browser (headed). Default is headless.",
    )
    parser.add_argument(
        "--budget-profile",
        default=os.environ.get("CORTEXPILOT_CI_UI_FULL_AUDIT_BUDGET_PROFILE", "unknown"),
        help="Budget profile label used by CI (for example: pr/nightly_full).",
    )
    parser.add_argument(
        "--run-profile",
        default=os.environ.get("CORTEXPILOT_UI_FULL_E2E_RUN_PROFILE", "default"),
        help="Experiment profile label for A/B attribution.",
    )
    parser.add_argument(
        "--run-label",
        default=os.environ.get("CORTEXPILOT_UI_FULL_E2E_RUN_LABEL", "single"),
        help="Experiment label for this execution.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=int(os.environ.get("CORTEXPILOT_UI_FULL_E2E_MAX_PAGES", "0")),
        help="Forward global route budget; 0 disables cap.",
    )
    parser.add_argument(
        "--max-interactions",
        type=int,
        default=int(os.environ.get("CORTEXPILOT_UI_FULL_E2E_MAX_INTERACTIONS", "0")),
        help="Forward global interaction budget to each shard; 0 disables cap.",
    )
    parser.add_argument(
        "--max-buttons-per-page",
        type=int,
        default=int(os.environ.get("CORTEXPILOT_UI_FULL_E2E_MAX_BUTTONS_PER_PAGE", "120")),
        help="Forward per-route target cap to each shard.",
    )
    parser.add_argument(
        "--max-duplicate-targets",
        type=int,
        default=int(os.environ.get("CORTEXPILOT_UI_FULL_E2E_MAX_DUPLICATE_TARGETS", "3")),
        help="Forward per-signature duplicate cap to each shard.",
    )
    parser.add_argument(
        "--route-sampling-mode",
        default=os.environ.get("CORTEXPILOT_UI_FULL_E2E_ROUTE_SAMPLING_MODE", "off"),
        choices=["off", "stratified"],
        help="Route selection mode: off keeps classic shard slicing, stratified picks prioritized routes first.",
    )
    parser.add_argument(
        "--route-priority-file",
        default=os.environ.get("CORTEXPILOT_UI_FULL_E2E_ROUTE_PRIORITY_FILE", ""),
        help="Optional JSON file providing per-route priority/risk overrides.",
    )
    parser.add_argument(
        "--route-priority-profile",
        default=os.environ.get("CORTEXPILOT_UI_FULL_E2E_ROUTE_PRIORITY_PROFILE", ""),
        help="Priority profile label for filtering route-priority-file entries.",
    )
    parser.add_argument(
        "--route-sample-size",
        type=int,
        default=int(os.environ.get("CORTEXPILOT_UI_FULL_E2E_ROUTE_SAMPLE_SIZE", "0")),
        help="Target selected route count before strict execution; 0 means full catalog.",
    )
    parser.add_argument(
        "--summary-out",
        default="",
        help="Optional path to copy summary.json for downstream orchestration.",
    )
    parser.add_argument(
        "--ab-matrix",
        action="store_true",
        default=_env_flag("CORTEXPILOT_UI_FULL_E2E_AB_MATRIX", False),
        help="Run A/B experiment matrix and auto-summary (p50/p95/fail_rate ranking).",
    )
    parser.add_argument(
        "--ab-profiles",
        default=os.environ.get("CORTEXPILOT_UI_FULL_E2E_AB_PROFILES", ""),
        help=(
            "Semicolon-separated profiles: "
            "label=A,profile=baseline,shards=6,max_pages=24,max_interactions=180,max_runtime_sec=1800;"
            "label=B,profile=stress,shards=7,max_pages=24,max_interactions=360,max_runtime_sec=3600"
        ),
    )
    parser.add_argument(
        "--ab-iterations",
        type=int,
        default=int(os.environ.get("CORTEXPILOT_UI_FULL_E2E_AB_ITERATIONS", "3")),
        help="Run count per A/B profile.",
    )
    parser.add_argument(
        "--click-only",
        action="store_true",
        help="Use click-consistency strict mode (do not block on Gemini warn/fail verdict counts).",
    )
    parser.add_argument(
        "--matrix-child",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()

    if args.shards < 1:
        print("invalid argument: --shards must be >= 1", file=sys.stderr)
        return 2
    if int(args.ab_iterations) < 1:
        print("invalid argument: --ab-iterations must be >= 1", file=sys.stderr)
        return 2
    if int(args.route_sample_size) < 0:
        print("invalid argument: --route-sample-size must be >= 0", file=sys.stderr)
        return 2

    if not AUDIT_SCRIPT.exists():
        print(f"audit script not found: {AUDIT_SCRIPT}", file=sys.stderr)
        return 2

    _prime_llm_keys()
    if not os.environ.get(args.gemini_key_env, "").strip():
        print(f"missing Gemini API key env: {args.gemini_key_env}", file=sys.stderr)
        return 2

    if args.ab_matrix and not args.matrix_child:
        matrix_started_at = _now_iso()
        matrix_run_id = f"ui_full_e2e_parallel_matrix_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        matrix_dir = PARALLEL_OUT_ROOT / matrix_run_id
        matrix_dir.mkdir(parents=True, exist_ok=True)
        matrix_results: list[dict[str, Any]] = []
        profiles = _build_ab_profiles_from_args(args)
        python_bin = _resolve_python()
        script_path = Path(__file__).resolve()
        has_failure = False
        for profile_idx, profile in enumerate(profiles):
            for iteration in range(int(args.ab_iterations)):
                child_summary_path = matrix_dir / f"profile_{profile_idx + 1}_iter_{iteration + 1}.summary.json"
                child_cmd = [
                    python_bin,
                    str(script_path),
                    "--matrix-child",
                    "--shards",
                    str(max(1, int(profile.get("shards", args.shards)))),
                    "--model",
                    str(args.model),
                    "--gemini-key-env",
                    str(args.gemini_key_env),
                    "--host",
                    str(args.host),
                    "--api-port",
                    str(args.api_port),
                    "--dashboard-port",
                    str(args.dashboard_port),
                    "--shard-timeout-sec",
                    str(max(0, int(profile.get("shard_timeout_sec", args.shard_timeout_sec)))),
                    "--heartbeat-interval-sec",
                    str(args.heartbeat_interval_sec),
                    "--snapshot-tail-lines",
                    str(args.snapshot_tail_lines),
                    "--audit-max-runtime-sec",
                    str(max(0, int(profile.get("audit_max_runtime_sec", args.audit_max_runtime_sec)))),
                    "--budget-profile",
                    str(args.budget_profile),
                    "--run-profile",
                    str(profile.get("profile", args.run_profile)),
                    "--run-label",
                    str(profile.get("label", args.run_label)),
                    "--max-pages",
                    str(max(0, int(profile.get("max_pages", args.max_pages)))),
                    "--max-interactions",
                    str(max(0, int(profile.get("max_interactions", args.max_interactions)))),
                    "--max-buttons-per-page",
                    str(max(1, int(profile.get("max_buttons_per_page", args.max_buttons_per_page)))),
                    "--max-duplicate-targets",
                    str(max(1, int(profile.get("max_duplicate_targets", args.max_duplicate_targets)))),
                    "--summary-out",
                    str(child_summary_path),
                ]
                if args.reuse_running_services:
                    child_cmd.append("--reuse-running-services")
                if args.headed:
                    child_cmd.append("--headed")
                print(
                    "[ab-matrix] launching "
                    f"profile={profile.get('profile')} label={profile.get('label')} "
                    f"iteration={iteration + 1}/{int(args.ab_iterations)}"
                )
                child = subprocess.run(
                    child_cmd,
                    cwd=str(ROOT),
                    text=True,
                    capture_output=True,
                )
                if child.stdout:
                    print(child.stdout, end="" if child.stdout.endswith("\n") else "\n")
                if child.stderr:
                    print(child.stderr, file=sys.stderr, end="" if child.stderr.endswith("\n") else "\n")
                child_summary = _read_json_object(child_summary_path)
                if not child_summary:
                    has_failure = True
                    child_summary = {
                        "run_id": "",
                        "run_label": str(profile.get("label", args.run_label)),
                        "run_profile": str(profile.get("profile", args.run_profile)),
                        "duration_sec": 0.0,
                        "strict_ok": False,
                        "fail_reason": "missing_summary",
                        "overall_exit_code": int(child.returncode),
                        "summary_path": str(child_summary_path),
                    }
                elif int(child.returncode) != 0:
                    has_failure = True
                matrix_results.append(
                    {
                        "profile": str(child_summary.get("run_profile") or profile.get("profile") or args.run_profile),
                        "label": str(child_summary.get("run_label") or profile.get("label") or args.run_label),
                        "iteration": int(iteration + 1),
                        "run_id": str(child_summary.get("run_id") or ""),
                        "duration_sec": round(_to_float(child_summary.get("duration_sec"), 0.0), 3),
                        "strict_ok": bool(child_summary.get("strict_ok", False)),
                        "fail_reason": str(child_summary.get("fail_reason") or "unknown"),
                        "overall_exit_code": int(child_summary.get("overall_exit_code", child.returncode)),
                        "summary_path": str(child_summary_path),
                        "strict_stats": child_summary.get("strict_stats", child_summary.get("strict_metrics", {})),
                    }
                )

        grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for item in matrix_results:
            grouped.setdefault((item["profile"], item["label"]), []).append(item)

        rankings: list[dict[str, Any]] = []
        for (profile_name, run_label), items in grouped.items():
            total = len(items)
            failed = sum(1 for x in items if not bool(x.get("strict_ok", False)))
            durations = [float(x.get("duration_sec", 0.0)) for x in items]
            rankings.append(
                {
                    "profile": profile_name,
                    "label": run_label,
                    "runs": total,
                    "failed_runs": failed,
                    "fail_rate": round((failed / total) if total else 1.0, 4),
                    "duration_p50_sec": _percentile(durations, 0.5),
                    "duration_p95_sec": _percentile(durations, 0.95),
                    "strict_pass_count": sum(1 for x in items if bool(x.get("strict_ok", False))),
                }
            )
        rankings.sort(key=lambda x: (x["fail_rate"], x["duration_p95_sec"], x["duration_p50_sec"]))
        recommended = rankings[0] if rankings else None
        recommended_summary_path = ""
        if recommended:
            candidates = [
                x
                for x in matrix_results
                if x.get("profile") == recommended.get("profile")
                and x.get("label") == recommended.get("label")
                and bool(x.get("strict_ok", False))
            ]
            if not candidates:
                candidates = [
                    x
                    for x in matrix_results
                    if x.get("profile") == recommended.get("profile") and x.get("label") == recommended.get("label")
                ]
            candidates.sort(key=lambda x: (_to_float(x.get("duration_sec"), 0.0), int(x.get("iteration", 0))))
            if candidates:
                recommended_summary_path = str(candidates[0].get("summary_path") or "")

        matrix_summary = {
            "run_id": matrix_run_id,
            "started_at": matrix_started_at,
            "finished_at": _now_iso(),
            "ab_iterations": int(args.ab_iterations),
            "profiles_input": profiles,
            "results": matrix_results,
            "timing_summary": {
                "run_duration_sec": _duration_summary([_to_float(x.get("duration_sec"), 0.0) for x in matrix_results]),
                "strict_success_count": sum(1 for x in matrix_results if bool(x.get("strict_ok", False))),
                "strict_fail_count": sum(1 for x in matrix_results if not bool(x.get("strict_ok", False))),
            },
            "rankings": rankings,
            "recommended": recommended,
            "recommended_summary_path": recommended_summary_path,
            "overall_exit_code": 1 if has_failure else 0,
        }
        matrix_summary_path = matrix_dir / "ab_matrix_summary.json"
        matrix_summary_path.write_text(json.dumps(matrix_summary, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

        if args.summary_out:
            target = Path(str(args.summary_out)).expanduser()
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(matrix_summary, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

        print(json.dumps(matrix_summary, ensure_ascii=True, indent=2))
        print("")
        print("Human summary")
        print(f"- run_id: {matrix_run_id}")
        print(f"- ab_matrix: true")
        print(f"- profiles: {len(profiles)}")
        print(f"- ab_iterations: {int(args.ab_iterations)}")
        print(f"- matrix_summary_path: {matrix_summary_path}")
        print(f"- summary_path: {recommended_summary_path or matrix_summary_path}")
        if recommended:
            print(
                "- board_decision: "
                f"profile={recommended.get('profile')} label={recommended.get('label')} "
                f"fail_rate={recommended.get('fail_rate')} "
                f"p50={recommended.get('duration_p50_sec')}s "
                f"p95={recommended.get('duration_p95_sec')}s"
            )
        if rankings:
            print("- ranking:")
            for idx, item in enumerate(rankings, start=1):
                print(
                    "  "
                    f"{idx}. {item['profile']}[{item['label']}] "
                    f"fail_rate={item['fail_rate']} p50={item['duration_p50_sec']}s p95={item['duration_p95_sec']}s"
                )
        return int(matrix_summary["overall_exit_code"])

    run_label = str(args.run_label)
    run_profile = str(args.run_profile)
    run_id = (
        f"ui_full_e2e_parallel_{_sanitize_label(run_label)}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    )
    run_dir = PARALLEL_OUT_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    heartbeat_stream = run_dir / "heartbeats.jsonl"
    python_bin = _resolve_python()
    started_at = _now_iso()
    started_monotonic = time.monotonic()
    global_max_pages = max(0, int(args.max_pages))
    global_max_interactions = max(0, int(args.max_interactions))
    route_priority_profile = str(args.route_priority_profile or args.budget_profile or "default")
    explicit_route_sample_size = max(0, int(args.route_sample_size))
    requested_sample_size = explicit_route_sample_size if explicit_route_sample_size > 0 else global_max_pages
    try:
        route_plan = _build_route_sampling_plan(
            mode=str(args.route_sampling_mode),
            budget_profile=str(args.budget_profile),
            sample_size=requested_sample_size,
            priority_file=str(args.route_priority_file),
            priority_profile=route_priority_profile,
        )
    except Exception as exc:
        print(f"failed to build route sampling plan: {exc}", file=sys.stderr)
        return 2
    selected_route_indices = [int(value) for value in route_plan.get("selected_route_indices", [])]
    selected_routes = [str(value) for value in route_plan.get("selected_routes", [])]
    if not selected_route_indices:
        print("route sampling selected 0 routes; aborting strict run", file=sys.stderr)
        return 2
    shard_concurrency = max(1, int(args.shards))
    task_count = len(selected_route_indices)
    max_pages_per_task = 1
    max_interactions_per_task = (
        (global_max_interactions + task_count - 1) // task_count if global_max_interactions > 0 else 0
    )
    route_catalog_size = max(1, int(route_plan.get("catalog_size", len(selected_route_indices))))
    route_tasks = [
        {
            "task_index": index,
            "route_catalog_index": selected_route_indices[index],
            "route_catalog_route": selected_routes[index] if index < len(selected_routes) else "",
        }
        for index in range(task_count)
    ]

    shards_runtime: list[dict[str, Any]] = []
    pending_tasks = list(route_tasks)
    exit_code = 0
    external_api_base = ""
    external_dashboard_base = ""
    if args.reuse_running_services:
        candidate_api = f"http://{args.host}:{int(args.api_port)}"
        candidate_dashboard = f"http://{args.host}:{int(args.dashboard_port)}"
        if not _http_ok(f"{candidate_api}/health", timeout_sec=3):
            print(
                f"reuse-running-services enabled but api is not healthy: {candidate_api}/health",
                file=sys.stderr,
            )
            return 2
        if not _http_ok(f"{candidate_api}/api/runs", timeout_sec=4, auth=True):
            print(
                "reuse-running-services enabled but api contract probe failed: "
                f"{candidate_api}/api/runs",
                file=sys.stderr,
            )
            return 2
        if not _http_ok(f"{candidate_dashboard}/pm", timeout_sec=4):
            print(
                f"reuse-running-services enabled but dashboard is not healthy: {candidate_dashboard}/pm",
                file=sys.stderr,
            )
            return 2
        external_api_base = candidate_api
        external_dashboard_base = candidate_dashboard
        print(
            "using shared external services for all shards: "
            f"api={external_api_base} dashboard={external_dashboard_base}"
        )
    try:
        heartbeat_interval_sec = max(1, int(args.heartbeat_interval_sec))
        next_heartbeat_deadline = time.monotonic()
        while True:
            running_count = sum(
                1
                for item in shards_runtime
                if isinstance(item.get("process"), subprocess.Popen) and not item.get("finished_at")
            )
            while pending_tasks and running_count < shard_concurrency:
                task = pending_tasks.pop(0)
                task_index = int(task.get("task_index", 0))
                route_index = int(task.get("route_catalog_index", 0))
                route_path = str(task.get("route_catalog_route") or "")
                api_port = int(args.api_port) + task_index * PORT_STRIDE
                dashboard_port = int(args.dashboard_port) + task_index * PORT_STRIDE
                runtime = _spawn_shard(
                    python_bin=python_bin,
                    execution_index=task_index,
                    route_shard_total=route_catalog_size,
                    route_shard_index=route_index,
                    route_path=route_path,
                    model=args.model,
                    gemini_key_env=args.gemini_key_env,
                    host=args.host,
                    api_port=api_port,
                    dashboard_port=dashboard_port,
                    parent_run_id=run_id,
                    run_dir=run_dir,
                    audit_max_runtime_sec=int(args.audit_max_runtime_sec),
                    audit_heartbeat_interval_sec=int(args.heartbeat_interval_sec),
                    external_api_base=external_api_base,
                    external_dashboard_base=external_dashboard_base,
                    headed=bool(args.headed),
                    max_pages=int(max_pages_per_task),
                    max_buttons_per_page=int(args.max_buttons_per_page),
                    max_interactions=int(max_interactions_per_task),
                    max_duplicate_targets=int(args.max_duplicate_targets),
                )
                shards_runtime.append(runtime)
                running_count += 1
            now_mono = time.monotonic()
            for item in shards_runtime:
                proc = item.get("process")
                if not isinstance(proc, subprocess.Popen):
                    continue
                if item.get("finished_at"):
                    continue
                return_code = proc.poll()
                if return_code is not None:
                    item["exit_code"] = int(return_code)
                    item["finished_at"] = _now_iso()
                    item["finished_monotonic"] = time.monotonic()
                    _close_log_fp(item)
                    continue
                running_count += 1
                elapsed_sec = now_mono - float(item.get("started_monotonic", now_mono))
                if int(args.shard_timeout_sec) > 0 and elapsed_sec > float(args.shard_timeout_sec):
                    reason = f"timeout exceeded: elapsed={elapsed_sec:.1f}s limit={int(args.shard_timeout_sec)}s"
                    snapshot_path = _write_failure_snapshot(
                        run_dir=run_dir,
                        item=item,
                        reason=reason,
                        tail_lines=int(args.snapshot_tail_lines),
                    )
                    item["failure_snapshot_path"] = str(snapshot_path)
                    item["timed_out"] = True
                    item["termination_signal"] = _terminate_proc(proc)
                    item["exit_code"] = int(proc.poll() if proc.poll() is not None else 124)
                    item["finished_at"] = _now_iso()
                    item["finished_monotonic"] = time.monotonic()
                    _close_log_fp(item)
                    print(
                        f"shard {item.get('index')} timeout: {reason}, snapshot={snapshot_path}",
                        file=sys.stderr,
                    )
            running_count = sum(
                1
                for item in shards_runtime
                if isinstance(item.get("process"), subprocess.Popen) and not item.get("finished_at")
            )
            if running_count == 0 and not pending_tasks:
                break
            if now_mono >= next_heartbeat_deadline:
                for item in shards_runtime:
                    if item.get("finished_at"):
                        continue
                    log_path = Path(str(item.get("log_path", "")))
                    log_size = int(log_path.stat().st_size) if log_path.exists() else 0
                    heartbeat = {
                        "at": _now_iso(),
                        "run_id": run_id,
                        "shard_index": item.get("index"),
                        "shard_run_id": item.get("run_id"),
                        "pid": item.get("pid"),
                        "elapsed_sec": round(now_mono - float(item.get("started_monotonic", now_mono)), 3),
                        "report_exists": Path(str(item.get("report_path", ""))).exists(),
                        "log_size_bytes": log_size,
                    }
                    item["last_heartbeat_at"] = heartbeat["at"]
                    item["last_heartbeat"] = heartbeat
                    _append_jsonl(heartbeat_stream, heartbeat)
                    print(
                        "💓 [parallel-ui-full-e2e] "
                        f"shard={item.get('index')} pid={item.get('pid')} "
                        f"route_index={item.get('route_catalog_index')} "
                        f"elapsed={heartbeat['elapsed_sec']}s log={log_size}B "
                        f"report={'yes' if heartbeat['report_exists'] else 'no'}"
                    )
                next_heartbeat_deadline = now_mono + float(heartbeat_interval_sec)
            time.sleep(1.0)
    except KeyboardInterrupt:
        for item in shards_runtime:
            proc = item.get("process")
            if not isinstance(proc, subprocess.Popen):
                continue
            if item.get("finished_at"):
                continue
            snapshot_path = _write_failure_snapshot(
                run_dir=run_dir,
                item=item,
                reason="keyboard_interrupt",
                tail_lines=int(args.snapshot_tail_lines),
            )
            item["failure_snapshot_path"] = str(snapshot_path)
            item["termination_signal"] = _terminate_proc(proc)
            item["exit_code"] = int(proc.poll() if proc.poll() is not None else 130)
            item["finished_at"] = _now_iso()
            item["finished_monotonic"] = time.monotonic()
            _close_log_fp(item)
        _terminate_shards(shards_runtime)
        print("parallel audit interrupted", file=sys.stderr)
        return 130

    failed_shards: list[int] = []
    report_errors: list[dict[str, Any]] = []
    totals = {
        "route_count": 0,
        "reported_total_routes": 0,
        "page_pass": 0,
        "page_warn": 0,
        "page_fail": 0,
        "inter_pass": 0,
        "inter_warn": 0,
        "inter_fail": 0,
        "total_interactions": 0,
        "interaction_entry_count": 0,
        "click_failures": 0,
        "derived_click_failures": 0,
        "summary_warn_or_fail": 0,
        "derived_warn_or_fail": 0,
        "reported_click_inventory_entries": 0,
        "reported_click_inventory_blocking_failures": 0,
        "reported_click_inventory_missing_target_refs": 0,
        "reported_click_inventory_overall_passed_false_count": 0,
        "derived_click_inventory_entries": 0,
        "derived_click_inventory_blocking_failures": 0,
        "derived_click_inventory_missing_target_refs": 0,
        "click_inventory_report_exists_count": 0,
        "click_inventory_report_missing_count": 0,
        "click_inventory_report_entries": 0,
        "click_inventory_report_blocking_failures": 0,
        "click_inventory_report_missing_target_refs": 0,
        "click_inventory_report_overall_passed_false_count": 0,
        "click_inventory_consistency_error_count": 0,
        "summary_consistency_error_count": 0,
        "route_error_count": 0,
        "blocking_route_error_count": 0,
        "recovered_route_error_count": 0,
        "navigation_failures": 0,
        "missing_page_analysis_count": 0,
        "missing_interaction_analysis_count": 0,
        "gemini_skipped_count": 0,
    }
    missing_page_analysis_routes: list[dict[str, Any]] = []
    missing_interaction_analysis_entries: list[dict[str, Any]] = []

    shard_results: list[dict[str, Any]] = []
    for item in shards_runtime:
        shard_result = {
            "index": item["index"],
            "run_id": item["run_id"],
            "api_port": item["api_port"],
            "dashboard_port": item["dashboard_port"],
            "exit_code": item.get("exit_code", 1),
            "report_path": item["report_path"],
            "log_path": item["log_path"],
            "started_at": item["started_at"],
            "finished_at": item.get("finished_at", ""),
            "pid": item.get("pid"),
            "timed_out": bool(item.get("timed_out", False)),
            "termination_signal": item.get("termination_signal", ""),
            "failure_snapshot_path": item.get("failure_snapshot_path", ""),
            "last_heartbeat_at": item.get("last_heartbeat_at", ""),
            "report_exists": False,
            "duration_sec": round(
                max(
                    0.0,
                    _to_float(item.get("finished_monotonic"), time.monotonic())
                    - _to_float(item.get("started_monotonic"), time.monotonic()),
                ),
                3,
            ),
        }
        shard_result["route_catalog_index"] = _to_int(item.get("route_catalog_index"), -1)
        shard_result["route_catalog_route"] = str(item.get("route_catalog_route") or "")
        if int(shard_result["exit_code"]) != 0:
            failed_shards.append(int(item["index"]))

        report_path = Path(item["report_path"])
        if not report_path.exists():
            report_errors.append(
                {
                    "index": item["index"],
                    "reason": "report_not_found",
                    "report_path": str(report_path),
                }
            )
            shard_results.append(shard_result)
            continue
        shard_result["report_exists"] = True
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("report payload is not object")
            stats = _collect_stats(payload, report_path=report_path)
            shard_result["strict_stats"] = stats
            for key in totals:
                totals[key] += _to_int(stats.get(key, 0), 0)
            for route_path in stats.get("missing_page_analysis_routes", []) or []:
                missing_page_analysis_routes.append(
                    {
                        "shard_index": int(item["index"]),
                        "run_id": str(item["run_id"]),
                        "route": str(route_path),
                    }
                )
            for missing_entry in stats.get("missing_interaction_analysis_entries", []) or []:
                if not isinstance(missing_entry, dict):
                    continue
                missing_interaction_analysis_entries.append(
                    {
                        "shard_index": int(item["index"]),
                        "run_id": str(item["run_id"]),
                        "route": str(missing_entry.get("route") or ""),
                        "interaction_index": _to_int(missing_entry.get("interaction_index"), 0),
                        "target_label": str(missing_entry.get("target_label") or "unknown"),
                    }
                )
        except Exception as exc:
            report_errors.append(
                {
                    "index": item["index"],
                    "reason": "report_parse_failed",
                    "error": str(exc),
                    "report_path": str(report_path),
                }
            )
        shard_results.append(shard_result)

    strict_metrics = {
        "route_count": totals["route_count"],
        "reported_total_routes": totals["reported_total_routes"],
        "page_warn": totals["page_warn"],
        "page_fail": totals["page_fail"],
        "inter_warn": totals["inter_warn"],
        "inter_fail": totals["inter_fail"],
        "total_interactions": totals["total_interactions"],
        "interaction_entry_count": totals["interaction_entry_count"],
        "click_failures": totals["click_failures"],
        "derived_click_failures": totals["derived_click_failures"],
        "summary_warn_or_fail": totals["summary_warn_or_fail"],
        "derived_warn_or_fail": totals["derived_warn_or_fail"],
        "reported_click_inventory_entries": totals["reported_click_inventory_entries"],
        "reported_click_inventory_blocking_failures": totals["reported_click_inventory_blocking_failures"],
        "reported_click_inventory_missing_target_refs": totals["reported_click_inventory_missing_target_refs"],
        "reported_click_inventory_overall_passed_false_count": totals["reported_click_inventory_overall_passed_false_count"],
        "derived_click_inventory_entries": totals["derived_click_inventory_entries"],
        "derived_click_inventory_blocking_failures": totals["derived_click_inventory_blocking_failures"],
        "derived_click_inventory_missing_target_refs": totals["derived_click_inventory_missing_target_refs"],
        "click_inventory_report_exists_count": totals["click_inventory_report_exists_count"],
        "click_inventory_report_missing_count": totals["click_inventory_report_missing_count"],
        "click_inventory_report_entries": totals["click_inventory_report_entries"],
        "click_inventory_report_blocking_failures": totals["click_inventory_report_blocking_failures"],
        "click_inventory_report_missing_target_refs": totals["click_inventory_report_missing_target_refs"],
        "click_inventory_report_overall_passed_false_count": totals["click_inventory_report_overall_passed_false_count"],
        "click_inventory_consistency_error_count": totals["click_inventory_consistency_error_count"],
        "summary_consistency_error_count": totals["summary_consistency_error_count"],
        "route_error_count": totals["route_error_count"],
        "blocking_route_error_count": totals["blocking_route_error_count"],
        "recovered_route_error_count": totals["recovered_route_error_count"],
        "navigation_failures": totals["navigation_failures"],
        "missing_page_analysis_count": totals["missing_page_analysis_count"],
        "missing_page_analysis_routes": missing_page_analysis_routes,
        "missing_interaction_analysis_count": totals["missing_interaction_analysis_count"],
        "missing_interaction_analysis_entries": missing_interaction_analysis_entries,
        "gemini_skipped_count": totals["gemini_skipped_count"],
    }
    require_gemini_clean = not bool(args.click_only)
    strict_ok = (
        strict_metrics["route_count"] > 0
        and strict_metrics["reported_total_routes"] == strict_metrics["route_count"]
        and strict_metrics["total_interactions"] > 0
        and strict_metrics["interaction_entry_count"] > 0
        and strict_metrics["total_interactions"] == strict_metrics["interaction_entry_count"]
        and strict_metrics["click_failures"] == 0
        and strict_metrics["click_failures"] == strict_metrics["derived_click_failures"]
        and strict_metrics["summary_warn_or_fail"] == strict_metrics["derived_warn_or_fail"]
        and strict_metrics["reported_click_inventory_entries"] > 0
        and strict_metrics["reported_click_inventory_entries"] == strict_metrics["derived_click_inventory_entries"]
        and strict_metrics["reported_click_inventory_blocking_failures"] == 0
        and strict_metrics["reported_click_inventory_missing_target_refs"] == 0
        and strict_metrics["reported_click_inventory_overall_passed_false_count"] == 0
        and strict_metrics["reported_click_inventory_blocking_failures"] == strict_metrics["derived_click_inventory_blocking_failures"]
        and strict_metrics["reported_click_inventory_missing_target_refs"] == strict_metrics["derived_click_inventory_missing_target_refs"]
        and strict_metrics["click_inventory_report_missing_count"] == 0
        and strict_metrics["click_inventory_report_entries"] == strict_metrics["reported_click_inventory_entries"]
        and strict_metrics["click_inventory_report_blocking_failures"] == strict_metrics["reported_click_inventory_blocking_failures"]
        and strict_metrics["click_inventory_report_missing_target_refs"] == strict_metrics["reported_click_inventory_missing_target_refs"]
        and strict_metrics["click_inventory_report_overall_passed_false_count"] == strict_metrics["reported_click_inventory_overall_passed_false_count"]
        and strict_metrics["click_inventory_consistency_error_count"] == 0
        and strict_metrics["summary_consistency_error_count"] == 0
        and strict_metrics["navigation_failures"] == 0
        and strict_metrics["missing_page_analysis_count"] == 0
        and strict_metrics["missing_interaction_analysis_count"] == 0
        and (
            not require_gemini_clean
            or (
                strict_metrics["blocking_route_error_count"] == 0
                and strict_metrics["gemini_skipped_count"] == 0
                and
                strict_metrics["page_warn"] == 0
                and strict_metrics["page_fail"] == 0
                and strict_metrics["inter_warn"] == 0
                and strict_metrics["inter_fail"] == 0
            )
        )
    )

    if failed_shards or report_errors or not strict_ok:
        exit_code = 1

    fail_reasons = _resolve_fail_reasons(
        failed_shards=failed_shards,
        report_errors=report_errors,
        strict_metrics=strict_metrics,
        strict_ok=strict_ok,
        require_gemini_clean=require_gemini_clean,
    )
    duration_sec = round(max(0.0, time.monotonic() - started_monotonic), 3)
    timing_summary = _build_timing_summary(shard_results, require_gemini_clean=require_gemini_clean)

    summary = {
        "run_id": run_id,
        "run_label": run_label,
        "run_profile": run_profile,
        "started_at": started_at,
        "finished_at": _now_iso(),
        "duration_sec": duration_sec,
        "shards": int(args.shards),
        "task_count": int(task_count),
        "model": str(args.model),
        "gemini_key_env": str(args.gemini_key_env),
        "host": str(args.host),
        "api_port_base": int(args.api_port),
        "dashboard_port_base": int(args.dashboard_port),
        "port_stride": PORT_STRIDE,
        "reuse_running_services": bool(args.reuse_running_services),
        "budget_profile": str(args.budget_profile),
        "route_sampling": {
            "mode": str(args.route_sampling_mode),
            "priority_file": str(route_plan.get("priority_file") or ""),
            "priority_profile": str(route_priority_profile),
            "catalog_size": int(route_plan.get("catalog_size", 0)),
            "sample_size_requested": int(route_plan.get("sample_size_requested", 0)),
            "selected_route_count": int(route_plan.get("selected_route_count", 0)),
            "tier_counts": route_plan.get("tier_counts", {}),
            "selected_route_indices": route_plan.get("selected_route_indices", []),
            "selected_routes": route_plan.get("selected_routes", []),
        },
        "shard_timeout_sec": int(args.shard_timeout_sec),
        "heartbeat_interval_sec": int(args.heartbeat_interval_sec),
        "audit_max_runtime_sec": int(args.audit_max_runtime_sec),
        "budget": {
            "max_pages_global": int(global_max_pages),
            "max_pages_per_shard": int(max_pages_per_task),
            "max_interactions_global": int(global_max_interactions),
            "max_interactions_per_shard": int(max_interactions_per_task),
            "max_buttons_per_page": int(args.max_buttons_per_page),
            "max_duplicate_targets": int(args.max_duplicate_targets),
        },
        "external_api_base": external_api_base,
        "external_dashboard_base": external_dashboard_base,
        "heartbeat_stream_path": str(heartbeat_stream),
        "strict_metrics": strict_metrics,
        "strict_stats": strict_metrics,
        "strict_ok": strict_ok,
        "strict_mode": "click_only" if args.click_only else "gemini_clean",
        "timing_summary": timing_summary,
        "fail_reason": fail_reasons[0],
        "fail_reasons": fail_reasons,
        "failed_shards": failed_shards,
        "report_errors": report_errors,
        "shard_results": shard_results,
        "overall_exit_code": exit_code,
    }

    summary_path = run_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    if args.summary_out:
        target = Path(str(args.summary_out)).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(summary, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=True, indent=2))
    print("")
    print("Human summary")
    print(f"- run_id: {run_id}")
    print(f"- run_profile: {run_profile}")
    print(f"- run_label: {run_label}")
    print(f"- shards: {args.shards}")
    print(f"- duration_sec: {duration_sec}")
    print(f"- failed_shards: {failed_shards if failed_shards else 'none'}")
    if report_errors:
        print(f"- report_errors: {len(report_errors)}")
    else:
        print("- report_errors: 0")
    print(f"- strict_stats: {strict_metrics}")
    print(f"- timing_summary: {timing_summary}")
    print(f"- fail_reason: {fail_reasons[0]}")
    print(f"- strict_ok: {strict_ok}")
    print(f"- summary_path: {summary_path}")

    if failed_shards:
        print(f"parallel shards failed: {failed_shards}", file=sys.stderr)
    if not strict_ok:
        if args.click_only:
            print("strict gate failed: non-zero click_failures/navigation/missing_analysis", file=sys.stderr)
        else:
            print(
                "strict gate failed: non-zero warn/fail/click_failures/blocking_route_errors/"
                "missing_analysis/gemini_skipped",
                file=sys.stderr,
            )
    if report_errors:
        print("strict gate failed: report errors detected", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
