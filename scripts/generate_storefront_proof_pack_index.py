#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "configs" / "storefront_proof_bundle_registry.json"
OUTPUT_PATH = ROOT / "docs" / "assets" / "storefront" / "proof-pack-index.json"

PRIMARY_ROLE_MAP: dict[str, dict[str, Any]] = {
    "proof_summary_markdown": {
        "role": "healthy_proof_summary",
        "format": "markdown",
        "truth_class": "repo_side_proof",
        "required_for_claim": True,
    },
    "proof_summary_json": {
        "role": "healthy_proof_summary_machine",
        "format": "json",
        "truth_class": "repo_side_machine_summary",
        "required_for_claim": True,
    },
    "benchmark_summary_markdown": {
        "role": "benchmark_summary",
        "format": "markdown",
        "truth_class": "repo_side_benchmark",
        "required_for_claim": True,
    },
    "benchmark_summary_json": {
        "role": "benchmark_summary_machine",
        "format": "json",
        "truth_class": "repo_side_machine_summary",
        "required_for_claim": True,
    },
    "workflow_case_recap_markdown": {
        "role": "workflow_case_recap",
        "format": "markdown",
        "truth_class": "share_ready_recap",
        "required_for_claim": True,
    },
    "demo_status_markdown": {
        "role": "demo_status_ledger",
        "format": "markdown",
        "truth_class": "truth_boundary_ledger",
        "required_for_claim": True,
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate the public storefront proof-pack index.")
    parser.add_argument("--registry", default=str(REGISTRY_PATH))
    parser.add_argument("--output", default=str(OUTPUT_PATH))
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"❌ [generate-storefront-proof-pack-index] expected JSON object: {path}")
    return payload


def _normalize_asset(path_text: str, descriptor: dict[str, Any]) -> dict[str, Any]:
    item = {"path": path_text}
    item.update(descriptor)
    return item


def _supporting_asset(path_text: str, key: str) -> dict[str, Any]:
    ext = Path(path_text).suffix.lower().lstrip(".") or "unknown"
    return {
        "path": path_text,
        "role": key,
        "format": ext,
        "truth_class": "supporting_capture",
        "required_for_claim": False,
    }


def build_index(registry_payload: dict[str, Any]) -> dict[str, Any]:
    bundles_payload = registry_payload.get("bundles")
    if not isinstance(bundles_payload, list):
        raise SystemExit("❌ [generate-storefront-proof-pack-index] registry missing bundles[]")

    rendered_bundles: list[dict[str, Any]] = []
    for bundle in bundles_payload:
        if not isinstance(bundle, dict):
            raise SystemExit("❌ [generate-storefront-proof-pack-index] bundle entries must be objects")
        rendered = dict(bundle)
        assets: list[dict[str, Any]] = []
        pack_manifest_rel = str(bundle.get("pack_manifest") or "").strip()
        if pack_manifest_rel:
            pack_manifest = _load_json(ROOT / pack_manifest_rel)
            rendered.setdefault("safe_public_claims", bundle.get("safe_public_claims", []))
            rendered.setdefault("forbidden_claims", bundle.get("forbidden_claims", []))
            rendered.setdefault("missing_expected_artifacts", bundle.get("missing_expected_artifacts", []))

            primary_assets = pack_manifest.get("primary_assets")
            if isinstance(primary_assets, dict):
                for key, descriptor in PRIMARY_ROLE_MAP.items():
                    path_text = str(primary_assets.get(key) or "").strip()
                    if path_text:
                        assets.append(_normalize_asset(path_text, descriptor))

            supporting_assets = pack_manifest.get("supporting_assets")
            if isinstance(supporting_assets, dict):
                for key, path_value in supporting_assets.items():
                    path_text = str(path_value or "").strip()
                    if path_text:
                        assets.append(_supporting_asset(path_text, key))

            rendered["pack_manifest"] = pack_manifest_rel

        rendered["assets"] = assets
        rendered_bundles.append(rendered)

    return {
        "artifact_type": "cortexpilot_public_proof_pack_index",
        "generated_by": "scripts/generate_storefront_proof_pack_index.py",
        "source_registry": str(Path(registry_payload.get("source_registry") or "configs/storefront_proof_bundle_registry.json")),
        "vocabulary_contract": registry_payload.get("vocabulary_contract", {}),
        "bundles": rendered_bundles,
    }


def main() -> int:
    args = parse_args()
    registry_path = Path(args.registry).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    registry_payload = _load_json(registry_path)
    registry_payload["source_registry"] = registry_path.relative_to(ROOT).as_posix()
    rendered = build_index(registry_payload)
    rendered_json = json.dumps(rendered, ensure_ascii=False, indent=2) + "\n"

    if args.check:
        if not output_path.exists():
            print(f"❌ [generate-storefront-proof-pack-index] missing output: {output_path.relative_to(ROOT)}")
            return 1
        current = output_path.read_text(encoding="utf-8")
        if current != rendered_json:
            print("❌ [generate-storefront-proof-pack-index] output drift detected")
            return 1
        print("✅ [generate-storefront-proof-pack-index] output is up to date")
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered_json, encoding="utf-8")
    print(f"✅ [generate-storefront-proof-pack-index] wrote {output_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
