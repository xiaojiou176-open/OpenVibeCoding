from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from openvibecoding_orch.gates.mcp_gate import validate_mcp_tools
from openvibecoding_orch.gates.reviewer_gate import snapshot_worktree, validate_reviewer_isolation
from openvibecoding_orch.gates.tool_gate import validate_command
from openvibecoding_orch.runners import mcp_adapter_runtime
from openvibecoding_orch.runners.mcp_adapter_runtime import execute_mcp_adapter
from openvibecoding_orch.scheduler import policy_pipeline
from tooling.mcp.adapter import sanitize_mcp_payload


def _git(cmd: list[str], cwd: Path) -> None:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(["git", "init"], cwd=repo)
    _git(["git", "config", "user.email", "test@example.com"], cwd=repo)
    _git(["git", "config", "user.name", "tester"], cwd=repo)


def test_mcp_payload_is_redacted() -> None:
    synthetic_api_key = "sk-" + ("A" * 22)
    synthetic_gh_token = "ghp_" + "12345678901234567890"
    payload = {
        "token": "abc",
        "nested": {"api_key": synthetic_api_key, "ok": "value"},
        "message": f"prefix {synthetic_gh_token} suffix",
        "arr": [{"password": "x"}],
    }
    sanitized = sanitize_mcp_payload(payload)
    assert sanitized["token"] == "[REDACTED]"
    assert sanitized["nested"]["api_key"] == "[REDACTED]"
    assert sanitized["nested"]["ok"] == "value"
    assert "[REDACTED]" in sanitized["message"]
    assert sanitized["arr"][0]["password"] == "[REDACTED]"


def test_mcp_gate_fail_closed_on_invalid_allowlist(tmp_path: Path) -> None:
    policies = tmp_path / "policies"
    policies.mkdir(parents=True, exist_ok=True)
    (policies / "mcp_allowlist.json").write_text("{", encoding="utf-8")

    result = validate_mcp_tools(["codex"], ["codex"], repo_root=tmp_path)

    assert result["ok"] is False
    assert result["reason"] == "mcp allowlist invalid"
    assert "parse error" in result.get("error", "")


def test_reviewer_gate_detects_ignored_critical_file_changes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / ".gitignore").write_text(".env.secret\n", encoding="utf-8")
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    _git(["git", "add", ".gitignore", "README.md"], cwd=repo)
    _git(["git", "commit", "-m", "init"], cwd=repo)

    ignored_critical = repo / ".env.secret"
    ignored_critical.write_text("token=old\n", encoding="utf-8")
    snapshot = snapshot_worktree(repo)

    ignored_critical.write_text("token=new\n", encoding="utf-8")
    result = validate_reviewer_isolation(repo, snapshot)

    assert result["ok"] is False
    assert any(item["path"] == ".env.secret" for item in result["changed"])


def test_restricted_role_mcp_tools_are_converged() -> None:
    filesystem_order = {"read-only": 0, "workspace-write": 1, "danger-full-access": 2}
    shell_order = {"never": 0, "on-failure": 1, "untrusted": 2, "on-request": 3}
    network_order = {"deny": 0, "on-request": 1, "allow": 2}
    contract = {
        "assigned_agent": {"role": "REVIEWER", "agent_id": "r-1"},
        "tool_permissions": {"mcp_tools": ["open_interpreter", "codex"]},
    }
    registry = {
        "agents": [
            {
                "role": "REVIEWER",
                "agent_id": "r-1",
                "defaults": {"sandbox": "read-only", "approval_policy": "never", "network": "deny"},
            }
        ]
    }

    updated, violations = policy_pipeline.apply_role_defaults(
        contract=contract,
        registry=registry,
        filesystem_order=filesystem_order,
        shell_order=shell_order,
        network_order=network_order,
    )

    assert updated["mcp_tools"] == []
    assert "tool_permissions.mcp_tools" in violations


def test_mcp_adapter_accepts_shell_on_request_semantics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mcp_adapter_runtime, "validate_command", lambda *args, **kwargs: {"ok": True})
    monkeypatch.setattr(
        mcp_adapter_runtime.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=args, returncode=0, stdout="ok", stderr=""),
    )

    result = execute_mcp_adapter(
        "aider",
        {"command": "aider --help"},
        {"tool_permissions": {"shell": "on-request", "network": "deny"}},
        repo_root=tmp_path,
    )

    assert result["ok"] is True


def test_low_policy_pack_blocks_git_push(tmp_path: Path) -> None:
    policies = tmp_path / "policies"
    packs = policies / "packs"
    packs.mkdir(parents=True, exist_ok=True)

    (policies / "command_allowlist.json").write_text(
        json.dumps(
            {
                "version": "v1",
                "allow": [{"exec": "git", "argv_prefixes": [["git"]]}],
                "deny_substrings": [],
            }
        ),
        encoding="utf-8",
    )

    low_pack = REPO_ROOT / "policies" / "packs" / "low.json"
    (packs / "low.json").write_text(low_pack.read_text(encoding="utf-8"), encoding="utf-8")

    result = validate_command("git push origin main", [], policy_pack="low", repo_root=tmp_path)

    assert result["ok"] is False
    assert result["reason"] == "command contains forbidden action"
