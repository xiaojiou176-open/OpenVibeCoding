from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_generator_module() -> object:
    script_path = Path(__file__).resolve().parents[3] / "scripts" / "generate_storefront_proof_pack_index.py"
    spec = importlib.util.spec_from_file_location("openvibecoding_generate_storefront_proof_pack_index", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _load_gate_module() -> object:
    script_path = Path(__file__).resolve().parents[3] / "scripts" / "check_storefront_proof_assets.py"
    spec = importlib.util.spec_from_file_location("openvibecoding_storefront_proof_assets_gate", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _write_fixture(root: Path) -> None:
    (root / "docs" / "assets" / "storefront").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "releases" / "assets").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "runbooks").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "use-cases").mkdir(parents=True, exist_ok=True)
    (root / "configs").mkdir(parents=True, exist_ok=True)

    for rel in [
        "docs/releases/assets/news-digest-healthy-proof-2026-03-27.md",
        "docs/releases/assets/news-digest-benchmark-summary-2026-03-27.md",
        "docs/releases/assets/news-digest-workflow-case-recap-2026-03-27.md",
    ]:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("ok\n", encoding="utf-8")

    (root / "docs" / "releases" / "assets" / "news-digest-healthy-proof-summary-2026-03-27.json").write_text(
        json.dumps({"artifact_type": "healthy-proof-summary"}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (root / "docs" / "releases" / "assets" / "news-digest-benchmark-summary-2026-03-27.json").write_text(
        json.dumps({"artifact_type": "benchmark-summary"}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (root / "docs" / "releases" / "assets" / "news-digest-healthy-proof-gemini-2026-03-27.png").write_text(
        "png\n",
        encoding="utf-8",
    )
    (root / "docs" / "assets" / "storefront" / "dashboard-home-live-1440x900.png").write_text("png\n", encoding="utf-8")
    (root / "docs" / "assets" / "storefront" / "dashboard-command-tower-live-1440x900.png").write_text("png\n", encoding="utf-8")
    (root / "docs" / "assets" / "storefront" / "dashboard-runs-live-1440x900.png").write_text("png\n", encoding="utf-8")
    (root / "docs" / "assets" / "storefront" / "dashboard-live-healthy-loop.gif").write_text("gif\n", encoding="utf-8")
    (root / "docs" / "releases" / "assets" / "news-digest-proof-pack-2026-03-27.json").write_text(
        json.dumps(
            {
                "artifact_type": "news_digest_public_proof_pack",
                "primary_assets": {
                    "proof_summary_markdown": "docs/releases/assets/news-digest-healthy-proof-2026-03-27.md",
                    "proof_summary_json": "docs/releases/assets/news-digest-healthy-proof-summary-2026-03-27.json",
                    "benchmark_summary_markdown": "docs/releases/assets/news-digest-benchmark-summary-2026-03-27.md",
                    "benchmark_summary_json": "docs/releases/assets/news-digest-benchmark-summary-2026-03-27.json",
                    "workflow_case_recap_markdown": "docs/releases/assets/news-digest-workflow-case-recap-2026-03-27.md",
                    "demo_status_markdown": "docs/assets/storefront/demo-status.md"
                },
                "supporting_assets": {
                    "gemini_proof_screenshot": "docs/releases/assets/news-digest-healthy-proof-gemini-2026-03-27.png",
                    "dashboard_home_capture": "docs/assets/storefront/dashboard-home-live-1440x900.png",
                    "dashboard_command_tower_capture": "docs/assets/storefront/dashboard-command-tower-live-1440x900.png",
                    "dashboard_runs_capture": "docs/assets/storefront/dashboard-runs-live-1440x900.png",
                    "healthy_live_capture_gif": "docs/assets/storefront/dashboard-live-healthy-loop.gif"
                }
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    (root / "docs" / "use-cases" / "index.html").write_text(
        """
        <h1>First proven workflow and public proof pack</h1>
        <a href="../assets/storefront/proof-pack-index.json">Open proof-pack index</a>
        <p>The current recap story now has one tracked <strong>news_digest</strong> Workflow Case asset, tracked healthy local captures and proof assets, and one remaining broader benchmark gap.</p>
        <p>The current benchmark story is a tracked single-run baseline, not a broad release average.</p>
        <p>Global proof-pack index across public proven and showcase bundles</p>
        """,
        encoding="utf-8",
    )
    (root / "docs" / "assets" / "storefront" / "demo-status.md").write_text(
        """
        | Proof class | Current status | Notes |
        | --- | --- | --- |
        | Healthy backend-backed dashboard capture set | present | tracked English-first home, Command Tower session, and Runs captures from a clean local runtime root |
        | Healthy backend-backed live GIF | present | tracked multi-page walkthrough of the official first public happy path |
        ## Truth Boundary
        - these tracked captures are safe repo-side proof of a healthy local first public path, not proof of hosted production scale or live GitHub publication state.
        """,
        encoding="utf-8",
    )
    (root / "docs" / "assets" / "storefront" / "live-capture-requirements.json").write_text(
        json.dumps(
            {
                "artifact_type": "openvibecoding_storefront_live_capture_requirements",
                "required_assets": [
                    {"asset_id": "healthy_live_capture_gif", "status": "present"},
                    {"asset_id": "healthy_english_first_dashboard_home_capture", "status": "present"},
                    {"asset_id": "healthy_english_first_command_tower_capture", "status": "present"},
                    {"asset_id": "healthy_english_first_runs_capture", "status": "present"},
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "docs" / "runbooks" / "storefront-share-kit.md").write_text(
        """
        ## Proof Status By Asset Type
        - Healthy backend-backed dashboard capture set
        - Healthy backend-backed live GIF
        ## Safe Post Angles
        - safe to reference as repo-tracked proof, not as proof of live GitHub publication
        """,
        encoding="utf-8",
    )

    (root / "configs" / "storefront_proof_bundle_registry.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact_type": "openvibecoding_storefront_proof_bundle_registry",
                "vocabulary_contract": {
                    "proven_workflow_label": "first proven workflow",
                    "proof_pack_label": "public proof pack",
                    "showcase_label": "showcase expansion",
                },
                "bundles": [
                    {
                        "bundle_id": "news_digest",
                        "task_template": "news_digest",
                        "proof_state": "release_proven",
                        "claim_scope": "official_first_public_baseline",
                        "authority_level": "repo_side_public_proof",
                        "public_entrypoint": "docs/use-cases/index.html",
                        "pack_manifest": "docs/releases/assets/news-digest-proof-pack-2026-03-27.json",
                        "capture_contract": {
                            "healthy_live_capture_gif_present": True,
                            "healthy_english_first_public_capture_set_present": True,
                            "current_tracked_dashboard_captures": "healthy_english_first_backend_backed_local",
                        },
                        "missing_expected_artifacts": [
                            "broader_multi_round_benchmark",
                        ],
                    },
                    {
                        "bundle_id": "topic_brief",
                        "proof_state": "showcase_only",
                        "missing_expected_artifacts": ["dedicated_healthy_proof_summary"],
                    },
                    {
                        "bundle_id": "page_brief",
                        "proof_state": "showcase_only",
                        "missing_expected_artifacts": ["dedicated_healthy_proof_summary"],
                    },
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    generator = _load_generator_module()
    generator.ROOT = root
    generator.REGISTRY_PATH = root / "configs" / "storefront_proof_bundle_registry.json"
    generator.OUTPUT_PATH = root / "docs" / "assets" / "storefront" / "proof-pack-index.json"
    rendered = generator.build_index(generator._load_json(generator.REGISTRY_PATH))
    generator.OUTPUT_PATH.write_text(json.dumps(rendered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_storefront_proof_assets_gate_passes_with_expected_index(tmp_path: Path, monkeypatch) -> None:
    module = _load_gate_module()
    _write_fixture(tmp_path)
    module.ROOT = tmp_path
    module.PROOF_PACK_INDEX = tmp_path / "docs" / "assets" / "storefront" / "proof-pack-index.json"
    module.DEMO_STATUS_PATH = tmp_path / "docs" / "assets" / "storefront" / "demo-status.md"
    module.LIVE_CAPTURE_REQUIREMENTS_PATH = tmp_path / "docs" / "assets" / "storefront" / "live-capture-requirements.json"
    module.SHARE_KIT_PATH = tmp_path / "docs" / "runbooks" / "storefront-share-kit.md"
    module.USE_CASES_PATH = tmp_path / "docs" / "use-cases" / "index.html"
    monkeypatch.setattr(sys, "argv", ["check_storefront_proof_assets.py"])
    assert module.main() == 0


def test_storefront_proof_assets_gate_fails_when_news_digest_loses_release_proven(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    module = _load_gate_module()
    _write_fixture(tmp_path)
    index_path = tmp_path / "docs" / "assets" / "storefront" / "proof-pack-index.json"
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    payload["bundles"][0]["proof_state"] = "showcase_only"
    index_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    module.ROOT = tmp_path
    module.PROOF_PACK_INDEX = index_path
    module.DEMO_STATUS_PATH = tmp_path / "docs" / "assets" / "storefront" / "demo-status.md"
    module.LIVE_CAPTURE_REQUIREMENTS_PATH = tmp_path / "docs" / "assets" / "storefront" / "live-capture-requirements.json"
    module.SHARE_KIT_PATH = tmp_path / "docs" / "runbooks" / "storefront-share-kit.md"
    module.USE_CASES_PATH = tmp_path / "docs" / "use-cases" / "index.html"
    monkeypatch.setattr(sys, "argv", ["check_storefront_proof_assets.py"])

    rc = module.main()
    out = capsys.readouterr().out
    assert rc == 1
    assert "release_proven" in out
