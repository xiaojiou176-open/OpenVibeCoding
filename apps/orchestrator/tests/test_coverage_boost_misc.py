import json
import subprocess
from pathlib import Path

import pytest

from cortexpilot_orch.contract import validator as validator_mod
from cortexpilot_orch.gates import diff_gate
from cortexpilot_orch.gates.mcp_concurrency_gate import validate_mcp_concurrency
from cortexpilot_orch.gates.mcp_gate import validate_mcp_tools
from cortexpilot_orch.runners import agents_prompting
from cortexpilot_orch.runners import common as runner_common


def _init_git_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "tester"], cwd=repo, check=True, capture_output=True, text=True)
    (repo / "README.md").write_text("hello", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True, text=True)


def test_mcp_gate_and_concurrency_paths(tmp_path: Path, monkeypatch) -> None:
    # mcp_allowlist: repo_root=None
    res_none = validate_mcp_tools(["codex", "search"], ["codex"], repo_root=None)
    assert res_none["ok"] is True

    repo = tmp_path / "repo"
    (repo / "policies").mkdir(parents=True, exist_ok=True)

    # invalid json -> default allowlist
    (repo / "policies" / "mcp_allowlist.json").write_text("{", encoding="utf-8")
    res_invalid = validate_mcp_tools(["codex"], ["codex"], repo_root=repo)
    assert res_invalid["ok"] is True

    # non-dict -> default
    (repo / "policies" / "mcp_allowlist.json").write_text("[]", encoding="utf-8")
    res_non_dict = validate_mcp_tools(["codex"], ["codex"], repo_root=repo)
    assert res_non_dict["ok"] is True

    # allow/deny both active
    (repo / "policies" / "mcp_allowlist.json").write_text(
        json.dumps({"allow": ["codex", "search"], "deny": ["search"]}),
        encoding="utf-8",
    )
    res_allow_deny = validate_mcp_tools(["codex", "search", "x"], ["codex", "search"], repo_root=repo)
    assert res_allow_deny["ok"] is False
    assert res_allow_deny["allowed"] == ["codex"]
    assert res_allow_deny["missing"] == ["search"]

    # concurrency gate
    assert validate_mcp_concurrency("single")["ok"] is True

    monkeypatch.delenv("CORTEXPILOT_MCP_PROXY_ENABLED", raising=False)
    proxy_disabled = validate_mcp_concurrency("proxy")
    assert proxy_disabled["ok"] is False

    monkeypatch.setenv("CORTEXPILOT_MCP_PROXY_ENABLED", "1")
    proxy_enabled = validate_mcp_concurrency("proxy")
    assert proxy_enabled["ok"] is True

    monkeypatch.delenv("CORTEXPILOT_MCP_ALLOW_MULTI", raising=False)
    multi_disabled = validate_mcp_concurrency("multi")
    assert multi_disabled["ok"] is False

    monkeypatch.setenv("CORTEXPILOT_MCP_ALLOW_MULTI", "yes")
    multi_enabled = validate_mcp_concurrency("multi-client")
    assert multi_enabled["ok"] is True

    invalid_mode = validate_mcp_concurrency("weird-mode")
    assert invalid_mode["ok"] is False


def test_runner_common_branches(monkeypatch, tmp_path: Path) -> None:
    contract = {"task_id": "task-1"}
    monkeypatch.setenv("CORTEXPILOT_RUN_ID", "run-env")
    assert runner_common.resolve_run_id(contract) == "run-env"

    assert runner_common.normalize_status("ok", "FAILED") == "SUCCESS"
    assert runner_common.normalize_status("error", "SUCCESS") == "FAILED"
    assert runner_common.normalize_status("blocked", "SUCCESS") == "BLOCKED"
    assert runner_common.normalize_status(None, "SUCCESS") == "SUCCESS"

    refs = runner_common.build_evidence_refs("thread-1", "session-1")
    assert refs["thread_id"] == "thread-1"
    assert refs["session_id"] == "session-1"

    payload = {
        "task_id": "task-x",
        "status": "SUCCEEDED",
        "diff_summary": "diff",
        "evidence_refs": {"a": 1},
        "contracts": [1, {"ok": True}],
        "handoff_payload": {"next": "pm"},
    }
    coerced = runner_common.coerce_task_result(payload, {"task_id": "fallback"}, {"thread_id": "t"}, "FAILED")
    assert coerced["status"] == "SUCCESS"
    assert coerced["evidence_refs"]["thread_id"] == "t"
    assert coerced["contracts"] == [{"ok": True}]
    assert coerced["handoff_payload"] == {"next": "pm"}

    failed = runner_common.coerce_task_result({}, {"task_id": "task-f"}, None, "FAILED", failure_reason="boom")
    assert failed["status"] == "FAILED"
    assert failed["failure"] == {"message": "boom"}

    assert runner_common.extract_instruction({"inputs": {"spec": "x"}}) == "x"
    assert runner_common.extract_instruction({"instruction": "inst"}) == "inst"
    assert runner_common.extract_instruction({"objective": "obj"}) == "obj"
    context_pack = tmp_path / "context_pack.json"
    context_pack.write_text(
        json.dumps(
            {
                "trigger_reason": "contamination",
                "source_session_id": "thread-1",
                "global_state_summary": "Need explicit handoff.",
                "actor_handoff_summary": "Resume from proof room.",
                "required_reads": ["contract.json", "reports/task_result.json"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    instruction = runner_common.extract_instruction(
        {
            "inputs": {
                "spec": "continue task",
                "artifacts": [{"name": "context_pack.json", "uri": str(context_pack)}],
            }
        },
        tmp_path,
    )
    assert "continue task" in instruction
    assert "Context Pack Fallback" in instruction
    assert "trigger_reason: contamination" in instruction

    assert runner_common.extract_required_output({"required_outputs": [{"name": "a.txt"}]}) == "a.txt"
    assert runner_common.extract_required_output({"required_outputs": ["b.txt"]}) == "b.txt"
    assert runner_common.extract_required_output({"required_outputs": [123]}) is None
    assert runner_common.extract_required_output({}) is None


def test_agents_prompting_branches(tmp_path: Path, monkeypatch) -> None:
    worktree = tmp_path / "worktree"
    worktree.mkdir(parents=True, exist_ok=True)

    with monkeypatch.context() as ctx:
        ctx.setattr(agents_prompting, "resolve_roles_root", lambda _worktree: None)
        assert agents_prompting.load_role_prompt("WORKER", worktree) == ""
        assert agents_prompting.resolve_role_prompt_path("WORKER", worktree) is None

    roles_dir = worktree / "codex" / "roles"
    roles_dir.mkdir(parents=True, exist_ok=True)
    (roles_dir / "50_worker_core.md").write_text("role prompt", encoding="utf-8")

    assert agents_prompting.resolve_roles_root(worktree) == roles_dir
    assert agents_prompting.load_role_prompt("WORKER", worktree) == "role prompt"
    assert agents_prompting.resolve_role_prompt_path("WORKER", worktree) == roles_dir / "50_worker_core.md"

    contract_missing_inputs = {}
    schema_root = tmp_path / "schemas"
    schema_root.mkdir(parents=True, exist_ok=True)

    with pytest.raises(RuntimeError, match="output_schema artifact missing"):
        agents_prompting.resolve_output_schema_path(contract_missing_inputs, "WORKER", schema_root)

    bad_uri_contract = {"inputs": {"artifacts": [{"name": "output_schema.worker", "uri": ""}]}}
    with pytest.raises(RuntimeError, match="uri missing"):
        agents_prompting.resolve_output_schema_path(bad_uri_contract, "WORKER", schema_root)

    wrong_name = schema_root / "wrong.json"
    wrong_name.write_text("{}", encoding="utf-8")
    wrong_name_contract = {
        "inputs": {"artifacts": [{"name": "output_schema.worker", "uri": str(wrong_name)}]}
    }
    with pytest.raises(RuntimeError, match="mismatch"):
        agents_prompting.resolve_output_schema_path(wrong_name_contract, "WORKER", schema_root)

    expected = schema_root / "agent_task_result.v1.json"
    expected.write_text("{}", encoding="utf-8")
    ok_contract = {
        "inputs": {"artifacts": [{"name": "output_schema.worker", "uri": str(expected)}]}
    }
    resolved = agents_prompting.resolve_output_schema_path(ok_contract, "WORKER", schema_root)
    assert resolved == expected

    assert agents_prompting.load_output_schema(schema_root / "missing.json") == ""
    (schema_root / "invalid.json").write_text("{", encoding="utf-8")
    assert agents_prompting.load_output_schema(schema_root / "invalid.json") == ""

    assert agents_prompting.is_fixed_json_template("Output JSON only") is True
    assert agents_prompting.is_fixed_json_template("RETURN EXACTLY THIS JSON") is True
    assert agents_prompting.extract_fixed_json_payload("{\"ok\":true}") == {"ok": True}
    assert agents_prompting.extract_fixed_json_payload("not-json") is None

    decorated_fixed = agents_prompting.decorate_instruction(
        "WORKER", "RETURN EXACTLY THIS JSON {\"ok\":true}", worktree, expected, expected.name
    )
    assert "RETURN EXACTLY THIS JSON" in decorated_fixed

    decorated = agents_prompting.decorate_instruction(
        "WORKER", "do task", worktree, expected, expected.name
    )
    assert "Output JSON only" in decorated
    assert "role prompt" in decorated

    monkeypatch.setenv("CORTEXPILOT_CODEX_MODEL", "gpt-test")
    codex_payload = agents_prompting.build_codex_payload(
        {"tool_permissions": {"filesystem": "workspace-write", "shell": "deny"}},
        "do",
        worktree,
    )
    assert codex_payload["sandbox"] == "workspace-write"
    assert codex_payload["approval-policy"] == "never"
    assert codex_payload["model"] == "gpt-test"

    instruction = agents_prompting.agent_instructions(
        "task-1", "codex", {"prompt": "x"}, False, "agent_task_result.v1.json"
    )
    assert "Call the MCP tool" in instruction
    assert agents_prompting.user_prompt("fix", "agent_task_result.v1.json").startswith("Execute")


def test_validator_registry_and_schema_registry(tmp_path: Path, monkeypatch) -> None:
    # schema registry states
    schema_root = tmp_path / "schemas"
    schema_root.mkdir(parents=True, exist_ok=True)
    (schema_root / "a.json").write_text("{}", encoding="utf-8")

    missing_registry = validator_mod.check_schema_registry(schema_root)
    assert missing_registry["status"] == "missing"

    (schema_root / "schema_registry.json").write_text("{", encoding="utf-8")
    invalid_registry = validator_mod.check_schema_registry(schema_root)
    assert invalid_registry["status"] == "invalid"

    (schema_root / "schema_registry.json").write_text(
        json.dumps({"version": "v1", "schemas": {"a.json": {"sha256": "deadbeef"}, "extra.json": {"sha256": "x"}}}),
        encoding="utf-8",
    )
    mismatch_registry = validator_mod.check_schema_registry(schema_root)
    assert mismatch_registry["status"] == "mismatch"
    assert "a.json" in mismatch_registry["mismatched"]
    assert "extra.json" in mismatch_registry["extra"]

    # resolve agent registry path fallbacks
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "policies").mkdir(parents=True, exist_ok=True)
    (repo / "policies" / "agent_registry.json").write_text("{}", encoding="utf-8")
    resolved = validator_mod.resolve_agent_registry_path(repo)
    assert resolved == repo / "policies" / "agent_registry.json"

    # _load_agent_registry error paths
    missing_path = tmp_path / "missing_agent_registry.json"
    monkeypatch.setattr(validator_mod, "_agent_registry_path", lambda: missing_path)
    with pytest.raises(ValueError, match="agent_registry missing"):
        validator_mod._load_agent_registry()

    bad_json = tmp_path / "bad_agent_registry.json"
    bad_json.write_text("{", encoding="utf-8")
    monkeypatch.setattr(validator_mod, "_agent_registry_path", lambda: bad_json)
    with pytest.raises(ValueError, match="agent_registry invalid"):
        validator_mod._load_agent_registry()


def test_diff_gate_parser_branches_and_fail_paths(tmp_path: Path, monkeypatch) -> None:
    assert diff_gate._is_internal_memory_file(".codex-memory.jsonl") is True
    assert diff_gate._is_internal_memory_file("foo/.codex-memory.20260208.jsonl") is True
    assert diff_gate._is_internal_memory_file("docs/readme.md") is False

    assert diff_gate._split_z_output("A\0B\0") == ["A", "B"]

    name_status = "R100\0old.txt\0new.txt\0M\0keep.txt\0"
    parsed_name_status = diff_gate._parse_name_status(name_status)
    assert "old.txt" in parsed_name_status and "new.txt" in parsed_name_status and "keep.txt" in parsed_name_status

    raw_output = ":120000 100644 a b M\0link.txt\0:160000 160000 a b M\0submodule\0"
    symlinks, submodules = diff_gate._parse_raw(raw_output)
    assert isinstance(symlinks, list)
    assert isinstance(submodules, list)

    numstat_output = "-\0-\0bin.dat\0"
    binaries = diff_gate._parse_numstat(numstat_output)
    assert "bin.dat" in binaries

    repo = tmp_path / "repo"
    _init_git_repo(repo)
    (repo / "a.txt").write_text("a", encoding="utf-8")
    subprocess.run(["git", "add", "a.txt"], cwd=repo, check=True, capture_output=True, text=True)

    def _fake_git(cmd: list[str], cwd: Path):
        if "--name-status" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "M\0a.txt\0", "")
        if "--raw" in cmd:
            return subprocess.CompletedProcess(cmd, 0, ":120000 100644 a b M\0link.txt\0", "")
        if "--numstat" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if "status" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(diff_gate, "_git", _fake_git)
    symlink_result = diff_gate.validate_diff(repo, ["a.txt"], baseline_ref="HEAD")
    assert isinstance(symlink_result["ok"], bool)
    assert "changed_files" in symlink_result

    def _fake_git_binary(cmd: list[str], cwd: Path):
        if "--name-status" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "M\0a.txt\0", "")
        if "--raw" in cmd:
            return subprocess.CompletedProcess(cmd, 0, ":100644 100644 a b M\0a.txt\0", "")
        if "--numstat" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "-\0-\0bin.dat\0", "")
        if "status" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(diff_gate, "_git", _fake_git_binary)
    binary_result = diff_gate.validate_diff(repo, ["a.txt"], baseline_ref="HEAD")
    assert binary_result["ok"] is False
    assert binary_result["reason"] == "binary changes are not allowed"

    assert diff_gate.run_diff_gate(repo, ["a.txt"], baseline_ref="HEAD")["ok"] is False
