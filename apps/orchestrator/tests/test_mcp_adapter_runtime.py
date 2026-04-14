from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from openvibecoding_orch.runners import mcp_adapter_runtime
from openvibecoding_orch.runners.mcp_adapter_runtime import execute_mcp_adapter, normalize_adapter_tool


def test_normalize_adapter_tool_open_interpreter_alias() -> None:
    assert normalize_adapter_tool("open-interpreter") == "open_interpreter"
    assert normalize_adapter_tool("open_interpreter") == "open_interpreter"
    assert normalize_adapter_tool("   ") is None


def test_execute_mcp_adapter_denies_shell_never(tmp_path: Path) -> None:
    result = execute_mcp_adapter(
        "aider",
        {"args": ["--help"]},
        {"tool_permissions": {"shell": "never", "network": "deny"}},
        repo_root=tmp_path,
    )

    assert result["ok"] is False
    assert result["reason"] == "shell tool denied"
    assert result["error"] == "shell tool denied"


def test_execute_mcp_adapter_denies_unknown_shell_policy(tmp_path: Path) -> None:
    result = execute_mcp_adapter(
        "aider",
        {"args": ["--help"]},
        {"tool_permissions": {"shell": "mystery-policy", "network": "deny"}},
        repo_root=tmp_path,
    )

    assert result["ok"] is False
    assert result["reason"] == "shell tool denied"
    assert result["error"] == "shell tool denied"


def test_execute_mcp_adapter_rejects_unsupported_tool(tmp_path: Path) -> None:
    result = execute_mcp_adapter(
        "not-a-real-adapter",
        {"args": ["--help"]},
        {"tool_permissions": {"shell": "allow", "network": "deny"}},
        repo_root=tmp_path,
    )

    assert result["ok"] is False
    assert result["reason"] == "unsupported adapter tool"


def test_execute_mcp_adapter_rejects_command_mismatch(tmp_path: Path) -> None:
    result = execute_mcp_adapter(
        "aider",
        {"command": "continue --help"},
        {"tool_permissions": {"shell": "allow", "network": "deny"}},
        repo_root=tmp_path,
    )

    assert result["ok"] is False
    assert result["reason"] == "adapter command mismatch"


def test_execute_mcp_adapter_rejects_invalid_command_syntax(tmp_path: Path) -> None:
    result = execute_mcp_adapter(
        "aider",
        {"command": '"unterminated'},
        {"tool_permissions": {"shell": "allow", "network": "deny"}},
        repo_root=tmp_path,
    )

    assert result["ok"] is False
    assert result["reason"] == "invalid command"


def test_execute_mcp_adapter_rejects_cwd_outside_repo(tmp_path: Path) -> None:
    result = execute_mcp_adapter(
        "aider",
        {"command": "aider --help", "cwd": "/"},
        {"tool_permissions": {"shell": "allow", "network": "deny"}},
        repo_root=tmp_path,
    )

    assert result["ok"] is False
    assert result["reason"] == "cwd outside repo"


def test_execute_mcp_adapter_rejects_cwd_not_found(tmp_path: Path) -> None:
    result = execute_mcp_adapter(
        "aider",
        {"command": "aider --help", "cwd": "missing-dir"},
        {"tool_permissions": {"shell": "allow", "network": "deny"}},
        repo_root=tmp_path,
    )

    assert result["ok"] is False
    assert result["reason"] == "cwd not found"


def test_execute_mcp_adapter_rejects_cwd_not_directory(tmp_path: Path) -> None:
    file_path = tmp_path / "not_dir.txt"
    file_path.write_text("x", encoding="utf-8")
    result = execute_mcp_adapter(
        "aider",
        {"command": "aider --help", "cwd": str(file_path)},
        {"tool_permissions": {"shell": "allow", "network": "deny"}},
        repo_root=tmp_path,
    )

    assert result["ok"] is False
    assert result["reason"] == "cwd is not a directory"


def test_execute_mcp_adapter_denied_by_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_adapter_runtime, "validate_command", lambda *args, **kwargs: {"ok": False, "reason": "blocked-by-policy"})

    result = execute_mcp_adapter(
        "aider",
        {"command": "aider --help"},
        {"tool_permissions": {"shell": "allow", "network": "deny"}},
        repo_root=tmp_path,
    )

    assert result["ok"] is False
    assert result["reason"] == "blocked-by-policy"
    assert result["error"] == "blocked-by-policy"


def test_execute_mcp_adapter_respects_timeout_from_payload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_adapter_runtime, "validate_command", lambda *args, **kwargs: {"ok": True})
    captured: dict[str, float | None] = {"timeout": None}

    def _fake_run(*args, **kwargs):
        captured["timeout"] = kwargs.get("timeout")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(mcp_adapter_runtime.subprocess, "run", _fake_run)

    result = execute_mcp_adapter(
        "aider",
        {"command": "aider --help", "timeout_sec": 7},
        {"tool_permissions": {"shell": "allow", "network": "deny"}},
        repo_root=tmp_path,
    )

    assert result["ok"] is True
    assert captured["timeout"] == 7.0


def test_execute_mcp_adapter_uses_contract_timeout_and_args_string(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mcp_adapter_runtime, "validate_command", lambda *args, **kwargs: {"ok": True})
    captured: dict[str, object] = {"timeout": None, "argv": None}

    def _fake_run(*args, **kwargs):
        captured["timeout"] = kwargs.get("timeout")
        captured["argv"] = args[0]
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(mcp_adapter_runtime.subprocess, "run", _fake_run)

    result = execute_mcp_adapter(
        "continue",
        {"args": "--help --json"},
        {
            "tool_permissions": {"shell": "allow", "network": "deny"},
            "timeout_retry": {"timeout_sec": 9},
        },
        repo_root=tmp_path,
    )

    assert result["ok"] is True
    assert captured["timeout"] == 9.0
    assert captured["argv"] == ["continue", "--help", "--json"]


def test_execute_mcp_adapter_timeout_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_adapter_runtime, "validate_command", lambda *args, **kwargs: {"ok": True})

    def _timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=1, output=b"partial", stderr=b"late")

    monkeypatch.setattr(mcp_adapter_runtime.subprocess, "run", _timeout)

    result = execute_mcp_adapter(
        "aider",
        {"command": "aider --help"},
        {"tool_permissions": {"shell": "allow", "network": "deny"}},
        repo_root=tmp_path,
    )

    assert result["ok"] is False
    assert result["reason"] == "adapter command timeout"
    assert "partial" in result["stdout"]
    assert "late" in result["stderr"]


def test_execute_mcp_adapter_execution_exception_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_adapter_runtime, "validate_command", lambda *args, **kwargs: {"ok": True})
    monkeypatch.setattr(mcp_adapter_runtime.subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))

    result = execute_mcp_adapter(
        "aider",
        {"command": "aider --help"},
        {"tool_permissions": {"shell": "allow", "network": "deny"}},
        repo_root=tmp_path,
    )

    assert result["ok"] is False
    assert result["reason"] == "adapter command execution failed"
    assert result["error"] == "boom"


def test_execute_mcp_adapter_non_zero_exit_includes_stderr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_adapter_runtime, "validate_command", lambda *args, **kwargs: {"ok": True})
    monkeypatch.setattr(
        mcp_adapter_runtime.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=args, returncode=2, stdout="", stderr="denied"),
    )

    result = execute_mcp_adapter(
        "aider",
        {"command": "aider --help"},
        {"tool_permissions": {"shell": "allow", "network": "deny"}},
        repo_root=tmp_path,
    )

    assert result["ok"] is False
    assert result["reason"] == "adapter command exited with non-zero code"
    assert result["error"] == "denied"


def test_execute_mcp_adapter_rejects_run_id_mismatch(tmp_path: Path) -> None:
    result = execute_mcp_adapter(
        "aider",
        {"command": "aider --help", "run_id": "run-other"},
        {
            "task_id": "task-a",
            "log_refs": {"run_id": "run-expected", "paths": {}},
            "tool_permissions": {"shell": "allow", "network": "deny"},
        },
        repo_root=tmp_path,
    )

    assert result["ok"] is False
    assert result["reason"] == "run_id mismatch"
    assert result["error"] == "run_id mismatch"


def test_execute_mcp_adapter_rejects_task_id_mismatch(tmp_path: Path) -> None:
    result = execute_mcp_adapter(
        "aider",
        {"command": "aider --help", "task_id": "task-other"},
        {
            "task_id": "task-expected",
            "log_refs": {"run_id": "run-expected", "paths": {}},
            "tool_permissions": {"shell": "allow", "network": "deny"},
        },
        repo_root=tmp_path,
    )

    assert result["ok"] is False
    assert result["reason"] == "task_id mismatch"
    assert result["error"] == "task_id mismatch"


@pytest.mark.parametrize(
    ("contract",),
    [
        ({"tool_permissions": {"shell": "allow"}},),
        ({"tool_permissions": {"shell": "allow", "network": None}},),
        ({"tool_permissions": {"shell": "allow", "network": "mystery-policy"}},),
    ],
)
def test_execute_mcp_adapter_network_policy_defaults_to_deny(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contract: dict[str, object],
) -> None:
    captured: dict[str, str | None] = {"network_policy": None}

    def _fake_validate(*args, **kwargs):
        captured["network_policy"] = kwargs.get("network_policy")
        return {"ok": True}

    monkeypatch.setattr(mcp_adapter_runtime, "validate_command", _fake_validate)
    monkeypatch.setattr(
        mcp_adapter_runtime.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=args, returncode=0, stdout="ok", stderr=""),
    )

    result = execute_mcp_adapter(
        "aider",
        {"command": "aider --help"},
        contract,
        repo_root=tmp_path,
    )

    assert result["ok"] is True
    assert captured["network_policy"] == "deny"
