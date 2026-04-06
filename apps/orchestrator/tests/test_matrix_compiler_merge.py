from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "matrix_compiler_merge.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("matrix_compiler_merge", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_matrix_compiler_merge_accepts_legacy_chinese_fields() -> None:
    module = _load_module()
    row = module.MatrixRow.from_payload(
        {
            "list": "A",
            "id": "ROW-1",
            "问题": "legacy issue",
            "状态": "TODO",
            "证据路径": "evidence/path",
            "修复PR/测试命令": "pytest -q",
        },
        SCRIPT_PATH,
        1,
    )
    assert row.issue == "legacy issue"
    assert row.status == "TODO"
    assert row.evidence_path == "evidence/path"
    assert row.fix_ref == "pytest -q"


def test_matrix_compiler_merge_accepts_modern_english_fields() -> None:
    module = _load_module()
    row = module.MatrixRow.from_payload(
        {
            "list": "B",
            "id": "ROW-2",
            "issue": "modern issue",
            "status": "COVERED",
            "evidence_path": "evidence/path",
            "fix_ref": "python3 scripts/check.py",
        },
        SCRIPT_PATH,
        1,
    )
    assert row.issue == "modern issue"
    assert row.status == "COVERED"
    assert row.evidence_path == "evidence/path"
    assert row.fix_ref == "python3 scripts/check.py"


def test_matrix_compiler_merge_renders_english_headers() -> None:
    module = _load_module()
    output = module.render_master(
        [
            module.MatrixRow(
                list_name="A",
                row_id="ROW-1",
                issue="issue",
                status="TODO",
                evidence_path="evidence/path",
                fix_ref="pytest -q",
            )
        ]
    )
    assert "# Matrix-Compiler Master Table (49/70/68/52)" in output
    assert "## Summary" in output
    assert "| list | id | issue | status | evidence_path | fix_ref |" in output
