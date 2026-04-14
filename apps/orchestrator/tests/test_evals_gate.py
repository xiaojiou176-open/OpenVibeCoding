import json
from pathlib import Path

from openvibecoding_orch.gates.tests_gate import run_evals_gate


def _write_allowlist(root: Path) -> None:
    policies = root / "policies"
    policies.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": "v1",
        "allow": [
            {"exec": "bash", "argv_prefixes": [["bash"]]},
        ],
        "deny_substrings": [],
    }
    (policies / "command_allowlist.json").write_text(json.dumps(payload), encoding="utf-8")


def test_run_evals_gate_missing_script(tmp_path: Path) -> None:
    result = run_evals_gate(tmp_path, tmp_path)
    assert result["ok"] is False
    assert result["reason"] == "eval script missing"


def test_run_evals_gate_passes(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_allowlist(repo_root)
    scripts_dir = repo_root / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    script = scripts_dir / "run_evals.sh"
    script.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    result = run_evals_gate(repo_root, repo_root)
    assert result["ok"] is True
    assert result["report"]["status"] == "PASS"


def test_run_evals_gate_fails(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_allowlist(repo_root)
    scripts_dir = repo_root / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    script = scripts_dir / "run_evals.sh"
    script.write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
    result = run_evals_gate(repo_root, repo_root)
    assert result["ok"] is False
    assert result["report"]["status"] == "FAIL"
