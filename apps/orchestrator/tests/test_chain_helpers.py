from pathlib import Path
import json

from openvibecoding_orch.chain.helpers import (
    _check_exclusive_paths,
    _exclusive_paths_for_step,
    _normalize_depends,
    _paths_overlap,
    _prefix_before_glob,
    _step_task_id,
)
from openvibecoding_orch.chain.runner import (
    _apply_context_policy,
    _artifact_names,
    _is_purified_name,
    _is_raw_name,
    _load_json,
    _load_manifest,
)


def test_prefix_and_overlap_helpers() -> None:
    assert _prefix_before_glob("src/*.py") == "src/"
    assert _paths_overlap("src/*.py", "src/app.py") is True
    assert _paths_overlap("docs/", "src/") is False


def test_exclusive_paths_conflict_and_normalize_depends() -> None:
    steps = [
        {"name": "a", "exclusive_paths": ["src/"]},
        {"name": "b", "exclusive_paths": ["src/"]},
    ]
    payloads = [{"allowed_paths": ["src/"]}, {"allowed_paths": ["src/"]}]
    conflicts = _check_exclusive_paths(steps, payloads)
    assert conflicts

    assert _normalize_depends("a") == ["a"]
    assert _normalize_depends(["a", " ", "b"]) == ["a", "b"]
    assert _normalize_depends(123) == []


def test_chain_io_helpers(tmp_path: Path) -> None:
    data = {"task_id": "task_plan"}
    path = tmp_path / "payload.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert _load_json(path)["task_id"] == "task_plan"

    assert _load_manifest(tmp_path, "missing") == {}

    assert _step_task_id("plan", {"plan_id": "plan_123"}) == "plan_123"
    assert _step_task_id("contract", {"task_id": "task_123"}) == "task_123"

    step = {"name": "step", "exclusive_paths": []}
    payload = {"allowed_paths": ["src/"]}
    assert _exclusive_paths_for_step(step, payload) == ["src/"]


def test_artifact_name_helpers() -> None:
    contract = {"inputs": {"artifacts": [{"name": "summary.txt"}, {"name": "raw_results.json"}]}}
    names = _artifact_names(contract)
    assert "summary.txt" in names
    assert _is_purified_name("summary.txt") is True
    assert _is_raw_name("raw_results.json") is True


def test_apply_context_policy_modes_and_truncation() -> None:
    contract = {"inputs": {"spec": "abcdef", "artifacts": [{"name": "summary.txt"}, {"name": "raw_results.json"}]}}

    updated, violations, truncations = _apply_context_policy(
        contract,
        {"mode": "isolated", "max_spec_chars": 3},
        owner_role="WORKER",
        step_name="step-1",
    )
    assert any("context isolated" in item for item in violations)
    assert "spec truncated" in truncations[0]

    contract = {"inputs": {"spec": "spec", "artifacts": [{"name": "raw_results.json"}]}}
    updated, violations, truncations = _apply_context_policy(
        contract,
        {"mode": "summary-only", "allow_artifact_names": ["summary.txt"], "deny_artifact_substrings": ["raw"]},
        owner_role="WORKER",
        step_name="step-2",
    )
    assert any("summary-only" in item for item in violations)
    assert any("artifact denied" in item for item in violations)

    contract = {"inputs": {"spec": "spec", "artifacts": [{"name": "summary.txt"}, {"name": "summary2.txt"}]}}
    updated, violations, truncations = _apply_context_policy(
        contract,
        {"mode": "inherit", "max_artifacts": 1, "require_summary": True},
        owner_role="PM",
        step_name="step-3",
    )
    assert not violations
    assert updated["inputs"]["artifacts"] == [{"name": "summary.txt"}]
