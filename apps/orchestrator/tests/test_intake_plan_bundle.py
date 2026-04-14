import json

from openvibecoding_orch.planning import intake


def test_generate_plan_bundle_prefers_agent_output(monkeypatch) -> None:
    payload = {
        "objective": "audit docs vs repo",
        "allowed_paths": ["docs/", "apps/"],
        "owner_agent": {"role": "PM", "agent_id": "agent-1"},
        "mcp_tool_set": ["01-filesystem"],
    }
    answers: list[str] = []

    def _fake_agent(_: str, __: str) -> dict:
        return {
            "bundle_id": "bundle-123456",
            "created_at": "2025-01-01T00:00:00Z",
            "objective": "audit docs vs repo",
            "owner_agent": {"role": "TECH_LEAD", "agent_id": "agent-1"},
            "plans": [
                {
                    "plan_id": "plan-docs",
                    "plan_type": "BACKEND",
                    "task_type": "IMPLEMENT",
                    "spec": "check docs",
                    "allowed_paths": ["docs/"],
                    "assigned_agent": {"role": "WORKER", "agent_id": "agent-1"},
                    "acceptance_tests": [{"name": "echo", "cmd": "echo ok", "must_pass": True}],
                    "tool_permissions": {
                        "filesystem": "workspace-write",
                        "shell": "never",
                        "network": "deny",
                        "mcp_tools": ["codex"],
                    },
                    "mcp_tool_set": ["01-filesystem"],
                },
                {
                    "plan_id": "plan-apps",
                    "plan_type": "FRONTEND",
                    "task_type": "IMPLEMENT",
                    "spec": "check apps",
                    "allowed_paths": ["apps/"],
                    "mcp_tool_set": ["01-filesystem"],
                },
            ],
        }

    monkeypatch.setattr(intake, "_agents_available", lambda: True)
    monkeypatch.setattr(intake, "_run_agent", _fake_agent)

    bundle, note = intake.generate_plan_bundle(payload, answers)

    assert note == ""
    assert bundle["bundle_id"] == "bundle-123456"
    assert len(bundle["plans"]) == 2
    for plan in bundle["plans"]:
        assert plan["assigned_agent"]["role"] == "WORKER"
        assert plan["tool_permissions"]["filesystem"] == "workspace-write"
        assert plan["tool_permissions"]["shell"] == "never"
        assert plan["tool_permissions"]["network"] == "deny"
        assert plan["tool_permissions"]["mcp_tools"] == ["codex"]


def test_generate_plan_bundle_fallback_on_invalid_output(monkeypatch) -> None:
    payload = {
        "objective": "audit docs vs repo",
        "allowed_paths": ["docs/"],
        "owner_agent": {"role": "PM", "agent_id": "agent-1"},
        "mcp_tool_set": ["01-filesystem"],
    }
    answers: list[str] = []

    monkeypatch.setattr(intake, "_agents_available", lambda: True)
    monkeypatch.setattr(intake, "_run_agent", lambda _prompt, _instructions: {"bundle_id": "bad", "plans": []})
    monkeypatch.setattr(intake, "generate_plan", lambda _payload, _answers: intake._build_plan_fallback(_payload, _answers))

    bundle, note = intake.generate_plan_bundle(payload, answers)

    assert note.startswith("plan_bundle_fallback:")
    assert isinstance(bundle.get("plans"), list)
    assert len(bundle["plans"]) == 1
    assert bundle["plans"][0]["allowed_paths"] == ["docs/"]
    assert bundle["plans"][0]["owner_agent"]["role"] == "PM"
    assert bundle["plans"][0]["assigned_agent"]["role"] == "WORKER"


def test_build_task_chain_from_bundle() -> None:
    bundle = {
        "bundle_id": "bundle-abcdef",
        "owner_agent": {"role": "TECH_LEAD", "agent_id": "agent-1"},
        "plans": [
            {
                "plan_id": "plan-docs",
                "plan_type": "BACKEND",
                "task_type": "IMPLEMENT",
                "spec": "check docs",
                "allowed_paths": ["docs/"],
                "acceptance_tests": [{"name": "echo", "cmd": "echo ok", "must_pass": True}],
                "tool_permissions": {
                    "filesystem": "workspace-write",
                    "shell": "never",
                    "network": "deny",
                    "mcp_tools": ["codex"],
                },
                "mcp_tool_set": ["01-filesystem"],
                "assigned_agent": {"role": "WORKER", "agent_id": "agent-1"},
            }
        ],
    }
    chain = intake.build_task_chain_from_bundle(bundle, {"role": "PM", "agent_id": "agent-1"})

    assert chain["chain_id"].startswith("chain-")
    assert len(chain["steps"]) == 2
    fan_in = chain["steps"][-1]
    assert fan_in["name"] == "fan_in"
    assert fan_in["depends_on"] == [chain["steps"][0]["name"]]
    assert fan_in["exclusive_paths"] == intake._FANIN_ALLOWED_PATHS
    json.dumps(chain)  # ensure json serializable
