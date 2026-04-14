#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "configs" / "ci_governance_policy.json"
DEFAULT_COST_PROFILE = ROOT / ".runtime-cache" / "openvibecoding" / "reports" / "ci" / "cost_profile" / "cost_profile.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail closed when retry-green policy is violated.")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    parser.add_argument("--cost-profile", default=str(DEFAULT_COST_PROFILE))
    args = parser.parse_args()
    policy = json.loads(Path(args.policy).read_text(encoding="utf-8"))
    payload = json.loads(Path(args.cost_profile).read_text(encoding="utf-8"))
    max_retry_green_count = int(policy["retry_green_policy"]["max_retry_green_count"])
    retry_green_count = int(payload.get("retry_green_count") or 0)
    if retry_green_count > max_retry_green_count:
        print(
            f"❌ [ci-retry-green-policy] retry_green_count={retry_green_count} exceeds max_retry_green_count={max_retry_green_count}"
        )
        return 1
    print(
        f"✅ [ci-retry-green-policy] retry_green_count={retry_green_count} within max_retry_green_count={max_retry_green_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
