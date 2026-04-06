#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "configs" / "ci_governance_policy.json"


ACTION_RE = re.compile(r"uses:\s*([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)@([0-9a-f]{40})")
URL_RE = re.compile(r"https://([A-Za-z0-9.-]+)/")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate CI supply-chain allowlists.")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    args = parser.parse_args()
    policy = json.loads(Path(args.policy).read_text(encoding="utf-8"))
    allowed_action_repos = set(policy["supply_chain"]["allowed_action_repos"])
    allowed_download_hosts = set(policy["supply_chain"]["allowed_download_hosts"])

    errors: list[str] = []
    for workflow in (ROOT / ".github" / "workflows").glob("*.yml"):
        text = workflow.read_text(encoding="utf-8")
        for match in ACTION_RE.finditer(text):
            repo = match.group(1)
            if repo not in allowed_action_repos:
                errors.append(f"{workflow}: unallowlisted action repo `{repo}`")

    dockerfile = ROOT / "infra" / "ci" / "Dockerfile.core"
    for host in URL_RE.findall(dockerfile.read_text(encoding="utf-8")):
        if host not in allowed_download_hosts:
            errors.append(f"{dockerfile}: unallowlisted download host `{host}`")

    if errors:
        print("❌ [ci-supply-chain-policy] violations:")
        for item in errors:
            print(f"- {item}")
        return 1
    print("✅ [ci-supply-chain-policy] supply-chain allowlists satisfied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
