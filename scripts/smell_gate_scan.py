#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SELF_RELATIVE_PATH = Path(__file__).resolve().relative_to(ROOT_DIR).as_posix()
TEST_FILE_RE = re.compile(
    r"""
    (
        \.(test|spec|suite)\.(js|jsx|ts|tsx|mjs|cjs)$
        |(^|/)test_[^/]+\.py$
        |(^|/)[^/]+_test\.py$
        |(^|/)(__tests__|tests|test)(/.*)?\.(js|jsx|ts|tsx|mjs|cjs|py)$
    )
    """,
    re.VERBOSE,
)
EXCLUDED_PARTS = {"node_modules", ".runtime-cache", "dist", "build", "coverage"}
TEST_DISCOVERY_RE = re.compile(r"\b(it|test|describe)\s*\(|^\s*def\s+test_", re.MULTILINE)
ASSERTION_RE = re.compile(
    r"\bexpect\s*\(|\bexpectTypeOf\s*(<|\()|\bexpect[A-Z][A-Za-z0-9_]*\s*\(|\bassert\b|pytest\.raises|self\.assert|raise\s+AssertionError",
    re.MULTILINE,
)

CHECKS: list[tuple[str, str, bool]] = [
    ("forbidden js/ts .only/.skip in tests", r"\b(test|it|describe)\s*\.\s*(only|skip)\s*\(", False),
    ("forbidden placebo assertion: expect(true).toBe(true)", r"expect\s*\(\s*true\s*\)\s*\.toBe\s*\(\s*true\s*\)", False),
    ("forbidden placebo assertion: expect(false).toBe(false)", r"expect\s*\(\s*false\s*\)\s*\.toBe\s*\(\s*false\s*\)", False),
    (
        "forbidden literal-identity assertion: expect(<literal>).to(Be|Equal|StrictEqual)(<same literal>)",
        r"expect\s*\(\s*(true|false|null|undefined|NaN|-?Infinity)\s*\)\s*\.(toBe|toEqual|toStrictEqual)\s*\(\s*\1\s*\)",
        False,
    ),
    (
        "forbidden self-equality assertion: expect(x).to(Be|Equal|StrictEqual)(x)",
        r"expect\s*\(\s*([A-Za-z_$][A-Za-z0-9_$\.\[\]'\"`]*)\s*\)\s*\.(toBe|toEqual|toStrictEqual)\s*\(\s*\1\s*\)",
        False,
    ),
    (
        "forbidden self-equality assertion: expect('x').to(Be|Equal|StrictEqual)('x')",
        r"expect\s*\(\s*(['\"])(.*?)\1\s*\)\s*\.(toBe|toEqual|toStrictEqual)\s*\(\s*\1\2\1\s*\)",
        False,
    ),
    (
        "forbidden self-equality assertion: expect(123).to(Be|Equal|StrictEqual)(123)",
        r"expect\s*\(\s*([0-9]+(?:\.[0-9]+)?)\s*\)\s*\.(toBe|toEqual|toStrictEqual)\s*\(\s*\1\s*\)",
        False,
    ),
    ("forbidden placebo assertion: python assert True", r"^\s*assert\s+True\s*(#.*)?$", False),
    ("forbidden placebo assertion: unittest assertTrue(True)", r"\.assertTrue\s*\(\s*True\s*\)", False),
    ("forbidden self-equality assertion: unittest assertEqual(x, x)", r"\.assertEqual\s*\(\s*([^,\n]+)\s*,\s*\1\s*\)", False),
    (
        "forbidden literal-identity assertion: python assert <literal> == <same literal>",
        r"^\s*assert\s+((?:True|False|None|-?[0-9]+(?:\.[0-9]+)?|\"[^\"]*\"|'[^']*'))\s*==\s*\1\s*(#.*)?$",
        False,
    ),
    ("forbidden weak assertion: toBeDefined()", r"\.toBeDefined\s*\(\s*\)", False),
    ("forbidden weak assertion: toBeTruthy()", r"\.toBeTruthy\s*\(\s*\)", False),
    ("forbidden commented-out test/it", r"^\s*//\s*(test|it|describe)\s*\(", False),
    ("forbidden commented-out test/it (block style)", r"^\s*/\*+\s*(test|it|describe)\s*\(", False),
    ("forbidden placebo assertion: unittest assertTrue(numeric literal)", r"\.assertTrue\s*\(\s*-?[0-9]+(?:\.[0-9]+)?\s*\)", False),
    ("forbidden placebo assertion: python assert numeric literal", r"^\s*assert\s+-?[0-9]+(?:\.[0-9]+)?\s*(#.*)?$", False),
    ("forbidden placebo assertion: unittest assertTrue(1/'literal')", r"\.assertTrue\s*\(\s*(1|\"[^\"]*\"|'[^']*')\s*\)", False),
    ("forbidden placebo assertion: python assert 1/'literal'", r"^\s*assert\s+(1|\"[^\"]*\"|'[^']*')\s*(#.*)?$", False),
    ("forbidden un-awaited promise assertion: expect(...).resolves/rejects", r"^[^\n]*(?<!await\s)(?<!return\s)expect\s*\([^\n]*\)\s*\.(resolves|rejects)", False),
    ("forbidden conditional expect in if branch", r"if\s*\([^\)]*\)\s*\{[^\}]*expect\s*\(", True),
    ("forbidden conditional expect in catch branch", r"catch\s*(?:\([^\)]*\))?\s*\{[^\}]*expect\s*\(", True),
]


def iter_candidate_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT_DIR.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT_DIR)
        if rel.as_posix() == SELF_RELATIVE_PATH:
            continue
        if any(part in EXCLUDED_PARTS for part in rel.parts):
            continue
        rel_posix = rel.as_posix()
        if TEST_FILE_RE.search(rel_posix):
            files.append(path)
    return files


def line_for_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def preview_line(text: str, lineno: int) -> str:
    lines = text.splitlines()
    if 1 <= lineno <= len(lines):
        return lines[lineno - 1].strip()
    return ""


def print_match(path: Path, text: str, match: re.Match[str]) -> None:
    lineno = line_for_offset(text, match.start())
    rel = path.relative_to(ROOT_DIR).as_posix()
    preview = preview_line(text, lineno)
    if preview:
        print(f"{rel}:{lineno}:{preview}")
    else:
        print(f"{rel}:{lineno}")


def main() -> int:
    violations = 0
    candidate_files = iter_candidate_files()

    for title, pattern, multiline in CHECKS:
        regex = re.compile(pattern, re.MULTILINE | (re.DOTALL if multiline else 0))
        matches: list[tuple[Path, str, re.Match[str]]] = []
        for path in candidate_files:
            text = path.read_text(encoding="utf-8", errors="ignore")
            match = regex.search(text)
            if match:
                matches.append((path, text, match))
        if matches:
            print(f"❌ [test-smell-gate] {title}")
            for path, text, match in matches:
                print_match(path, text, match)
            violations += 1

    no_assertion_matches: list[str] = []
    for path in candidate_files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        if TEST_DISCOVERY_RE.search(text) and not ASSERTION_RE.search(text):
            no_assertion_matches.append(path.relative_to(ROOT_DIR).as_posix())
    if no_assertion_matches:
        print("❌ [test-smell-gate] forbidden file-level no-assertion tests")
        for rel in no_assertion_matches:
            print(rel)
        violations += 1

    if violations > 0:
        print(f"❌ [test-smell-gate] detected {violations} test-smell category violations")
        return 1

    print("✅ [test-smell-gate] no blocked test smells found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
