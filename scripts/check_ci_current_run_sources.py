#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ci_current_run_support import (
    ROOT,
    analytics_exclusion_paths,
    current_truth_authority,
    load_json,
    load_source_manifest,
    manifest_expected_files,
    manifest_report_paths,
    now_utc,
    source_metadata,
    timestamp_to_iso,
)


def _load(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate current-run CI sources and linked reports.")
    parser.add_argument("--source-manifest", default="")
    parser.add_argument("--out-json", default=".runtime-cache/cortexpilot/reports/ci/current_run/consistency.json")
    parser.add_argument("--out-markdown", default=".runtime-cache/cortexpilot/reports/ci/current_run/consistency.md")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_json = Path(args.out_json).expanduser().resolve()
    out_md = Path(args.out_markdown).expanduser().resolve()
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    try:
        source_manifest = load_source_manifest(args.source_manifest or None)
    except ValueError as exc:
        payload = {
            "report_type": "cortexpilot_ci_current_run_consistency",
            "generated_at": now_utc(),
            "status": "fail",
            "errors": [
                str(exc),
                "hint: build a local-advisory source manifest before running this checker locally, or use the CI authoritative path",
            ],
            "analytics_only_pollution_count": 0,
            "fresh_current_run_report_ratio": 0.0,
            "remote_provenance_ready": False,
            "linked_reports": {},
            "current_head_sha": "",
            "source_head_match": False,
            "authoritative_current_truth": False,
            "advisory_local_only": False,
            "authority_level": "missing",
            "authority_reasons": ["source_manifest_missing"],
            "source_run_id": "",
            "source_run_attempt": "",
            "source_sha": "",
            "source_ref": "",
            "source_event": "",
            "source_route": "",
            "source_trust_class": "",
            "source_runner_class": "",
            "authority_hint": "",
        }
        out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        out_md.write_text(
            "\n".join(
                [
                    "## CI Current Run Consistency",
                    "",
                    "- status: `fail`",
                    "",
                    "### Errors",
                    f"- {payload['errors'][0]}",
                    f"- {payload['errors'][1]}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        print(str(out_json))
        print(str(out_md))
        print("❌ [ci-current-run] consistency check failed")
        for item in payload["errors"]:
            print(f"- {item}")
        return 1

    meta = source_metadata(source_manifest)
    authority = current_truth_authority(source_manifest)
    report_paths = manifest_report_paths(source_manifest)
    errors: list[str] = []
    linked_reports: dict[str, dict[str, Any]] = {}
    required_total = 0
    matching_count = 0

    for name, path in sorted(report_paths.items()):
        required_total += 1
        exists = path.is_file()
        payload = _load(path)
        generated_at = timestamp_to_iso(payload.get("generated_at"))
        source_run_id = str(payload.get("source_run_id") or "")
        source_route = str(payload.get("source_route") or "")
        source_event = str(payload.get("source_event") or "")
        linked_reports[name] = {
            "path": str(path),
            "exists": exists,
            "generated_at": generated_at,
            "source_run_id": source_run_id,
            "source_route": source_route,
            "source_event": source_event,
        }
        if not exists:
            errors.append(f"missing report: {name}")
            continue
        if not generated_at:
            errors.append(f"report missing generated_at: {name}")
        if name != "sbom":
            if source_run_id != meta["source_run_id"]:
                errors.append(f"source_run_id mismatch: {name}")
            if source_route != meta["source_route"]:
                errors.append(f"source_route mismatch: {name}")
            if source_event != meta["source_event"]:
                errors.append(f"source_event mismatch: {name}")
            if (
                source_run_id == meta["source_run_id"]
                and source_route == meta["source_route"]
                and source_event == meta["source_event"]
                and generated_at
            ):
                matching_count += 1
        elif generated_at:
            matching_count += 1

    provenance_path = report_paths.get("provenance")
    provenance = _load(provenance_path)
    workflow = provenance.get("workflow") if isinstance(provenance.get("workflow"), dict) else {}
    remote_provenance_ready = True
    if provenance_path is not None:
        for field in ("github_run_id", "github_run_attempt", "github_ref", "github_event_name"):
            if not str(workflow.get(field) or "").strip():
                errors.append(f"provenance missing workflow metadata: {field}")
                remote_provenance_ready = False
    elif authority["authoritative_current_truth"]:
        errors.append("provenance report missing for authoritative current truth")
        remote_provenance_ready = False
    else:
        remote_provenance_ready = False

    current_run_index = _load(report_paths.get("current_run_index"))
    file_paths = {
        str((ROOT / str(item.get("path") or "")).resolve())
        for group in current_run_index.get("groups", [])
        if isinstance(group, dict)
        for item in group.get("files", [])
        if isinstance(item, dict)
    }
    pollution_count = 0
    for path in analytics_exclusion_paths(source_manifest):
        if str(path.resolve()) in file_paths:
            pollution_count += 1
            errors.append(f"analytics-only pollution detected: {path}")
    pollution_count = max(pollution_count, int(current_run_index.get("analytics_only_pollution_count") or 0))
    if pollution_count > 0 and not any("analytics-only pollution detected:" in item for item in errors):
        errors.append("analytics-only pollution detected: current_run_index.analytics_only_pollution_count")

    for _, path in manifest_expected_files(source_manifest):
        if not path.exists():
            errors.append(f"missing expected file: {path}")

    payload = {
        "report_type": "cortexpilot_ci_current_run_consistency",
        "generated_at": now_utc(),
        "status": "fail" if errors else ("pass" if authority["authoritative_current_truth"] else "advisory"),
        "errors": errors,
        "analytics_only_pollution_count": pollution_count,
        "fresh_current_run_report_ratio": (matching_count / required_total) if required_total > 0 else 0.0,
        "remote_provenance_ready": remote_provenance_ready,
        "linked_reports": linked_reports,
        **authority,
        **meta,
    }
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "## CI Current Run Consistency",
        "",
        f"- status: `{payload['status']}`",
        f"- source_run_id: `{meta['source_run_id']}`",
        f"- source_route: `{meta['source_route']}`",
        f"- authoritative_current_truth: `{payload['authoritative_current_truth']}`",
        f"- source_head_match: `{payload['source_head_match']}`",
        f"- analytics_only_pollution_count: `{pollution_count}`",
        "",
    ]
    if payload["status"] == "advisory":
        lines.append("### Advisory")
        lines.extend([f"- {item}" for item in payload["authority_reasons"]])
        lines.append("")
    if errors:
        lines.append("### Errors")
        lines.extend([f"- {item}" for item in errors])
        lines.append("")
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(str(out_json))
    print(str(out_md))
    if errors:
        print("❌ [ci-current-run] consistency check failed")
        for item in errors:
            print(f"- {item}")
        return 1
    if payload["status"] == "advisory":
        print("⚠️ [ci-current-run] consistency is internally coherent but not authoritative current truth")
        for item in payload["authority_reasons"]:
            print(f"- {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
