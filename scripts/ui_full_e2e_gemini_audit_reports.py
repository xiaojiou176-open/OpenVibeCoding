from __future__ import annotations

from typing import Any

from scripts.ui_full_e2e_gemini_audit_common import now_iso
from scripts.ui_full_e2e_gemini_audit_targets import build_target_ref, target_label


def derive_interaction_result(*, click_ok: bool, analysis_verdict: str) -> str:
    verdict = analysis_verdict.strip().lower()
    if not click_ok:
        return "fail"
    if verdict in {"pass", "warn", "fail"}:
        return verdict
    return "unknown"


def build_click_inventory_report(payload: dict[str, Any], *, source_report: str) -> dict[str, Any]:
    inventory: list[dict[str, Any]] = []
    pass_count = 0
    warn_count = 0
    fail_count = 0
    unknown_count = 0
    click_failures = 0
    analysis_warn_or_fail_count = 0
    missing_target_ref_count = 0
    blocking_failures = 0

    for route_item in payload.get("routes", []) or []:
        route = str(route_item.get("route") or "")
        route_inventory = route_item.get("click_inventory")
        if isinstance(route_inventory, list) and route_inventory:
            for item in route_inventory:
                if not isinstance(item, dict):
                    continue
                click_ok = item.get("click_ok") is True
                analysis_verdict = str(item.get("analysis_verdict") or "").strip().lower()
                result = str(item.get("interaction_result") or "").strip().lower()
                if result not in {"pass", "warn", "fail", "unknown"}:
                    result = derive_interaction_result(click_ok=click_ok, analysis_verdict=analysis_verdict)
                target_ref = str(item.get("target_ref") or "").strip()
                if not target_ref:
                    missing_target_ref_count += 1
                if not click_ok:
                    click_failures += 1
                if analysis_verdict in {"warn", "fail"}:
                    analysis_warn_or_fail_count += 1

                entry_blocking = (not click_ok) or (not target_ref)
                if result == "pass":
                    pass_count += 1
                elif result == "warn":
                    warn_count += 1
                elif result == "fail":
                    fail_count += 1
                else:
                    unknown_count += 1
                if entry_blocking:
                    blocking_failures += 1

                inventory.append(
                    {
                        "route": route,
                        "interaction_index": int(item.get("interaction_index", 0) or 0),
                        "target_label": str(item.get("target_label") or "").strip() or "unknown",
                        "target_selector": str(item.get("target_selector") or "").strip(),
                        "target_instance_id": str(item.get("target_instance_id") or "").strip(),
                        "target_id_attr": str(item.get("target_id_attr") or "").strip(),
                        "target_data_testid": str(item.get("target_data_testid") or "").strip(),
                        "target_role": str(item.get("target_role") or "").strip(),
                        "target_tag": str(item.get("target_tag") or "").strip(),
                        "target_ref": target_ref,
                        "click_ok": click_ok,
                        "click_strategy": str(item.get("click_strategy") or "").strip(),
                        "analysis_verdict": analysis_verdict or "unknown",
                        "interaction_result": result,
                        "errors": [str(err) for err in (item.get("errors") or [])],
                    }
                )
            continue

        interactions = route_item.get("interactions", []) or []
        for interaction in interactions:
            target = interaction.get("target") if isinstance(interaction.get("target"), dict) else {}
            analysis = interaction.get("analysis") if isinstance(interaction.get("analysis"), dict) else {}
            click_ok = interaction.get("click_ok") is True
            analysis_verdict = str(analysis.get("verdict", "")).strip().lower()
            result = derive_interaction_result(click_ok=click_ok, analysis_verdict=analysis_verdict)
            selector = str(target.get("selector") or "").strip()
            id_attr = str(target.get("id_attr") or "").strip()
            data_testid = str(target.get("data_testid") or "").strip()
            instance_id = str(target.get("instance_id") or "").strip()
            target_ref = build_target_ref(
                target,
                route=route,
                interaction_index=int(interaction.get("index", 0) or 0),
            )
            if not target_ref:
                missing_target_ref_count += 1
            if not click_ok:
                click_failures += 1
            if analysis_verdict in {"warn", "fail"}:
                analysis_warn_or_fail_count += 1

            entry_blocking = (not click_ok) or (not target_ref)
            if result == "pass":
                pass_count += 1
            elif result == "warn":
                warn_count += 1
            elif result == "fail":
                fail_count += 1
            else:
                unknown_count += 1
            if entry_blocking:
                blocking_failures += 1

            inventory.append(
                {
                    "route": route,
                    "interaction_index": int(interaction.get("index", 0) or 0),
                    "target_label": target_label(target),
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
                    "interaction_result": result,
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
        "generated_at": now_iso(),
        "report_run_id": str(payload.get("run_id") or "").strip(),
        "source_report": source_report,
        "summary": summary,
        "inventory": inventory,
    }


def build_markdown_report(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# UI Full E2E + Gemini Audit Report")
    lines.append("")
    lines.append(f"- run_id: `{payload.get('run_id', '')}`")
    lines.append(f"- started_at: `{payload.get('started_at', '')}`")
    lines.append(f"- finished_at: `{payload.get('finished_at', '')}`")
    lines.append(f"- dashboard_base_url: `{payload.get('dashboard_base_url', '')}`")
    lines.append(f"- total_routes: `{payload.get('summary', {}).get('total_routes', 0)}`")
    lines.append(f"- total_interactions: `{payload.get('summary', {}).get('total_interactions', 0)}`")
    lines.append(f"- interaction_click_failures: `{payload.get('summary', {}).get('interaction_click_failures', 0)}`")
    lines.append(f"- gemini_warn_or_fail: `{payload.get('summary', {}).get('gemini_warn_or_fail', 0)}`")
    lines.append("")
    lines.append("## Route Results")
    lines.append("")
    for route_item in payload.get("routes", []):
        lines.append(f"### `{route_item.get('route', '')}`")
        lines.append(f"- page_screenshot: `{route_item.get('page_screenshot', '')}`")
        page_analysis = route_item.get("page_analysis") or {}
        if page_analysis:
            lines.append(f"- page_verdict: `{page_analysis.get('verdict', 'unknown')}`")
            lines.append(f"- page_summary: {page_analysis.get('summary', '')}")
        interactions = route_item.get("interactions", [])
        lines.append(f"- interactions: `{len(interactions)}`")
        for item in interactions:
            target = item.get("target") or {}
            label = (
                target.get("text")
                or target.get("aria_label")
                or target.get("data_testid")
                or target.get("id_attr")
                or target.get("tag")
                or "unknown"
            )
            lines.append(
                f"  - `{label}` | click_ok=`{item.get('click_ok')}` | verdict=`{(item.get('analysis') or {}).get('verdict', 'unknown')}`"
            )
        lines.append("")
    return "\n".join(lines).strip() + "\n"
