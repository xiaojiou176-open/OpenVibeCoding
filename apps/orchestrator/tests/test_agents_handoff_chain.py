import hashlib
import json
import sys
import types
from pathlib import Path

from openvibecoding_orch.runners.agents_runner import AgentsRunner
from openvibecoding_orch.store.run_store import RunStore


class DummyRunConfig:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


class DummyModelSettings:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


class DummyStreamResult:
    def __init__(self, text: str | None) -> None:
        self.final_output = text

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


def _base_contract(task_id: str) -> dict:
    return {
        "task_id": task_id,
        "owner_agent": {"role": "PM", "agent_id": "agent-1", "codex_thread_id": ""},
        "assigned_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "handoff_chain": {"enabled": True, "roles": ["PM", "TECH_LEAD", "WORKER"]},
        "inputs": {"spec": "mock", "artifacts": _output_schema_artifacts("worker")},
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


def test_agents_runner_handoff_chain(monkeypatch, tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task_chain")
    monkeypatch.setenv("OPENVIBECODING_RUN_ID", run_id)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    class DummyAgent:
        def __init__(self, name: str, instructions: str, mcp_servers: list):
            self.name = name
            self.instructions = instructions
            self.mcp_servers = mcp_servers

    outputs = [
        json.dumps({"summary": "tl", "risks": []}),
        json.dumps({"summary": "worker", "risks": ["risk"]}),
        json.dumps(
            {
                "task_id": "task_chain",
                "status": "SUCCESS",
                "summary": "ok",
                "evidence_refs": {"thread_id": "thread-x", "session_id": "session-y"},
                "failure": None,
            }
        ),
    ]

    class DummyRunner:
        @staticmethod
        def run_streamed(agent, prompt, **kwargs):
            return DummyStreamResult(outputs.pop(0))

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
    result = runner.run_contract(_base_contract("task_chain"), worktree, schema_path, mock_mode=False)

    assert result["status"] == "SUCCESS"
    events_text = (tmp_path / run_id / "events.jsonl").read_text(encoding="utf-8")
    assert "AGENT_HANDOFF_CHAIN_STARTED" in events_text
    assert "AGENT_HANDOFF_STEP" in events_text


def test_agents_runner_handoff_chain_timeout_fail_open(monkeypatch, tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task_chain_timeout_fail_open")
    monkeypatch.setenv("OPENVIBECODING_RUN_ID", run_id)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("OPENVIBECODING_AGENTS_HANDOFF_TIMEOUT_FAIL_OPEN", "true")

    class DummyAgent:
        def __init__(self, name: str, instructions: str, mcp_servers: list):
            self.name = name
            self.instructions = instructions
            self.mcp_servers = mcp_servers

    class DummyRunner:
        @staticmethod
        def run_streamed(agent, prompt, **kwargs):
            del prompt, kwargs
            if agent.name.startswith("OpenVibeCodingHandoff_"):
                raise RuntimeError("Request timed out.")
            payload = {
                "task_id": "task_chain_timeout_fail_open",
                "status": "SUCCESS",
                "summary": "ok",
                "evidence_refs": {"thread_id": "thread-x", "session_id": "session-y"},
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
    result = runner.run_contract(_base_contract("task_chain_timeout_fail_open"), worktree, schema_path, mock_mode=False)

    assert result["status"] == "SUCCESS"
    events_text = (tmp_path / run_id / "events.jsonl").read_text(encoding="utf-8")
    assert "AGENT_HANDOFF_TIMEOUT_FAIL_OPEN" in events_text
