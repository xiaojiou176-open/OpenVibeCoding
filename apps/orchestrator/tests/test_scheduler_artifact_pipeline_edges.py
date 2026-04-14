from __future__ import annotations

import json
from pathlib import Path

from openvibecoding_orch.scheduler import artifact_pipeline


def _contract_with_artifact(name: str, uri: str) -> dict[str, object]:
    return {"inputs": {"artifacts": [{"name": name, "uri": uri}]}}


def test_safe_artifact_path_relative_uri_and_non_dict_agents(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))

    nested = repo_root / "artifacts" / "result.json"
    nested.parent.mkdir(parents=True, exist_ok=True)
    nested.write_text("{}", encoding="utf-8")

    resolved = artifact_pipeline.safe_artifact_path("artifacts/result.json", repo_root)
    assert resolved == nested.resolve()

    ok, reason = artifact_pipeline.validate_assigned_agent(
        {"agents": ["skip-me", {"agent_id": "agent-1", "role": "WORKER"}]},
        {"agent_id": "agent-1", "role": "WORKER"},
    )
    assert ok is True
    assert reason == ""


def test_load_sampling_requests_tool_validation_and_alias(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    non_string_tool = repo_root / "sampling_non_string_tool.json"
    non_string_tool.write_text(json.dumps({"requests": [{"input": "q", "tool": 1}]}), encoding="utf-8")
    payload, error = artifact_pipeline.load_sampling_requests(
        _contract_with_artifact("sampling_requests.json", str(non_string_tool)),
        repo_root,
    )
    assert payload is None
    assert error == "sampling requests invalid tool"

    empty_tool = repo_root / "sampling_empty_tool.json"
    empty_tool.write_text(json.dumps({"requests": [{"input": "q", "tool": "   "}]}), encoding="utf-8")
    payload, error = artifact_pipeline.load_sampling_requests(
        _contract_with_artifact("sampling_requests.json", str(empty_tool)),
        repo_root,
    )
    assert payload is None
    assert error == "sampling requests empty tool"

    invalid_tool = repo_root / "sampling_invalid_tool.json"
    invalid_tool.write_text(json.dumps({"requests": [{"input": "q", "tool": "unsupported"}]}), encoding="utf-8")
    payload, error = artifact_pipeline.load_sampling_requests(
        _contract_with_artifact("sampling_tasks.json", str(invalid_tool)),
        repo_root,
    )
    assert payload is None
    assert error == "sampling requests invalid tool"

    alias_tool = repo_root / "sampling_alias_tool.json"
    alias_tool.write_text(
        json.dumps(
            {
                "requests": [
                    {"id": "1", "input": "first", "tool": "open-interpreter"},
                    {"id": "2", "input": "second", "tool": "open_interpreter"},
                    "fallback-default",
                ]
            }
        ),
        encoding="utf-8",
    )
    payload, error = artifact_pipeline.load_sampling_requests(
        _contract_with_artifact("sampling_requests.json", str(alias_tool)),
        repo_root,
    )
    assert error is None
    assert payload is not None
    assert payload["requested_tools"] == ["open_interpreter", "sampling"]
    assert payload["requests"][0]["tool"] == "open_interpreter"
    assert payload["requests"][1]["tool"] == "open_interpreter"
    assert payload["requests"][2] == {"input": "fallback-default"}
