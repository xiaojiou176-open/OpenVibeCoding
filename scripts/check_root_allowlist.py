#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "configs" / "root_allowlist.json"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _top_level_entries(root: Path) -> list[str]:
    return sorted(item.name for item in root.iterdir())


def main() -> int:
    parser = argparse.ArgumentParser(description="Enforce repository root allowlist policy.")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    parser.add_argument("--mode", choices=("authoritative",), default="authoritative")
    args = parser.parse_args()

    policy = _load_json(Path(args.policy))
    tracked_allowed = set(policy.get("tracked_allowed", []))
    local_allowed = set(policy.get("local_allowed", []))
    compatibility_allowed = set(policy.get("compatibility_allowed", []))
    forbidden_generated = set(policy.get("forbidden_generated", []))

    errors: list[str] = []
    warnings: list[str] = []
    entries = _top_level_entries(ROOT)
    tracked_top_level = {path.split("/", 1)[0] for path in (ROOT / ".git").exists() and [] or []}
    try:
        import subprocess

        result = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files"],
            check=True,
            capture_output=True,
            text=True,
        )
        tracked_top_level = {
            line.split("/", 1)[0]
            for line in result.stdout.splitlines()
            if line.strip() and (ROOT / line.split("/", 1)[0]).exists()
        }
    except Exception:
        tracked_top_level = set()

    for entry in entries:
        if entry in forbidden_generated:
            errors.append(f"forbidden top-level entry present: {entry}")
            continue
        if entry in tracked_allowed or entry in local_allowed:
            continue
        if entry in compatibility_allowed:
            errors.append(f"compatibility top-level entry should be migrated away: {entry}")
            continue
        if entry in tracked_top_level:
            errors.append(f"tracked top-level entry not in allowlist: {entry}")
        else:
            errors.append(f"local top-level entry not declared in allowlist: {entry}")

    for tracked in sorted(tracked_top_level):
        if tracked not in tracked_allowed and tracked not in local_allowed and tracked not in compatibility_allowed:
            errors.append(f"tracked top-level surface missing from policy: {tracked}")

    if warnings:
        print("⚠️ [root-allowlist] warnings:")
        for item in warnings:
            print(f"- {item}")

    if errors:
        print("❌ [root-allowlist] violations:")
        for item in sorted(set(errors)):
            print(f"- {item}")
        return 1

    print("✅ [root-allowlist] policy satisfied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
