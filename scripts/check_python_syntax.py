#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compile Python source in memory without writing bytecode.")
    parser.add_argument("paths", nargs="+", help="Files or directories to syntax-check")
    return parser.parse_args()


def iter_python_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path] if path.suffix == ".py" else []
    return sorted(candidate for candidate in path.rglob("*.py") if candidate.is_file())


def main() -> int:
    args = parse_args()
    errors: list[str] = []
    checked = 0
    for raw_path in args.paths:
        path = Path(raw_path)
        for candidate in iter_python_files(path):
            checked += 1
            try:
                source = candidate.read_text(encoding="utf-8")
                compile(source, str(candidate), "exec")
            except SyntaxError as exc:
                errors.append(f"{candidate}:{exc.lineno}:{exc.offset}: {exc.msg}")

    if errors:
        print("❌ [python-syntax] syntax errors detected:")
        for item in errors:
            print(f"- {item}")
        return 1

    print(f"✅ [python-syntax] checked {checked} python files without writing bytecode")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
