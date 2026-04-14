#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ci_current_run_support import (
    current_truth_authority,
    load_json,
    load_source_manifest,
    manifest_required_slices,
    manifest_slice_summary_paths,
    now_utc,
    source_metadata,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "configs" / "ci_governance_policy.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build CI SLO dashboard from current-run source manifest.")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    parser.add_argument("--source-manifest", default="")
    parser.add_argument("--out-dir", default=".runtime-cache/openvibecoding/reports/ci/slo")
    parser.add_argument("--mode", choices=("strict", "report"), default="report")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    policy = json.loads(Path(args.policy).read_text(encoding="utf-8"))
    source_manifest = load_source_manifest(args.source_manifest or None)
    authority = current_truth_authority(source_manifest)
    slice_paths = manifest_slice_summary_paths(source_manifest)
    required_slices = manifest_required_slices(source_manifest)
    rows = []
    breaches = []
    missing_required = []
    for name, threshold in policy["slice_slo_sec"].items():
        path = slice_paths.get(name)
        duration = None
        status = "missing"
        if path and path.is_file():
            payload = load_json(path, label=f"ci slice summary {name}")
            duration = int(payload.get("duration_sec") or 0)
            status = str(payload.get("status") or "unknown")
            if duration > int(threshold):
                breaches.append(f"{name}: duration {duration}s > slo {threshold}s")
        elif name in required_slices:
            missing_required.append(name)
        rows.append({"slice": name, "status": status, "duration_sec": duration, "slo_sec": int(threshold)})
    payload = {
        "report_type": "openvibecoding_ci_slo_dashboard",
        "generated_at": now_utc(),
        "authoritative": bool(authority["authoritative_current_truth"]),
        **authority,
        "mode": args.mode,
        "status": "pass" if not breaches and not missing_required else "fail",
        "breaches": breaches,
        "missing_required_slices": missing_required,
        "slices": rows,
        **source_metadata(source_manifest),
    }
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "dashboard.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "dashboard.md").write_text(
        "\n".join(
            [
                "## CI SLO Dashboard",
                "",
                f"- status: **{payload['status']}**",
                f"- authoritative: `{bool(authority['authoritative_current_truth'])}`",
                f"- authority_level: `{authority['authority_level']}`",
                f"- source_head_match: `{authority['source_head_match']}`",
                f"- source_route: `{payload['source_route']}`",
                "",
            ]
            + [f"- `{row['slice']}`: duration=`{row['duration_sec']}`, slo=`{row['slo_sec']}`, status=`{row['status']}`" for row in rows]
            + [""]
            + [f"- missing_required: {item}" for item in missing_required]
            + [f"- breach: {item}" for item in breaches]
            + [""]
        ),
        encoding="utf-8",
    )
    print(str(out_dir / "dashboard.json"))
    print(str(out_dir / "dashboard.md"))
    if payload["status"] == "fail" and args.mode == "strict":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
