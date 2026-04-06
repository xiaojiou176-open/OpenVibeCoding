import hashlib
import json
import sys
import types
from pathlib import Path

from cortexpilot_orch.runners.agents_runner import (
    AgentsRunner,
    _build_codex_payload,
    _extract_binding_from_result,
    _resolve_session_binding,
)
from cortexpilot_orch.runners.codex_runner import (
    CodexRunner,
    _codex_allowed,
    _codex_flags,
    _extract_session_id,
    _extract_thread_id,
)
from cortexpilot_orch.store.run_store import RunStore
from cortexpilot_orch.store.session_map import SessionAliasStore


class DummyRunConfig:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


class DummyModelSettings:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


class DummyStreamResult:
    def __init__(self, text: str | None, trace: list[dict] | None = None) -> None:
        self.final_output = text
        self.trace = trace or []

    async def stream_events(self):
        if self.final_output == "__stream__":
            yield None
        return


def _output_schema_artifacts(role: str = "worker") -> list[dict]:
    schema_root = Path(__file__).resolve().parents[3] / "schemas"
    schema_name = "agent_task_result.v1.json"
    if role.lower() in {"reviewer"}:
        schema_name = "review_report.v1.json"
    if role.lower() in {"test", "test_runner"}:
        schema_name = "test_report.v1.json"
    schema_path = schema_root / schema_name
    sha = hashlib.sha256(schema_path.read_bytes()).hexdigest()
    return [
        {
            "name": f"output_schema.{role.lower()}",
            "uri": f"schemas/{schema_name}",
            "sha256": sha,
        }
    ]


def _base_contract(task_id: str, output_name: str = "mock_output.txt") -> dict:
    return {
        "task_id": task_id,
        "owner_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "assigned_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "inputs": {"spec": "mock", "artifacts": _output_schema_artifacts("worker")},
        "required_outputs": [{"name": output_name, "type": "file", "acceptance": "ok"}],
        "allowed_paths": [output_name],
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


def test_codex_runner_parses_stdout_and_writes_transcript(tmp_path: Path, monkeypatch) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task_codex")
    monkeypatch.setenv("CORTEXPILOT_RUN_ID", run_id)

    repo_root = Path(__file__).resolve().parents[3]
    schema_path = repo_root / "schemas" / "task_result.v1.json"

    worktree = tmp_path / "worktree"
    worktree.mkdir()

    event_meta = {"event": "META", "thread_id": "thread-1", "session_id": "session-1"}
    payload = {
        "task_id": "task_codex",
        "status": "SUCCESS",
        "summary": "ok",
        "evidence_refs": {},
        "failure": None,
    }
    stdout = json.dumps(event_meta) + "\n" + json.dumps(payload) + "\n"
    stderr = ""

    class DummyProc:
        def __init__(self) -> None:
            self.returncode = 0

        def communicate(self, timeout=None):
            del timeout
            return stdout, stderr

    monkeypatch.setattr("subprocess.Popen", lambda *args, **kwargs: DummyProc())

    runner = CodexRunner(store)
    result = runner.run_contract(_base_contract("task_codex"), worktree, schema_path, mock_mode=False)

    assert result["status"] == "SUCCESS"
    transcript_path = tmp_path / run_id / "codex" / "task_codex" / "transcript.md"
    assert transcript_path.exists()
    session_map_path = tmp_path / run_id / "codex" / "session_map.json"
    assert session_map_path.exists()


def test_codex_runner_handles_subprocess_failures(tmp_path: Path, monkeypatch) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task_codex_fail")
    monkeypatch.setenv("CORTEXPILOT_RUN_ID", run_id)

    repo_root = Path(__file__).resolve().parents[3]
    schema_path = repo_root / "schemas" / "task_result.v1.json"
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    stdout = ""
    stderr = "boom"

    class DummyProc:
        def __init__(self) -> None:
            self.returncode = 1

        def communicate(self, timeout=None):
            del timeout
            return stdout, stderr

    monkeypatch.setattr("subprocess.Popen", lambda *args, **kwargs: DummyProc())

    runner = CodexRunner(store)
    result = runner.run_contract(_base_contract("task_codex_fail"), worktree, schema_path, mock_mode=False)
    assert result["status"] == "FAILED"
    assert "codex exec failed" in result["summary"]


def test_codex_runner_missing_task_result_and_schema_invalid(tmp_path: Path, monkeypatch) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task_codex_missing")
    monkeypatch.setenv("CORTEXPILOT_RUN_ID", run_id)

    repo_root = Path(__file__).resolve().parents[3]
    schema_path = repo_root / "schemas" / "task_result.v1.json"
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    stdout = json.dumps({"event": "INFO"}) + "\n"
    stderr = ""

    class DummyProcMissing:
        def __init__(self) -> None:
            self.returncode = 0

        def communicate(self, timeout=None):
            del timeout
            return stdout, stderr

    monkeypatch.setattr("subprocess.Popen", lambda *args, **kwargs: DummyProcMissing())
    runner = CodexRunner(store)
    result = runner.run_contract(_base_contract("task_codex_missing"), worktree, schema_path, mock_mode=False)
    assert result["status"] == "FAILED"
    assert "missing task result" in result["summary"]

    invalid_payload = {
        "task_id": "task_codex_invalid",
        "status": "success",
        "diff_summary": "diff",
        "extra": "invalid",
    }
    stdout_invalid = json.dumps(invalid_payload) + "\n"

    class DummyProcInvalid:
        def __init__(self) -> None:
            self.returncode = 0

        def communicate(self, timeout=None):
            del timeout
            return stdout_invalid, ""

    monkeypatch.setattr("subprocess.Popen", lambda *args, **kwargs: DummyProcInvalid())
    result = runner.run_contract(_base_contract("task_codex_invalid"), worktree, schema_path, mock_mode=False)
    assert result["status"] == "SUCCESS"


def test_agents_runner_with_fake_sdk(monkeypatch, tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task_agents")
    monkeypatch.setenv("CORTEXPILOT_RUN_ID", run_id)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(tmp_path / "runtime"))

    alias_store = SessionAliasStore()
    alias_store.set_alias("agent-1", "session-legacy", thread_id="thread-legacy", note="seed")

    class DummyAgent:
        def __init__(self, name: str, instructions: str, mcp_servers: list):
            self.name = name
            self.instructions = instructions
            self.mcp_servers = mcp_servers

    class DummyRunner:
        @staticmethod
        def run_streamed(agent, prompt, **kwargs):
            payload = {
                "task_id": "task_agents",
                "status": "SUCCESS",
                "summary": "mock",
                "evidence_refs": {"thread_id": "thread-new", "session_id": "session-new"},
                "failure": None,
            }
            return DummyStreamResult(json.dumps(payload))

    class DummyMCP:
        def __init__(self, params=None):
            self.params = params

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    agents_mod = types.ModuleType("agents")
    agents_mod.Agent = DummyAgent
    agents_mod.Runner = DummyRunner
    agents_mod.set_default_openai_api = lambda key: None
    agents_mod.RunConfig = DummyRunConfig
    agents_mod.ModelSettings = DummyModelSettings
    mcp_mod = types.ModuleType("agents.mcp")
    mcp_mod.MCPServerStdio = DummyMCP

    monkeypatch.setitem(sys.modules, "agents", agents_mod)
    monkeypatch.setitem(sys.modules, "agents.mcp", mcp_mod)

    worktree = tmp_path / "worktree"
    worktree.mkdir()
    repo_root = Path(__file__).resolve().parents[3]
    schema_path = repo_root / "schemas" / "task_result.v1.json"

    runner = AgentsRunner(store)
    result = runner.run_contract(_base_contract("task_agents"), worktree, schema_path, mock_mode=False)

    assert result["status"] == "SUCCESS"
    events_text = (tmp_path / run_id / "events.jsonl").read_text(encoding="utf-8")
    assert "AGENT_SESSION_BOUND" in events_text
    transcript_path = tmp_path / run_id / "codex" / "task_agents" / "transcript.md"
    assert transcript_path.exists()
    codex_events_path = tmp_path / run_id / "codex" / "task_agents" / "events.jsonl"
    assert codex_events_path.exists()
    session_map_path = tmp_path / run_id / "codex" / "session_map.json"
    assert session_map_path.exists()


def test_agents_runner_missing_api_key(monkeypatch, tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task_agents_missing_key")
    monkeypatch.setenv("CORTEXPILOT_RUN_ID", run_id)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("CORTEXPILOT_AGENTS_BASE_URL", raising=False)
    monkeypatch.setattr("cortexpilot_orch.runners.agents_runner._equilibrium_healthcheck", lambda *_args, **_kwargs: False)

    agents_mod = types.ModuleType("agents")
    agents_mod.Agent = object
    agents_mod.Runner = object
    agents_mod.set_default_openai_api = lambda key: None
    agents_mod.RunConfig = DummyRunConfig
    agents_mod.ModelSettings = DummyModelSettings
    mcp_mod = types.ModuleType("agents.mcp")
    mcp_mod.MCPServerStdio = object

    monkeypatch.setitem(sys.modules, "agents", agents_mod)
    monkeypatch.setitem(sys.modules, "agents.mcp", mcp_mod)

    worktree = tmp_path / "worktree"
    worktree.mkdir()
    repo_root = Path(__file__).resolve().parents[3]
    schema_path = repo_root / "schemas" / "task_result.v1.json"

    runner = AgentsRunner(store)
    result = runner.run_contract(_base_contract("task_agents_missing_key"), worktree, schema_path, mock_mode=False)
    assert result["status"] == "FAILED"
    assert "missing LLM API key" in result["summary"]
    assert "GEMINI_API_KEY" in result["summary"]


def test_agents_runner_shell_deny_detects_tool(monkeypatch, tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task_shell_deny")
    monkeypatch.setenv("CORTEXPILOT_RUN_ID", run_id)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    class DummyAgent:
        def __init__(self, name: str, instructions: str, mcp_servers: list):
            self.name = name
            self.instructions = instructions
            self.mcp_servers = mcp_servers

    class DummyRunner:
        @staticmethod
        def run_streamed(agent, prompt, **kwargs):
            payload = {
                "task_id": "task_shell_deny",
                "status": "SUCCESS",
                "summary": "mock",
                "evidence_refs": {},
                "failure": None,
            }
            return DummyStreamResult(
                json.dumps(payload),
                trace=[{"tool": "shell", "command": "ls"}],
            )

    class DummyMCP:
        def __init__(self, params=None):
            self.params = params

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    agents_mod = types.ModuleType("agents")
    agents_mod.Agent = DummyAgent
    agents_mod.Runner = DummyRunner
    agents_mod.set_default_openai_api = lambda key: None
    agents_mod.RunConfig = DummyRunConfig
    agents_mod.ModelSettings = DummyModelSettings
    mcp_mod = types.ModuleType("agents.mcp")
    mcp_mod.MCPServerStdio = DummyMCP

    monkeypatch.setitem(sys.modules, "agents", agents_mod)
    monkeypatch.setitem(sys.modules, "agents.mcp", mcp_mod)

    worktree = tmp_path / "worktree"
    worktree.mkdir()
    repo_root = Path(__file__).resolve().parents[3]
    schema_path = repo_root / "schemas" / "task_result.v1.json"

    contract = _base_contract("task_shell_deny")
    contract["tool_permissions"]["shell"] = "deny"

    runner = AgentsRunner(store)
    result = runner.run_contract(contract, worktree, schema_path, mock_mode=False)

    assert result["status"] == "FAILED"
    events_text = (tmp_path / run_id / "events.jsonl").read_text(encoding="utf-8")
    assert "policy_violation" in events_text


def test_agents_runner_handoff_chain(monkeypatch, tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task_agents_handoff")
    monkeypatch.setenv("CORTEXPILOT_RUN_ID", run_id)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(tmp_path / "runtime"))

    class DummyAgent:
        def __init__(self, name: str, instructions: str, mcp_servers: list):
            self.name = name
            self.instructions = instructions
            self.mcp_servers = mcp_servers

    class DummyRunner:
        @staticmethod
        def run_streamed(agent, prompt, **kwargs):
            if agent.name.startswith("CortexPilotHandoff_") or agent.name == "CortexPilotOwner":
                payload = {
                    "summary": "handoff summary",
                    "risks": ["risk-1"],
                }
                return DummyStreamResult(json.dumps(payload))
            payload = {
                "task_id": "task_agents_handoff",
                "status": "SUCCESS",
                "summary": "ok",
                "evidence_refs": {"thread_id": "thread-handoff"},
                "failure": None,
            }
            return DummyStreamResult(json.dumps(payload))

    class DummyMCP:
        def __init__(self, params=None):
            self.params = params

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    agents_mod = types.ModuleType("agents")
    agents_mod.Agent = DummyAgent
    agents_mod.Runner = DummyRunner
    agents_mod.set_default_openai_api = lambda key: None
    agents_mod.RunConfig = DummyRunConfig
    agents_mod.ModelSettings = DummyModelSettings
    mcp_mod = types.ModuleType("agents.mcp")
    mcp_mod.MCPServerStdio = DummyMCP

    monkeypatch.setitem(sys.modules, "agents", agents_mod)
    monkeypatch.setitem(sys.modules, "agents.mcp", mcp_mod)

    worktree = tmp_path / "worktree"
    worktree.mkdir()
    repo_root = Path(__file__).resolve().parents[3]
    schema_path = repo_root / "schemas" / "task_result.v1.json"

    contract = _base_contract("task_agents_handoff")
    contract["owner_agent"]["role"] = "TECH_LEAD"
    contract["assigned_agent"]["role"] = "WORKER"

    runner = AgentsRunner(store)
    result = runner.run_contract(contract, worktree, schema_path, mock_mode=False)

    assert result["status"] == "SUCCESS"
    events_text = (tmp_path / run_id / "events.jsonl").read_text(encoding="utf-8")
    assert "AGENT_HANDOFF_REQUESTED" in events_text
    assert "AGENT_HANDOFF_RESULT" in events_text


def test_agents_runner_invalid_output(monkeypatch, tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task_agents_invalid")
    monkeypatch.setenv("CORTEXPILOT_RUN_ID", run_id)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    class DummyAgent:
        def __init__(self, name: str, instructions: str, mcp_servers: list):
            self.name = name
            self.instructions = instructions
            self.mcp_servers = mcp_servers

    class DummyRunner:
        @staticmethod
        def run_streamed(agent, prompt, **kwargs):
            return DummyStreamResult("not-json")

    class DummyMCP:
        def __init__(self, params=None):
            self.params = params

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    agents_mod = types.ModuleType("agents")
    agents_mod.Agent = DummyAgent
    agents_mod.Runner = DummyRunner
    agents_mod.set_default_openai_api = lambda key: None
    agents_mod.RunConfig = DummyRunConfig
    agents_mod.ModelSettings = DummyModelSettings
    mcp_mod = types.ModuleType("agents.mcp")
    mcp_mod.MCPServerStdio = DummyMCP

    monkeypatch.setitem(sys.modules, "agents", agents_mod)
    monkeypatch.setitem(sys.modules, "agents.mcp", mcp_mod)

    worktree = tmp_path / "worktree"
    worktree.mkdir()
    repo_root = Path(__file__).resolve().parents[3]
    schema_path = repo_root / "schemas" / "task_result.v1.json"

    runner = AgentsRunner(store)
    result = runner.run_contract(_base_contract("task_agents_invalid"), worktree, schema_path, mock_mode=False)
    assert result["status"] == "FAILED"
    assert "output not json" in result["summary"]
