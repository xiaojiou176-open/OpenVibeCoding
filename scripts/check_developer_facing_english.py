#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HAN_RE = re.compile(r"[\u4e00-\u9fff]")
INLINE_CODE_RE = re.compile(r"`[^`]*`")
FENCE_RE = re.compile(r"^```")

TARGETS = [
    ROOT / "AGENTS.md",
    ROOT / "apps" / "orchestrator" / "AGENTS.md",
    ROOT / "docs" / "README.md",
    ROOT / "docs" / "runbooks" / "onboarding-30min.md",
]


def strip_inline_code(text: str) -> str:
    return INLINE_CODE_RE.sub("", text)


def main() -> int:
    violations: list[str] = []
    for path in TARGETS:
        if not path.is_file():
            violations.append(f"missing target file: {path.relative_to(ROOT)}")
            continue
        in_fence = False
        for lineno, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            line = raw_line.rstrip("\n")
            if FENCE_RE.match(line.strip()):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            candidate = strip_inline_code(line)
            if not candidate.strip():
                continue
            if HAN_RE.search(candidate):
                violations.append(
                    f"{path.relative_to(ROOT)}:{lineno}: contains developer-facing non-English prose outside localized/code examples"
                )

    if violations:
        print("❌ [developer-facing-english] policy violations:")
        for item in violations:
            print(f"- {item}")
        return 1

    print("✅ [developer-facing-english] targeted developer-facing docs are English-first outside localized/code examples")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
