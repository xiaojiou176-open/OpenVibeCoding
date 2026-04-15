#!/usr/bin/env python3
from __future__ import annotations

import argparse
from html.parser import HTMLParser
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
README_PATH = ROOT / "README.md"
DOCS_README_PATH = ROOT / "docs" / "README.md"
INDEX_PATH = ROOT / "docs" / "index.html"
USE_CASES_PATH = ROOT / "docs" / "use-cases" / "index.html"
COMPATIBILITY_PATH = ROOT / "docs" / "compatibility" / "index.html"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the static public front-door contract for OpenVibeCoding."
    )
    return parser.parse_args()


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.anchors: list[tuple[str, str]] = []
        self._current_href: str | None = None
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self._current_href = href
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._current_href is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._current_href is None:
            return
        text = _normalize_text("".join(self._parts))
        self.anchors.append((self._current_href, text))
        self._current_href = None
        self._parts = []


def _read_html(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(path)
    return path.read_text(encoding="utf-8")


def _parse_anchors(path: Path) -> list[tuple[str, str]]:
    parser = _AnchorParser()
    parser.feed(_read_html(path))
    return parser.anchors


def _require_substrings(path: Path, content: str, required: list[str], errors: list[str]) -> None:
    normalized = _normalize_text(content)
    for snippet in required:
        if _normalize_text(snippet) not in normalized:
            errors.append(f"{path.relative_to(ROOT)} missing required text: {snippet}")


def _require_anchor(path: Path, anchors: list[tuple[str, str]], href: str, text: str, errors: list[str]) -> None:
    target = (_normalize_text(href), _normalize_text(text))
    normalized = [(_normalize_text(item_href), _normalize_text(item_text)) for item_href, item_text in anchors]
    if target not in normalized:
        errors.append(
            f"{path.relative_to(ROOT)} missing required link: text='{text}' href='{href}'"
        )


def _require_no_forbidden_link_targets(
    path: Path, anchors: list[tuple[str, str]], forbidden_markers: list[str], errors: list[str]
) -> None:
    for href, text in anchors:
        normalized_href = _normalize_text(href)
        for marker in forbidden_markers:
            if marker in normalized_href:
                errors.append(
                    f"{path.relative_to(ROOT)} must not link public readers to raw proof metadata: "
                    f"text='{text}' href='{href}'"
                )
                break


def main() -> int:
    _ = parse_args()
    errors: list[str] = []

    required_paths = [
        README_PATH,
        DOCS_README_PATH,
        INDEX_PATH,
        USE_CASES_PATH,
        COMPATIBILITY_PATH,
    ]
    for path in required_paths:
        if not path.exists():
            errors.append(f"required front-door artifact missing: {path.relative_to(ROOT)}")

    if errors:
        print("❌ [frontdoor-contract] missing required artifacts:")
        for item in errors:
            print(f"- {item}")
        return 1

    readme_text = README_PATH.read_text(encoding="utf-8")
    docs_readme_text = DOCS_README_PATH.read_text(encoding="utf-8")
    index_html = _read_html(INDEX_PATH)
    use_cases_html = _read_html(USE_CASES_PATH)
    compatibility_html = _read_html(COMPATIBILITY_PATH)

    _require_substrings(
        README_PATH,
        readme_text,
        [
            "Machine-readable proof ledgers now belong under `configs/public_proof/`",
            "public reading path stays on the use-cases page",
            "instead of raw ledger files or `docs/README.md`",
        ],
        errors,
    )

    _require_substrings(
        DOCS_README_PATH,
        docs_readme_text,
        [
            "This file is not the public proof router.",
            "keep machine-readable proof ledgers under `configs/public_proof/`",
            "instead of turning `docs/README.md` into a human path toward raw proof metadata.",
        ],
        errors,
    )

    _require_substrings(
        INDEX_PATH,
        index_html,
        [
            "See the first proven workflow",
            "Choose the right adoption path",
            "repo-backed operator control plane, not a hosted product",
            "shipped MCP surface remains read-only",
            "news_digest",
            "topic_brief",
            "page_brief",
        ],
        errors,
    )

    _require_substrings(
        USE_CASES_PATH,
        use_cases_html,
        [
            "First proven workflow and public proof pack",
            "news_digest",
            "only official release-proven public baseline",
            "topic_brief",
            "page_brief",
            "not yet equally release-proven",
            "What we still do not claim",
        ],
        errors,
    )

    _require_substrings(
        COMPATIBILITY_PATH,
        compatibility_html,
        [
            "One truthful compatibility matrix for modern coding-agent teams.",
            "read-only MCP",
            "See the first proven workflow",
        ],
        errors,
    )

    _require_substrings(
        USE_CASES_PATH,
        use_cases_html,
        [
            "repo-tracked public proof bundle",
            "Machine-readable proof metadata now lives under",
            "configs/public_proof/",
            "Proof you can rely on today",
            "human-facing proof summary",
        ],
        errors,
    )

    index_anchors = _parse_anchors(INDEX_PATH)
    _require_anchor(
        INDEX_PATH,
        index_anchors,
        "./use-cases/",
        "See the first proven workflow",
        errors,
    )
    _require_anchor(
        INDEX_PATH,
        index_anchors,
        "./compatibility/",
        "Choose the right adoption path",
        errors,
    )

    compatibility_anchors = _parse_anchors(COMPATIBILITY_PATH)
    _require_anchor(
        COMPATIBILITY_PATH,
        compatibility_anchors,
        "../use-cases/",
        "See the first proven workflow",
        errors,
    )

    use_cases_anchors = _parse_anchors(USE_CASES_PATH)
    _require_no_forbidden_link_targets(
        USE_CASES_PATH,
        use_cases_anchors,
        [
            "configs/public_proof/",
            "docs/releases/assets/",
            "docs/assets/storefront/",
        ],
        errors,
    )

    if errors:
        print("❌ [frontdoor-contract] public front-door contract violations:")
        for item in errors:
            print(f"- {item}")
        return 1

    print("✅ [frontdoor-contract] public front-door contract satisfied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
