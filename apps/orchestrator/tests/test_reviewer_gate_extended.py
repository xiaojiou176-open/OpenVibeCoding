import subprocess
from pathlib import Path

import pytest

from cortexpilot_orch.gates import reviewer_gate
from cortexpilot_orch.gates.reviewer_gate import snapshot_worktree, validate_reviewer_isolation


def _git(cmd: list[str], cwd: Path) -> None:
    res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(["git", "init"], cwd=repo)
    _git(["git", "config", "user.email", "test@example.com"], cwd=repo)
    _git(["git", "config", "user.name", "tester"], cwd=repo)
    (repo / "README.md").write_text("hello", encoding="utf-8")
    _git(["git", "add", "README.md"], cwd=repo)
    _git(["git", "commit", "-m", "init"], cwd=repo)


def test_reviewer_gate_detects_modifications_verbose(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    snap = snapshot_worktree(repo)
    (repo / "README.md").write_text("changed", encoding="utf-8")

    monkeypatch.setenv("CORTEXPILOT_REVIEWER_SNAPSHOT_VERBOSE", "1")
    result = validate_reviewer_isolation(repo, snap)
    assert result["ok"] is False
    assert result["reason"] == "reviewer modified working tree"
    assert "before" in result and "after" in result
    assert any(change["change"] == "modified" for change in result["changed"])


def test_reviewer_gate_snapshot_missing_file(monkeypatch, tmp_path: Path) -> None:
    def _fake_ls_files(worktree: Path) -> list[str]:
        return ["missing.txt"]

    monkeypatch.setattr(reviewer_gate, "_git_ls_files", _fake_ls_files)
    monkeypatch.setattr(reviewer_gate, "_list_untracked", lambda worktree: [])

    snapshot = reviewer_gate._snapshot_files(tmp_path)
    assert snapshot["missing.txt"]["missing"] is True


def test_reviewer_gate_git_status_failure(monkeypatch, tmp_path: Path) -> None:
    class Dummy:
        returncode = 1
        stdout = ""
        stderr = "boom"

    monkeypatch.setattr(reviewer_gate.subprocess, "run", lambda *args, **kwargs: Dummy())
    with pytest.raises(RuntimeError):
        reviewer_gate._git_status_porcelain(tmp_path)


def test_reviewer_gate_git_ls_files_failure(monkeypatch, tmp_path: Path) -> None:
    class Dummy:
        returncode = 1
        stdout = ""
        stderr = "boom"

    monkeypatch.setattr(reviewer_gate.subprocess, "run", lambda *args, **kwargs: Dummy())
    with pytest.raises(RuntimeError):
        reviewer_gate._git_ls_files(tmp_path)


def test_reviewer_gate_removed_file(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo_removed"
    _init_repo(repo)
    snap = snapshot_worktree(repo)
    (repo / "README.md").unlink()
    monkeypatch.setattr(reviewer_gate, "_git_ls_files", lambda worktree: [])
    result = validate_reviewer_isolation(repo, snap)
    assert any(change["change"] == "removed" for change in result["changed"])


def test_reviewer_gate_skips_directory(tmp_path: Path, monkeypatch) -> None:
    def _fake_ls_files(worktree: Path) -> list[str]:
        return ["dir/"]

    monkeypatch.setattr(reviewer_gate, "_git_ls_files", _fake_ls_files)
    monkeypatch.setattr(reviewer_gate, "_list_untracked", lambda worktree: [])
    (tmp_path / "dir").mkdir()
    snapshot = reviewer_gate._snapshot_files(tmp_path)
    assert "dir/" not in snapshot
