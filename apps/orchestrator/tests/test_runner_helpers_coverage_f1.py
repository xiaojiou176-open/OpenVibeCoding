from __future__ import annotations

import types
from pathlib import Path

import pytest

from openvibecoding_orch.runners import agents_mcp_runtime
from openvibecoding_orch.runners import agents_runner_execution_helpers as execution_helpers
from openvibecoding_orch.runners.provider_resolution import ProviderCredentials
from openvibecoding_orch.store.run_store import RunStore


def test_agents_mcp_runtime_key_resolution_exception_and_empty_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise(*_args, **_kwargs):
        raise RuntimeError("resolver boom")

    monkeypatch.setattr(agents_mcp_runtime, "resolve_preferred_api_key", _raise)

    creds_with_openai = types.SimpleNamespace(openai_api_key="openai-fallback")
    assert (
        agents_mcp_runtime._resolve_preferred_api_key_for_provider(creds_with_openai, "openai")
        == "openai-fallback"
    )

    creds_empty = types.SimpleNamespace()
    assert agents_mcp_runtime._resolve_preferred_api_key_for_provider(creds_empty, "custom-provider") == ""


def test_agents_mcp_runtime_materialize_worker_codex_home_fallback_catalog_branch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    role_home = tmp_path / "role-home"
    fallback_home_parent = tmp_path / "fake-home"
    fallback_home = fallback_home_parent / ".codex"
    role_home.mkdir(parents=True, exist_ok=True)
    fallback_home.mkdir(parents=True, exist_ok=True)

    (role_home / "config.toml").write_text('model_provider = "gemini"\n', encoding="utf-8")
    (role_home / "requirements.toml").write_text("name = \"reqs\"\n", encoding="utf-8")
    (fallback_home / "config.toml").write_text(
        "\n".join(
            [
                'model_provider = "gemini"',
                '[model_providers.gemini]',
                'base_url = "https://gemini.local/v1"',
                "",
                '[mcp_servers."01-filesystem"]',
                'command = ["python", "-m", "dummy"]',
                "",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("CODEX_HOME", str(role_home))
    monkeypatch.delenv("OPENVIBECODING_CODEX_BASE_HOME", raising=False)
    monkeypatch.setenv("OPENVIBECODING_CODEX_MODEL", "gemini-model")
    monkeypatch.setattr(agents_mcp_runtime.Path, "home", staticmethod(lambda: fallback_home_parent))
    monkeypatch.setattr(agents_mcp_runtime, "resolve_runtime_provider_from_env", lambda: "gemini")
    monkeypatch.setattr(
        agents_mcp_runtime,
        "resolve_provider_credentials",
        lambda: types.SimpleNamespace(
            gemini_api_key="gemini-key",
            openai_api_key="",
            anthropic_api_key="",
            equilibrium_api_key="",
        ),
    )
    monkeypatch.setattr(
        agents_mcp_runtime.agents_prompting,
        "resolve_role_prompt_path",
        lambda _role, _worktree_path: tmp_path / "role-prompt.md",
    )

    store = RunStore(runs_root=tmp_path / "runs")
    out = agents_mcp_runtime.materialize_worker_codex_home(
        store=store,
        run_id="run-1",
        task_id="task-1",
        tool_set=["01-filesystem"],
        role="WORKER",
        worktree_path=tmp_path,
        skip_role_prompt=False,
        resolve_codex_base_url=lambda: "https://provider.example/v1",
    )
    text = (out / "config.toml").read_text(encoding="utf-8")
    assert 'model_provider = "gemini"' in text
    assert 'model = "gemini-model"' in text
    assert 'env_key = "GEMINI_API_KEY"' not in text
    assert "experimental_bearer_token" not in text
    assert 'model_instructions_file = "' in text
    assert 'developer_instructions = ""' in text
    assert (out / "requirements.toml").exists()


def test_agents_mcp_runtime_materialize_worker_codex_home_strips_generic_secret_keys(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    role_home = tmp_path / "role-home"
    base_home = tmp_path / "base-home"
    role_home.mkdir(parents=True, exist_ok=True)
    base_home.mkdir(parents=True, exist_ok=True)

    (role_home / "config.toml").write_text(
        "\n".join(
            [
                'model_provider = "gemini"',
                "[model_providers.gemini]",
                'password = "should-not-persist"',
                'secret = "should-not-persist"',
                'token = "should-not-persist"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (base_home / "config.toml").write_text(
        "\n".join(
            [
                'model_provider = "gemini"',
                "",
                '[mcp_servers."01-filesystem"]',
                'command = ["python", "-m", "dummy"]',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("CODEX_HOME", str(role_home))
    monkeypatch.setenv("OPENVIBECODING_CODEX_BASE_HOME", str(base_home))
    monkeypatch.setattr(agents_mcp_runtime, "resolve_runtime_provider_from_env", lambda: "gemini")
    monkeypatch.setattr(
        agents_mcp_runtime,
        "resolve_provider_credentials",
        lambda: types.SimpleNamespace(
            gemini_api_key="gemini-key",
            openai_api_key="",
            anthropic_api_key="",
            equilibrium_api_key="",
        ),
    )
    monkeypatch.setattr(
        agents_mcp_runtime.agents_prompting,
        "resolve_role_prompt_path",
        lambda _role, _worktree_path: None,
    )

    store = RunStore(runs_root=tmp_path / "runs")
    out = agents_mcp_runtime.materialize_worker_codex_home(
        store=store,
        run_id="run-strip-generic-secrets",
        task_id="task-strip-generic-secrets",
        tool_set=["01-filesystem"],
        role="WORKER",
        worktree_path=tmp_path,
        skip_role_prompt=True,
    )
    text = (out / "config.toml").read_text(encoding="utf-8")
    assert 'password = "should-not-persist"' not in text
    assert 'secret = "should-not-persist"' not in text
    assert 'token = "should-not-persist"' not in text


def test_agents_mcp_runtime_materialize_worker_codex_home_strips_nested_agent_tables(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    role_home = tmp_path / "role-home"
    base_home = tmp_path / "base-home"
    role_home.mkdir(parents=True, exist_ok=True)
    base_home.mkdir(parents=True, exist_ok=True)

    (role_home / "config.toml").write_text(
        '\n'.join(
            [
                'model_provider = "gemini"',
                "",
                "[agents.l2-debugger]",
                'description = "debug worker"',
                'config_file = "agents/l2-debugger.toml"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    (base_home / "config.toml").write_text(
        '\n'.join(
            [
                'model_provider = "gemini"',
                "",
                '[mcp_servers."01-filesystem"]',
                'command = ["python", "-m", "dummy"]',
                "",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("CODEX_HOME", str(role_home))
    monkeypatch.setenv("OPENVIBECODING_CODEX_BASE_HOME", str(base_home))
    monkeypatch.setattr(agents_mcp_runtime, "resolve_runtime_provider_from_env", lambda: "gemini")
    monkeypatch.setattr(
        agents_mcp_runtime,
        "resolve_provider_credentials",
        lambda: types.SimpleNamespace(
            gemini_api_key="gemini-key",
            openai_api_key="",
            anthropic_api_key="",
            equilibrium_api_key="",
        ),
    )
    monkeypatch.setattr(
        agents_mcp_runtime.agents_prompting,
        "resolve_role_prompt_path",
        lambda _role, _worktree_path: None,
    )

    store = RunStore(runs_root=tmp_path / "runs")
    out = agents_mcp_runtime.materialize_worker_codex_home(
        store=store,
        run_id="run-strip-agents",
        task_id="task-strip-agents",
        tool_set=["01-filesystem"],
        role="WORKER",
        worktree_path=tmp_path,
        skip_role_prompt=True,
    )
    text = (out / "config.toml").read_text(encoding="utf-8")
    assert "[agents.l2-debugger]" not in text
    assert 'config_file = "agents/l2-debugger.toml"' not in text


def test_agents_runner_execution_provider_resolution_edge_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    creds = ProviderCredentials(
        gemini_api_key="",
        openai_api_key="",
        anthropic_api_key="",
        equilibrium_api_key="eq-key",
    )

    assert (
        execution_helpers._resolve_preferred_api_key_for_provider(
            creds,
            "codex_equilibrium",
        )
        == "eq-key"
    )
    assert (
        execution_helpers._resolve_preferred_api_key_for_provider(
            creds,
            "google-genai",
            base_url="http://127.0.0.1:1456/v1",
        )
        == "eq-key"
    )

    monkeypatch.setattr(
        execution_helpers,
        "resolve_preferred_api_key",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("unexpected-resolver-error")),
    )
    fallback_creds = ProviderCredentials(
        gemini_api_key="",
        openai_api_key="openai-key",
        anthropic_api_key="",
        equilibrium_api_key="",
    )
    assert (
        execution_helpers._resolve_preferred_api_key_for_provider(
            fallback_creds,
            "unknown-provider",
        )
        == "openai-key"
    )
    assert (
        execution_helpers._resolve_preferred_api_key_for_provider(
            ProviderCredentials("", "", "", ""),
            "unknown-provider",
        )
        == ""
    )
