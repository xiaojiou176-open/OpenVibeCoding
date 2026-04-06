#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MATRIX = ROOT / "docs" / "governance" / "ui-button-coverage-matrix.md"
DEFAULT_INVENTORY_DIR = ROOT / ".runtime-cache" / "test_output" / "ui_regression"
INVENTORY_SCRIPT = ROOT / "scripts" / "ui_button_inventory.py"

SUPPORTED_EVIDENCE_TYPES = ("real_playwright", "component_test", "unit_test", "mixed")
SUPPORTED_SOURCE_KINDS = ("real_playwright", "component_test", "unit_test")
SOURCE_ROOT_PREFIXES = (
    "apps/",
    "scripts/",
    "docs/",
    "tests/",
    "packages/",
    "configs/",
    "contracts/",
)
LINE_SUFFIX_RE = re.compile(r":\d+(?::\d+)?$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fail when required-tier UI buttons exist in inventory but are missing from matrix SSOT."
    )
    parser.add_argument(
        "--matrix",
        default=str(DEFAULT_MATRIX),
        help="Matrix markdown file path.",
    )
    parser.add_argument(
        "--inventory-dir",
        default=str(DEFAULT_INVENTORY_DIR),
        help="Directory containing button_inventory.{surface}.json files.",
    )
    parser.add_argument(
        "--surfaces",
        default="dashboard,desktop",
        help="Comma-separated surfaces to check.",
    )
    parser.add_argument(
        "--required-tiers",
        default="P0",
        help="Comma-separated tiers that must be present in matrix.",
    )
    parser.add_argument(
        "--fail-on-stale",
        action="store_true",
        help="Fail when matrix contains ids no longer present in inventory.",
    )
    parser.add_argument(
        "--base-ref",
        default="",
        help="Optional git base ref (e.g. origin/main). When set, only checks required-tier buttons in changed files.",
    )
    parser.add_argument(
        "--auto-generate-inventory",
        dest="auto_generate_inventory",
        action="store_true",
        default=True,
        help="Auto-generate missing inventory files by running scripts/ui_button_inventory.py (default: on).",
    )
    parser.add_argument(
        "--no-auto-generate-inventory",
        dest="auto_generate_inventory",
        action="store_false",
        help="Disable auto inventory generation.",
    )
    return parser.parse_args()


def clean_source_path(value: str) -> str:
    cleaned = str(value or "").strip().strip("`\"'()[]{}")
    cleaned = cleaned.replace("\\", "/")
    cleaned = cleaned.rstrip(".,;:")
    cleaned = LINE_SUFFIX_RE.sub("", cleaned)
    if not cleaned:
        return ""
    if not cleaned.startswith(SOURCE_ROOT_PREFIXES):
        return ""
    return cleaned


def split_paths(value: str) -> list[str]:
    parts = re.split(r"\s*;\s*|\s*,\s*|\s*\+\s*", str(value or "").strip())
    result: list[str] = []
    seen: set[str] = set()
    for part in parts:
        path = clean_source_path(part)
        if path and path not in seen:
            seen.add(path)
            result.append(path)
    return result


def split_source_kinds(value: str) -> list[str]:
    parts = re.split(r"\s*[;,/]\s*|\s+", str(value or "").strip().lower())
    result: list[str] = []
    seen: set[str] = set()
    for part in parts:
        if part in SUPPORTED_SOURCE_KINDS and part not in seen:
            seen.add(part)
            result.append(part)
    return sorted(result)


def normalize_source_exists(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"yes", "true", "1", "verified", "exists"}:
        return "yes"
    if normalized in {"no", "false", "0", "missing", "broken"}:
        return "no"
    return ""


def normalize_evidence_type(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in SUPPORTED_EVIDENCE_TYPES:
        return normalized
    return ""


def source_paths_exist(paths: list[str]) -> bool:
    if not paths:
        return False
    return all((ROOT / path).exists() for path in paths)


def ensure_inventory_files(inventory_dir: Path, surfaces: list[str], auto_generate_inventory: bool) -> None:
    missing_surfaces = [
        surface
        for surface in surfaces
        if not (inventory_dir / f"button_inventory.{surface}.json").exists()
    ]
    if not missing_surfaces:
        return
    if not auto_generate_inventory:
        raise FileNotFoundError(
            "missing inventory files and auto-generation disabled: " + ", ".join(missing_surfaces)
        )
    if not INVENTORY_SCRIPT.exists():
        raise FileNotFoundError(f"inventory script not found: {INVENTORY_SCRIPT}")

    print(
        "[ui-button-matrix-check] auto-generating missing inventory: "
        + ", ".join(missing_surfaces)
    )
    for surface in missing_surfaces:
        cmd = [sys.executable, str(INVENTORY_SCRIPT), "--surface", surface]
        result = subprocess.run(cmd, cwd=ROOT, check=False, capture_output=True, text=True)
        if result.stdout.strip():
            print(result.stdout.strip())
        if result.returncode != 0:
            stderr = result.stderr.strip()
            raise RuntimeError(
                "failed to generate inventory for surface "
                f"{surface}: {' '.join(cmd)}\n{stderr or '[no stderr]'}"
            )
        expected_path = inventory_dir / f"button_inventory.{surface}.json"
        if expected_path.exists():
            continue
        default_generated = DEFAULT_INVENTORY_DIR / f"button_inventory.{surface}.json"
        if inventory_dir != DEFAULT_INVENTORY_DIR and default_generated.exists():
            inventory_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(default_generated, expected_path)
        if not expected_path.exists():
            raise FileNotFoundError(
                f"inventory auto-generation finished but file still missing: {expected_path}"
            )


def load_inventory(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"missing inventory file: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("entries", [])
    if not isinstance(entries, list):
        raise ValueError(f"invalid entries in {path}")
    return entries


def parse_matrix_rows(matrix_path: Path) -> tuple[set[str], dict[str, dict[str, object]], list[str]]:
    if not matrix_path.exists():
        raise FileNotFoundError(f"matrix file not found: {matrix_path}")

    ids: set[str] = set()
    rows_by_id: dict[str, dict[str, object]] = {}
    structural_errors: list[str] = []

    for line_no, line in enumerate(matrix_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.startswith("| btn-"):
            continue

        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) < 11:
            structural_errors.append(
                f"line={line_no} row has insufficient columns (<11): cols={len(cols)}"
            )

        row_id = cols[0] if len(cols) > 0 else ""
        surface = cols[1] if len(cols) > 1 else ""
        tier = cols[2] if len(cols) > 2 else ""
        file_col = cols[3] if len(cols) > 3 else ""
        action = cols[4] if len(cols) > 4 else ""
        status = cols[5] if len(cols) > 5 else ""
        notes = cols[6] if len(cols) > 6 else ""
        evidence_type = normalize_evidence_type(cols[7] if len(cols) > 7 else "")
        source_paths = split_paths(cols[8] if len(cols) > 8 else "")
        source_kinds = split_source_kinds(cols[9] if len(cols) > 9 else "")
        source_exists = normalize_source_exists(cols[10] if len(cols) > 10 else "")

        if not row_id.startswith("btn-"):
            structural_errors.append(f"line={line_no} invalid row id: {row_id!r}")
            continue

        ids.add(row_id)
        rows_by_id[row_id] = {
            "id": row_id,
            "surface": surface,
            "tier": tier,
            "file": file_col,
            "action": action,
            "status": status,
            "notes": notes,
            "evidence_type": evidence_type,
            "source_paths": source_paths,
            "source_kinds": source_kinds,
            "source_exists": source_exists,
            "line_no": line_no,
        }

    return ids, rows_by_id, structural_errors


def changed_files_from_git(base_ref: str) -> set[str]:
    if not base_ref:
        return set()
    cmd = ["git", "diff", "--name-only", f"{base_ref}...HEAD"]
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"failed to resolve changed files from git: {' '.join(cmd)}\n{result.stderr.strip()}")
    changed = {line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()}
    return changed


def validate_required_row_structure(row: dict[str, object]) -> list[str]:
    errors: list[str] = []
    row_id = str(row.get("id", ""))
    tier = str(row.get("tier", ""))
    status = str(row.get("status", ""))
    evidence_type = str(row.get("evidence_type", ""))
    source_paths = list(row.get("source_paths") or [])
    source_kinds = list(row.get("source_kinds") or [])
    source_exists = str(row.get("source_exists", ""))

    if status != "COVERED":
        return errors

    if evidence_type not in SUPPORTED_EVIDENCE_TYPES:
        errors.append(f"{row_id}: COVERED row missing/invalid evidence type ({evidence_type!r})")

    if not source_paths:
        errors.append(f"{row_id}: COVERED row missing source path")

    if not source_kinds:
        errors.append(f"{row_id}: COVERED row missing source kind")

    if source_exists not in {"yes", "no"}:
        errors.append(f"{row_id}: COVERED row missing source existence validation")

    actual_exists = source_paths_exist(source_paths)
    if source_exists == "yes" and not actual_exists:
        errors.append(f"{row_id}: source exists is yes but source path validation failed")
    if source_exists == "no" and actual_exists:
        errors.append(f"{row_id}: source exists is no but all source paths exist")

    if evidence_type == "mixed":
        if len(set(source_kinds)) < 2:
            errors.append(f"{row_id}: evidence type mixed requires >=2 source kinds")
    elif evidence_type in SUPPORTED_SOURCE_KINDS:
        if set(source_kinds) != {evidence_type}:
            errors.append(
                f"{row_id}: evidence type {evidence_type} must match source kind exactly, got {source_kinds}"
            )

    # Authenticity floor: P0 rows must use real_playwright, or mixed evidence that includes real_playwright.
    if tier == "P0":
        p0_ok = evidence_type == "real_playwright" or (
            evidence_type == "mixed" and "real_playwright" in set(source_kinds)
        )
        if not p0_ok:
            errors.append(
                f"{row_id}: P0 authenticity gate failed, requires real_playwright or mixed including real_playwright"
            )

    return errors


def main() -> int:
    args = parse_args()
    matrix_path = Path(args.matrix)
    inventory_dir = Path(args.inventory_dir)
    surfaces = [item.strip() for item in args.surfaces.split(",") if item.strip()]
    required_tiers = {item.strip() for item in args.required_tiers.split(",") if item.strip()}

    ensure_inventory_files(inventory_dir, surfaces, args.auto_generate_inventory)

    required_entries: list[dict] = []
    all_entry_ids: set[str] = set()
    base_ref = args.base_ref.strip()
    scope_changed_only = bool(base_ref)
    changed_files = changed_files_from_git(base_ref) if scope_changed_only else set()

    for surface in surfaces:
        entries = load_inventory(inventory_dir / f"button_inventory.{surface}.json")
        for entry in entries:
            entry_id = str(entry.get("id", "")).strip()
            if not entry_id:
                continue
            all_entry_ids.add(entry_id)
            if str(entry.get("tier", "")).strip() in required_tiers:
                if scope_changed_only and str(entry.get("file", "")).strip() not in changed_files:
                    continue
                required_entries.append(entry)

    matrix_ids, matrix_rows_by_id, structural_errors = parse_matrix_rows(matrix_path)
    required_ids = {entry["id"] for entry in required_entries}

    missing_ids = sorted(required_ids - matrix_ids)
    stale_ids = sorted(matrix_ids - all_entry_ids)

    authenticity_errors: list[str] = []
    for row_id in sorted(required_ids.intersection(matrix_rows_by_id.keys())):
        row = matrix_rows_by_id[row_id]
        authenticity_errors.extend(validate_required_row_structure(row))

    covered_required = sum(
        1
        for row_id in required_ids
        if row_id in matrix_rows_by_id and str(matrix_rows_by_id[row_id].get("status", "")) == "COVERED"
    )

    print(
        "[ui-button-matrix-check] "
        f"required={len(required_ids)} covered_required={covered_required} matrix={len(matrix_ids)} "
        f"missing={len(missing_ids)} stale={len(stale_ids)} "
        f"structure_errors={len(structural_errors)} authenticity_errors={len(authenticity_errors)} "
        f"mode={'changed-files' if scope_changed_only else 'full'}"
    )

    if missing_ids:
        print("\nMissing required button ids in matrix:")
        index = {entry["id"]: entry for entry in required_entries}
        for missing_id in missing_ids:
            entry = index[missing_id]
            print(
                f"- {missing_id} | {entry.get('tier')} | {entry.get('surface')} | "
                f"{entry.get('file')}:{entry.get('line')} | text={entry.get('text')!r} | onClick={entry.get('on_click')!r}"
            )

    if stale_ids:
        print("\nStale matrix ids (not found in current inventory):")
        for stale_id in stale_ids:
            print(f"- {stale_id}")

    if structural_errors:
        print("\nStructure errors:")
        for error in structural_errors:
            print(f"- {error}")

    if authenticity_errors:
        print("\nAuthenticity threshold errors:")
        for error in authenticity_errors:
            print(f"- {error}")

    if missing_ids:
        return 1
    if stale_ids and args.fail_on_stale:
        return 1
    if structural_errors:
        return 1
    if authenticity_errors:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
