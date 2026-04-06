#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "configs" / "runtime_artifact_policy.json"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _runtime_cache_top_level(raw_path: str) -> str | None:
    normalized = str(raw_path).strip()
    prefix = ".runtime-cache/"
    if not normalized.startswith(prefix):
        return None
    remainder = normalized[len(prefix):]
    if not remainder:
        return None
    return remainder.split("/", 1)[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate runtime artifact root policy.")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    args = parser.parse_args()

    policy = _load_json(Path(args.policy))
    errors: list[str] = []

    runtime_roots = policy.get("runtime_roots", {})
    namespaces = policy.get("namespaces", {})
    machine_managed_repo_local_roots = policy.get("machine_managed_repo_local_roots", [])
    machine_cache_roots = policy.get("machine_cache_roots", [])
    forbidden = policy.get("forbidden_top_level_outputs", [])
    legacy_paths = policy.get("legacy_runtime_paths", [])
    allowed_runtime_cache_children = {
        child
        for raw_path in [*runtime_roots.values(), *namespaces.values()]
        for child in [_runtime_cache_top_level(str(raw_path))]
        if child
    }

    for name, raw_path in sorted(runtime_roots.items()):
        if not str(raw_path).startswith(".runtime-cache/"):
            errors.append(f"{name} must stay under .runtime-cache/: {raw_path}")

    for name, raw_path in sorted(namespaces.items()):
        if not str(raw_path).startswith(".runtime-cache/"):
            errors.append(f"namespace {name} must stay under .runtime-cache/: {raw_path}")

    allowed_repo_local_parents = (ROOT / "apps", ROOT / "packages")
    for raw_path in machine_managed_repo_local_roots:
        path = ROOT / str(raw_path)
        if path.exists() and not any(path.is_relative_to(parent) for parent in allowed_repo_local_parents):
            errors.append(f"machine-managed repo-local root must stay under apps/ or packages/: {raw_path}")

    if "temp" not in namespaces:
        errors.append("runtime artifact policy must declare temp namespace")

    if not machine_cache_roots:
        errors.append("runtime artifact policy must declare machine_cache_roots")

    runtime_cache_root = ROOT / ".runtime-cache"
    if runtime_cache_root.exists():
        for child in sorted(runtime_cache_root.iterdir()):
            if child.name not in allowed_runtime_cache_children:
                errors.append(f"undeclared .runtime-cache child present: .runtime-cache/{child.name}")

    for entry in forbidden:
        if (ROOT / entry).exists():
            errors.append(f"forbidden top-level runtime artifact present: {entry}")

    for entry in legacy_paths:
        if (ROOT / entry).exists():
            errors.append(f"legacy runtime path still present: {entry}")

    if errors:
        print("❌ [runtime-artifact-policy] violations:")
        for item in errors:
            print(f"- {item}")
        return 1

    print("✅ [runtime-artifact-policy] policy satisfied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
