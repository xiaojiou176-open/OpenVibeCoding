from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_gate_module() -> object:
    script_path = Path(__file__).resolve().parents[3] / "scripts" / "check_docs_manual_fact_boundary.py"
    spec = importlib.util.spec_from_file_location("cortexpilot_docs_fact_boundary_gate", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_docs_fact_boundary_gate_reads_active_entries_from_registry(tmp_path: Path) -> None:
    module = _load_gate_module()

    root = tmp_path
    docs_root = root / "docs"
    docs_root.mkdir(parents=True)
    target = docs_root / "policy.md"
    target.write_text("safe content\n", encoding="utf-8")

    registry_path = root / "configs" / "docs_nav_registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "path": "docs/policy.md",
                        "status": "active",
                        "canonical": True,
                        "generated": False,
                    },
                    {
                        "path": "docs/generated.md",
                        "status": "active",
                        "canonical": True,
                        "generated": True,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    module.ROOT = root
    module.DOCS_NAV_REGISTRY = registry_path
    module.WRAPPER_TARGETS = ()

    targets = module._iter_registry_targets()
    assert targets == [target]


def test_docs_fact_boundary_gate_fails_closed_when_registry_entries_missing(tmp_path: Path, capsys, monkeypatch) -> None:
    module = _load_gate_module()

    root = tmp_path
    registry_path = root / "configs" / "docs_nav_registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps({"documents": []}), encoding="utf-8")

    module.ROOT = root
    module.DOCS_NAV_REGISTRY = registry_path
    module.WRAPPER_TARGETS = ()
    monkeypatch.setattr(sys, "argv", ["check_docs_manual_fact_boundary.py"])

    rc = module.main()
    out = capsys.readouterr().out
    assert rc == 1
    assert "invalid docs navigation registry" in out
