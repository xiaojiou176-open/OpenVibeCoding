#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROOF_PACK_INDEX = ROOT / "docs" / "assets" / "storefront" / "proof-pack-index.json"
DEMO_STATUS_PATH = ROOT / "docs" / "assets" / "storefront" / "demo-status.md"
LIVE_CAPTURE_REQUIREMENTS_PATH = ROOT / "docs" / "assets" / "storefront" / "live-capture-requirements.json"
SHARE_KIT_PATH = ROOT / "docs" / "runbooks" / "storefront-share-kit.md"
USE_CASES_PATH = ROOT / "docs" / "use-cases" / "index.html"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the public storefront proof asset contract."
    )
    return parser.parse_args()


def _load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def _asset_exists(path_text: str, errors: list[str], *, reason: str) -> None:
    path = ROOT / path_text
    if not path.exists():
        errors.append(f"{reason}: missing asset {path_text}")


def _require_text(path: Path, snippets: list[str], errors: list[str]) -> None:
    text = path.read_text(encoding="utf-8")
    for snippet in snippets:
        if snippet not in text:
            errors.append(f"{path.relative_to(ROOT)} missing required text: {snippet}")


def _load_generator_module() -> object:
    script_path = Path(__file__).resolve().with_name("generate_storefront_proof_pack_index.py")
    spec = importlib.util.spec_from_file_location("cortexpilot_generate_storefront_proof_pack_index", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def main() -> int:
    _ = parse_args()
    errors: list[str] = []

    if not PROOF_PACK_INDEX.exists():
        print("❌ [storefront-proof-assets] proof-pack index missing")
        return 1
    if not LIVE_CAPTURE_REQUIREMENTS_PATH.exists():
        print("❌ [storefront-proof-assets] live capture requirements missing")
        return 1

    generator = _load_generator_module()
    generator.ROOT = ROOT
    generator.REGISTRY_PATH = ROOT / "configs" / "storefront_proof_bundle_registry.json"
    generator.OUTPUT_PATH = PROOF_PACK_INDEX
    registry_payload = generator._load_json(generator.REGISTRY_PATH)
    registry_payload["source_registry"] = generator.REGISTRY_PATH.relative_to(ROOT).as_posix()
    expected_payload = generator.build_index(registry_payload)
    current_payload = _load_json(PROOF_PACK_INDEX)
    if current_payload != expected_payload:
        errors.append("proof-pack index drifted from generator output")

    payload = current_payload
    live_capture_requirements = _load_json(LIVE_CAPTURE_REQUIREMENTS_PATH)
    _require(
        payload.get("artifact_type") == "cortexpilot_public_proof_pack_index",
        "proof-pack index has unexpected artifact_type",
        errors,
    )
    _require(
        live_capture_requirements.get("artifact_type") == "cortexpilot_storefront_live_capture_requirements",
        "live capture requirements has unexpected artifact_type",
        errors,
    )

    vocabulary = payload.get("vocabulary_contract")
    _require(isinstance(vocabulary, dict), "proof-pack index missing vocabulary_contract", errors)
    if isinstance(vocabulary, dict):
        _require(
            vocabulary.get("proven_workflow_label") == "first proven workflow",
            "proof-pack index must pin the proven workflow label",
            errors,
        )
        _require(
            vocabulary.get("proof_pack_label") == "public proof pack",
            "proof-pack index must pin the proof pack label",
            errors,
        )

    bundles = payload.get("bundles")
    _require(isinstance(bundles, list), "proof-pack index missing bundles[]", errors)
    bundle_map = {}
    if isinstance(bundles, list):
        for item in bundles:
            if isinstance(item, dict) and isinstance(item.get("bundle_id"), str):
                bundle_map[item["bundle_id"]] = item

    for bundle_id in ("news_digest", "topic_brief", "page_brief"):
        _require(bundle_id in bundle_map, f"missing proof bundle `{bundle_id}`", errors)

    news = bundle_map.get("news_digest", {})
    if isinstance(news, dict):
        _require(news.get("proof_state") == "release_proven", "news_digest must stay release_proven", errors)
        _require(
            news.get("claim_scope") == "official_first_public_baseline",
            "news_digest must stay the official first public baseline",
            errors,
        )
        pack_manifest = str(news.get("pack_manifest") or "").strip()
        _require(bool(pack_manifest), "news_digest must reference a pack_manifest", errors)
        if pack_manifest:
            _asset_exists(pack_manifest, errors, reason="news_digest pack manifest")

        capture_contract = news.get("capture_contract")
        _require(isinstance(capture_contract, dict), "news_digest missing capture_contract", errors)
        if isinstance(capture_contract, dict):
            _require(
                capture_contract.get("healthy_live_capture_gif_present") is True,
                "news_digest capture contract must acknowledge the landed healthy live-capture GIF",
                errors,
            )
            _require(
                capture_contract.get("healthy_english_first_public_capture_set_present") is True,
                "news_digest capture contract must acknowledge the landed healthy English-first public capture set",
                errors,
            )

        missing = news.get("missing_expected_artifacts")
        _require(isinstance(missing, list), "news_digest missing expected_artifacts list", errors)
        if isinstance(missing, list):
            required_missing = {"broader_multi_round_benchmark"}
            missing_set = {str(item) for item in missing}
            if not required_missing.issubset(missing_set):
                errors.append("news_digest missing_expected_artifacts must retain the broader benchmark gap")
            forbidden_missing = {
                "healthy_live_capture_gif",
                "healthy_english_first_public_capture_set",
            }
            if forbidden_missing & missing_set:
                errors.append("news_digest missing_expected_artifacts still lists landed healthy capture assets")

        assets = news.get("assets")
        _require(isinstance(assets, list), "news_digest missing assets[]", errors)
        if isinstance(assets, list):
            roles = {str(item.get("role")) for item in assets if isinstance(item, dict)}
            required_roles = {
                "healthy_proof_summary",
                "healthy_proof_summary_machine",
                "benchmark_summary",
                "benchmark_summary_machine",
                "workflow_case_recap",
                "demo_status_ledger",
                "dashboard_home_capture",
                "dashboard_command_tower_capture",
                "dashboard_runs_capture",
                "healthy_live_capture_gif",
            }
            if not required_roles.issubset(roles):
                errors.append("news_digest bundle lost one or more required proof asset roles")
            for item in assets:
                if not isinstance(item, dict):
                    errors.append("news_digest assets[] must contain objects")
                    continue
                path_text = str(item.get("path") or "").strip()
                if not path_text:
                    errors.append("news_digest assets[] contains an entry without path")
                    continue
                _asset_exists(path_text, errors, reason="news_digest asset")

    for showcase_id in ("topic_brief", "page_brief"):
        bundle = bundle_map.get(showcase_id, {})
        if isinstance(bundle, dict):
            _require(
                bundle.get("proof_state") == "showcase_only",
                f"{showcase_id} must stay showcase_only until its own healthy proof bundle exists",
                errors,
            )
            missing = bundle.get("missing_expected_artifacts")
            _require(
                isinstance(missing, list) and len(missing) > 0,
                f"{showcase_id} must keep explicit missing_expected_artifacts",
                errors,
            )

    _require_text(
        DEMO_STATUS_PATH,
        [
            "Healthy backend-backed dashboard capture set",
            "Healthy backend-backed live GIF",
            "safe repo-side proof of a healthy local first public path",
        ],
        errors,
    )
    _require_text(
        SHARE_KIT_PATH,
        [
            "Healthy backend-backed dashboard capture set",
            "Healthy backend-backed live GIF",
            "safe to reference as repo-tracked proof, not as proof of live GitHub publication",
        ],
        errors,
    )
    _require_text(
        USE_CASES_PATH,
        [
            "tracked healthy local captures and proof assets",
            "The current benchmark story is a tracked single-run baseline, not a broad release average.",
            "Global proof-pack index across public proven and showcase bundles",
        ],
        errors,
    )
    requirements_assets = live_capture_requirements.get("required_assets")
    _require(isinstance(requirements_assets, list), "live capture requirements missing required_assets[]", errors)
    if isinstance(requirements_assets, list):
        required_ids = {
            "healthy_live_capture_gif",
            "healthy_english_first_dashboard_home_capture",
            "healthy_english_first_command_tower_capture",
            "healthy_english_first_runs_capture",
        }
        seen_ids = {str(item.get("asset_id")) for item in requirements_assets if isinstance(item, dict)}
        if not required_ids.issubset(seen_ids):
            errors.append("live capture requirements lost one or more required asset ids")
        for item in requirements_assets:
            if not isinstance(item, dict):
                errors.append("live capture requirements entries must be objects")
                continue
            if str(item.get("status") or "").strip() != "present":
                errors.append("live capture requirements must mark landed assets as present")

    if errors:
        print("❌ [storefront-proof-assets] public proof asset contract violations:")
        for item in errors:
            print(f"- {item}")
        return 1

    print("✅ [storefront-proof-assets] public proof asset contract satisfied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
