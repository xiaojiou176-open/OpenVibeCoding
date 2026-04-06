from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "codex_jsonl_pipeline_markdown.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("codex_jsonl_pipeline_markdown", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load module from {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_validate_markdown_accepts_legacy_chinese_headings() -> None:
    mod = _load_module()
    legacy = """## 轮次提炼
### Turn 1
#### 用户诉求深度分析
- a
#### 用户情绪与态度
- b
#### Codex 响应深度分析
- c
#### 后续行动建议
- d
#### 交互效率评估
- e

## 总体观察
- x
"""

    valid, reason, _ = mod.validate_markdown_text(legacy, ["1"], require_overall_section=True)

    assert valid is True, reason


def test_validate_markdown_accepts_modern_english_headings() -> None:
    mod = _load_module()
    modern = """## Turn-by-Turn Analysis
### Turn 1
#### User Request Analysis
- a
#### User Tone And Attitude
- b
#### Codex Response Analysis
- c
#### Next Action Suggestion
- d
#### Interaction Efficiency
- e

## Overall Findings
- x
"""

    valid, reason, _ = mod.validate_markdown_text(modern, ["1"], require_overall_section=True)

    assert valid is True, reason


def test_compose_chunked_markdown_uses_english_output_contract(tmp_path: Path) -> None:
    mod = _load_module()
    jsonl_path = tmp_path / "sample.jsonl"
    jsonl_path.write_text("", encoding="utf-8")

    markdown = mod.compose_chunked_markdown(
        jsonl_path=jsonl_path,
        root=tmp_path,
        expected_turn_ids=["1"],
        turn_sections={"1": "#### User Request Analysis\n- a\n#### User Tone And Attitude\n- b\n#### Codex Response Analysis\n- c\n#### Next Action Suggestion\n- d\n#### Interaction Efficiency\n- e\n"},
    )

    assert "# Conversation Audit Report:" in markdown
    assert "## File Information" in markdown
    assert "## Turn-by-Turn Analysis" in markdown
    assert "## Overall Findings" in markdown
