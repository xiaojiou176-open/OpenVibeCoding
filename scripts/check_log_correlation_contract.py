#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / ".runtime-cache" / "test_output" / "governance" / "log_event_contract_report.json"


def _expected_correlation(payload: dict[str, object]) -> str:
    for field, correlation in (
        ("run_id", "run"),
        ("session_id", "session"),
        ("test_id", "test"),
        ("request_id", "request"),
        ("trace_id", "trace"),
    ):
        value = str(payload.get(field) or "").strip()
        if value:
            return correlation
    return "none"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate log correlation contract against fresh sample report.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    args = parser.parse_args()

    report = json.loads(Path(args.input).read_text(encoding="utf-8"))
    samples = report.get("samples", {})
    errors: list[str] = []
    for name, payload in samples.items():
        if not isinstance(payload, dict):
            errors.append(f"{name}: payload is not an object")
            continue
        lane = str(payload.get("lane") or "").strip()
        if not lane:
            errors.append(f"{name}: missing lane")
        correlation_kind = str(payload.get("correlation_kind") or "").strip()
        expected = _expected_correlation(payload)
        if correlation_kind != expected:
            errors.append(f"{name}: correlation_kind must be `{expected}`, got `{correlation_kind}`")

    if errors:
        print("❌ [log-correlation-contract] violations:")
        for item in errors:
            print(f"- {item}")
        return 1

    print("✅ [log-correlation-contract] correlation contract satisfied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
