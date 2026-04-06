from __future__ import annotations

import subprocess
from typing import Any


def _wait_for_exit(proc: subprocess.Popen[Any], timeout_sec: float) -> bool:
    if proc.poll() is not None:
        return True
    try:
        proc.wait(timeout=max(0.1, float(timeout_sec)))
    except subprocess.TimeoutExpired:
        return False
    return True


def terminate_tracked_child(
    proc: subprocess.Popen[Any] | None,
    *,
    term_timeout_sec: float = 5.0,
    kill_timeout_sec: float = 3.0,
) -> str:
    """Terminate only the recorded child handle; never escalate to process groups."""
    if proc is None:
        return "missing_child"
    if proc.poll() is not None:
        return "already_exited"
    if not isinstance(getattr(proc, "pid", None), int) or int(proc.pid) <= 0:
        return "invalid_pid"

    try:
        proc.terminate()
    except ProcessLookupError:
        return "already_exited"
    except OSError:
        # Keep the cleanup path fail-closed to the tracked child handle:
        # if terminate() itself errors, we still attempt a direct kill() next.
        pass

    if _wait_for_exit(proc, term_timeout_sec):
        return "SIGTERM"

    try:
        proc.kill()
    except ProcessLookupError:
        return "already_exited"
    except Exception:
        return "kill_failed"

    if _wait_for_exit(proc, kill_timeout_sec):
        return "SIGKILL"
    return "still_running"
