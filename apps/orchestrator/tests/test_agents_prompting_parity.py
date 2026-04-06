from pathlib import Path

from cortexpilot_orch.runners import agents_prompting
from cortexpilot_orch.runners import agents_runner as runner


def _contract_with_worker_schema() -> dict:
    schema_root = Path(__file__).resolve().parents[3] / "schemas"
    schema_path = schema_root / "agent_task_result.v1.json"
    return {
        "inputs": {
            "artifacts": [
                {
                    "name": "output_schema.worker",
                    "uri": f"schemas/{schema_path.name}",
                }
            ]
        },
        "tool_permissions": {
            "filesystem": "workspace-write",
            "shell": "on-request",
            "network": "deny",
        },
    }


def test_agents_prompt_aliases_match_module(monkeypatch, tmp_path: Path) -> None:
    contract = _contract_with_worker_schema()
    schema_root = Path(__file__).resolve().parents[3] / "schemas"

    wrapper_path = runner._resolve_output_schema_path(contract, "WORKER", tmp_path, schema_root)
    module_path = agents_prompting.resolve_output_schema_path(contract, "WORKER", schema_root)
    assert wrapper_path == module_path

    monkeypatch.setenv("CORTEXPILOT_CODEX_MODEL", "gpt-test")
    wrapper_payload = runner._build_codex_payload(contract, "do it", tmp_path)
    module_payload = agents_prompting.build_codex_payload(contract, "do it", tmp_path)
    assert wrapper_payload == module_payload

    instructions_wrapper = runner._agent_instructions(
        "task-1",
        "mcp__vcs",
        {"prompt": "x"},
        False,
        "agent_task_result.v1.json",
    )
    instructions_module = agents_prompting.agent_instructions(
        "task-1",
        "mcp__vcs",
        {"prompt": "x"},
        False,
        "agent_task_result.v1.json",
    )
    assert instructions_wrapper == instructions_module

    assert runner._user_prompt("fix bug", "agent_task_result.v1.json") == agents_prompting.user_prompt(
        "fix bug", "agent_task_result.v1.json"
    )


def test_output_schema_role_name_parity() -> None:
    assert runner._output_schema_name_for_role("REVIEWER") == agents_prompting.output_schema_name_for_role("REVIEWER")
    assert runner._output_schema_name_for_role("WORKER") == agents_prompting.output_schema_name_for_role("WORKER")
