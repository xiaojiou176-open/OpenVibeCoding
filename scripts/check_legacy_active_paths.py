#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LEGACY_VENV_SEGMENT = "." + "venv"
LEGACY_CARGO_SEGMENT = "." + "cargo"
ACTIVE_SCAN_EXCLUDES = (
    "configs/",
    "docs/archive/",
    "docs/plans/",
    ".git/",
    ".runtime-cache/",
    "node_modules/",
    "schemas/",
)
IGNORED_FILES = {"CHANGELOG.md", "scripts/check_legacy_active_paths.py"}
FORBIDDEN_PATTERNS = (
    ("legacy_config_changed_scope", re.compile(r"(?<![A-Za-z0-9_.-])config/changed_scope/")),
    ("legacy_root_out", re.compile(r"(?<![A-Za-z0-9_.-])out/")),
    ("legacy_runtime_contract_root", re.compile(r"(?<!\.runtime-cache/)openvibecoding/contracts/")),
    ("legacy_codex_tmp", re.compile(r"(?<![A-Za-z0-9_.-])codex/tmp/")),
    ("legacy_python_venv", re.compile(rf"(?<![A-Za-z0-9_.-]){re.escape(LEGACY_VENV_SEGMENT)}/bin/")),
    ("legacy_cargo_root", re.compile(rf"(?<![A-Za-z0-9_.-]){re.escape(LEGACY_CARGO_SEGMENT)}/")),
)
FORBIDDEN_ROOTS = ("config", "out", "openvibecoding", "codex", LEGACY_VENV_SEGMENT, LEGACY_CARGO_SEGMENT)


def iter_active_files() -> list[Path]:
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    files: list[Path] = []
    for rel in tracked:
        if not rel or rel in IGNORED_FILES or rel.startswith(ACTIVE_SCAN_EXCLUDES):
            continue
        path = ROOT / rel
        if path.is_file():
            files.append(path)
    return files


def main() -> int:
    violations: list[str] = []
    for rel in FORBIDDEN_ROOTS:
        if (ROOT / rel).exists():
            violations.append(f"forbidden_root:{rel}")

    for path in iter_active_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in FORBIDDEN_PATTERNS:
            if pattern.search(text):
                violations.append(f"forbidden_pattern:{path.relative_to(ROOT)}:{label}")

    if violations:
        for item in violations:
            print(f"❌ [legacy-active-paths] {item}", file=sys.stderr)
        return 1

    print("✅ [legacy-active-paths] active surface is free of legacy root/path contracts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
