from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_gate_module() -> object:
    script_path = Path(__file__).resolve().parents[3] / "scripts" / "check_frontdoor_contract.py"
    spec = importlib.util.spec_from_file_location("openvibecoding_frontdoor_contract_gate", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _write_frontdoor_fixture(root: Path) -> None:
    (root / "docs" / "use-cases").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "compatibility").mkdir(parents=True, exist_ok=True)

    (root / "README.md").write_text(
        """
        Machine-readable proof ledgers now belong under `configs/public_proof/`.
        The public reading path stays on the use-cases page instead of raw ledger files or `docs/README.md`.
        """,
        encoding="utf-8",
    )
    (root / "docs" / "README.md").write_text(
        """
        This file is not the public proof router.
        Keep machine-readable proof ledgers under `configs/public_proof/`
        for tooling and audits instead of turning `docs/README.md` into a human path toward raw proof metadata.
        """,
        encoding="utf-8",
    )

    (root / "docs" / "index.html").write_text(
        """
        <a href="./use-cases/">See the first proven workflow</a>
        <a href="./compatibility/">Choose the right adoption path</a>
        <p>repo-backed operator control plane, not a hosted product</p>
        <p>shipped MCP surface remains read-only</p>
        <p>news_digest topic_brief page_brief</p>
        """,
        encoding="utf-8",
    )
    (root / "docs" / "use-cases" / "index.html").write_text(
        """
        <h1>First proven workflow and public proof pack</h1>
        <p>news_digest is the only official release-proven public baseline.</p>
        <p>topic_brief and page_brief are not yet equally release-proven.</p>
        <p>What we still do not claim</p>
        <p>This page summarizes the repo-tracked public proof bundle instead of deep-linking every raw ledger file.</p>
        <p>Proof you can rely on today</p>
        <p>Machine-readable proof metadata now lives under configs/public_proof/ for tooling and audits, while this page stays the human-facing proof summary.</p>
        """,
        encoding="utf-8",
    )
    (root / "docs" / "compatibility" / "index.html").write_text(
        """
        <h1>One truthful compatibility matrix for modern coding-agent teams.</h1>
        <p>read-only MCP</p>
        <a href="../use-cases/">See the first proven workflow</a>
        """,
        encoding="utf-8",
    )

def test_frontdoor_contract_gate_passes_with_required_surfaces(tmp_path: Path, monkeypatch) -> None:
    module = _load_gate_module()
    _write_frontdoor_fixture(tmp_path)
    module.ROOT = tmp_path
    module.README_PATH = tmp_path / "README.md"
    module.DOCS_README_PATH = tmp_path / "docs" / "README.md"
    module.INDEX_PATH = tmp_path / "docs" / "index.html"
    module.USE_CASES_PATH = tmp_path / "docs" / "use-cases" / "index.html"
    module.COMPATIBILITY_PATH = tmp_path / "docs" / "compatibility" / "index.html"
    monkeypatch.setattr(sys, "argv", ["check_frontdoor_contract.py"])
    assert module.main() == 0


def test_frontdoor_contract_gate_fails_when_public_proof_bundle_text_drifts(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    module = _load_gate_module()
    _write_frontdoor_fixture(tmp_path)
    use_cases = tmp_path / "docs" / "use-cases" / "index.html"
    use_cases.write_text(
        use_cases.read_text(encoding="utf-8").replace(
            "Proof you can rely on today", "Proof files you can inspect today"
        ),
        encoding="utf-8",
    )
    module.ROOT = tmp_path
    module.README_PATH = tmp_path / "README.md"
    module.DOCS_README_PATH = tmp_path / "docs" / "README.md"
    module.INDEX_PATH = tmp_path / "docs" / "index.html"
    module.USE_CASES_PATH = use_cases
    module.COMPATIBILITY_PATH = tmp_path / "docs" / "compatibility" / "index.html"
    monkeypatch.setattr(sys, "argv", ["check_frontdoor_contract.py"])

    rc = module.main()
    out = capsys.readouterr().out
    assert rc == 1
    assert "Proof you can rely on today" in out
