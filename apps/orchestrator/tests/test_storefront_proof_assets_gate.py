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
    (root / "docs" / "use-cases").mkdir(parents=True, exist_ok=True)
    (root / "configs" / "public_proof" / "releases_assets").mkdir(parents=True, exist_ok=True)
    (root / "configs" / "public_proof" / "storefront").mkdir(parents=True, exist_ok=True)

    for rel in [
        "configs/public_proof/releases_assets/news-digest-healthy-proof-2026-03-27.md",
        "configs/public_proof/releases_assets/news-digest-benchmark-summary-2026-03-27.md",
        "configs/public_proof/releases_assets/news-digest-workflow-case-recap-2026-03-27.md",
        "configs/public_proof/releases_assets/page-brief-healthy-proof-2026-04-15.md",
        "configs/public_proof/releases_assets/page-brief-benchmark-summary-2026-04-15.md",
        "configs/public_proof/releases_assets/page-brief-workflow-case-recap-2026-04-15.md",
    ]:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("ok\n", encoding="utf-8")

    (root / "configs" / "public_proof" / "releases_assets" / "news-digest-healthy-proof-summary-2026-03-27.json").write_text(
        json.dumps({"artifact_type": "healthy-proof-summary"}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (root / "configs" / "public_proof" / "releases_assets" / "news-digest-benchmark-summary-2026-03-27.json").write_text(
        json.dumps({"artifact_type": "benchmark-summary"}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (root / "configs" / "public_proof" / "releases_assets" / "page-brief-healthy-proof-summary-2026-04-15.json").write_text(
        json.dumps({"artifact_type": "page-brief-healthy-proof-summary"}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (root / "configs" / "public_proof" / "releases_assets" / "page-brief-benchmark-summary-2026-04-15.json").write_text(
        json.dumps({"artifact_type": "page-brief-benchmark-summary"}, ensure_ascii=False, indent=2) + "\n",
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
    (root / "configs" / "public_proof" / "releases_assets" / "news-digest-proof-pack-2026-03-27.json").write_text(
        json.dumps(
            {
                "artifact_type": "news_digest_public_proof_pack",
                "primary_assets": {
                    "proof_summary_markdown": "configs/public_proof/releases_assets/news-digest-healthy-proof-2026-03-27.md",
                    "proof_summary_json": "configs/public_proof/releases_assets/news-digest-healthy-proof-summary-2026-03-27.json",
                    "benchmark_summary_markdown": "configs/public_proof/releases_assets/news-digest-benchmark-summary-2026-03-27.md",
                    "benchmark_summary_json": "configs/public_proof/releases_assets/news-digest-benchmark-summary-2026-03-27.json",
                    "workflow_case_recap_markdown": "configs/public_proof/releases_assets/news-digest-workflow-case-recap-2026-03-27.md",
                    "demo_status_markdown": "configs/public_proof/storefront/demo-status.md"
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
    (root / "configs" / "public_proof" / "releases_assets" / "page-brief-proof-pack-2026-04-15.json").write_text(
        json.dumps(
            {
                "artifact_type": "page_brief_public_proof_pack",
                "primary_assets": {
                    "proof_summary_markdown": "configs/public_proof/releases_assets/page-brief-healthy-proof-2026-04-15.md",
                    "proof_summary_json": "configs/public_proof/releases_assets/page-brief-healthy-proof-summary-2026-04-15.json",
                    "benchmark_summary_markdown": "configs/public_proof/releases_assets/page-brief-benchmark-summary-2026-04-15.md",
                    "benchmark_summary_json": "configs/public_proof/releases_assets/page-brief-benchmark-summary-2026-04-15.json",
                    "workflow_case_recap_markdown": "configs/public_proof/releases_assets/page-brief-workflow-case-recap-2026-04-15.md",
                    "demo_status_markdown": "configs/public_proof/storefront/demo-status.md"
                },
                "supporting_assets": {}
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
        <p>page_brief now has one tracked browser-backed public proof bundle beside the official news_digest baseline.</p>
        <p>The current benchmark story is a tracked single-run baseline, not a broad release average.</p>
        <p>Global proof-pack index across the official baseline, tracked bundle, and showcase bundles</p>
        <p>topic_brief still needs its own dedicated healthy proof summary, dedicated benchmark summary, and share-ready recap before it can leave showcase status.</p>
        <p>topic_brief does not yet have a repo-tracked proof pack or another share-ready proof asset on the public surface.</p>
        """,
        encoding="utf-8",
    )
    (root / "configs" / "public_proof" / "storefront" / "demo-status.md").write_text(
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
    (root / "configs" / "storefront_proof_bundle_registry.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact_type": "openvibecoding_storefront_proof_bundle_registry",
                "public_proof_contract": {
                    "authoritative_registry_path": "configs/storefront_proof_bundle_registry.json",
                    "render_manifest_path": "configs/docs_render_manifest.json",
                    "required_rendered_outputs": [
                        "configs/public_proof/storefront/proof-pack-index.json"
                    ],
                    "tracked_contract_inputs": [
                        "configs/storefront_proof_bundle_registry.json",
                        "configs/public_proof/releases_assets/news-digest-proof-pack-2026-03-27.json",
                        "configs/public_proof/releases_assets/page-brief-proof-pack-2026-04-15.json",
                        "configs/public_proof/storefront/demo-status.md",
                        "configs/public_proof/storefront/live-capture-requirements.json"
                    ]
                },
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
                        "pack_manifest": "configs/public_proof/releases_assets/news-digest-proof-pack-2026-03-27.json",
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
                        "task_template": "topic_brief",
                        "proof_state": "showcase_only",
                        "claim_scope": "public_showcase_path",
                        "authority_level": "repo_side_story_surface",
                        "safe_public_claims": [
                            "topic_brief is a public showcase and discovery lane with search-backed evidence",
                            "topic_brief is pending a dedicated healthy proof summary, a dedicated benchmark summary, and a share-ready recap before it can leave showcase status",
                        ],
                        "forbidden_claims": [
                            "topic_brief is an equally release-proven baseline today",
                            "topic_brief already has a tracked public proof bundle today",
                        ],
                        "missing_expected_artifacts": [
                            "dedicated_healthy_proof_summary",
                            "dedicated_benchmark_summary",
                            "share_ready_recap",
                        ],
                    },
                    {
                        "bundle_id": "page_brief",
                        "task_template": "page_brief",
                        "proof_state": "proof_bundle_tracked",
                        "claim_scope": "browser_backed_public_proof_bundle",
                        "authority_level": "repo_side_public_proof",
                        "public_entrypoint": "docs/use-cases/index.html",
                        "pack_manifest": "configs/public_proof/releases_assets/page-brief-proof-pack-2026-04-15.json",
                        "safe_public_claims": ["page_brief now has a tracked browser-backed public proof bundle"],
                        "forbidden_claims": ["page_brief is the official first public baseline today"],
                        "missing_expected_artifacts": [],
                    },
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "configs" / "docs_render_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "description": "Minimal public/generated doc outputs kept after the public-surface reduction; proof contracts live under configs.",
                "entries": [
                    {
                        "output_path": "configs/public_proof/storefront/proof-pack-index.json",
                        "mode": "full_render",
                        "source_inputs": [
                            "scripts/generate_storefront_proof_pack_index.py",
                            "configs/storefront_proof_bundle_registry.json",
                            "configs/public_proof/releases_assets/news-digest-proof-pack-2026-03-27.json",
                            "configs/public_proof/releases_assets/page-brief-proof-pack-2026-04-15.json",
                        ],
                        "contract_inputs": [
                            "configs/storefront_proof_bundle_registry.json",
                            "configs/public_proof/releases_assets/news-digest-proof-pack-2026-03-27.json",
                            "configs/public_proof/releases_assets/page-brief-proof-pack-2026-04-15.json",
                            "configs/public_proof/storefront/demo-status.md",
                            "configs/public_proof/storefront/live-capture-requirements.json",
                        ],
                        "generator": "python3 scripts/generate_storefront_proof_pack_index.py",
                        "freshness_strategy": "timestamp",
                        "authoritative_for": [
                            "public_storefront_proof_pack_index",
                        ],
                        "human_editable_regions": "none",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "configs" / "public_proof" / "storefront" / "live-capture-requirements.json").write_text(
        json.dumps(
            {
                "artifact_type": "openvibecoding_storefront_live_capture_requirements",
                "applies_to_bundle": "news_digest",
                "required_assets": [],
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
    generator.OUTPUT_PATH = root / "configs" / "public_proof" / "storefront" / "proof-pack-index.json"
    rendered = generator.build_index(generator._load_json(generator.REGISTRY_PATH))
    generator.OUTPUT_PATH.write_text(json.dumps(rendered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_storefront_proof_assets_gate_passes_with_expected_index(tmp_path: Path, monkeypatch) -> None:
    module = _load_gate_module()
    _write_fixture(tmp_path)
    module.ROOT = tmp_path
    module.REGISTRY_PATH = tmp_path / "configs" / "storefront_proof_bundle_registry.json"
    module.RENDER_MANIFEST_PATH = tmp_path / "configs" / "docs_render_manifest.json"
    module.PROOF_PACK_INDEX = tmp_path / "configs" / "public_proof" / "storefront" / "proof-pack-index.json"
    module.USE_CASES_PATH = tmp_path / "docs" / "use-cases" / "index.html"
    monkeypatch.setattr(sys, "argv", ["check_storefront_proof_assets.py"])
    assert module.main() == 0


def test_storefront_proof_assets_gate_fails_when_news_digest_loses_release_proven(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    module = _load_gate_module()
    _write_fixture(tmp_path)
    index_path = tmp_path / "configs" / "public_proof" / "storefront" / "proof-pack-index.json"
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    payload["bundles"][0]["proof_state"] = "showcase_only"
    index_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    module.ROOT = tmp_path
    module.REGISTRY_PATH = tmp_path / "configs" / "storefront_proof_bundle_registry.json"
    module.RENDER_MANIFEST_PATH = tmp_path / "configs" / "docs_render_manifest.json"
    module.PROOF_PACK_INDEX = index_path
    module.USE_CASES_PATH = tmp_path / "docs" / "use-cases" / "index.html"
    monkeypatch.setattr(sys, "argv", ["check_storefront_proof_assets.py"])

    rc = module.main()
    out = capsys.readouterr().out
    assert rc == 1
    assert "release_proven" in out


def test_storefront_proof_assets_gate_fails_when_page_brief_bundle_loses_pack_manifest(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    module = _load_gate_module()
    generator = _load_generator_module()
    _write_fixture(tmp_path)

    registry_path = tmp_path / "configs" / "storefront_proof_bundle_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["bundles"][2].pop("pack_manifest", None)
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    generator.ROOT = tmp_path
    generator.REGISTRY_PATH = registry_path
    generator.OUTPUT_PATH = tmp_path / "configs" / "public_proof" / "storefront" / "proof-pack-index.json"
    rendered = generator.build_index(generator._load_json(generator.REGISTRY_PATH))
    generator.OUTPUT_PATH.write_text(json.dumps(rendered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    module.ROOT = tmp_path
    module.REGISTRY_PATH = registry_path
    module.RENDER_MANIFEST_PATH = tmp_path / "configs" / "docs_render_manifest.json"
    module.PROOF_PACK_INDEX = generator.OUTPUT_PATH
    module.USE_CASES_PATH = tmp_path / "docs" / "use-cases" / "index.html"
    monkeypatch.setattr(sys, "argv", ["check_storefront_proof_assets.py"])

    rc = module.main()
    out = capsys.readouterr().out
    assert rc == 1
    assert "page_brief must reference a pack_manifest" in out


def test_storefront_proof_assets_gate_fails_when_topic_brief_claim_scope_drifts(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    module = _load_gate_module()
    generator = _load_generator_module()
    _write_fixture(tmp_path)

    registry_path = tmp_path / "configs" / "storefront_proof_bundle_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["bundles"][1]["claim_scope"] = "browser_backed_public_proof_bundle"
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    generator.ROOT = tmp_path
    generator.REGISTRY_PATH = registry_path
    generator.OUTPUT_PATH = tmp_path / "configs" / "public_proof" / "storefront" / "proof-pack-index.json"
    rendered = generator.build_index(generator._load_json(generator.REGISTRY_PATH))
    generator.OUTPUT_PATH.write_text(json.dumps(rendered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    module.ROOT = tmp_path
    module.REGISTRY_PATH = registry_path
    module.RENDER_MANIFEST_PATH = tmp_path / "configs" / "docs_render_manifest.json"
    module.PROOF_PACK_INDEX = generator.OUTPUT_PATH
    module.USE_CASES_PATH = tmp_path / "docs" / "use-cases" / "index.html"
    monkeypatch.setattr(sys, "argv", ["check_storefront_proof_assets.py"])

    rc = module.main()
    out = capsys.readouterr().out
    assert rc == 1
    assert "topic_brief must keep the public_showcase_path claim scope" in out


def test_storefront_proof_assets_gate_accepts_topic_brief_tracked_bundle_when_complete(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_gate_module()
    generator = _load_generator_module()
    _write_fixture(tmp_path)

    topic_pack_path = tmp_path / "configs" / "public_proof" / "releases_assets" / "topic-brief-proof-pack-2026-04-15.json"
    topic_pack_path.write_text(
        json.dumps(
            {
                "artifact_type": "topic_brief_public_proof_pack",
                "primary_assets": {
                    "proof_summary_markdown": "configs/public_proof/releases_assets/topic-brief-healthy-proof-2026-04-15.md",
                    "proof_summary_json": "configs/public_proof/releases_assets/topic-brief-healthy-proof-summary-2026-04-15.json",
                    "benchmark_summary_markdown": "configs/public_proof/releases_assets/topic-brief-benchmark-summary-2026-04-15.md",
                    "benchmark_summary_json": "configs/public_proof/releases_assets/topic-brief-benchmark-summary-2026-04-15.json",
                    "workflow_case_recap_markdown": "configs/public_proof/releases_assets/topic-brief-workflow-case-recap-2026-04-15.md",
                    "demo_status_markdown": "configs/public_proof/storefront/demo-status.md",
                },
                "supporting_assets": {},
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    for name in [
        "topic-brief-healthy-proof-2026-04-15.md",
        "topic-brief-healthy-proof-summary-2026-04-15.json",
        "topic-brief-benchmark-summary-2026-04-15.md",
        "topic-brief-benchmark-summary-2026-04-15.json",
        "topic-brief-workflow-case-recap-2026-04-15.md",
    ]:
        (tmp_path / "configs" / "public_proof" / "releases_assets" / name).write_text("ok\n", encoding="utf-8")

    registry_path = tmp_path / "configs" / "storefront_proof_bundle_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["bundles"][1]["proof_state"] = "proof_bundle_tracked"
    registry["bundles"][1]["claim_scope"] = "search_backed_public_proof_bundle"
    registry["bundles"][1]["authority_level"] = "repo_side_public_proof"
    registry["bundles"][1]["pack_manifest"] = "configs/public_proof/releases_assets/topic-brief-proof-pack-2026-04-15.json"
    registry["bundles"][1]["missing_expected_artifacts"] = []
    registry["bundles"][1]["safe_public_claims"] = ["topic_brief now has a tracked search-backed public proof bundle"]
    registry["bundles"][1]["forbidden_claims"] = ["topic_brief is the official first public baseline today"]
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    (tmp_path / "docs" / "use-cases" / "index.html").write_text(
        """
        <h1>First proven workflow and public proof pack</h1>
        <a href="../assets/storefront/proof-pack-index.json">Open proof-pack index</a>
        <p>topic_brief now has one tracked search-backed public proof bundle beside the official news_digest baseline.</p>
        <p>page_brief now has one tracked browser-backed public proof bundle beside the official news_digest baseline.</p>
        <p>The current benchmark story is a tracked single-run baseline, not a broad release average.</p>
        <p>Global proof-pack index across the official baseline, tracked bundle, and showcase bundles</p>
        <p>topic_brief is not yet equally release-proven with news_digest.</p>
        """,
        encoding="utf-8",
    )

    generator.ROOT = tmp_path
    generator.REGISTRY_PATH = registry_path
    generator.OUTPUT_PATH = tmp_path / "configs" / "public_proof" / "storefront" / "proof-pack-index.json"
    rendered = generator.build_index(generator._load_json(generator.REGISTRY_PATH))
    generator.OUTPUT_PATH.write_text(json.dumps(rendered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    module.ROOT = tmp_path
    module.REGISTRY_PATH = registry_path
    module.RENDER_MANIFEST_PATH = tmp_path / "configs" / "docs_render_manifest.json"
    module.PROOF_PACK_INDEX = generator.OUTPUT_PATH
    module.USE_CASES_PATH = tmp_path / "docs" / "use-cases" / "index.html"
    monkeypatch.setattr(sys, "argv", ["check_storefront_proof_assets.py"])

    assert module.main() == 0
