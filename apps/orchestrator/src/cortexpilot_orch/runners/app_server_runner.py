from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from cortexpilot_orch.contract.validator import ContractValidator
from cortexpilot_orch.observability.tracer import trace_span
from cortexpilot_orch.runners import common as runner_common
from cortexpilot_orch.store.run_store import RunStore
from cortexpilot_orch.transport.mcp_jsonl import JsonlStream, send_json


def _codex_allowed(contract: dict[str, Any]) -> bool:
    return runner_common.mcp_tool_allowed(contract, "codex")


def _sandbox_policy(contract: dict[str, Any], worktree_path: Path) -> dict[str, Any] | None:
    tool_permissions = contract.get("tool_permissions")
    if not isinstance(tool_permissions, dict):
        return None
    filesystem = tool_permissions.get("filesystem")
    if filesystem not in {"read-only", "workspace-write", "danger-full-access"}:
        return None
    mapping = {
        "read-only": "readOnly",
        "workspace-write": "workspaceWrite",
        "danger-full-access": "dangerFullAccess",
    }
    policy: dict[str, Any] = {"type": mapping[filesystem]}
    if filesystem == "workspace-write":
        policy["writableRoots"] = [str(worktree_path)]
    network_policy = str(tool_permissions.get("network", "deny")).strip().lower()
    policy["networkAccess"] = network_policy == "allow"
    return policy


def _approval_policy(contract: dict[str, Any]) -> str | None:
    tool_permissions = contract.get("tool_permissions")
    if not isinstance(tool_permissions, dict):
        return None
    shell_policy = tool_permissions.get("shell")
    if shell_policy == "never":
        return "never"
    if shell_policy == "on-request":
        return "onRequest"
    if shell_policy == "untrusted":
        return "untrusted"
    return None


def _build_turn_params(
    contract: dict[str, Any],
    instruction: str,
    worktree_path: Path,
    schema_path: Path,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "input": [{"type": "text", "text": instruction}],
        "cwd": str(worktree_path),
    }
    policy = _sandbox_policy(contract, worktree_path)
    if policy:
        params["sandboxPolicy"] = policy
    approval = _approval_policy(contract)
    if approval:
        params["approvalPolicy"] = approval
    model = os.getenv("CORTEXPILOT_CODEX_MODEL", "").strip()
    if model:
        params["model"] = model
    if schema_path.exists():
        try:
            params["outputSchema"] = json.loads(schema_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return params


def _extract_agent_delta(payload: dict[str, Any]) -> str:
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    for key in ("delta", "text", "textDelta"):
        value = params.get(key)
        if isinstance(value, str):
            return value
    return ""


def _extract_agent_message(payload: dict[str, Any]) -> str | None:
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    item = params.get("item") if isinstance(params.get("item"), dict) else None
    if not item:
        return None
    if item.get("type") != "agentMessage":
        return None
    text = item.get("text")
    return text if isinstance(text, str) else None


def _extract_turn_status(payload: dict[str, Any]) -> tuple[str | None, str | None]:
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    turn = params.get("turn") if isinstance(params.get("turn"), dict) else None
    if not turn:
        return None, None
    status = turn.get("status") if isinstance(turn.get("status"), str) else None
    error = turn.get("error") if isinstance(turn.get("error"), dict) else None
    message = error.get("message") if isinstance(error, dict) else None
    return status, message if isinstance(message, str) else None


# -------------------------------------------------------------------
# Runner
# -------------------------------------------------------------------

class AppServerRunner:
    def __init__(self, run_store: RunStore) -> None:
        self._store = run_store

    @trace_span("app_server_runner.run_contract")
    def run_contract(
        self,
        contract: dict[str, Any],
        worktree_path: Path,
        schema_path: Path,
        mock_mode: bool = False,
    ) -> dict[str, Any]:
        run_id = runner_common.resolve_run_id(contract)
        instruction = runner_common.extract_instruction(contract)
        if not instruction:
            return runner_common.failure_result(contract, "missing instruction")

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
                    "event": "APP_SERVER_DENIED",
                    "run_id": run_id,
                    "meta": {"tool": "codex"},
                },
            )
            return runner_common.failure_result(contract, "codex tool not allowed")

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
                "APP_SERVER_MOCK_EVENT",
            )

        cmd = ["codex", "app-server"]
        self._store.append_event(
            run_id,
            {
                "level": "INFO",
                "event": "APP_SERVER_CMD",
                "run_id": run_id,
                "meta": {"cmd": cmd, "cwd": str(worktree_path)},
            },
        )
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=worktree_path,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except Exception as exc:  # noqa: BLE001
            return runner_common.failure_result(contract, "app-server spawn failed", {"error": str(exc)})

        try:
            stream = JsonlStream(proc)

            transcript_lines: list[str] = []
            agent_parts: list[str] = []
            thread_id: str | None = None
            task_id = contract.get("task_id", "task")

            send_json(
                proc,
                {
                    "method": "initialize",
                    "id": 0,
                    "params": {
                        "clientInfo": {"name": "cortexpilot_orch", "title": "CortexPilot Orchestrator", "version": "0.1.0"}
                    },
                },
            )

            init_deadline = time.monotonic() + 10.0
            init_ok = False
            while time.monotonic() < init_deadline:
                line = stream.read_line(0.2)
                if not line:
                    continue
                transcript_lines.append(line.rstrip("\n"))
                self._store.append_codex_event(run_id, task_id, line)
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if payload.get("id") == 0:
                    if "error" in payload:
                        return runner_common.failure_result(contract, "app-server initialize failed", {"error": payload.get("error")})
                    init_ok = True
                    break
            if not init_ok:
                return runner_common.failure_result(contract, "app-server initialize timeout")

            send_json(proc, {"method": "initialized", "params": {}})

            resume_thread = runner_common.resolve_assigned_thread_id(contract, "codex_thread_id")
            if resume_thread:
                send_json(proc, {"method": "thread/resume", "id": 1, "params": {"threadId": resume_thread}})
            else:
                thread_params: dict[str, Any] = {"cwd": str(worktree_path)}
                model = os.getenv("CORTEXPILOT_CODEX_MODEL", "").strip()
                if model:
                    thread_params["model"] = model
                approval = _approval_policy(contract)
                if approval:
                    thread_params["approvalPolicy"] = approval
                policy = _sandbox_policy(contract, worktree_path)
                if policy:
                    thread_params["sandboxPolicy"] = policy
                send_json(proc, {"method": "thread/start", "id": 1, "params": thread_params})

            thread_deadline = time.monotonic() + 15.0
            while time.monotonic() < thread_deadline:
                line = stream.read_line(0.2)
                if not line:
                    continue
                transcript_lines.append(line.rstrip("\n"))
                self._store.append_codex_event(run_id, task_id, line)
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if payload.get("id") == 1:
                    if "error" in payload:
                        return runner_common.failure_result(contract, "app-server thread start failed", {"error": payload.get("error")})
                    result = payload.get("result", {}) if isinstance(payload.get("result"), dict) else {}
                    thread = result.get("thread", {}) if isinstance(result.get("thread"), dict) else {}
                    thread_id = thread.get("id") if isinstance(thread.get("id"), str) else resume_thread
                    break
            if not thread_id:
                return runner_common.failure_result(contract, "app-server thread id missing")

            turn_params = _build_turn_params(contract, instruction, worktree_path, schema_path)
            turn_params["threadId"] = thread_id
            send_json(proc, {"method": "turn/start", "id": 2, "params": turn_params})

            timeout_sec = float(contract.get("timeout_retry", {}).get("timeout_sec", 900))
            deadline = time.monotonic() + max(timeout_sec, 1)
            turn_status = None
            turn_error = None

            while time.monotonic() < deadline:
                line = stream.read_line(0.5)
                if line is None:
                    if proc.poll() is not None:
                        break
                    continue
                if not line:
                    continue
                transcript_lines.append(line.rstrip("\n"))
                self._store.append_codex_event(run_id, task_id, line)
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    self._store.append_event(
                        run_id,
                        {
                            "level": "ERROR",
                            "event": "APP_SERVER_INVALID_JSON",
                            "run_id": run_id,
                            "meta": {"line": line.strip()},
                        },
                    )
                    continue
                if payload.get("method") == "item/agentMessage/delta":
                    delta = _extract_agent_delta(payload)
                    if delta:
                        agent_parts.append(delta)
                if payload.get("method") == "item/completed":
                    text = _extract_agent_message(payload)
                    if text:
                        agent_parts = [text]
                if payload.get("method") == "turn/completed":
                    turn_status, turn_error = _extract_turn_status(payload)
                    if turn_status:
                        break

            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()

            stderr_text = ""
            if proc.stderr is not None:
                stderr_text = proc.stderr.read()
                if stderr_text.strip():
                    self._store.append_event(
                        run_id,
                        {
                            "level": "ERROR",
                            "event": "APP_SERVER_STDERR",
                            "run_id": run_id,
                            "meta": {"text": stderr_text.strip()},
                        },
                    )

            if turn_status is None:
                return runner_common.failure_result(contract, "app-server turn timeout", {"stderr": stderr_text.strip()})
            if turn_status != "completed":
                reason = turn_error or f"turn status {turn_status}"
                return runner_common.failure_result(contract, reason, {"thread_id": thread_id or ""})

            transcript = "\n".join(transcript_lines)
            if transcript:
                self._store.write_codex_transcript(run_id, task_id, transcript)
            if thread_id:
                self._store.write_codex_thread_id(run_id, task_id, thread_id)
                self._store.write_codex_session_map(
                    run_id,
                    {
                        "run_id": run_id,
                        "task_id": task_id,
                        "codex_thread_id": thread_id,
                    },
                )

            agent_text = "".join(agent_parts).strip()
            if not agent_text:
                return runner_common.failure_result(contract, "app-server missing output", {"thread_id": thread_id or ""})
            try:
                payload = json.loads(agent_text)
            except json.JSONDecodeError as exc:
                return runner_common.failure_result(contract, "app-server output not json", {"error": str(exc)})

            evidence_refs = runner_common.build_evidence_refs(thread_id)
            return runner_common.coerce_task_result(payload, contract, evidence_refs, "SUCCESS")
        except Exception as exc:  # noqa: BLE001
            if proc.poll() is None:
                proc.terminate()
            return runner_common.failure_result(contract, "app-server execution failed", {"error": str(exc)})
