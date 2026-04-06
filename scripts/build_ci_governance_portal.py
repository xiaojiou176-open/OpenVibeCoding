#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ci_current_run_support import (
    analytics_exclusion_paths,
    current_truth_authority,
    load_json,
    load_source_manifest,
    manifest_report_paths,
    now_utc,
    source_metadata,
    timestamp_to_iso,
)


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _report_meta(payload: dict[str, Any], *, path: Path) -> dict[str, Any]:
    generated_at = timestamp_to_iso(payload.get("generated_at"))
    return {
        "path": str(path),
        "exists": path.is_file(),
        "generated_at": generated_at,
        "source_run_id": str(payload.get("source_run_id") or ""),
        "source_route": str(payload.get("source_route") or ""),
        "source_event": str(payload.get("source_event") or ""),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build CI governance portal from current-run reports.")
    parser.add_argument("--source-manifest", default="")
    parser.add_argument("--out-dir", default=".runtime-cache/cortexpilot/reports/ci/portal")
    parser.add_argument("--allow-local-advisory", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    advisory_local_only = False
    try:
        source_manifest = load_source_manifest(args.source_manifest or None)
        meta = source_metadata(source_manifest)
        report_paths = manifest_report_paths(source_manifest)
    except Exception as exc:  # noqa: BLE001
        if not args.allow_local_advisory:
            raise SystemExit(f"❌ [ci-portal] current-run source manifest required: {exc}") from exc
        advisory_local_only = True
        source_manifest = {}
        meta = {
            "source_run_id": "local-advisory",
            "source_run_attempt": "",
            "source_sha": "",
            "source_ref": "",
            "source_event": "local",
            "source_route": "local-advisory",
            "source_trust_class": "trusted",
            "source_runner_class": "local",
        }
        report_paths = {}
    authority = current_truth_authority(source_manifest) if source_manifest else {
        "current_head_sha": "",
        "source_head_match": False,
        "authoritative_current_truth": False,
        "advisory_local_only": True,
        "authority_level": "advisory",
        "authority_reasons": ["missing_source_manifest"],
    }
    reports: dict[str, dict[str, Any]] = {}
    matching_count = 0
    required_total = 0
    for name in (
        "artifact_index_verdict",
        "current_run_index",
        "cost_profile",
        "runner_drift",
        "runner_health",
        "sbom",
        "slo",
        "provenance",
        "evidence_manifest",
    ):
        path = report_paths.get(name)
        if path is None:
            continue
        required_total += 1
        payload = _load(path)
        report_meta = _report_meta(payload, path=path)
        reports[name] = report_meta
        if (
            report_meta["exists"]
            and report_meta["generated_at"]
            and report_meta["source_run_id"] == meta["source_run_id"]
            and report_meta["source_route"] == meta["source_route"]
            and report_meta["source_event"] == meta["source_event"]
        ):
            matching_count += 1

    current_run_index_path = report_paths.get("current_run_index")
    pollution_count = 0
    if current_run_index_path and current_run_index_path.is_file():
        current_run_index = load_json(current_run_index_path, label="ci current run index")
        file_paths = {
            str(item.get("path") or "")
            for group in current_run_index.get("groups", [])
            if isinstance(group, dict)
            for item in group.get("files", [])
            if isinstance(item, dict)
        }
        pollution_count = sum(
            1
            for path in analytics_exclusion_paths(source_manifest)
            if str(path.relative_to(Path.cwd().resolve())) in file_paths
        )
        pollution_count = int(current_run_index.get("analytics_only_pollution_count") or pollution_count)

    provenance_payload = _load(report_paths.get("provenance", Path(".")))
    workflow = provenance_payload.get("workflow") if isinstance(provenance_payload.get("workflow"), dict) else {}
    remote_provenance_ready = all(
        str(workflow.get(key) or "").strip()
        for key in ("github_run_id", "github_run_attempt", "github_ref", "github_event_name")
    )

    fresh_ratio = (matching_count / required_total) if required_total > 0 else 0.0
    structurally_pass = required_total > 0 and matching_count == required_total and pollution_count == 0 and remote_provenance_ready
    overall_status = (
        "pass"
        if structurally_pass and authority["authoritative_current_truth"]
        else ("advisory" if structurally_pass else "fail")
    )
    payload = {
        "report_type": "cortexpilot_ci_governance_portal",
        "generated_at": now_utc(),
        "authoritative": bool(authority["authoritative_current_truth"]),
        "advisory_local_only": advisory_local_only,
        **authority,
        "overall": {
            "status": overall_status,
            "fresh_current_run_report_ratio": fresh_ratio,
            "analytics_only_pollution_count": pollution_count,
            "remote_provenance_ready": remote_provenance_ready,
        },
        "reports": reports,
        **meta,
    }
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "portal.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# CI Governance Portal",
        "",
        f"- authoritative: `{payload['authoritative']}`",
        f"- advisory_local_only: `{advisory_local_only}`",
        f"- authority_level: `{payload['authority_level']}`",
        f"- source_head_match: `{payload['source_head_match']}`",
        f"- source_run_id: `{meta['source_run_id']}`",
        f"- source_route: `{meta['source_route']}`",
        f"- status: `{overall_status}`",
        f"- fresh_current_run_report_ratio: `{fresh_ratio:.2f}`",
        f"- analytics_only_pollution_count: `{pollution_count}`",
        f"- remote_provenance_ready: `{remote_provenance_ready}`",
        "",
        "## Linked Reports",
    ]
    if payload["authority_reasons"]:
        lines.extend(["## Authority Notes", *[f"- {item}" for item in payload["authority_reasons"]], ""])
    for name, report_meta in sorted(reports.items()):
        lines.append(
            f"- `{name}`: exists=`{report_meta['exists']}`, generated_at=`{report_meta['generated_at']}`, "
            f"source_run_id=`{report_meta['source_run_id']}`, source_route=`{report_meta['source_route']}`, "
            f"source_event=`{report_meta['source_event']}`"
        )
    lines.append("")
    (out_dir / "portal.md").write_text("\n".join(lines), encoding="utf-8")
    print(str(out_dir / "portal.json"))
    print(str(out_dir / "portal.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
