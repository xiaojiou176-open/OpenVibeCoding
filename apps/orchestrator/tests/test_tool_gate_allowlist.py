import json
from pathlib import Path

from openvibecoding_orch.gates.tool_gate import validate_command


def _write_allowlist(root: Path, allow: list[dict] | None = None, deny: list[str] | None = None) -> None:
    policies = root / "policies"
    policies.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": "v1",
        "allow": allow or [],
        "deny_substrings": deny or [],
    }
    (policies / "command_allowlist.json").write_text(json.dumps(payload), encoding="utf-8")


def test_tool_gate_blocks_non_allowlisted_command(tmp_path: Path, monkeypatch) -> None:
    _write_allowlist(tmp_path, allow=[{"exec": "git", "argv_prefixes": [["git"]]}])
    result = validate_command("rm -rf /", [], repo_root=tmp_path)
    assert result["ok"] is False
    assert result["reason"] == "command not in allowlist"


def test_tool_gate_blocks_inline_exec(monkeypatch, tmp_path: Path) -> None:
    _write_allowlist(tmp_path, allow=[{"exec": "python", "argv_prefixes": [["python"]]}])
    result = validate_command("python -c \"print(1)\"", [], repo_root=tmp_path)
    assert result["ok"] is False
    assert result["reason"] == "inline execution not allowed"


def test_tool_gate_blocks_shell_inline_exec(monkeypatch, tmp_path: Path) -> None:
    _write_allowlist(tmp_path, allow=[{"exec": "bash", "argv_prefixes": [["bash"]]}])
    result = validate_command("bash -c \"echo ok\"", [], repo_root=tmp_path)
    assert result["ok"] is False
    assert result["reason"] == "inline execution not allowed"


def test_tool_gate_allows_repo_script(tmp_path: Path, monkeypatch) -> None:
    _write_allowlist(tmp_path, allow=[{"exec": "bash", "argv_prefixes": [["bash"]]}])
    script = tmp_path / "scripts"
    script.mkdir()
    tool = script / "echo.sh"
    tool.write_text("#!/usr/bin/env bash\necho ok\n", encoding="utf-8")
    result = validate_command(f"bash {tool.relative_to(tmp_path)}", [], repo_root=tmp_path)
    assert result["ok"] is True


def test_tool_gate_allows_prefix_patterns(tmp_path: Path) -> None:
    _write_allowlist(tmp_path, allow=[{"exec": "bash", "argv_prefixes": [["bash", "scripts/"]]}])
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    tool = scripts_dir / "echo.sh"
    tool.write_text("#!/usr/bin/env bash\necho ok\n", encoding="utf-8")
    result = validate_command("bash scripts/echo.sh", [], repo_root=tmp_path)
    assert result["ok"] is True


def test_tool_gate_blocks_outside_repo_path(tmp_path: Path, monkeypatch) -> None:
    _write_allowlist(tmp_path, allow=[{"exec": "git", "argv_prefixes": [["git"]]}])
    result = validate_command("/bin/ls", [], repo_root=tmp_path)
    assert result["ok"] is False
    assert result["reason"] == "command path outside repo"
