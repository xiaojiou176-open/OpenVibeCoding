from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from openvibecoding_orch.scheduler import artifact_pipeline


class _Store:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def append_event(self, run_id: str, payload: dict[str, Any]) -> None:
        self.events.append({"run_id": run_id, **payload})


def _artifact_contract(name: str, uri: str) -> dict[str, Any]:
    return {"inputs": {"artifacts": [{"name": name, "uri": uri}]}}


def test_path_helpers_and_artifact_items(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))

    assert artifact_pipeline.is_within(repo_root / "a", repo_root) is True
    assert artifact_pipeline.is_within(Path("/tmp/outside"), repo_root) is False

    repo_file = repo_root / "a.json"
    repo_file.write_text("{}", encoding="utf-8")
    runtime_file = runtime_root / "b.json"
    runtime_file.write_text("{}", encoding="utf-8")

    assert artifact_pipeline.safe_artifact_path(str(repo_file), repo_root) == repo_file.resolve()
    assert artifact_pipeline.safe_artifact_path(str(runtime_file), repo_root) == runtime_file.resolve()
    assert artifact_pipeline.safe_artifact_path("", repo_root) is None
    assert artifact_pipeline.safe_artifact_path("/etc/passwd", repo_root) is None

    assert artifact_pipeline.artifact_items({}) == []
    assert artifact_pipeline.artifact_items({"inputs": []}) == []
    assert artifact_pipeline.artifact_items({"inputs": {"artifacts": "bad"}}) == []
    items = artifact_pipeline.artifact_items({"inputs": {"artifacts": [{"name": "x"}, "bad"]}})
    assert items == [{"name": "x"}]


def test_load_json_artifact(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    missing_payload, missing_error, missing_path = artifact_pipeline.load_json_artifact(
        {"uri": str(repo_root / "missing.json")},
        repo_root,
    )
    assert missing_payload is None
    assert missing_error == "artifact path invalid"
    assert missing_path is None

    bad_file = repo_root / "bad.json"
    bad_file.write_text("{", encoding="utf-8")
    bad_payload, bad_error, bad_path = artifact_pipeline.load_json_artifact({"uri": str(bad_file)}, repo_root)
    assert bad_payload is None
    assert bad_path == bad_file.resolve()
    assert bad_error and bad_error.startswith("artifact json invalid")

    ok_file = repo_root / "ok.json"
    ok_file.write_text('{"ok": true}', encoding="utf-8")
    payload, error, path = artifact_pipeline.load_json_artifact({"uri": str(ok_file)}, repo_root)
    assert payload == {"ok": True}
    assert error is None
    assert path == ok_file.resolve()


def test_load_agent_registry_and_validate_assigned_agent(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    schema_root = tmp_path / "schemas"
    schema_root.mkdir()

    registry_path = repo_root / "policies" / "agent_registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(artifact_pipeline, "resolve_agent_registry_path", lambda _repo_root: registry_path)

    payload, error = artifact_pipeline.load_agent_registry(repo_root, schema_root)
    assert payload is None
    assert error and error.startswith("agent registry missing")

    registry_path.write_text("{", encoding="utf-8")
    payload, error = artifact_pipeline.load_agent_registry(repo_root, schema_root)
    assert payload is None
    assert error and error.startswith("agent registry invalid")

    registry_data = {"agents": [{"agent_id": "a-1", "role": "WORKER"}]}
    registry_path.write_text(json.dumps(registry_data), encoding="utf-8")

    def _raise_validate(self: Any, report: dict[str, Any], schema_name: str) -> None:  # noqa: ARG001
        raise RuntimeError("schema fail")

    monkeypatch.setattr(artifact_pipeline.ContractValidator, "validate_report", _raise_validate)
    payload, error = artifact_pipeline.load_agent_registry(repo_root, schema_root)
    assert payload is None
    assert error and error.startswith("agent registry schema invalid")

    monkeypatch.setattr(
        artifact_pipeline.ContractValidator,
        "validate_report",
        lambda self, report, schema_name: None,
    )
    payload, error = artifact_pipeline.load_agent_registry(repo_root, schema_root)
    assert payload == registry_data
    assert error is None

    ok, reason = artifact_pipeline.validate_assigned_agent(registry_data, {"agent_id": "a-1", "role": "WORKER"})
    assert ok is True
    assert reason == ""

    ok, reason = artifact_pipeline.validate_assigned_agent({"agents": "bad"}, {"agent_id": "a-1", "role": "WORKER"})
    assert ok is False
    assert reason == "agent registry invalid agents list"

    ok, reason = artifact_pipeline.validate_assigned_agent(registry_data, {"agent_id": "a-2", "role": "WORKER"})
    assert ok is False
    assert reason == "assigned agent not registered"


def test_patch_collection_and_patch_apply(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    repo_patch = repo_root / "from_repo.diff"
    repo_patch.write_text("repo", encoding="utf-8")

    worktree_patch = worktree / "from_worktree.diff"
    worktree_patch.write_text("worktree", encoding="utf-8")

    abs_patch = tmp_path / "absolute.diff"
    abs_patch.write_text("abs", encoding="utf-8")

    outside_root = tmp_path / "outside"
    outside_root.mkdir()
    outside_patch = outside_root / "outside.diff"
    outside_patch.write_text("outside", encoding="utf-8")

    artifacts = [
        "bad",
        {"name": "note.txt", "uri": "note.txt"},
        {"name": "repo", "path": "from_repo.diff"},
        {"name": "worktree", "uri": "from_worktree.diff"},
        {"name": "abs", "uri": str(abs_patch)},
        {"name": "outside", "uri": "../outside/outside.diff"},
    ]
    paths = artifact_pipeline.collect_patch_artifacts(artifacts, repo_root, worktree)
    assert repo_patch in paths
    assert worktree_patch in paths
    assert abs_patch in paths
    assert outside_patch not in paths

    assert artifact_pipeline.collect_patch_artifacts({}, repo_root, worktree) == []

    assert artifact_pipeline.should_apply_dependency_patches({"assigned_agent": {"role": "REVIEWER"}}) is True
    assert artifact_pipeline.should_apply_dependency_patches({"task_type": "test"}) is True
    assert artifact_pipeline.should_apply_dependency_patches({"task_type": "build"}) is False

    store = _Store()
    run_id = "run-1"

    # Empty list is a no-op success.
    assert artifact_pipeline.apply_dependency_patches(worktree, [], store, run_id) is True

    # Empty patch file is skipped.
    empty_patch = repo_root / "empty.diff"
    empty_patch.write_text("", encoding="utf-8")
    assert artifact_pipeline.apply_dependency_patches(worktree, [empty_patch], store, run_id) is True
    assert any(event.get("event") == "DEPENDENCY_PATCH_SKIPPED" for event in store.events)

    # Success path.
    monkeypatch.setattr(
        artifact_pipeline.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr=""),
    )
    assert artifact_pipeline.apply_dependency_patches(worktree, [repo_patch], store, run_id) is True
    assert any(event.get("event") == "DEPENDENCY_PATCH_APPLIED" for event in store.events)

    # Failure path.
    def _raise_called_process_error(*args, **kwargs):  # noqa: ARG001
        raise subprocess.CalledProcessError(
            returncode=1,
            cmd=["git", "apply"],
            output="bad out",
            stderr="bad err",
        )

    monkeypatch.setattr(artifact_pipeline.subprocess, "run", _raise_called_process_error)
    assert artifact_pipeline.apply_dependency_patches(worktree, [repo_patch], store, run_id) is False
    failed = [event for event in store.events if event.get("event") == "DEPENDENCY_PATCH_FAILED"]
    assert failed
    assert failed[-1]["meta"]["stderr"] == "bad err"


def test_load_search_requests_matrix(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    schema_root = tmp_path / "schemas"
    schema_root.mkdir()

    monkeypatch.setattr(
        artifact_pipeline.ContractValidator,
        "validate_report",
        lambda self, report, schema_name: None,
    )

    # No artifact.
    payload, error = artifact_pipeline.load_search_requests({}, repo_root, schema_root)
    assert payload is None and error is None

    list_path = repo_root / "search_requests.json"
    list_path.write_text(json.dumps(["one", "two"]), encoding="utf-8")
    payload, error = artifact_pipeline.load_search_requests(
        _artifact_contract("search_requests.json", str(list_path)),
        repo_root,
        schema_root,
    )
    assert error is None
    assert payload and payload["queries"] == ["one", "two"]

    dict_path = repo_root / "search_queries.json"
    dict_path.write_text(
        json.dumps(
            {
                "query": "single",
                "repeat": "bad",
                "parallel": "bad",
                "providers": [],
                "verify": {"provider": "chatgpt_web", "repeat": "bad"},
                "verify_ai": {"enabled": False},
            }
        ),
        encoding="utf-8",
    )
    payload, error = artifact_pipeline.load_search_requests(
        _artifact_contract("search_queries.json", str(dict_path)),
        repo_root,
        schema_root,
    )
    assert error is None
    assert payload and payload["repeat"] == 2
    assert payload["parallel"] == 2
    assert payload["providers"] == ["chatgpt_web", "grok_web"]
    assert payload["verify"]["providers"] == ["chatgpt_web"]
    assert payload["verify"]["repeat"] == 2

    invalid_queries = repo_root / "invalid_queries.json"
    invalid_queries.write_text(json.dumps({"queries": 1}), encoding="utf-8")
    payload, error = artifact_pipeline.load_search_requests(
        _artifact_contract("search_requests.json", str(invalid_queries)),
        repo_root,
        schema_root,
    )
    assert payload is None
    assert error == "search queries invalid"

    invalid_providers = repo_root / "invalid_providers.json"
    invalid_providers.write_text(json.dumps({"queries": ["q"], "providers": 1}), encoding="utf-8")
    payload, error = artifact_pipeline.load_search_requests(
        _artifact_contract("search_requests.json", str(invalid_providers)),
        repo_root,
        schema_root,
    )
    assert payload is None
    assert error == "search providers invalid"

    invalid_verify = repo_root / "invalid_verify.json"
    invalid_verify.write_text(json.dumps({"queries": ["q"], "verify": "bad"}), encoding="utf-8")
    payload, error = artifact_pipeline.load_search_requests(
        _artifact_contract("search_requests.json", str(invalid_verify)),
        repo_root,
        schema_root,
    )
    assert payload is None
    assert error == "search verify config invalid"

    invalid_verify_providers = repo_root / "invalid_verify_providers.json"
    invalid_verify_providers.write_text(
        json.dumps({"queries": ["q"], "verify": {"providers": 1}}),
        encoding="utf-8",
    )
    payload, error = artifact_pipeline.load_search_requests(
        _artifact_contract("search_requests.json", str(invalid_verify_providers)),
        repo_root,
        schema_root,
    )
    assert payload is None
    assert error == "search verify providers invalid"

    invalid_payload = repo_root / "invalid_payload.json"
    invalid_payload.write_text(json.dumps(123), encoding="utf-8")
    payload, error = artifact_pipeline.load_search_requests(
        _artifact_contract("search_requests.json", str(invalid_payload)),
        repo_root,
        schema_root,
    )
    assert payload is None
    assert error == "search requests payload invalid"

    schema_bad = repo_root / "schema_bad.json"
    schema_bad.write_text(json.dumps(["q"]), encoding="utf-8")

    def _raise_schema(self: Any, report: dict[str, Any], schema_name: str) -> None:  # noqa: ARG001
        raise RuntimeError("schema fail")

    monkeypatch.setattr(artifact_pipeline.ContractValidator, "validate_report", _raise_schema)
    payload, error = artifact_pipeline.load_search_requests(
        _artifact_contract("search_requests.json", str(schema_bad)),
        repo_root,
        schema_root,
    )
    assert payload is None
    assert error and error.startswith("search requests schema invalid")


def test_load_browser_tampermonkey_and_sampling_requests(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    schema_root = tmp_path / "schemas"
    schema_root.mkdir()

    monkeypatch.setattr(
        artifact_pipeline.ContractValidator,
        "validate_report",
        lambda self, report, schema_name: None,
    )

    # Browser tasks success and branch coverage.
    browser_path = repo_root / "browser_tasks.json"
    browser_path.write_text(
        json.dumps({"headless": True, "tasks": [{"url": "https://example.com", "script": ""}, {"url": "", "script": "x"}]}),
        encoding="utf-8",
    )
    payload, error = artifact_pipeline.load_browser_tasks(
        _artifact_contract("browser_tasks.json", str(browser_path)),
        repo_root,
        schema_root,
    )
    assert error is None
    assert payload and payload["headless"] is True
    assert payload["tasks"] == [{"url": "https://example.com", "script": ""}]

    browser_invalid = repo_root / "browser_invalid.json"
    browser_invalid.write_text(json.dumps({"tasks": "bad"}), encoding="utf-8")
    payload, error = artifact_pipeline.load_browser_tasks(
        _artifact_contract("browser_tasks.json", str(browser_invalid)),
        repo_root,
        schema_root,
    )
    assert payload is None
    assert error == "browser tasks invalid"

    browser_empty = repo_root / "browser_empty.json"
    browser_empty.write_text(json.dumps({"tasks": [{"script": "x"}]}), encoding="utf-8")
    payload, error = artifact_pipeline.load_browser_tasks(
        _artifact_contract("browser_tasks.json", str(browser_empty)),
        repo_root,
        schema_root,
    )
    assert payload is None
    assert error == "browser tasks empty"

    def _raise_schema(self: Any, report: dict[str, Any], schema_name: str) -> None:  # noqa: ARG001
        raise RuntimeError("schema fail")

    monkeypatch.setattr(artifact_pipeline.ContractValidator, "validate_report", _raise_schema)
    payload, error = artifact_pipeline.load_browser_tasks(
        _artifact_contract("browser_tasks.json", str(browser_path)),
        repo_root,
        schema_root,
    )
    assert payload is None
    assert error and error.startswith("browser tasks schema invalid")

    # Restore schema success for remaining tests.
    monkeypatch.setattr(
        artifact_pipeline.ContractValidator,
        "validate_report",
        lambda self, report, schema_name: None,
    )

    # Tampermonkey with list payload -> dict conversion.
    tamper_list = repo_root / "tamper_list.json"
    tamper_list.write_text(
        json.dumps([
            {"script": "ok", "raw_output": "out"},
            {"script_name": "ok2", "script_content": "code", "url": "https://x"},
            {"name": "skip-no-output"},
        ]),
        encoding="utf-8",
    )
    payload, error = artifact_pipeline.load_tampermonkey_tasks(
        _artifact_contract("tampermonkey_tasks.json", str(tamper_list)),
        repo_root,
        schema_root,
    )
    assert error is None
    assert payload and len(payload["tasks"]) == 2

    tamper_invalid = repo_root / "tamper_invalid.json"
    tamper_invalid.write_text(json.dumps({"tasks": "bad"}), encoding="utf-8")
    payload, error = artifact_pipeline.load_tampermonkey_tasks(
        _artifact_contract("tampermonkey_output.json", str(tamper_invalid)),
        repo_root,
        schema_root,
    )
    assert payload is None
    assert error == "tampermonkey tasks invalid"

    tamper_empty = repo_root / "tamper_empty.json"
    tamper_empty.write_text(json.dumps({"tasks": [{"script": "x"}]}), encoding="utf-8")
    payload, error = artifact_pipeline.load_tampermonkey_tasks(
        _artifact_contract("tampermonkey_tasks.json", str(tamper_empty)),
        repo_root,
        schema_root,
    )
    assert payload is None
    assert error == "tampermonkey tasks empty"

    monkeypatch.setattr(artifact_pipeline.ContractValidator, "validate_report", _raise_schema)
    payload, error = artifact_pipeline.load_tampermonkey_tasks(
        _artifact_contract("tampermonkey_tasks.json", str(tamper_list)),
        repo_root,
        schema_root,
    )
    assert payload is None
    assert error and error.startswith("tampermonkey tasks schema invalid")

    monkeypatch.setattr(
        artifact_pipeline.ContractValidator,
        "validate_report",
        lambda self, report, schema_name: None,
    )

    # Sampling branches.
    sampling_path = repo_root / "sampling_requests.json"
    sampling_path.write_text(
        json.dumps({"requests": ["a", {"id": "2", "prompt": "b", "model": "m"}, {"id": "skip", "prompt": ""}]}),
        encoding="utf-8",
    )
    payload, error = artifact_pipeline.load_sampling_requests(
        _artifact_contract("sampling_requests.json", str(sampling_path)),
        repo_root,
    )
    assert error is None
    assert payload and payload["requests"] == [
        {"input": "a"},
        {"id": "2", "input": "b", "model": "m"},
    ]

    sampling_invalid = repo_root / "sampling_invalid.json"
    sampling_invalid.write_text(json.dumps({"requests": "bad"}), encoding="utf-8")
    payload, error = artifact_pipeline.load_sampling_requests(
        _artifact_contract("sampling_tasks.json", str(sampling_invalid)),
        repo_root,
    )
    assert payload is None
    assert error == "sampling requests invalid"

    sampling_empty = repo_root / "sampling_empty.json"
    sampling_empty.write_text(json.dumps({"requests": [{"prompt": ""}]}), encoding="utf-8")
    payload, error = artifact_pipeline.load_sampling_requests(
        _artifact_contract("sampling_tasks.json", str(sampling_empty)),
        repo_root,
    )
    assert payload is None
    assert error == "sampling requests empty"

    payload, error = artifact_pipeline.load_sampling_requests({}, repo_root)
    assert payload is None and error is None
