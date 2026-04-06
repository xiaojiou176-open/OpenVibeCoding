from types import SimpleNamespace

from cortexpilot_orch.runners import agents_runtime_helpers


def test_path_allowed_and_mock_output_path_matrix(monkeypatch) -> None:
    assert not agents_runtime_helpers.path_allowed("apps/a.txt", ["apps/"])
    assert agents_runtime_helpers.path_allowed("apps/a.txt", ["apps/a.txt"])
    assert not agents_runtime_helpers.path_allowed("apps/a.txt", ["docs/"])
    assert not agents_runtime_helpers.path_allowed("", ["apps/"])

    monkeypatch.setattr(agents_runtime_helpers.runner_common, "extract_required_output", lambda _contract: "preferred.txt")
    assert agents_runtime_helpers.mock_output_path({"inputs": {"spec": "normal"}, "allowed_paths": []}) == "preferred.txt"

    monkeypatch.setattr(agents_runtime_helpers.runner_common, "extract_required_output", lambda _contract: "patch.diff")
    assert agents_runtime_helpers.mock_output_path({"inputs": {"spec": "normal"}, "allowed_paths": ["patch.diff"]}) == "patch.diff"
    assert (
        agents_runtime_helpers.mock_output_path(
            {"inputs": {"spec": "normal"}, "allowed_paths": [None, " ", "outputs/"]}  # type: ignore[list-item]
        )
        == "outputs/mock_output.txt"
    )
    assert (
        agents_runtime_helpers.mock_output_path({"inputs": {"spec": "normal"}, "allowed_paths": ["report.json"]})
        == "report.json"
    )
    assert (
        agents_runtime_helpers.mock_output_path({"inputs": {"spec": "normal"}, "allowed_paths": ["reports"]})
        == "reports/mock_output.txt"
    )
    assert agents_runtime_helpers.mock_output_path({"inputs": "bad", "allowed_paths": "bad"}) == "patch.diff"
    assert agents_runtime_helpers.mock_output_path({"inputs": {"spec": "outside allowed"}, "allowed_paths": []}) == "README.md"

    monkeypatch.setattr(agents_runtime_helpers.runner_common, "extract_required_output", lambda _contract: "")
    assert agents_runtime_helpers.mock_output_path({"inputs": {"spec": "normal"}, "allowed_paths": []}) == "mock_output.txt"


def test_path_allowed_trailing_slash_branch_with_path_adapter(monkeypatch) -> None:
    class _FakePath:
        def __init__(self, raw: str) -> None:
            self.raw = raw

        def as_posix(self) -> str:
            return self.raw

    monkeypatch.setattr(agents_runtime_helpers, "Path", _FakePath)
    assert agents_runtime_helpers.path_allowed("apps/a.txt", ["apps/"])


def test_resolve_helpers_and_base_url_resolution(monkeypatch) -> None:
    monkeypatch.setenv("CORTEXPILOT_CODEX_PROFILE", "manual-profile")
    assert agents_runtime_helpers.resolve_profile() == "manual-profile"

    monkeypatch.setenv("CORTEXPILOT_CODEX_PROFILE", "")
    monkeypatch.setattr(agents_runtime_helpers, "pick_profile", lambda: "pooled-profile")
    assert agents_runtime_helpers.resolve_profile() == "pooled-profile"

    monkeypatch.setattr(
        agents_runtime_helpers,
        "get_runner_config",
        lambda: SimpleNamespace(
            agents_model="",
            codex_model="",
            agents_store=True,
            agents_base_url="",
        ),
    )
    assert agents_runtime_helpers.resolve_agents_model() == "gemini-2.5-flash"
    assert agents_runtime_helpers.resolve_agents_store() is True
    assert agents_runtime_helpers.resolve_agents_base_url() == ""
    assert agents_runtime_helpers.resolve_equilibrium_base_url() == "http://127.0.0.1:1456/v1"

    monkeypatch.setattr(
        agents_runtime_helpers,
        "get_runner_config",
        lambda: SimpleNamespace(
            agents_model="gemini-3.1-pro-preview",
            codex_model="unused",
            agents_store=False,
            agents_base_url="https://gateway.example/v1",
        ),
    )
    assert agents_runtime_helpers.resolve_agents_model() == "gemini-3.1-pro-preview"
    assert agents_runtime_helpers.resolve_agents_store() is False
    assert agents_runtime_helpers.resolve_equilibrium_base_url() == "https://gateway.example/v1"


def test_equilibrium_health_url_and_healthcheck(monkeypatch) -> None:
    assert agents_runtime_helpers.equilibrium_health_url("bad-url") == ""
    assert (
        agents_runtime_helpers.equilibrium_health_url("http://127.0.0.1:1456/v1")
        == "http://127.0.0.1:1456/api/health"
    )
    assert agents_runtime_helpers.equilibrium_healthcheck("bad-url") is False

    class _Resp:
        def __init__(self, status: int) -> None:
            self.status = status

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):  # noqa: ANN001
            return False

    monkeypatch.setattr(agents_runtime_helpers, "urlopen", lambda *_args, **_kwargs: _Resp(204))
    assert agents_runtime_helpers.equilibrium_healthcheck("http://127.0.0.1:1456/v1") is True

    monkeypatch.setattr(agents_runtime_helpers, "urlopen", lambda *_args, **_kwargs: _Resp(503))
    assert agents_runtime_helpers.equilibrium_healthcheck("http://127.0.0.1:1456/v1") is False

    def _boom(*_args, **_kwargs):
        raise RuntimeError("probe failed")

    monkeypatch.setattr(agents_runtime_helpers, "urlopen", _boom)
    assert agents_runtime_helpers.equilibrium_healthcheck("http://127.0.0.1:1456/v1") is False


def test_is_local_base_url_matrix() -> None:
    assert agents_runtime_helpers.is_local_base_url("http://127.0.0.1:1456/v1")
    assert agents_runtime_helpers.is_local_base_url("http://localhost:1456/v1")
    assert agents_runtime_helpers.is_local_base_url("http://0.0.0.0:1456/v1")
    assert not agents_runtime_helpers.is_local_base_url("https://api.openai.com/v1")
