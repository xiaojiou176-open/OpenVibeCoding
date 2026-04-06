#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ALLOWED_TIERS = ("core", "profile", "advanced", "deprecated")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate env governance observability report (json + markdown).",
        epilog=(
            "Example: python3 scripts/report_env_governance.py "
            "--registry configs/env.registry.json --tiers-config configs/env_tiers.json"
        ),
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
    parser.add_argument(
        "--output-dir",
        default=".runtime-cache/test_output/env_governance",
        help="Output directory for report artifacts",
    )
    parser.add_argument(
        "--max-deprecated-count",
        type=int,
        default=10,
        help="Deprecated-tier key count budget for auditable trend status",
    )
    parser.add_argument(
        "--max-deprecated-ratio",
        type=float,
        default=0.03,
        help="Deprecated-tier key ratio budget for auditable trend status",
    )
    return parser.parse_args()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"[FAIL] file not found: {path}")
        raise SystemExit(1)
    except json.JSONDecodeError as exc:
        print(f"[FAIL] invalid json: {path} ({exc})")
        raise SystemExit(1)


def resolve_tier(
    name: str,
    prefix_rules: list[dict[str, Any]],
    overrides: dict[str, str],
    default_tier: str | None,
) -> str | None:
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


def collect_report(
    registry: list[dict[str, Any]],
    tiers_cfg: dict[str, Any],
    *,
    max_deprecated_count: int,
    max_deprecated_ratio: float,
) -> dict[str, Any]:
    prefix_rules = tiers_cfg.get("prefix_rules", [])
    overrides = tiers_cfg.get("overrides", {})
    default_tier = tiers_cfg.get("default_tier")

    if not isinstance(prefix_rules, list):
        prefix_rules = []
    if not isinstance(overrides, dict):
        overrides = {}

    tier_counter: Counter[str] = Counter()
    unresolved_keys: list[str] = []
    deprecated_keys: list[str] = []
    timeout_keys: list[str] = []
    registry_names: set[str] = set()
    mergeable_candidates: list[dict[str, str]] = []
    deletable_candidates: list[dict[str, str]] = []
    single_consumer_count = 0
    valid_entries = 0

    for entry in registry:
        if isinstance(entry, dict):
            name = entry.get("name")
            if isinstance(name, str) and name:
                registry_names.add(name)

    def timeout_family_key(name: str) -> str | None:
        if not name.endswith("_TIMEOUT_SEC"):
            return None
        if not name.startswith("CORTEXPILOT_CI_STEP"):
            return None
        base = name[: -len("_TIMEOUT_SEC")]
        parts = base.split("_")
        # CORTEXPILOT_CI_STEP8_4_INVENTORY -> CORTEXPILOT_CI_STEP8_4_TIMEOUT_SEC
        # CORTEXPILOT_CI_STEP8_2 -> CORTEXPILOT_CI_STEP8_TIMEOUT_SEC
        if len(parts) >= 5 and parts[4].isdigit():
            return "_".join(parts[:5]) + "_TIMEOUT_SEC"
        if len(parts) >= 4:
            return "_".join(parts[:4]) + "_TIMEOUT_SEC"
        return None

    def is_convergence_implemented(entry: dict[str, Any], family_key: str) -> bool:
        target = entry.get("convergence_target")
        status = str(entry.get("convergence_status") or "").strip().lower()
        if not isinstance(target, str) or not target:
            return False
        if target != family_key:
            return False
        return status in {"implemented", "merged", "done"}

    def has_implemented_convergence_target(entry: dict[str, Any]) -> bool:
        target = entry.get("convergence_target")
        status = str(entry.get("convergence_status") or "").strip().lower()
        if not isinstance(target, str) or not target:
            return False
        if target not in registry_names:
            return False
        return status in {"implemented", "merged", "done"}

    for entry in registry:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            continue
        valid_entries += 1

        consumers = entry.get("consumers")
        if isinstance(consumers, list) and len(consumers) == 1:
            single_consumer_count += 1

        if "TIMEOUT" in name:
            timeout_keys.append(name)
            family_key = timeout_family_key(name)
            if (
                family_key
                and family_key != name
                and family_key in registry_names
                and not is_convergence_implemented(entry, family_key)
            ):
                mergeable_candidates.append(
                    {
                        "name": name,
                        "target_group_key": family_key,
                        "reason": "timeout leaf key can be converged to existing timeout group key",
                    }
                )

        resolved = resolve_tier(name, prefix_rules, overrides, default_tier)
        if resolved is None or resolved not in ALLOWED_TIERS:
            unresolved_keys.append(name)
            continue
        tier_counter[resolved] += 1
        if resolved == "deprecated":
            deprecated_keys.append(name)
            deletable_candidates.append(
                {
                    "name": name,
                    "reason": "deprecated tier key; candidate for removal after migration window",
                }
            )
            continue
        if (
            isinstance(consumers, list)
            and len(consumers) == 1
            and resolved in {"profile", "advanced"}
            and not has_implemented_convergence_target(entry)
        ):
            deletable_candidates.append(
                {
                    "name": name,
                    "reason": "single-consumer non-core key; candidate for consolidation into group/alias key",
                }
            )

    total = valid_entries
    resolved_total = sum(tier_counter.values())
    single_consumer_ratio = (single_consumer_count / total) if total else 0.0
    deprecated_count = len(deprecated_keys)
    deprecated_ratio = (deprecated_count / total) if total else 0.0
    count_ok = deprecated_count <= max_deprecated_count
    ratio_ok = deprecated_ratio <= max_deprecated_ratio

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "registry_entries": len(registry),
            "default_tier": default_tier,
            "declared_tiers": tiers_cfg.get("tiers", []),
        },
        "metrics": {
            "total": total,
            "tier_distribution": {tier: tier_counter.get(tier, 0) for tier in ALLOWED_TIERS},
            "resolved_total": resolved_total,
            "unresolved_total": len(unresolved_keys),
            "single_consumer": {
                "count": single_consumer_count,
                "ratio": round(single_consumer_ratio, 6),
            },
            "timeout_class": {
                "count": len(timeout_keys),
                "keys": sorted(timeout_keys),
            },
            "deprecated": {
                "count": deprecated_count,
                "ratio": round(deprecated_ratio, 6),
                "keys": sorted(deprecated_keys),
            },
            "deprecated_budget": {
                "max_count": max_deprecated_count,
                "max_ratio": max_deprecated_ratio,
                "count_ok": count_ok,
                "ratio_ok": ratio_ok,
                "status": "ok" if (count_ok and ratio_ok) else "exceeded",
            },
            "convergence_candidates": {
                "mergeable_keys": sorted(mergeable_candidates, key=lambda item: item["name"]),
                "deletable_keys": sorted(deletable_candidates, key=lambda item: item["name"]),
                "mergeable_count": len(mergeable_candidates),
                "deletable_count": len(deletable_candidates),
            },
        },
        "unresolved_keys": sorted(unresolved_keys),
    }


def render_markdown(report: dict[str, Any], registry_path: Path, tiers_path: Path) -> str:
    metrics = report["metrics"]
    tier_distribution = metrics["tier_distribution"]
    single_consumer = metrics["single_consumer"]
    timeout_class = metrics["timeout_class"]
    deprecated = metrics["deprecated"]
    deprecated_budget = metrics["deprecated_budget"]
    convergence = metrics["convergence_candidates"]
    unresolved = report["unresolved_keys"]

    lines = [
        "# Env Governance Report",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- registry: `{registry_path}`",
        f"- tiers_config: `{tiers_path}`",
        "",
        "## Summary",
        "",
        f"- total: **{metrics['total']}**",
        f"- resolved_total: **{metrics['resolved_total']}**",
        f"- unresolved_total: **{metrics['unresolved_total']}**",
        (
            f"- single_consumer: **{single_consumer['count']}** "
            f"({single_consumer['ratio'] * 100:.2f}%)"
        ),
        f"- timeout_class_count: **{timeout_class['count']}**",
        f"- deprecated_count: **{deprecated['count']}**",
        f"- deprecated_ratio: **{deprecated['ratio'] * 100:.2f}%**",
        (
            f"- deprecated_budget_status: **{deprecated_budget['status']}** "
            f"(max_count={deprecated_budget['max_count']}, max_ratio={deprecated_budget['max_ratio']:.6f})"
        ),
        f"- mergeable_candidates: **{convergence['mergeable_count']}**",
        f"- deletable_candidates: **{convergence['deletable_count']}**",
        "",
        "## Tier Distribution",
        "",
        "| tier | count |",
        "|---|---:|",
    ]
    for tier in ALLOWED_TIERS:
        lines.append(f"| {tier} | {tier_distribution.get(tier, 0)} |")

    lines.extend(["", "## Deprecated Keys", ""])
    if deprecated["keys"]:
        for key in deprecated["keys"]:
            lines.append(f"- `{key}`")
    else:
        lines.append("- (none)")

    lines.extend(["", "## Timeout-Class Keys", ""])
    if timeout_class["keys"]:
        for key in timeout_class["keys"]:
            lines.append(f"- `{key}`")
    else:
        lines.append("- (none)")

    lines.extend(["", "## Unresolved Keys", ""])
    if unresolved:
        for key in unresolved:
            lines.append(f"- `{key}`")
    else:
        lines.append("- (none)")

    lines.extend(["", "## Convergence Candidates", ""])
    lines.append("### Mergeable Keys")
    if convergence["mergeable_keys"]:
        for item in convergence["mergeable_keys"]:
            lines.append(
                f"- `{item['name']}` -> `{item['target_group_key']}` ({item['reason']})"
            )
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("### Deletable Keys")
    if convergence["deletable_keys"]:
        for item in convergence["deletable_keys"]:
            lines.append(f"- `{item['name']}` ({item['reason']})")
    else:
        lines.append("- (none)")

    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    registry_path = Path(args.registry)
    tiers_path = Path(args.tiers_config)
    output_dir = Path(args.output_dir)

    registry = load_json(registry_path)
    tiers_cfg = load_json(tiers_path)
    if args.max_deprecated_count < 0:
        print("[FAIL] --max-deprecated-count must be >= 0")
        return 1
    if args.max_deprecated_ratio < 0 or args.max_deprecated_ratio > 1:
        print("[FAIL] --max-deprecated-ratio must be within [0, 1]")
        return 1

    if not isinstance(registry, list):
        print(f"[FAIL] registry payload must be a JSON array: {registry_path}")
        return 1
    if not isinstance(tiers_cfg, dict):
        print(f"[FAIL] tiers config must be a JSON object: {tiers_path}")
        return 1

    report = collect_report(
        registry,
        tiers_cfg,
        max_deprecated_count=args.max_deprecated_count,
        max_deprecated_ratio=args.max_deprecated_ratio,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    report_json_path = output_dir / "report.json"
    report_md_path = output_dir / "report.md"

    report_json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    report_md_path.write_text(
        render_markdown(report, registry_path, tiers_path),
        encoding="utf-8",
    )

    print("[PASS] env governance report generated")
    print(f"report_json={report_json_path}")
    print(f"report_md={report_md_path}")
    print(
        "summary:"
        f" total={report['metrics']['total']},"
        f" core={report['metrics']['tier_distribution']['core']},"
        f" profile={report['metrics']['tier_distribution']['profile']},"
        f" advanced={report['metrics']['tier_distribution']['advanced']},"
        f" deprecated={report['metrics']['tier_distribution']['deprecated']},"
        f" single_consumer_ratio={report['metrics']['single_consumer']['ratio']:.6f},"
        f" timeout_count={report['metrics']['timeout_class']['count']},"
        f" deprecated_count={report['metrics']['deprecated']['count']},"
        f" deprecated_ratio={report['metrics']['deprecated']['ratio']:.6f},"
        f" deprecated_budget_status={report['metrics']['deprecated_budget']['status']},"
        f" mergeable_candidates={report['metrics']['convergence_candidates']['mergeable_count']},"
        f" deletable_candidates={report['metrics']['convergence_candidates']['deletable_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
