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
    display_path,
    file_mtime_iso,
    load_source_manifest,
    manifest_expected_files,
    manifest_required_slices,
    manifest_route_report_path,
    manifest_slice_summary_paths,
    now_utc,
    source_metadata,
)


OUT_DIR = ROOT / ".runtime-cache" / "cortexpilot" / "reports" / "ci" / "artifact_index"
TARGETS = [
    ROOT / ".runtime-cache" / "test_output",
    ROOT / ".runtime-cache" / "logs",
    ROOT / ".runtime-cache" / "cortexpilot" / "release",
    ROOT / ".runtime-cache" / "cortexpilot" / "reports",
]


def _iter_files(base: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    if not base.exists():
        return rows
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        rows.append(
            {
                "path": display_path(path),
                "size_bytes": path.stat().st_size,
                "modified_at": file_mtime_iso(path),
            }
        )
    return rows


def _current_run_groups(source_manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    groups: dict[str, list[dict[str, object]]] = {}
    pollution = 0
    excluded = {path.resolve() for path in analytics_exclusion_paths(source_manifest)}
    for group_name, path in manifest_expected_files(source_manifest):
        if not path.is_file():
            continue
        row = {
            "path": display_path(path),
            "size_bytes": path.stat().st_size,
            "modified_at": file_mtime_iso(path),
        }
        groups.setdefault(group_name, []).append(row)
        if path.resolve() in excluded:
            pollution += 1
    payload = [
        {
            "group": name,
            "file_count": len(rows),
            "files": rows,
        }
        for name, rows in sorted(groups.items())
    ]
    return payload, pollution


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build CI artifact index and current-run index.")
    parser.add_argument(
        "--source-manifest",
        default="",
        help="Optional current-run source manifest path. Defaults to repo standard path.",
    )
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    parser.add_argument("--allow-local-advisory", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    groups = []
    total_files = 0
    for target in TARGETS:
        files = _iter_files(target)
        total_files += len(files)
        groups.append(
            {
                "root": str(target.relative_to(ROOT)),
                "exists": target.exists(),
                "file_count": len(files),
                "files": files,
            }
        )

    advisory_local_only = False
    try:
        source_manifest = load_source_manifest(args.source_manifest or None)
        source_meta = source_metadata(source_manifest)
        required_slices = manifest_required_slices(source_manifest)
        slice_paths = manifest_slice_summary_paths(source_manifest)
        has_slice_summaries = all(
            name in slice_paths and slice_paths[name].is_file() for name in required_slices
        )
        route_report_exists = bool(
            manifest_route_report_path(source_manifest) and manifest_route_report_path(source_manifest).is_file()
        )
        current_groups, pollution_count = _current_run_groups(source_manifest)
        current_total = sum(group["file_count"] for group in current_groups)
    except Exception as exc:  # noqa: BLE001
        if not args.allow_local_advisory:
            raise SystemExit(f"❌ [ci-artifact-index] current-run source manifest required: {exc}") from exc
        advisory_local_only = True
        source_manifest = {}
        source_meta = {
            "source_run_id": "local-advisory",
            "source_run_attempt": "",
            "source_sha": "",
            "source_ref": "",
            "source_event": "local",
            "source_route": "local-advisory",
            "source_trust_class": "trusted",
            "source_runner_class": "local",
        }
        required_slices = []
        has_slice_summaries = False
        route_report_exists = False
        current_groups = []
        pollution_count = 0
        current_total = 0
    authority = current_truth_authority(source_manifest) if source_manifest else {
        "current_head_sha": "",
        "source_head_match": False,
        "authoritative_current_truth": False,
        "advisory_local_only": True,
        "authority_level": "advisory",
        "authority_reasons": ["missing_source_manifest"],
    }

    artifact_index = {
        "report_type": "cortexpilot_ci_artifact_index",
        "generated_at": now_utc(),
        "authoritative": bool(authority["authoritative_current_truth"]),
        "advisory_local_only": advisory_local_only,
        **authority,
        "total_files": total_files,
        "groups": groups,
        **source_meta,
    }
    current_run_index = {
        "report_type": "cortexpilot_ci_current_run_index",
        "generated_at": artifact_index["generated_at"],
        "authoritative": bool(authority["authoritative_current_truth"]),
        "advisory_local_only": advisory_local_only,
        **authority,
        "freshness_window_sec": int(source_manifest.get("freshness_window_sec") or 0),
        "required_slice_summaries": required_slices,
        "has_slice_summaries": has_slice_summaries,
        "route_report_exists": route_report_exists,
        "analytics_only_pollution_count": pollution_count,
        "total_files": current_total,
        "groups": current_groups,
        **source_meta,
    }
    verdict = {
        "report_type": "cortexpilot_ci_verdict",
        "generated_at": artifact_index["generated_at"],
        "authoritative": bool(authority["authoritative_current_truth"]),
        "advisory_local_only": advisory_local_only,
        **authority,
        "artifact_groups_present": [g["root"] for g in groups if g["exists"]],
        "total_files": total_files,
        "current_run_file_count": current_total,
        "has_slice_summaries": has_slice_summaries,
        "analytics_only_pollution_count": pollution_count,
        "route_report_exists": route_report_exists,
        **source_meta,
    }

    (out_dir / "artifact_index.json").write_text(
        json.dumps(artifact_index, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (out_dir / "current_run_index.json").write_text(
        json.dumps(current_run_index, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (out_dir / "verdict.json").write_text(
        json.dumps(verdict, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (out_dir / "summary.md").write_text(
        "\n".join(
            [
                "## CI Artifact Index",
                "",
                f"- authoritative: `{bool(authority['authoritative_current_truth'])}`",
                f"- advisory_local_only: `{advisory_local_only}`",
                f"- authority_level: `{authority['authority_level']}`",
                f"- source_head_match: `{authority['source_head_match']}`",
                f"- source_run_id: `{source_meta['source_run_id']}`",
                f"- source_route: `{source_meta['source_route']}`",
                f"- total_files: `{total_files}`",
                f"- current_run_file_count: `{current_total}`",
                f"- has_slice_summaries: `{has_slice_summaries}`",
                f"- route_report_exists: `{route_report_exists}`",
                f"- analytics_only_pollution_count: `{pollution_count}`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(str(out_dir / "artifact_index.json"))
    print(str(out_dir / "current_run_index.json"))
    print(str(out_dir / "verdict.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
