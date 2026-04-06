from __future__ import annotations

import os

from cortexpilot_orch.planning import intake as intake_mod


def test_intake_preview_builds_execution_plan_report(monkeypatch) -> None:
    monkeypatch.setattr(
        intake_mod,
        "generate_plan",
        lambda payload, answers: {
            "plan_id": "plan-preview-1",
            "task_id": "task-preview-1",
            "spec": str(payload.get("objective") or ""),
            "allowed_paths": list(payload.get("allowed_paths") or []),
            "mcp_tool_set": ["codex", "search"],
            "owner_agent": {"role": "PM", "agent_id": "agent-1"},
            "assigned_agent": {"role": "SEARCHER", "agent_id": "agent-1"},
            "acceptance_tests": [{"name": "repo_hygiene", "cmd": "bash scripts/check_repo_hygiene.sh", "must_pass": True}],
            "tool_permissions": {"filesystem": "workspace-write", "shell": "deny", "network": "allow", "mcp_tools": ["codex", "search"]},
        },
    )
    monkeypatch.setattr(
        intake_mod,
        "generate_plan_bundle",
        lambda payload, answers: (
            {
                "bundle_id": "bundle-preview-1",
                "created_at": "2026-03-29T00:00:00Z",
                "objective": str(payload.get("objective") or ""),
                "owner_agent": {"role": "PM", "agent_id": "agent-1"},
                "plans": [
                    {
                        "plan_id": "plan-preview-1",
                        "task_id": "task-preview-1",
                        "plan_type": "AI",
                        "spec": str(payload.get("objective") or ""),
                        "allowed_paths": list(payload.get("allowed_paths") or []),
                        "mcp_tool_set": ["codex", "search"],
                        "owner_agent": {"role": "PM", "agent_id": "agent-1"},
                        "assigned_agent": {"role": "SEARCHER", "agent_id": "agent-1"},
                        "acceptance_tests": [{"name": "repo_hygiene", "cmd": "bash scripts/check_repo_hygiene.sh", "must_pass": True}],
                        "tool_permissions": {"filesystem": "workspace-write", "shell": "deny", "network": "allow", "mcp_tools": ["codex", "search"]},
                    }
                ],
            },
            "bundle note",
        ),
    )
    monkeypatch.setattr(
        intake_mod,
        "build_task_chain_from_bundle",
        lambda plan_bundle, owner_agent: {
            "chain_id": "chain-preview-12345678",
            "owner_agent": {"role": "PM", "agent_id": "agent-1"},
            "steps": [{"name": "plan", "kind": "plan", "payload": {}}],
        },
    )
    monkeypatch.setattr(
        intake_mod,
        "compile_plan",
        lambda plan: {
            "task_id": "task-preview-1",
            "allowed_paths": ["apps/dashboard"],
            "acceptance_tests": [{"name": "repo_hygiene", "cmd": "bash scripts/check_repo_hygiene.sh", "must_pass": True}],
            "tool_permissions": {"filesystem": "workspace-write", "shell": "deny", "network": "allow", "mcp_tools": ["codex", "search"]},
            "assigned_agent": {"role": "SEARCHER", "agent_id": "agent-1"},
        },
    )

    service = intake_mod.IntakeService()
    report = service.preview(
        {
            "objective": "Build a public digest about Seattle AI",
            "allowed_paths": ["apps/dashboard"],
            "task_template": "news_digest",
            "template_payload": {
                "topic": "Seattle AI",
                "sources": ["theverge.com", "techcrunch.com"],
                "time_range": "24h",
                "max_results": 5,
            },
        }
    )

    assert report["report_type"] == "execution_plan_report"
    assert report["task_template"] == "news_digest"
    assert report["assigned_role"] == "SEARCHER"
    assert report["requires_human_approval"] is False
    assert "news_digest_result.json" in report["predicted_reports"]
    assert "search_requests.json" in report["predicted_artifacts"]
    assert report["questions"]
    assert "bundle note" in report["notes"]


def test_intake_preview_marks_manual_approval_when_env_requires_it(monkeypatch) -> None:
    monkeypatch.setattr(
        intake_mod,
        "generate_plan",
        lambda payload, answers: {
            "plan_id": "plan-preview-2",
            "task_id": "task-preview-2",
            "spec": str(payload.get("objective") or ""),
            "allowed_paths": list(payload.get("allowed_paths") or []),
            "mcp_tool_set": ["codex"],
            "owner_agent": {"role": "PM", "agent_id": "agent-1"},
            "assigned_agent": {"role": "WORKER", "agent_id": "agent-1"},
            "acceptance_tests": [{"name": "repo_hygiene", "cmd": "bash scripts/check_repo_hygiene.sh", "must_pass": True}],
            "tool_permissions": {"filesystem": "workspace-write", "shell": "deny", "network": "deny", "mcp_tools": ["codex"]},
        },
    )
    monkeypatch.setattr(
        intake_mod,
        "generate_plan_bundle",
        lambda payload, answers: (
            {
                "bundle_id": "bundle-preview-2",
                "created_at": "2026-03-29T00:00:00Z",
                "objective": str(payload.get("objective") or ""),
                "owner_agent": {"role": "PM", "agent_id": "agent-1"},
                "plans": [
                    {
                        "plan_id": "plan-preview-2",
                        "task_id": "task-preview-2",
                        "plan_type": "AI",
                        "spec": str(payload.get("objective") or ""),
                        "allowed_paths": list(payload.get("allowed_paths") or []),
                        "mcp_tool_set": ["codex"],
                        "owner_agent": {"role": "PM", "agent_id": "agent-1"},
                        "assigned_agent": {"role": "WORKER", "agent_id": "agent-1"},
                        "acceptance_tests": [{"name": "repo_hygiene", "cmd": "bash scripts/check_repo_hygiene.sh", "must_pass": True}],
                        "tool_permissions": {"filesystem": "workspace-write", "shell": "deny", "network": "deny", "mcp_tools": ["codex"]},
                    }
                ],
            },
            "",
        ),
    )
    monkeypatch.setattr(
        intake_mod,
        "build_task_chain_from_bundle",
        lambda plan_bundle, owner_agent: {
            "chain_id": "chain-preview-87654321",
            "owner_agent": {"role": "PM", "agent_id": "agent-1"},
            "steps": [{"name": "plan", "kind": "plan", "payload": {}}],
        },
    )
    monkeypatch.setattr(
        intake_mod,
        "compile_plan",
        lambda plan: {
                "task_id": "task-preview-2",
                "allowed_paths": ["apps/orchestrator/src"],
                "acceptance_tests": [{"name": "repo_hygiene", "cmd": "bash scripts/check_repo_hygiene.sh", "must_pass": True}],
                "tool_permissions": {"filesystem": "workspace-write", "shell": "deny", "network": "deny", "mcp_tools": ["codex"]},
                "assigned_agent": {"role": "WORKER", "agent_id": "agent-1"},
            },
    )

    monkeypatch.setenv("CORTEXPILOT_GOD_MODE_REQUIRED", "1")
    try:
        service = intake_mod.IntakeService()
        report = service.preview(
            {
                "objective": "General preview contract",
                "allowed_paths": ["apps/orchestrator/src"],
            }
        )
    finally:
        os.environ.pop("CORTEXPILOT_GOD_MODE_REQUIRED", None)

    assert report["requires_human_approval"] is True
    assert report["warnings"]
