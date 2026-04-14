#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ci_current_run_support import (
    current_truth_authority,
    load_json,
    load_source_manifest,
    manifest_report_paths,
    now_utc,
    source_metadata,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "configs" / "ci_governance_policy.json"
DEFAULT_DOCTOR_REPORT = ROOT / ".runtime-cache" / "test_output" / "ci_control_plane_doctor" / "report.json"
DEFAULT_RUNNER_DRIFT_REPORT = ROOT / ".runtime-cache" / "openvibecoding" / "reports" / "ci" / "runner_drift" / "report.json"


def _load(path: Path | None) -> dict:
    if path is None or not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build CI runner health/quarantine dashboard.")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    parser.add_argument("--source-manifest", default="")
    parser.add_argument("--out-dir", default=".runtime-cache/openvibecoding/reports/ci/runner_health")
    parser.add_argument("--allow-local-advisory", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    policy = json.loads(Path(args.policy).read_text(encoding="utf-8"))
    advisory_local_only = False
    try:
        source_manifest = load_source_manifest(args.source_manifest or None)
        report_paths = manifest_report_paths(source_manifest)
        meta = source_metadata(source_manifest)
    except Exception as exc:  # noqa: BLE001
        if not args.allow_local_advisory:
            raise SystemExit(f"❌ [ci-runner-health] current-run source manifest required: {exc}") from exc
        advisory_local_only = True
        source_manifest = {}
        report_paths = {}
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
    authority = current_truth_authority(source_manifest) if source_manifest else {
        "current_head_sha": "",
        "source_head_match": False,
        "authoritative_current_truth": False,
        "advisory_local_only": True,
        "authority_level": "advisory",
        "authority_reasons": ["missing_source_manifest"],
    }
    quarantine = policy["runner_quarantine"]

    doctor_path = report_paths.get("control_plane_doctor")
    if doctor_path is None and DEFAULT_DOCTOR_REPORT.is_file():
        doctor_path = DEFAULT_DOCTOR_REPORT
    drift_path = report_paths.get("runner_drift")
    if drift_path is None and DEFAULT_RUNNER_DRIFT_REPORT.is_file():
        drift_path = DEFAULT_RUNNER_DRIFT_REPORT

    doctor = _load(doctor_path)
    drift = _load(drift_path)
    slo = _load(report_paths.get("slo"))
    cost = _load(report_paths.get("cost_profile"))

    retry_green_count = int(cost.get("retry_green_count") or 0)
    slo_breach_count = len(slo.get("breaches") or [])
    doctor_checks = doctor.get("checks") if isinstance(doctor.get("checks"), dict) else {}
    doctor_failed = any(v is False for v in doctor_checks.values())
    drift_failed = drift.get("status") == "fail"
    quarantine_recommended = (
        (doctor_failed and quarantine.get("doctor_failure_blocking"))
        or (drift_failed and quarantine.get("drift_failure_blocking"))
        or retry_green_count >= int(quarantine.get("retry_green_count_blocking", 999999))
        or slo_breach_count >= int(quarantine.get("slo_breach_count_blocking", 999999))
    )
    payload = {
        "report_type": "openvibecoding_ci_runner_health_dashboard",
        "generated_at": now_utc(),
        "authoritative": bool(authority["authoritative_current_truth"]),
        "advisory_local_only": advisory_local_only,
        **authority,
        "doctor_failed": doctor_failed,
        "drift_failed": drift_failed,
        "retry_green_count": retry_green_count,
        "slo_breach_count": slo_breach_count,
        "quarantine_recommended": quarantine_recommended,
        **meta,
    }
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "health.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "health.md").write_text(
        "\n".join(
            [
                "## CI Runner Health",
                "",
                f"- authoritative: `{bool(authority['authoritative_current_truth'])}`",
                f"- advisory_local_only: `{advisory_local_only}`",
                f"- authority_level: `{authority['authority_level']}`",
                f"- source_head_match: `{authority['source_head_match']}`",
                f"- source_run_id: `{payload['source_run_id']}`",
                f"- source_route: `{payload['source_route']}`",
                f"- doctor_failed: `{doctor_failed}`",
                f"- drift_failed: `{drift_failed}`",
                f"- retry_green_count: `{retry_green_count}`",
                f"- slo_breach_count: `{slo_breach_count}`",
                f"- quarantine_recommended: `{quarantine_recommended}`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(str(out_dir / "health.json"))
    print(str(out_dir / "health.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
