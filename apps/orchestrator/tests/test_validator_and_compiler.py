import hashlib
import importlib
import json
import sys
from pathlib import Path

import pytest

from cortexpilot_orch.contract.compiler import compile_plan, compile_plan_text
from cortexpilot_orch.contract.validator import (
    ContractValidator,
    validate_contract,
    validate_report,
    find_wide_paths,
)


def _plan_base() -> dict:
    return {
        "plan_id": "plan-0001",
        "task_id": "plan-0001",
        "owner_agent": {"role": "WORKER", "agent_id": "agent-1"},
        "spec": "spec",
        "allowed_paths": ["out.txt"],
        "required_outputs": [{"name": "out.txt", "type": "file", "acceptance": "ok"}],
        "tool_permissions": {"filesystem": "workspace-write", "shell": "on-request", "network": "deny", "mcp_tools": ["codex"]},
        "mcp_tool_set": ["01-filesystem"],
        "acceptance_tests": [{"name": "noop", "cmd": "echo ok", "must_pass": True}],
        "timeout_retry": {"timeout_sec": 1, "max_retries": 0, "retry_backoff_sec": 0},
        "rollback": {"strategy": "git_reset_hard", "baseline_ref": "HEAD"},
        "evidence_links": [],
    }


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


def _contract_base() -> dict:
    return {
        "task_id": "task-0001",
        "owner_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "assigned_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "inputs": {"spec": "spec", "artifacts": _output_schema_artifacts("worker")},
        "required_outputs": [{"name": "out.txt", "type": "file", "acceptance": "ok"}],
        "allowed_paths": ["out.txt"],
        "forbidden_actions": [],
        "acceptance_tests": [{"name": "noop", "cmd": "echo ok", "must_pass": True}],
        "tool_permissions": {"filesystem": "workspace-write", "shell": "on-request", "network": "deny", "mcp_tools": ["codex"]},
        "mcp_tool_set": ["01-filesystem"],
        "timeout_retry": {"timeout_sec": 1, "max_retries": 0, "retry_backoff_sec": 0},
        "rollback": {"strategy": "git_reset_hard", "baseline_ref": "HEAD"},
        "evidence_links": [],
        "log_refs": {"run_id": "", "paths": {}},
    }


def _registry_path() -> Path:
    return Path(__file__).resolve().parents[3] / "policies" / "agent_registry.json"


def test_compile_plan_text_errors() -> None:
    with pytest.raises(ValueError, match="invalid json"):
        compile_plan_text("{")
    with pytest.raises(ValueError, match="payload must be object"):
        compile_plan_text("[]")


def test_contract_validator_import_does_not_eagerly_import_compiler() -> None:
    saved_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "cortexpilot_orch.contract" or name.startswith("cortexpilot_orch.contract.")
    }
    for name in list(saved_modules):
        sys.modules.pop(name, None)

    try:
        validator_module = importlib.import_module("cortexpilot_orch.contract.validator")
        assert validator_module.ContractValidator is not None
        assert "cortexpilot_orch.contract.compiler" not in sys.modules
    finally:
        for name in list(sys.modules):
            if name == "cortexpilot_orch.contract" or name.startswith("cortexpilot_orch.contract."):
                sys.modules.pop(name, None)
        sys.modules.update(saved_modules)


def test_compile_plan_missing_task_id(monkeypatch) -> None:
    plan = _plan_base()
    plan["plan_id"] = ""
    plan.pop("task_id", None)
    monkeypatch.setattr("cortexpilot_orch.contract.compiler.ContractValidator.validate_report", lambda *args, **kwargs: None)
    with pytest.raises(ValueError, match="missing task_id"):
        compile_plan(plan)


def test_compile_plan_parent_task_id() -> None:
    plan = _plan_base()
    plan["parent_task_id"] = "parent-1"
    contract = compile_plan(plan)
    assert contract["parent_task_id"] == "parent-1"


def test_compile_plan_text_valid() -> None:
    plan = _plan_base()
    payload = json.dumps(plan)
    contract = compile_plan_text(payload)
    assert contract["task_id"] == plan["task_id"]


def test_compile_plan_assigned_agent_from_owner() -> None:
    plan = _plan_base()
    plan["owner_agent"]["role"] = "REVIEWER"
    contract = compile_plan(plan)
    assert contract["assigned_agent"]["role"] == "REVIEWER"


def test_compile_plan_inherits_forbidden_actions(monkeypatch) -> None:
    plan = _plan_base()
    plan.pop("forbidden_actions", None)
    monkeypatch.setattr("cortexpilot_orch.contract.compiler._load_forbidden_actions", lambda: ["rm -rf"])
    contract = compile_plan(plan)
    assert "rm -rf" in contract.get("forbidden_actions", [])


def test_validator_schema_missing(tmp_path: Path) -> None:
    validator = ContractValidator(schema_root=tmp_path)
    with pytest.raises(ValueError, match="output_schema"):
        validator.validate_contract(_contract_base())


def test_validator_contract_rules() -> None:
    validator = ContractValidator()
    contract = _contract_base()
    contract["allowed_paths"] = []
    original_validate = validator._validate
    try:
        validator._validate = lambda payload, schema: payload  # type: ignore[assignment]
        with pytest.raises(ValueError, match="allowed_paths is empty"):
            validator.validate_contract(contract)
    finally:
        validator._validate = original_validate  # type: ignore[assignment]

    contract = _contract_base()
    contract["allowed_paths"] = ["*"]
    with pytest.raises(ValueError, match="invalid entries"):
        validator.validate_contract(contract)


def test_find_wide_paths() -> None:
    wide = find_wide_paths(["src/", "README.md", "docs/"])
    assert wide == ["src/", "docs/"]


def test_validate_contract_and_report_file(tmp_path: Path) -> None:
    contract = _contract_base()
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")
    validated = validate_contract(contract_path)
    assert validated["task_id"] == "task-0001"

    report = {
        "run_id": "run-0001",
        "task_id": "task-0001",
        "producer": {"role": "WORKER", "agent_id": "agent-1"},
        "status": "SUCCESS",
        "started_at": "2024-01-01T00:00:00Z",
        "finished_at": "2024-01-01T00:01:00Z",
        "summary": "ok",
        "artifacts": [
            {
                "name": "task_result",
                "path": "reports/task_result.json",
                "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            }
        ],
        "git": {
            "baseline_ref": "HEAD",
            "head_ref": "HEAD",
            "changed_files": {
                "name": "diff_name_only",
                "path": "diff_name_only.txt",
                "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            },
            "patch": {
                "name": "patch",
                "path": "patch.diff",
                "sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
            },
        },
        "gates": {
            "diff_gate": {"passed": True, "violations": []},
            "policy_gate": {"passed": True, "violations": []},
            "review_gate": {"passed": True, "violations": []},
            "tests_gate": {"passed": True, "violations": []},
        },
        "next_steps": {"suggested_action": "none", "notes": "n/a"},
        "failure": None,
    }
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    validated_report = validate_report(report_path, "task_result.v1.json")
    assert validated_report["status"] == "SUCCESS"


def test_compile_plan_enforces_role_defaults() -> None:
    plan = _plan_base()
    plan["tool_permissions"]["network"] = "allow"
    contract = compile_plan(plan)
    assert contract["tool_permissions"]["network"] == "deny"


def test_compile_plan_uses_nontrivial_acceptance_default_when_missing() -> None:
    plan = _plan_base()
    plan.pop("acceptance_tests", None)
    contract = compile_plan(plan)
    assert contract["acceptance_tests"] == [
        {"name": "repo_hygiene", "cmd": "bash scripts/check_repo_hygiene.sh", "must_pass": True}
    ]


def test_validate_contract_rejects_absolute_role_contract_ref(tmp_path: Path) -> None:
    contract = compile_plan(_plan_base())
    absolute_ref = tmp_path / "outside.md"
    absolute_ref.write_text("outside", encoding="utf-8")
    contract["role_contract"]["system_prompt_ref"] = str(absolute_ref)

    with pytest.raises(ValueError, match="repo-relative path"):
        ContractValidator().validate_contract(contract)


def test_validate_contract_rejects_parent_traversal_role_contract_ref() -> None:
    contract = compile_plan(_plan_base())
    contract["role_contract"]["system_prompt_ref"] = "../outside.md"

    with pytest.raises(ValueError, match="within the repository"):
        ContractValidator().validate_contract(contract)


def test_validate_contract_rejects_directory_mcp_bundle_ref() -> None:
    contract = compile_plan(_plan_base())
    contract["role_contract"]["mcp_bundle_ref"] = "schemas#agents(role=WORKER).capabilities.mcp_tools"

    with pytest.raises(ValueError, match="must reference a file"):
        ContractValidator().validate_contract(contract)


def test_validate_contract_rejects_system_prompt_fragments() -> None:
    contract = compile_plan(_plan_base())
    contract["role_contract"]["system_prompt_ref"] = "policies/agents/codex/roles/50_worker_core.md#fragment"

    with pytest.raises(ValueError, match="fragments not allowed"):
        ContractValidator().validate_contract(contract)


def test_compile_plan_searcher_role_contract_accepts_registry_backed_mcp_bundle() -> None:
    plan = _plan_base()
    plan["assigned_agent"] = {"role": "SEARCHER", "agent_id": "agent-1"}
    contract = compile_plan(plan)
    assert (
        contract["role_contract"]["mcp_bundle_ref"]
        == "policies/agent_registry.json#agents(role=SEARCHER).capabilities.mcp_tools"
    )


def test_compile_plan_worker_role_contract_accepts_registry_backed_skills_bundle() -> None:
    contract = compile_plan(_plan_base())
    assert (
        contract["role_contract"]["skills_bundle_ref"]
        == "policies/skills_bundle_registry.json#bundles.worker_delivery_core_v1"
    )


def test_compile_plan_rejects_missing_mcp_bundle_fragment(monkeypatch, tmp_path: Path) -> None:
    registry = json.loads(_registry_path().read_text(encoding="utf-8"))
    registry["role_contracts"]["WORKER"]["mcp_bundle_ref"] = (
        "policies/agent_registry.json#agents(role=WORKER).capabilities.missing"
    )
    registry_path = tmp_path / "agent_registry.json"
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    monkeypatch.setenv("CORTEXPILOT_AGENT_REGISTRY", str(registry_path))

    with pytest.raises(ValueError, match="role_contract.mcp_bundle_ref"):
        compile_plan(_plan_base())


def test_validate_contract_rejects_non_allowlisted_mcp_bundle_fragment() -> None:
    contract = compile_plan(_plan_base())
    contract["role_contract"]["mcp_bundle_ref"] = "schemas/agent_registry.v1.json#/title"

    with pytest.raises(ValueError, match="fragment source must be allowlisted"):
        ContractValidator().validate_contract(contract)


def test_validate_contract_rejects_non_allowlisted_skills_bundle_fragment() -> None:
    contract = compile_plan(_plan_base())
    contract["role_contract"]["skills_bundle_ref"] = "policies/agent_registry.json#role_contracts.WORKER"

    with pytest.raises(ValueError, match="fragment source must be allowlisted"):
        ContractValidator().validate_contract(contract)
