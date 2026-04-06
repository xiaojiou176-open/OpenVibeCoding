import subprocess
from pathlib import Path

import pytest

from cortexpilot_orch.gates import diff_gate
from cortexpilot_orch.gates.diff_gate import validate_diff


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


def test_diff_gate_allows_prefix_and_blocks_protected(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    src = repo / "src"
    src.mkdir()
    (src / "app.py").write_text("print('ok')", encoding="utf-8")
    _git(["git", "add", "src/app.py"], cwd=repo)

    result = validate_diff(repo, ["src/"], baseline_ref="HEAD")
    assert result["ok"] is True

    (repo / "pytest.ini").write_text("[pytest]", encoding="utf-8")
    protected = validate_diff(repo, ["pytest.ini"], baseline_ref="HEAD")
    assert protected["ok"] is False
    assert protected["reason"] == "protected files modified"


def test_diff_gate_reports_git_diff_failure(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    result = validate_diff(repo, ["README.md"], baseline_ref="missing")
    assert result["ok"] is False
    assert result["reason"]


def test_diff_gate_ignores_root_runtime_artifacts(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    (repo / "patch.diff").write_text("mock", encoding="utf-8")
    (repo / "diff_name_only.txt").write_text("mock", encoding="utf-8")

    result = validate_diff(repo, ["apps/orchestrator/src", "apps/dashboard"], baseline_ref="HEAD")
    assert result["ok"] is True
    assert result["changed_files"] == []
    assert result["violations"] == []


def test_diff_gate_reports_git_status_failure(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    def _fake_git(cmd: list[str], cwd: Path):
        if "status" in cmd:
            return subprocess.CompletedProcess(cmd, 1, "", "boom")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(diff_gate, "_git", _fake_git)
    result = validate_diff(repo, ["README.md"], baseline_ref="HEAD")
    assert result["ok"] is False
    assert result["reason"] == "boom" or "git status failed" in result["reason"]


def test_diff_gate_helpers() -> None:
    assert diff_gate._is_allowed("src/app.py", ["src/"]) is True
    assert diff_gate._is_allowed("src/app.py", ["docs/"]) is False
    assert diff_gate._is_allowed("src/app.py", ["src/*.py"]) is False
    assert diff_gate._is_allowed("src/app.py", ["docs/*.md"]) is False
    assert diff_gate._is_allowed("src/app.py", [""]) is False

    protected = diff_gate._default_protected_paths()
    assert diff_gate._is_protected("pytest.ini", protected) is True
    assert diff_gate._is_protected("docs/readme.md", protected) is False
    assert diff_gate._is_protected(".env.example", protected) is False
    assert diff_gate._is_protected(".env.local", protected) is True


def test_diff_gate_protected_env(monkeypatch) -> None:
    monkeypatch.setenv("CORTEXPILOT_PROTECTED_PATHS", "a.txt, b.txt")
    protected = diff_gate._default_protected_paths()
    assert protected == ["a.txt", "b.txt"]
    assert diff_gate._is_protected("a.txt", ["", "a.txt"]) is True
    assert diff_gate._is_protected("dir/file.txt", ["dir"]) is True
