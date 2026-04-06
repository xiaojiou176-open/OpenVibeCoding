#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "configs" / "third_party_asset_registry.json"

ALLOWED_SURFACE_KINDS = {
    "application_icon_bundle",
    "branding_surface",
    "documentation_media",
    "redistributed_text_excerpt",
    "release_asset_bundle",
}
ALLOWED_STATUS = {"active", "retired"}
ALLOWED_REVIEW_STATES = {"pending_review", "in_review", "verified", "blocked"}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _matched_files(globs: list[str]) -> list[Path]:
    rows: list[Path] = []
    for raw_pattern in globs:
        pattern = str(raw_pattern or "").strip()
        if not pattern:
            continue
        rows.extend(path for path in ROOT.glob(pattern) if path.is_file())
    return sorted(set(rows))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the third-party asset provenance registry.")
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    args = parser.parse_args()

    registry_path = Path(args.registry).expanduser().resolve()
    payload = _load_json(registry_path)
    errors: list[str] = []

    version = payload.get("version")
    if version != 1:
        errors.append(f"registry version must be 1 (got {version!r})")

    entries = payload.get("entries")
    if not isinstance(entries, list) or not entries:
        errors.append("registry entries must be a non-empty array")
        entries = []

    seen_ids: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append("registry entries must be JSON objects")
            continue
        entry_id = str(entry.get("id") or "").strip()
        if not entry_id:
            errors.append("entry missing non-empty id")
            continue
        if entry_id in seen_ids:
            errors.append(f"duplicate entry id: {entry_id}")
        seen_ids.add(entry_id)

        surface_kind = str(entry.get("surface_kind") or "").strip()
        if surface_kind not in ALLOWED_SURFACE_KINDS:
            errors.append(f"{entry_id}: unsupported surface_kind `{surface_kind}`")

        status = str(entry.get("status") or "").strip()
        if status not in ALLOWED_STATUS:
            errors.append(f"{entry_id}: unsupported status `{status}`")

        review_state = str(entry.get("review_state") or "").strip()
        if review_state not in ALLOWED_REVIEW_STATES:
            errors.append(f"{entry_id}: unsupported review_state `{review_state}`")

        owner = str(entry.get("owner") or "").strip()
        if not owner:
            errors.append(f"{entry_id}: missing owner")

        origin_summary = str(entry.get("origin_summary") or "").strip()
        if not origin_summary:
            errors.append(f"{entry_id}: missing origin_summary")

        usage_boundary = str(entry.get("usage_boundary") or "").strip()
        if not usage_boundary:
            errors.append(f"{entry_id}: missing usage_boundary")

        path_globs = entry.get("path_globs")
        if not isinstance(path_globs, list) or not path_globs:
            errors.append(f"{entry_id}: path_globs must be a non-empty array")
            matched = []
        else:
            normalized_globs = [str(item).strip() for item in path_globs if str(item).strip()]
            if not normalized_globs:
                errors.append(f"{entry_id}: path_globs must contain non-empty strings")
                matched = []
            else:
                matched = _matched_files(normalized_globs)
                if not matched:
                    errors.append(f"{entry_id}: path_globs do not match any tracked file")

        evidence_refs = entry.get("evidence_refs")
        if not isinstance(evidence_refs, list) or not evidence_refs:
            errors.append(f"{entry_id}: evidence_refs must be a non-empty array")
        else:
            for raw_ref in evidence_refs:
                ref = str(raw_ref or "").strip()
                if not ref:
                    errors.append(f"{entry_id}: evidence_refs contains empty path")
                    continue
                ref_path = (ROOT / ref).resolve()
                if not ref_path.exists():
                    errors.append(f"{entry_id}: evidence_ref missing: {ref}")

        if review_state == "verified" and not evidence_refs:
            errors.append(f"{entry_id}: verified entry requires evidence_refs")

    if errors:
        print("❌ [third-party-asset-registry] violations:")
        for item in errors:
            print(f"- {item}")
        return 1

    print(
        f"✅ [third-party-asset-registry] registry satisfied: "
        f"{registry_path.relative_to(ROOT)} ({len(entries)} entries)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
