from __future__ import annotations

import hashlib
import math
import os
import re
import shlex
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from cortexpilot_orch.gates.tool_gate import validate_command
from cortexpilot_orch.config import load_config


_DEFAULT_TIMEOUT_SEC = 600
_TRIVIAL_ACCEPTANCE_COMMANDS = {
    "echo ok",
    "echo hello",
    "echo pass",
    "echo success",
    "echo done",
    "true",
    ":",
}


def _coerce_timeout_sec(raw: object) -> float:
    timeout_sec = _DEFAULT_TIMEOUT_SEC
    try:
        timeout_sec = float(raw)
    except (TypeError, ValueError):
        return float(_DEFAULT_TIMEOUT_SEC)
    if not math.isfinite(timeout_sec) or timeout_sec <= 0:
        return float(_DEFAULT_TIMEOUT_SEC)
    return timeout_sec


def _now_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _artifact_ref(name: str, path: str, content: str) -> dict:
    return {
        "name": name,
        "path": path,
        "sha256": _sha256_text(content),
        "media_type": "text/plain",
        "size_bytes": len(content.encode("utf-8")),
    }


def _write_artifact(worktree_path: Path, relative_path: str, content: str) -> dict:
    target = worktree_path / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    name = Path(relative_path).name
    return _artifact_ref(name, relative_path, content)


def _build_subprocess_env(worktree_root: Path) -> dict[str, str]:
    env = dict(os.environ)
    repo_root = _repo_root()
    venv_root = load_config().toolchain_cache_root / "python" / "current"
    venv_bin = venv_root / ("Scripts" if os.name == "nt" else "bin")
    if venv_bin.exists():
        existing_path = env.get("PATH", "")
        env["PATH"] = str(venv_bin) if not existing_path else f"{venv_bin}{os.pathsep}{existing_path}"
        env["VIRTUAL_ENV"] = str(venv_root)
    existing_pythonpath = env.get("PYTHONPATH", "")
    repo_src = str(repo_root / "apps" / "orchestrator" / "src")
    env["PYTHONPATH"] = repo_src if not existing_pythonpath else f"{repo_src}{os.pathsep}{existing_pythonpath}"
    env["PYTHONDONTWRITEBYTECODE"] = env.get("PYTHONDONTWRITEBYTECODE", "1")
    env["CORTEXPILOT_LOG_SCHEMA_VERSION"] = env.get("CORTEXPILOT_LOG_SCHEMA_VERSION", "log_event.v2")
    return env


_STRICT_NONTRIVIAL_ENV = "CORTEXPILOT_ACCEPTANCE_STRICT_NONTRIVIAL"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _is_strict_nontrivial_enabled() -> bool:
    value = str(os.getenv(_STRICT_NONTRIVIAL_ENV, "")).strip().lower()
    if not value:
        return False
    return value in {"1", "true", "yes", "y", "on"}


def _coerce_must_pass(raw: object) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        value = raw.strip().lower()
        if value in {"0", "false", "no", "n", "off"}:
            return False
        if value in {"1", "true", "yes", "y", "on"}:
            return True
    if isinstance(raw, (int, float)):
        if raw == 0:
            return False
        if raw == 1:
            return True
    return True


def _normalize_command(command: str) -> str:
    text = command.strip().lower()
    if not text:
        return ""
    # Remove escaped control-whitespace so repeated normalization stays idempotent.
    text = re.sub(r"\\[\r\n\t\f\v ]+", " ", text)
    try:
        tokens = shlex.split(text, posix=False)
    except ValueError:
        tokens = text.split()
    normalized_tokens = [" ".join(token.split()) for token in tokens if token]
    normalized = " ".join(token for token in normalized_tokens if token)
    # shlex can materialize escaped-space fragments (e.g. "\\ ") that should
    # be normalized in the same pass to guarantee idempotence.
    normalized = re.sub(r"\\[\r\n\t\f\v ]+", " ", normalized)
    # Isolate balanced quoted fragments when control whitespace was collapsed
    # inside a token (e.g. '0\\x0c""0' -> '0 "" 0') so a second pass is stable.
    normalized = re.sub(r'(?<=\S)("(?:[^"\\]|\\.)*")', r" \1", normalized)
    normalized = re.sub(r'("(?:[^"\\]|\\.)*")(?=\S)', r"\1 ", normalized)
    normalized = re.sub(r"(?<=\S)('(?:[^'\\]|\\.)*')", r" \1", normalized)
    normalized = re.sub(r"('(?:[^'\\]|\\.)*')(?=\S)", r"\1 ", normalized)
    return " ".join(normalized.split())


def _is_trivial_acceptance_command(command: str) -> bool:
    normalized = _normalize_command(command)
    if not normalized:
        return True
    # Treat quoted-empty forms like '""' / "''" as trivial placeholder commands.
    if normalized.replace('"', "").replace("'", "").strip() == "":
        return True
    if normalized in _TRIVIAL_ACCEPTANCE_COMMANDS:
        return True
    if normalized.startswith("echo "):
        payload = normalized[5:].strip().strip('"').strip("'")
        if payload in {"", "ok", "hello", "pass", "success", "done", "1"}:
            return True
    return False


def _normalize_tests(test_items: Iterable[object]) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for item in test_items:
        if isinstance(item, str):
            normalized.append(
                {
                    "name": item,
                    "cmd": item,
                    "must_pass": True,
                    "timeout_sec": _DEFAULT_TIMEOUT_SEC,
                }
            )
            continue
        if isinstance(item, dict):
            cmd = item.get("cmd") or item.get("command")
            if isinstance(cmd, str) and cmd.strip():
                timeout_sec = _coerce_timeout_sec(item.get("timeout_sec", _DEFAULT_TIMEOUT_SEC))
                normalized.append(
                    {
                        "name": item.get("name") or cmd,
                        "cmd": cmd,
                        "must_pass": _coerce_must_pass(item.get("must_pass", True)),
                        "timeout_sec": timeout_sec,
                    }
                )
    return normalized


def _build_report(
    task_id: str,
    commands: list[dict[str, object]],
    artifacts: list[dict[str, object]],
    started_at: str,
    finished_at: str,
    status: str,
    failure: dict[str, str] | None,
) -> dict:
    report: dict[str, object] = {
        "task_id": task_id,
        "runner": {"role": "TEST_RUNNER", "agent_id": "tests_gate"},
        "started_at": started_at,
        "finished_at": finished_at,
        "status": status,
        "commands": commands,
        "artifacts": artifacts,
    }
    if failure:
        report["failure"] = failure
    return report


def run_acceptance_tests(
    worktree_path: Path,
    test_commands: Iterable[object],
    forbidden_actions: Iterable[str] | None = None,
    network_policy: str | None = None,
    policy_pack: str | None = None,
    strict_nontrivial: bool | None = None,
) -> dict:
    worktree_root = worktree_path.resolve()
    reports: list[dict] = []
    started_at = _now_ts()
    normalized = _normalize_tests(test_commands)
    if not normalized:
        report = _build_report(
            "",
            [],
            [],
            started_at,
            started_at,
            "ERROR",
            {"message": "acceptance_tests empty"},
        )
        reports.append(report)
        return {"ok": False, "reports": reports, "reason": "acceptance_tests empty"}
    forbidden = list(forbidden_actions or [])
    command_runs: list[dict[str, object]] = []
    artifacts: list[dict[str, object]] = []
    strict_nontrivial_enabled = (
        bool(strict_nontrivial) if strict_nontrivial is not None else _is_strict_nontrivial_enabled()
    )
    has_must_pass = any(bool(test.get("must_pass", True)) for test in normalized)
    if not has_must_pass:
        finished_at = _now_ts()
        report = _build_report(
            "",
            command_runs,
            artifacts,
            started_at,
            finished_at,
            "ERROR",
            {"message": "at least one acceptance test must set must_pass=true"},
        )
        reports.append(report)
        return {
            "ok": False,
            "reports": reports,
            "reason": "missing must_pass acceptance test",
        }

    for idx, test in enumerate(normalized):
        command = str(test.get("cmd", "")).strip()
        if not command:
            finished_at = _now_ts()
            report = _build_report("", command_runs, artifacts, started_at, finished_at, "ERROR", {"message": "empty command"})
            reports.append(report)
            return {"ok": False, "reports": reports, "reason": "empty command"}
        if strict_nontrivial_enabled and _is_trivial_acceptance_command(command):
            finished_at = _now_ts()
            report = _build_report(
                "",
                command_runs,
                artifacts,
                started_at,
                finished_at,
                "ERROR",
                {"message": "trivial acceptance command blocked"},
            )
            reports.append(report)
            return {
                "ok": False,
                "reports": reports,
                "reason": "trivial acceptance command blocked",
            }

        gate = validate_command(
            command,
            forbidden,
            network_policy=network_policy,
            policy_pack=policy_pack,
            repo_root=worktree_root,
        )
        if not gate.get("ok", False):
            finished_at = _now_ts()
            report = _build_report("", command_runs, artifacts, started_at, finished_at, "ERROR", {"message": "tool gate violation"})
            reports.append(report)
            return {
                "ok": False,
                "reports": reports,
                "reason": "tool gate violation",
                "gate": gate,
            }
        try:
            args = shlex.split(command)
        except ValueError as exc:
            finished_at = _now_ts()
            report = _build_report("", command_runs, artifacts, started_at, finished_at, "ERROR", {"message": f"invalid command: {exc}"})
            reports.append(report)
            return {
                "ok": False,
                "reports": reports,
                "reason": f"invalid command: {exc}",
            }
        timeout_sec = _coerce_timeout_sec(test.get("timeout_sec", _DEFAULT_TIMEOUT_SEC))
        cmd_start = time.perf_counter()
        launch_error = ""
        try:
            child_env = _build_subprocess_env(worktree_root)
            proc = subprocess.run(
                args,
                cwd=worktree_root,
                capture_output=True,
                text=True,
                timeout=timeout_sec if timeout_sec > 0 else None,
                env=child_env,
            )
            duration = max(time.perf_counter() - cmd_start, 0.0)
            exit_code = proc.returncode
            stdout_text = proc.stdout or ""
            stderr_text = proc.stderr or ""
        except subprocess.TimeoutExpired as exc:
            duration = max(time.perf_counter() - cmd_start, 0.0)
            exit_code = 124
            stdout_text = exc.stdout or ""
            stderr_text = exc.stderr or ""
        except (OSError, ValueError) as exc:
            duration = max(time.perf_counter() - cmd_start, 0.0)
            exit_code = 127
            stdout_text = ""
            launch_error = f"test launch failed: {exc}"
            stderr_text = launch_error

        stdout_path = f"tests/stdout_{idx}.log"
        stderr_path = f"tests/stderr_{idx}.log"
        stdout_artifact = _write_artifact(worktree_root, stdout_path, stdout_text)
        stderr_artifact = _write_artifact(worktree_root, stderr_path, stderr_text)
        artifacts.extend([stdout_artifact, stderr_artifact])

        command_runs.append(
            {
                "name": str(test.get("name") or command),
                "cmd_argv": args,
                "must_pass": _coerce_must_pass(test.get("must_pass", True)),
                "timeout_sec": timeout_sec,
                "exit_code": exit_code,
                "duration_sec": duration,
                "cwd": str(worktree_root),
                "stdout": stdout_artifact,
                "stderr": stderr_artifact,
            }
        )

        if launch_error:
            finished_at = _now_ts()
            report = _build_report(
                "",
                command_runs,
                artifacts,
                started_at,
                finished_at,
                "ERROR",
                {"message": launch_error},
            )
            reports.append(report)
            return {"ok": False, "reports": reports, "reason": "test launch failed"}

        if exit_code == 124:
            finished_at = _now_ts()
            report = _build_report(
                "",
                command_runs,
                artifacts,
                started_at,
                finished_at,
                "ERROR",
                {"message": "test timeout"},
            )
            reports.append(report)
            return {"ok": False, "reports": reports, "reason": "test timeout"}

        if exit_code != 0 and _coerce_must_pass(test.get("must_pass", True)):
            finished_at = _now_ts()
            report = _build_report("", command_runs, artifacts, started_at, finished_at, "FAIL", {"message": "test failed"})
            reports.append(report)
            return {"ok": False, "reports": reports, "reason": "test failed"}

    finished_at = _now_ts()
    report = _build_report("", command_runs, artifacts, started_at, finished_at, "PASS", None)
    reports.append(report)
    return {"ok": True, "reports": reports, "reason": ""}


def run_tests_gate(run_id: str, worktree: Path, tests: list[str]) -> dict:
    return run_acceptance_tests(worktree, tests)


# -------------------------------------------------------------------
# Evals gate (Promptfoo)
# -------------------------------------------------------------------


def run_evals_gate(
    repo_root: Path,
    worktree_path: Path,
    forbidden_actions: Iterable[str] | None = None,
    network_policy: str | None = None,
    policy_pack: str | None = None,
) -> dict:
    script_path = repo_root / "scripts" / "run_evals.sh"
    if not script_path.exists():
        return {"ok": False, "reason": "eval script missing", "command": str(script_path)}

    relative = script_path.relative_to(repo_root)
    command = f"bash {relative}"
    gate = validate_command(
        command,
        forbidden_actions or [],
        network_policy=network_policy,
        policy_pack=policy_pack,
        repo_root=repo_root,
    )
    if not gate.get("ok", False):
        return {"ok": False, "reason": "tool gate violation", "gate": gate, "command": command}

    started_at = _now_ts()
    cmd_start = time.perf_counter()
    try:
        proc = subprocess.run(
            shlex.split(command),
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=_DEFAULT_TIMEOUT_SEC,
        )
        exit_code = proc.returncode
        stdout_text = proc.stdout or ""
        stderr_text = proc.stderr or ""
    except subprocess.TimeoutExpired as exc:
        exit_code = 124
        stdout_text = exc.stdout or ""
        stderr_text = exc.stderr or ""

    duration = max(time.perf_counter() - cmd_start, 0.0)
    finished_at = _now_ts()

    report = {
        "status": "PASS" if exit_code == 0 else "FAIL",
        "command": command,
        "exit_code": exit_code,
        "duration_sec": duration,
        "started_at": started_at,
        "finished_at": finished_at,
        "stdout": stdout_text,
        "stderr": stderr_text,
    }
    return {"ok": exit_code == 0, "reason": "" if exit_code == 0 else "evals failed", "report": report}
