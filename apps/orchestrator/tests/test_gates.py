import json
import subprocess
from pathlib import Path

from cortexpilot_orch.gates.diff_gate import validate_diff
from cortexpilot_orch.gates.tool_gate import validate_command
from cortexpilot_orch.gates.mcp_concurrency_gate import validate_mcp_concurrency
from cortexpilot_orch.gates.mcp_gate import validate_mcp_tools
from cortexpilot_orch.gates.tests_gate import run_acceptance_tests


def _write_allowlist(root: Path, allow: list[dict] | None = None) -> None:
    policies = root / "policies"
    policies.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": "v1",
        "allow": allow or [],
        "deny_substrings": ["rm -rf", "sudo", "ssh ", "scp ", "sftp ", "curl ", "wget "],
    }
    (policies / "command_allowlist.json").write_text(json.dumps(payload), encoding="utf-8")


def _git(cmd: list[str], cwd: Path) -> None:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def _init_repo(repo: Path) -> None:
    _git(["git", "init"], cwd=repo)
    _git(["git", "config", "user.email", "test@example.com"], cwd=repo)
    _git(["git", "config", "user.name", "tester"], cwd=repo)


def test_diff_gate(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / "README.md").write_text("hello", encoding="utf-8")
    _git(["git", "add", "README.md"], cwd=repo)
    _git(["git", "commit", "-m", "init"], cwd=repo)

    (repo / "README.md").write_text("changed", encoding="utf-8")
    result = validate_diff(repo, ["src/"], baseline_ref="HEAD")
    assert result["ok"] is False

    result = validate_diff(repo, ["README.md"], baseline_ref="HEAD")
    assert result["ok"] is True


def test_diff_gate_protected_files(tmp_path: Path):
    repo = tmp_path / "repo_protected"
    repo.mkdir()
    _init_repo(repo)
    (repo / ".gitignore").write_text(".runtime-cache\n", encoding="utf-8")
    _git(["git", "add", ".gitignore"], cwd=repo)
    _git(["git", "commit", "-m", "init"], cwd=repo)

    (repo / ".gitignore").write_text(".runtime-cache\nnode_modules\n", encoding="utf-8")
    result = validate_diff(repo, [".gitignore"], baseline_ref="HEAD")
    assert result["ok"] is False
    assert result["reason"] == "protected files modified"


def test_tool_gate():
    result = validate_command("rm -rf /", ["rm -rf"]) 
    assert result["ok"] is False


def test_tests_gate(tmp_path: Path):
    _write_allowlist(
        tmp_path,
        allow=[
            {"exec": "echo", "argv_prefixes": [["echo"]]},
            {"exec": "sh", "argv_prefixes": [["sh"]]},
            {"exec": "curl", "argv_prefixes": [["curl"]]},
        ],
    )
    ok = run_acceptance_tests(tmp_path, ["echo governance-check"])
    assert ok["ok"] is True

    fail = run_acceptance_tests(tmp_path, ["sh -c \"exit 1\""])
    assert fail["ok"] is False

    blocked = run_acceptance_tests(tmp_path, ["rm -rf /"], forbidden_actions=["rm -rf"])
    assert blocked["ok"] is False

    network_blocked = run_acceptance_tests(
        tmp_path,
        ["curl http://example.com"],
        network_policy="deny",
    )
    assert network_blocked["ok"] is False


def test_mcp_concurrency_gate():
    assert validate_mcp_concurrency("single")["ok"] is True
    assert validate_mcp_concurrency("multi")["ok"] is False
    assert validate_mcp_concurrency("weird")["ok"] is False


def test_mcp_global_allowlist(tmp_path: Path) -> None:
    policies = tmp_path / "policies"
    policies.mkdir(parents=True, exist_ok=True)
    (policies / "mcp_allowlist.json").write_text(
        json.dumps({"version": "v1", "allow": ["codex"], "deny": []}),
        encoding="utf-8",
    )
    ok = validate_mcp_tools(["codex", "sampling"], ["codex"], repo_root=tmp_path)
    assert ok["ok"] is True
    blocked = validate_mcp_tools(["sampling"], ["sampling"], repo_root=tmp_path)
    assert blocked["ok"] is False
