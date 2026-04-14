from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from openvibecoding_orch.contract.validator import ContractValidator
from openvibecoding_orch.observability.codex_event_parser import parse_codex_event_line
from openvibecoding_orch.observability.tracer import trace_span
from openvibecoding_orch.runners import common as runner_common
from openvibecoding_orch.store.run_store import RunStore
from openvibecoding_orch.transport.codex_profile_pool import pick_profile


def _is_task_result(payload: dict[str, Any]) -> bool:
    required = {"task_id", "status"}
    return required.issubset(payload.keys())


def _resolve_resume_id(contract: dict[str, Any]) -> str | None:
    return runner_common.resolve_assigned_thread_id(contract, "codex_thread_id")


def _normalize_status(value: Any, fallback: str) -> str:
    return runner_common.normalize_status(value, fallback)


def _codex_allowed(contract: dict[str, Any]) -> bool:
    return runner_common.mcp_tool_allowed(contract, "codex")


def _extract_thread_id(payload: dict[str, Any]) -> str | None:
    keys = ("thread_id", "threadId")
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    for container in ("payload", "msg", "context", "data"):
        nested = payload.get(container)
        if isinstance(nested, dict):
            for key in keys:
                value = nested.get(key)
                if isinstance(value, str) and value.strip():
                    return value
    return None


def _extract_session_id(payload: dict[str, Any]) -> str | None:
    keys = ("session_id", "sessionId")
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    for container in ("payload", "msg", "context", "data"):
        nested = payload.get(container)
        if isinstance(nested, dict):
            for key in keys:
                value = nested.get(key)
                if isinstance(value, str) and value.strip():
                    return value
    return None


def _codex_flags(contract: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    tool_permissions = contract.get("tool_permissions")
    if not isinstance(tool_permissions, dict):
        return flags
    filesystem = tool_permissions.get("filesystem")
    if filesystem in {"read-only", "workspace-write"}:
        flags.extend(["--sandbox", filesystem])
    return flags


def _resolve_profile() -> str | None:
    profile = os.getenv("OPENVIBECODING_CODEX_PROFILE", "").strip()
    if profile:
        return profile
    return pick_profile()


def _resolve_model() -> str | None:
    model = os.getenv("OPENVIBECODING_CODEX_MODEL", "").strip()
    if model:
        return model
    return None


def _use_output_schema() -> bool:
    raw = os.getenv("OPENVIBECODING_CODEX_USE_OUTPUT_SCHEMA", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _exec_timeout_sec() -> int:
    raw = os.getenv("OPENVIBECODING_CODEX_EXEC_TIMEOUT_SEC", "300").strip()
    try:
        value = int(raw)
    except ValueError:
        value = 300
    return max(value, 30)


def _extract_task_result_payload(payload: dict[str, Any], task_id: str) -> dict[str, Any] | None:
    if _is_task_result(payload):
        return payload

    status = payload.get("status")
    summary = payload.get("summary")
    if isinstance(status, str) and isinstance(summary, str):
        candidate: dict[str, Any] = {
            "task_id": payload.get("task_id") or task_id,
            "status": status,
            "summary": summary,
        }
        evidence_refs = payload.get("evidence_refs")
        if isinstance(evidence_refs, dict):
            candidate["evidence_refs"] = evidence_refs
        failure = payload.get("failure")
        if isinstance(failure, dict) or failure is None:
            candidate["failure"] = failure
        return candidate

    item = payload.get("item")
    if not isinstance(item, dict):
        return None
    text = item.get("text")
    if not isinstance(text, str):
        return None
    text = text.strip()
    if not text.startswith("{"):
        return None
    try:
        embedded = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(embedded, dict):
        return None
    embedded_status = embedded.get("status")
    if not isinstance(embedded_status, str) or not embedded_status.strip():
        return None

    candidate = {
        "task_id": embedded.get("task_id") or task_id,
        "status": embedded_status,
        "summary": embedded.get("summary") if isinstance(embedded.get("summary"), str) else "",
        "evidence_refs": {"agent_message": embedded},
    }
    failure = embedded.get("failure")
    if isinstance(failure, dict) or failure is None:
        candidate["failure"] = failure
    else:
        errors = embedded.get("errors")
        if isinstance(errors, list) and errors:
            first = errors[0]
            if isinstance(first, dict) and isinstance(first.get("message"), str):
                candidate["failure"] = {"message": first.get("message")}
    return candidate


class CodexRunner:
    def __init__(self, run_store: RunStore) -> None:
        self._store = run_store

    @trace_span("codex_runner.run_contract")
    def run_contract(
        self,
        contract: dict[str, Any],
        worktree_path: Path,
        schema_path: Path,
        mock_mode: bool = False,
    ) -> dict[str, Any]:
        run_id = runner_common.resolve_run_id(contract)
        instruction = runner_common.extract_instruction(contract, worktree_path)
        if not instruction:
            return runner_common.failure_result(contract, "missing instruction")
        mcp_only = os.getenv("OPENVIBECODING_MCP_ONLY", "1").strip().lower() in {"1", "true", "yes"}
        allow_codex = os.getenv("OPENVIBECODING_ALLOW_CODEX_EXEC", "").strip().lower() in {"1", "true", "yes"}
        if mcp_only and not mock_mode and not allow_codex:
            return runner_common.failure_result(contract, "mcp-only enforced: codex exec blocked")

        tool_permissions = contract.get("tool_permissions", {}) if isinstance(contract, dict) else {}
        shell_policy = str(tool_permissions.get("shell", "")).strip().lower()
        if shell_policy == "deny":
            self._store.append_event(
                run_id,
                {
                    "level": "ERROR",
                    "event": "policy_violation",
                    "run_id": run_id,
                    "meta": {"reason": "shell tool denied", "path": "tool_permissions.shell"},
                },
            )
            return runner_common.failure_result(contract, "shell tool denied")

        if not runner_common.mcp_tool_allowed(contract, "codex"):
            self._store.append_event(
                run_id,
                {
                    "level": "ERROR",
                    "event": "MCP_TOOL_DENIED",
                    "run_id": run_id,
                    "meta": {"tool": "codex"},
                },
            )
            return runner_common.failure_result(contract, "codex mcp tool not allowed")

        schema_path, validation_error = runner_common.validate_contract_schema(
            contract,
            schema_path,
            self._store,
            run_id,
            validator_cls=ContractValidator,
        )
        if validation_error:
            return validation_error

        if mock_mode:
            return runner_common.execute_mock_contract(
                contract,
                tool_permissions,
                instruction,
                worktree_path,
                self._store,
                run_id,
                "CODEX_MOCK_EVENT",
            )

        profile = _resolve_profile()
        model = _resolve_model()
        use_output_schema = _use_output_schema()
        resume_id = _resolve_resume_id(contract)
        cmd = ["codex"]
        if profile:
            cmd.extend(["--profile", profile])
        if resume_id:
            cmd.extend(
                [
                    "exec",
                    "resume",
                    resume_id,
                    "--json",
                ]
            )
        else:
            cmd.extend(
                [
                    "exec",
                    "--json",
                ]
            )
        if use_output_schema:
            cmd.extend(["--output-schema", str(schema_path)])
        else:
            self._store.append_event(
                run_id,
                {
                    "level": "WARN",
                    "event": "CODEX_OUTPUT_SCHEMA_DISABLED",
                    "run_id": run_id,
                    "meta": {
                        "schema_path": str(schema_path),
                        "env": "OPENVIBECODING_CODEX_USE_OUTPUT_SCHEMA",
                    },
                },
            )
        if model:
            cmd.extend(["--model", model])
        cmd.extend(_codex_flags(contract))
        cmd.append(instruction)
        self._store.append_event(
            run_id,
            {
                "level": "INFO",
                "event": "CODEX_CMD",
                "run_id": run_id,
                "meta": {"cmd": cmd, "cwd": str(worktree_path)},
            },
        )

        proc = subprocess.Popen(
            cmd,
            cwd=worktree_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        exec_timeout = _exec_timeout_sec()
        if hasattr(proc, "communicate"):
            try:
                stdout_text, stderr_text = proc.communicate(timeout=exec_timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout_text, stderr_text = proc.communicate()
                return runner_common.failure_result(
                    contract,
                    f"codex exec timeout after {exec_timeout}s",
                    {
                        "stdout": (stdout_text or "")[-2000:],
                        "stderr": (stderr_text or "")[-2000:],
                    },
                )
        else:
            stdout_stream = getattr(proc, "stdout", None)
            stderr_stream = getattr(proc, "stderr", None)
            stdout_text = stdout_stream.read() if stdout_stream is not None else ""
            stderr_text = stderr_stream.read() if stderr_stream is not None else ""
            wait_fn = getattr(proc, "wait", None)
            if callable(wait_fn):
                wait_fn()

        final_result: dict[str, Any] | None = None
        task_id = contract.get("task_id", "task")
        transcript_lines: list[str] = []
        thread_id: str | None = None
        session_id: str | None = None
        codex_version = os.getenv("OPENVIBECODING_CODEX_VERSION", "").strip() or None
        for raw_line in (stdout_text or "").splitlines():
            line = raw_line.rstrip("\n")
            if not line.strip():
                continue
            parsed = parse_codex_event_line(line, codex_version=codex_version)
            self._store.append_codex_event(run_id, task_id, parsed.to_codex_jsonl())
            self._store.append_event(
                run_id,
                {
                    "level": "INFO",
                    "event": "CODEX_RAW_EVENT",
                    "run_id": run_id,
                    "meta": parsed.to_event_context(),
                },
            )
            if parsed.is_json:
                payload = parsed.payload
                self._store.append_event(
                    run_id,
                    {
                        "level": "INFO",
                        "event": "CODEX_STDOUT",
                        "run_id": run_id,
                        "meta": payload,
                    },
                )
                transcript_lines.append(json.dumps(payload, ensure_ascii=False))
                thread_id = thread_id or parsed.thread_id or _extract_thread_id(payload)
                session_id = session_id or parsed.session_id or _extract_session_id(payload)
                task_payload = _extract_task_result_payload(payload, task_id)
                if task_payload is not None:
                    final_result = task_payload
            else:
                self._store.append_event(
                    run_id,
                    {
                        "level": "ERROR",
                        "event": "CODEX_STDERR",
                        "run_id": run_id,
                        "meta": {"stream": "stdout", "line": line},
                    },
                )
                transcript_lines.append(line)

        stderr_text = stderr_text or ""
        if stderr_text.strip():
            self._store.append_event(
                run_id,
                {
                    "level": "ERROR",
                    "event": "CODEX_STDERR",
                    "run_id": run_id,
                    "meta": {"stream": "stderr", "text": stderr_text.strip()},
                },
            )

        exit_code = getattr(proc, "returncode", None)
        if exit_code is None:
            wait_fn = getattr(proc, "wait", None)
            exit_code = wait_fn() if callable(wait_fn) else 0
        if exit_code != 0:
            return runner_common.failure_result(
                contract,
                f"codex exec failed with {exit_code}",
                {"stderr": stderr_text.strip()},
            )

        if final_result is None:
            return runner_common.failure_result(contract, "missing task result in codex output")

        if transcript_lines:
            transcript = "\n".join(transcript_lines)
            self._store.write_codex_transcript(run_id, task_id, transcript)
        if thread_id:
            self._store.write_codex_thread_id(run_id, task_id, thread_id)
        if session_id or thread_id:
            self._store.write_codex_session_map(
                run_id,
                {
                    "run_id": run_id,
                    "task_id": task_id,
                    "codex_session_id": session_id or "",
                    "codex_thread_id": thread_id or "",
                },
            )
        evidence_refs = runner_common.build_evidence_refs(thread_id, session_id)
        return runner_common.coerce_task_result(final_result, contract, evidence_refs, "SUCCESS")


def run_contract(
    run_store: RunStore,
    contract: dict[str, Any],
    worktree_path: Path,
    schema_path: Path,
    mock_mode: bool = False,
) -> dict[str, Any]:
    runner = CodexRunner(run_store)
    return runner.run_contract(contract, worktree_path, schema_path, mock_mode=mock_mode)
