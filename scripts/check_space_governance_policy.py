#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "orchestrator" / "src"))

from cortexpilot_orch.runtime.space_governance import load_space_governance_policy
DEFAULT_POLICY = ROOT / "configs" / "space_governance_policy.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the CortexPilot space governance policy.")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_space_governance_policy(Path(args.policy).expanduser().resolve())
    print("✅ [space-governance-policy] policy satisfied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
