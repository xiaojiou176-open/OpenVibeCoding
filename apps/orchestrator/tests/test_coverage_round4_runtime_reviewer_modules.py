from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import pytest

from openvibecoding_orch.chain import runtime_helpers as runtime_helpers
from openvibecoding_orch.contract import validator as validator_mod
from openvibecoding_orch.reviewer import reviewer as reviewer_mod
from openvibecoding_orch.runners import codex_runner as codex_mod
from openvibecoding_orch.store.run_store import RunStore


def _output_schema_artifacts(role: str = "worker") -> list[dict]:
    schema_root = Path(__file__).resolve().parents[3] / "schemas"
    schema_name = "agent_task_result.v1.json"
    if role.lower() in {"reviewer"}:
        schema_name = "review_report.v1.json"
    if role.lower() in {"test", "test_runner"}:
        schema_name = "test_report.v1.json"
    schema_path = schema_root / schema_name
    sha = hashlib.sha256(schema_path.read_bytes()).hexdigest()
    return [
        {
            "name": f"output_schema.{role.lower()}",
            "uri": f"schemas/{schema_name}",
            "sha256": sha,
        }
    ]


def _base_contract(task_id: str) -> dict:
    return {
        "task_id": task_id,
        "owner_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "assigned_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "inputs": {"spec": "mock", "artifacts": _output_schema_artifacts("worker")},
        "required_outputs": [{"name": "mock_output.txt", "type": "file", "acceptance": "ok"}],
        "allowed_paths": ["mock_output.txt"],
        "forbidden_actions": [],
        "acceptance_tests": [{"name": "noop", "cmd": "echo ok", "must_pass": True}],
        "tool_permissions": {
            "filesystem": "workspace-write",
            "shell": "on-request",
            "network": "deny",
            "mcp_tools": ["codex"],
        },
        "mcp_tool_set": ["01-filesystem"],
        "timeout_retry": {"timeout_sec": 1, "max_retries": 0, "retry_backoff_sec": 0},
        "rollback": {"strategy": "git_reset_hard", "baseline_ref": "HEAD"},
        "evidence_links": [],
        "log_refs": {"run_id": "", "paths": {}},
    }


def test_validator_helper_edge_branches(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(validator_mod, "_REPO_ROOT", tmp_path)

    resolved = validator_mod.resolve_agent_registry_path()
    assert resolved == tmp_path / "policies" / "agent_registry.json"
    assert validator_mod._schema_root() == tmp_path / "schemas"
    assert validator_mod._resolve_output_schema_artifact(["not-a-dict"], "worker") is None

    assert validator_mod._is_truthy(None) is False
    assert validator_mod._is_truthy("ENFORCE") is True
    assert validator_mod._contains_plan_marker(123) is False
    assert validator_mod._contains_plan_marker("   ") is False
    assert validator_mod._normalize_command(None) == ""
    assert validator_mod._is_trivial_acceptance_command(":") is True

    monkeypatch.setenv("OPENVIBECODING_SUPERPOWERS_GATE_ENFORCE", "1")
    assert validator_mod.is_superpowers_gate_required({}) is True
    monkeypatch.delenv("OPENVIBECODING_SUPERPOWERS_GATE_ENFORCE", raising=False)
    assert validator_mod.is_superpowers_gate_required({"evidence_links": [1, "no-match"]}) is False
    assert (
        validator_mod.is_superpowers_gate_required(
            {"evidence_links": [" superpowers://required "]}
        )
        is True
    )


def test_validator_allowed_path_and_registry_guard_branches() -> None:
    invalid = validator_mod.find_invalid_allowed_paths([123, "", "src/*.py"])
    assert len(invalid) == 3
    # Force explicit fail-closed markers that are normalized away by default helper.
    original_normalize = validator_mod._normalize_allowed_path
    try:
        validator_mod._normalize_allowed_path = lambda value: value  # type: ignore[assignment]
        invalid2 = validator_mod.find_invalid_allowed_paths(["/tmp/x", "../x", ".runtime-cache/run"])
    finally:
        validator_mod._normalize_allowed_path = original_normalize  # type: ignore[assignment]
    assert len(invalid2) == 3
    assert validator_mod.is_wide_path(123) is False
    assert validator_mod.is_wide_path("") is True
    assert validator_mod.is_wide_path(".runtime-cache/tmp") is False
    original_normalize2 = validator_mod._normalize_allowed_path
    try:
        validator_mod._normalize_allowed_path = lambda value: value  # type: ignore[assignment]
        assert validator_mod.is_wide_path(".runtime-cache/tmp") is True
    finally:
        validator_mod._normalize_allowed_path = original_normalize2  # type: ignore[assignment]
    assert validator_mod.is_wide_path("src/") is True
    assert validator_mod.find_wide_paths(["src/", 7, "apps/orchestrator/tests"]) == ["src/"]

    with pytest.raises(ValueError, match="owner invalid"):
        validator_mod._ensure_agent_in_registry({}, "not-dict", "owner")
    with pytest.raises(ValueError, match="owner.agent_id missing"):
        validator_mod._ensure_agent_in_registry({}, {"role": "WORKER"}, "owner")
    with pytest.raises(ValueError, match="owner.role missing"):
        validator_mod._ensure_agent_in_registry({}, {"agent_id": "a"}, "owner")
    with pytest.raises(ValueError, match="owner not registered"):
        validator_mod._ensure_agent_in_registry({"agents": ["bad-entry"]}, {"agent_id": "a", "role": "WORKER"}, "owner")


def test_validator_schema_registry_missing_and_load_schema_not_found(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    schema_root = tmp_path / "schemas"
    schema_root.mkdir(parents=True, exist_ok=True)
    (schema_root / "alpha.json").write_text("{}", encoding="utf-8")
    (schema_root / "schema_registry.json").write_text(
        json.dumps({"version": "v1", "schemas": {}}),
        encoding="utf-8",
    )
    check = validator_mod.check_schema_registry(schema_root)
    assert check["status"] == "mismatch"
    assert "alpha.json" in check["missing"]

    repo_root = tmp_path / "repo"
    (repo_root / "schemas").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(validator_mod, "_REPO_ROOT", repo_root)
    validator = validator_mod.ContractValidator(schema_root=tmp_path / "empty")
    with pytest.raises(FileNotFoundError, match="Schema not found"):
        validator._load_schema("not-found.schema.json")


def test_validator_superpowers_gate_required_branch_violations() -> None:
    payload = {
        "evidence_links": ["superpowers://required"],
        "inputs": {"spec": " ", "artifacts": [7, {"name": "artifact-without-marker"}]},
        "required_outputs": [7, {"name": "report", "acceptance": "done"}],
        "handoff_chain": {"enabled": False, "roles": ["PM"], "max_handoffs": 0},
        "acceptance_tests": [7, {"must_pass": False, "cmd": "echo ok"}],
    }
    gate = validator_mod.evaluate_superpowers_gate(payload)
    assert gate["required"] is True
    assert gate["ok"] is False
    codes = {item["code"] for item in gate["violations"]}
    assert {"missing_spec", "missing_plan_evidence", "invalid_handoff_chain", "missing_reviewer_stage", "missing_test_stage"} <= codes


def test_validator_enforce_contract_rules_output_schema_and_superpowers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    schema_root = tmp_path / "schemas"
    schema_root.mkdir(parents=True, exist_ok=True)
    schema_file = schema_root / "agent_task_result.v1.json"
    schema_file.write_text("{}", encoding="utf-8")
    validator = validator_mod.ContractValidator(schema_root=schema_root)

    payload = {
        "allowed_paths": ["apps/orchestrator/tests"],
        "mcp_tool_set": ["01-filesystem"],
        "owner_agent": {"agent_id": "owner-1", "role": "WORKER"},
        "assigned_agent": {"agent_id": "owner-1", "role": "WORKER"},
        "inputs": {
            "artifacts": [
                {
                    "name": "output_schema.worker",
                    "uri": "schemas/agent_task_result.v1.json",
                    "sha256": "declared-mismatch",
                }
            ]
        },
    }
    registry = {"agents": [{"agent_id": "owner-1", "role": "WORKER"}]}
    monkeypatch.setattr(validator_mod, "_load_agent_registry", lambda: registry)
    monkeypatch.setattr(validator_mod, "_resolve_output_schema_path", lambda *args, **kwargs: schema_file)
    monkeypatch.setattr(validator_mod, "_schema_hash", lambda _path: "expected-sha")

    with pytest.raises(ValueError, match="output_schema sha256 mismatch"):
        validator._enforce_contract_rules(payload)

    payload["inputs"]["artifacts"][0]["sha256"] = "expected-sha"
    monkeypatch.setattr(
        validator_mod,
        "evaluate_superpowers_gate",
        lambda _payload: {"required": True, "ok": False, "violations": [{"code": "missing_plan_evidence"}]},
    )
    with pytest.raises(ValueError, match="superpowers gate violation"):
        validator._enforce_contract_rules(payload)


def test_runtime_helpers_edge_branches(tmp_path: Path) -> None:
    contract = {}
    updated = runtime_helpers.ensure_output_schema_artifact(contract)
    assert isinstance(updated["inputs"], dict)
    assert isinstance(updated["inputs"]["artifacts"], list)
    assert updated["inputs"]["artifacts"]

    store = RunStore(runs_root=tmp_path / "runs")
    dep_run = store.create_run("dep")
    assert runtime_helpers.dependency_artifact(store, "dep", dep_run) is None
    assert runtime_helpers.dependency_patch_artifact(store, "dep", dep_run) is None
    assert (
        runtime_helpers.should_propagate_dependency_patch(
            {"kind": "contract", "payload": {"assigned_agent": {"role": "WORKER"}, "task_type": "IMPLEMENT"}}
        )
        is True
    )
    assert runtime_helpers.resolve_contract_from_dependency(None, 0) is None
    assert runtime_helpers.resolve_contract_from_dependency({"evidence_refs": []}, 0) is None
    assert runtime_helpers.resolve_contract_from_dependency({"evidence_refs": {"contracts": []}}, 0) is None

    normalized = json.loads(runtime_helpers.normalize_fanin_summary("1", [" dep-1 ", ""]))
    assert normalized["notes"] == "1"
    assert normalized["dependency_run_ids"] == ["dep-1"]

    normalized2 = json.loads(
        runtime_helpers.normalize_fanin_summary(
            json.dumps(
                {
                    "dependency_run_ids": "bad",
                    "inconsistencies": [{"severity": "unexpected"}, 123],
                }
            ),
            ["dep-2"],
        )
    )
    assert normalized2["inconsistencies"][0]["severity"] == "medium"
    assert normalized2["inconsistencies"][0]["title"]
    assert normalized2["dependency_run_ids"] == ["dep-2"]

    assert runtime_helpers.artifact_names({"inputs": {"artifacts": "bad"}}) == []

    contract_policy = {"inputs": {"spec": "abcdef", "artifacts": "bad"}}
    updated_policy, violations, truncations = runtime_helpers.apply_context_policy(
        contract_policy,
        {"mode": "summary-only", "max_spec_chars": 3},
        owner_role="WORKER",
        step_name="step-x",
    )
    assert updated_policy["inputs"]["artifacts"] == []
    assert any("requires artifacts" in item for item in violations)
    assert any("spec truncated" in item for item in truncations)

    contract_policy2 = {
        "inputs": {
            "spec": "x",
            "artifacts": [
                {"name": ""},
                {"name": "output_schema.worker"},
                {"name": "raw_dump"},
            ],
        }
    }
    _, violations2, _ = runtime_helpers.apply_context_policy(
        contract_policy2,
        {
            "mode": "summary-only",
            "allow_artifact_names": ["raw_dump", "output_schema.worker"],
            "deny_artifact_substrings": ["raw"],
            "require_summary": True,
        },
        owner_role="WORKER",
        step_name="step-y",
    )
    assert any("artifact denied by policy" in item for item in violations2)
    assert any("summary required" in item for item in violations2)


def test_codex_runner_helper_and_no_communicate_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OPENVIBECODING_CODEX_EXEC_TIMEOUT_SEC", "bad")
    assert codex_mod._exec_timeout_sec() == 300

    assert (
        codex_mod._extract_task_result_payload(
            {"status": "SUCCESS", "summary": "ok", "failure": "bad", "task_id": "x"},
            "fallback",
        )["task_id"]
        == "x"
    )
    assert codex_mod._extract_task_result_payload({"item": {"text": 1}}, "task") is None
    assert codex_mod._extract_task_result_payload({"item": {"text": "plain-text"}}, "task") is None
    assert codex_mod._extract_task_result_payload({"item": {"text": "{bad-json"}}, "task") is None
    assert codex_mod._extract_task_result_payload({"item": {"text": "[]"}}, "task") is None
    assert codex_mod._extract_task_result_payload({"item": {"text": json.dumps({"status": ""})}}, "task") is None

    embedded = codex_mod._extract_task_result_payload(
        {
            "item": {
                "text": json.dumps(
                    {"status": "SUCCESS", "failure": "bad", "errors": [{"message": "boom"}]}
                )
            }
        },
        "task-id",
    )
    assert embedded is not None
    assert embedded["failure"] == {"message": "boom"}

    store = RunStore(runs_root=tmp_path / "runs")
    run_id = store.create_run("task_codex_no_communicate")
    monkeypatch.setenv("OPENVIBECODING_RUN_ID", run_id)
    monkeypatch.setenv("OPENVIBECODING_MCP_ONLY", "0")
    monkeypatch.setenv("OPENVIBECODING_CODEX_USE_OUTPUT_SCHEMA", "1")

    payload = {
        "event": "MESSAGE",
        "task_id": "task_codex_no_communicate",
        "status": "SUCCESS",
        "summary": "ok",
        "evidence_refs": {},
        "failure": None,
    }
    captured_cmd: list[str] = []

    class _DummyProcNoCommunicate:
        def __init__(self, cmd: list[str]) -> None:
            self.stdout = io.StringIO(json.dumps(payload, ensure_ascii=False) + "\n")
            self.stderr = io.StringIO("")
            self.returncode = None
            self._cmd = cmd

        def wait(self) -> int:
            return 0

    def _popen(cmd, **kwargs):
        del kwargs
        captured_cmd[:] = cmd
        return _DummyProcNoCommunicate(cmd)

    monkeypatch.setattr("subprocess.Popen", _popen)
    runner = codex_mod.CodexRunner(store)
    schema_path = Path(__file__).resolve().parents[3] / "schemas" / "task_result.v1.json"
    result = runner.run_contract(_base_contract("task_codex_no_communicate"), tmp_path / "worktree", schema_path, mock_mode=False)
    assert result["status"] == "SUCCESS"
    assert "--output-schema" in captured_cmd


def test_reviewer_and_codex_reviewer_edge_branches(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    contract = {
        "task_id": "review-edge",
        "allowed_paths": ["README.md"],
        "task_type": "IMPLEMENT",
        "tool_permissions": {"filesystem": "read-only"},
        "required_outputs": [{"type": "report"}, "bad-entry"],
    }
    report = reviewer_mod.Reviewer().review_task(
        contract,
        diff_text="diff --git a/README.md b/README.md\n",
        test_report={"status": "", "artifacts": []},
        reviewer_meta={"agent_id": "reviewer-1", "codex_thread_id": "thread-r"},
        inputs_meta={"baseline_ref": "", "head_ref": ""},
    )
    assert report["verdict"] == "FAIL"
    assert report["reviewer"]["codex_thread_id"] == "thread-r"
    assert "read-only tasks must not produce a diff" in report["summary"]
    assert "test result is missing" in report["summary"]
    assert "contract alignment:" in report["notes"]

    bad_alignment = reviewer_mod._contract_alignment({"allowed_paths": "bad"}, "", None)
    assert bad_alignment["passed"] is False
    assert "allowed_paths empty or invalid" in bad_alignment["violations"][0]
    policy = reviewer_mod._diff_policy({"task_type": "IMPLEMENT", "tool_permissions": {"filesystem": "read-only"}})
    assert policy["forbid_diff"] is True

    class _ProcFail:
        def __init__(self) -> None:
            self.stdout = io.StringIO("")
            self.stderr = io.StringIO("boom")

        def wait(self) -> int:
            return 1

    monkeypatch.setattr("subprocess.Popen", lambda *args, **kwargs: _ProcFail())
    with pytest.raises(RuntimeError, match="codex reviewer failed"):
        reviewer_mod.CodexReviewer().review_task(contract, "", {"status": "PASS", "artifacts": []}, tmp_path)

    class _ProcNoReport:
        def __init__(self) -> None:
            self.stdout = io.StringIO("\n")
            self.stderr = io.StringIO("")

        def wait(self) -> int:
            return 0

    monkeypatch.setattr("subprocess.Popen", lambda *args, **kwargs: _ProcNoReport())
    with pytest.raises(RuntimeError, match="missing review report"):
        reviewer_mod.CodexReviewer().review_task(contract, "diff", {"status": "PASS", "artifacts": []}, tmp_path)

    base_payload = {
        "run_id": "run-1",
        "task_id": "review-edge",
        "reviewer": {"role": "REVIEWER", "agent_id": "reviewer-1"},
        "reviewed_at": "2024-01-01T00:00:00Z",
        "verdict": "PASS",
        "summary": "ok",
        "scope_check": {"passed": True, "violations": []},
        "evidence": [],
        "produced_diff": False,
    }
    popen_calls: list[list[str]] = []

    class _ProcOk:
        def __init__(self) -> None:
            self.stdout = io.StringIO("\n" + json.dumps(base_payload, ensure_ascii=False) + "\n")
            self.stderr = io.StringIO("")

        def wait(self) -> int:
            return 0

    def _popen_ok(cmd, **kwargs):
        del kwargs
        popen_calls.append(cmd)
        return _ProcOk()

    monkeypatch.setattr("subprocess.Popen", _popen_ok)
    monkeypatch.setenv("OPENVIBECODING_CODEX_USE_OUTPUT_SCHEMA", "1")
    monkeypatch.setenv("OPENVIBECODING_CODEX_MODEL", "gemini-test")

    contract_audit = dict(contract)
    contract_audit["audit_only"] = True
    report_audit = reviewer_mod.CodexReviewer().review_task(
        contract_audit,
        "",
        {"status": "PASS", "artifacts": [{"name": "x", "path": "p", "sha256": "s"}]},
        tmp_path,
        reviewer_meta={"agent_id": "reviewer-2", "codex_thread_id": "thread-audit"},
    )
    assert report_audit["verdict"] == "PASS"
    assert report_audit["reviewer"]["codex_thread_id"] == "thread-audit"

    contract_strict = dict(contract)
    contract_strict["audit_only"] = False
    report_strict = reviewer_mod.CodexReviewer().review_task(
        contract_strict,
        "",
        {"status": "PASS", "artifacts": []},
        tmp_path,
    )
    assert report_strict["verdict"] == "FAIL"
    assert any("--output-schema" in call for call in popen_calls)
    assert any("--model" in call for call in popen_calls)

    run_review_report = reviewer_mod.run_review(
        {"task_id": "review-run-review", "allowed_paths": ["README.md"], "task_type": "PLAN"},
        "",
        {"status": "PASS", "artifacts": []},
    )
    assert run_review_report["verdict"] == "PASS"
