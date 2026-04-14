from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Awaitable, Callable, TextIO

from openvibecoding_orch.runners import agents_events
from openvibecoding_orch.runners.provider_resolution import (
    ProviderResolutionError,
    resolve_preferred_api_key,
    resolve_provider_credentials,
    resolve_runtime_provider,
    resolve_runtime_provider_from_env,
)
from openvibecoding_orch.store.run_store import RunStore


_logger = logging.getLogger(__name__)


def _normalize_provider_name(provider: str) -> str:
    normalized = str(provider or "").strip().lower().replace("-", "_")
    if normalized == "google_genai":
        return "gemini"
    return normalized


def _resolve_preferred_api_key_for_provider(credentials: Any, provider: str) -> str:
    provider_name = str(provider or "").strip()
    try:
        candidate = resolve_preferred_api_key(credentials, provider_name)  # type: ignore[call-arg]
    except ProviderResolutionError:
        candidate = ""
    except (TypeError, AttributeError):
        candidate = resolve_preferred_api_key(credentials)
    except Exception as exc:  # noqa: BLE001
        _logger.debug("agents_mcp_execution_helpers: resolve_preferred_api_key fallback: %s", exc)
        candidate = ""
    resolved = str(candidate or "").strip()
    if resolved:
        return resolved
    normalized = _normalize_provider_name(provider_name)
    for attr in (
        f"{normalized}_api_key",
        "gemini_api_key",
        "openai_api_key",
        "anthropic_api_key",
        "equilibrium_api_key",
    ):
        value = str(getattr(credentials, attr, "") or "").strip()
        if value:
            return value
    return ""


async def run_worker_execution(
    *,
    store: RunStore,
    run_id: str,
    task_id: str,
    instruction: str,
    output_schema_name: str,
    output_schema_binding: Any,
    tool_name: str,
    tool_payload: dict[str, Any],
    tool_config: dict[str, Any],
    fixed_output: bool,
    mcp_tool_set: list[str],
    worker_codex_home: Path,
    mcp_stderr_path: Path | None,
    mcp_message_handler: Callable[[Any], Awaitable[None]],
    finalize_archive: Callable[[], None],
    agent_cls: Any,
    mcp_server_stdio_cls: Any,
    stdio_client: Callable[..., Any] | None,
    run_streamed: Callable[[Any, str], Awaitable[Any]],
    agent_instructions: Callable[[str, str, dict[str, Any], bool, str], str],
    user_prompt: Callable[[str, str], str],
    resolve_profile: Callable[[], str | None],
    patch_initialized_notification: Callable[[], tuple[bool, str]],
    patch_codex_event_notifications: Callable[[], tuple[bool, str]],
    resolve_mcp_timeout_seconds: Callable[[], float | None],
    resolve_mcp_connect_timeout_sec: Callable[[], float | None],
    resolve_mcp_cleanup_timeout_sec: Callable[[], float | None],
    resolve_codex_base_url: Callable[[], str],
    probe_mcp_ready: Callable[[Any, list[str]], Awaitable[dict[str, Any]]],
    runtime_provider: str | None = None,
) -> Any:
    class _OpenVibeCodingMCPServerStdio(mcp_server_stdio_cls):
        def __init__(
            self,
            params: Any,
            *,
            errlog_path: Path | None = None,
            **kwargs: Any,
        ) -> None:
            try:
                super().__init__(params, **kwargs)
            except TypeError:
                super().__init__(params)
            self._errlog_path = errlog_path
            self._errlog_handle: TextIO | None = None

        def create_streams(self):
            if self._errlog_path is not None and callable(stdio_client):
                self._errlog_path.parent.mkdir(parents=True, exist_ok=True)
                self._errlog_handle = self._errlog_path.open("a", encoding="utf-8")
                return stdio_client(self.params, errlog=self._errlog_handle)
            if hasattr(super(), "create_streams"):
                return super().create_streams()
            raise RuntimeError("MCP create_streams unavailable")

        async def cleanup(self):
            try:
                parent_cleanup = getattr(super(), "cleanup", None)
                if callable(parent_cleanup):
                    await parent_cleanup()
            finally:
                if self._errlog_handle is not None:
                    try:
                        self._errlog_handle.close()
                    except Exception as exc:  # noqa: BLE001
                        _logger.debug("agents_mcp_execution_helpers: errlog close failed: %s", exc)
                    self._errlog_handle = None

    profile = resolve_profile()
    args = ["mcp-server"]
    if profile:
        args = ["--profile", profile, "mcp-server"]
    patched_init, init_detail = patch_initialized_notification()
    store.append_event(
        run_id,
        {
            "level": "INFO" if patched_init else "WARN",
            "event": "MCP_NOTIFICATION_PATCH",
            "run_id": run_id,
            "meta": {"ok": patched_init, "detail": init_detail, "patch": "initialized"},
        },
    )
    patched, detail = patch_codex_event_notifications()
    store.append_event(
        run_id,
        {
            "level": "INFO" if patched else "WARN",
            "event": "MCP_NOTIFICATION_PATCH",
            "run_id": run_id,
            "meta": {"ok": patched, "detail": detail, "patch": "codex_event"},
        },
    )
    store.append_event(
        run_id,
        {
            "level": "INFO",
            "event": "MCP_SERVER_START",
            "run_id": run_id,
            "meta": {
                "command": "codex",
                "args": args,
                "timeout_sec": resolve_mcp_timeout_seconds(),
                "codex_home": str(worker_codex_home),
                "mcp_tool_set": mcp_tool_set,
            },
        },
    )
    env = dict(os.environ)
    env["CODEX_HOME"] = str(worker_codex_home)
    try:
        if isinstance(runtime_provider, str) and runtime_provider.strip():
            provider = resolve_runtime_provider(runtime_provider)
        else:
            provider = resolve_runtime_provider_from_env(env)
    except ProviderResolutionError as exc:
        raise RuntimeError(str(exc)) from exc
    normalized_provider = _normalize_provider_name(provider)
    env["OPENVIBECODING_PROVIDER"] = provider
    codex_base_url = resolve_codex_base_url()
    if codex_base_url:
        env["OPENVIBECODING_PROVIDER_BASE_URL"] = codex_base_url
    resolved_api_key = _resolve_preferred_api_key_for_provider(resolve_provider_credentials(env), provider)
    if resolved_api_key:
        if normalized_provider == "gemini":
            env.setdefault("GEMINI_API_KEY", resolved_api_key)
        elif normalized_provider == "openai":
            env.setdefault("OPENAI_API_KEY", resolved_api_key)
        elif normalized_provider == "anthropic":
            env.setdefault("ANTHROPIC_API_KEY", resolved_api_key)
        elif normalized_provider in {"equilibrium", "codex_equilibrium"}:
            env.setdefault("OPENVIBECODING_EQUILIBRIUM_API_KEY", resolved_api_key)
    server = _OpenVibeCodingMCPServerStdio(
        params={"command": "codex", "args": args, "env": env},
        client_session_timeout_seconds=resolve_mcp_timeout_seconds(),
        errlog_path=mcp_stderr_path,
        message_handler=mcp_message_handler,
    )
    connect_timeout = resolve_mcp_connect_timeout_sec()
    cleanup_timeout = resolve_mcp_cleanup_timeout_sec()
    entered_context_manager = False
    try:
        try:
            connect_fn = getattr(server, "connect", None)
            if callable(connect_fn):
                if connect_timeout is None:
                    await connect_fn()
                else:
                    await asyncio.wait_for(connect_fn(), timeout=connect_timeout)
            elif hasattr(server, "__aenter__") and callable(getattr(server, "__aenter__")):
                entered_context_manager = True
                enter_fn = getattr(server, "__aenter__")
                if connect_timeout is None:
                    await enter_fn()
                else:
                    await asyncio.wait_for(enter_fn(), timeout=connect_timeout)
        except asyncio.TimeoutError:
            store.append_event(
                run_id,
                {
                    "level": "ERROR",
                    "event": "MCP_SERVER_CONNECT_TIMEOUT",
                    "run_id": run_id,
                    "meta": {
                        "command": "codex",
                        "args": args,
                        "timeout_sec": connect_timeout,
                    },
                },
            )
            raise
        store.append_event(
            run_id,
            {
                "level": "INFO",
                "event": "MCP_SERVER_READY",
                "run_id": run_id,
                "meta": {
                    "command": "codex",
                    "args": args,
                    "timeout_sec": resolve_mcp_timeout_seconds(),
                },
            },
        )
        try:
            probe = await probe_mcp_ready(server, mcp_tool_set)
        except Exception as exc:  # noqa: BLE001
            store.append_event(
                run_id,
                {
                    "level": "ERROR",
                    "event": "MCP_READY_PROBE_FAILED",
                    "run_id": run_id,
                    "meta": {"error": str(exc), "mcp_tool_set": mcp_tool_set},
                },
            )
            raise RuntimeError(f"mcp ready probe failed: {exc}") from exc
        probe_state = str(probe.get("probe", "")).strip().lower() if isinstance(probe, dict) else ""
        if probe_state in {"ok", "empty", "skipped"}:
            event_level = "INFO" if probe_state == "ok" else "WARN"
            event_name = "MCP_READY_PROBE_OK" if probe_state == "ok" else "MCP_READY_PROBE_DEGRADED"
            store.append_event(
                run_id,
                {
                    "level": event_level,
                    "event": event_name,
                    "run_id": run_id,
                    "meta": probe if isinstance(probe, dict) else {"probe": probe_state or "unknown"},
                },
            )
        else:
            store.append_event(
                run_id,
                {
                    "level": "ERROR",
                    "event": "MCP_READY_PROBE_BLOCKED",
                    "run_id": run_id,
                    "meta": {
                        "reason": "mcp ready probe must be ok before execution",
                        "probe": probe if isinstance(probe, dict) else {"probe": "invalid", "raw": str(probe)},
                        "mcp_tool_set": mcp_tool_set,
                    },
                },
            )
            raise RuntimeError("mcp ready probe did not reach ready state")
        agent_kwargs = {
            "name": "OpenVibeCodingWorker",
            "instructions": agent_instructions(
                task_id,
                tool_name,
                tool_payload,
                fixed_output,
                output_schema_name,
            ),
            "mcp_servers": [server],
        }
        try:
            agent = agent_cls(output_type=output_schema_binding, **agent_kwargs)
        except TypeError:
            agent = agent_cls(**agent_kwargs)
        prompt = user_prompt(instruction, output_schema_name)
        sanitized_tool_payload = agents_events.sanitize_tool_payload(tool_payload)
        sanitized_tool_config = agents_events.sanitize_tool_payload(tool_config)
        agents_events.append_agents_raw_event(
            store,
            run_id,
            {
                "kind": "execution_start",
                "agent": agent.name,
                "prompt": prompt,
                "codex_payload": sanitized_tool_payload,
                "codex_tool": tool_name,
            },
            task_id,
        )
        store.append_tool_call(
            run_id,
            {
                "tool": tool_name,
                "args": sanitized_tool_payload,
                "config": sanitized_tool_config,
                "status": "requested",
                "task_id": task_id,
            },
        )
        store.append_event(
            run_id,
            {
                "level": "INFO",
                "event": "MCP_TOOL_CALL_REQUESTED",
                "run_id": run_id,
                "meta": {
                    "task_id": task_id,
                    "tool": tool_name,
                    "sandbox": tool_config.get("sandbox", ""),
                    "cwd": tool_config.get("cwd", ""),
                    "model": tool_config.get("model", ""),
                },
            },
        )
        result = await run_streamed(agent, prompt)
        output = getattr(result, "final_output", None)
        agents_events.append_agents_raw_event(
            store,
            run_id,
            {
                "kind": "execution_result",
                "agent": agent.name,
                "output": output or "",
            },
            task_id,
        )
        store.append_event(
            run_id,
            {
                "level": "INFO",
                "event": "MCP_TOOL_CALL_RESULT",
                "run_id": run_id,
                "meta": {
                    "task_id": task_id,
                    "tool": tool_name,
                    "has_output": bool(output),
                },
            },
        )
        return result
    finally:
        try:
            cleanup_fn = getattr(server, "cleanup", None)
            if callable(cleanup_fn):
                if cleanup_timeout is None:
                    await cleanup_fn()
                else:
                    await asyncio.wait_for(cleanup_fn(), timeout=cleanup_timeout)
            elif entered_context_manager and hasattr(server, "__aexit__"):
                exit_fn = getattr(server, "__aexit__")
                if callable(exit_fn):
                    if cleanup_timeout is None:
                        await exit_fn(None, None, None)
                    else:
                        await asyncio.wait_for(exit_fn(None, None, None), timeout=cleanup_timeout)
        except asyncio.TimeoutError:
            store.append_event(
                run_id,
                {
                    "level": "ERROR",
                    "event": "MCP_SERVER_CLEANUP_TIMEOUT",
                    "run_id": run_id,
                    "meta": {
                        "command": "codex",
                        "args": args,
                        "timeout_sec": cleanup_timeout,
                    },
                },
            )
        finalize_archive()
        store.append_event(
            run_id,
            {
                "level": "INFO",
                "event": "MCP_SERVER_CLOSED",
                "run_id": run_id,
                "meta": {"command": "codex", "args": args},
            },
        )
