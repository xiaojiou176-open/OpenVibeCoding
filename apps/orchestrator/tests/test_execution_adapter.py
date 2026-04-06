import os
from pathlib import Path

import pytest

from cortexpilot_orch.runners import execution_adapter as adapter
from cortexpilot_orch.store.run_store import RunStore


def test_claude_adapter_injects_anthropic_via_contract_without_mutating_process_env(
    tmp_path: Path, monkeypatch
) -> None:
    captured: dict[str, object] = {}

    class FakeAgentsRunner:
        def __init__(self, _store) -> None:
            pass

        def run_contract(self, contract, worktree_path, schema_path, mock_mode=False):
            captured["provider"] = os.environ.get("CORTEXPILOT_PROVIDER")
            captured["provider_model"] = os.environ.get("CORTEXPILOT_PROVIDER_MODEL")
            captured["provider_base_url"] = os.environ.get("CORTEXPILOT_PROVIDER_BASE_URL")
            captured["contract"] = contract
            captured["worktree_path"] = worktree_path
            captured["schema_path"] = schema_path
            captured["mock_mode"] = mock_mode
            return {"status": "SUCCESS", "summary": "ok", "runner": "fake-claude"}

    monkeypatch.setattr(adapter, "AgentsRunner", FakeAgentsRunner)
    monkeypatch.setenv("CORTEXPILOT_PROVIDER", "openai")
    monkeypatch.setenv("CORTEXPILOT_PROVIDER_MODEL", "gemini-3.1-pro-preview")
    monkeypatch.delenv("CORTEXPILOT_PROVIDER_BASE_URL", raising=False)

    run_store = RunStore(runs_root=tmp_path / "runs")
    claude_adapter = adapter.ClaudeExecutionAdapter(run_store)
    result = claude_adapter.run_contract(
        {
            "task_id": "task-claude",
            "runtime_options": {
                "provider": "openai",
                "execution": {"max_attempts": 1},
            },
        },
        tmp_path / "worktree",
        tmp_path / "schema.json",
        mock_mode=True,
    )

    assert result["status"] == "SUCCESS"
    assert captured["provider"] == "openai"
    assert captured["provider_model"] == "gemini-3.1-pro-preview"
    assert captured["provider_base_url"] is None
    assert captured["mock_mode"] is True
    assert captured["worktree_path"] == tmp_path / "worktree"
    assert captured["schema_path"] == tmp_path / "schema.json"

    adapted_contract = captured["contract"]
    assert isinstance(adapted_contract, dict)
    runtime_options = adapted_contract.get("runtime_options")
    assert isinstance(runtime_options, dict)
    assert runtime_options.get("provider") == "anthropic"
    execution = runtime_options.get("execution")
    assert isinstance(execution, dict)
    assert execution.get("mcp_first") is True
    assert execution.get("max_attempts") == 1

    assert os.environ.get("CORTEXPILOT_PROVIDER") == "openai"
    assert os.environ.get("CORTEXPILOT_PROVIDER_MODEL") == "gemini-3.1-pro-preview"
    assert "CORTEXPILOT_PROVIDER_BASE_URL" not in os.environ


def test_claude_adapter_restores_process_env_even_when_runner_raises(
    tmp_path: Path, monkeypatch
) -> None:
    class FakeAgentsRunner:
        def __init__(self, _store) -> None:
            pass

        def run_contract(self, contract, worktree_path, schema_path, mock_mode=False):
            del contract, worktree_path, schema_path, mock_mode
            raise RuntimeError("runner boom")

    monkeypatch.setattr(adapter, "AgentsRunner", FakeAgentsRunner)
    monkeypatch.setenv("CORTEXPILOT_PROVIDER", "openai")
    monkeypatch.setenv("CORTEXPILOT_PROVIDER_MODEL", "gemini-3.1-pro-preview")
    monkeypatch.setenv("CORTEXPILOT_PROVIDER_BASE_URL", "http://localhost:1456/v1")

    run_store = RunStore(runs_root=tmp_path / "runs")
    claude_adapter = adapter.ClaudeExecutionAdapter(run_store)

    with pytest.raises(RuntimeError, match="runner boom"):
        claude_adapter.run_contract(
            {"task_id": "task-claude-exception"},
            tmp_path / "worktree",
            tmp_path / "schema.json",
            mock_mode=True,
        )

    assert os.environ.get("CORTEXPILOT_PROVIDER") == "openai"
    assert os.environ.get("CORTEXPILOT_PROVIDER_MODEL") == "gemini-3.1-pro-preview"
    assert os.environ.get("CORTEXPILOT_PROVIDER_BASE_URL") == "http://localhost:1456/v1"


def test_codex_adapter_keeps_contract_output_shape_and_passthrough(tmp_path: Path, monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    class FakeCodexRunner:
        def __init__(self, _store) -> None:
            pass

        def run_contract(self, contract, worktree_path, schema_path, mock_mode=False):
            calls.append(
                {
                    "contract": contract,
                    "worktree_path": worktree_path,
                    "schema_path": schema_path,
                    "mock_mode": mock_mode,
                }
            )
            return {
                "status": "SUCCESS",
                "summary": "codex-ok",
                "task_result": {"kind": "task_result", "status": "SUCCESS"},
            }

    monkeypatch.setattr(adapter, "CodexRunner", FakeCodexRunner)

    run_store = RunStore(runs_root=tmp_path / "runs")
    codex_adapter = adapter.CodexExecutionAdapter(run_store)
    contract = {
        "task_id": "task-codex",
        "assigned_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": "origin-thread"},
    }
    worktree = tmp_path / "worktree"
    schema = tmp_path / "schema.json"

    run_out = codex_adapter.run_contract(contract, worktree, schema, mock_mode=False)
    execute_out = codex_adapter.execute(contract, worktree, schema, mock_mode=True)
    resume_out = codex_adapter.resume(contract, worktree, schema, resume_id="resume-thread", mock_mode=True)

    assert run_out["status"] == "SUCCESS"
    assert execute_out["summary"] == "codex-ok"
    assert resume_out["task_result"]["kind"] == "task_result"
    assert len(calls) == 3

    assert calls[0]["contract"] is contract
    assert calls[0]["worktree_path"] == worktree
    assert calls[0]["schema_path"] == schema
    assert calls[0]["mock_mode"] is False

    assert calls[1]["contract"] is contract
    assert calls[1]["mock_mode"] is True

    resumed_contract = calls[2]["contract"]
    assert isinstance(resumed_contract, dict)
    resumed_assigned = resumed_contract.get("assigned_agent")
    assert isinstance(resumed_assigned, dict)
    assert resumed_assigned.get("codex_thread_id") == "resume-thread"
    assert contract["assigned_agent"]["codex_thread_id"] == "origin-thread"
    assert calls[2]["mock_mode"] is True


def test_build_execution_adapter_only_supports_codex_or_claude(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path / "runs")

    codex = adapter.build_execution_adapter(run_store=store, runner_name="codex")
    claude = adapter.build_execution_adapter(run_store=store, runner_name="claude")
    by_provider = adapter.build_execution_adapter(run_store=store, provider="anthropic")

    assert isinstance(codex, adapter.CodexExecutionAdapter)
    assert isinstance(claude, adapter.ClaudeExecutionAdapter)
    assert isinstance(by_provider, adapter.ClaudeExecutionAdapter)

    with pytest.raises(ValueError, match="unsupported runner/provider"):
        adapter.build_execution_adapter(run_store=store, runner_name="agents")
    with pytest.raises(ValueError, match="unsupported runner/provider"):
        adapter.build_execution_adapter(run_store=store, runner_name="app-server")


def test_claude_adapter_supports_does_not_accept_agents_runner(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path / "runs")
    claude = adapter.ClaudeExecutionAdapter(store)
    assert claude.supports(runner_name="claude") is True
    assert claude.supports(provider="claude") is True
    assert claude.supports(provider="anthropic") is True
    assert claude.supports(runner_name="agents") is False


def test_claude_adapter_runner_path_forces_anthropic_provider_semantics(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeAgentsRunner:
        def __init__(self, _store) -> None:
            pass

        def run_contract(self, contract, worktree_path, schema_path, mock_mode=False):
            captured["contract"] = contract
            del worktree_path, schema_path, mock_mode
            return {"status": "SUCCESS"}

    monkeypatch.setattr(adapter, "AgentsRunner", FakeAgentsRunner)
    run_store = RunStore(runs_root=tmp_path / "runs")
    claude = adapter.ClaudeExecutionAdapter(run_store)

    out = claude.run_contract(
        {"task_id": "task-claude-provider", "runtime_options": {"provider": "gemini"}},
        tmp_path / "worktree",
        tmp_path / "schema.json",
        mock_mode=True,
    )

    assert out["status"] == "SUCCESS"
    adapted_contract = captured["contract"]
    assert isinstance(adapted_contract, dict)
    runtime_options = adapted_contract.get("runtime_options")
    assert isinstance(runtime_options, dict)
    assert runtime_options.get("provider") == "anthropic"
