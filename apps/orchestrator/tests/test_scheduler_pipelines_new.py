from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from openvibecoding_orch.scheduler import approval_flow, evidence_pipeline, task_build_pipeline, test_pipeline


class _ApprovalStore:
    def __init__(self, events_path: Path) -> None:
        self._events_path = events_path
        self.events: list[dict[str, Any]] = []

    def append_event(self, run_id: str, payload: dict[str, Any]) -> None:
        self.events.append({"run_id": run_id, **payload})

    def events_path(self, run_id: str) -> Path:
        return self._events_path


class _EvidenceStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.writes: list[tuple[str, str, dict[str, Any]]] = []

    def run_dir(self, run_id: str) -> Path:
        path = self.root / run_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write_report(self, run_id: str, name: str, payload: dict[str, Any]) -> None:
        self.writes.append((run_id, name, payload))
        out = self.run_dir(run_id) / "reports" / f"{name}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


class _LegacyEvidenceStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.writes: list[tuple[str, str, dict[str, Any]]] = []

    def _run_dir(self, run_id: str) -> Path:
        path = self.root / run_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write_report(self, run_id: str, name: str, payload: dict[str, Any]) -> None:
        self.writes.append((run_id, name, payload))


def test_approval_requires_human_approval_modes(monkeypatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_GOD_MODE_REQUIRED", "1")
    assert approval_flow.requires_human_approval(
        requires_network=False,
        filesystem_policy="read-only",
        network_policy="deny",
        shell_policy="untrusted",
    )

    monkeypatch.setenv("OPENVIBECODING_GOD_MODE_REQUIRED", "0")
    monkeypatch.setenv("OPENVIBECODING_GOD_MODE_ON_REQUEST", "0")
    assert approval_flow.requires_human_approval(
        requires_network=False,
        filesystem_policy="danger-full-access",
        network_policy="deny",
        shell_policy="deny",
    )

    monkeypatch.setenv("OPENVIBECODING_GOD_MODE_ON_REQUEST", "1")
    assert approval_flow.requires_human_approval(
        requires_network=True,
        filesystem_policy="workspace-write",
        network_policy="on-request",
        shell_policy="deny",
    )
    assert approval_flow.requires_human_approval(
        requires_network=False,
        filesystem_policy="workspace-write",
        network_policy="deny",
        shell_policy="on-request",
    )


def test_approval_helpers_flags(monkeypatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_FORCE_UNLOCK", "true")
    assert approval_flow.force_unlock_requested()

    monkeypatch.setenv("OPENVIBECODING_LOCK_AUTO_CLEANUP", "")
    monkeypatch.setenv("OPENVIBECODING_LOCK_TTL_SEC", "120")
    assert approval_flow.auto_lock_cleanup_requested()

    monkeypatch.setenv("OPENVIBECODING_GOD_MODE_TIMEOUT_SEC", "15")
    assert approval_flow.god_mode_timeout_sec() == 15
    monkeypatch.setenv("OPENVIBECODING_GOD_MODE_TIMEOUT_SEC", "bad")
    assert approval_flow.god_mode_timeout_sec() == 0


def test_await_human_approval_success(tmp_path: Path, monkeypatch) -> None:
    events = tmp_path / "events.jsonl"
    events.write_text(
        json.dumps({"event": "HUMAN_APPROVAL_COMPLETED"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    store = _ApprovalStore(events)
    monkeypatch.setenv("OPENVIBECODING_GOD_MODE_TIMEOUT_SEC", "3")
    assert approval_flow.await_human_approval("run-1", store, reason=["r"]) is True
    assert store.events and store.events[0]["event"] == "HUMAN_APPROVAL_REQUIRED"


def test_await_human_approval_timeout(tmp_path: Path, monkeypatch) -> None:
    events = tmp_path / "events-empty.jsonl"
    events.write_text("", encoding="utf-8")
    store = _ApprovalStore(events)
    monkeypatch.setenv("OPENVIBECODING_GOD_MODE_TIMEOUT_SEC", "1")

    tick = {"value": 0}

    def _fake_monotonic() -> float:
        tick["value"] += 1
        return float(tick["value"])

    monkeypatch.setattr(approval_flow.time, "monotonic", _fake_monotonic)
    monkeypatch.setattr(approval_flow.time, "sleep", lambda _: None)

    assert approval_flow.await_human_approval("run-timeout", store) is False
    assert any(event.get("event") == "HUMAN_APPROVAL_TIMEOUT" for event in store.events)


def test_test_pipeline_read_extract_cleanup_and_stubs(tmp_path: Path) -> None:
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    out = worktree / "stdout.log"
    err = worktree / "stderr.log"
    out.write_text("ok", encoding="utf-8")
    err.write_text("warn", encoding="utf-8")

    report = {
        "commands": [
            {
                "cmd_argv": ["pytest", "-q"],
                "stdout": {"path": "stdout.log"},
                "stderr": {"path": "stderr.log"},
            }
        ]
    }

    cmd, stdout_text, stderr_text = test_pipeline.extract_test_logs(report, worktree)
    assert cmd == "pytest -q"
    assert stdout_text == "ok"
    assert stderr_text == "warn"

    test_pipeline.cleanup_test_artifacts(report, worktree)
    assert not out.exists()
    assert not err.exists()

    stub_ok = test_pipeline.build_test_report_stub("r", "t", 1, "s", "f", "SUCCESS", "")
    stub_fail = test_pipeline.build_test_report_stub("r", "t", 1, "s", "f", "FAIL", "bad")
    review = test_pipeline.build_review_report_stub("r", "t", 1, "now", "FAIL", "oops")

    assert "failure" not in stub_ok
    assert stub_fail["failure"]["message"] == "bad"
    assert review["notes"] == "oops"


def test_evidence_hash_collect_and_report(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    (run_dir / "reports").mkdir(parents=True)

    events = run_dir / "events.jsonl"
    events.write_text(
        "\n".join(
            [
                json.dumps({"event": "REPLAY_START"}, ensure_ascii=False),
                json.dumps({"event": "KEEP", "k": 1}, ensure_ascii=False),
                "not-json",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "reports" / "x.json").write_text('{"x":1}', encoding="utf-8")

    digest = evidence_pipeline.hash_events(events)
    expected = hashlib.sha256(
        (
            json.dumps({"event": "KEEP", "k": 1}, ensure_ascii=False)
            + "\n"
            + "not-json"
        ).encode("utf-8")
    ).hexdigest()
    assert digest == expected

    hashes = evidence_pipeline.collect_evidence_hashes(run_dir)
    assert "events.jsonl" in hashes
    assert hashes["events.jsonl"] == digest
    assert "reports/x.json" in hashes

    fail_report = evidence_pipeline.build_evidence_report(run_dir)
    assert fail_report["status"] == "fail"

    for rel in [
        "contract.json",
        "patch.diff",
        "reports/task_result.json",
        "reports/test_report.json",
        "reports/review_report.json",
    ]:
        p = run_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{}", encoding="utf-8")

    ok_report = evidence_pipeline.build_evidence_report(run_dir)
    assert ok_report["status"] == "ok"


def test_evidence_placeholder_and_ensure(tmp_path: Path, monkeypatch) -> None:
    payload = evidence_pipeline.placeholder_evidence_bundle(
        {"assigned_agent": {"role": "UNKNOWN", "agent_id": ""}},
        "reason",
    )
    assert payload["requested_by"]["role"] == "ORCHESTRATOR"
    assert payload["requested_by"]["agent_id"] == "orchestrator"

    store = _EvidenceStore(tmp_path)

    def _raise_validate(self: Any, report: dict[str, Any], schema_name: str) -> None:  # noqa: ARG001
        raise RuntimeError("schema fail")

    monkeypatch.setattr(evidence_pipeline.ContractValidator, "validate_report", _raise_validate)
    evidence_pipeline.ensure_evidence_bundle_placeholder(store, "run-a", {}, "test")
    assert store.writes and store.writes[0][1] == "evidence_bundle"

    before = len(store.writes)
    evidence_pipeline.ensure_evidence_bundle_placeholder(store, "run-a", {}, "test")
    assert len(store.writes) == before

    legacy = _LegacyEvidenceStore(tmp_path)
    evidence_pipeline.ensure_evidence_bundle_placeholder(legacy, "run-b", {}, "legacy")
    assert legacy.writes


def test_approval_extra_branches_and_invalid_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_GOD_MODE_REQUIRED", "0")
    monkeypatch.setenv("OPENVIBECODING_GOD_MODE_ON_REQUEST", "1")
    assert approval_flow.requires_human_approval(
        requires_network=False,
        filesystem_policy="danger-full-access",
        network_policy="deny",
        shell_policy="deny",
    )

    monkeypatch.setenv("OPENVIBECODING_LOCK_AUTO_CLEANUP", "true")
    assert approval_flow.auto_lock_cleanup_requested()

    events = tmp_path / "missing-events.jsonl"
    store = _ApprovalStore(events)
    monkeypatch.setenv("OPENVIBECODING_GOD_MODE_TIMEOUT_SEC", "1")

    tick = {"value": 0}

    def _fake_monotonic() -> float:
        tick["value"] += 1
        return float(tick["value"])

    monkeypatch.setattr(approval_flow.time, "monotonic", _fake_monotonic)
    monkeypatch.setattr(approval_flow.time, "sleep", lambda _: None)
    assert approval_flow.await_human_approval("run-missing", store) is False

    bad = tmp_path / "bad-events.jsonl"
    bad.write_text("not-json\n" + json.dumps({"event": "HUMAN_APPROVAL_COMPLETED"}) + "\n", encoding="utf-8")
    store_bad = _ApprovalStore(bad)
    monkeypatch.setenv("OPENVIBECODING_GOD_MODE_TIMEOUT_SEC", "2")
    assert approval_flow.await_human_approval("run-bad", store_bad) is True


def test_test_pipeline_extra_branches(tmp_path: Path, monkeypatch) -> None:
    worktree = tmp_path / "work"
    worktree.mkdir()

    assert test_pipeline.read_artifact_text(worktree, "not-dict") == ""
    assert test_pipeline.read_artifact_text(worktree, {"path": ""}) == ""

    test_pipeline.cleanup_test_artifacts({"commands": "bad"}, worktree)
    test_pipeline.cleanup_test_artifacts({"commands": ["bad", {"stdout": "bad"}, {"stderr": {"path": ""}}]}, worktree)

    file_path = worktree / "stdout.log"
    file_path.write_text("x", encoding="utf-8")

    original_unlink = Path.unlink

    def _raise_once(self: Path, *args: Any, **kwargs: Any) -> None:  # noqa: ARG001
        if self == file_path:
            raise OSError("blocked")
        original_unlink(self)

    monkeypatch.setattr(Path, "unlink", _raise_once)
    test_pipeline.cleanup_test_artifacts(
        {"commands": [{"stdout": {"path": "stdout.log"}}]},
        worktree,
    )


def test_task_build_pipeline_result_and_work_report() -> None:
    producer = {"role": "WORKER", "agent_id": "w-1"}
    changed_files = {"name": "diff_name_only", "path": "diff_name_only.txt"}
    patch = {"name": "patch", "path": "patch.diff"}

    success = task_build_pipeline.build_task_result(
        run_id="run-1",
        task_id="task-1",
        attempt=1,
        producer=producer,
        status="SUCCESS",
        started_at="s",
        finished_at="f",
        summary="done",
        failure_reason="",
        diff_gate={"ok": True, "violations": []},
        policy_gate={"passed": True, "violations": []},
        review_report={"verdict": "PASS"},
        review_gate_result={"ok": True},
        tests_result={"ok": True},
        baseline_ref="b",
        head_ref="h",
        changed_files=changed_files,
        patch=patch,
    )
    assert success["gates"]["tests_gate"]["passed"] is True
    assert success["next_steps"]["suggested_action"] == "none"

    failure = task_build_pipeline.build_task_result(
        run_id="run-2",
        task_id="task-2",
        attempt=2,
        producer=producer,
        status="FAIL",
        started_at="s",
        finished_at="f",
        summary="",
        failure_reason="bad",
        diff_gate=None,
        policy_gate={"passed": False, "violations": ["p"]},
        review_report={"verdict": "FAIL"},
        review_gate_result={"ok": False},
        tests_result=None,
        baseline_ref="",
        head_ref="",
        changed_files=changed_files,
        patch=patch,
    )
    assert failure["gates"]["diff_gate"]["violations"] == ["diff_gate_missing"]
    assert failure["gates"]["tests_gate"]["violations"] == ["tests_missing"]
    assert failure["failure"]["message"] == "bad"

    work = task_build_pipeline.build_work_report(
        run_id="run-3",
        task_id="task-3",
        status="FAIL",
        diff_gate={"ok": False, "violations": ["x"], "changed_files": ["a.py", "b.py"]},
        tests_result=None,
        review_report=None,
    )
    assert work["diff_summary"] == "a.py, b.py"
    assert work["gates"]["diff_gate"]["passed"] is False
