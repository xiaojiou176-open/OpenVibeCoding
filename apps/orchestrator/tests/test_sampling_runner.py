from tooling.mcp.sampling_runner import run_sampling


def test_sampling_provider_mode_requires_api_key(monkeypatch):
    monkeypatch.setenv("CORTEXPILOT_SAMPLING_MODE", "gemini")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    result = run_sampling({"input": "ping"})
    assert result["ok"] is False
    assert "missing" in result.get("error", "").lower()
    assert "api_key" in result.get("error", "").lower() or "api key" in result.get("error", "").lower()


def test_sampling_mock_default(monkeypatch):
    monkeypatch.setenv("CORTEXPILOT_SAMPLING_MODE", "mock")
    result = run_sampling({"input": "ping"})
    assert result["ok"] is True
    assert result["mode"] == "mock"
