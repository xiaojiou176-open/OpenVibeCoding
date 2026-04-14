from __future__ import annotations

import asyncio
import inspect
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable

from openvibecoding_orch.contract.validator import ContractValidator
from openvibecoding_orch.runners.provider_resolution import (
    build_llm_compat_client,
    ProviderCredentials,
    ProviderResolutionError,
    resolve_compat_api_mode,
    resolve_preferred_api_key,
    resolve_runtime_provider_from_contract,
)
from openvibecoding_orch.store.run_store import RunStore
from openvibecoding_orch.runners.agents_runner_result_helpers import finalize_agents_run_result


_logger = logging.getLogger(__name__)
FailureResult = Callable[[str, dict[str, Any] | None], dict[str, Any]]
TranscriptRecorder = Callable[[dict[str, Any]], None]
_PROVIDER_API_KEY_ENV_HINTS = {
    "gemini": "GEMINI_API_KEY",
    "google": "GEMINI_API_KEY",
    "google-genai": "GEMINI_API_KEY",
    "google_genai": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
    "anthropic-claude": "ANTHROPIC_API_KEY",
    "anthropic_claude": "ANTHROPIC_API_KEY",
    "equilibrium": "OPENVIBECODING_EQUILIBRIUM_API_KEY",
    "codex_equilibrium": "OPENVIBECODING_EQUILIBRIUM_API_KEY",
}


def _missing_llm_api_key_message(provider: str) -> str:
    env_key = _PROVIDER_API_KEY_ENV_HINTS.get(provider, "GEMINI_API_KEY")
    return f"missing LLM API key ({env_key})"


def _resolve_preferred_api_key_for_provider(
    credentials: ProviderCredentials,
    provider: str,
    *,
    base_url: str = "",
) -> str:
    provider_name = str(provider or "").strip()
    normalized = provider_name.lower().replace("-", "_")
    if normalized == "google_genai":
        normalized = "gemini"
    if normalized == "codex_equilibrium":
        normalized = "equilibrium"
    provider_attr = {
        "gemini": "gemini_api_key",
        "openai": "openai_api_key",
        "anthropic": "anthropic_api_key",
        "equilibrium": "gemini_api_key",
    }
    attr = provider_attr.get(normalized)
    if attr:
        value = str(getattr(credentials, attr, "") or "").strip()
        if value:
            return value
        if normalized == "equilibrium":
            equilibrium_key = str(getattr(credentials, "equilibrium_api_key", "") or "").strip()
            if equilibrium_key:
                return equilibrium_key
        if normalized == "gemini" and base_url.strip().lower().startswith(
            ("http://127.0.0.1", "http://localhost", "http://0.0.0.0")
        ):
            equilibrium_key = str(getattr(credentials, "equilibrium_api_key", "") or "").strip()
            if equilibrium_key:
                return equilibrium_key

    try:
        candidate = resolve_preferred_api_key(credentials, provider_name)  # type: ignore[call-arg]
    except ProviderResolutionError:
        candidate = ""
    except (TypeError, AttributeError):
        candidate = resolve_preferred_api_key(credentials)
    except Exception as exc:  # noqa: BLE001
        _logger.debug("agents_runner_execution_helpers: resolve_preferred_api_key fallback: %s", exc)
        candidate = ""
    resolved = str(candidate or "").strip()
    if resolved:
        return resolved
    for fallback_attr in (
        "openai_api_key",
        "gemini_api_key",
        "anthropic_api_key",
        "equilibrium_api_key",
    ):
        value = str(getattr(credentials, fallback_attr, "") or "").strip()
        if value:
            return value
    if resolve_compat_api_mode("responses", base_url=base_url) == "chat_completions":
        return "switchyard-local"
    return ""


def execute_agents_contract(
    *,
    module: Any,
    store: RunStore,
    contract: dict[str, Any],
    worktree_path: Path,
    schema_path: Path,
    run_id: str,
    task_id: str,
    instruction: str,
    shell_policy: str,
    validator: ContractValidator,
    record_transcript: TranscriptRecorder,
    flush_transcript: Callable[[], None],
    failure_result: FailureResult,
) -> dict[str, Any]:
    def _is_timeout_like_error(exc: Exception) -> bool:
        text = str(exc).strip().lower()
        return bool(text) and ("timed out" in text or "timeout" in text)

    def _is_retryable_sdk_error(exc: Exception) -> bool:
        text = str(exc).strip().lower()
        if not text:
            return False
        if "incorrect api key" in text or "invalid_api_key" in text:
            return False
        return (
            "an error occurred while processing your request" in text
            or "help.openai.com if the error persists" in text
            or "stream disconnected" in text
        )

    def _resolve_positive_float(raw: str, default: float) -> float:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return default
        return value if value > 0 else default

    def _resolve_non_negative_int(raw: str, default: int) -> int:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return default
        return max(0, value)

    try:
        import importlib

        agents_module = importlib.import_module("agents")
        Agent = getattr(agents_module, "Agent")
        ModelSettings = getattr(agents_module, "ModelSettings")
        RunConfig = getattr(agents_module, "RunConfig")
        Runner = getattr(agents_module, "Runner")

        mcp_module = importlib.import_module("agents.mcp")
        MCPServerStdio = getattr(mcp_module, "MCPServerStdio")

        from jsonschema import Draft202012Validator

        try:
            from agents.agent_output import AgentOutputSchemaBase
        except Exception:  # noqa: BLE001
            class AgentOutputSchemaBase:  # type: ignore[override]
                pass

        try:
            from agents.exceptions import ModelBehaviorError
        except Exception:  # noqa: BLE001
            class ModelBehaviorError(Exception):
                pass

        try:
            from mcp.client.stdio import stdio_client
        except Exception:  # noqa: BLE001
            stdio_client = None
    except Exception as exc:  # noqa: BLE001
        record_transcript({"kind": "agents_sdk_missing", "text": str(exc)})
        flush_transcript()
        return failure_result("agents sdk not available", {"error": str(exc)})

    runner_cfg = module.get_runner_config()
    base_url = str(getattr(runner_cfg, "agents_base_url", "") or "").strip()
    if not base_url:
        base_url = module._resolve_agents_base_url().strip()
    try:
        provider = resolve_runtime_provider_from_contract(contract)
    except ProviderResolutionError as exc:
        record_transcript(
            {
                "kind": "provider_resolution_failed",
                "text": str(exc),
                "code": exc.code,
            }
        )
        flush_transcript()
        return failure_result(str(exc), {"error_code": exc.code})
    provider_credentials = ProviderCredentials(
        gemini_api_key=str(getattr(runner_cfg, "gemini_api_key", "") or "").strip(),
        openai_api_key=str(getattr(runner_cfg, "openai_api_key", "") or "").strip(),
        anthropic_api_key=str(getattr(runner_cfg, "anthropic_api_key", "") or "").strip(),
        equilibrium_api_key=str(getattr(runner_cfg, "equilibrium_api_key", "") or "").strip(),
    )
    api_key = _resolve_preferred_api_key_for_provider(provider_credentials, provider, base_url=base_url)
    if not api_key:
        missing_message = _missing_llm_api_key_message(provider)
        record_transcript({"kind": "missing_api_key", "text": missing_message})
        flush_transcript()
        return failure_result(missing_message, None)
    if resolve_compat_api_mode("responses", base_url=base_url) == "chat_completions":
        record_transcript(
            {
                "kind": "switchyard_runtime_unsupported",
                "text": "Switchyard runtime-first adapter is not supported for agents_runner MCP tool execution yet.",
            }
        )
        flush_transcript()
        return failure_result(
            "Switchyard runtime-first adapter is not supported for agents_runner MCP tool execution yet.",
            {"base_url": base_url},
        )

    compat_client = None
    try:
        llm_timeout_sec = _resolve_positive_float(
            os.getenv("OPENVIBECODING_AGENTS_LLM_TIMEOUT_SEC", "180.0").strip(),
            180.0,
        )
        llm_client_retries = _resolve_non_negative_int(
            os.getenv("OPENVIBECODING_AGENTS_LLM_CLIENT_RETRIES", "2").strip(),
            2,
        )
        compat_client = build_llm_compat_client(
            api_key=api_key,
            base_url=base_url or None,
            timeout=llm_timeout_sec,
            max_retries=llm_client_retries,
            provider=provider,
        )
    except Exception as exc:  # noqa: BLE001
        record_transcript({"kind": "llm_compat_client_setup_failed", "text": str(exc)})
        flush_transcript()
        return failure_result("agents sdk client setup failed", {"error": str(exc)})
    if compat_client is not None:
        try:
            from agents import set_default_openai_client

            if callable(set_default_openai_client):
                set_default_openai_client(compat_client)
        except Exception:  # noqa: BLE001
            pass

    mcp_stderr_path: Path | None = None
    stream_activity_bridge: dict[str, Any] = {"touch": None}

    def _touch_activity(source: str) -> None:
        touch = stream_activity_bridge.get("touch")
        if callable(touch):
            touch(source)

    async def _run_streamed(
        agent: Any,
        prompt: str,
        tool_context: dict[str, Any] | None = None,
    ) -> Any:
        tool_context = tool_context or {}
        extra_headers = {
            "x-openvibecoding-run-id": run_id,
            "x-openvibecoding-task-id": task_id,
        }
        model_name = module._resolve_agents_model()
        run_config = RunConfig(
            model=model_name,
            tracing_disabled=True,
            model_settings=ModelSettings(
                extra_headers=extra_headers,
                store=module._resolve_agents_store(),
            ),
            call_model_input_filter=module._strip_model_input_ids,
        )
        fallback_enabled = os.getenv("OPENVIBECODING_AGENTS_STREAM_TIMEOUT_FALLBACK", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        stream_timeout_retries = _resolve_non_negative_int(
            os.getenv("OPENVIBECODING_AGENTS_STREAM_TIMEOUT_RETRIES", "2").strip(),
            2,
        )
        retry_backoff_sec = _resolve_positive_float(
            os.getenv("OPENVIBECODING_AGENTS_STREAM_RETRY_BACKOFF_SEC", "1.5").strip(),
            1.5,
        )
        max_attempts = stream_timeout_retries + 1
        runner_run = getattr(Runner, "run", None)

        for attempt in range(1, max_attempts + 1):
            result = Runner.run_streamed(
                agent,
                prompt,
                run_config=run_config,
            )
            if not hasattr(result, "stream_events"):
                return result
            try:
                await module.agents_stream_runtime.consume_stream_events(
                    result=result,
                    store=store,
                    run_id=run_id,
                    task_id=task_id,
                    contract=contract,
                    mcp_stderr_path=mcp_stderr_path,
                    tool_context=tool_context,
                    activity_bridge=stream_activity_bridge,
                )
                return result
            except Exception as exc:  # noqa: BLE001
                timeout_like = _is_timeout_like_error(exc)
                if timeout_like and fallback_enabled and callable(runner_run):
                    store.append_event(
                        run_id,
                        {
                            "level": "WARN",
                            "event": "AGENTS_STREAM_TIMEOUT_FALLBACK",
                            "run_id": run_id,
                            "meta": {
                                "task_id": task_id,
                                "error": str(exc),
                                "attempt": attempt,
                                "max_attempts": max_attempts,
                            },
                        },
                    )
                    try:
                        fallback_result = runner_run(agent, prompt, run_config=run_config)
                        if inspect.isawaitable(fallback_result):
                            fallback_result = await fallback_result
                        return fallback_result
                    except Exception as fallback_exc:  # noqa: BLE001
                        if _is_timeout_like_error(fallback_exc) and attempt < max_attempts:
                            store.append_event(
                                run_id,
                                {
                                    "level": "WARN",
                                    "event": "AGENTS_STREAM_TIMEOUT_RETRY",
                                    "run_id": run_id,
                                    "meta": {
                                        "task_id": task_id,
                                        "attempt": attempt,
                                        "max_attempts": max_attempts,
                                        "mode": "fallback",
                                        "error": str(fallback_exc),
                                        "backoff_sec": retry_backoff_sec,
                                    },
                                },
                            )
                            await asyncio.sleep(retry_backoff_sec * attempt)
                            continue
                        raise fallback_exc
                retryable_sdk_error = _is_retryable_sdk_error(exc)
                if (timeout_like or retryable_sdk_error) and attempt < max_attempts:
                    store.append_event(
                        run_id,
                        {
                            "level": "WARN",
                            "event": "AGENTS_STREAM_TIMEOUT_RETRY" if timeout_like else "AGENTS_STREAM_RETRYABLE_ERROR",
                            "run_id": run_id,
                            "meta": {
                                "task_id": task_id,
                                "attempt": attempt,
                                "max_attempts": max_attempts,
                                "mode": "stream",
                                "error": str(exc),
                                "backoff_sec": retry_backoff_sec,
                            },
                        },
                    )
                    await asyncio.sleep(retry_backoff_sec * attempt)
                    continue
                raise
        raise RuntimeError("stream retries exhausted")

    owner_agent = contract.get("owner_agent", {})
    assigned_agent = module._resolve_assigned_agent(contract)
    owner_role = module._agent_role(owner_agent)
    assigned_role = module._agent_role(assigned_agent)
    chain_roles = module._handoff_chain_roles(contract)
    handoff_refs: dict[str, Any] = {}
    schema_root = worktree_path / "schemas"
    if not schema_root.exists():
        schema_root = schema_path.parent
    try:
        output_schema_path = module._resolve_output_schema_path(
            contract,
            assigned_role or "WORKER",
            worktree_path,
            schema_root,
        )
    except Exception as exc:  # noqa: BLE001
        store.append_event(
            run_id,
            {
                "level": "ERROR",
                "event": "OUTPUT_SCHEMA_BIND_FAILED",
                "run_id": run_id,
                "meta": {"error": str(exc)},
            },
        )
        return failure_result("output schema binding failed", {"error": str(exc)})
    output_schema_name = output_schema_path.name
    try:
        output_schema_binding = module._build_output_schema_binding(
            output_schema_path,
            agent_output_schema_base=AgentOutputSchemaBase,
            model_behavior_error=ModelBehaviorError,
            draft_validator_cls=Draft202012Validator,
        )
    except Exception as exc:  # noqa: BLE001
        store.append_event(
            run_id,
            {
                "level": "ERROR",
                "event": "OUTPUT_SCHEMA_BIND_FAILED",
                "run_id": run_id,
                "meta": {"error": str(exc)},
            },
        )
        return failure_result("output schema binding failed", {"error": str(exc)})

    instruction, handoff_refs, handoff_failure = module.agents_handoff_runtime.execute_handoff_flow(
        store=store,
        contract=contract,
        run_id=run_id,
        task_id=task_id,
        instruction=instruction,
        owner_agent=owner_agent,
        assigned_agent=assigned_agent,
        owner_role=owner_role,
        assigned_role=assigned_role,
        chain_roles=chain_roles,
        schema_root=schema_path.parent,
        agent_cls=Agent,
        run_streamed=lambda agent, prompt: _run_streamed(agent, prompt),
        handoff_instructions=module._handoff_instructions,
        record_transcript=record_transcript,
        flush_transcript=flush_transcript,
        failure_result=lambda _payload, reason, evidence: failure_result(reason, evidence),
        sha256_text=module._sha256_text,
    )
    if handoff_failure is not None:
        return handoff_failure

    fixed_output = module._is_fixed_json_template(instruction)
    instruction = module._decorate_instruction(
        assigned_role or "WORKER",
        instruction,
        worktree_path,
        output_schema_path,
        output_schema_name,
    )
    store.append_event(
        run_id,
        {
            "level": "INFO",
            "event": "OUTPUT_SCHEMA_ENFORCED",
            "run_id": run_id,
            "meta": {
                "schema": output_schema_name,
                "mode": "agents_output_type+validation",
                "role": assigned_role or "WORKER",
            },
        },
    )
    thread_id, session_id = module._resolve_session_binding(contract)
    codex_payload = module._build_codex_payload(contract, instruction, worktree_path)
    if fixed_output:
        codex_payload["cwd"] = module._fixed_output_cwd(store)
    tool_name, tool_payload, tool_config, unsupported_thread_id = module._resolve_tool_dispatch(
        codex_payload,
        instruction=instruction,
        thread_id=thread_id,
        is_codex_reply_thread_id=module._is_codex_reply_thread_id,
    )
    if unsupported_thread_id:
        store.append_event(
            run_id,
            {
                "level": "WARN",
                "event": "AGENT_SESSION_THREAD_ID_UNSUPPORTED",
                "run_id": run_id,
                "meta": {
                    "thread_id": unsupported_thread_id,
                    "reason": "codex-reply requires uuid-like threadId; fallback to codex",
                },
            },
        )
    if thread_id or session_id:
        store.append_event(
            run_id,
            {
                "level": "INFO",
                "event": "AGENT_SESSION_RESOLVED",
                "run_id": run_id,
                "meta": {"thread_id": thread_id or "", "session_id": session_id or ""},
            },
        )

    mcp_tool_set = module._normalize_mcp_tool_set(contract.get("mcp_tool_set"))
    tool_set_disabled = module._tool_set_disabled(mcp_tool_set)
    if tool_set_disabled:
        mcp_tool_set = []
    if fixed_output and tool_set_disabled:
        fixed_payload = module._extract_fixed_json_payload(instruction)
        if not fixed_payload:
            store.append_event(
                run_id,
                {
                    "level": "ERROR",
                    "event": "AGENT_FIXED_OUTPUT_INVALID",
                    "run_id": run_id,
                    "meta": {"task_id": task_id, "reason": "fixed output json missing"},
                },
            )
            return failure_result("fixed output json missing", None)
        try:
            validator.validate_report(fixed_payload, output_schema_name)
        except Exception as exc:  # noqa: BLE001
            store.append_event(
                run_id,
                {
                    "level": "ERROR",
                    "event": "OUTPUT_SCHEMA_BIND_FAILED",
                    "run_id": run_id,
                    "meta": {"error": str(exc)},
                },
            )
            return failure_result("fixed output schema invalid", {"error": str(exc)})
        store.append_event(
            run_id,
            {
                "level": "INFO",
                "event": "AGENT_FIXED_OUTPUT_BYPASS",
                "run_id": run_id,
                "meta": {"task_id": task_id},
            },
        )
        evidence_refs = module._build_evidence_refs(None, None)
        if handoff_refs:
            evidence_refs.update(handoff_refs)
        return module._coerce_task_result(fixed_payload, contract, evidence_refs, "SUCCESS")
    if not mcp_tool_set and not fixed_output:
        store.append_event(
            run_id,
            {
                "level": "ERROR",
                "event": "MCP_READY_PROBE_FAILED",
                "run_id": run_id,
                "meta": {"reason": "mcp_tool_set missing or empty"},
            },
        )
        return failure_result("mcp_tool_set missing or empty", None)

    try:
        worker_codex_home = module._materialize_worker_codex_home(
            store,
            run_id,
            task_id,
            mcp_tool_set,
            assigned_role or "WORKER",
            worktree_path,
            fixed_output,
            runtime_provider=provider,
        )
    except Exception as exc:  # noqa: BLE001
        store.append_event(
            run_id,
            {
                "level": "ERROR",
                "event": "MCP_READY_PROBE_FAILED",
                "run_id": run_id,
                "meta": {"reason": "codex_home materialize failed", "error": str(exc)},
            },
        )
        return failure_result(f"codex home materialize failed: {exc}", None)

    mcp_stdout_path, mcp_stderr_path = module.agents_mcp_runtime.bind_mcp_log_paths(
        store=store,
        run_id=run_id,
        task_id=task_id,
    )
    mcp_message_archive = module.agents_mcp_runtime.MCPMessageArchive(
        store=store,
        run_id=run_id,
        task_id=task_id,
        stdout_path=mcp_stdout_path,
        touch_activity=_touch_activity,
    )

    async def _mcp_message_handler(message: Any) -> None:
        await mcp_message_archive.handle_message(message)

    async def _run() -> Any:
        return await module.agents_mcp_runtime.run_worker_execution(
            store=store,
            run_id=run_id,
            task_id=task_id,
            instruction=instruction,
            output_schema_name=output_schema_name,
            output_schema_binding=output_schema_binding,
            tool_name=tool_name,
            tool_payload=tool_payload,
            tool_config=tool_config,
            fixed_output=fixed_output,
            mcp_tool_set=mcp_tool_set,
            worker_codex_home=worker_codex_home,
            mcp_stderr_path=mcp_stderr_path,
            mcp_message_handler=_mcp_message_handler,
            finalize_archive=mcp_message_archive.finalize,
            agent_cls=Agent,
            mcp_server_stdio_cls=MCPServerStdio,
            stdio_client=stdio_client,
            run_streamed=_run_streamed,
            agent_instructions=module._agent_instructions,
            user_prompt=module._user_prompt,
            resolve_profile=module._resolve_profile,
            patch_initialized_notification=module._patch_mcp_initialized_notification,
            patch_codex_event_notifications=module._patch_mcp_codex_event_notifications,
            resolve_mcp_timeout_seconds=module._resolve_mcp_timeout_seconds,
            resolve_mcp_connect_timeout_sec=module._resolve_mcp_connect_timeout_sec,
            resolve_mcp_cleanup_timeout_sec=module._resolve_mcp_cleanup_timeout_sec,
            resolve_codex_base_url=module._resolve_codex_base_url,
            probe_mcp_ready=module._probe_mcp_ready,
            runtime_provider=provider,
        )

    start = time.monotonic()
    try:
        result = asyncio.run(_run())
    except Exception as exc:  # noqa: BLE001
        store.append_tool_call(
            run_id,
            module._build_tool_call(
                tool_name=tool_name,
                tool_payload=tool_payload,
                tool_config=tool_config,
                status="error",
                duration_ms=int((time.monotonic() - start) * 1000),
                error=str(exc),
                task_id=task_id,
            ),
        )
        module._append_agents_raw_event(
            store,
            run_id,
            {"kind": "execution_error", "error": str(exc)},
            task_id,
        )
        record_transcript({"kind": "execution_error", "text": str(exc)})
        flush_transcript()
        return failure_result("agents sdk execution failed", {"error": str(exc)})

    return finalize_agents_run_result(
        module=module,
        store=store,
        run_id=run_id,
        task_id=task_id,
        contract=contract,
        result=result,
        start_monotonic=start,
        tool_name=tool_name,
        tool_payload=tool_payload,
        tool_config=tool_config,
        shell_policy=shell_policy,
        output_schema_name=output_schema_name,
        validator=validator,
        handoff_refs=handoff_refs,
        record_transcript=record_transcript,
        flush_transcript=flush_transcript,
        failure_result=failure_result,
    )
