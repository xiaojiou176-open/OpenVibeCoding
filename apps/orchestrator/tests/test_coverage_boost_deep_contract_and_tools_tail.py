from pathlib import Path

import pytest

from cortexpilot_orch.contract import compiler as compiler_mod


def test_compiler_helper_edges(tmp_path: Path, monkeypatch) -> None:
    schema_root = tmp_path / "schemas"
    schema_root.mkdir(parents=True, exist_ok=True)
    (schema_root / "agent_task_result.v1.json").write_text("{}", encoding="utf-8")

    artifact = compiler_mod._build_output_schema_artifact("WORKER", schema_root)
    assert artifact["name"] == "output_schema.worker"

    with pytest.raises(ValueError, match="output schema missing"):
        compiler_mod._build_output_schema_artifact("REVIEWER", schema_root)

    injected = compiler_mod._inject_output_schema_artifact(
        [{"name": "output_schema.worker", "uri": "old"}, {"name": "keep", "uri": "x"}],
        "WORKER",
        schema_root,
    )
    assert any(item.get("name") == "keep" for item in injected if isinstance(item, dict))
    assert any(item.get("name") == "output_schema.worker" for item in injected if isinstance(item, dict))

    assert compiler_mod._resolve_assigned_agent({"assigned_agent": {"role": "WORKER", "agent_id": "a"}}, None)["agent_id"] == "a"
    assert compiler_mod._resolve_assigned_agent({}, {"role": "REVIEWER", "agent_id": "b"})["role"] == "REVIEWER"

    assert compiler_mod._coerce_value(None, "deny", {"deny": 0, "allow": 1}) == "deny"
    assert compiler_mod._coerce_value("unknown", "deny", {"deny": 0}) == "unknown"

    registry = {
        "agents": [
            {
                "role": "WORKER",
                "agent_id": "agent-1",
                "defaults": {"sandbox": "read-only", "approval_policy": "deny", "network": "deny"},
                "capabilities": {"mcp_tools": ["codex"]},
            }
        ]
    }
    monkeypatch.setattr(compiler_mod, "_load_agent_registry", lambda: registry)
    contract = {
        "assigned_agent": {"role": "WORKER", "agent_id": "agent-1"},
        "tool_permissions": {
            "filesystem": "danger-full-access",
            "shell": "on-request",
            "network": "allow",
            "mcp_tools": ["codex", "sampling"],
        },
    }
    compiler_mod._apply_role_defaults(contract)
    assert contract["tool_permissions"]["filesystem"] == "read-only"
    assert contract["tool_permissions"]["shell"] == "deny"
    assert contract["tool_permissions"]["network"] == "deny"
    assert contract["tool_permissions"]["mcp_tools"] == ["codex"]
