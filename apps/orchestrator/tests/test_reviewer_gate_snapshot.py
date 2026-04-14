import subprocess
from pathlib import Path

from openvibecoding_orch.gates.reviewer_gate import snapshot_worktree, validate_reviewer_isolation


def _git(cmd: list[str], cwd: Path) -> None:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def _init_repo(repo: Path) -> None:
    _git(["git", "init"], cwd=repo)
    _git(["git", "config", "user.email", "test@example.com"], cwd=repo)
    _git(["git", "config", "user.name", "tester"], cwd=repo)


def test_reviewer_snapshot_detects_modification(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    target = repo / "README.md"
    target.write_text("hello", encoding="utf-8")
    _git(["git", "add", "README.md"], cwd=repo)
    _git(["git", "commit", "-m", "init"], cwd=repo)

    snapshot = snapshot_worktree(repo)
    target.write_text("changed", encoding="utf-8")

    result = validate_reviewer_isolation(repo, snapshot)
    assert result["ok"] is False
    assert any(item["path"] == "README.md" and item["change"] == "modified" for item in result["changed"])


def test_reviewer_snapshot_detects_added_file(tmp_path: Path) -> None:
    repo = tmp_path / "repo_added"
    repo.mkdir()
    _init_repo(repo)
    (repo / "base.txt").write_text("base", encoding="utf-8")
    _git(["git", "add", "base.txt"], cwd=repo)
    _git(["git", "commit", "-m", "init"], cwd=repo)

    snapshot = snapshot_worktree(repo)
    (repo / "new.txt").write_text("new", encoding="utf-8")

    result = validate_reviewer_isolation(repo, snapshot)
    assert result["ok"] is False
    assert any(item["path"] == "new.txt" and item["change"] == "added" for item in result["changed"])
