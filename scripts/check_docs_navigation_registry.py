#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "configs" / "docs_nav_registry.json"
PRIMARY_NAV_DOCS = (
    ROOT / "docs" / "README.md",
    ROOT / "docs" / "runbooks" / "README.md",
    ROOT / "docs" / "governance" / "README.md",
)
PRIMARY_NAV_REFERENCE_EXEMPTIONS = {"docs/README.md"}
DOCS_SUMMARY_PATH = ROOT / "docs" / "README.md"
REPOSITORY_ENTRY_ALLOWED = {"README.md"}


def _nav_tokens(path: str) -> set[str]:
    rel = Path(path)
    tokens = {path}
    if rel.name.lower() != "readme.md":
        tokens.add(rel.name)
    if path.startswith("docs/"):
        tokens.add(path.removeprefix("docs/"))
    for prefix in ("docs/runbooks/", "docs/governance/", "docs/ai/", "docs/archive/"):
        if path.startswith(prefix):
            tokens.add(path.removeprefix(prefix))
    return {token for token in tokens if token}


def _extract_section_targets(markdown: str, heading: str) -> set[str]:
    lines = markdown.splitlines()
    in_section = False
    captured: set[str] = set()
    for line in lines:
        if line.startswith("## "):
            in_section = line.strip() == heading
            continue
        if not in_section:
            continue
        for match in re.finditer(r"\(([^)]+)\)", line):
            target = match.group(1).strip()
            if not target or "://" in target or target.startswith("#"):
                continue
            try:
                rel = (DOCS_SUMMARY_PATH.parent / target).resolve().relative_to(ROOT).as_posix()
            except ValueError:
                continue
            captured.add(rel)
    return captured


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the curated docs navigation registry and active/archive boundaries."
    )
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    return parser.parse_args()


def _load_registry(path: Path) -> list[dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise SystemExit("❌ [docs-nav] invalid registry: entries(list) required")
    return entries


def main() -> int:
    args = parse_args()
    registry_path = Path(args.registry).expanduser().resolve()
    entries = _load_registry(registry_path)
    errors: list[str] = []

    nav_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in PRIMARY_NAV_DOCS
        if path.is_file()
    )
    active_primary_targets = {
        str(item.get("path") or "").strip()
        for item in entries
        if item.get("status") == "active" and item.get("listed_in_primary_navigation") is True
    }
    active_registered_supplemental_targets = {
        str(item.get("path") or "").strip()
        for item in entries
        if item.get("status") == "active"
        and item.get("canonical") is True
        and item.get("listed_in_primary_navigation") is False
    }
    archived_targets = {
        str(item.get("path") or "").strip()
        for item in entries
        if item.get("status") == "archived"
    }

    docs_summary_text = DOCS_SUMMARY_PATH.read_text(encoding="utf-8")
    repository_entry_targets = _extract_section_targets(docs_summary_text, "## Repository Entry")
    primary_summary_targets = _extract_section_targets(docs_summary_text, "## Primary Registered Docs")
    supplemental_summary_targets = _extract_section_targets(docs_summary_text, "## Supplemental Registered Docs")

    for item in entries:
        path = str(item.get("path") or "").strip()
        if not path:
            errors.append("registry entry missing path")
            continue
        abs_path = ROOT / path
        if not abs_path.exists():
            errors.append(f"registered path missing on disk: {path}")
        if item.get("listed_in_primary_navigation") is True and (
            item.get("status") != "active"
            or (item.get("canonical") is not True and item.get("generated") is not True)
        ):
            errors.append(f"primary navigation entry must be active canonical or generated: {path}")
        if item.get("status") == "active" and item.get("listed_in_primary_navigation") is True and not any(
            token in nav_text for token in _nav_tokens(path)
        ) and path not in PRIMARY_NAV_REFERENCE_EXEMPTIONS:
            errors.append(f"active primary-nav doc not referenced by navigation: {path}")

    for path in archived_targets:
        if any(token in nav_text for token in _nav_tokens(path)):
            errors.append(f"archived path must not appear in primary navigation: {path}")

    for path in active_primary_targets:
        if path in PRIMARY_NAV_REFERENCE_EXEMPTIONS:
            continue
        if not any(token in nav_text for token in _nav_tokens(path)):
            errors.append(f"missing required primary navigation reference: {path}")

    if repository_entry_targets != REPOSITORY_ENTRY_ALLOWED:
        extras = sorted(repository_entry_targets - REPOSITORY_ENTRY_ALLOWED)
        missing = sorted(REPOSITORY_ENTRY_ALLOWED - repository_entry_targets)
        if extras:
            errors.append(f"repository entry section contains unexpected targets: {', '.join(extras)}")
        if missing:
            errors.append(f"repository entry section missing targets: {', '.join(missing)}")

    expected_primary_summary_targets = active_primary_targets - PRIMARY_NAV_REFERENCE_EXEMPTIONS
    if primary_summary_targets != expected_primary_summary_targets:
        extras = sorted(primary_summary_targets - expected_primary_summary_targets)
        missing = sorted(expected_primary_summary_targets - primary_summary_targets)
        if extras:
            errors.append(f"primary docs summary lists non-registry targets: {', '.join(extras)}")
        if missing:
            errors.append(f"primary docs summary missing registry targets: {', '.join(missing)}")

    if supplemental_summary_targets != active_registered_supplemental_targets:
        extras = sorted(supplemental_summary_targets - active_registered_supplemental_targets)
        missing = sorted(active_registered_supplemental_targets - supplemental_summary_targets)
        if extras:
            errors.append(f"supplemental docs summary lists non-registry targets: {', '.join(extras)}")
        if missing:
            errors.append(f"supplemental docs summary missing registry targets: {', '.join(missing)}")

    if errors:
        print("❌ [docs-nav] navigation registry violations:")
        for item in errors:
            print(f"- {item}")
        return 1

    print(
        "✅ [docs-nav] curated navigation registry is consistent "
        f"({len(active_primary_targets)} primary-nav entries, {len(entries)} total registry entries)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
