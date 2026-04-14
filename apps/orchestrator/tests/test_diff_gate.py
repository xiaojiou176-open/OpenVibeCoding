import subprocess
from pathlib import Path

from openvibecoding_orch.gates.diff_gate import run_diff_gate


def _git(cmd, cwd: Path):
    res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr


def test_diff_gate_violation(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["git", "init"], cwd=repo)
    _git(["git", "config", "user.email", "test@example.com"], cwd=repo)
    _git(["git", "config", "user.name", "tester"], cwd=repo)
    (repo / "a.txt").write_text("hello", encoding="utf-8")
    _git(["git", "add", "a.txt"], cwd=repo)
    _git(["git", "commit", "-m", "init"], cwd=repo)

    (repo / "b.txt").write_text("oops", encoding="utf-8")
    result = run_diff_gate(repo, ["a.txt"], baseline_ref="HEAD")
    assert result["ok"] is False
