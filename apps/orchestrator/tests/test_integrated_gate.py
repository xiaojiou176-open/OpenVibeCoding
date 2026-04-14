from __future__ import annotations

import json
from pathlib import Path

from openvibecoding_orch.gates.integrated_gate import validate_integrated_tools


def test_integrated_gate_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OPENVIBECODING_TOOL_REGISTRY", raising=False)
    repo_root = tmp_path
    tools_dir = repo_root / "tooling"
    tools_dir.mkdir(parents=True, exist_ok=True)
    registry = {
        "installed": ["codex", "search"],
        "integrated": ["codex"],
    }
    (tools_dir / "registry.json").write_text(json.dumps(registry), encoding="utf-8")

    result = validate_integrated_tools(repo_root, ["codex", "search"])
    assert result["ok"] is False
    assert "search" in result["missing"]


def test_integrated_gate_ok(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OPENVIBECODING_TOOL_REGISTRY", raising=False)
    repo_root = tmp_path
    tools_dir = repo_root / "tooling"
    tools_dir.mkdir(parents=True, exist_ok=True)
    registry = {
        "installed": ["codex", "search"],
        "integrated": ["codex", "search"],
    }
    (tools_dir / "registry.json").write_text(json.dumps(registry), encoding="utf-8")

    result = validate_integrated_tools(repo_root, ["codex", "search"])
    assert result["ok"] is True
