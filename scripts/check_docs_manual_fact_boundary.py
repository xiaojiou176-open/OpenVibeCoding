#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WRAPPER_TARGETS = (
    ROOT / "README.md",
    ROOT / "AGENTS.md",
    ROOT / "CLAUDE.md",
    ROOT / "docs" / "ai" / "agent-guide.md",
)
DOCS_NAV_REGISTRY = ROOT / "configs" / "docs_nav_registry.json"
GENERATED_BLOCK_RE = re.compile(
    r"<!-- GENERATED:(?P<name>[a-z0-9\-]+):start -->.*?<!-- GENERATED:(?P=name):end -->",
    re.S,
)
RULES = {
    "latest_coverage_snapshot": re.compile(r"95\.29%|Latest stable coverage|\u6700\u65b0\u7a33\u5b9a\u89c2\u6d4b|Latest stable repo coverage"),
    "route_report_naming": re.compile(r"ci-route-report-[A-Za-z0-9_<>{}_\-$]+"),
    "generated_at_snapshot": re.compile(r"Latest audited matrix snapshot|_generated_at\s+is\s+the\s+single snapshot timestamp SSOT"),
    "workflow_job_inventory": re.compile(r"Jobs and trust boundary:"),
    "current_run_internal_file_inventory": re.compile(
        r"downstream builders \(`artifact_index/current_run_index`, `cost_profile`, `slo`, `runner_health`, `portal`, `provenance`\)"
    ),
    "matrix_authenticity_split_snapshot": re.compile(
        r"includes `real_playwright` = `\d+`|excludes `real_playwright` = `\d+`"
    ),
    "matrix_coverage_count_snapshot": re.compile(
        r"\u5f53\u524d\u77e9\u9635\u4e3a\s*\d+/\d+|`P0/P1 TODO=0`|\u5305\u542b\s*`real_playwright`\s*\u7684\u4e3a\s*`\d+`|\u4e0d\u5305\u542b\s*`real_playwright`\s*\u7684\u4e3a\s*`\d+`"
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Block hand-written high-drift facts in wrapper docs and registered "
            "active canonical docs outside generated anchors."
        )
    )
    return parser.parse_args()


def _strip_generated_blocks(text: str) -> str:
    return GENERATED_BLOCK_RE.sub("", text)


def _iter_registry_targets() -> list[Path]:
    registry = json.loads(DOCS_NAV_REGISTRY.read_text(encoding="utf-8"))
    entries = registry.get("entries")
    if not isinstance(entries, list):
        raise RuntimeError(
            "configs/docs_nav_registry.json must expose active canonical docs under `entries`"
        )
    targets: list[Path] = []
    for entry in entries:
        path = entry.get("path")
        if not path or not path.endswith(".md"):
            continue
        if entry.get("status") != "active":
            continue
        if not entry.get("canonical"):
            continue
        if entry.get("generated"):
            continue
        targets.append(ROOT / path)
    return targets


def _target_paths() -> list[Path]:
    ordered: list[Path] = []
    seen: set[Path] = set()
    for path in (*WRAPPER_TARGETS, *_iter_registry_targets()):
        if path in seen or not path.exists():
            continue
        ordered.append(path)
        seen.add(path)
    return ordered


def main() -> int:
    _ = parse_args()
    errors: list[str] = []
    try:
        targets = _target_paths()
    except RuntimeError as exc:
        print(f"❌ [docs-fact-boundary] invalid docs navigation registry: {exc}")
        return 1

    for path in targets:
        text = path.read_text(encoding="utf-8")
        stripped = _strip_generated_blocks(text)
        for rule_name, pattern in RULES.items():
            if pattern.search(stripped):
                errors.append(f"{path.relative_to(ROOT)} violates {rule_name}")

    if errors:
        print("❌ [docs-fact-boundary] detected hand-written high-drift facts outside generated anchors:")
        for item in errors:
            print(f"- {item}")
        return 1

    print(
        "✅ [docs-fact-boundary] manual docs stay within allowed fact boundary "
        f"across {len(targets)} wrapper/registered canonical docs"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
