import sys
from pathlib import Path

import pytest

sys.dont_write_bytecode = True


@pytest.fixture(autouse=True)
def _allow_codex_exec(monkeypatch):
    monkeypatch.setenv("OPENVIBECODING_ALLOW_CODEX_EXEC", "1")
    monkeypatch.setenv("OPENVIBECODING_API_AUTH_REQUIRED", "0")
    yield


@pytest.fixture(autouse=True)
def _default_codex_home(monkeypatch, tmp_path_factory):
    codex_home = tmp_path_factory.mktemp("codex_home")
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("OPENVIBECODING_CODEX_BASE_HOME", str(codex_home))
    if not Path(codex_home).exists():
        Path(codex_home).mkdir(parents=True, exist_ok=True)
    config_path = Path(codex_home) / "config.toml"
    if not config_path.exists():
        config_path.write_text(
            '\n'.join(
                [
                    'model_provider = "codex_equilibrium"',
                    'model = "gemini-2.5-flash"',
                    '',
                    '[mcp_servers."01-filesystem"]',
                    'command = ["python", "-m", "dummy"]',
                    "",
                ]
            ),
            encoding="utf-8",
        )
    yield


@pytest.fixture(autouse=True)
def _sanitize_provider_credentials(monkeypatch):
    # Keep tests hermetic: host machine provider keys must not alter test behavior.
    for key in (
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    yield
