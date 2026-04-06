#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ALLOWED_TIERS = {"core", "profile", "advanced", "deprecated"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate env tier mapping (prefix + overrides) against registry.",
        epilog="Example: python3 scripts/check_env_tiers.py",
    )
    parser.add_argument(
        "--registry",
        default="configs/env.registry.json",
        help="Path to env registry JSON (default: configs/env.registry.json)",
    )
    parser.add_argument(
        "--tiers-config",
        default="configs/env_tiers.json",
        help="Path to env tiers JSON (default: configs/env_tiers.json)",
    )
    return parser.parse_args()


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"[FAIL] file not found: {path}")
        raise SystemExit(1)
    except json.JSONDecodeError as exc:
        print(f"[FAIL] invalid json: {path} ({exc})")
        raise SystemExit(1)


def resolve_tier(name: str, prefix_rules: list[dict], overrides: dict[str, str], default_tier: str | None) -> str | None:
    override = overrides.get(name)
    if override:
        return override

    for rule in prefix_rules:
        prefix = str(rule.get("prefix", ""))
        tier = str(rule.get("tier", ""))
        if not prefix or not tier:
            continue
        exact = bool(rule.get("exact", False))
        if (exact and name == prefix) or (not exact and name.startswith(prefix)):
            return tier

    return default_tier


def main() -> int:
    args = parse_args()
    registry_path = Path(args.registry)
    tiers_path = Path(args.tiers_config)

    registry = load_json(registry_path)
    tiers_cfg = load_json(tiers_path)

    issues: list[str] = []

    if not isinstance(registry, list):
        issues.append(f"registry must be a JSON array: {registry_path}")
        registry = []

    if not isinstance(tiers_cfg, dict):
        issues.append(f"tiers config must be a JSON object: {tiers_path}")
        tiers_cfg = {}

    declared_tiers = tiers_cfg.get("tiers", [])
    default_tier = tiers_cfg.get("default_tier")
    prefix_rules = tiers_cfg.get("prefix_rules", [])
    overrides = tiers_cfg.get("overrides", {})

    if not isinstance(declared_tiers, list) or not all(isinstance(x, str) for x in declared_tiers):
        issues.append("tiers must be a string array")
        declared_tiers = []

    declared_tier_set = set(declared_tiers)
    missing_required = sorted(ALLOWED_TIERS - declared_tier_set)
    illegal_declared = sorted(declared_tier_set - ALLOWED_TIERS)
    if missing_required:
        issues.append(f"tiers missing required values: {', '.join(missing_required)}")
    if illegal_declared:
        issues.append(f"tiers contains illegal values: {', '.join(illegal_declared)}")

    if default_tier is not None and default_tier not in ALLOWED_TIERS:
        issues.append(f"default_tier is illegal: {default_tier}")

    if not isinstance(prefix_rules, list):
        issues.append("prefix_rules must be an array")
        prefix_rules = []

    if not isinstance(overrides, dict):
        issues.append("overrides must be an object")
        overrides = {}

    for idx, rule in enumerate(prefix_rules):
        if not isinstance(rule, dict):
            issues.append(f"prefix_rules[{idx}] must be an object")
            continue
        prefix = rule.get("prefix")
        tier = rule.get("tier")
        if not isinstance(prefix, str) or not prefix:
            issues.append(f"prefix_rules[{idx}].prefix must be a non-empty string")
        if tier not in ALLOWED_TIERS:
            issues.append(f"prefix_rules[{idx}].tier is illegal: {tier}")

    for key, tier in overrides.items():
        if not isinstance(key, str) or not key:
            issues.append(f"overrides contains invalid key: {key!r}")
        if tier not in ALLOWED_TIERS:
            issues.append(f"override tier illegal for {key}: {tier}")

    names: list[str] = []
    for idx, entry in enumerate(registry):
        if not isinstance(entry, dict):
            issues.append(f"registry[{idx}] must be an object")
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            issues.append(f"registry[{idx}].name must be a non-empty string")
            continue
        names.append(name)

    if issues:
        print("[FAIL] env tiers validation failed")
        for issue in issues:
            print(f"- {issue}")
        return 1

    tier_counter: Counter[str] = Counter()
    uncovered: list[str] = []
    illegal_resolved: list[tuple[str, str]] = []

    for name in names:
        tier = resolve_tier(name, prefix_rules, overrides, default_tier)
        if tier is None:
            uncovered.append(name)
            continue
        if tier not in ALLOWED_TIERS:
            illegal_resolved.append((name, tier))
            continue
        tier_counter[tier] += 1

    if uncovered or illegal_resolved:
        print("[FAIL] env tiers resolution failed")
        if uncovered:
            print(f"- uncovered keys: {len(uncovered)}")
            for key in uncovered[:20]:
                print(f"  - {key}")
            if len(uncovered) > 20:
                print(f"  ... and {len(uncovered) - 20} more")
        if illegal_resolved:
            print(f"- illegal resolved tiers: {len(illegal_resolved)}")
            for key, tier in illegal_resolved[:20]:
                print(f"  - {key}: {tier}")
            if len(illegal_resolved) > 20:
                print(f"  ... and {len(illegal_resolved) - 20} more")
        return 1

    total = len(names)
    covered = sum(tier_counter.values())
    print("[PASS] env tiers check passed")
    print(f"registry_total={total}")
    print(f"covered={covered}")
    print(f"uncovered={total - covered}")
    print("tier_counts:")
    for tier in ("core", "profile", "advanced", "deprecated"):
        print(f"- {tier}: {tier_counter.get(tier, 0)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
