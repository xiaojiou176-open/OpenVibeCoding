import io
import json
from pathlib import Path

import pytest

from cortexpilot_orch.reviewer.reviewer import Reviewer, CodexReviewer, _contract_alignment, _extract_diff_files


def test_reviewer_flags_missing_diff_and_failed_tests() -> None:
    contract = {
        "task_id": "review_task",
        "allowed_paths": ["README.md"],
        "task_type": "IMPLEMENT",
        "required_outputs": [{"name": "patch.diff", "type": "patch", "acceptance": "code change"}],
        "tool_permissions": {"filesystem": "workspace-write"},
        "mcp_tool_set": ["01-filesystem"],
    }
    report = Reviewer().review_task(contract, diff_text="", test_report={"status": "FAIL", "artifacts": []})
    assert report["verdict"] == "FAIL"
    assert "diff is empty" in report["summary"]
    assert "tests did not pass" in report["summary"]


def test_reviewer_allows_empty_diff_for_plan_task() -> None:
    contract = {
        "task_id": "review_task",
        "allowed_paths": ["README.md"],
        "task_type": "PLAN",
        "required_outputs": [{"name": "report.json", "type": "report", "acceptance": "analysis report"}],
        "tool_permissions": {"filesystem": "read-only"},
        "mcp_tool_set": ["01-filesystem"],
    }
    report = Reviewer().review_task(contract, diff_text="", test_report={"status": "PASS", "artifacts": []})
    assert report["verdict"] == "PASS"


def test_contract_alignment_glob_and_out_of_scope() -> None:
    contract = {"allowed_paths": ["src/", "README.md"]}
    diff = "diff --git a/src/app.py b/src/app.py\n"
    aligned = _contract_alignment(contract, diff, inputs_meta={"baseline_ref": "a", "head_ref": "b"})
    assert aligned["passed"] is True

    diff_out = "diff --git a/secret.txt b/secret.txt\n"
    violated = _contract_alignment(contract, diff_out, inputs_meta={"baseline_ref": "", "head_ref": ""})
    assert violated["passed"] is False
    assert any("allowed_paths" in item for item in violated["violations"])


def test_extract_diff_files_handles_renames() -> None:
    diff = "\n".join(
        [
            "diff --git a/old.txt b/new.txt",
            "rename from old.txt",
            "rename to new.txt",
        ]
    )
    files = _extract_diff_files(diff)
    assert "new.txt" in files


def test_contract_alignment_ignores_root_runtime_artifacts() -> None:
    contract = {"allowed_paths": ["README.md"]}
    diff = "\n".join(
        [
            "diff --git a/patch.diff b/patch.diff",
            "new file mode 100644",
            "diff --git a/README.md b/README.md",
        ]
    )
    aligned = _contract_alignment(contract, diff, inputs_meta={"baseline_ref": "a", "head_ref": "b"})
    assert aligned["passed"] is True


def test_codex_reviewer_happy_path(monkeypatch, tmp_path: Path) -> None:
    contract = {"task_id": "review_task", "allowed_paths": ["README.md"]}
    diff_text = "diff --git a/README.md b/README.md\n"
    test_report = {"status": "PASS", "artifacts": []}
    inputs_meta = {"baseline_ref": "a", "head_ref": "b", "patch_ref": "patch"}

    payload = {
        "run_id": "run-0001",
        "task_id": "review_task",
        "reviewer": {"role": "REVIEWER", "agent_id": "reviewer-1"},
        "reviewed_at": "2024-01-01T00:00:00Z",
        "verdict": "PASS",
        "summary": "ok",
        "scope_check": {"passed": True, "violations": []},
        "evidence": [],
        "produced_diff": False,
    }
    stdout = io.StringIO(json.dumps(payload) + "\n")
    stderr = io.StringIO("")

    class DummyProc:
        def __init__(self) -> None:
            self.stdout = stdout
            self.stderr = stderr

        def wait(self) -> int:
            return 0

    monkeypatch.setattr("subprocess.Popen", lambda *args, **kwargs: DummyProc())

    reviewer = CodexReviewer()
    report = reviewer.review_task(contract, diff_text, test_report, tmp_path, inputs_meta=inputs_meta)
    assert report["verdict"] == "PASS"
    assert report["scope_check"]["passed"] is True


def test_codex_reviewer_rejects_produced_diff(monkeypatch, tmp_path: Path) -> None:
    contract = {"task_id": "review_task", "allowed_paths": ["README.md"]}
    diff_text = "diff --git a/README.md b/README.md\n"
    test_report = {"status": "PASS", "artifacts": []}

    payload = {
        "run_id": "run-0001",
        "task_id": "review_task",
        "reviewer": {"role": "REVIEWER", "agent_id": "reviewer-1"},
        "reviewed_at": "2024-01-01T00:00:00Z",
        "verdict": "PASS",
        "summary": "ok",
        "scope_check": {"passed": True, "violations": []},
        "evidence": [],
        "produced_diff": True,
    }
    stdout = io.StringIO(json.dumps(payload) + "\n")
    stderr = io.StringIO("")

    class DummyProc:
        def __init__(self) -> None:
            self.stdout = stdout
            self.stderr = stderr

        def wait(self) -> int:
            return 0

    monkeypatch.setattr("subprocess.Popen", lambda *args, **kwargs: DummyProc())

    reviewer = CodexReviewer()
    with pytest.raises(RuntimeError):
        reviewer.review_task(contract, diff_text, test_report, tmp_path)
