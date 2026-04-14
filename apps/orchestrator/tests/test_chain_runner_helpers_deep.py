from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from openvibecoding_orch.chain import parsers as chain_parsers
from openvibecoding_orch.chain import helpers as chain_helpers
from openvibecoding_orch.chain import runner as chain_runner
from openvibecoding_orch.chain.runner import ChainRunner
from openvibecoding_orch.store.run_store import RunStore


def _execute_stub(_contract_path: Path, _mock_mode: bool) -> str:
    return "run-stub"


def test_chain_low_level_helpers_branch_matrix(tmp_path: Path, monkeypatch) -> None:
    schema_root = tmp_path / "schemas"
    schema_root.mkdir(parents=True, exist_ok=True)
    (schema_root / "plan.schema.json").write_text(
        json.dumps({"properties": {"a": {}, "b": {}}}),
        encoding="utf-8",
    )

    chain_runner._SCHEMA_KEYS_CACHE.clear()
    first = chain_runner._schema_allowed_keys(schema_root, "plan.schema.json")
    assert first == {"a", "b"}
    (schema_root / "plan.schema.json").write_text(json.dumps({"properties": {"x": {}}}), encoding="utf-8")
    second = chain_runner._schema_allowed_keys(schema_root, "plan.schema.json")
    assert second == {"a", "b"}

    merged = chain_runner._deep_merge_payload({"a": {"x": 1}, "b": 2}, {"a": {"y": 3}, "b": 4, "c": 5})
    assert merged == {"a": {"x": 1, "y": 3}, "b": 4, "c": 5}
    assert chain_runner._deep_merge_payload({"a": 1}, {}) == {"a": 1}

    assert chain_runner._filter_payload_keys({"a": 1, "b": 2}, set()) == {"a": 1, "b": 2}
    assert chain_runner._filter_payload_keys({"a": 1, "b": 2}, {"b"}) == {"b": 2}

    assert chain_parsers._extract_handoff_payload(None) == {}
    assert chain_parsers._extract_handoff_payload({"handoff_payload": {"k": 1}}) == {"k": 1}
    assert chain_parsers._extract_handoff_payload({"next_payload": {"k": 2}}) == {"k": 2}
    assert chain_parsers._extract_handoff_payload({"evidence_refs": {"handoff_payload": {"k": 3}}}) == {"k": 3}
    assert chain_parsers._extract_handoff_payload({"evidence_refs": {"payload": {"k": 3}}}) == {}

    assert chain_parsers._extract_contracts(None) == []
    assert chain_parsers._extract_contracts({"contracts": [{"a": 1}, "x"]}) == [{"a": 1}]
    assert chain_parsers._extract_contracts({"evidence_refs": {"contracts": [{"b": 2}]}}) == [{"b": 2}]

    assert chain_runner._output_schema_name_for_role("REVIEWER") == "review_report.v1.json"
    assert chain_runner._output_schema_name_for_role("TEST") == "test_report.v1.json"

    contract = {"assigned_agent": {"role": "WORKER"}}
    updated = chain_runner._ensure_output_schema_artifact(contract)
    artifacts = updated["inputs"]["artifacts"]
    assert isinstance(artifacts, list)
    assert any(str(item.get("name", "")).startswith("output_schema") for item in artifacts)

    monkeypatch.setattr(chain_runner, "_output_schema_name_for_role", lambda _role: "missing.schema.json")
    contract_missing = {"assigned_agent": {"role": "WORKER"}, "inputs": {"artifacts": []}}
    unchanged = chain_runner._ensure_output_schema_artifact(contract_missing)
    assert unchanged["inputs"]["artifacts"] == []

    store = RunStore(runs_root=tmp_path / "runs")
    run_id = store.create_run("dep")
    task_result_path = store._run_dir(run_id) / "reports" / "task_result.json"
    task_result_path.parent.mkdir(parents=True, exist_ok=True)
    task_result_path.write_text("{}", encoding="utf-8")

    assert chain_runner._dependency_artifact(store, "dep", "") is None
    assert chain_runner._dependency_artifact(store, "dep", run_id) is not None
    assert chain_runner._dependency_patch_artifact(store, "dep", "") is None

    assert chain_runner._should_propagate_dependency_patch({"kind": "plan"}) is False
    assert chain_runner._should_propagate_dependency_patch(
        {"kind": "contract", "payload": {"assigned_agent": {"role": "REVIEWER"}}}
    ) is False
    assert chain_runner._should_propagate_dependency_patch(
        {"kind": "contract", "payload": {"task_type": "TEST"}}
    ) is False

    assert chain_runner._load_task_result(store, "") is None
    bad_run = store.create_run("bad")
    bad_path = store._run_dir(bad_run) / "artifacts" / "agent_task_result.json"
    bad_path.parent.mkdir(parents=True, exist_ok=True)
    bad_path.write_text("{", encoding="utf-8")
    assert chain_runner._load_task_result(store, bad_run) is None

    payload = {"evidence_refs": {"contracts": [{"task_id": "a"}]}}
    assert chain_runner._resolve_contract_from_dependency(payload, None) == {"task_id": "a"}
    assert chain_runner._resolve_contract_from_dependency(payload, "x") == {"task_id": "a"}
    assert chain_runner._resolve_contract_from_dependency(payload, 3) is None
    assert chain_runner._resolve_contract_from_dependency({"evidence_refs": {}}, 0) is None

    assert chain_runner._merge_contract_overrides({"a": 1}, None) == {"a": 1}
    assert chain_runner._merge_contract_overrides({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}
    assert chain_helpers._paths_overlap("*", "apps/dashboard/file.ts") is True


def test_chain_fanin_and_policy_helpers(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path / "runs")

    as_list = chain_runner._normalize_fanin_summary(json.dumps(["issue-a"]), ["r1"])
    parsed_list = json.loads(as_list)
    assert parsed_list["stats"]["total"] == 1
    assert parsed_list["inconsistencies"][0]["severity"] == "medium"

    as_obj = chain_runner._normalize_fanin_summary(
        json.dumps({"inconsistencies": [{"title": "x", "severity": "unexpected"}]}),
        ["r2"],
    )
    parsed_obj = json.loads(as_obj)
    assert parsed_obj["stats"]["medium"] == 1

    as_text = chain_runner._normalize_fanin_summary("not-json", ["r3"])
    parsed_text = json.loads(as_text)
    assert parsed_text["notes"] == "not-json"

    run_id = store.create_run("fanin")
    run_dir = store._run_dir(run_id)
    report_path = run_dir / "reports" / "task_result.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    chain_runner._normalize_fanin_task_result(store, run_id, "step", "", ["dep-1"])
    chain_runner._normalize_fanin_task_result(store, run_id, "step", "missing-run", ["dep-1"])

    bad_step_run = store.create_run("fanin-bad")
    bad_report = store._run_dir(bad_step_run) / "reports" / "task_result.json"
    bad_report.parent.mkdir(parents=True, exist_ok=True)
    bad_report.write_text("{", encoding="utf-8")
    chain_runner._normalize_fanin_task_result(store, run_id, "step", bad_step_run, ["dep-2"])

    list_step_run = store.create_run("fanin-list")
    list_report = store._run_dir(list_step_run) / "reports" / "task_result.json"
    list_report.parent.mkdir(parents=True, exist_ok=True)
    list_report.write_text("[]", encoding="utf-8")
    chain_runner._normalize_fanin_task_result(store, run_id, "step", list_step_run, ["dep-3"])

    good_step_run = store.create_run("fanin-good")
    good_report = store._run_dir(good_step_run) / "reports" / "task_result.json"
    good_report.parent.mkdir(parents=True, exist_ok=True)
    good_report.write_text(json.dumps({"task_id": "fanin", "summary": "[]"}), encoding="utf-8")
    chain_runner._normalize_fanin_task_result(store, run_id, "step", good_step_run, ["dep-4"])

    normalized = json.loads((store._run_dir(good_step_run) / "reports" / "task_result.json").read_text(encoding="utf-8"))
    assert "dependency_run_ids" in normalized["evidence_refs"]

    agent_only_run = store.create_run("fanin-agent-only")
    agent_only_report = store._run_dir(agent_only_run) / "artifacts" / "agent_task_result.json"
    agent_only_report.parent.mkdir(parents=True, exist_ok=True)
    agent_only_report.write_text(json.dumps({"task_id": "fanin", "summary": "[]"}), encoding="utf-8")
    chain_runner._normalize_fanin_task_result(store, run_id, "step", agent_only_run, ["dep-5"])

    normalized_agent_only = json.loads(
        (store._run_dir(agent_only_run) / "reports" / "task_result.json").read_text(encoding="utf-8")
    )
    normalized_agent_only_summary = json.loads(normalized_agent_only["summary"])
    assert normalized_agent_only_summary["dependency_run_ids"] == ["dep-5"]
    assert normalized_agent_only["evidence_refs"]["dependency_run_ids"] == ["dep-5"]

    contract = {"inputs": "invalid"}
    updated, violations, truncations = chain_runner._apply_context_policy(
        contract,
        {
            "mode": "summary-only",
            "allow_artifact_names": "allowed.summary",
            "deny_artifact_substrings": "raw",
            "require_summary": True,
            "max_artifacts": "bad",
            "max_spec_chars": "bad",
        },
        "PM",
        "step-a",
    )
    assert isinstance(updated["inputs"], dict)
    assert any("requires artifacts" in item for item in violations)
    assert truncations == []

    contract2 = {
        "inputs": {
            "spec": "X" * 20,
            "artifacts": [
                {"name": "raw_payload"},
                {"name": "clean.summary"},
                {"name": "extra.summary"},
            ],
        }
    }
    updated2, violations2, truncations2 = chain_runner._apply_context_policy(
        contract2,
        {
            "mode": "unknown-mode",
            "max_artifacts": 2,
            "max_spec_chars": 5,
            "allow_artifact_names": ["clean.summary", "extra.summary"],
            "deny_artifact_substrings": ["raw"],
            "require_summary": True,
        },
        "TECH_LEAD",
        "step-b",
    )
    assert len(updated2["inputs"]["artifacts"]) == 2
    assert updated2["inputs"]["spec"] == "XXXXX"
    assert any("unknown context_policy mode" in item for item in violations2)
    assert any("artifact denied by policy" in item for item in violations2)
    assert any("artifacts truncated" in item for item in truncations2)
    assert any("spec truncated" in item for item in truncations2)


def test_chain_lifecycle_helpers_and_subprocess_paths(tmp_path: Path, monkeypatch) -> None:
    store = RunStore(runs_root=tmp_path / "runs")

    assert chain_parsers._as_int("x", 3) == 3
    assert chain_parsers._as_int("0", 3) == 3
    assert chain_runner._normalize_required_path(None)
    assert chain_parsers._is_subsequence([], ["PM"])

    assert chain_runner._step_roles({"owner_agent": {"role": "PM"}, "assigned_agent": {"role": "PM"}}) == ["PM"]

    rid = store.create_run("lifecycle")
    run_dir = store._run_dir(rid)
    (run_dir / "reports").mkdir(parents=True, exist_ok=True)

    (run_dir / "reports" / "review_report.json").write_text(json.dumps({"verdict": "PASS"}), encoding="utf-8")
    assert chain_runner._reviewer_verdict(store, rid) == "PASS"

    (run_dir / "reports" / "review_report.json").write_text("{", encoding="utf-8")
    (run_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    (run_dir / "artifacts" / "agent_task_result.json").write_text(json.dumps({"status": "FAILURE"}), encoding="utf-8")
    assert chain_runner._reviewer_verdict(store, rid) == "FAIL"

    (run_dir / "reports" / "test_report.json").write_text(json.dumps({"status": "PASS"}), encoding="utf-8")
    assert chain_runner._test_stage_status(store, rid) == "PASS"

    step_reports = [
        {
            "index": 0,
            "status": "SUCCESS",
            "owner_agent": {"role": "PM"},
            "assigned_agent": {"role": "TECH_LEAD"},
            "run_id": "",
        },
        {
            "index": 1,
            "status": "SUCCESS",
            "owner_agent": {"role": "TECH_LEAD"},
            "assigned_agent": {"role": "WORKER"},
            "run_id": "",
        },
    ]
    summary, violations = chain_runner._build_lifecycle_summary(
        store,
        {"role": "PM"},
        step_reports,
        {
            "lifecycle": {
                "enforce": True,
                "required_path": ["PM", "TECH_LEAD", "WORKER", "REVIEWER", "TEST_RUNNER", "PM"],
                "min_workers": 2,
                "min_reviewers": 1,
                "reviewer_quorum": 1,
                "require_test_stage": True,
                "require_return_to_pm": True,
            }
        },
    )
    assert summary["is_complete"] is False
    assert any("insufficient worker" in item for item in violations)

    runner = ChainRunner(tmp_path, store, _execute_stub)

    monkeypatch.delenv("OPENVIBECODING_CHAIN_SUBPROCESS_TIMEOUT_SEC", raising=False)
    assert runner._resolve_chain_subprocess_timeout_sec() is None
    monkeypatch.setenv("OPENVIBECODING_CHAIN_SUBPROCESS_TIMEOUT_SEC", "abc")
    assert runner._resolve_chain_subprocess_timeout_sec() is None
    monkeypatch.setenv("OPENVIBECODING_CHAIN_SUBPROCESS_TIMEOUT_SEC", "0")
    assert runner._resolve_chain_subprocess_timeout_sec() is None
    monkeypatch.setenv("OPENVIBECODING_CHAIN_SUBPROCESS_TIMEOUT_SEC", "3.5")
    assert runner._resolve_chain_subprocess_timeout_sec() == 3.5

    def _timeout_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd=kwargs.get("args") or "cmd",
            timeout=1,
            output=b"s-bytes",
            stderr=b"e-bytes",
        )

    monkeypatch.setattr(subprocess, "run", _timeout_run)
    out_timeout = runner._execute_task_subprocess("chain-1", tmp_path / "contract.json", mock_mode=True)
    assert out_timeout == ""
    timeout_events = []
    for line in (store._run_dir("chain-1") / "events.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if event.get("event") == "CHAIN_SUBPROCESS_TIMEOUT":
            timeout_events.append(event)
    assert timeout_events
    timeout_meta = timeout_events[-1]["meta"]
    assert timeout_meta["stdout"] == "s-bytes"
    assert timeout_meta["stderr"] == "e-bytes"

    class _Result:
        def __init__(self, stdout: str, stderr: str, returncode: int) -> None:
            self.stdout = stdout
            self.stderr = stderr
            self.returncode = returncode

    captured_env: dict[str, str] = {}

    def _ok_run(*args, **kwargs):
        captured_env.update(kwargs["env"])
        return _Result(stdout="run_id=abc123\n", stderr="", returncode=0)

    monkeypatch.setattr(subprocess, "run", _ok_run)
    monkeypatch.setenv("PYTHONPATH", "existing")
    out_ok = runner._execute_task_subprocess("chain-2", tmp_path / "contract.json", mock_mode=False)
    assert out_ok == "abc123"
    assert "existing" in captured_env["PYTHONPATH"]

    monkeypatch.delenv("PYTHONPATH", raising=False)
    out_ok2 = runner._execute_task_subprocess("chain-3", tmp_path / "contract.json", mock_mode=False)
    assert out_ok2 == "abc123"

    timeout_run_id = store.create_run("timeout-summary")
    store.append_event(
        timeout_run_id,
        {
            "level": "ERROR",
            "event": "CHAIN_SUBPROCESS_TIMEOUT",
            "run_id": timeout_run_id,
            "meta": {
                "cmd": ["python", "-m", "openvibecoding_orch.cli", "run", "artifacts/chain_step_2_worker_cov_02.json"],
                "timeout_sec": 12,
                "stdout": "",
                "stderr": "timeout",
            },
        },
    )
    store.append_event(
        timeout_run_id,
        {
            "level": "ERROR",
            "event": "CHAIN_SUBPROCESS_TIMEOUT",
            "run_id": timeout_run_id,
            "meta": {
                "cmd": ["python", "-m", "openvibecoding_orch.cli", "run", "artifacts/chain_step_3_worker_cov_03.json"],
                "timeout_sec": 12,
                "stdout": "",
                "stderr": "timeout",
            },
        },
    )
    timeout_summary = chain_runner._collect_chain_timeout_summary(
        store,
        timeout_run_id,
        [
            {"name": "pm_to_tl"},
            {"name": "worker_cov_01"},
            {"name": "worker_cov_02"},
            {"name": "worker_cov_03"},
        ],
    )
    assert timeout_summary["count"] == 2
    assert timeout_summary["timeout_sec"] == 12.0
    assert timeout_summary["timed_out_steps"] == ["worker_cov_02", "worker_cov_03"]
    assert len(timeout_summary["timed_out_commands"]) == 2


def test_chain_handoff_chain_validation_full_matrix() -> None:
    ok, reason = chain_runner._validate_handoff_chain({"handoff_chain": {"enabled": True, "roles": []}})
    assert ok is False
    assert "requires roles" in reason

    ok, reason = chain_runner._validate_handoff_chain(
        {
            "handoff_chain": {"enabled": True, "roles": ["PM", "ALIEN"]},
            "owner_agent": {"role": "PM"},
            "assigned_agent": {"role": "ALIEN"},
        }
    )
    assert ok is False
    assert "role invalid" in reason

    ok, reason = chain_runner._validate_handoff_chain(
        {
            "handoff_chain": {"enabled": True, "roles": ["TECH_LEAD", "PM"]},
            "owner_agent": {"role": "TECH_LEAD"},
            "assigned_agent": {"role": "PM"},
        }
    )
    assert ok is False
    assert "out of order" in reason

    ok, reason = chain_runner._validate_handoff_chain(
        {
            "handoff_chain": {"enabled": True, "roles": ["TECH_LEAD", "WORKER"]},
            "owner_agent": {"role": "TECH_LEAD"},
            "assigned_agent": {"role": "WORKER"},
        }
    )
    assert ok is False
    assert "missing required roles before" in reason

    ok, reason = chain_runner._validate_handoff_chain(
        {
            "handoff_chain": {"enabled": True, "roles": ["PM", "TECH_LEAD", "WORKER"]},
            "owner_agent": {"role": "WORKER"},
            "assigned_agent": {"role": "WORKER"},
        }
    )
    assert ok is False
    assert "must start with owner role" in reason

    ok, reason = chain_runner._validate_handoff_chain(
        {
            "handoff_chain": {"enabled": True, "roles": ["PM", "TECH_LEAD", "WORKER"]},
            "owner_agent": {"role": "PM"},
            "assigned_agent": {"role": "REVIEWER"},
        }
    )
    assert ok is False
    assert "must end with assigned role" in reason


def test_lifecycle_test_role_alias_matches_test_runner_path(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path / "runs")
    reviewer_run_id = store.create_run("review-pass")
    reviewer_run_dir = store._run_dir(reviewer_run_id)
    (reviewer_run_dir / "reports").mkdir(parents=True, exist_ok=True)
    (reviewer_run_dir / "reports" / "review_report.json").write_text(
        json.dumps({"verdict": "PASS"}),
        encoding="utf-8",
    )

    step_reports = [
        {
            "index": 0,
            "status": "SUCCESS",
            "owner_agent": {"role": "PM"},
            "assigned_agent": {"role": "TECH_LEAD"},
            "run_id": "",
        },
        {
            "index": 1,
            "status": "SUCCESS",
            "owner_agent": {"role": "TECH_LEAD"},
            "assigned_agent": {"role": "WORKER"},
            "run_id": "",
        },
        {
            "index": 2,
            "status": "SUCCESS",
            "owner_agent": {"role": "WORKER"},
            "assigned_agent": {"role": "REVIEWER"},
            "run_id": reviewer_run_id,
        },
        {
            "index": 3,
            "status": "SUCCESS",
            "owner_agent": {"role": "REVIEWER"},
            "assigned_agent": {"role": "TEST"},
            "run_id": "",
        },
        {
            "index": 4,
            "status": "SUCCESS",
            "owner_agent": {"role": "TEST"},
            "assigned_agent": {"role": "PM"},
            "run_id": "",
        },
    ]

    summary, violations = chain_runner._build_lifecycle_summary(
        store,
        {"role": "PM"},
        step_reports,
        {
            "lifecycle": {
                "required_path": ["PM", "TECH_LEAD", "WORKER", "REVIEWER", "TEST_RUNNER", "PM"],
                "min_workers": 1,
                "min_reviewers": 1,
                "reviewer_quorum": 1,
                "require_test_stage": False,
                "require_return_to_pm": True,
            }
        },
    )

    assert summary["is_complete"] is True
    assert "required lifecycle path not satisfied" not in violations
