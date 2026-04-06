#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "configs" / "runtime_artifact_policy.json"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail closed on undeclared workspace-level runtime residue under configured workspace scan roots."
    )
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    args = parser.parse_args()

    policy = _load_json(Path(args.policy))
    scan_roots = [ROOT / raw for raw in policy.get("workspace_pollution_scan_roots", [])]
    forbidden_dirnames = set(policy.get("workspace_forbidden_dirnames", []))
    forbidden_file_globs = list(policy.get("workspace_forbidden_file_globs", []))
    allowed_roots = [
        ROOT / raw
        for raw in [
            *policy.get("machine_managed_repo_local_roots", []),
            *policy.get("runtime_roots", {}).values(),
            *policy.get("namespaces", {}).values(),
        ]
    ]
    internal_ignore_roots = {
        ROOT / ".git",
        ROOT / ".runtime-cache",
        ROOT / ".agents",
    }
    errors: list[str] = []

    def is_allowed_path(path: Path) -> bool:
        return any(_is_within(path, allowed_root) for allowed_root in allowed_roots)

    for scan_root in scan_roots:
        if not scan_root.exists():
            continue
        for current_root, dirnames, filenames in os.walk(scan_root):
            current_path = Path(current_root)

            if any(_is_within(current_path, ignore_root) for ignore_root in internal_ignore_roots):
                dirnames[:] = []
                continue
            if is_allowed_path(current_path):
                dirnames[:] = []
                continue

            next_dirnames: list[str] = []
            for dirname in dirnames:
                candidate = current_path / dirname
                if any(_is_within(candidate, ignore_root) for ignore_root in internal_ignore_roots):
                    continue
                if is_allowed_path(candidate):
                    continue
                if dirname in forbidden_dirnames:
                    errors.append(
                        f"forbidden workspace runtime directory present: {candidate.relative_to(ROOT).as_posix()}"
                    )
                    continue
                next_dirnames.append(dirname)
            dirnames[:] = next_dirnames

            for filename in filenames:
                candidate = current_path / filename
                if is_allowed_path(candidate):
                    continue
                if any(fnmatch.fnmatch(filename, pattern) for pattern in forbidden_file_globs):
                    errors.append(
                        f"forbidden workspace runtime file present: {candidate.relative_to(ROOT).as_posix()}"
                    )

    if errors:
        print("❌ [workspace-runtime-pollution] violations:")
        for item in errors:
            print(f"- {item}")
        return 1

    print("✅ [workspace-runtime-pollution] workspace runtime residue policy satisfied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
