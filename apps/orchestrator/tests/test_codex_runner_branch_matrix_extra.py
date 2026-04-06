import io
import json
from pathlib import Path

import pytest

from cortexpilot_orch.runners import codex_runner as codex_mod
from cortexpilot_orch.store.run_store import RunStore


class _NoopValidator:
    def __init__(self, schema_root: Path | None = None) -> None:
        self.schema_root = schema_root

    def validate_contract(self, contract: dict) -> None:
        return None


class _DummyProc:
    def __init__(self, stdout_text: str, stderr_text: str, exit_code: int = 0) -> None:
        self.stdout = io.StringIO(stdout_text)
        self.stderr = io.StringIO(stderr_text)
        self._stdout_text = stdout_text
        self._stderr_text = stderr_text
        self.returncode = exit_code

    def communicate(self, timeout: int | None = None) -> tuple[str, str]:
        return self._stdout_text, self._stderr_text

    def kill(self) -> None:
        self.returncode = -9

    def wait(self) -> int:
        return self.returncode


def _base_contract(task_id: str = "task-codex-extra") -> dict:
    return {
        "task_id": task_id,
        "owner_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "assigned_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "inputs": {"spec": "run codex"},
        "required_outputs": [{"name": ".runtime-cache/test_output/worker_markers/mock.txt", "type": "file", "acceptance": "ok"}],
        "allowed_paths": [".runtime-cache/test_output/worker_markers/mock.txt"],
        "forbidden_actions": [],
        "acceptance_tests": [{"name": "noop", "cmd": "echo ok", "must_pass": True}],
        "tool_permissions": {
            "filesystem": "workspace-write",
            "shell": "on-request",
            "network": "deny",
            "mcp_tools": ["codex"],
        },
        "mcp_tool_set": ["01-filesystem"],
        "timeout_retry": {"timeout_sec": 1, "max_retries": 0, "retry_backoff_sec": 0},
        "rollback": {"strategy": "git_reset_hard", "baseline_ref": "HEAD"},
        "evidence_links": [],
        "log_refs": {"run_id": "", "paths": {}},
    }


def test_codex_runner_helper_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    assert codex_mod._normalize_status("", "SUCCESS") == "SUCCESS"
    assert codex_mod._resolve_resume_id({"assigned_agent": []}) is None
    assert codex_mod._resolve_resume_id({"assigned_agent": {"codex_thread_id": "  t-123  "}}) == "t-123"

    assert codex_mod._extract_thread_id({"thread_id": "top-thread"}) == "top-thread"
    assert codex_mod._extract_session_id({"sessionId": "top-session"}) == "top-session"

    assert codex_mod._codex_flags({"tool_permissions": "oops"}) == []
    flags = codex_mod._codex_flags(
        {
            "tool_permissions": {
                "filesystem": "read-only",
                "network": "deny",
                "shell": "on-request",
            }
        }
    )
    assert flags == ["--sandbox", "read-only"]

    assert codex_mod._codex_allowed({"tool_permissions": []}) is False
    assert codex_mod._codex_allowed({"tool_permissions": {"mcp_tools": "codex"}}) is False

    embedded = {
        "item": {
            "type": "agent_message",
            "text": json.dumps({"status": "BLOCKED", "summary": "need access"}),
        }
    }
    extracted = codex_mod._extract_task_result_payload(embedded, "task-helper")
    assert extracted == {
        "task_id": "task-helper",
        "status": "BLOCKED",
        "summary": "need access",
        "evidence_refs": {"agent_message": {"status": "BLOCKED", "summary": "need access"}},
        "failure": None,
    }

    monkeypatch.setenv("CORTEXPILOT_CODEX_PROFILE", "  profile-a  ")
    assert codex_mod._resolve_profile() == "profile-a"
    monkeypatch.setenv("CORTEXPILOT_CODEX_PROFILE", "")
    monkeypatch.setattr(codex_mod, "pick_profile", lambda: "pool-profile")
    assert codex_mod._resolve_profile() == "pool-profile"

    monkeypatch.setenv("CORTEXPILOT_CODEX_MODEL", "  gpt-5.2-codex  ")
    assert codex_mod._resolve_model() == "gpt-5.2-codex"
    monkeypatch.setenv("CORTEXPILOT_CODEX_MODEL", "")
    assert codex_mod._resolve_model() is None

    monkeypatch.setenv("CORTEXPILOT_CODEX_USE_OUTPUT_SCHEMA", "1")
    assert codex_mod._use_output_schema() is True
    monkeypatch.setenv("CORTEXPILOT_CODEX_USE_OUTPUT_SCHEMA", "")
    assert codex_mod._use_output_schema() is False


def test_codex_runner_blocks_mcp_only_and_shell_deny(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task-mcp-only")
    monkeypatch.setenv("CORTEXPILOT_RUN_ID", run_id)

    contract = _base_contract("task-mcp-only")
    monkeypatch.setenv("CORTEXPILOT_MCP_ONLY", "1")
    monkeypatch.delenv("CORTEXPILOT_ALLOW_CODEX_EXEC", raising=False)
    blocked = codex_mod.CodexRunner(store).run_contract(
        contract,
        tmp_path,
        tmp_path / "missing-schema.json",
        mock_mode=False,
    )
    assert blocked["status"] == "FAILED"
    assert "mcp-only enforced" in blocked["summary"]

    contract_shell_deny = _base_contract("task-shell-deny")
    contract_shell_deny["tool_permissions"]["shell"] = "deny"
    monkeypatch.setenv("CORTEXPILOT_MCP_ONLY", "0")
    denied = codex_mod.CodexRunner(store).run_contract(
        contract_shell_deny,
        tmp_path,
        tmp_path / "still-missing.json",
        mock_mode=True,
    )
    assert denied["status"] == "FAILED"
    assert "shell tool denied" in denied["summary"]

    contract_shell_never = _base_contract("task-shell-never")
    contract_shell_never["tool_permissions"]["shell"] = "never"
    schema_path = Path(__file__).resolve().parents[3] / "schemas" / "task_result.v1.json"
    monkeypatch.setattr(codex_mod, "ContractValidator", _NoopValidator)
    allowed = codex_mod.CodexRunner(store).run_contract(
        contract_shell_never,
        tmp_path,
        schema_path,
        mock_mode=True,
    )
    assert allowed["status"] == "SUCCESS"


def test_codex_runner_mock_read_only_and_wrapper(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task-read-only")
    monkeypatch.setenv("CORTEXPILOT_RUN_ID", run_id)

    repo_root = Path(__file__).resolve().parents[3]
    schema_path = repo_root / "schemas" / "task_result.v1.json"
    monkeypatch.setattr(codex_mod, "ContractValidator", _NoopValidator)

    contract = _base_contract("task-read-only")
    contract["tool_permissions"]["filesystem"] = "read-only"
    result = codex_mod.CodexRunner(store).run_contract(
        contract,
        tmp_path,
        schema_path,
        mock_mode=True,
    )
    assert result["status"] == "SUCCESS"

    # Cover module-level wrapper path.
    wrapped = codex_mod.run_contract(
        run_store=store,
        contract=contract,
        worktree_path=tmp_path,
        schema_path=schema_path,
        mock_mode=True,
    )
    assert wrapped["status"] == "SUCCESS"


def test_codex_runner_mock_mode_still_validates_contract(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task-mock-validate")
    monkeypatch.setenv("CORTEXPILOT_RUN_ID", run_id)

    repo_root = Path(__file__).resolve().parents[3]
    schema_path = repo_root / "schemas" / "task_result.v1.json"

    class _FailValidator:
        def __init__(self, schema_root: Path | None = None) -> None:
            self.schema_root = schema_root

        def validate_contract(self, contract: dict) -> None:
            raise RuntimeError("invalid contract in mock mode")

    monkeypatch.setattr(codex_mod, "ContractValidator", _FailValidator)

    result = codex_mod.CodexRunner(store).run_contract(
        _base_contract("task-mock-validate"),
        tmp_path,
        schema_path,
        mock_mode=True,
    )
    assert result["status"] == "FAILED"
    assert "contract schema validation failed" in result["summary"]


def test_codex_runner_resume_profile_and_non_json_stream(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task-stream")
    monkeypatch.setenv("CORTEXPILOT_RUN_ID", run_id)
    monkeypatch.setenv("CORTEXPILOT_MCP_ONLY", "0")
    monkeypatch.setenv("CORTEXPILOT_CODEX_PROFILE", "profile-z")
    monkeypatch.setenv("CORTEXPILOT_CODEX_MODEL", "gpt-5.2-codex")

    repo_root = Path(__file__).resolve().parents[3]
    schema_path = repo_root / "schemas" / "task_result.v1.json"

    contract = _base_contract("task-stream")
    contract["assigned_agent"]["codex_thread_id"] = "resume-thread-1"

    stdout_lines = "\n".join(
        [
            "",
            "plain-text-event",
            json.dumps({"event": "META", "threadId": "thread-xyz", "sessionId": "session-xyz"}),
            json.dumps(
                {
                    "task_id": "task-stream",
                    "status": "SUCCESS",
                    "summary": "done",
                    "evidence_refs": {},
                    "failure": None,
                }
            ),
        ]
    )
    popen_cmd: dict[str, list[str]] = {}

    def _fake_popen(*args, **kwargs):
        cmd = args[0]
        popen_cmd["cmd"] = list(cmd)
        return _DummyProc(stdout_text=stdout_lines + "\n", stderr_text="minor stderr", exit_code=0)

    monkeypatch.setattr(codex_mod, "ContractValidator", _NoopValidator)
    monkeypatch.setattr(codex_mod.subprocess, "Popen", _fake_popen)

    runner = codex_mod.CodexRunner(store)
    result = runner.run_contract(contract, tmp_path, schema_path, mock_mode=False)
    assert result["status"] == "SUCCESS"
    assert result["evidence_refs"]["thread_id"] == "thread-xyz"
    assert result["evidence_refs"]["session_id"] == "session-xyz"

    transcript = (tmp_path / run_id / "codex" / "task-stream" / "transcript.md").read_text(encoding="utf-8")
    assert "plain-text-event" in transcript

    events = (tmp_path / run_id / "events.jsonl").read_text(encoding="utf-8")
    assert "CODEX_STDERR" in events
    assert "CODEX_CMD" in events

    cmd = popen_cmd["cmd"]
    assert "-m" not in cmd
    assert "--ask-for-approval" not in cmd
    assert "--output-schema" not in cmd
    assert "--model" in cmd
    assert cmd[-1] == "run codex"
    assert "CODEX_OUTPUT_SCHEMA_DISABLED" in events


def test_codex_runner_timeout_returns_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task-timeout")
    monkeypatch.setenv("CORTEXPILOT_RUN_ID", run_id)
    monkeypatch.setenv("CORTEXPILOT_MCP_ONLY", "0")
    monkeypatch.setenv("CORTEXPILOT_CODEX_EXEC_TIMEOUT_SEC", "60")

    repo_root = Path(__file__).resolve().parents[3]
    schema_path = repo_root / "schemas" / "task_result.v1.json"

    contract = _base_contract("task-timeout")

    class _TimeoutProc(_DummyProc):
        def __init__(self) -> None:
            super().__init__("", "", exit_code=124)
            self._timed_out = False

        def communicate(self, timeout: int | None = None) -> tuple[str, str]:
            if not self._timed_out:
                self._timed_out = True
                raise codex_mod.subprocess.TimeoutExpired(cmd="codex", timeout=timeout)
            return "", "stderr-tail"

    monkeypatch.setattr(codex_mod, "ContractValidator", _NoopValidator)
    monkeypatch.setattr(codex_mod.subprocess, "Popen", lambda *a, **_k: _TimeoutProc())

    result = codex_mod.CodexRunner(store).run_contract(contract, tmp_path, schema_path, mock_mode=False)
    assert result["status"] == "FAILED"
    assert "timeout after 60s" in result["summary"]
