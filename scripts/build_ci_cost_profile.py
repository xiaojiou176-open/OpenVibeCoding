#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ci_current_run_support import (
    current_truth_authority,
    load_json,
    load_source_manifest,
    manifest_expected_files,
    manifest_retry_telemetry_paths,
    manifest_slice_summary_paths,
    now_utc,
    source_metadata,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build current-run CI cost profile.")
    parser.add_argument("--source-manifest", default="")
    parser.add_argument(
        "--out-dir",
        default=".runtime-cache/openvibecoding/reports/ci/cost_profile",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_manifest = load_source_manifest(args.source_manifest or None)
    authority = current_truth_authority(source_manifest)
    slice_paths = manifest_slice_summary_paths(source_manifest)
    slice_rows = []
    total_duration = 0
    for name, path in sorted(slice_paths.items()):
        if not path.is_file():
            continue
        payload = load_json(path, label=f"ci slice summary {name}")
        duration = int(payload.get("duration_sec") or 0)
        total_duration += duration
        slice_rows.append(
            {
                "slice": payload.get("slice") or name,
                "status": payload.get("status"),
                "duration_sec": duration,
            }
        )
    total_bytes = 0
    for _, path in manifest_expected_files(source_manifest):
        if path.is_file():
            total_bytes += path.stat().st_size
    retry_rows = []
    retry_green = 0
    for path in manifest_retry_telemetry_paths(source_manifest):
        if not path.is_file():
            continue
        payload = load_json(path, label=f"ci retry telemetry {path.name}")
        retry_rows.append(payload)
        if payload.get("retry_green") is True:
            retry_green += 1
    payload = {
        "report_type": "openvibecoding_ci_cost_profile",
        "generated_at": now_utc(),
        "authoritative": bool(authority["authoritative_current_truth"]),
        **authority,
        "total_duration_sec": total_duration,
        "artifact_bytes_current_run": total_bytes,
        "slices": slice_rows,
        "retry_telemetry_count": len(retry_rows),
        "retry_green_count": retry_green,
        **source_metadata(source_manifest),
    }
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    report_json = out_dir / "cost_profile.json"
    report_md = out_dir / "cost_profile.md"
    report_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "## CI Cost Profile",
        "",
        f"- authoritative: `{bool(authority['authoritative_current_truth'])}`",
        f"- authority_level: `{authority['authority_level']}`",
        f"- source_head_match: `{authority['source_head_match']}`",
        f"- source_run_id: `{payload['source_run_id']}`",
        f"- source_route: `{payload['source_route']}`",
        f"- total_duration_sec: `{payload['total_duration_sec']}`",
        f"- artifact_bytes_current_run: `{payload['artifact_bytes_current_run']}`",
        f"- retry_green_count: `{payload['retry_green_count']}`",
        "",
        "### Slice Durations",
    ]
    if slice_rows:
        lines.extend(
            [f"- `{row['slice']}`: status=`{row['status']}`, duration_sec=`{row['duration_sec']}`" for row in slice_rows]
        )
    else:
        lines.append("- none")
    lines.append("")
    report_md.write_text("\n".join(lines), encoding="utf-8")
    print(str(report_json))
    print(str(report_md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
