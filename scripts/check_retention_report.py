#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / ".runtime-cache" / "openvibecoding" / "reports" / "retention_report.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate runtime retention report contract.")
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    args = parser.parse_args()

    report_path = Path(args.report).expanduser().resolve()
    if not report_path.exists():
        print(f"❌ [retention-report] missing report: {report_path}")
        return 1

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    required_root_fields = {
        "schema_version",
        "generated_at",
        "applied",
        "cleanup_scope",
        "candidates",
        "cache_namespace_summary",
        "log_lane_summary",
        "space_bridge",
        "test_output_visibility",
        "result",
    }
    missing_root = sorted(required_root_fields - set(payload))
    if missing_root:
        errors.append(f"missing root fields: {', '.join(missing_root)}")

    cleanup_scope = payload.get("cleanup_scope")
    if not isinstance(cleanup_scope, dict):
        errors.append("cleanup_scope must be an object")
    else:
        for field in ("labels", "included_roots", "observed_roots", "protected_live_roots", "excluded_examples"):
            if field not in cleanup_scope:
                errors.append(f"cleanup_scope missing `{field}`")
        observed_roots = cleanup_scope.get("observed_roots")
        if isinstance(observed_roots, dict):
            if "test_output" not in observed_roots:
                errors.append("cleanup_scope.observed_roots missing `test_output`")
        else:
            errors.append("cleanup_scope.observed_roots must be an object")

    summary = payload.get("cache_namespace_summary")
    if not isinstance(summary, dict):
        errors.append("cache_namespace_summary must be an object")
    else:
        for field in ("canonical_namespaces", "candidate_bucket_counts", "non_contract_buckets"):
            if field not in summary:
                errors.append(f"cache_namespace_summary missing `{field}`")

    log_lane_summary = payload.get("log_lane_summary")
    if not isinstance(log_lane_summary, dict):
        errors.append("log_lane_summary must be an object")
    else:
        for lane in ("runtime", "error", "access", "e2e", "ci", "governance"):
            lane_payload = log_lane_summary.get(lane)
            if not isinstance(lane_payload, dict):
                errors.append(f"log_lane_summary missing lane object: {lane}")
                continue
            for field in (
                "path",
                "file_count",
                "total_size_bytes",
                "newest_mtime",
                "oldest_mtime",
                "rotation_headroom_bytes_estimate",
                "max_file_size_bytes",
            ):
                if field not in lane_payload:
                    errors.append(f"log_lane_summary.{lane} missing `{field}`")

    space_bridge = payload.get("space_bridge")
    if not isinstance(space_bridge, dict):
        errors.append("space_bridge must be an object")
    else:
        for field in (
            "path",
            "exists",
            "latest_space_audit_generated_at",
            "repo_internal_total_bytes",
            "repo_external_related_total_bytes",
            "shared_observation_total_bytes",
        ):
            if field not in space_bridge:
                errors.append(f"space_bridge missing `{field}`")

    test_output_visibility = payload.get("test_output_visibility")
    if not isinstance(test_output_visibility, dict):
        errors.append("test_output_visibility must be an object")
    else:
        for field in ("path", "exists", "total_files", "total_size_bytes", "root_level_files", "bucket_file_counts"):
            if field not in test_output_visibility:
                errors.append(f"test_output_visibility missing `{field}`")
        if isinstance(test_output_visibility.get("root_level_files"), list):
            for item in test_output_visibility["root_level_files"]:
                if not isinstance(item, str):
                    errors.append("test_output_visibility.root_level_files must contain strings")
                    break
            if test_output_visibility["root_level_files"]:
                errors.append(
                    "test_output_visibility.root_level_files must be empty once test_output namespace discipline is enabled"
                )
        else:
            errors.append("test_output_visibility.root_level_files must be a list")
        if not isinstance(test_output_visibility.get("bucket_file_counts"), dict):
            errors.append("test_output_visibility.bucket_file_counts must be an object")

    result = payload.get("result")
    if not isinstance(result, dict):
        errors.append("result must be an object")
    else:
        if "removed_total" not in result:
            errors.append("result missing `removed_total`")
        if "removed" not in result:
            errors.append("result missing `removed`")

    if errors:
        print("❌ [retention-report] violations:")
        for item in errors:
            print(f"- {item}")
        return 1

    print(f"✅ [retention-report] report satisfied: {report_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
