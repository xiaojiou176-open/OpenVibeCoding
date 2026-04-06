#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORT_ROOT = ROOT / ".runtime-cache" / "test_output" / "ui_full_gemini_audit"


def _resolve_break_glass_state(*, click_only: bool, allow_gemini_skipped: bool, report_path: Path) -> dict[str, Any]:
    # `click_only` is now a first-class strict mode (default in CI policy).
    # Break-glass remains mandatory only for high-risk downgrade paths.
    requested = bool(allow_gemini_skipped)
    enabled = str(os.environ.get("CORTEXPILOT_UI_STRICT_BREAK_GLASS", "0")).strip().lower() in {"1", "true", "yes", "y"}
    reason = str(os.environ.get("CORTEXPILOT_UI_STRICT_BREAK_GLASS_REASON", "")).strip()
    ticket = str(os.environ.get("CORTEXPILOT_UI_STRICT_BREAK_GLASS_TICKET", "")).strip()
    state = {
        "requested": requested,
        "enabled": enabled,
        "reason": reason,
        "ticket": ticket,
    }
    if not requested:
        return state
    if not enabled:
        raise ValueError("allow-gemini-skipped requires CORTEXPILOT_UI_STRICT_BREAK_GLASS=1")
    if not reason:
        raise ValueError("break-glass requires CORTEXPILOT_UI_STRICT_BREAK_GLASS_REASON")
    if not ticket:
        raise ValueError("break-glass requires CORTEXPILOT_UI_STRICT_BREAK_GLASS_TICKET")
    audit_path = Path(
        os.environ.get(
            "CORTEXPILOT_UI_STRICT_BREAK_GLASS_AUDIT_PATH",
            str(report_path.parent / "break_glass_audit.jsonl"),
        )
    ).expanduser()
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
        "mode": "allow_gemini_skipped",
        "report": str(report_path),
        "reason": reason,
        "ticket": ticket,
    }
    with audit_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    state["audit_path"] = str(audit_path)
    return state


@dataclass(frozen=True)
class StrictStats:
    route_count: int
    reported_total_routes: int
    page_pass: int
    page_warn: int
    page_fail: int
    inter_pass: int
    inter_warn: int
    inter_fail: int
    total_interactions: int
    interaction_entry_count: int
    click_failures: int
    derived_click_failures: int
    summary_warn_or_fail: int
    derived_warn_or_fail: int
    route_error_count: int
    blocking_route_error_count: int
    recovered_route_error_count: int
    navigation_failures: int
    gemini_skipped_count: int
    missing_page_analysis_count: int
    missing_page_analysis_routes: list[str]
    missing_interaction_analysis_count: int
    missing_interaction_analysis_entries: list[dict[str, Any]]
    reported_click_inventory_entries: int
    reported_click_inventory_blocking_failures: int
    reported_click_inventory_missing_target_refs: int
    reported_click_inventory_overall_passed: bool
    derived_click_inventory_entries: int
    derived_click_inventory_blocking_failures: int
    derived_click_inventory_missing_target_refs: int
    click_inventory_report_path: str
    click_inventory_report_exists: bool
    click_inventory_report_entries: int
    click_inventory_report_blocking_failures: int
    click_inventory_report_missing_target_refs: int
    click_inventory_report_overall_passed: bool
    click_inventory_report_click_failures: int
    click_inventory_report_analysis_warn_or_fail_count: int

    @property
    def hard_gate_ok(self) -> bool:
        return (
            self.click_failures == 0
            and self.reported_click_inventory_blocking_failures == 0
            and self.reported_click_inventory_missing_target_refs == 0
            and self.reported_click_inventory_overall_passed
        )

    @property
    def gemini_clean_ok(self) -> bool:
        return self.page_warn == 0 and self.page_fail == 0 and self.inter_warn == 0 and self.inter_fail == 0

    @property
    def anti_fake_ok(self) -> bool:
        return (
            self.route_count > 0
            and self.reported_total_routes == self.route_count
            and self.total_interactions > 0
            and self.interaction_entry_count > 0
            and self.total_interactions == self.interaction_entry_count
            and self.navigation_failures == 0
            and self.missing_page_analysis_count == 0
            and self.missing_interaction_analysis_count == 0
            and self.reported_click_inventory_entries > 0
            and bool(self.click_inventory_report_path)
            and self.click_inventory_report_exists
            and self.click_inventory_report_entries == self.reported_click_inventory_entries
            and self.click_inventory_report_blocking_failures == self.reported_click_inventory_blocking_failures
            and self.click_inventory_report_missing_target_refs == self.reported_click_inventory_missing_target_refs
            and self.click_inventory_report_overall_passed == self.reported_click_inventory_overall_passed
        )

    @property
    def ok(self) -> bool:
        return self.hard_gate_ok and self.anti_fake_ok


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


def _resolve_report_path(explicit: str) -> Path:
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"report not found: {path}")
        return path

    if not REPORT_ROOT.exists():
        raise FileNotFoundError(f"report root not found: {REPORT_ROOT}")

    candidates = sorted(
        REPORT_ROOT.glob("*/report.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(f"no report.json under: {REPORT_ROOT}")
    return candidates[0]


def _count_verdict(value: Any, *, pass_count: int, warn_count: int, fail_count: int) -> tuple[int, int, int]:
    verdict = str((value or {}).get("verdict", "")).strip().lower()
    if verdict == "pass":
        return pass_count + 1, warn_count, fail_count
    if verdict == "warn":
        return pass_count, warn_count + 1, fail_count
    if verdict == "fail":
        return pass_count, warn_count, fail_count + 1
    return pass_count, warn_count, fail_count


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


def _resolve_click_inventory_report_path(
    payload: dict[str, Any],
    *,
    report_path: Path,
    explicit: str,
) -> str:
    if explicit:
        return str(Path(explicit).expanduser().resolve())
    artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), dict) else {}
    raw = str((artifacts or {}).get("click_inventory_report") or "").strip()
    if not raw:
        return ""
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = (report_path.parent / candidate).resolve()
    else:
        candidate = candidate.resolve()
    return str(candidate)


def _collect_stats(payload: dict[str, Any], *, report_path: Path, click_inventory_report: str = "") -> StrictStats:
    route_count = 0
    page_pass = page_warn = page_fail = 0
    inter_pass = inter_warn = inter_fail = 0
    derived_warn_or_fail = 0
    route_error_count = 0
    blocking_route_error_count = 0
    recovered_route_error_count = 0
    navigation_failures = 0
    gemini_skipped_count = 0
    missing_page_analysis_count = 0
    missing_page_analysis_routes: list[str] = []
    missing_interaction_analysis_count = 0
    missing_interaction_analysis_entries: list[dict[str, Any]] = []
    interaction_entry_count = 0
    derived_click_failures = 0
    derived_click_inventory_entries = 0
    derived_click_inventory_blocking_failures = 0
    derived_click_inventory_missing_target_refs = 0

    for route in payload.get("routes", []) or []:
        route_count += 1
        route_path = str(route.get("route") or "")
        route_errors = route.get("errors", []) or []
        if route_errors:
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
        page_pass, page_warn, page_fail = _count_verdict(
            page_analysis,
            pass_count=page_pass,
            warn_count=page_warn,
            fail_count=page_fail,
        )
        page_verdict = str((page_analysis or {}).get("verdict", "")).strip().lower()
        if (
            isinstance(page_analysis, dict)
            and page_analysis.get("_degraded") is True
            and str(page_analysis.get("_degrade_reason", "")).strip().lower() == "gemini_skipped"
        ):
            gemini_skipped_count += 1
        if page_verdict in {"warn", "fail"}:
            derived_warn_or_fail += 1
        for interaction in route.get("interactions", []) or []:
            interaction_entry_count += 1
            derived_click_inventory_entries += 1
            analysis = interaction.get("analysis")
            if not isinstance(analysis, dict) or not str(analysis.get("verdict", "")).strip():
                missing_interaction_analysis_count += 1
                missing_interaction_analysis_entries.append(
                    {
                        "route": route_path,
                        "interaction_index": int(interaction.get("index", 0) or 0),
                        "target_label": _target_label(interaction.get("target")),
                    }
                )
            inter_pass, inter_warn, inter_fail = _count_verdict(
                analysis,
                pass_count=inter_pass,
                warn_count=inter_warn,
                fail_count=inter_fail,
            )
            inter_verdict = str((analysis or {}).get("verdict", "")).strip().lower()
            if (
                isinstance(analysis, dict)
                and analysis.get("_degraded") is True
                and str(analysis.get("_degrade_reason", "")).strip().lower() == "gemini_skipped"
            ):
                gemini_skipped_count += 1
            if inter_verdict in {"warn", "fail"}:
                derived_warn_or_fail += 1
            if interaction.get("click_ok") is not True:
                derived_click_failures += 1
            click_ok = interaction.get("click_ok") is True
            if not click_ok:
                derived_click_inventory_blocking_failures += 1
            if not _target_ref(
                interaction.get("target"),
                route=route_path,
                interaction_index=int(interaction.get("index", 0) or 0),
            ):
                derived_click_inventory_missing_target_refs += 1

    summary = payload.get("summary") or {}
    click_inventory_summary = payload.get("click_inventory_summary") or {}
    reported_total_routes = int(summary.get("total_routes", 0) or 0)
    click_failures = int(summary.get("interaction_click_failures", 0) or 0)
    total_interactions = int(summary.get("total_interactions", 0) or 0)
    summary_warn_or_fail = int(summary.get("gemini_warn_or_fail", 0) or 0)
    reported_click_inventory_entries = int(
        summary.get("click_inventory_entries", click_inventory_summary.get("total_entries", 0)) or 0
    )
    reported_click_inventory_blocking_failures = int(
        summary.get(
            "click_inventory_blocking_failures",
            click_inventory_summary.get("blocking_failures", 0),
        )
        or 0
    )
    reported_click_inventory_missing_target_refs = int(
        summary.get(
            "click_inventory_missing_target_refs",
            click_inventory_summary.get("missing_target_ref_count", 0),
        )
        or 0
    )
    reported_click_inventory_overall_passed = bool(
        summary.get(
            "click_inventory_overall_passed",
            click_inventory_summary.get("overall_passed", False),
        )
    )

    click_inventory_report_path = _resolve_click_inventory_report_path(
        payload,
        report_path=report_path,
        explicit=click_inventory_report,
    )
    click_inventory_report_exists = False
    click_inventory_report_entries = 0
    click_inventory_report_blocking_failures = 0
    click_inventory_report_missing_target_refs = 0
    click_inventory_report_overall_passed = False
    click_inventory_report_click_failures = 0
    click_inventory_report_analysis_warn_or_fail_count = 0
    if click_inventory_report_path:
        path = Path(click_inventory_report_path)
        if path.exists():
            click_inventory_report_exists = True
            try:
                click_inventory_payload = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(click_inventory_payload, dict):
                    inv_summary = click_inventory_payload.get("summary") or {}
                    click_inventory_report_entries = int(inv_summary.get("total_entries", 0) or 0)
                    click_inventory_report_blocking_failures = int(inv_summary.get("blocking_failures", 0) or 0)
                    click_inventory_report_missing_target_refs = int(
                        inv_summary.get("missing_target_ref_count", 0) or 0
                    )
                    click_inventory_report_overall_passed = bool(inv_summary.get("overall_passed", False))
                    click_inventory_report_click_failures = int(inv_summary.get("click_failures", 0) or 0)
                    click_inventory_report_analysis_warn_or_fail_count = int(
                        inv_summary.get("analysis_warn_or_fail_count", 0) or 0
                    )
            except Exception:
                click_inventory_report_exists = False

    if click_inventory_report_exists:
        reported_click_inventory_entries = click_inventory_report_entries
        reported_click_inventory_blocking_failures = click_inventory_report_blocking_failures
        reported_click_inventory_missing_target_refs = click_inventory_report_missing_target_refs
        reported_click_inventory_overall_passed = click_inventory_report_overall_passed
    click_failures = int(summary.get("interaction_click_failures", click_inventory_report_click_failures) or 0)
    summary_warn_or_fail = int(
        summary.get("gemini_warn_or_fail", click_inventory_report_analysis_warn_or_fail_count) or 0
    )

    return StrictStats(
        route_count=route_count,
        reported_total_routes=reported_total_routes,
        page_pass=page_pass,
        page_warn=page_warn,
        page_fail=page_fail,
        inter_pass=inter_pass,
        inter_warn=inter_warn,
        inter_fail=inter_fail,
        total_interactions=total_interactions,
        interaction_entry_count=interaction_entry_count,
        click_failures=click_failures,
        derived_click_failures=derived_click_failures,
        summary_warn_or_fail=summary_warn_or_fail,
        derived_warn_or_fail=derived_warn_or_fail,
        route_error_count=route_error_count,
        blocking_route_error_count=blocking_route_error_count,
        recovered_route_error_count=recovered_route_error_count,
        navigation_failures=navigation_failures,
        gemini_skipped_count=gemini_skipped_count,
        missing_page_analysis_count=missing_page_analysis_count,
        missing_page_analysis_routes=sorted(set(missing_page_analysis_routes)),
        missing_interaction_analysis_count=missing_interaction_analysis_count,
        missing_interaction_analysis_entries=missing_interaction_analysis_entries,
        reported_click_inventory_entries=reported_click_inventory_entries,
        reported_click_inventory_blocking_failures=reported_click_inventory_blocking_failures,
        reported_click_inventory_missing_target_refs=reported_click_inventory_missing_target_refs,
        reported_click_inventory_overall_passed=reported_click_inventory_overall_passed,
        derived_click_inventory_entries=derived_click_inventory_entries,
        derived_click_inventory_blocking_failures=derived_click_inventory_blocking_failures,
        derived_click_inventory_missing_target_refs=derived_click_inventory_missing_target_refs,
        click_inventory_report_path=click_inventory_report_path,
        click_inventory_report_exists=click_inventory_report_exists,
        click_inventory_report_entries=click_inventory_report_entries,
        click_inventory_report_blocking_failures=click_inventory_report_blocking_failures,
        click_inventory_report_missing_target_refs=click_inventory_report_missing_target_refs,
        click_inventory_report_overall_passed=click_inventory_report_overall_passed,
        click_inventory_report_click_failures=click_inventory_report_click_failures,
        click_inventory_report_analysis_warn_or_fail_count=click_inventory_report_analysis_warn_or_fail_count,
    )


def _collect_failures(stats: StrictStats, *, require_gemini_clean: bool, allow_gemini_skipped: bool) -> list[str]:
    failures: list[str] = []
    if require_gemini_clean and (stats.page_warn != 0 or stats.page_fail != 0):
        failures.append(f"page verdict has warn/fail: warn={stats.page_warn}, fail={stats.page_fail}")
    if require_gemini_clean and (stats.inter_warn != 0 or stats.inter_fail != 0):
        failures.append(f"interaction verdict has warn/fail: warn={stats.inter_warn}, fail={stats.inter_fail}")
    if require_gemini_clean and not allow_gemini_skipped and stats.gemini_skipped_count != 0:
        failures.append(
            "gemini_skipped degrade markers must be 0, "
            f"got {stats.gemini_skipped_count}"
        )
    if stats.click_failures != 0:
        failures.append(f"interaction_click_failures must be 0, got {stats.click_failures}")
    if require_gemini_clean and stats.blocking_route_error_count != 0:
        failures.append(f"blocking route errors must be 0, got {stats.blocking_route_error_count}")
    if stats.reported_click_inventory_blocking_failures != 0:
        failures.append(
            "click inventory blocking_failures must be 0, "
            f"got {stats.reported_click_inventory_blocking_failures}"
        )
    if stats.reported_click_inventory_missing_target_refs != 0:
        failures.append(
            "click inventory missing_target_refs must be 0, "
            f"got {stats.reported_click_inventory_missing_target_refs}"
        )
    if not stats.reported_click_inventory_overall_passed:
        failures.append("click inventory overall_passed must be true")

    if stats.route_count <= 0:
        failures.append("route_count must be > 0")
    if stats.reported_total_routes != stats.route_count:
        failures.append(
            "summary.total_routes mismatch: "
            f"summary={stats.reported_total_routes}, routes={stats.route_count}"
        )
    if stats.total_interactions <= 0:
        failures.append("summary.total_interactions must be > 0")
    if stats.interaction_entry_count <= 0:
        failures.append("routes[].interactions total must be > 0")
    if stats.total_interactions != stats.interaction_entry_count:
        failures.append(
            "summary.total_interactions mismatch: "
            f"summary={stats.total_interactions}, routes_interactions={stats.interaction_entry_count}"
        )
    if stats.click_failures != stats.click_inventory_report_click_failures:
        failures.append(
            "summary.interaction_click_failures mismatch: "
            f"summary={stats.click_failures}, click_inventory_report={stats.click_inventory_report_click_failures}"
        )
    if stats.summary_warn_or_fail != stats.click_inventory_report_analysis_warn_or_fail_count:
        failures.append(
            "summary.gemini_warn_or_fail mismatch: "
            "summary="
            f"{stats.summary_warn_or_fail}, "
            "click_inventory_report="
            f"{stats.click_inventory_report_analysis_warn_or_fail_count}"
        )
    if stats.navigation_failures != 0:
        failures.append(f"navigation_failures must be 0, got {stats.navigation_failures}")
    if stats.missing_page_analysis_count != 0:
        failures.append(
            "missing_page_analysis_count must be 0, "
            f"got {stats.missing_page_analysis_count}"
        )
        failures.append(
            "missing_page_analysis_routes: "
            f"{stats.missing_page_analysis_routes[:10]}"
        )
    if stats.missing_interaction_analysis_count != 0:
        failures.append(
            "missing_interaction_analysis_count must be 0, "
            f"got {stats.missing_interaction_analysis_count}"
        )
        failures.append(
            "missing_interaction_analysis_entries(sample): "
            f"{stats.missing_interaction_analysis_entries[:10]}"
        )
    if stats.reported_click_inventory_entries <= 0:
        failures.append("summary.click_inventory_entries must be > 0")
    if not stats.click_inventory_report_path:
        failures.append("click inventory report path is missing (artifacts.click_inventory_report)")
    elif not stats.click_inventory_report_exists:
        failures.append(f"click inventory report missing or unreadable: {stats.click_inventory_report_path}")
    else:
        if stats.click_inventory_report_entries != stats.reported_click_inventory_entries:
            failures.append(
                "click inventory report total_entries mismatch: "
                f"report={stats.click_inventory_report_entries}, summary={stats.reported_click_inventory_entries}"
            )
        if stats.click_inventory_report_blocking_failures != stats.reported_click_inventory_blocking_failures:
            failures.append(
                "click inventory report blocking_failures mismatch: "
                f"report={stats.click_inventory_report_blocking_failures}, "
                f"summary={stats.reported_click_inventory_blocking_failures}"
            )
        if stats.click_inventory_report_missing_target_refs != stats.reported_click_inventory_missing_target_refs:
            failures.append(
                "click inventory report missing_target_ref_count mismatch: "
                f"report={stats.click_inventory_report_missing_target_refs}, "
                f"summary={stats.reported_click_inventory_missing_target_refs}"
            )
        if stats.click_inventory_report_overall_passed != stats.reported_click_inventory_overall_passed:
            failures.append(
                "click inventory report overall_passed mismatch: "
                f"report={stats.click_inventory_report_overall_passed}, "
                f"summary={stats.reported_click_inventory_overall_passed}"
            )
    return failures


def _write_summary(summary_out: str, payload: dict[str, Any]) -> None:
    raw = str(summary_out or "").strip()
    if not raw:
        return
    path = Path(raw).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Strict gate for full Gemini UI audit report.")
    parser.add_argument("--report", default="", help="Path to report.json. Defaults to latest report under runtime output.")
    parser.add_argument(
        "--click-inventory-report",
        default="",
        help="Optional explicit click_inventory_report.json path. Defaults to report artifacts field.",
    )
    parser.add_argument(
        "--click-only",
        action="store_true",
        help="Only enforce click inventory + click execution consistency (do not fail on Gemini warn/fail verdict counts).",
    )
    parser.add_argument(
        "--allow-gemini-skipped",
        action="store_true",
        help="Allow gemini_skipped degraded analyses in non-click-only mode (for manual diagnostics only).",
    )
    parser.add_argument(
        "--summary-out",
        default="",
        help="Optional path to persist strict gate summary JSON for closeout auditing.",
    )
    args = parser.parse_args()
    summary_out = str(args.summary_out or "").strip()

    try:
        report_path = _resolve_report_path(args.report)
    except Exception as exc:  # noqa: BLE001
        _write_summary(
            summary_out,
            {
                "status": "error",
                "stage": "resolve_report",
                "overall_passed": False,
                "report": str(args.report or ""),
                "click_only_mode": bool(args.click_only),
                "allow_gemini_skipped": bool(args.allow_gemini_skipped),
                "failures": [str(exc)],
            },
        )
        print(f"❌ [ui-full-e2e:strict] {exc}", file=sys.stderr)
        return 2

    try:
        break_glass = _resolve_break_glass_state(
            click_only=bool(args.click_only),
            allow_gemini_skipped=bool(args.allow_gemini_skipped),
            report_path=report_path,
        )
    except Exception as exc:  # noqa: BLE001
        _write_summary(
            summary_out,
            {
                "status": "error",
                "stage": "resolve_break_glass",
                "overall_passed": False,
                "report": str(report_path),
                "click_only_mode": bool(args.click_only),
                "allow_gemini_skipped": bool(args.allow_gemini_skipped),
                "failures": [str(exc)],
            },
        )
        print(f"❌ [ui-full-e2e:strict] {exc}", file=sys.stderr)
        return 2

    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("report payload is not an object")
    except Exception as exc:  # noqa: BLE001
        _write_summary(
            summary_out,
            {
                "status": "error",
                "stage": "load_report",
                "overall_passed": False,
                "report": str(report_path),
                "click_only_mode": bool(args.click_only),
                "allow_gemini_skipped": bool(args.allow_gemini_skipped),
                "failures": [str(exc)],
            },
        )
        print(f"❌ [ui-full-e2e:strict] failed to read report: {exc}", file=sys.stderr)
        return 2

    stats = _collect_stats(
        payload,
        report_path=report_path,
        click_inventory_report=args.click_inventory_report,
    )
    summary = {
        "report": str(report_path),
        "route_count": stats.route_count,
        "reported_total_routes": stats.reported_total_routes,
        "page_pass": stats.page_pass,
        "page_warn": stats.page_warn,
        "page_fail": stats.page_fail,
        "inter_pass": stats.inter_pass,
        "inter_warn": stats.inter_warn,
        "inter_fail": stats.inter_fail,
        "total_interactions": stats.total_interactions,
        "interaction_entry_count": stats.interaction_entry_count,
        "click_failures": stats.click_failures,
        "derived_click_failures": stats.derived_click_failures,
        "summary_warn_or_fail": stats.summary_warn_or_fail,
        "derived_warn_or_fail": stats.derived_warn_or_fail,
        "route_error_count": stats.route_error_count,
        "blocking_route_error_count": stats.blocking_route_error_count,
        "recovered_route_error_count": stats.recovered_route_error_count,
        "navigation_failures": stats.navigation_failures,
        "gemini_skipped_count": stats.gemini_skipped_count,
        "missing_page_analysis_count": stats.missing_page_analysis_count,
        "missing_page_analysis_routes": stats.missing_page_analysis_routes,
        "missing_interaction_analysis_count": stats.missing_interaction_analysis_count,
        "missing_interaction_analysis_entries": stats.missing_interaction_analysis_entries,
        "reported_click_inventory_entries": stats.reported_click_inventory_entries,
        "reported_click_inventory_blocking_failures": stats.reported_click_inventory_blocking_failures,
        "reported_click_inventory_missing_target_refs": stats.reported_click_inventory_missing_target_refs,
        "reported_click_inventory_overall_passed": stats.reported_click_inventory_overall_passed,
        "derived_click_inventory_entries": stats.derived_click_inventory_entries,
        "derived_click_inventory_blocking_failures": stats.derived_click_inventory_blocking_failures,
        "derived_click_inventory_missing_target_refs": stats.derived_click_inventory_missing_target_refs,
        "click_inventory_report_path": stats.click_inventory_report_path,
        "click_inventory_report_exists": stats.click_inventory_report_exists,
        "click_inventory_report_entries": stats.click_inventory_report_entries,
        "click_inventory_report_blocking_failures": stats.click_inventory_report_blocking_failures,
        "click_inventory_report_missing_target_refs": stats.click_inventory_report_missing_target_refs,
        "click_inventory_report_overall_passed": stats.click_inventory_report_overall_passed,
        "click_inventory_report_click_failures": stats.click_inventory_report_click_failures,
        "click_inventory_report_analysis_warn_or_fail_count": stats.click_inventory_report_analysis_warn_or_fail_count,
        "hard_gate_ok": stats.hard_gate_ok,
        "gemini_clean_ok": stats.gemini_clean_ok,
        "anti_fake_ok": stats.anti_fake_ok,
        "click_only_mode": bool(args.click_only),
        "allow_gemini_skipped": bool(args.allow_gemini_skipped),
        "break_glass": break_glass,
    }

    print(json.dumps(summary, ensure_ascii=False, indent=2))

    failures = _collect_failures(
        stats,
        require_gemini_clean=not args.click_only,
        allow_gemini_skipped=bool(args.allow_gemini_skipped),
    )
    summary["failures"] = failures
    summary["overall_passed"] = len(failures) == 0
    summary["status"] = "passed" if not failures else "failed"
    _write_summary(summary_out, summary)
    if failures:
        print("❌ [ui-full-e2e:strict] strict gate failed:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    if args.click_only:
        print("✅ [ui-full-e2e:strict] click-only gate passed (click consistency + anti-fake checks)")
    else:
        print("✅ [ui-full-e2e:strict] full strict gate passed (zero warn/fail + click consistency + anti-fake checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
