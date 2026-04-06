import hashlib
import json
from pathlib import Path

import pytest

from cortexpilot_orch.contract import validator as validator_mod


def test_registry_path_and_load_fail_closed_edges(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    monkeypatch.delenv("CORTEXPILOT_AGENT_REGISTRY", raising=False)
    monkeypatch.setattr(validator_mod, "_REPO_ROOT", repo)

    assert validator_mod.resolve_agent_registry_path(repo) == (repo / "policies" / "agent_registry.json")

    missing_registry = repo / "missing.json"
    monkeypatch.setattr(validator_mod, "_agent_registry_path", lambda: missing_registry)
    with pytest.raises(ValueError, match="agent_registry missing"):
        validator_mod._load_agent_registry()

    bad_registry = repo / "bad.json"
    bad_registry.write_text("{", encoding="utf-8")
    monkeypatch.setattr(validator_mod, "_agent_registry_path", lambda: bad_registry)
    with pytest.raises(ValueError, match="agent_registry invalid"):
        validator_mod._load_agent_registry()

    monkeypatch.setattr(validator_mod, "_REPO_ROOT", repo)
    assert validator_mod._schema_root() == (repo / "schemas")


def test_schema_registry_and_agent_validation_edges(tmp_path: Path) -> None:
    schema_root = tmp_path / "schemas"
    schema_root.mkdir(parents=True, exist_ok=True)
    (schema_root / "agent_task_result.v1.json").write_text("{}", encoding="utf-8")
    registry_path = schema_root / "schema_registry.json"

    missing = validator_mod.check_schema_registry(schema_root)
    assert missing["status"] == "missing"

    registry_path.write_text("{", encoding="utf-8")
    invalid = validator_mod.check_schema_registry(schema_root)
    assert invalid["status"] == "invalid"

    registry_path.write_text(json.dumps({"version": "v1", "schemas": {}}), encoding="utf-8")
    missing_declared = validator_mod.check_schema_registry(schema_root)
    assert "agent_task_result.v1.json" in missing_declared["missing"]

    registry_path.write_text(
        json.dumps(
            {
                "version": "v1",
                "schemas": {
                    "agent_task_result.v1.json": {"sha256": "deadbeef"},
                    "ghost.schema.json": {"sha256": "abc"},
                },
            }
        ),
        encoding="utf-8",
    )
    mismatched = validator_mod.check_schema_registry(schema_root)
    assert "agent_task_result.v1.json" in mismatched["mismatched"]
    assert "ghost.schema.json" in mismatched["extra"]

    with pytest.raises(ValueError, match="owner invalid"):
        validator_mod._ensure_agent_in_registry({}, "bad-agent", "owner")
    with pytest.raises(ValueError, match="owner.agent_id missing"):
        validator_mod._ensure_agent_in_registry({}, {"role": "WORKER"}, "owner")
    with pytest.raises(ValueError, match="owner.role missing"):
        validator_mod._ensure_agent_in_registry({}, {"agent_id": "agent-1"}, "owner")
    with pytest.raises(ValueError, match="owner not registered"):
        validator_mod._ensure_agent_in_registry(
            {"agents": ["noise", {"agent_id": "agent-1", "role": "WORKER"}]},
            {"agent_id": "agent-x", "role": "WORKER"},
            "owner",
        )


def test_path_and_helper_edges() -> None:
    invalid_paths = validator_mod.find_invalid_allowed_paths(
        [
            42,
            " ",
            "safe/../outside.txt",
            "src/*.py",
        ]
    )
    assert "42" in invalid_paths
    assert " " in invalid_paths
    assert "safe/../outside.txt" in invalid_paths
    assert "src/*.py" in invalid_paths

    assert validator_mod.is_wide_path(1) is False
    assert validator_mod.is_wide_path(" ") is True
    assert validator_mod.is_wide_path(".") is True
    assert validator_mod.is_wide_path("**") is True
    assert validator_mod.is_wide_path(".runtime-cache/run.log") is False
    assert validator_mod.find_wide_paths([1, "docs/", "README.md"]) == ["docs/"]

    assert validator_mod._is_truthy("strict") is True
    assert validator_mod._contains_plan_marker(1) is False
    assert validator_mod._contains_plan_marker(" ") is False
    assert validator_mod._normalize_command(1) == ""
    assert validator_mod._is_trivial_acceptance_command("") is True
    assert validator_mod._is_trivial_acceptance_command(":") is True


def test_superpowers_gate_markers_and_violations(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORTEXPILOT_SUPERPOWERS_GATE_ENFORCE", "true")
    assert validator_mod.is_superpowers_gate_required({"evidence_links": []}) is True
    monkeypatch.delenv("CORTEXPILOT_SUPERPOWERS_GATE_ENFORCE", raising=False)

    assert (
        validator_mod.is_superpowers_gate_required({"evidence_links": [1, "gate:superpowers"]})
        is True
    )

    fail_closed = validator_mod.evaluate_superpowers_gate(
        {
            "evidence_links": ["gate:superpowers"],
            "inputs": {"spec": "", "artifacts": []},
            "required_outputs": [],
            "handoff_chain": {},
            "acceptance_tests": [],
        }
    )
    assert fail_closed["required"] is True
    assert fail_closed["ok"] is False
    assert {item["code"] for item in fail_closed["violations"]} == {
        "missing_spec",
        "missing_plan_evidence",
        "invalid_handoff_chain",
        "missing_reviewer_stage",
        "missing_test_stage",
    }

    plan_from_required_outputs = validator_mod.evaluate_superpowers_gate(
        {
            "evidence_links": [],
            "inputs": {"spec": "do task", "artifacts": []},
            "required_outputs": [123, {"name": "plan milestone"}],
            "handoff_chain": {
                "enabled": True,
                "roles": ["TECH_LEAD", "WORKER", "REVIEWER", "TEST"],
                "max_handoffs": 1,
            },
            "acceptance_tests": [123, {"cmd": "echo ok", "must_pass": False}, {"cmd": "bash scripts/check_repo_hygiene.sh", "must_pass": True}],
        }
    )
    assert plan_from_required_outputs["stages"]["plan"]["ok"] is True
    assert plan_from_required_outputs["stages"]["test"]["non_trivial_acceptance_tests"] == 1

    plan_from_artifact = validator_mod.evaluate_superpowers_gate(
        {
            "evidence_links": [],
            "inputs": {"spec": "do task", "artifacts": [123, {"name": "plan evidence"}]},
            "required_outputs": [{"name": "artifact_only", "acceptance": "ok"}],
            "handoff_chain": {"enabled": False, "roles": [], "max_handoffs": 0},
            "acceptance_tests": [],
        }
    )
    assert plan_from_artifact["stages"]["plan"]["ok"] is True


def test_contract_enforce_schema_sha_and_superpowers_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema_root = tmp_path / "schemas"
    schema_root.mkdir(parents=True, exist_ok=True)
    schema_path = schema_root / "agent_task_result.v1.json"
    schema_path.write_text("{}", encoding="utf-8")

    validator = validator_mod.ContractValidator(schema_root=schema_root)

    payload = {
        "allowed_paths": ["README.md"],
        "mcp_tool_set": ["codex"],
        "inputs": {
            "spec": "ok",
            "artifacts": [
                {
                    "name": "output_schema.worker",
                    "uri": str(schema_path),
                    "sha256": "bad-sha",
                }
            ],
        },
        "owner_agent": {"agent_id": "agent-1", "role": "WORKER"},
        "assigned_agent": {"agent_id": "agent-1", "role": "WORKER"},
    }
    with pytest.raises(ValueError, match="sha256 mismatch"):
        validator._enforce_contract_rules(payload)

    monkeypatch.setattr(
        validator_mod,
        "_load_agent_registry",
        lambda: {"agents": [{"agent_id": "agent-1", "role": "WORKER"}]},
    )
    payload = {
        "allowed_paths": ["README.md"],
        "mcp_tool_set": ["codex"],
        "inputs": {"spec": ""},
        "owner_agent": {"agent_id": "agent-1", "role": "WORKER"},
        "assigned_agent": {"agent_id": "agent-1", "role": "WORKER"},
        "evidence_links": ["superpowers://required"],
        "handoff_chain": {},
        "required_outputs": [],
        "acceptance_tests": [],
    }
    with pytest.raises(ValueError, match="superpowers gate violation"):
        validator._enforce_contract_rules(payload)


def test_output_schema_path_legacy_relative_check_and_missing_schema_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema_root = tmp_path / "schemas"
    schema_root.mkdir(parents=True, exist_ok=True)
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(validator_mod.Path, "is_relative_to", lambda _self, _other: (_ for _ in ()).throw(AttributeError("legacy")))
    with pytest.raises(ValueError, match="must live under"):
        validator_mod._resolve_output_schema_path(
            {"uri": str(outside)},
            schema_root,
            repo_root,
            "agent_task_result.v1.json",
        )

    with pytest.raises(FileNotFoundError, match="Schema not found"):
        validator_mod.ContractValidator(schema_root=tmp_path / "missing").validate_report({}, "not-exist.schema.json")


def test_hash_contract_is_deterministic() -> None:
    payload = {"b": 2, "a": 1}
    expected = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    assert validator_mod.hash_contract(payload) == expected
