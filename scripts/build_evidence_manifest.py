#!/usr/bin/env python3
"""Build a fail-closed evidence manifest for UI/mutation/security/incident chains."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

from ci_current_run_support import load_source_manifest


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TRUTH_REPORT = ROOT / ".runtime-cache" / "test_output" / "ui_regression" / "ui_e2e_truth_gate.json"
DEFAULT_FULL_AUDIT_ROOT = ROOT / ".runtime-cache" / "test_output" / "ui_full_gemini_audit"
DEFAULT_OUTPUT = ROOT / ".runtime-cache" / "test_output" / "ui_regression" / "evidence_manifest.json"
DEFAULT_SCHEMA = ROOT / "schemas" / "evidence_manifest.schema.json"

STRICT_SECTION_IDS = {
    "ui_truth",
    "ui_flake_p0",
    "ui_flake_p1",
    "ui_full_strict",
    "mutation",
    "security",
    "incident",
}


def _now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _mtime_utc(path: Path) -> str:
    return dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.timezone.utc).isoformat()


def _parse_iso(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc).isoformat()


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"{label} missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} invalid json: {path} ({exc})") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object: {path}")
    return payload


def _resolve_existing_path(raw: str, *, base_dir: Path) -> Path:
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = (base_dir / candidate).resolve()
    else:
        candidate = candidate.resolve()
    if not candidate.is_file():
        raise ValueError(f"report file not found: {candidate}")
    return candidate


def _resolve_latest_full_report(root: Path) -> Path:
    if not root.is_dir():
        raise ValueError(f"full audit report root missing: {root}")
    candidates = sorted(root.glob("*/report.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise ValueError(f"no full strict report.json found under: {root}")
    return candidates[0].resolve()


def _timestamp_for_payload(payload: dict[str, Any], *, report_path: Path) -> tuple[str, str]:
    for key in ("generated_at", "created_at", "updated_at", "finished_at"):
        parsed = _parse_iso(payload.get(key))
        if parsed:
            return parsed, key
    return _mtime_utc(report_path), "file_mtime"


def _must_non_empty_str(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing/invalid {field}")
    return value.strip()


def _resolve_truth_run_id(payload: dict[str, Any]) -> str:
    candidates: list[str] = []
    run_alignment = payload.get("run_id_alignment")
    if isinstance(run_alignment, dict):
        for key in (
            "p0_run_id_normalized",
            "p1_run_id_normalized",
            "click_run_id_normalized",
            "p0_run_id",
            "p1_run_id",
            "click_run_id",
        ):
            value = run_alignment.get(key)
            if isinstance(value, str) and value.strip():
                candidates.append(value.strip())
    flake = payload.get("flake")
    if isinstance(flake, dict):
        for key in ("p0", "p1"):
            detail = flake.get(key)
            if isinstance(detail, dict):
                value = detail.get("run_id")
                if isinstance(value, str) and value.strip():
                    candidates.append(value.strip())
    for value in candidates:
        if value:
            return value
    raise ValueError("truth report run_id missing (run_id_alignment/flake)")


def _normalize_flake_section(*, name: str, report_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    run_id = _must_non_empty_str(payload.get("run_id"), field=f"flake.{name}.run_id")
    gate_passed = payload.get("gate_passed")
    completed = payload.get("completed_all_attempts")
    if not isinstance(gate_passed, bool):
        raise ValueError(f"flake.{name}.gate_passed missing/invalid")
    if not isinstance(completed, bool):
        raise ValueError(f"flake.{name}.completed_all_attempts missing/invalid")
    timestamp_utc, timestamp_source = _timestamp_for_payload(payload, report_path=report_path)
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError(f"flake.{name}.artifacts missing/invalid")
    attempts_jsonl = _must_non_empty_str(artifacts.get("attempts_jsonl"), field=f"flake.{name}.artifacts.attempts_jsonl")
    report_markdown = _must_non_empty_str(
        artifacts.get("report_markdown"),
        field=f"flake.{name}.artifacts.report_markdown",
    )
    attempts_sha256 = _must_non_empty_str(
        artifacts.get("attempts_sha256"),
        field=f"flake.{name}.artifacts.attempts_sha256",
    )
    return {
        "run_id": run_id,
        "status": "pass" if (gate_passed and completed) else "fail",
        "timestamp_utc": timestamp_utc,
        "timestamp_source": timestamp_source,
        "artifacts": {
            "report_json": str(report_path),
            "attempts_jsonl": attempts_jsonl,
            "attempts_sha256": attempts_sha256,
            "report_markdown": report_markdown,
        },
        "metrics": {
            "gate_passed": gate_passed,
            "completed_all_attempts": completed,
            "flake_rate_percent": payload.get("flake_rate_percent"),
            "threshold_percent": payload.get("threshold_percent"),
            "iterations_per_command": payload.get("iterations_per_command"),
        },
    }


def _normalize_truth_section(*, report_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    overall_passed = payload.get("overall_passed")
    if not isinstance(overall_passed, bool):
        raise ValueError("truth.overall_passed missing/invalid")
    run_id = _resolve_truth_run_id(payload)
    timestamp_utc, timestamp_source = _timestamp_for_payload(payload, report_path=report_path)
    flake = payload.get("flake") if isinstance(payload.get("flake"), dict) else {}
    return {
        "run_id": run_id,
        "status": "pass" if overall_passed else "fail",
        "timestamp_utc": timestamp_utc,
        "timestamp_source": timestamp_source,
        "artifacts": {"report_json": str(report_path)},
        "metrics": {
            "overall_passed": overall_passed,
            "strict": bool(payload.get("strict")),
            "p0_run_id": (flake.get("p0") or {}).get("run_id"),
            "p1_run_id": (flake.get("p1") or {}).get("run_id"),
        },
    }


def _normalize_full_strict_section(*, report_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    run_id = _must_non_empty_str(payload.get("run_id"), field="full_strict.run_id")
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("full_strict.summary missing/invalid")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError("full_strict.artifacts missing/invalid")
    click_inventory_report = _must_non_empty_str(
        artifacts.get("click_inventory_report"),
        field="full_strict.artifacts.click_inventory_report",
    )
    click_failures = int(summary.get("interaction_click_failures", 0))
    gemini_warn_or_fail = int(summary.get("gemini_warn_or_fail", 0))
    click_inventory_blocking_failures = int(summary.get("click_inventory_blocking_failures", 0))
    click_inventory_missing_target_refs = int(summary.get("click_inventory_missing_target_refs", 0))
    click_inventory_ok = bool(summary.get("click_inventory_overall_passed"))
    total_routes = int(summary.get("total_routes", 0))
    total_interactions = int(summary.get("total_interactions", 0))
    status = (
        "pass"
        if (
            click_failures == 0
            and gemini_warn_or_fail == 0
            and click_inventory_blocking_failures == 0
            and click_inventory_missing_target_refs == 0
            and click_inventory_ok
            and total_routes > 0
            and total_interactions > 0
        )
        else "fail"
    )
    timestamp_utc, timestamp_source = _timestamp_for_payload(payload, report_path=report_path)
    return {
        "run_id": run_id,
        "status": status,
        "timestamp_utc": timestamp_utc,
        "timestamp_source": timestamp_source,
        "artifacts": {
            "report_json": str(report_path),
            "click_inventory_report": click_inventory_report,
        },
        "metrics": {
            "total_routes": total_routes,
            "total_interactions": total_interactions,
            "interaction_click_failures": click_failures,
            "gemini_warn_or_fail": gemini_warn_or_fail,
            "click_inventory_blocking_failures": click_inventory_blocking_failures,
            "click_inventory_missing_target_refs": click_inventory_missing_target_refs,
            "click_inventory_overall_passed": click_inventory_ok,
        },
    }


def _resolve_flake_path_from_truth(truth_payload: dict[str, Any], *, tier: str, fallback: str) -> str:
    flake = truth_payload.get("flake")
    if isinstance(flake, dict):
        detail = flake.get(tier)
        if isinstance(detail, dict):
            raw = detail.get("path")
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
    if fallback.strip():
        return fallback.strip()
    raise ValueError(f"missing flake report path for {tier}")


def _normalize_status_string(raw: str) -> str | None:
    value = raw.strip().lower()
    mapping = {
        "pass": "pass",
        "passed": "pass",
        "ok": "pass",
        "success": "pass",
        "succeeded": "pass",
        "fail": "fail",
        "failed": "fail",
        "error": "fail",
    }
    return mapping.get(value)


def _derive_optional_status(payload: dict[str, Any], *, section_name: str) -> str:
    for key in ("overall_passed", "gate_passed", "passed", "success"):
        value = payload.get(key)
        if isinstance(value, bool):
            return "pass" if value else "fail"
    raw_status = payload.get("status")
    if isinstance(raw_status, str):
        status = _normalize_status_string(raw_status)
        if status:
            return status
    raise ValueError(f"{section_name} report missing status signal (expected bool gate/overall/passed or status string)")


def _derive_optional_run_id(payload: dict[str, Any], *, report_path: Path) -> str:
    for key in ("run_id", "session_id", "execution_id", "id"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return report_path.stem


def _normalize_optional_section(*, section_name: str, report_path: Path | None) -> tuple[dict[str, Any], str]:
    if report_path is None:
        return (
            {
                "run_id": "n/a",
                "status": "missing",
                "timestamp_utc": _now_utc(),
                "timestamp_source": "generated_at",
                "artifacts": {"report_json": ""},
                "metrics": {"present": False},
            },
            "",
        )
    payload = _load_json(report_path, label=f"{section_name} report")
    status = _derive_optional_status(payload, section_name=section_name)
    run_id = _derive_optional_run_id(payload, report_path=report_path)
    timestamp_utc, timestamp_source = _timestamp_for_payload(payload, report_path=report_path)
    metrics: dict[str, Any] = {"present": True}
    for key in ("critical_count", "high_count", "major_count", "fail_count", "pass_count", "total"):
        if key in payload and isinstance(payload[key], int):
            metrics[key] = payload[key]
    return (
        {
            "run_id": run_id,
            "status": status,
            "timestamp_utc": timestamp_utc,
            "timestamp_source": timestamp_source,
            "artifacts": {"report_json": str(report_path)},
            "metrics": metrics,
        },
        str(report_path),
    )


def _resolve_optional_report(path_arg: str) -> Path | None:
    if not path_arg.strip():
        return None
    return _resolve_existing_path(path_arg, base_dir=ROOT)


def _parse_strict_required_sections(raw: str) -> list[str]:
    sections = [item.strip() for item in raw.split(",") if item.strip()]
    if not sections:
        raise ValueError("strict mode enabled but no strict-required-sections provided")
    for item in sections:
        if item not in STRICT_SECTION_IDS:
            raise ValueError(f"invalid strict section id: {item}")
    return sections


def _section_status_map(manifest: dict[str, Any]) -> dict[str, str]:
    evidence = manifest["evidence"]
    return {
        "ui_truth": evidence["ui_truth"]["status"],
        "ui_flake_p0": evidence["ui_flake"]["p0"]["status"],
        "ui_flake_p1": evidence["ui_flake"]["p1"]["status"],
        "ui_full_strict": evidence["ui_full_strict"]["status"],
        "mutation": evidence["mutation"]["status"],
        "security": evidence["security"]["status"],
        "incident": evidence["incident"]["status"],
    }


def _check_strict_missing(manifest: dict[str, Any], *, strict_required: list[str]) -> None:
    statuses = _section_status_map(manifest)
    missing = [item for item in strict_required if statuses.get(item) == "missing"]
    if missing:
        raise ValueError(f"strict mode missing required evidence sections: {', '.join(missing)}")


def build_manifest(args: argparse.Namespace) -> dict[str, Any]:
    truth_path = Path(args.truth_report).expanduser().resolve()
    truth_payload = _load_json(truth_path, label="truth report")

    p0_raw = _resolve_flake_path_from_truth(truth_payload, tier="p0", fallback=args.p0_flake_report or "")
    p1_raw = _resolve_flake_path_from_truth(truth_payload, tier="p1", fallback=args.p1_flake_report or "")
    p0_path = _resolve_existing_path(p0_raw, base_dir=ROOT)
    p1_path = _resolve_existing_path(p1_raw, base_dir=ROOT)

    if args.full_strict_report:
        full_path = _resolve_existing_path(args.full_strict_report, base_dir=ROOT)
    else:
        full_path = _resolve_latest_full_report(Path(args.full_audit_root).expanduser().resolve())

    p0_payload = _load_json(p0_path, label="p0 flake report")
    p1_payload = _load_json(p1_path, label="p1 flake report")
    full_payload = _load_json(full_path, label="full strict report")

    ui_truth = _normalize_truth_section(report_path=truth_path, payload=truth_payload)
    ui_flake_p0 = _normalize_flake_section(name="p0", report_path=p0_path, payload=p0_payload)
    ui_flake_p1 = _normalize_flake_section(name="p1", report_path=p1_path, payload=p1_payload)
    ui_full_strict = _normalize_full_strict_section(report_path=full_path, payload=full_payload)

    mutation_section, mutation_source = _normalize_optional_section(
        section_name="mutation",
        report_path=_resolve_optional_report(args.mutation_report),
    )
    security_section, security_source = _normalize_optional_section(
        section_name="security",
        report_path=_resolve_optional_report(args.security_report),
    )
    incident_section, incident_source = _normalize_optional_section(
        section_name="incident",
        report_path=_resolve_optional_report(args.incident_report),
    )

    overall_components = [
        ui_truth["status"],
        ui_flake_p0["status"],
        ui_flake_p1["status"],
        ui_full_strict["status"],
    ]
    for status in (mutation_section["status"], security_section["status"], incident_section["status"]):
        if status != "missing":
            overall_components.append(status)
    overall_status = "pass" if all(status == "pass" for status in overall_components) else "fail"

    manifest = {
        "manifest_type": "cortexpilot_evidence_manifest",
        "schema_version": 2,
        "generated_at": _now_utc(),
        "overall_status": overall_status,
        "schema_path": str(Path(args.schema_path).expanduser().resolve()),
        "strict_mode": bool(args.strict_mode),
        "strict_required_sections": _parse_strict_required_sections(args.strict_required_sections),
        "sources": {
            "truth_report": str(truth_path),
            "flake_p0_report": str(p0_path),
            "flake_p1_report": str(p1_path),
            "full_strict_report": str(full_path),
            "mutation_report": mutation_source,
            "security_report": security_source,
            "incident_report": incident_source,
        },
        "evidence": {
            "ui_truth": ui_truth,
            "ui_flake": {"p0": ui_flake_p0, "p1": ui_flake_p1},
            "ui_full_strict": ui_full_strict,
            "mutation": mutation_section,
            "security": security_section,
            "incident": incident_section,
        },
    }
    if args.release_source_manifest:
        release_source = load_source_manifest(args.release_source_manifest)
        manifest["release_context"] = {
            "source_manifest": str(Path(args.release_source_manifest).expanduser().resolve()),
            "source_run_id": str(release_source.get("source_run_id") or ""),
            "source_route": str(release_source.get("source_route") or ""),
            "source_event": str(release_source.get("source_event") or ""),
            "freshness_window_sec": int(release_source.get("freshness_window_sec") or 0),
            "provenance_report": str(
                ((release_source.get("reports") or {}).get("provenance") or "")
            ),
            "current_run_index": str(
                ((release_source.get("reports") or {}).get("current_run_index") or "")
            ),
            "analytics_exclusions": [
                str((item or {}).get("path") or "")
                for item in (release_source.get("analytics_exclusions") or [])
                if isinstance(item, dict)
            ],
        }
    if args.strict_mode:
        _check_strict_missing(manifest, strict_required=manifest["strict_required_sections"])
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build CortexPilot evidence manifest.")
    parser.add_argument(
        "--truth-report",
        default=str(DEFAULT_TRUTH_REPORT),
        help="Path to ui truth gate report JSON.",
    )
    parser.add_argument(
        "--p0-flake-report",
        default="",
        help="Optional explicit p0 flake report path. Defaults to truth report pointer.",
    )
    parser.add_argument(
        "--p1-flake-report",
        default="",
        help="Optional explicit p1 flake report path. Defaults to truth report pointer.",
    )
    parser.add_argument(
        "--full-strict-report",
        default="",
        help="Optional explicit full strict report path. Defaults to latest report under --full-audit-root.",
    )
    parser.add_argument(
        "--full-audit-root",
        default=str(DEFAULT_FULL_AUDIT_ROOT),
        help="Directory containing full audit run folders (used when --full-strict-report is omitted).",
    )
    parser.add_argument(
        "--mutation-report",
        default="",
        help="Optional mutation gate report JSON path.",
    )
    parser.add_argument(
        "--security-report",
        default="",
        help="Optional security gate report JSON path.",
    )
    parser.add_argument(
        "--incident-report",
        default="",
        help="Optional incident regression gate report JSON path.",
    )
    parser.add_argument(
        "--strict-mode",
        action="store_true",
        help="Enable strict mode: required evidence sections cannot be status=missing.",
    )
    parser.add_argument(
        "--strict-required-sections",
        default="ui_truth,ui_flake_p0,ui_flake_p1,ui_full_strict",
        help="Comma separated section IDs for strict-mode missing checks.",
    )
    parser.add_argument(
        "--schema-path",
        default=str(DEFAULT_SCHEMA),
        help="Schema path recorded in manifest metadata.",
    )
    parser.add_argument(
        "--release-source-manifest",
        default="",
        help="Optional current-run source manifest path used for release-evidence semantic checks.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Output evidence manifest path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        manifest = build_manifest(args)
    except ValueError as exc:
        print(f"❌ [evidence-manifest] build failed: {exc}")
        return 1
    output_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"✅ [evidence-manifest] built: {output_path}")
    print(f"ℹ️ [evidence-manifest] overall_status={manifest['overall_status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
