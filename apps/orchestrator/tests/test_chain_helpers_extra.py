from openvibecoding_orch.chain import helpers as chain_helpers
from openvibecoding_orch.chain import runner as chain_runner


def test_exclusive_paths_and_overlap() -> None:
    step = {"exclusive_paths": ["src/", ""]}
    payload = {"allowed_paths": ["fallback/"]}
    assert chain_helpers._exclusive_paths_for_step(step, payload) == ["src/"]

    step = {"exclusive_paths": []}
    assert chain_helpers._exclusive_paths_for_step(step, payload) == ["fallback/"]
    assert chain_helpers._exclusive_paths_for_step(step, {"allowed_paths": "single/path"}) == ["single/path"]
    assert chain_helpers._exclusive_paths_for_step(step, {"allowed_paths": ("tuple/path",)}) == ["tuple/path"]

    assert chain_helpers._exclusive_paths_for_step(step, "bad") == []

    assert chain_helpers._paths_overlap("src/app.py", "src/") is True
    assert chain_helpers._paths_overlap("docs/readme.md", "src/") is False
    assert chain_helpers._paths_overlap("", "src/") is True


def test_check_exclusive_paths_and_normalize_depends() -> None:
    steps = [
        {"name": "s1", "exclusive_paths": []},
        {"name": "s2", "exclusive_paths": ["src/"]},
        {"name": "s3", "exclusive_paths": ["src/"]},
    ]
    payloads = [{}, {}, {}]
    conflicts = chain_helpers._check_exclusive_paths(steps, payloads)
    assert any("exclusive_paths empty" in item for item in conflicts)
    assert any("s2 <-> s3" in item for item in conflicts)

    assert chain_helpers._normalize_depends("a") == ["a"]
    assert chain_helpers._normalize_depends(["a", " ", "b"]) == ["a", "b"]
    assert chain_helpers._normalize_depends(123) == []


def test_artifact_names_and_policy_truncation() -> None:
    assert chain_runner._artifact_names({"inputs": None}) == []
    assert chain_runner._artifact_names({"inputs": {"artifacts": ["x", {"name": "a"}]}}) == ["a"]

    contract = {
        "task_id": "task-0001",
        "inputs": {"spec": "abcdef", "artifacts": [{"name": "summary.txt"}, {"name": "raw.txt"}]},
    }
    policy = {"mode": "summary-only", "max_artifacts": 1, "max_spec_chars": 3}
    updated, violations, truncations = chain_runner._apply_context_policy(
        contract,
        policy,
        owner_role="PM",
        step_name="step",
    )
    assert "step: artifacts truncated to 1" in truncations
    assert "step: spec truncated to 3 chars" in truncations
    assert any("summary-only requires purified artifact" in v for v in violations)
