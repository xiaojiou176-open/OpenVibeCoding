#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import threading
from pathlib import Path
from typing import Any

try:
    from scripts.host_process_safety import terminate_tracked_child
except ModuleNotFoundError:
    from host_process_safety import terminate_tracked_child


def run_codex_once(
    *,
    prompt: str,
    md_path: Path,
    cwd: Path,
    codex_bin: str,
    model: str,
    profile: str,
    timeout_sec: int,
    dry_run: bool,
    print_lock: threading.Lock,
) -> tuple[bool, str, dict[str, Any]]:
    cmd: list[str] = [
        codex_bin,
        "exec",
        "--skip-git-repo-check",
        "--cd",
        str(cwd),
        "--sandbox",
        "read-only",
        "--output-last-message",
        str(md_path),
    ]
    if model:
        cmd.extend(["--model", model])
    if profile:
        cmd.extend(["--profile", profile])
    cmd.append(prompt)

    if dry_run:
        with print_lock:
            print(f"[DRY-RUN] {' '.join(cmd[:8])} ... <PROMPT>")
        return True, "dry-run", {"provider": "codex", "dry_run": True}

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout, stderr = process.communicate(timeout=max(30, timeout_sec))
    except subprocess.TimeoutExpired:
        termination_signal = terminate_tracked_child(
            process,
            term_timeout_sec=5,
            kill_timeout_sec=3,
        )
        return (
            False,
            f"timeout>{timeout_sec}s",
            {
                "provider": "codex",
                "error_type": "timeout",
                "terminated_tracked_child": True,
                "termination_signal": termination_signal,
            },
        )
    except FileNotFoundError:
        return (
            False,
            f"codex binary not found: {codex_bin}",
            {"provider": "codex", "error_type": "binary_not_found"},
        )
    except Exception as exc:  # noqa: BLE001
        return (
            False,
            f"unexpected error: {exc}",
            {"provider": "codex", "error_type": "unexpected", "error": str(exc)},
        )

    meta: dict[str, Any] = {
        "provider": "codex",
        "returncode": process.returncode,
        "stderr_tail": (stderr or "").strip().splitlines()[-1:] if stderr else [],
        "stdout_tail": (stdout or "").strip().splitlines()[-1:] if stdout else [],
    }

    if process.returncode != 0:
        err_lines = (stderr or "").strip().splitlines()
        msg = err_lines[-1] if err_lines else f"returncode={process.returncode}"
        return False, msg, meta

    if not md_path.exists() or not md_path.read_text(encoding="utf-8").strip():
        return False, "codex returned empty markdown", meta

    return True, "ok", meta
