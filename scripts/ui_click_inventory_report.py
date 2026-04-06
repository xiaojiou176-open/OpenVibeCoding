#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORT_ROOT = ROOT / ".runtime-cache" / "test_output" / "ui_full_gemini_audit"


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


def _target_label(target: dict[str, Any]) -> str:
    return (
        str(target.get("text") or "").strip()
        or str(target.get("aria_label") or "").strip()
        or str(target.get("data_testid") or "").strip()
        or str(target.get("id_attr") or "").strip()
        or str(target.get("instance_id") or "").strip()
        or str(target.get("selector") or "").strip()
        or str(target.get("tag") or "").strip()
        or "unknown"
    )


def _derive_interaction_result(*, click_ok: bool, analysis_verdict: str) -> str:
    verdict = str(analysis_verdict or "").strip().lower()
    if not click_ok:
        return "fail"
    if verdict in {"pass", "warn", "fail"}:
        return verdict
    return "unknown"


def _build_inventory(payload: dict[str, Any], *, source_report: Path) -> dict[str, Any]:
    inventory: list[dict[str, Any]] = []
    pass_count = 0
    warn_count = 0
    fail_count = 0
    unknown_count = 0
    click_failures = 0
    analysis_warn_or_fail_count = 0
    missing_target_ref_count = 0
    blocking_failures = 0

    for route in payload.get("routes", []) or []:
        route_path = str(route.get("route") or "")
        for interaction in route.get("interactions", []) or []:
            target = interaction.get("target") if isinstance(interaction.get("target"), dict) else {}
            analysis = interaction.get("analysis") if isinstance(interaction.get("analysis"), dict) else {}
            click_ok = interaction.get("click_ok") is True
            analysis_verdict = str(analysis.get("verdict", "")).strip().lower()
            interaction_result = _derive_interaction_result(click_ok=click_ok, analysis_verdict=analysis_verdict)
            selector = str(target.get("selector") or "").strip()
            instance_id = str(target.get("instance_id") or "").strip()
            id_attr = str(target.get("id_attr") or "").strip()
            data_testid = str(target.get("data_testid") or "").strip()
            target_ref = selector or id_attr or data_testid or instance_id

            if not click_ok:
                click_failures += 1
            if analysis_verdict in {"warn", "fail"}:
                analysis_warn_or_fail_count += 1
            if not target_ref:
                missing_target_ref_count += 1

            entry_blocking = interaction_result != "pass" or not target_ref
            if interaction_result == "pass":
                pass_count += 1
            elif interaction_result == "warn":
                warn_count += 1
            elif interaction_result == "fail":
                fail_count += 1
            else:
                unknown_count += 1
            if entry_blocking:
                blocking_failures += 1

            inventory.append(
                {
                    "route": route_path,
                    "interaction_index": int(interaction.get("index", 0) or 0),
                    "target_label": _target_label(target),
                    "target_selector": selector,
                    "target_instance_id": instance_id,
                    "target_id_attr": id_attr,
                    "target_data_testid": data_testid,
                    "target_role": str(target.get("role") or "").strip(),
                    "target_tag": str(target.get("tag") or "").strip(),
                    "target_ref": target_ref,
                    "click_ok": click_ok,
                    "click_strategy": str(interaction.get("click_strategy") or "").strip(),
                    "analysis_verdict": analysis_verdict or "unknown",
                    "interaction_result": interaction_result,
                    "errors": [str(err) for err in (interaction.get("errors") or [])],
                }
            )

    summary = {
        "total_routes": len(payload.get("routes", []) or []),
        "total_entries": len(inventory),
        "pass_count": pass_count,
        "warn_count": warn_count,
        "fail_count": fail_count,
        "unknown_count": unknown_count,
        "click_failures": click_failures,
        "analysis_warn_or_fail_count": analysis_warn_or_fail_count,
        "missing_target_ref_count": missing_target_ref_count,
        "blocking_failures": blocking_failures,
        "overall_passed": len(inventory) > 0 and blocking_failures == 0,
    }
    return {
        "source_report": str(source_report),
        "summary": summary,
        "inventory": inventory,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build auditable click inventory from full Gemini UI audit report.")
    parser.add_argument("--report", default="", help="Path to ui_full_e2e report.json. Defaults to latest report.")
    parser.add_argument(
        "--out",
        default="",
        help="Output JSON path. Defaults to report sibling click_inventory_report.json.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 when inventory summary overall_passed is false.",
    )
    args = parser.parse_args()

    try:
        report_path = _resolve_report_path(args.report)
    except Exception as exc:  # noqa: BLE001
        print(f"❌ [ui-click-inventory] {exc}", file=sys.stderr)
        return 2

    out_path = Path(args.out).expanduser().resolve() if args.out else report_path.parent / "click_inventory_report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("report payload is not an object")
    except Exception as exc:  # noqa: BLE001
        print(f"❌ [ui-click-inventory] failed to parse report: {exc}", file=sys.stderr)
        return 2

    inventory_report = _build_inventory(payload, source_report=report_path)
    out_path.write_text(json.dumps(inventory_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = inventory_report.get("summary") or {}
    print(
        json.dumps(
            {
                "report": str(report_path),
                "click_inventory_report": str(out_path),
                "total_entries": int(summary.get("total_entries", 0) or 0),
                "blocking_failures": int(summary.get("blocking_failures", 0) or 0),
                "overall_passed": bool(summary.get("overall_passed", False)),
            },
            ensure_ascii=False,
        )
    )

    if args.strict and not bool(summary.get("overall_passed", False)):
        print("❌ [ui-click-inventory] strict gate failed: overall_passed=false", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
