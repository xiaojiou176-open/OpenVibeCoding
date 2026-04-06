import pytest

from cortexpilot_orch.contract.compiler import compile_plan, compile_plan_text
from cortexpilot_orch.contract.validator import ContractValidator


def test_compile_plan_defaults():
    plan = {
        "plan_id": "plan_001",
        "spec": "update orchestrator docs",
        "allowed_paths": ["docs/"],
        "mcp_tool_set": ["01-filesystem"],
    }
    contract = compile_plan(plan)
    validator = ContractValidator()
    validator.validate_contract(contract)

    assert contract["task_id"] == "plan_001"
    assert contract["inputs"]["spec"] == "update orchestrator docs"
    assert contract["allowed_paths"] == ["docs/"]
    assert contract["required_outputs"][0]["type"] == "patch"


def test_compile_plan_text_errors():
    with pytest.raises(ValueError):
        compile_plan_text("{")
    with pytest.raises(ValueError):
        compile_plan_text("[]")

    with pytest.raises(ValueError):
        compile_plan({"spec": "missing id", "allowed_paths": ["docs/"], "mcp_tool_set": ["01-filesystem"]})
