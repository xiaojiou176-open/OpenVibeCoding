import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from openvibecoding_orch.contract import compiler as compiler_mod
from openvibecoding_orch.contract import validator as validator_mod
from openvibecoding_orch.gates import diff_gate
from openvibecoding_orch.runners import tool_runner as tool_runner_mod
from openvibecoding_orch.runners.tool_runner import ToolRunner
from openvibecoding_orch.store.run_store import RunStore


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "tester"], cwd=repo, check=True, capture_output=True, text=True)
    (repo / "README.md").write_text("hello", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True, text=True)


def test_validator_registry_resolution_and_loading_edges(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    policies = repo / "policies"
    policies.mkdir(parents=True, exist_ok=True)
    preferred = policies / "agent_registry.json"
    preferred.write_text("{}", encoding="utf-8")

    resolved = validator_mod.resolve_agent_registry_path(repo)
    assert resolved == preferred

    fallback_root = tmp_path / "fallback"
    fallback_root.mkdir(parents=True, exist_ok=True)
    fallback_registry = fallback_root / "policies" / "agent_registry.json"
    fallback_registry.parent.mkdir(parents=True, exist_ok=True)
    fallback_registry.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(validator_mod, "_REPO_ROOT", fallback_root)
    assert validator_mod.resolve_agent_registry_path(repo) == preferred

    monkeypatch.setenv("OPENVIBECODING_AGENT_REGISTRY", "relative/registry.json")
    assert validator_mod.resolve_agent_registry_path(repo) == (repo / "relative/registry.json").resolve()

    absolute_override = tmp_path / "absolute-registry.json"
    monkeypatch.setenv("OPENVIBECODING_AGENT_REGISTRY", str(absolute_override))
    assert validator_mod.resolve_agent_registry_path(repo) == absolute_override


def test_validator_load_registry_schema_validation_paths(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "root"
    root.mkdir(parents=True, exist_ok=True)
    registry_path = root / "policies" / "agent_registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(validator_mod, "_REPO_ROOT", root)
    monkeypatch.setattr(validator_mod, "_agent_registry_path", lambda: registry_path)

    with pytest.raises(ValueError, match="schema missing"):
        validator_mod._load_agent_registry()

    schemas = root / "schemas"
    schemas.mkdir(parents=True, exist_ok=True)
    schema_path = schemas / "agent_registry.v1.json"
    schema_path.write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {
                    "agents": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "agent_id": {"type": "string"},
                                "role": {"type": "string"},
                            },
                            "required": ["agent_id", "role"],
                        },
                    }
                },
                "required": ["agents"],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="schema validation failed"):
        validator_mod._load_agent_registry()

    registry_path.write_text(json.dumps({"agents": [{"agent_id": "agent-1", "role": "WORKER"}]}), encoding="utf-8")
    payload = validator_mod._load_agent_registry()
    assert isinstance(payload, dict)
    assert payload["agents"][0]["agent_id"] == "agent-1"


def test_validator_contract_rule_and_schema_path_edges(tmp_path: Path, monkeypatch) -> None:
    schema_root = tmp_path / "schemas"
    schema_root.mkdir(parents=True, exist_ok=True)
    (schema_root / "agent_task_result.v1.json").write_text("{}", encoding="utf-8")

    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)

    with pytest.raises(ValueError, match="uri missing"):
        validator_mod._resolve_output_schema_path({}, schema_root, repo_root, "agent_task_result.v1.json")

    with pytest.raises(ValueError, match="not found"):
        validator_mod._resolve_output_schema_path(
            {"uri": "schemas/not-found.json"},
            schema_root,
            repo_root,
            "agent_task_result.v1.json",
        )

    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="must live under"):
        validator_mod._resolve_output_schema_path(
            {"uri": str(outside)},
            schema_root,
            repo_root,
            "agent_task_result.v1.json",
        )

    target = schema_root / "agent_task_result.v1.json"
    with pytest.raises(ValueError, match="output_schema mismatch"):
        validator_mod._resolve_output_schema_path(
            {"uri": str(target)},
            schema_root,
            repo_root,
            "review_report.v1.json",
        )

    resolved = validator_mod._resolve_output_schema_path(
        {"uri": str(target)},
        schema_root,
        repo_root,
        "agent_task_result.v1.json",
    )
    assert resolved == target.resolve()

    normalized = validator_mod._normalize_contract_payload(
        {
            "inputs": {"artifacts": {"name": "x"}},
            "tool_permissions": {"mcp_tools": ["01-filesystem"]},
        }
    )
    assert isinstance(normalized["inputs"]["artifacts"], list)
    assert normalized["mcp_tool_set"] == ["01-filesystem"]

    registry_ok = {
        "agents": [
            {"agent_id": "agent-1", "role": "WORKER"},
            {"agent_id": "agent-2", "role": "REVIEWER"},
        ]
    }
    monkeypatch.setattr(validator_mod, "_load_agent_registry", lambda: registry_ok)

    validator = validator_mod.ContractValidator(schema_root=schema_root)
    payload = {
        "allowed_paths": ["README.md"],
        "rollback": {"strategy": "git_revert_commit", "target_ref": 1},
        "policy_pack": "low",
        "mcp_tool_set": ["01-filesystem"],
        "owner_agent": {"agent_id": "agent-1", "role": "WORKER"},
        "assigned_agent": {"agent_id": "agent-1", "role": "WORKER"},
    }
    with pytest.raises(ValueError, match="target_ref invalid"):
        validator._enforce_contract_rules(payload)

    payload["rollback"] = {"strategy": "git_reset_hard"}
    payload["policy_pack"] = "extreme"
    with pytest.raises(ValueError, match="policy_pack invalid"):
        validator._enforce_contract_rules(payload)

    payload["policy_pack"] = "medium"
    payload["mcp_tool_set"] = []
    payload["tool_permissions"] = {}
    with pytest.raises(ValueError, match="mcp_tool_set missing or empty"):
        validator._enforce_contract_rules(payload)

    payload["tool_permissions"] = {"mcp_tools": ["01-filesystem"]}
    validator._enforce_contract_rules(payload)

    registry_file = schema_root / "schema_registry.json"
    sha = hashlib.sha256((schema_root / "agent_task_result.v1.json").read_bytes()).hexdigest()
    registry_file.write_text(
        json.dumps(
            {
                "version": "v1",
                "schemas": {
                    "agent_task_result.v1.json": {"sha256": sha},
                },
            }
        ),
        encoding="utf-8",
    )
    check = validator_mod.check_schema_registry(schema_root)
    assert check["status"] == "ok"


def test_diff_gate_parser_and_validate_branches(tmp_path: Path, monkeypatch) -> None:
    assert diff_gate._is_internal_memory_file("codex-memory.20260208.jsonl") is True
    assert diff_gate._is_internal_memory_file("codex-memory.20260208.jsonl.bak") is True
    assert diff_gate._is_internal_memory_file(".codex-memory.20260208.jsonl.bak") is True

    root = tmp_path / "root"
    root.mkdir(parents=True, exist_ok=True)
    assert diff_gate._is_within(root / "a.txt", root) is True
    assert diff_gate._is_within(tmp_path / "outside.txt", root) is False

    assert diff_gate._parse_name_status("C100\0a.txt\0b.txt\0") == ["a.txt", "b.txt"]
    assert diff_gate._parse_name_status("R100\0only-old.txt\0") == []

    symlinks, submodules = diff_gate._parse_raw("garbage\0:100644\0")
    assert symlinks == []
    assert submodules == []

    binaries = diff_gate._parse_numstat("-\0-\0old.bin\0new.bin\0")
    assert "old.bin" in binaries
    assert "new.bin" in binaries
    assert diff_gate._looks_like_numstat_value("12") is True
    assert diff_gate._looks_like_numstat_value("-") is True
    assert diff_gate._looks_like_numstat_value("x") is False

    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "src").mkdir(parents=True, exist_ok=True)
    (repo / "src" / "app.py").write_text("print('ok')", encoding="utf-8")

    def _raw_fail(cmd: list[str], cwd: Path):
        del cwd
        if "--name-status" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "M\0src/app.py\0", "")
        if "--raw" in cmd:
            return subprocess.CompletedProcess(cmd, 1, "", "raw fail")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(diff_gate, "_git", _raw_fail)
    raw_failed = diff_gate.validate_diff(repo, ["src/"], baseline_ref="HEAD")
    assert raw_failed["ok"] is False
    assert raw_failed["reason"] == "raw fail"

    def _numstat_fail(cmd: list[str], cwd: Path):
        del cwd
        if "--name-status" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "M\0src/app.py\0", "")
        if "--raw" in cmd:
            return subprocess.CompletedProcess(cmd, 0, ":100644 100644 a b M\0src/app.py\0", "")
        if "--numstat" in cmd:
            return subprocess.CompletedProcess(cmd, 1, "", "numstat fail")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(diff_gate, "_git", _numstat_fail)
    numstat_failed = diff_gate.validate_diff(repo, ["src/"], baseline_ref="HEAD")
    assert numstat_failed["ok"] is False
    assert numstat_failed["reason"] == "numstat fail"

    def _submodule_change(cmd: list[str], cwd: Path):
        del cwd
        if "--name-status" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "M\0src/app.py\0", "")
        if "--raw" in cmd:
            return subprocess.CompletedProcess(cmd, 0, ":160000 160000 a b M\0vendor/submodule\0", "")
        if "--numstat" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if "status" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(diff_gate, "_git", _submodule_change)
    submodule_result = diff_gate.validate_diff(repo, ["src/"], baseline_ref="HEAD")
    assert submodule_result["ok"] is False
    assert submodule_result["reason"] == "submodule changes are not allowed"

    def _all_ok(cmd: list[str], cwd: Path):
        del cwd
        if "--name-status" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "M\0src/app.py\0", "")
        if "--raw" in cmd:
            return subprocess.CompletedProcess(cmd, 0, ":100644 100644 a b M\0src/app.py\0", "")
        if "--numstat" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "1\01\0src/app.py\0", "")
        if "status" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(diff_gate, "_git", _all_ok)
    monkeypatch.setattr(diff_gate, "_is_allowed", lambda *_args, **_kwargs: False)
    cleared = diff_gate.validate_diff(repo, ["src"], baseline_ref="   ")
    assert cleared["baseline_ref"] == "HEAD"
    assert cleared["ok"] is True
    assert cleared["violations"] == []


def test_tool_runner_sync_artifacts_and_success_paths(tmp_path: Path, monkeypatch) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("run_success")

    assert tool_runner_mod._safe_slug("") == "task"
    assert tool_runner_mod._safe_slug("a b/c") == "a_b_c"
    assert len(tool_runner_mod._safe_slug("x" * 100)) == 40

    source = tmp_path / "search_source.json"
    source.write_text("{}", encoding="utf-8")
    synced = tool_runner_mod._sync_search_artifacts(
        store,
        run_id,
        "query text",
        None,
        {
            "ok": True,
            "meta": {
                "artifacts": {
                    "result": str(source),
                    "missing": str(tmp_path / "missing.json"),
                    "empty": "",
                }
            },
        },
    )
    artifacts = synced["meta"]["artifacts"]
    assert "result" in artifacts
    assert Path(artifacts["result"]).exists()
    assert "missing" not in artifacts
    assert "artifacts_original" in synced["meta"]

    passthrough = tool_runner_mod._sync_search_artifacts(store, run_id, "q", "x", {"ok": True})
    assert passthrough == {"ok": True}

    class DummyBrowser:
        def __init__(self, run_dir: Path, headless=None, browser_policy=None):
            self.run_dir = run_dir
            self.headless = headless
            self.browser_policy = browser_policy

        def run_script(self, script: str, url: str) -> dict:
            del script, url
            return {"ok": True, "mode": "playwright", "duration_ms": 1, "artifacts": {}}

    monkeypatch.setattr(tool_runner_mod, "BrowserRunner", DummyBrowser)

    def _search_ok(query: str, provider: str | None = None, browser_policy=None) -> dict:
        del query, provider, browser_policy
        return {
            "ok": True,
            "mode": "web",
            "duration_ms": 2,
            "meta": {"artifacts": {"result": str(source)}},
        }

    monkeypatch.setattr(tool_runner_mod, "search_verify", _search_ok)

    runner = ToolRunner(run_id, store)
    browser_result = runner.run_browser("https://example.com", "return 1", task_id="browser-success")
    assert browser_result["ok"] is True

    search_result = runner.run_search("openvibecoding", provider="chatgpt_web")
    assert search_result["ok"] is True

    store.clear_active_contract(run_id)
    no_contract_mcp = runner.run_mcp("codex", {"payload": {}})
    assert no_contract_mcp["ok"] is False

    contract = {
        "tool_permissions": {"mcp_tools": ["codex"]},
        "task_id": "tool_task",
        "owner_agent": {"role": "WORKER", "agent_id": "agent-1"},
        "assigned_agent": {"role": "WORKER", "agent_id": "agent-1"},
        "inputs": {"spec": "spec", "artifacts": []},
        "required_outputs": [{"name": "out", "type": "file", "acceptance": "ok"}],
        "allowed_paths": ["README.md"],
        "forbidden_actions": [],
        "acceptance_tests": [{"name": "noop", "cmd": "echo ok", "must_pass": True}],
        "mcp_tool_set": ["01-filesystem"],
        "timeout_retry": {"timeout_sec": 1, "max_retries": 0, "retry_backoff_sec": 0},
        "rollback": {"strategy": "git_reset_hard", "baseline_ref": "HEAD"},
        "evidence_links": [],
        "log_refs": {"run_id": run_id, "paths": {}},
    }
    store.write_active_contract(run_id, contract)

    calls: list[tuple[str, dict]] = []

    def _record(run_id_arg: str, tool_name: str, payload: dict) -> None:
        calls.append((tool_name, payload))
        assert run_id_arg == run_id

    monkeypatch.setattr(tool_runner_mod.mcp_adapter, "record_mcp_call", _record)
    allowed = runner.run_mcp("codex", {"payload": {"k": "v"}})
    assert allowed["ok"] is False
    assert allowed["reason"] == "non-adapter mcp execution is not supported"
    assert calls and calls[0][0] == "codex"

    events = (tmp_path / run_id / "events.jsonl").read_text(encoding="utf-8")
    assert "TOOL_USED" in events


def test_diff_gate_remaining_branches(tmp_path: Path, monkeypatch) -> None:
    assert diff_gate._is_protected(".env.local", [".env*"]) is True
    assert diff_gate._parse_name_status("M\0") == []

    broken_rename = diff_gate._parse_raw(":100644 100644 a b R100\0old.txt\0")
    assert broken_rename == ([], [])

    broken_modify = diff_gate._parse_raw(":100644 100644 a b M\0")
    assert broken_modify == ([], [])

    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "a.txt").write_text("a", encoding="utf-8")

    def _symlink_raw(cmd: list[str], cwd: Path):
        del cwd
        if "--name-status" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "M\0a.txt\0", "")
        if "--raw" in cmd:
            return subprocess.CompletedProcess(cmd, 0, ":100644 120000 a b M\0link.txt\0", "")
        if "--numstat" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if "status" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(diff_gate, "_git", _symlink_raw)
    symlink = diff_gate.validate_diff(repo, ["a.txt"], baseline_ref="HEAD")
    assert symlink["ok"] is False
    assert symlink["reason"] == "symlink changes are not allowed"

    def _outside_and_exact(cmd: list[str], cwd: Path):
        del cwd
        if "--name-status" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "M\0../escape.txt\0M\0a.txt\0", "")
        if "--raw" in cmd:
            return subprocess.CompletedProcess(cmd, 0, ":100644 100644 a b M\0a.txt\0", "")
        if "--numstat" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "1\01\0a.txt\0", "")
        if "status" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(diff_gate, "_git", _outside_and_exact)
    monkeypatch.setattr(diff_gate, "_is_allowed", lambda *_args, **_kwargs: False)

    exact_allowed = diff_gate.validate_diff(repo, ["a.txt"], baseline_ref="HEAD")
    assert exact_allowed["ok"] is False
    assert "../escape.txt" in exact_allowed["violations"]

    dot_allowed = diff_gate.validate_diff(repo, ["."], baseline_ref="HEAD")
    assert dot_allowed["ok"] is False


def test_tool_runner_artifact_copy_exception_path(tmp_path: Path, monkeypatch) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("run_copy_exception")
    source = tmp_path / "source.json"
    source.write_text("{}", encoding="utf-8")

    payload = {
        "ok": True,
        "meta": {
            "artifacts": {
                "result": str(source),
            }
        },
    }

    monkeypatch.setattr(tool_runner_mod.shutil, "copy2", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("copy failed")))
    copied = tool_runner_mod._sync_search_artifacts(store, run_id, "q", "p", payload)
    assert copied["meta"]["artifacts"]["result"] == str(source)

    no_artifacts = tool_runner_mod._sync_search_artifacts(
        store,
        run_id,
        "q",
        "p",
        {"ok": True, "meta": {"artifacts": {}}},
    )
    assert no_artifacts["meta"]["artifacts"] == {}
