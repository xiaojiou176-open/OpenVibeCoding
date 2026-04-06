from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Awaitable, Callable

from cortexpilot_orch.contract.validator import ContractValidator
from cortexpilot_orch.runners import agents_events, agents_handoff
from cortexpilot_orch.store.run_store import RunStore


def _handoff_timeout_fail_open_enabled() -> bool:
    raw = os.getenv("CORTEXPILOT_AGENTS_HANDOFF_TIMEOUT_FAIL_OPEN", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _is_timeout_like_error(exc: Exception) -> bool:
    text = str(exc).strip().lower()
    if not text:
        return False
    return "timed out" in text or "timeout" in text


def execute_handoff_flow(
    *,
    store: RunStore,
    contract: dict[str, Any],
    run_id: str,
    task_id: str,
    instruction: str,
    owner_agent: dict[str, Any],
    assigned_agent: dict[str, Any],
    owner_role: str,
    assigned_role: str,
    chain_roles: list[str],
    schema_root: Path,
    agent_cls: Any,
    run_streamed: Callable[[Any, str], Awaitable[Any]],
    handoff_instructions: Callable[[str, str], str],
    record_transcript: Callable[[dict[str, Any]], None],
    flush_transcript: Callable[[], None],
    failure_result: Callable[[dict[str, Any], str, dict[str, Any] | None], dict[str, Any]],
    sha256_text: Callable[[str], str],
) -> tuple[str, dict[str, Any], dict[str, Any] | None]:
    handoff_refs: dict[str, Any] = {}
    initial_instruction = instruction

    def _parse_payload(output: str, *, instruction_hash: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        try:
            payload, raw = agents_handoff._parse_handoff_payload(
                output,
                instruction_sha256=instruction_hash,
            )
        except TypeError:
            legacy_first, legacy_second = agents_handoff._parse_handoff_payload(output)
            if isinstance(legacy_first, dict) or legacy_first is None:
                payload = legacy_first
                raw = legacy_second if isinstance(legacy_second, dict) else {}
                if payload is not None and "instruction_sha256" not in raw:
                    payload = dict(payload)
                    raw = dict(raw)
                    payload["instruction_sha256"] = instruction_hash
                    raw["instruction_sha256"] = instruction_hash
            else:
                legacy_payload = legacy_second if isinstance(legacy_second, dict) else {}
                translated_payload: dict[str, Any] = {}
                for key in ("summary", "risks"):
                    if key in legacy_payload:
                        translated_payload[key] = legacy_payload[key]
                translated_payload["instruction_sha256"] = instruction_hash
                payload = translated_payload if legacy_payload else None
                raw = translated_payload if legacy_payload else {"error": "invalid handoff payload"}
        return payload, raw

    store.append_event(
        run_id,
        {
            "level": "INFO",
            "event": "AGENT_HANDOFF",
            "run_id": run_id,
            "meta": {
                "owner_agent": owner_agent,
                "assigned_agent": assigned_agent,
            },
        },
    )

    if chain_roles and len(chain_roles) > 1:
        max_handoffs = (
            contract.get("handoff_chain", {}).get("max_handoffs")
            if isinstance(contract.get("handoff_chain"), dict)
            else None
        )
        try:
            max_handoffs = int(max_handoffs) if max_handoffs is not None else len(chain_roles) - 1
        except (TypeError, ValueError):
            max_handoffs = len(chain_roles) - 1
        if max_handoffs < len(chain_roles) - 1:
            return instruction, handoff_refs, failure_result(contract, "handoff chain exceeds max_handoffs", None)

        store.append_event(
            run_id,
            {
                "level": "INFO",
                "event": "AGENT_HANDOFF_CHAIN_STARTED",
                "run_id": run_id,
                "meta": {"roles": chain_roles},
            },
        )

        handoff_validator = ContractValidator(schema_root=schema_root)

        async def _run_chain() -> list[dict[str, Any]]:
            outputs: list[dict[str, Any]] = []
            current = instruction
            for idx in range(len(chain_roles) - 1):
                from_role = chain_roles[idx]
                to_role = chain_roles[idx + 1]
                agent = agent_cls(
                    name=f"CortexPilotHandoff_{from_role}",
                    instructions=handoff_instructions(from_role or "OWNER", to_role or "WORKER"),
                    mcp_servers=[],
                )
                prompt = agents_handoff._handoff_prompt(contract.get("task_id", "task"), current)
                agents_events.append_agents_raw_event(
                    store,
                    run_id,
                    {
                        "kind": "handoff_start",
                        "from": from_role,
                        "to": to_role,
                        "agent": agent.name,
                        "prompt": prompt,
                    },
                    task_id,
                )
                result = await run_streamed(agent, prompt)
                handoff_output = getattr(result, "final_output", None)
                agents_events.append_agents_raw_event(
                    store,
                    run_id,
                    {
                        "kind": "handoff_result",
                        "from": from_role,
                        "to": to_role,
                        "agent": agent.name,
                        "output": handoff_output or "",
                    },
                    task_id,
                )
                if not isinstance(handoff_output, str) or not handoff_output.strip():
                    raise RuntimeError("handoff output missing")
                handoff_payload, payload = _parse_payload(
                    handoff_output,
                    instruction_hash=sha256_text(current),
                )
                if not handoff_payload:
                    raise RuntimeError(payload.get("error", "handoff invalid"))
                handoff_validator.validate_report(payload, "handoff.v1.json")
                outputs.append(
                    {
                        "from": from_role,
                        "to": to_role,
                        "summary": payload.get("summary", ""),
                        "risks": payload.get("risks", []),
                        "instruction_sha256": payload.get("instruction_sha256", ""),
                    }
                )
            return outputs

        try:
            chain_outputs = asyncio.run(_run_chain())
        except Exception as exc:  # noqa: BLE001
            if _handoff_timeout_fail_open_enabled() and _is_timeout_like_error(exc):
                agents_events.append_agents_raw_event(
                    store,
                    run_id,
                    {"kind": "handoff_chain_timeout_fail_open", "error": str(exc)},
                    task_id,
                )
                store.append_event(
                    run_id,
                    {
                        "level": "WARN",
                        "event": "AGENT_HANDOFF_TIMEOUT_FAIL_OPEN",
                        "run_id": run_id,
                        "meta": {
                            "mode": "chain",
                            "error": str(exc),
                        },
                    },
                )
                record_transcript({"kind": "handoff_timeout_fail_open", "text": str(exc)})
                return instruction, handoff_refs, None
            agents_events.append_agents_raw_event(
                store,
                run_id,
                {"kind": "handoff_chain_error", "error": str(exc)},
                task_id,
            )
            record_transcript({"kind": "handoff_chain_error", "text": str(exc)})
            flush_transcript()
            return instruction, handoff_refs, failure_result(contract, "agents sdk handoff failed", {"error": str(exc)})

        if not chain_outputs:
            record_transcript({"kind": "handoff_chain_empty", "text": "handoff chain empty"})
            flush_transcript()
            return instruction, handoff_refs, failure_result(contract, "handoff chain empty", None)

        for payload in chain_outputs:
            store.append_event(
                run_id,
                {
                    "level": "INFO",
                    "event": "AGENT_HANDOFF_STEP",
                    "run_id": run_id,
                    "meta": {
                        "from": payload.get("from"),
                        "to": payload.get("to"),
                        "summary": payload.get("summary", ""),
                        "risks": payload.get("risks", []),
                    },
                },
            )
            record_transcript(
                {
                    "kind": "handoff_step",
                    "from": payload.get("from"),
                    "to": payload.get("to"),
                    "summary": payload.get("summary", ""),
                    "risks": payload.get("risks", []),
                    "instruction_sha256": payload.get("instruction_sha256", ""),
                },
            )
        store.append_event(
            run_id,
            {
                "level": "INFO",
                "event": "AGENT_HANDOFF_CHAIN_COMPLETED",
                "run_id": run_id,
                "meta": {"roles": chain_roles},
            },
        )
        handoff_refs = {
            "handoff_chain": chain_roles,
            "instruction_sha256": sha256_text(initial_instruction),
            "instruction_final_sha256": sha256_text(instruction),
        }
        return instruction, handoff_refs, None

    if not agents_handoff._handoff_required(contract):
        return instruction, handoff_refs, None

    store.append_event(
        run_id,
        {
            "level": "INFO",
            "event": "AGENT_HANDOFF_REQUESTED",
            "run_id": run_id,
            "meta": {
                "owner_role": owner_role,
                "assigned_role": assigned_role,
            },
        },
    )

    async def _run_handoff() -> Any:
        agent = agent_cls(
            name="CortexPilotOwner",
            instructions=handoff_instructions(owner_role or "OWNER", assigned_role or "WORKER"),
            mcp_servers=[],
        )
        prompt = agents_handoff._handoff_prompt(contract.get("task_id", "task"), instruction)
        agents_events.append_agents_raw_event(
            store,
            run_id,
            {
                "kind": "handoff_start",
                "from": owner_role,
                "to": assigned_role,
                "agent": agent.name,
                "prompt": prompt,
            },
            task_id,
        )
        result = await run_streamed(agent, prompt)
        handoff_output = getattr(result, "final_output", None)
        agents_events.append_agents_raw_event(
            store,
            run_id,
            {
                "kind": "handoff_result",
                "from": owner_role,
                "to": assigned_role,
                "agent": agent.name,
                "output": handoff_output or "",
            },
            task_id,
        )
        return result

    try:
        handoff_result = asyncio.run(_run_handoff())
    except Exception as exc:  # noqa: BLE001
        if _handoff_timeout_fail_open_enabled() and _is_timeout_like_error(exc):
            agents_events.append_agents_raw_event(
                store,
                run_id,
                {"kind": "handoff_timeout_fail_open", "error": str(exc)},
                task_id,
            )
            store.append_event(
                run_id,
                {
                    "level": "WARN",
                    "event": "AGENT_HANDOFF_TIMEOUT_FAIL_OPEN",
                    "run_id": run_id,
                    "meta": {
                        "mode": "single",
                        "error": str(exc),
                    },
                },
            )
            record_transcript({"kind": "handoff_timeout_fail_open", "text": str(exc)})
            return instruction, handoff_refs, None
        agents_events.append_agents_raw_event(
            store,
            run_id,
            {"kind": "handoff_error", "error": str(exc)},
            task_id,
        )
        record_transcript({"kind": "handoff_error", "text": str(exc)})
        flush_transcript()
        return instruction, handoff_refs, failure_result(contract, "agents sdk handoff failed", {"error": str(exc)})

    handoff_output = getattr(handoff_result, "final_output", None)
    if not isinstance(handoff_output, str) or not handoff_output.strip():
        record_transcript({"kind": "handoff_output_missing", "text": "handoff output missing"})
        flush_transcript()
        return instruction, handoff_refs, failure_result(contract, "handoff output missing", None)

    handoff_payload, payload = _parse_payload(
        handoff_output,
        instruction_hash=sha256_text(initial_instruction),
    )
    if not handoff_payload:
        store.append_event(
            run_id,
            {
                "level": "ERROR",
                "event": "AGENT_HANDOFF_INVALID",
                "run_id": run_id,
                "meta": payload,
            },
        )
        record_transcript({"kind": "handoff_invalid", "text": payload.get("error", "handoff invalid")})
        flush_transcript()
        return instruction, handoff_refs, failure_result(
            contract, payload.get("error", "handoff invalid"), None
        )
    try:
        ContractValidator(schema_root=schema_root).validate_report(payload, "handoff.v1.json")
    except Exception as exc:  # noqa: BLE001
        record_transcript({"kind": "handoff_schema_invalid", "text": str(exc)})
        flush_transcript()
        return instruction, handoff_refs, failure_result(contract, "handoff schema invalid", {"error": str(exc)})

    handoff_refs = {
        "handoff_chain": [owner_role, assigned_role] if owner_role and assigned_role else [],
        "instruction_sha256": sha256_text(initial_instruction),
        "instruction_final_sha256": sha256_text(instruction),
    }
    store.append_event(
        run_id,
        {
            "level": "INFO",
            "event": "AGENT_HANDOFF_RESULT",
            "run_id": run_id,
            "meta": {
                "summary": payload.get("summary", ""),
                "risks": payload.get("risks", []),
            },
        },
    )
    record_transcript(
        {
            "kind": "handoff_result",
            "summary": payload.get("summary", ""),
            "risks": payload.get("risks", []),
            "instruction_sha256": payload.get("instruction_sha256", ""),
        },
    )
    return instruction, handoff_refs, None
