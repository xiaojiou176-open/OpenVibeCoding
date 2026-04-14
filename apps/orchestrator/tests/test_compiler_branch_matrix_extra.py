import json
from pathlib import Path

import pytest

from openvibecoding_orch.contract import compiler as compiler_mod


def _plan_base() -> dict:
    return {
        "plan_id": "plan-extra-001",
        "task_id": "plan-extra-001",
        "owner_agent": {"role": "WORKER", "agent_id": "agent-1"},
        "spec": "spec",
        "allowed_paths": ["out.txt"],
        "required_outputs": [{"name": "out.txt", "type": "file", "acceptance": "ok"}],
        "tool_permissions": {
            "filesystem": "workspace-write",
            "shell": "on-request",
            "network": "deny",
            "mcp_tools": ["codex"],
        },
        "mcp_tool_set": ["01-filesystem"],
        "acceptance_tests": [{"name": "noop", "cmd": "echo ok", "must_pass": True}],
        "timeout_retry": {"timeout_sec": 1, "max_retries": 0, "retry_backoff_sec": 0},
        "rollback": {"strategy": "git_reset_hard", "baseline_ref": "HEAD"},
        "evidence_links": [],
    }


def test_compiler_internal_branches_for_defaults_and_forbidden(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    owner = compiler_mod._default_owner_agent()
    assert owner["role"] == "WORKER"
    assert compiler_mod._default_assigned_agent({"role": "UNKNOWN", "agent_id": "x"})["role"] == "WORKER"

    schema_root = Path(__file__).resolve().parents[3] / "schemas"
    artifacts = compiler_mod._inject_output_schema_artifact(
        ["raw", {"name": "output_schema.worker", "uri": "x", "sha256": "y"}],
        "worker",
        schema_root,
    )
    assert "raw" in artifacts
    assert any(isinstance(item, dict) and item.get("name") == "output_schema.worker" for item in artifacts)

    missing_policy = tmp_path / "missing_forbidden.json"
    monkeypatch.setattr(compiler_mod, "_FORBIDDEN_POLICY_FILE", str(missing_policy))
    assert compiler_mod._load_forbidden_actions() == []

    bad_policy = tmp_path / "bad_forbidden.json"
    bad_policy.write_text("{", encoding="utf-8")
    monkeypatch.setattr(compiler_mod, "_FORBIDDEN_POLICY_FILE", str(bad_policy))
    assert compiler_mod._load_forbidden_actions() == []


def test_compiler_registry_and_find_entry_branches(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    missing_registry = tmp_path / "missing_registry.json"
    monkeypatch.setattr(compiler_mod, "resolve_agent_registry_path", lambda: missing_registry)
    assert compiler_mod._load_agent_registry() is None

    bad_registry = tmp_path / "bad_registry.json"
    bad_registry.write_text("{", encoding="utf-8")
    monkeypatch.setattr(compiler_mod, "resolve_agent_registry_path", lambda: bad_registry)
    with pytest.raises(ValueError, match="agent_registry invalid"):
        compiler_mod._load_agent_registry()

    assert compiler_mod._find_registry_entry(None, {"role": "WORKER", "agent_id": "a1"}) is None

    registry = {
        "agents": [
            "not-a-dict",
            {"role": "WORKER", "agent_id": "fallback", "defaults": {"network": "deny"}},
        ]
    }
    found = compiler_mod._find_registry_entry(registry, {"role": "WORKER", "agent_id": "missing"})
    assert isinstance(found, dict)
    assert found.get("agent_id") == "fallback"


def test_compiler_apply_role_defaults_and_compile_artifacts(monkeypatch: pytest.MonkeyPatch) -> None:
    assert compiler_mod._coerce_value("on-request", None, {"on-request": 1}) == "on-request"
    assert compiler_mod._coerce_value("unknown", "deny", {"deny": 0}) == "unknown"

    contract_no_entry = {
        "assigned_agent": {"role": "WORKER", "agent_id": "agent-1"},
        "tool_permissions": {"filesystem": "workspace-write", "shell": "on-request", "network": "allow", "mcp_tools": ["x"]},
    }
    monkeypatch.setattr(compiler_mod, "_load_agent_registry", lambda: {})
    compiler_mod._apply_role_defaults(contract_no_entry)
    assert contract_no_entry["tool_permissions"]["network"] == "allow"

    registry = {
        "agents": [
            {
                "role": "WORKER",
                "agent_id": "agent-1",
                "defaults": {
                    "sandbox": "read-only",
                    "approval_policy": "never",
                    "network": "deny",
                },
                "capabilities": {"mcp_tools": ["codex", "fs"]},
            }
        ]
    }
    monkeypatch.setattr(compiler_mod, "_load_agent_registry", lambda: registry)

    contract_with_defaults = {
        "assigned_agent": {"role": "WORKER", "agent_id": "agent-1"},
        "tool_permissions": {},
    }
    compiler_mod._apply_role_defaults(contract_with_defaults)
    assert set(contract_with_defaults["tool_permissions"]["mcp_tools"]) == {"codex", "fs"}
    assert contract_with_defaults["tool_permissions"]["filesystem"] == "read-only"

    plan = _plan_base()
    plan["artifacts"] = [
        {
            "name": "raw-artifact-item",
            "uri": "artifacts/raw.txt",
            "sha256": "0" * 64,
        }
    ]
    plan["audit_only"] = True
    plan.pop("acceptance_tests", None)
    contract = compiler_mod.compile_plan(plan)
    assert contract["audit_only"] is True
    assert isinstance(contract["inputs"]["artifacts"], list)
    assert any(
        isinstance(item, dict) and item.get("name") == "raw-artifact-item"
        for item in contract["inputs"]["artifacts"]
    )
    assert contract["acceptance_tests"] == [
        {"name": "repo_hygiene", "cmd": "bash scripts/check_repo_hygiene.sh", "must_pass": True}
    ]
