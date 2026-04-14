import json
from pathlib import Path

import pytest

from openvibecoding_orch.runners import agents_prompting


def test_resolve_roles_root_and_role_prompt_paths(tmp_path: Path, monkeypatch) -> None:
    worktree = tmp_path / "worktree"
    local_roles = worktree / "codex" / "roles"
    local_roles.mkdir(parents=True, exist_ok=True)
    (local_roles / "50_worker_core.md").write_text("worker local", encoding="utf-8")

    assert agents_prompting.resolve_roles_root(worktree) == local_roles

    monkeypatch.setenv("OPENVIBECODING_SKIP_ROLE_PROMPT", "true")
    assert agents_prompting.load_role_prompt("WORKER", worktree) == ""
    assert agents_prompting.resolve_role_prompt_path("WORKER", worktree) is None

    monkeypatch.setenv("OPENVIBECODING_SKIP_ROLE_PROMPT", "false")
    assert agents_prompting.load_role_prompt("WORKER", worktree) == "worker local"
    assert agents_prompting.resolve_role_prompt_path("WORKER", worktree) == local_roles / "50_worker_core.md"

    assert agents_prompting.load_role_prompt("UNKNOWN_ROLE", worktree) == "worker local"
    assert agents_prompting.resolve_role_prompt_path("UNKNOWN_ROLE", worktree) == local_roles / "50_worker_core.md"

    (local_roles / "50_worker_core.md").unlink()
    assert agents_prompting.load_role_prompt("WORKER", worktree) == ""
    assert agents_prompting.resolve_role_prompt_path("WORKER", worktree) is None


def test_resolve_output_schema_artifact_and_paths(tmp_path: Path) -> None:
    schema_root = tmp_path / "schemas"
    schema_root.mkdir(parents=True, exist_ok=True)
    worker_schema = schema_root / "agent_task_result.v1.json"
    worker_schema.write_text("{}", encoding="utf-8")
    reviewer_schema = schema_root / "review_report.v1.json"
    reviewer_schema.write_text("{}", encoding="utf-8")

    assert agents_prompting.resolve_output_schema_artifact({}, "WORKER") is None
    assert agents_prompting.resolve_output_schema_artifact({"inputs": {}}, "WORKER") is None
    assert agents_prompting.resolve_output_schema_artifact({"inputs": {"artifacts": "bad"}}, "WORKER") is None

    contract = {
        "inputs": {
            "artifacts": [
                "bad",
                {"name": "output_schema.worker", "uri": "schemas/agent_task_result.v1.json"},
            ]
        }
    }
    artifact = agents_prompting.resolve_output_schema_artifact(contract, "WORKER")
    assert isinstance(artifact, dict)

    with pytest.raises(RuntimeError, match="output_schema artifact missing"):
        agents_prompting.resolve_output_schema_path({}, "WORKER", schema_root)

    with pytest.raises(RuntimeError, match="artifact uri missing"):
        agents_prompting.resolve_output_schema_path(
            {"inputs": {"artifacts": [{"name": "output_schema.worker"}]}},
            "WORKER",
            schema_root,
        )

    with pytest.raises(RuntimeError, match="artifact not found"):
        agents_prompting.resolve_output_schema_path(
            {"inputs": {"artifacts": [{"name": "output_schema.worker", "uri": "schemas/missing.json"}]}},
            "WORKER",
            schema_root,
        )

    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="must live under"):
        agents_prompting.resolve_output_schema_path(
            {"inputs": {"artifacts": [{"name": "output_schema.worker", "uri": str(outside)}]}},
            "WORKER",
            schema_root,
        )

    with pytest.raises(RuntimeError, match="output_schema mismatch"):
        agents_prompting.resolve_output_schema_path(
            {"inputs": {"artifacts": [{"name": "output_schema.worker", "uri": "schemas/review_report.v1.json"}]}},
            "WORKER",
            schema_root,
        )

    resolved_rel = agents_prompting.resolve_output_schema_path(contract, "WORKER", schema_root)
    assert resolved_rel == worker_schema

    resolved_abs = agents_prompting.resolve_output_schema_path(
        {"inputs": {"artifacts": [{"name": "output_schema.reviewer", "uri": str(reviewer_schema)}]}},
        "REVIEWER",
        schema_root,
    )
    assert resolved_abs == reviewer_schema


def test_schema_loading_and_fixed_json_helpers(tmp_path: Path) -> None:
    schema_path = tmp_path / "schema.json"
    assert agents_prompting.load_output_schema(schema_path) == ""

    schema_path.write_text("not-json", encoding="utf-8")
    assert agents_prompting.load_output_schema(schema_path) == ""

    schema_path.write_text(json.dumps({"type": "object"}), encoding="utf-8")
    loaded = agents_prompting.load_output_schema(schema_path)
    assert '"type": "object"' in loaded

    assert agents_prompting.is_fixed_json_template("RETURN EXACTLY THIS JSON\n{}") is True
    assert agents_prompting.is_fixed_json_template("output json only") is True
    assert agents_prompting.is_fixed_json_template("normal prompt") is False

    assert agents_prompting.extract_fixed_json_payload(123) is None
    assert agents_prompting.extract_fixed_json_payload("no brace") is None
    assert agents_prompting.extract_fixed_json_payload("{bad") is None
    assert agents_prompting.extract_fixed_json_payload("[1,2,3]") is None
    payload = agents_prompting.extract_fixed_json_payload("prefix {\"k\": 1} suffix")
    assert payload == {"k": 1}


def test_instruction_decoration_payload_and_prompts(tmp_path: Path, monkeypatch) -> None:
    worktree = tmp_path / "worktree"
    roles = worktree / "codex" / "roles"
    roles.mkdir(parents=True, exist_ok=True)
    (roles / "50_worker_core.md").write_text("ROLE PROMPT", encoding="utf-8")

    schema = tmp_path / "schema.json"
    schema.write_text(json.dumps({"type": "object"}), encoding="utf-8")

    fixed = "RETURN EXACTLY THIS JSON\n{\"ok\": true}\nOUTPUT JSON ONLY"
    assert agents_prompting.decorate_instruction("WORKER", fixed, worktree, schema, "schema.json") == fixed

    monkeypatch.setenv("OPENVIBECODING_SKIP_ROLE_PROMPT", "true")
    decorated_no_role = agents_prompting.decorate_instruction("WORKER", "do work", worktree, schema, "schema.json")
    assert "Output JSON only" in decorated_no_role
    assert "ROLE PROMPT" not in decorated_no_role

    monkeypatch.setenv("OPENVIBECODING_SKIP_ROLE_PROMPT", "false")
    decorated_with_role = agents_prompting.decorate_instruction("WORKER", "do work", worktree, schema, "schema.json")
    assert "ROLE PROMPT" in decorated_with_role

    monkeypatch.setenv("OPENVIBECODING_INLINE_OUTPUT_SCHEMA", "false")
    decorated_without_inline_schema = agents_prompting.decorate_instruction(
        "WORKER",
        "do work",
        worktree,
        schema,
        "schema.json",
    )
    assert "\"type\": \"object\"" not in decorated_without_inline_schema
    monkeypatch.setenv("OPENVIBECODING_INLINE_OUTPUT_SCHEMA", "true")

    contract = {
        "tool_permissions": {
            "filesystem": "workspace-write",
            "shell": "deny",
            "network": "deny",
        }
    }
    monkeypatch.setenv("OPENVIBECODING_CODEX_MODEL", "gpt-5.2-codex")
    payload = agents_prompting.build_codex_payload(contract, "run", worktree)
    assert payload["sandbox"] == "workspace-write"
    assert payload["approval-policy"] == "never"
    assert payload["model"] == "gpt-5.2-codex"

    contract2 = {"tool_permissions": {"filesystem": "read-only", "shell": "on-request"}}
    payload2 = agents_prompting.build_codex_payload(contract2, "run", worktree)
    assert payload2["sandbox"] == "read-only"
    assert payload2["approval-policy"] == "on-request"

    monkeypatch.setenv("OPENVIBECODING_CODEX_TIMEBOX_SEC", "120")
    force_text = agents_prompting.agent_instructions("task-1", "mcp__tool", {"k": "v"}, True, "schema.json")
    assert "EXACTLY as-is" in force_text
    assert "120 seconds" in force_text

    non_force_text = agents_prompting.agent_instructions("task-1", "mcp__tool", {"k": "v"}, False, "schema.json")
    assert "conforms to schema.json" in non_force_text

    user_text = agents_prompting.user_prompt("fix bug", "schema.json")
    assert "Task: fix bug" in user_text
    assert "schema.json" in user_text
