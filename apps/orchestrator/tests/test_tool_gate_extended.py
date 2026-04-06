import json
from pathlib import Path

import pytest

from cortexpilot_orch.gates.tool_gate import validate_command
from cortexpilot_orch.gates.tool_gate import run_tool_gate


def _write_allowlist(root: Path, allow: list[dict] | None = None, deny: list[str] | None = None) -> None:
    policies = root / "policies"
    policies.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": "v1",
        "allow": allow or [],
        "deny_substrings": deny or [],
    }
    (policies / "command_allowlist.json").write_text(json.dumps(payload), encoding="utf-8")


def test_tool_gate_invalid_command() -> None:
    result = validate_command('echo "unterminated', [])
    assert result["ok"] is False
    assert result["reason"] == "invalid command"


def test_tool_gate_default_forbidden_actions(tmp_path: Path) -> None:
    _write_allowlist(tmp_path, allow=[{"exec": "rm", "argv_prefixes": [["rm"]]}], deny=[])
    policies = tmp_path / "policies"
    (policies / "forbidden_actions.json").write_text(
        json.dumps({"version": "v1", "forbidden_actions": ["rm -rf"]}),
        encoding="utf-8",
    )
    result = validate_command("rm -rf /", [], repo_root=tmp_path)
    assert result["ok"] is False
    assert result["reason"] == "command contains forbidden action"


def test_tool_gate_invalid_network_policy(tmp_path: Path) -> None:
    _write_allowlist(tmp_path, allow=[{"exec": "git", "argv_prefixes": [["git"]]}])
    result = validate_command("git status", [], network_policy="weird", repo_root=tmp_path)
    assert result["ok"] is False
    assert result["reason"] == "invalid network policy"


def test_tool_gate_network_on_request_approved(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CORTEXPILOT_NETWORK_APPROVED", "1")
    _write_allowlist(tmp_path, allow=[{"exec": "curl", "argv_prefixes": [["curl"]]}])
    result = validate_command("curl https://example.com", [], network_policy="on-request", repo_root=tmp_path)
    assert result["ok"] is True


def test_tool_gate_network_on_request_denied(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("CORTEXPILOT_NETWORK_APPROVED", raising=False)
    _write_allowlist(tmp_path, allow=[{"exec": "curl", "argv_prefixes": [["curl"]]}])
    result = validate_command("curl https://example.com", [], network_policy="on-request", repo_root=tmp_path)
    assert result["ok"] is False
    assert result["reason"] == "network access blocked by policy"


def test_tool_gate_blocks_interactive_commands(tmp_path: Path) -> None:
    _write_allowlist(tmp_path, allow=[{"exec": "sudo", "argv_prefixes": [["sudo"]]}])
    result = validate_command("sudo ls", [], repo_root=tmp_path)
    assert result["ok"] is False
    assert result["reason"] == "interactive commands are not allowed"


def test_tool_gate_blocks_shell_operators(tmp_path: Path) -> None:
    _write_allowlist(tmp_path, allow=[{"exec": "echo", "argv_prefixes": [["echo"]]}])
    result = validate_command("echo ok; rm -rf /", [], repo_root=tmp_path)
    assert result["ok"] is False
    assert result["reason"] == "shell operators are not allowed"


def test_tool_gate_allows_quoted_operators(tmp_path: Path) -> None:
    _write_allowlist(tmp_path, allow=[{"exec": "echo", "argv_prefixes": [["echo"]]}])
    result = validate_command('echo "a; b"', [], repo_root=tmp_path)
    assert result["ok"] is True


def test_tool_gate_repo_root_required_for_paths() -> None:
    result = validate_command("./scripts/tool.sh", [], repo_root=None)
    assert result["ok"] is False
    assert result["reason"] == "command path requires repo_root"


def test_tool_gate_path_not_found_and_directory(tmp_path: Path) -> None:
    _write_allowlist(tmp_path, allow=[{"exec": "missing.sh", "argv_prefixes": [["missing.sh"]]}])
    missing = validate_command("scripts/missing.sh", [], repo_root=tmp_path)
    assert missing["ok"] is False
    assert missing["reason"] == "command path not found"

    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    as_dir = validate_command("scripts/", [], repo_root=tmp_path)
    assert as_dir["ok"] is False
    assert as_dir["reason"] == "command path is directory"


def test_tool_gate_run_tool_gate() -> None:
    result = run_tool_gate("echo ok", [])
    assert result["ok"] is True


def test_tool_gate_allows_python_module(monkeypatch, tmp_path: Path) -> None:
    _write_allowlist(tmp_path, allow=[{"exec": "python", "argv_prefixes": [["python", "-m", "cortexpilot_orch.cli"]]}])
    result = validate_command("python -m cortexpilot_orch.cli", [], repo_root=tmp_path)
    assert result["ok"] is True


def test_tool_gate_allows_python_script_in_repo(monkeypatch, tmp_path: Path) -> None:
    _write_allowlist(tmp_path, allow=[{"exec": "python", "argv_prefixes": [["python"]]}])
    script_dir = tmp_path / "scripts"
    script_dir.mkdir()
    script = script_dir / "job.py"
    script.write_text("print('ok')\n", encoding="utf-8")
    result = validate_command("python scripts/job.py", [], repo_root=tmp_path)
    assert result["ok"] is True


def test_tool_gate_blocks_script_outside_repo(monkeypatch, tmp_path: Path) -> None:
    _write_allowlist(tmp_path, allow=[{"exec": "python", "argv_prefixes": [["python"]]}])
    outside = tmp_path.parent / "evil.py"
    outside.write_text("print('no')\n", encoding="utf-8")
    result = validate_command(f"python {outside}", [], repo_root=tmp_path)
    assert result["ok"] is False
    assert result["reason"] == "script path outside repo"


def test_tool_gate_allows_managed_toolchain_python_outside_worktree(monkeypatch, tmp_path: Path) -> None:
    actual_repo_root = tmp_path / "repo"
    worktree_root = tmp_path / "worktree"
    toolchain_bin = actual_repo_root / ".runtime-cache" / "cache" / "toolchains" / "python" / "current" / "bin"
    toolchain_bin.mkdir(parents=True, exist_ok=True)
    worktree_root.mkdir(parents=True, exist_ok=True)
    _write_allowlist(worktree_root, allow=[{"exec": "python", "argv_prefixes": [["python", "-m", "pytest"]]}])
    python_bin = toolchain_bin / "python"
    python_bin.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    python_bin.chmod(0o755)
    monkeypatch.setattr("cortexpilot_orch.gates.tool_gate._repo_root", lambda: actual_repo_root)

    result = validate_command(
        f'"{python_bin}" -m pytest apps/orchestrator/tests/test_schema_validation.py -q',
        [],
        repo_root=worktree_root,
    )

    assert result["ok"] is True


def test_tool_gate_blocks_missing_script(monkeypatch, tmp_path: Path) -> None:
    _write_allowlist(tmp_path, allow=[{"exec": "node", "argv_prefixes": [["node"]]}])
    result = validate_command("node scripts/missing.js", [], repo_root=tmp_path)
    assert result["ok"] is False
    assert result["reason"] == "script path not found"


def test_tool_gate_blocks_eval_long_flag(monkeypatch, tmp_path: Path) -> None:
    _write_allowlist(tmp_path, allow=[{"exec": "node", "argv_prefixes": [["node"]]}])
    result = validate_command("node --eval \"1+1\"", [], repo_root=tmp_path)
    assert result["ok"] is False


def test_tool_gate_policy_pack_forbidden_actions(tmp_path: Path) -> None:
    _write_allowlist(tmp_path, allow=[{"exec": "git", "argv_prefixes": [["git"]]}])
    packs_dir = tmp_path / "policies" / "packs"
    packs_dir.mkdir(parents=True, exist_ok=True)
    (packs_dir / "high.json").write_text(
        json.dumps(
            {
                "version": "v1",
                "allow": [{"exec": "git", "argv_prefixes": [["git"]]}],
                "deny_substrings": [],
                "forbidden_actions": ["git push"],
            }
        ),
        encoding="utf-8",
    )
    result = validate_command("git push origin main", [], policy_pack="high", repo_root=tmp_path)
    assert result["ok"] is False
    assert result["reason"] == "command contains forbidden action"


def test_tool_gate_policy_pack_allows_scoped_commit_script(tmp_path: Path) -> None:
    _write_allowlist(tmp_path, allow=[{"exec": "echo", "argv_prefixes": [["echo"]]}])
    packs_dir = tmp_path / "policies" / "packs"
    packs_dir.mkdir(parents=True, exist_ok=True)
    (tmp_path / "scripts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "scripts" / "coverage_self_heal_commit.sh").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    (tmp_path / "scripts" / "other.sh").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    (packs_dir / "high.json").write_text(
        json.dumps(
            {
                "version": "v1",
                "allow": [
                    {"exec": "bash", "argv_prefixes": [["bash", "scripts/coverage_self_heal_commit.sh"]]},
                ],
                "deny_substrings": [],
                "forbidden_actions": [],
            }
        ),
        encoding="utf-8",
    )

    allowed = validate_command(
        "bash scripts/coverage_self_heal_commit.sh --message 'ok' --output .runtime-cache/test_output/worker_markers/commit.txt",
        [],
        policy_pack="high",
        repo_root=tmp_path,
    )
    blocked = validate_command("bash scripts/other.sh", [], policy_pack="high", repo_root=tmp_path)

    assert allowed["ok"] is True
    assert blocked["ok"] is False
    assert blocked["reason"] == "command not in allowlist"


def test_tool_gate_allows_coverage_verify_script_under_medium_pack(tmp_path: Path) -> None:
    _write_allowlist(tmp_path, allow=[{"exec": "echo", "argv_prefixes": [["echo"]]}])
    packs_dir = tmp_path / "policies" / "packs"
    packs_dir.mkdir(parents=True, exist_ok=True)
    (packs_dir / "medium.json").write_text(
        json.dumps(
            {
                "version": "v1",
                "allow": [{"exec": "bash", "argv_prefixes": [["bash"]]}],
                "deny_substrings": [],
                "forbidden_actions": [],
            }
        ),
        encoding="utf-8",
    )

    scripts = tmp_path / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    verify_script = scripts / "coverage_self_heal_verify_test.sh"
    verify_script.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")

    tests_dir = tmp_path / "apps" / "orchestrator" / "tests" / "self_heal"
    tests_dir.mkdir(parents=True, exist_ok=True)
    target_test = tests_dir / "test_cov_demo.py"
    target_test.write_text(
        "def _sum(a, b):\n"
        "    return a + b\n\n"
        "def test_demo():\n"
        "    assert _sum(1, 2) == 3\n",
        encoding="utf-8",
    )

    result = validate_command(
        "bash scripts/coverage_self_heal_verify_test.sh apps/orchestrator/tests/self_heal/test_cov_demo.py",
        [],
        policy_pack="medium",
        repo_root=tmp_path,
    )

    assert result["ok"] is True


def test_tool_gate_blocks_interpreter_by_policy(monkeypatch, tmp_path: Path) -> None:
    _write_allowlist(tmp_path, allow=[{"exec": "python", "argv_prefixes": [["python"]]}])
    script_dir = tmp_path / "scripts"
    script_dir.mkdir()
    script = script_dir / "job.py"
    script.write_text("print('ok')\n", encoding="utf-8")
    result = validate_command("python scripts/job.py", [], network_policy="deny", repo_root=tmp_path)
    assert result["ok"] is True
