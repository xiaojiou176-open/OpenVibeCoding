from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "sync_ui_button_matrix.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("sync_ui_button_matrix", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_sync_ui_button_matrix_header_defaults_to_english() -> None:
    module = _load_module()
    assert "`ui-button-coverage-matrix.md` is the render-only reference" in module.HEADER
    assert "Refresh the button inventory" in module.FOOTER
    assert "This file is generated output only" in module.HEADER


def test_sync_ui_button_matrix_build_rows_preserves_existing_status_logic() -> None:
    module = _load_module()
    rows = module.build_rows(
        [
            {
                "id": "btn-dashboard-1",
                "surface": "dashboard",
                "tier": "P1",
                "file": "apps/dashboard/app/example.tsx",
                "line": 12,
                "text": "Refresh",
                "aria_label": "",
                "on_click": "reload()",
                "tag": "button",
            }
        ],
        {
            "btn-dashboard-1": {
                "status": "COVERED",
                "notes": "real coverage evidence",
                "evidence_type": "unit_test",
                "source_path": "apps/dashboard/tests/example.test.tsx",
                "source_kind": "unit_test",
            }
        },
    )
    assert len(rows) == 1
    assert "COVERED" in rows[0]
    assert "unit_test" in rows[0]
