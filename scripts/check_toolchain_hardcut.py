#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACTIVE_SCAN_EXCLUDES = (
    "docs/archive/",
    "docs/plans/",
    ".git/",
    ".runtime-cache/",
    "node_modules/",
)
IGNORED_FILES = {"CHANGELOG.md"}
FORBIDDEN_PATTERNS = ("".join((".venv", "/bin/")), "".join((".cargo", "/")))
FORBIDDEN_ROOTS = (ROOT / ".venv", ROOT / ".cargo")
PYTHON_TOOLCHAIN_BIN = ROOT / ".runtime-cache" / "cache" / "toolchains" / "python" / "current" / "bin"


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


def _default_toolchain_bin() -> Path:
    explicit = Path(str((ROOT / ".runtime-cache").resolve()))
    configured_root = Path(
        str(
            (
                Path(subprocess.run(["bash", "-lc", "source scripts/lib/toolchain_env.sh && openvibecoding_toolchain_cache_root \"$PWD\""], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip())
            )
        )
    )
    toolchain_bin = configured_root / "python" / "current" / "bin"
    if str(toolchain_bin).startswith(str(explicit)):
        return toolchain_bin
    return toolchain_bin


def validate_managed_python_toolchain() -> list[str]:
    violations: list[str] = []
    python_toolchain_bin = _default_toolchain_bin()
    if str(python_toolchain_bin).startswith(str(ROOT.resolve())):
        violations.append(f"toolchain_root_inside_repo:{python_toolchain_bin}")
    if not python_toolchain_bin.exists():
        violations.append(f"missing_python_toolchain_bin:{python_toolchain_bin}")
        return violations
    for name in ("python3", "python"):
        target = python_toolchain_bin / name
        if not target.exists():
            violations.append(f"missing_python_entrypoint:{target}")
            continue
        if not target.is_symlink():
            continue
        try:
            resolved = target.resolve(strict=True)
        except RuntimeError:
            violations.append(f"python_entrypoint_cycle:{target}")
            continue
        except FileNotFoundError:
            violations.append(f"python_entrypoint_broken:{target}")
            continue
        if not resolved.exists():
            violations.append(f"python_entrypoint_missing_target:{target}")
            continue
        if not resolved.is_file():
            violations.append(f"python_entrypoint_non_file_target:{target}")
    try:
        result = subprocess.run(
            [str(python_toolchain_bin / "python3"), "-V"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        violations.append(f"python_entrypoint_launch_failed:{exc}")
        return violations
    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()
        violations.append(f"python_entrypoint_unhealthy:returncode={result.returncode}:{stderr}")
    return violations


def main() -> int:
    violations: list[str] = []

    violations.extend(validate_managed_python_toolchain())

    for root_path in FORBIDDEN_ROOTS:
        if root_path.exists():
            violations.append(f"forbidden_root:{root_path.relative_to(ROOT)}")

    for path in iter_active_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in FORBIDDEN_PATTERNS:
            if pattern in text:
                violations.append(f"forbidden_pattern:{path.relative_to(ROOT)}:{pattern}")

    if violations:
        for item in violations:
            print(f"❌ [toolchain-hardcut] {item}", file=sys.stderr)
        return 1

    print("✅ [toolchain-hardcut] active surface has zero repo-local machine toolchain roots")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
