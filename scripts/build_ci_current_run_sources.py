#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ci_current_run_support import now_utc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the CI current-run source manifest.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--route-id", required=True)
    parser.add_argument("--trust-class", required=True, choices=("trusted", "untrusted"))
    parser.add_argument("--runner-class", required=True, choices=("github_hosted", "local"))
    parser.add_argument("--cloud-bootstrap-allowed", required=True, choices=("true", "false"))
    parser.add_argument("--cloud-bootstrap-used", default="false", choices=("true", "false"))
    parser.add_argument("--github-run-id", required=True)
    parser.add_argument("--github-run-attempt", required=True)
    parser.add_argument("--github-sha", required=True)
    parser.add_argument("--github-ref", required=True)
    parser.add_argument("--github-event-name", required=True)
    parser.add_argument("--route-report", required=True)
    parser.add_argument("--artifact-name", action="append", default=[])
    parser.add_argument("--required-slice", action="append", default=[])
    parser.add_argument("--slice-summary", action="append", default=[])
    parser.add_argument("--report", action="append", default=[])
    parser.add_argument("--retry-telemetry", action="append", default=[])
    parser.add_argument("--analytics-exclusion", action="append", default=[])
    parser.add_argument("--freshness-window-sec", type=int, default=172800)
    return parser.parse_args()


def _as_bool(raw: str) -> bool:
    return raw.strip().lower() == "true"


def _parse_pairs(rows: list[str]) -> dict[str, str]:
    payload: dict[str, str] = {}
    for item in rows:
        if "=" not in item:
            raise SystemExit(f"invalid NAME=PATH pair: {item}")
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or not value:
            raise SystemExit(f"invalid NAME=PATH pair: {item}")
        payload[key] = value
    return payload


def _parse_exclusions(rows: list[str]) -> list[dict[str, object]]:
    payload = []
    for item in rows:
        if "=" in item:
            path, reason = item.split("=", 1)
            path = path.strip()
            reason = reason.strip() or "analytics_only"
        else:
            path = item.strip()
            reason = "analytics_only"
        if not path:
            raise SystemExit(f"invalid analytics exclusion: {item}")
        payload.append(
            {
                "path": path,
                "release_truth_eligible": False,
                "reason": reason,
            }
        )
    return payload


def main() -> int:
    args = parse_args()
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    authority_hint = "advisory" if args.route_id.strip() == "local-advisory" else "authoritative_candidate"
    payload = {
        "report_type": "openvibecoding_ci_current_run_source_manifest",
        "schema_version": 1,
        "generated_at": now_utc(),
        "authority_hint": authority_hint,
        "source_run_id": args.github_run_id,
        "source_run_attempt": args.github_run_attempt,
        "source_sha": args.github_sha,
        "source_ref": args.github_ref,
        "source_event": args.github_event_name,
        "source_route": args.route_id,
        "source_trust_class": args.trust_class,
        "source_runner_class": args.runner_class,
        "cloud_bootstrap_allowed": _as_bool(args.cloud_bootstrap_allowed),
        "cloud_bootstrap_used": _as_bool(args.cloud_bootstrap_used),
        "freshness_window_sec": args.freshness_window_sec,
        "artifact_names": sorted(dict.fromkeys(args.artifact_name)),
        "route_report": args.route_report,
        "required_slice_summaries": sorted(dict.fromkeys(args.required_slice)),
        "slice_summaries": _parse_pairs(args.slice_summary),
        "reports": _parse_pairs(args.report),
        "retry_telemetry": list(dict.fromkeys(args.retry_telemetry)),
        "analytics_exclusions": _parse_exclusions(args.analytics_exclusion),
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(str(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
