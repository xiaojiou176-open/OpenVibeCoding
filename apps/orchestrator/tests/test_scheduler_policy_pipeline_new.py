from __future__ import annotations

from pathlib import Path

from cortexpilot_orch.scheduler import policy_pipeline


def test_policy_basic_extractors_and_normalizers() -> None:
    assert policy_pipeline.allowed_paths({"allowed_paths": ["a", "b"]}) == ["a", "b"]
    assert policy_pipeline.allowed_paths({"allowed_paths": "bad"}) == []

    assert policy_pipeline.forbidden_actions({"forbidden_actions": ["rm"]}) == ["rm"]
    assert policy_pipeline.forbidden_actions({"forbidden_actions": "bad"}) == []

    assert policy_pipeline.acceptance_tests({"acceptance_tests": [{"cmd": "pytest"}]}) == [{"cmd": "pytest"}]
    assert policy_pipeline.acceptance_tests({"acceptance_tests": "bad"}) == []

    assert policy_pipeline.tool_permissions({"tool_permissions": {"network": "enabled"}}) == {"network": "enabled"}
    assert policy_pipeline.tool_permissions({"tool_permissions": []}) == {}

    assert policy_pipeline.network_policy({"tool_permissions": {"network": " Enabled "}}) == "allow"
    assert policy_pipeline.network_policy({"tool_permissions": {"network": 1}}) == "deny"

    assert policy_pipeline.shell_policy({"tool_permissions": {"shell": " On-Request "}}) == "on-request"
    assert policy_pipeline.shell_policy({"tool_permissions": {"shell": 1}}) == "untrusted"

    assert policy_pipeline.filesystem_policy({"tool_permissions": {"filesystem": " Workspace-Write "}}) == "workspace-write"
    assert policy_pipeline.filesystem_policy({"tool_permissions": {"filesystem": 1}}) == "read-only"


def test_codex_shell_policy_and_env_flags(monkeypatch) -> None:
    overridden = policy_pipeline.codex_shell_policy({"tool_permissions": {"network": "deny", "shell": "on-request"}})
    assert overridden["effective_shell"] == "never"
    assert overridden["overridden"] is True

    passthrough = policy_pipeline.codex_shell_policy({"tool_permissions": {"network": "allow", "shell": "untrusted"}})
    assert passthrough["effective_shell"] == "untrusted"
    assert passthrough["overridden"] is False

    monkeypatch.setenv("CORTEXPILOT_MCP_ONLY", "yes")
    assert policy_pipeline.mcp_only_enabled() is True
    monkeypatch.setenv("CORTEXPILOT_MCP_ONLY", "0")
    assert policy_pipeline.mcp_only_enabled() is False

    monkeypatch.setenv("CORTEXPILOT_ALLOW_CODEX_EXEC", "TRUE")
    assert policy_pipeline.allow_codex_exec() is True
    monkeypatch.setenv("CORTEXPILOT_ALLOW_CODEX_EXEC", "")
    assert policy_pipeline.allow_codex_exec() is False


def test_default_policy_pack_and_agent_role_helpers() -> None:
    assert policy_pipeline.default_policy_pack_for_role("pm") == "high"
    assert policy_pipeline.default_policy_pack_for_role("frontend") == "medium"
    assert policy_pipeline.default_policy_pack_for_role("searcher") == "medium"
    assert policy_pipeline.default_policy_pack_for_role("unknown") == "low"

    assert policy_pipeline.agent_role({"role": " reviewer "}) == "REVIEWER"
    assert policy_pipeline.agent_role({}) == ""

    assert policy_pipeline.resolve_policy_pack({"policy_pack": " High "}) == "high"
    assert (
        policy_pipeline.resolve_policy_pack({"assigned_agent": {"role": "TECH_LEAD"}})
        == "high"
    )
    assert (
        policy_pipeline.resolve_policy_pack({"assigned_agent": {"role": "something_else"}})
        == "low"
    )

    assert policy_pipeline.mcp_tools({"tool_permissions": {"mcp_tools": ["a"]}}) == ["a"]
    assert policy_pipeline.mcp_tools({"tool_permissions": {"mcp_tools": "bad"}}) == []

    assert policy_pipeline.is_search_role("SEARCHER") is True
    assert policy_pipeline.is_search_role("WORKER") is False
    graph = policy_pipeline.override_order_graph()
    assert graph["tool_permissions.filesystem"] == "contract.tool_permissions.filesystem -> registry.defaults.sandbox"
    breakpoints = policy_pipeline.build_override_breakpoints(
        ["tool_permissions.filesystem", "tool_permissions.shell", "not-tracked"]
    )
    assert breakpoints == [
        "tool_permissions.filesystem: contract.tool_permissions.filesystem -> registry.defaults.sandbox",
        "tool_permissions.shell: contract.tool_permissions.shell -> registry.defaults.approval_policy",
    ]


def test_find_registry_entry_and_resolve_codex_home(tmp_path: Path) -> None:
    registry = {
        "agents": [
            {"role": "WORKER", "agent_id": "w-1", "codex_home": "worker-home"},
            {"role": "WORKER", "agent_id": "w-2", "codex_home": "worker2-home"},
        ]
    }

    exact = policy_pipeline.find_registry_entry(registry, {"role": "WORKER", "agent_id": "w-2"})
    assert exact and exact["agent_id"] == "w-2"

    fallback = policy_pipeline.find_registry_entry(registry, {"role": "WORKER", "agent_id": "missing"})
    assert fallback and fallback["agent_id"] == "w-1"

    assert policy_pipeline.find_registry_entry(None, {"role": "WORKER"}) is None

    resolved_dir = tmp_path / "worker-home"
    resolved_dir.mkdir()
    value, error = policy_pipeline.resolve_codex_home({"codex_home": "worker-home"}, tmp_path)
    assert error == ""
    assert value == str(resolved_dir.resolve())

    value, error = policy_pipeline.resolve_codex_home(None, tmp_path)
    assert value is None
    assert "missing" in error

    value, error = policy_pipeline.resolve_codex_home({"codex_home": ""}, tmp_path)
    assert value is None
    assert "missing" in error

    value, error = policy_pipeline.resolve_codex_home({"codex_home": "$NOT_SET/home"}, tmp_path)
    assert value is None
    assert "unresolved" in error

    value, error = policy_pipeline.resolve_codex_home({"codex_home": "missing-dir"}, tmp_path)
    assert value is None
    assert "not found" in error

    file_path = tmp_path / "file-home"
    file_path.write_text("x", encoding="utf-8")
    value, error = policy_pipeline.resolve_codex_home({"codex_home": str(file_path)}, tmp_path)
    assert value is None
    assert "not a directory" in error


def test_coerce_and_apply_role_defaults_branches() -> None:
    order = {"read-only": 0, "workspace-write": 1, "danger-full-access": 2}

    assert policy_pipeline.coerce_value("read-only", None, order) == ("read-only", False)
    assert policy_pipeline.coerce_value(None, "workspace-write", order) == ("workspace-write", False)
    assert policy_pipeline.coerce_value("unknown", "workspace-write", order) == ("unknown", False)
    assert policy_pipeline.coerce_value("danger-full-access", "workspace-write", order) == (
        "workspace-write",
        True,
    )
    assert policy_pipeline.coerce_value("read-only", "workspace-write", order) == ("read-only", False)

    filesystem_order = {"read-only": 0, "workspace-write": 1, "danger-full-access": 2}
    shell_order = {"never": 0, "on-failure": 1, "untrusted": 2, "on-request": 3}
    network_order = {"deny": 0, "on-request": 1, "allow": 2}

    contract = {
        "assigned_agent": {"role": "WORKER", "agent_id": "w-1"},
        "tool_permissions": {
            "filesystem": "danger-full-access",
            "shell": "on-request",
            "network": "allow",
            "mcp_tools": ["allowed", "blocked"],
        },
    }
    registry = {
        "agents": [
            {
                "role": "WORKER",
                "agent_id": "w-1",
                "defaults": {
                    "sandbox": "workspace-write",
                    "approval_policy": "untrusted",
                    "network": "deny",
                },
                "capabilities": {"mcp_tools": ["allowed", "tool-x"]},
            }
        ]
    }

    updated, violations = policy_pipeline.apply_role_defaults(
        contract,
        registry,
        filesystem_order,
        shell_order,
        network_order,
    )
    assert updated["filesystem"] == "workspace-write"
    assert updated["shell"] == "untrusted"
    assert updated["network"] == "deny"
    assert updated["mcp_tools"] == ["allowed"]
    assert set(violations) == {
        "tool_permissions.filesystem",
        "tool_permissions.shell",
        "tool_permissions.network",
        "tool_permissions.mcp_tools",
    }

    # No explicit tools -> use allowed set from registry capabilities.
    contract_without_tools = {
        "assigned_agent": {"role": "WORKER", "agent_id": "w-1"},
        "tool_permissions": {},
    }
    updated_no_tools, violations_no_tools = policy_pipeline.apply_role_defaults(
        contract_without_tools,
        registry,
        filesystem_order,
        shell_order,
        network_order,
    )
    assert set(updated_no_tools["mcp_tools"]) == {"allowed", "tool-x"}
    assert violations_no_tools == []

    # Missing registry entry returns original permissions copy.
    passthrough, passthrough_violations = policy_pipeline.apply_role_defaults(
        {"assigned_agent": {"role": "MISSING", "agent_id": "x"}, "tool_permissions": {"shell": "never"}},
        registry,
        filesystem_order,
        shell_order,
        network_order,
    )
    assert passthrough == {"shell": "never"}
    assert passthrough_violations == []
