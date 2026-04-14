from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import openvibecoding_orch.cli_coverage_helpers as coverage_helpers


class _FakeResponse:
    def __init__(self, status: int) -> None:
        self.status = status

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001
        return False


def _config_with_runner(*, base_url: str = "", openai_key: str = "", gemini_key: str = "", equilibrium_key: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        runner=SimpleNamespace(
            agents_base_url=base_url,
            openai_api_key=openai_key,
            gemini_api_key=gemini_key,
            equilibrium_api_key=equilibrium_key,
        )
    )


def test_equilibrium_health_url_and_healthcheck_paths(monkeypatch) -> None:
    assert coverage_helpers.equilibrium_health_url("not-a-url") == ""
    assert coverage_helpers.equilibrium_healthcheck("not-a-url") is False

    monkeypatch.setattr(coverage_helpers, "urlopen", lambda *_args, **_kwargs: _FakeResponse(204))
    assert coverage_helpers.equilibrium_healthcheck("http://127.0.0.1:1456/v1") is True

    monkeypatch.setattr(coverage_helpers, "urlopen", lambda *_args, **_kwargs: _FakeResponse(503))
    assert coverage_helpers.equilibrium_healthcheck("http://127.0.0.1:1456/v1") is False

    def _raise_urlopen(*_args, **_kwargs):  # noqa: ANN001
        raise OSError("network down")

    monkeypatch.setattr(coverage_helpers, "urlopen", _raise_urlopen)
    assert coverage_helpers.equilibrium_healthcheck("http://127.0.0.1:1456/v1") is False


def test_enable_lock_cleanup_and_chain_timeout_env_paths(monkeypatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_LOCK_AUTO_CLEANUP", "true")
    monkeypatch.setenv("OPENVIBECODING_LOCK_TTL_SEC", "abc")
    lock_env = coverage_helpers.enable_lock_auto_cleanup_for_coverage()
    assert lock_env["source"] == "env"
    assert lock_env["ttl_source"] == "env"
    assert lock_env["ttl_sec"] == "abc"

    monkeypatch.delenv("OPENVIBECODING_LOCK_AUTO_CLEANUP", raising=False)
    monkeypatch.delenv("OPENVIBECODING_LOCK_TTL_SEC", raising=False)
    lock_default = coverage_helpers.enable_lock_auto_cleanup_for_coverage()
    assert lock_default["source"] == "coverage_execute_default"
    assert lock_default["ttl_sec"] == 120

    monkeypatch.setenv("OPENVIBECODING_CHAIN_EXEC_MODE", "THREAD")
    monkeypatch.setenv("OPENVIBECODING_CHAIN_SUBPROCESS_TIMEOUT_SEC", "12.7")
    chain_env = coverage_helpers.enable_chain_subprocess_timeout_for_coverage()
    assert chain_env["mode"] == "thread"
    assert chain_env["mode_source"] == "env"
    assert chain_env["timeout_sec"] == 12

    monkeypatch.delenv("OPENVIBECODING_CHAIN_EXEC_MODE", raising=False)
    monkeypatch.delenv("OPENVIBECODING_CHAIN_SUBPROCESS_TIMEOUT_SEC", raising=False)
    chain_default = coverage_helpers.enable_chain_subprocess_timeout_for_coverage()
    assert chain_default["mode"] == "subprocess"
    assert chain_default["timeout_sec"] == 300
    assert chain_default["timeout_source"] == "coverage_execute_default"


def test_ensure_python_env_and_prepare_execute_env_modes(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPENVIBECODING_PYTHON", "/tmp/custom-python")
    assert coverage_helpers.ensure_coverage_python_env(tmp_path) == {"python": "/tmp/custom-python", "source": "env"}

    monkeypatch.delenv("OPENVIBECODING_PYTHON", raising=False)
    candidate = tmp_path / ".venv" / "bin" / "python"
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text("#!/bin/sh\n", encoding="utf-8")
    candidate.chmod(0o755)
    python_default = coverage_helpers.ensure_coverage_python_env(tmp_path)
    assert python_default["python"] == str(candidate)
    assert python_default["source"] == "coverage_execute_default"

    monkeypatch.delenv("OPENVIBECODING_RUNNER", raising=False)
    mock_result = coverage_helpers.prepare_coverage_execute_env(
        True,
        load_config_fn=lambda: _config_with_runner(),
        repo_root=tmp_path,
        equilibrium_healthcheck_fn=lambda _url: False,
        equilibrium_health_url_fn=coverage_helpers.equilibrium_health_url,
    )
    assert mock_result["mode"] == "mock"
    assert mock_result["runner"] == "agents"

    monkeypatch.setenv("OPENVIBECODING_RUNNER", "codex")
    runner_selected = coverage_helpers.prepare_coverage_execute_env(
        False,
        load_config_fn=lambda: _config_with_runner(),
        repo_root=tmp_path,
        equilibrium_healthcheck_fn=lambda _url: False,
        equilibrium_health_url_fn=coverage_helpers.equilibrium_health_url,
    )
    assert runner_selected["mode"] == "runner_already_selected"
    assert runner_selected["runner"] == "codex"

    monkeypatch.setenv("OPENVIBECODING_RUNNER", "agents")
    base_url_mode = coverage_helpers.prepare_coverage_execute_env(
        False,
        load_config_fn=lambda: _config_with_runner(base_url="http://service.local/v1"),
        repo_root=tmp_path,
        equilibrium_healthcheck_fn=lambda _url: False,
        equilibrium_health_url_fn=coverage_helpers.equilibrium_health_url,
    )
    assert base_url_mode["mode"] == "agents_base_url_present"
    assert base_url_mode["base_url"] == "http://service.local/v1"

    monkeypatch.setenv("OPENVIBECODING_RUNNER", "agents")
    missing_credentials = coverage_helpers.prepare_coverage_execute_env(
        False,
        load_config_fn=lambda: _config_with_runner(),
        repo_root=tmp_path,
        equilibrium_healthcheck_fn=lambda _url: False,
        equilibrium_health_url_fn=coverage_helpers.equilibrium_health_url,
    )
    assert missing_credentials["mode"] == "missing_credentials"
    assert missing_credentials["runner"] == "agents"
