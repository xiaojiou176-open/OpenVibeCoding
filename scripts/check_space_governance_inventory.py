#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME_POLICY = ROOT / "configs" / "runtime_artifact_policy.json"
DEFAULT_SPACE_POLICY = ROOT / "configs" / "space_governance_policy.json"
DEFAULT_CLEANUP_SCRIPT = ROOT / "scripts" / "cleanup_workspace_modules.sh"
APPLY_ELIGIBLE_MODES = {"remove-path", "aged-children", "named-descendants"}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_cleanup_script(path: Path) -> tuple[list[str], list[dict[str, object]]]:
    exact_targets: list[str] = []
    named_descendants: list[dict[str, object]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("cleanup_target "):
            args = re.findall(r'"([^"]+)"', line)
            if args and not args[0].startswith("$"):
                exact_targets.append(args[0])
            continue
        if line.startswith("cleanup_named_dirs_under "):
            args = re.findall(r'"([^"]+)"', line)
            if len(args) >= 2:
                named_descendants.append({"root": args[0], "names": args[1:]})
    return exact_targets, named_descendants


def _build_space_policy_index(policy: dict) -> tuple[set[str], dict[str, set[str]], list[dict], dict[str, dict]]:
    exact_repo_internal_paths: set[str] = set()
    named_descendant_roots: dict[str, set[str]] = {}
    apply_eligible_entries: list[dict] = []
    command_registry = {str(item.get("id", "")): item for item in policy.get("rebuild_commands", []) if item.get("id")}

    for layer_name in ("repo_internal", "repo_external_related"):
        for entry in policy.get("layers", {}).get(layer_name, []):
            raw_path = str(entry.get("path", "")).strip()
            cleanup_mode = str(entry.get("cleanup_mode", "")).strip()
            if layer_name == "repo_internal":
                if cleanup_mode == "named-descendants":
                    names = {
                        str(name).strip()
                        for name in entry.get("cleanup_target_names", [])
                        if str(name).strip()
                    }
                    named_descendant_roots[raw_path] = names
                elif raw_path:
                    exact_repo_internal_paths.add(raw_path)
            if cleanup_mode in APPLY_ELIGIBLE_MODES and str(entry.get("recommendation", "")).strip() != "observe_only":
                apply_eligible_entries.append(entry)

    return exact_repo_internal_paths, named_descendant_roots, apply_eligible_entries, command_registry


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate cleanup inventory consistency across runtime policy, space governance policy, and workspace cleanup script."
    )
    parser.add_argument("--runtime-policy", default=str(DEFAULT_RUNTIME_POLICY))
    parser.add_argument("--space-policy", default=str(DEFAULT_SPACE_POLICY))
    parser.add_argument("--cleanup-script", default=str(DEFAULT_CLEANUP_SCRIPT))
    args = parser.parse_args()

    runtime_policy = _load_json(Path(args.runtime_policy).expanduser().resolve())
    space_policy = _load_json(Path(args.space_policy).expanduser().resolve())
    cleanup_script = Path(args.cleanup_script).expanduser().resolve()

    exact_targets, named_descendants = _parse_cleanup_script(cleanup_script)
    machine_managed_repo_local_roots = {
        str(item).strip() for item in runtime_policy.get("machine_managed_repo_local_roots", []) if str(item).strip()
    }
    forbidden_top_level_outputs = {
        str(item).strip() for item in runtime_policy.get("forbidden_top_level_outputs", []) if str(item).strip()
    }
    (
        exact_repo_internal_paths,
        named_descendant_roots,
        apply_eligible_entries,
        command_registry,
    ) = _build_space_policy_index(space_policy)

    errors: list[str] = []
    classifications: list[str] = []

    for target in exact_targets:
        if target in exact_repo_internal_paths:
            classifications.append(f"space_cleanup_managed: {target}")
            continue
        if target in machine_managed_repo_local_roots:
            classifications.append(f"runtime_retention_managed: {target}")
            continue
        if target in forbidden_top_level_outputs:
            classifications.append(f"forbidden_generated: {target}")
            continue
        errors.append(f"cleanup script target is not declared by runtime/space policy: {target}")

    for item in named_descendants:
        root = str(item["root"])
        names = {str(name).strip() for name in item["names"] if str(name).strip()}
        declared = named_descendant_roots.get(root, set())
        if not declared:
            errors.append(f"cleanup named-descendants root is not declared by space policy: {root}")
            continue
        missing = sorted(names - declared)
        if missing:
            errors.append(
                f"cleanup named-descendants entries missing from space policy for {root}: {', '.join(missing)}"
            )
            continue
        classifications.append(f"space_cleanup_managed: {root} -> {', '.join(sorted(names))}")

    for entry in apply_eligible_entries:
        entry_id = str(entry.get("id", "")).strip() or "<unknown>"
        command_ids = [
            str(command_id).strip()
            for command_id in (entry.get("post_cleanup_command_ids") or entry.get("rebuild_command_ids") or [])
            if str(command_id).strip()
        ]
        if not command_ids:
            errors.append(f"apply-eligible target missing rebuild/verification commands: {entry_id}")
            continue
        missing_ids = sorted(command_id for command_id in command_ids if command_id not in command_registry)
        if missing_ids:
            errors.append(
                f"apply-eligible target references unknown rebuild/verification commands: {entry_id} -> {', '.join(missing_ids)}"
            )

    if errors:
        print("❌ [space-governance-inventory] violations:")
        for item in errors:
            print(f"- {item}")
        return 1

    print("✅ [space-governance-inventory] cleanup inventory satisfied")
    for item in classifications:
        print(f"- {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
