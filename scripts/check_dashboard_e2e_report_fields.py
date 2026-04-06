#!/usr/bin/env python3
"""Lightweight schema checks for dashboard real-E2E report payloads."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


COMMON_REQUIRED_FIELDS = (
    "scenario",
    "started_at",
    "api_base_url",
    "dashboard_base_url",
    "checks",
    "failed_checks",
    "status",
    "error",
)

VALID_STATUS = {"passed", "failed"}


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_common_fields(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in COMMON_REQUIRED_FIELDS:
        if field not in payload:
            errors.append(f"missing field: {field}")
    if "status" in payload and payload.get("status") not in VALID_STATUS:
        errors.append(f"invalid status: {payload.get('status')!r}")
    if "checks" in payload and not isinstance(payload.get("checks"), list):
        errors.append("field checks must be list")
    if "failed_checks" in payload and not isinstance(payload.get("failed_checks"), list):
        errors.append("field failed_checks must be list")
    return errors


def _validate_dashboard_artifacts(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    artifacts = payload.get("artifacts")
    if isinstance(artifacts, dict):
        required_artifacts = (
            "report_json",
            "network_json",
            "god_mode_screenshot",
            "diff_gate_screenshot",
            "run_detail_screenshot",
            "pm_screenshot",
            "search_screenshot",
        )
        for field in required_artifacts:
            if not _is_non_empty_string(artifacts.get(field)):
                errors.append(f"missing artifacts.{field}")
        return errors

    if _is_non_empty_string(payload.get("screenshot_path")) and _is_non_empty_string(payload.get("network_path")):
        return errors

    errors.append("missing dashboard artifacts: expected artifacts{} or screenshot_path+network_path")
    return errors


def validate_report(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return ["report must be a JSON object"]

    errors = _validate_common_fields(payload)
    errors.extend(_validate_dashboard_artifacts(payload))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate dashboard real-E2E report fields.")
    parser.add_argument("--report", required=True, help="Path to report JSON file.")
    args = parser.parse_args()

    report_path = Path(args.report)
    if not report_path.exists():
        print(f"❌ missing report file: {report_path}")
        return 1

    try:
        errors = validate_report(report_path)
    except Exception as exc:  # pragma: no cover - defensive
        print(f"❌ invalid report JSON: {exc}")
        return 1

    if errors:
        print("❌ dashboard report field check failed")
        for item in errors:
            print(f"- {item}")
        return 1

    print(f"✅ dashboard report field check passed: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
