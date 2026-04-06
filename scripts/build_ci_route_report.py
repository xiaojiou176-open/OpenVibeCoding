#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ci_current_run_support import load_json, now_utc, resolve_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed/finalize/validate CI route reports.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    seed = subparsers.add_parser("seed")
    seed.add_argument("--output", required=True)
    seed.add_argument("--route-id", required=True)
    seed.add_argument("--trust-class", required=True, choices=("trusted", "untrusted"))
    seed.add_argument("--runner-class", required=True, choices=("github_hosted", "local"))
    seed.add_argument("--cloud-bootstrap-allowed", required=True, choices=("true", "false"))
    seed.add_argument("--github-run-id", required=True)
    seed.add_argument("--github-run-attempt", required=True)
    seed.add_argument("--github-sha", required=True)
    seed.add_argument("--github-ref", required=True)
    seed.add_argument("--github-event-name", required=True)
    seed.add_argument("--job-observed", action="append", default=[])
    seed.add_argument("--job-expected", action="append", default=[])

    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("--input", required=True)
    finalize.add_argument("--output", required=True)
    finalize.add_argument("--overall-status", required=True, choices=("pass", "fail"))
    finalize.add_argument("--cloud-bootstrap-used", required=True, choices=("true", "false"))
    finalize.add_argument("--job-observed", action="append", default=[])
    finalize.add_argument("--artifact-name", action="append", default=[])

    validate = subparsers.add_parser("validate")
    validate.add_argument("--input", required=True)
    validate.add_argument("--expected-route-id", required=True)
    validate.add_argument("--expected-trust-class", required=True, choices=("trusted", "untrusted"))
    validate.add_argument("--expected-runner-class", required=True, choices=("github_hosted", "local"))
    validate.add_argument("--expected-cloud-bootstrap-allowed", required=True, choices=("true", "false"))
    validate.add_argument("--forbid-cloud-bootstrap-used", action="store_true")
    validate.add_argument("--forbid-self-hosted-artifacts", action="store_true")
    return parser.parse_args()


def _bool_str(value: str) -> bool:
    return value.strip().lower() == "true"


def _write(output: Path, payload: dict[str, Any]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path = output.with_suffix(".md")
    lines = [
        "## CI Route Report",
        "",
        f"- route_id: `{payload['route_id']}`",
        f"- overall_status: `{payload['overall_status']}`",
        f"- trust_class: `{payload['trust_class']}`",
        f"- runner_class: `{payload['runner_class']}`",
        f"- github_run_id: `{payload['github_run_id']}`",
        f"- github_event_name: `{payload['github_event_name']}`",
        f"- cloud_bootstrap_allowed: `{payload['cloud_bootstrap_allowed']}`",
        f"- cloud_bootstrap_used: `{payload['cloud_bootstrap_used']}`",
        "",
        "### Jobs Observed",
    ]
    if payload["jobs_observed"]:
        lines.extend([f"- `{item}`" for item in payload["jobs_observed"]])
    else:
        lines.append("- none")
    lines.extend(["", "### Artifact Names"])
    if payload["artifact_names"]:
        lines.extend([f"- `{item}`" for item in payload["artifact_names"]])
    else:
        lines.append("- none")
    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")


def command_seed(args: argparse.Namespace) -> int:
    payload = {
        "report_type": "cortexpilot_ci_route_report",
        "generated_at": now_utc(),
        "route_id": args.route_id,
        "trust_class": args.trust_class,
        "runner_class": args.runner_class,
        "cloud_bootstrap_allowed": _bool_str(args.cloud_bootstrap_allowed),
        "cloud_bootstrap_used": False,
        "github_run_id": args.github_run_id,
        "github_run_attempt": args.github_run_attempt,
        "github_sha": args.github_sha,
        "github_ref": args.github_ref,
        "github_event_name": args.github_event_name,
        "jobs_expected": sorted(dict.fromkeys(args.job_expected)),
        "jobs_observed": sorted(dict.fromkeys(args.job_observed)),
        "artifact_names": [],
        "overall_status": "seeded",
    }
    output = resolve_path(args.output)
    _write(output, payload)
    print(str(output))
    return 0


def command_finalize(args: argparse.Namespace) -> int:
    input_path = resolve_path(args.input)
    payload = load_json(input_path, label="ci route report")
    payload["generated_at"] = now_utc()
    payload["overall_status"] = args.overall_status
    payload["cloud_bootstrap_used"] = _bool_str(args.cloud_bootstrap_used)
    payload["jobs_observed"] = sorted(
        dict.fromkeys([*(payload.get("jobs_observed") or []), *args.job_observed])
    )
    payload["artifact_names"] = sorted(
        dict.fromkeys([*(payload.get("artifact_names") or []), *args.artifact_name])
    )
    output = resolve_path(args.output)
    _write(output, payload)
    print(str(output))
    return 0


def command_validate(args: argparse.Namespace) -> int:
    payload = load_json(resolve_path(args.input), label="ci route report")
    errors: list[str] = []
    if payload.get("report_type") != "cortexpilot_ci_route_report":
        errors.append("report_type drift")
    if payload.get("route_id") != args.expected_route_id:
        errors.append(f"route_id mismatch: {payload.get('route_id')} != {args.expected_route_id}")
    if payload.get("trust_class") != args.expected_trust_class:
        errors.append("trust_class mismatch")
    if payload.get("runner_class") != args.expected_runner_class:
        errors.append("runner_class mismatch")
    if bool(payload.get("cloud_bootstrap_allowed")) != _bool_str(args.expected_cloud_bootstrap_allowed):
        errors.append("cloud_bootstrap_allowed mismatch")
    if args.forbid_cloud_bootstrap_used and bool(payload.get("cloud_bootstrap_used")):
        errors.append("cloud_bootstrap_used unexpectedly true")
    artifact_names = payload.get("artifact_names") or []
    if args.forbid_self_hosted_artifacts and any("self-hosted" in str(item) for item in artifact_names):
        errors.append("self-hosted artifact name detected on low-priv route")
    for field in ("github_run_id", "github_run_attempt", "github_sha", "github_ref", "github_event_name"):
        if not str(payload.get(field) or "").strip():
            errors.append(f"missing workflow metadata: {field}")
    if not artifact_names:
        errors.append("artifact_names empty")
    if errors:
        print("❌ [ci-route-report] validation failed")
        for item in errors:
            print(f"- {item}")
        return 1
    print(f"✅ [ci-route-report] validation passed: {resolve_path(args.input)}")
    return 0


def main() -> int:
    args = parse_args()
    if args.command == "seed":
        return command_seed(args)
    if args.command == "finalize":
        return command_finalize(args)
    return command_validate(args)


if __name__ == "__main__":
    raise SystemExit(main())
