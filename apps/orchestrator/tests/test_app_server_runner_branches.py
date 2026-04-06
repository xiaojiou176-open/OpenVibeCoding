import io
import json
import subprocess
from pathlib import Path

from cortexpilot_orch.runners import app_server_runner as app_server_module
from cortexpilot_orch.runners.app_server_runner import AppServerRunner
from cortexpilot_orch.store.run_store import RunStore


def _base_contract(task_id: str = "task_app") -> dict:
    return {
        "task_id": task_id,
        "owner_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "assigned_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "inputs": {"spec": "do work", "artifacts": []},
        "required_outputs": [{"name": "mock_output.txt", "type": "file", "acceptance": "ok"}],
        "allowed_paths": ["mock_output.txt"],
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


def _prepare(tmp_path: Path, task_id: str, monkeypatch) -> tuple[RunStore, str, Path, Path]:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run(task_id)
    monkeypatch.setenv("CORTEXPILOT_RUN_ID", run_id)

    worktree = tmp_path / f"worktree_{task_id}"
    worktree.mkdir(parents=True, exist_ok=True)

    schema_path = tmp_path / "task_result.v1.json"
    schema_path.write_text(json.dumps({"type": "object", "additionalProperties": True}), encoding="utf-8")
    return store, run_id, worktree, schema_path


def test_app_server_helper_functions(monkeypatch, tmp_path: Path) -> None:
    contract = _base_contract("task_helper")
    worktree = tmp_path / "w"
    worktree.mkdir(parents=True, exist_ok=True)

    policy = app_server_module._sandbox_policy(contract, worktree)
    assert policy is not None
    assert policy["type"] == "workspaceWrite"
    assert policy["networkAccess"] is False

    contract["tool_permissions"]["filesystem"] = "read-only"
    assert app_server_module._sandbox_policy(contract, worktree)["type"] == "readOnly"
    contract["tool_permissions"]["filesystem"] = "danger-full-access"
    assert app_server_module._sandbox_policy(contract, worktree)["type"] == "dangerFullAccess"
    contract["tool_permissions"]["filesystem"] = "invalid"
    assert app_server_module._sandbox_policy(contract, worktree) is None

    contract["tool_permissions"]["shell"] = "never"
    assert app_server_module._approval_policy(contract) == "never"
    contract["tool_permissions"]["shell"] = "on-request"
    assert app_server_module._approval_policy(contract) == "onRequest"
    contract["tool_permissions"]["shell"] = "untrusted"
    assert app_server_module._approval_policy(contract) == "untrusted"
    contract["tool_permissions"]["shell"] = "deny"
    assert app_server_module._approval_policy(contract) is None

    schema_path = tmp_path / "schema.json"
    schema_path.write_text("{\"type\":\"object\"}", encoding="utf-8")
    monkeypatch.setenv("CORTEXPILOT_CODEX_MODEL", "gpt-test")
    params = app_server_module._build_turn_params(contract, "instruction", worktree, schema_path)
    assert params["cwd"] == str(worktree)
    assert params["model"] == "gpt-test"
    assert params["input"][0]["text"] == "instruction"
    assert params["outputSchema"]["type"] == "object"

    schema_path.write_text("{", encoding="utf-8")
    params_bad_schema = app_server_module._build_turn_params(contract, "instruction", worktree, schema_path)
    assert "outputSchema" not in params_bad_schema

    assert app_server_module._extract_agent_delta({"params": {"delta": "a"}}) == "a"
    assert app_server_module._extract_agent_delta({"params": {"text": "b"}}) == "b"
    assert app_server_module._extract_agent_delta({"params": {"textDelta": "c"}}) == "c"
    assert app_server_module._extract_agent_delta({"params": {}}) == ""

    completed = {
        "params": {
            "item": {
                "type": "agentMessage",
                "text": "hello",
            }
        }
    }
    assert app_server_module._extract_agent_message(completed) == "hello"
    assert app_server_module._extract_agent_message({"params": {"item": {"type": "other"}}}) is None

    status, error = app_server_module._extract_turn_status(
        {"params": {"turn": {"status": "failed", "error": {"message": "boom"}}}}
    )
    assert status == "failed"
    assert error == "boom"


def test_app_server_denied_by_policy(tmp_path: Path, monkeypatch) -> None:
    store, run_id, worktree, schema_path = _prepare(tmp_path, "task_policy", monkeypatch)
    contract = _base_contract("task_policy")
    contract["tool_permissions"]["shell"] = "deny"

    runner = AppServerRunner(store)
    result = runner.run_contract(contract, worktree, schema_path, mock_mode=False)

    assert result["status"] == "FAILED"
    assert "shell tool denied" in result["summary"]
    events_text = (tmp_path / run_id / "events.jsonl").read_text(encoding="utf-8")
    assert "policy_violation" in events_text


def test_app_server_denied_when_codex_not_allowed(tmp_path: Path, monkeypatch) -> None:
    store, run_id, worktree, schema_path = _prepare(tmp_path, "task_no_codex", monkeypatch)
    contract = _base_contract("task_no_codex")
    contract["tool_permissions"]["mcp_tools"] = []

    runner = AppServerRunner(store)
    result = runner.run_contract(contract, worktree, schema_path, mock_mode=False)

    assert result["status"] == "FAILED"
    assert "codex tool not allowed" in result["summary"]
    events_text = (tmp_path / run_id / "events.jsonl").read_text(encoding="utf-8")
    assert "APP_SERVER_DENIED" in events_text


def test_app_server_missing_schema_path(tmp_path: Path, monkeypatch) -> None:
    store, _run_id, worktree, _schema_path = _prepare(tmp_path, "task_missing_schema", monkeypatch)
    missing_schema = tmp_path / "missing.json"

    runner = AppServerRunner(store)
    result = runner.run_contract(_base_contract("task_missing_schema"), worktree, missing_schema, mock_mode=False)

    assert result["status"] == "FAILED"
    assert "schema path missing" in result["summary"]


def test_app_server_validation_and_spawn_failures(tmp_path: Path, monkeypatch) -> None:
    store, _run_id, worktree, schema_path = _prepare(tmp_path, "task_failures", monkeypatch)

    class BadValidator:
        def __init__(self, schema_root: Path) -> None:
            self.schema_root = schema_root

        def validate_contract(self, contract: dict) -> None:
            raise RuntimeError("invalid contract")

    monkeypatch.setattr(app_server_module, "ContractValidator", BadValidator)

    runner = AppServerRunner(store)
    validation_result = runner.run_contract(_base_contract("task_failures"), worktree, schema_path, mock_mode=False)
    assert validation_result["status"] == "FAILED"
    assert "contract schema validation failed" in validation_result["summary"]

    class GoodValidator:
        def __init__(self, schema_root: Path) -> None:
            self.schema_root = schema_root

        def validate_contract(self, contract: dict) -> None:
            return None

    monkeypatch.setattr(app_server_module, "ContractValidator", GoodValidator)

    def _raise_popen(*args, **kwargs):  # noqa: ANN001, ANN002
        raise OSError("spawn failed")

    monkeypatch.setattr(app_server_module.subprocess, "Popen", _raise_popen)
    spawn_result = runner.run_contract(_base_contract("task_failures"), worktree, schema_path, mock_mode=False)
    assert spawn_result["status"] == "FAILED"
    assert "app-server spawn failed" in spawn_result["summary"]


def test_app_server_mock_mode_still_validates_contract(tmp_path: Path, monkeypatch) -> None:
    store, _run_id, worktree, schema_path = _prepare(tmp_path, "task_mock_validate", monkeypatch)

    class BadValidator:
        def __init__(self, schema_root: Path) -> None:
            self.schema_root = schema_root

        def validate_contract(self, contract: dict) -> None:
            raise RuntimeError("invalid contract in mock mode")

    monkeypatch.setattr(app_server_module, "ContractValidator", BadValidator)

    result = AppServerRunner(store).run_contract(_base_contract("task_mock_validate"), worktree, schema_path, mock_mode=True)
    assert result["status"] == "FAILED"
    assert "contract schema validation failed" in result["summary"]


class _DummyProc:
    def __init__(self, stderr_text: str = "", initial_poll: int | None = None) -> None:
        self.stdin = io.StringIO()
        self.stdout = io.StringIO()
        self.stderr = io.StringIO(stderr_text)
        self._returncode = initial_poll

    def poll(self) -> int | None:
        return self._returncode

    def terminate(self) -> None:
        self._returncode = 0

    def wait(self, timeout: float | None = None) -> int:
        self._returncode = 0 if self._returncode is None else self._returncode
        return self._returncode

    def kill(self) -> None:
        self._returncode = -9


class _StreamFromLines:
    def __init__(self, proc: _DummyProc, lines: list[str]) -> None:
        self._lines = list(lines)

    def read_line(self, timeout: float) -> str | None:
        if not self._lines:
            return None
        return self._lines.pop(0)


def test_app_server_success_and_turn_failure_paths(tmp_path: Path, monkeypatch) -> None:
    store, run_id, worktree, schema_path = _prepare(tmp_path, "task_success", monkeypatch)

    class GoodValidator:
        def __init__(self, schema_root: Path) -> None:
            self.schema_root = schema_root

        def validate_contract(self, contract: dict) -> None:
            return None

    monkeypatch.setattr(app_server_module, "ContractValidator", GoodValidator)

    sent_messages: list[dict] = []

    def _fake_send_json(proc, payload: dict, ensure_ascii: bool = False) -> None:  # noqa: ANN001
        sent_messages.append(payload)

    monkeypatch.setattr(app_server_module, "send_json", _fake_send_json)

    success_lines = [
        json.dumps({"id": 0, "result": {}}) + "\n",
        json.dumps({"id": 1, "result": {"thread": {"id": "thread-1"}}}) + "\n",
        json.dumps(
            {
                "method": "item/completed",
                "params": {
                    "item": {
                        "type": "agentMessage",
                        "text": json.dumps(
                            {
                                "task_id": "task_success",
                                "status": "SUCCESS",
                                "summary": "ok",
                                "evidence_refs": {},
                            }
                        ),
                    }
                },
            }
        )
        + "\n",
        json.dumps({"method": "turn/completed", "params": {"turn": {"status": "completed"}}}) + "\n",
    ]

    monkeypatch.setattr(app_server_module.subprocess, "Popen", lambda *args, **kwargs: _DummyProc())
    monkeypatch.setattr(app_server_module, "JsonlStream", lambda proc: _StreamFromLines(proc, success_lines))

    runner = AppServerRunner(store)
    success_contract = _base_contract("task_success")
    # Keep this branch test deterministic on slower CI workers.
    success_contract["timeout_retry"]["timeout_sec"] = 5
    success = runner.run_contract(success_contract, worktree, schema_path, mock_mode=False)

    assert success["status"] == "SUCCESS"
    assert (tmp_path / run_id / "codex" / "task_success" / "transcript.md").exists()
    assert (tmp_path / run_id / "codex" / "task_success" / "thread_id.txt").exists()
    assert (tmp_path / run_id / "codex" / "session_map.json").exists()
    assert any(item.get("method") == "initialize" for item in sent_messages)
    assert any(item.get("method") == "turn/start" for item in sent_messages)

    failed_lines = [
        json.dumps({"id": 0, "result": {}}) + "\n",
        json.dumps({"id": 1, "result": {"thread": {"id": "thread-2"}}}) + "\n",
        "not-json\n",
        json.dumps(
            {
                "method": "turn/completed",
                "params": {"turn": {"status": "failed", "error": {"message": "turn failed"}}},
            }
        )
        + "\n",
    ]

    monkeypatch.setattr(app_server_module.subprocess, "Popen", lambda *args, **kwargs: _DummyProc(stderr_text="stderr-line"))
    monkeypatch.setattr(app_server_module, "JsonlStream", lambda proc: _StreamFromLines(proc, failed_lines))

    failed_contract = _base_contract("task_success")
    # Avoid racing the turn-completed failure message with the outer turn timeout.
    failed_contract["timeout_retry"]["timeout_sec"] = 5
    failed = runner.run_contract(failed_contract, worktree, schema_path, mock_mode=False)
    assert failed["status"] == "FAILED"
    assert "turn failed" in failed["summary"]

    events_text = (tmp_path / run_id / "events.jsonl").read_text(encoding="utf-8")
    assert "APP_SERVER_INVALID_JSON" in events_text
    assert "APP_SERVER_STDERR" in events_text


def test_app_server_turn_timeout_and_output_not_json(tmp_path: Path, monkeypatch) -> None:
    store, _run_id, worktree, schema_path = _prepare(tmp_path, "task_timeout", monkeypatch)

    class GoodValidator:
        def __init__(self, schema_root: Path) -> None:
            self.schema_root = schema_root

        def validate_contract(self, contract: dict) -> None:
            return None

    monkeypatch.setattr(app_server_module, "ContractValidator", GoodValidator)
    monkeypatch.setattr(app_server_module, "send_json", lambda *args, **kwargs: None)

    timeout_lines = [
        json.dumps({"id": 0, "result": {}}) + "\n",
        json.dumps({"id": 1, "result": {"thread": {"id": "thread-timeout"}}}) + "\n",
    ]
    monkeypatch.setattr(
        app_server_module.subprocess,
        "Popen",
        lambda *args, **kwargs: _DummyProc(stderr_text="boom", initial_poll=1),
    )
    monkeypatch.setattr(app_server_module, "JsonlStream", lambda proc: _StreamFromLines(proc, timeout_lines))

    runner = AppServerRunner(store)
    timeout_contract = _base_contract("task_timeout")
    timeout_contract["timeout_retry"]["timeout_sec"] = 1
    timeout_result = runner.run_contract(timeout_contract, worktree, schema_path, mock_mode=False)
    assert timeout_result["status"] == "FAILED"
    assert "turn timeout" in timeout_result["summary"]

    output_not_json_lines = [
        json.dumps({"id": 0, "result": {}}) + "\n",
        json.dumps({"id": 1, "result": {"thread": {"id": "thread-out"}}}) + "\n",
        json.dumps(
            {
                "method": "item/completed",
                "params": {"item": {"type": "agentMessage", "text": "not-json"}},
            }
        )
        + "\n",
        json.dumps({"method": "turn/completed", "params": {"turn": {"status": "completed"}}}) + "\n",
    ]
    monkeypatch.setattr(app_server_module.subprocess, "Popen", lambda *args, **kwargs: _DummyProc())
    monkeypatch.setattr(app_server_module, "JsonlStream", lambda proc: _StreamFromLines(proc, output_not_json_lines))

    not_json_result = runner.run_contract(_base_contract("task_timeout"), worktree, schema_path, mock_mode=False)
    assert not_json_result["status"] == "FAILED"
    assert "output not json" in not_json_result["summary"]


def test_app_server_mock_mode_paths_and_helper_edges(tmp_path: Path, monkeypatch) -> None:
    store, run_id, worktree, schema_path = _prepare(tmp_path, "task_mock_paths", monkeypatch)
    runner = AppServerRunner(store)

    readonly_contract = _base_contract("task_mock_paths")
    readonly_contract["tool_permissions"]["filesystem"] = "read-only"
    readonly = runner.run_contract(readonly_contract, worktree, schema_path, mock_mode=True)
    assert readonly["status"] == "SUCCESS"

    writable_contract = _base_contract("task_mock_paths")
    writable_contract["required_outputs"] = [{"name": "nested/out.txt", "type": "file", "acceptance": "ok"}]
    writable = runner.run_contract(writable_contract, worktree, schema_path, mock_mode=True)
    assert writable["status"] == "SUCCESS"
    assert (worktree / "nested" / "out.txt").exists()

    assert app_server_module._codex_allowed({"tool_permissions": None}) is False
    assert app_server_module._codex_allowed({"tool_permissions": {"mcp_tools": "codex"}}) is False
    assert app_server_module._sandbox_policy({"tool_permissions": None}, worktree) is None
    assert app_server_module._approval_policy({"tool_permissions": None}) is None
    assert app_server_module._extract_agent_message({"params": {"item": {}}}) is None
    status, err = app_server_module._extract_turn_status({"params": {}})
    assert status is None and err is None

    events_text = (tmp_path / run_id / "events.jsonl").read_text(encoding="utf-8")
    assert "APP_SERVER_MOCK_EVENT" in events_text


def test_app_server_resume_thread_missing_output_and_blank_lines(tmp_path: Path, monkeypatch) -> None:
    store, _run_id, worktree, schema_path = _prepare(tmp_path, "task_resume_blank", monkeypatch)

    class GoodValidator:
        def __init__(self, schema_root: Path) -> None:
            self.schema_root = schema_root

        def validate_contract(self, contract: dict) -> None:
            return None

    class _StreamFromItems:
        def __init__(self, proc: _DummyProc, items: list[str | None]) -> None:
            self._items = list(items)

        def read_line(self, timeout: float) -> str | None:
            del timeout
            if not self._items:
                return None
            return self._items.pop(0)

    monkeypatch.setattr(app_server_module, "ContractValidator", GoodValidator)
    monkeypatch.setattr(app_server_module, "send_json", lambda *args, **kwargs: None)
    monkeypatch.setattr(app_server_module.subprocess, "Popen", lambda *args, **kwargs: _DummyProc())

    lines = [
        "",
        json.dumps({"id": 0, "result": {}}) + "\n",
        "",
        json.dumps({"id": 1, "result": {"thread": {}}}) + "\n",
        None,
        "",
        json.dumps({"method": "turn/completed", "params": {"turn": {"status": "completed"}}}) + "\n",
    ]
    monkeypatch.setattr(app_server_module, "JsonlStream", lambda proc: _StreamFromItems(proc, lines))

    contract = _base_contract("task_resume_blank")
    contract["assigned_agent"]["codex_thread_id"] = "thread-reuse"
    result = AppServerRunner(store).run_contract(contract, worktree, schema_path, mock_mode=False)

    assert result["status"] == "FAILED"
    assert "missing output" in result["summary"]


def test_app_server_wait_timeout_kill_and_outer_exception(tmp_path: Path, monkeypatch) -> None:
    store, _run_id, worktree, schema_path = _prepare(tmp_path, "task_wait_kill", monkeypatch)

    class GoodValidator:
        def __init__(self, schema_root: Path) -> None:
            self.schema_root = schema_root

        def validate_contract(self, contract: dict) -> None:
            return None

    class _KillableProc(_DummyProc):
        def __init__(self) -> None:
            super().__init__(stderr_text="", initial_poll=None)
            self.killed = False

        def wait(self, timeout: float | None = None) -> int:
            del timeout
            raise subprocess.TimeoutExpired(cmd="codex", timeout=5)

        def kill(self) -> None:
            self.killed = True
            self._returncode = -9

    proc_ref: dict[str, _KillableProc] = {}

    def _make_proc(*args, **kwargs):  # noqa: ANN001, ANN002
        del args, kwargs
        proc = _KillableProc()
        proc_ref["proc"] = proc
        return proc

    success_lines = [
        json.dumps({"id": 0, "result": {}}) + "\n",
        json.dumps({"id": 1, "result": {"thread": {"id": "thread-kill"}}}) + "\n",
        json.dumps(
            {
                "method": "item/completed",
                "params": {
                    "item": {
                        "type": "agentMessage",
                        "text": json.dumps(
                            {
                                "task_id": "task_wait_kill",
                                "status": "SUCCESS",
                                "summary": "ok",
                                "evidence_refs": {},
                            }
                        ),
                    }
                },
            }
        )
        + "\n",
        json.dumps({"method": "turn/completed", "params": {"turn": {"status": "completed"}}}) + "\n",
    ]

    monkeypatch.setattr(app_server_module, "ContractValidator", GoodValidator)
    monkeypatch.setattr(app_server_module, "send_json", lambda *args, **kwargs: None)
    monkeypatch.setattr(app_server_module.subprocess, "Popen", _make_proc)
    monkeypatch.setattr(app_server_module, "JsonlStream", lambda proc: _StreamFromLines(proc, success_lines))

    ok = AppServerRunner(store).run_contract(_base_contract("task_wait_kill"), worktree, schema_path, mock_mode=False)
    assert ok["status"] == "SUCCESS"
    assert proc_ref["proc"].killed is True

    monkeypatch.setattr(app_server_module.subprocess, "Popen", lambda *args, **kwargs: _DummyProc())
    monkeypatch.setattr(app_server_module, "JsonlStream", lambda proc: (_ for _ in ()).throw(RuntimeError("stream failed")))

    failed = AppServerRunner(store).run_contract(_base_contract("task_wait_kill"), worktree, schema_path, mock_mode=False)
    assert failed["status"] == "FAILED"
    assert "execution failed" in failed["summary"]
