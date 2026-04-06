import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from cortexpilot_orch.gates import tests_gate


def _patch_tests_gate_subprocess(monkeypatch: pytest.MonkeyPatch, run_impl) -> None:
    monkeypatch.setattr(
        tests_gate,
        "subprocess",
        SimpleNamespace(
            run=run_impl,
            CompletedProcess=subprocess.CompletedProcess,
            TimeoutExpired=subprocess.TimeoutExpired,
        ),
    )


def test_tests_gate_empty_command(tmp_path: Path) -> None:
    result = tests_gate.run_acceptance_tests(tmp_path, [""])
    assert result["ok"] is False
    assert result["reason"] == "empty command"


def test_tests_gate_empty_list(tmp_path: Path) -> None:
    result = tests_gate.run_acceptance_tests(tmp_path, [])
    assert result["ok"] is False
    assert result["reason"] == "acceptance_tests empty"


def test_tests_gate_tool_gate_violation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(tests_gate, "validate_command", lambda *args, **kwargs: {"ok": False})
    result = tests_gate.run_acceptance_tests(
        tmp_path,
        [{"name": "hygiene", "cmd": "bash scripts/check_repo_hygiene.sh", "must_pass": True}],
    )
    assert result["ok"] is False
    assert result["reason"] == "tool gate violation"


def test_tests_gate_invalid_shlex(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(tests_gate, "validate_command", lambda *args, **kwargs: {"ok": True})
    result = tests_gate.run_acceptance_tests(tmp_path, ['echo "unterminated'])
    assert result["ok"] is False
    assert "invalid command" in result["reason"]


def test_tests_gate_fail_and_must_pass(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(tests_gate, "validate_command", lambda *args, **kwargs: {"ok": True})

    def _fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args, 1, "", "boom")

    _patch_tests_gate_subprocess(monkeypatch, _fake_run)
    result = tests_gate.run_acceptance_tests(tmp_path, ["echo fail"])
    assert result["ok"] is False
    assert result["reason"] == "test failed"


def test_tests_gate_must_pass_false(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(tests_gate, "validate_command", lambda *args, **kwargs: {"ok": True})

    def _fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args, 1, "", "boom")

    _patch_tests_gate_subprocess(monkeypatch, _fake_run)
    result = tests_gate.run_acceptance_tests(tmp_path, [{"name": "fail", "cmd": "echo fail", "must_pass": False}])
    assert result["ok"] is False
    assert result["reason"] == "missing must_pass acceptance test"


def test_run_tests_gate_wrapper(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(tests_gate, "validate_command", lambda *args, **kwargs: {"ok": True})

    def _fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args, 0, "ok", "")

    _patch_tests_gate_subprocess(monkeypatch, _fake_run)
    result = tests_gate.run_tests_gate("run-id", tmp_path, ["bash scripts/check_repo_hygiene.sh"])
    assert result["ok"] is True


def test_tests_gate_strict_nontrivial_blocks_echo(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CORTEXPILOT_ACCEPTANCE_STRICT_NONTRIVIAL", "1")
    monkeypatch.setattr(tests_gate, "validate_command", lambda *args, **kwargs: {"ok": True})

    result = tests_gate.run_acceptance_tests(tmp_path, ["echo ok"])

    assert result["ok"] is False
    assert result["reason"] == "trivial acceptance command blocked"


def test_tests_gate_strict_nontrivial_allows_real_command(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CORTEXPILOT_ACCEPTANCE_STRICT_NONTRIVIAL", "1")
    monkeypatch.setattr(tests_gate, "validate_command", lambda *args, **kwargs: {"ok": True})

    def _fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args, 0, "ok", "")

    _patch_tests_gate_subprocess(monkeypatch, _fake_run)

    result = tests_gate.run_acceptance_tests(
        tmp_path,
        [{"name": "hygiene", "cmd": "bash scripts/check_repo_hygiene.sh", "must_pass": True}],
    )

    assert result["ok"] is True


def test_tests_gate_strict_nontrivial_blocks_quoted_empty_command(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CORTEXPILOT_ACCEPTANCE_STRICT_NONTRIVIAL", "1")
    monkeypatch.setattr(tests_gate, "validate_command", lambda *args, **kwargs: {"ok": True})

    result = tests_gate.run_acceptance_tests(tmp_path, ['""'])

    assert result["ok"] is False
    assert result["reason"] == "trivial acceptance command blocked"


def test_tests_gate_strict_nontrivial_blocks_echo_numeric_payload(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CORTEXPILOT_ACCEPTANCE_STRICT_NONTRIVIAL", "1")
    monkeypatch.setattr(tests_gate, "validate_command", lambda *args, **kwargs: {"ok": True})

    result = tests_gate.run_acceptance_tests(tmp_path, ['echo "1"'])

    assert result["ok"] is False
    assert result["reason"] == "trivial acceptance command blocked"


def test_is_trivial_acceptance_command_treats_whitespace_only_as_trivial() -> None:
    assert tests_gate._is_trivial_acceptance_command(" \t  \n ") is True


def test_tests_gate_resolves_relative_worktree_for_tool_gate(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "policies").mkdir(parents=True)
    (repo_root / "scripts").mkdir(parents=True)

    (repo_root / "policies" / "command_allowlist.json").write_text(
        '{"allow": [{"exec": "bash", "argv_prefixes": [["bash", "scripts/"]]}], "deny_substrings": []}',
        encoding="utf-8",
    )

    script = repo_root / "scripts" / "test.sh"
    script.write_text("#!/usr/bin/env bash\necho ok\n", encoding="utf-8")
    script.chmod(0o755)

    relative_repo = Path(os.path.relpath(repo_root, Path.cwd()))
    result = tests_gate.run_acceptance_tests(relative_repo, ["bash scripts/test.sh"])

    assert result["ok"] is True
    assert result["reports"]


def test_tests_gate_respects_timeout_sec_from_acceptance_item(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(tests_gate, "validate_command", lambda *args, **kwargs: {"ok": True})

    captured: dict[str, float | None] = {"timeout": None}

    def _fake_run(*args, **kwargs):
        captured["timeout"] = kwargs.get("timeout")
        return subprocess.CompletedProcess(args, 0, "ok", "")

    _patch_tests_gate_subprocess(monkeypatch, _fake_run)

    result = tests_gate.run_acceptance_tests(
        tmp_path,
        [{"name": "custom-timeout", "cmd": "bash scripts/check_repo_hygiene.sh", "must_pass": True, "timeout_sec": 3}],
    )

    assert result["ok"] is True
    assert captured["timeout"] == 3.0
    report = result["reports"][0]
    command = report["commands"][0]
    assert command["timeout_sec"] == 3.0


def test_tests_gate_prefers_repo_venv_and_sets_pythonpath(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(tests_gate, "validate_command", lambda *args, **kwargs: {"ok": True})
    repo_root = Path(tests_gate.__file__).resolve().parents[5]
    machine_cache_root = tmp_path / "machine-cache"
    monkeypatch.setenv("CORTEXPILOT_MACHINE_CACHE_ROOT", str(machine_cache_root))
    monkeypatch.delenv("CORTEXPILOT_PYTHON", raising=False)
    monkeypatch.delenv("CORTEXPILOT_TOOLCHAIN_CACHE_ROOT", raising=False)
    monkeypatch.setattr(tests_gate, "load_config", lambda: __import__("types").SimpleNamespace(toolchain_cache_root=machine_cache_root / "toolchains"))
    venv_root = machine_cache_root / "toolchains" / "python" / "current"
    venv_bin = venv_root / "bin"
    venv_bin.mkdir(parents=True, exist_ok=True)
    (venv_bin / "python").write_text("", encoding="utf-8")

    captured: dict[str, object] = {}

    def _fake_run(*args, **kwargs):
        captured["env"] = kwargs.get("env", {})
        return subprocess.CompletedProcess(args, 0, "ok", "")

    _patch_tests_gate_subprocess(monkeypatch, _fake_run)

    result = tests_gate.run_acceptance_tests(
        tmp_path,
        [{"name": "pytest", "cmd": "python3 -m pytest apps/orchestrator/tests/test_schema_validation.py -q", "must_pass": True}],
    )

    assert result["ok"] is True
    env = captured["env"]
    assert isinstance(env, dict)
    assert str(venv_bin) in str(env.get("PATH", ""))
    assert str(repo_root / "apps" / "orchestrator" / "src") in str(env.get("PYTHONPATH", ""))
    assert env.get("VIRTUAL_ENV") == str(venv_root)
    assert env.get("PYTHONDONTWRITEBYTECODE") == "1"


def test_tests_gate_rejects_nan_timeout_value(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(tests_gate, "validate_command", lambda *args, **kwargs: {"ok": True})

    captured: dict[str, float | None] = {"timeout": None}

    def _fake_run(*args, **kwargs):
        captured["timeout"] = kwargs.get("timeout")
        return subprocess.CompletedProcess(args, 0, "ok", "")

    _patch_tests_gate_subprocess(monkeypatch, _fake_run)

    result = tests_gate.run_acceptance_tests(
        tmp_path,
        [{"name": "nan-timeout", "cmd": "bash scripts/check_repo_hygiene.sh", "must_pass": True, "timeout_sec": "nan"}],
    )

    assert result["ok"] is True
    assert captured["timeout"] == 600.0
    command = result["reports"][0]["commands"][0]
    assert command["timeout_sec"] == 600.0


def test_tests_gate_reports_launch_failure_without_raise(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(tests_gate, "validate_command", lambda *args, **kwargs: {"ok": True})

    def _fake_run(*args, **kwargs):
        raise PermissionError("permission denied")

    _patch_tests_gate_subprocess(monkeypatch, _fake_run)

    result = tests_gate.run_acceptance_tests(
        tmp_path,
        [{"name": "launch-error", "cmd": "bash scripts/check_repo_hygiene.sh", "must_pass": True, "timeout_sec": 5}],
    )

    assert result["ok"] is False
    assert result["reason"] == "test launch failed"
    report = result["reports"][0]
    assert report["failure"]["message"].startswith("test launch failed:")


def test_tests_gate_returns_timeout_reason(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(tests_gate, "validate_command", lambda *args, **kwargs: {"ok": True})

    def _fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=kwargs.get("args", "cmd"), timeout=kwargs.get("timeout", 1.0))

    _patch_tests_gate_subprocess(monkeypatch, _fake_run)

    result = tests_gate.run_acceptance_tests(
        tmp_path,
        [{"name": "timeout", "cmd": "bash scripts/check_repo_hygiene.sh", "must_pass": True, "timeout_sec": 1}],
    )

    assert result["ok"] is False
    assert result["reason"] == "test timeout"


def test_tests_gate_rejects_when_all_acceptance_tests_are_not_must_pass(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(tests_gate, "validate_command", lambda *args, **kwargs: {"ok": True})

    result = tests_gate.run_acceptance_tests(
        tmp_path,
        [{"name": "optional", "cmd": "bash scripts/check_repo_hygiene.sh", "must_pass": False}],
    )

    assert result["ok"] is False
    assert result["reason"] == "missing must_pass acceptance test"


def test_run_evals_gate_blocks_tool_gate_violation(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    worktree = repo_root / "worktree"
    (repo_root / "scripts").mkdir(parents=True)
    worktree.mkdir(parents=True)
    (repo_root / "scripts" / "run_evals.sh").write_text("#!/usr/bin/env bash\necho evals\n", encoding="utf-8")

    called: dict[str, bool] = {"run": False}

    def _fake_run(*args, **kwargs):
        called["run"] = True
        return subprocess.CompletedProcess(args, 0, "ok", "")

    monkeypatch.setattr(tests_gate, "validate_command", lambda *args, **kwargs: {"ok": False, "reason": "blocked"})
    _patch_tests_gate_subprocess(monkeypatch, _fake_run)

    result = tests_gate.run_evals_gate(repo_root, worktree)

    assert result["ok"] is False
    assert result["reason"] == "tool gate violation"
    assert called["run"] is False


def test_tests_gate_coerces_string_must_pass_false(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(tests_gate, "validate_command", lambda *args, **kwargs: {"ok": True})

    result = tests_gate.run_acceptance_tests(
        tmp_path,
        [{"name": "optional", "cmd": "bash scripts/check_repo_hygiene.sh", "must_pass": "false"}],
    )

    assert result["ok"] is False
    assert result["reason"] == "missing must_pass acceptance test"
