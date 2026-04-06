from __future__ import annotations

import shlex
import subprocess
import time
from pathlib import Path
from typing import Any

from cortexpilot_orch.gates.tool_gate import validate_command

_ADAPTER_ALIASES = {
    "aider": "aider",
    "continue": "continue",
    "open_interpreter": "open_interpreter",
    "open-interpreter": "open_interpreter",
}

_ADAPTER_BINARIES = {
    "aider": "aider",
    "continue": "continue",
    "open_interpreter": "open-interpreter",
}

_ADAPTER_EXEC_NAMES = {
    "aider": {"aider"},
    "continue": {"continue"},
    "open_interpreter": {"open-interpreter", "open_interpreter"},
}

_DEFAULT_TIMEOUT_SEC = 120.0
_MAX_TIMEOUT_SEC = 3600.0


def normalize_adapter_tool(tool_name: str) -> str | None:
    token = str(tool_name).strip().lower()
    if not token:
        return None
    return _ADAPTER_ALIASES.get(token)


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _ensure_result_shape(
    *,
    adapter: str | None,
    command: str = "",
    ok: bool = False,
    exit_code: int | None = None,
    stdout: str = "",
    stderr: str = "",
    error: str = "",
    reason: str = "",
    duration_ms: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": ok,
        "adapter": adapter,
        "command": command,
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "error": error,
        "reason": reason,
    }
    if duration_ms is not None:
        payload["duration_ms"] = duration_ms
    return payload


def _normalize_shell_policy(contract: dict[str, Any] | None) -> str:
    if not isinstance(contract, dict):
        return "deny"
    permissions = contract.get("tool_permissions") if isinstance(contract.get("tool_permissions"), dict) else {}
    raw = permissions.get("shell")
    normalized = str(raw).strip().lower()
    if normalized in {"allow", "on-request", "untrusted", "on-failure"}:
        return "allow"
    if normalized in {"deny", "never"}:
        return "deny"
    return "deny"


def _normalize_network_policy(contract: dict[str, Any] | None) -> str:
    if not isinstance(contract, dict):
        return "deny"
    permissions = contract.get("tool_permissions") if isinstance(contract.get("tool_permissions"), dict) else {}
    raw = permissions.get("network")
    normalized = str(raw).strip().lower()
    if normalized in {"deny", "on-request", "allow"}:
        return normalized
    return "deny"


def _forbidden_actions(contract: dict[str, Any] | None) -> list[str]:
    if not isinstance(contract, dict):
        return []
    actions = contract.get("forbidden_actions")
    if not isinstance(actions, list):
        return []
    return [str(item).strip() for item in actions if str(item).strip()]


def _extract_expected_run_id(contract: dict[str, Any] | None) -> str:
    if not isinstance(contract, dict):
        return ""
    candidate = contract.get("run_id")
    if isinstance(candidate, str) and candidate.strip():
        return candidate.strip()
    log_refs = contract.get("log_refs")
    if isinstance(log_refs, dict):
        bound_run_id = log_refs.get("run_id")
        if isinstance(bound_run_id, str) and bound_run_id.strip():
            return bound_run_id.strip()
    return ""


def _extract_expected_task_id(contract: dict[str, Any] | None) -> str:
    if not isinstance(contract, dict):
        return ""
    candidate = contract.get("task_id")
    if isinstance(candidate, str) and candidate.strip():
        return candidate.strip()
    return ""


def _validate_request_binding(payload: dict[str, Any], contract: dict[str, Any] | None) -> str:
    expected_run_id = _extract_expected_run_id(contract)
    expected_task_id = _extract_expected_task_id(contract)
    request_run_id = str(payload.get("run_id", "") or "").strip()
    request_task_id = str(payload.get("task_id", "") or "").strip()
    if expected_run_id and request_run_id and request_run_id != expected_run_id:
        return "run_id mismatch"
    if expected_task_id and request_task_id and request_task_id != expected_task_id:
        return "task_id mismatch"
    return ""


def _resolve_timeout_sec(payload: dict[str, Any], contract: dict[str, Any] | None) -> float:
    candidates: list[Any] = [payload.get("timeout_sec"), payload.get("timeout")]
    if isinstance(contract, dict) and isinstance(contract.get("timeout_retry"), dict):
        candidates.append(contract.get("timeout_retry", {}).get("timeout_sec"))
    for value in candidates:
        if value is None:
            continue
        try:
            timeout = float(value)
        except (TypeError, ValueError):
            continue
        if timeout <= 0:
            continue
        return min(timeout, _MAX_TIMEOUT_SEC)
    return _DEFAULT_TIMEOUT_SEC


def _resolve_cwd(payload: dict[str, Any], repo_root: Path) -> tuple[Path | None, str]:
    raw = payload.get("cwd")
    if raw is None or not str(raw).strip():
        return repo_root, ""
    candidate = Path(str(raw).strip())
    if not candidate.is_absolute():
        candidate = (repo_root / candidate).resolve()
    else:
        candidate = candidate.resolve()
    if not _is_within(candidate, repo_root):
        return None, "cwd outside repo"
    if not candidate.exists():
        return None, "cwd not found"
    if not candidate.is_dir():
        return None, "cwd is not a directory"
    return candidate, ""


def _parse_args(payload: dict[str, Any]) -> list[str]:
    raw_args = payload.get("args")
    if raw_args is None:
        raw_args = payload.get("argv", [])
    if isinstance(raw_args, str):
        try:
            return shlex.split(raw_args)
        except ValueError:
            return []
    if not isinstance(raw_args, list):
        return []
    args: list[str] = []
    for item in raw_args:
        token = str(item).strip()
        if token:
            args.append(token)
    return args


def _build_command(adapter: str, payload: dict[str, Any]) -> tuple[str, str]:
    for key in ("command", "cmd"):
        raw = payload.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip(), ""
        if isinstance(raw, list):
            tokens = [str(item).strip() for item in raw if str(item).strip()]
            if tokens:
                return shlex.join(tokens), ""
    binary = _ADAPTER_BINARIES[adapter]
    tokens = [binary] + _parse_args(payload)
    return shlex.join(tokens), ""


def _validate_adapter_exec_name(adapter: str, command: str) -> str:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return "invalid command"
    if not tokens:
        return "invalid command"
    executable = Path(tokens[0]).name.strip().lower()
    allowed = _ADAPTER_EXEC_NAMES.get(adapter, set())
    if executable not in allowed:
        return "adapter command mismatch"
    return ""


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def execute_mcp_adapter(
    tool_name: str,
    payload: dict[str, Any] | None,
    contract: dict[str, Any] | None,
    *,
    repo_root: Path,
) -> dict[str, Any]:
    start = time.monotonic()
    normalized = normalize_adapter_tool(tool_name)
    if normalized is None:
        reason = "unsupported adapter tool"
        return _ensure_result_shape(
            adapter=None,
            command="",
            ok=False,
            error=reason,
            reason=reason,
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    request = payload if isinstance(payload, dict) else {}
    binding_error = _validate_request_binding(request, contract)
    if binding_error:
        return _ensure_result_shape(
            adapter=normalized,
            command="",
            ok=False,
            error=binding_error,
            reason=binding_error,
            duration_ms=int((time.monotonic() - start) * 1000),
        )
    shell_policy = _normalize_shell_policy(contract)
    if shell_policy != "allow":
        reason = "shell tool denied"
        return _ensure_result_shape(
            adapter=normalized,
            command="",
            ok=False,
            error=reason,
            reason=reason,
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    command, command_error = _build_command(normalized, request)
    if command_error:
        return _ensure_result_shape(
            adapter=normalized,
            command="",
            ok=False,
            error=command_error,
            reason=command_error,
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    mismatch_reason = _validate_adapter_exec_name(normalized, command)
    if mismatch_reason:
        return _ensure_result_shape(
            adapter=normalized,
            command=command,
            ok=False,
            error=mismatch_reason,
            reason=mismatch_reason,
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    cwd, cwd_error = _resolve_cwd(request, repo_root)
    if cwd_error:
        return _ensure_result_shape(
            adapter=normalized,
            command=command,
            ok=False,
            error=cwd_error,
            reason=cwd_error,
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    gate = validate_command(
        command,
        _forbidden_actions(contract),
        network_policy=_normalize_network_policy(contract),
        policy_pack=str(request.get("policy_pack", "")).strip() or None,
        repo_root=repo_root,
    )
    if not gate.get("ok"):
        reason = str(gate.get("reason", "")).strip() or "command blocked by gate"
        return _ensure_result_shape(
            adapter=normalized,
            command=command,
            ok=False,
            error=reason,
            reason=reason,
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    timeout_sec = _resolve_timeout_sec(request, contract)
    try:
        process = subprocess.run(
            shlex.split(command),
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        reason = "adapter command timeout"
        return _ensure_result_shape(
            adapter=normalized,
            command=command,
            ok=False,
            exit_code=None,
            stdout=_coerce_text(exc.stdout),
            stderr=_coerce_text(exc.stderr),
            error=reason,
            reason=reason,
            duration_ms=int((time.monotonic() - start) * 1000),
        )
    except Exception as exc:  # noqa: BLE001
        reason = "adapter command execution failed"
        return _ensure_result_shape(
            adapter=normalized,
            command=command,
            ok=False,
            exit_code=None,
            stdout="",
            stderr="",
            error=str(exc),
            reason=reason,
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    ok = process.returncode == 0
    if ok:
        error = ""
        reason = ""
    else:
        reason = "adapter command exited with non-zero code"
        stderr_text = _coerce_text(process.stderr).strip()
        error = stderr_text or reason
    return _ensure_result_shape(
        adapter=normalized,
        command=command,
        ok=ok,
        exit_code=process.returncode,
        stdout=_coerce_text(process.stdout),
        stderr=_coerce_text(process.stderr),
        error=error,
        reason=reason,
        duration_ms=int((time.monotonic() - start) * 1000),
    )
