from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from openvibecoding_orch.contract.validator import ContractValidator
from openvibecoding_orch.observability.tracer import trace_span
from openvibecoding_orch.store.run_store import RunStore
from openvibecoding_orch.config import get_runner_config
from openvibecoding_orch.runners.agents_runner_execution_helpers import execute_agents_contract
from openvibecoding_orch.runners import common as runner_common
from openvibecoding_orch.runners import (
    agents_binding,
    agents_events,
    agents_handoff,
    agents_handoff_runtime,
    agents_mcp_config,
    agents_mcp_runtime,
    agents_payload,
    agents_runtime_helpers,
    agents_runner_phase2_helpers,
)
from openvibecoding_orch.runners import (
    agents_prompting,
    agents_session,
    agents_stream_runtime,
    mcp_server_lifecycle,
    mcp_streaming,
)


_HANDOFF_ROLE_ORDER = [
    "PM",
    "TECH_LEAD",
    "SEARCHER",
    "RESEARCHER",
    "UI_UX",
    "FRONTEND",
    "BACKEND",
    "AI",
    "SECURITY",
    "INFRA",
    "OPS",
    "WORKER",
    "REVIEWER",
    "TEST",
    "TEST_RUNNER",
]
_PRIMARY_HANDOFF_ORDER = ["PM", "TECH_LEAD", "WORKER", "REVIEWER", "TEST_RUNNER"]


_patch_mcp_codex_event_notifications = agents_mcp_runtime.patch_mcp_codex_event_notifications
_patch_mcp_initialized_notification = agents_mcp_runtime.patch_mcp_initialized_notification


_normalize_mcp_tool_set = agents_mcp_config._normalize_mcp_tool_set
_tool_set_disabled = agents_mcp_config._tool_set_disabled
_extract_mcp_server_names = agents_mcp_config._extract_mcp_server_names
_section_mcp_server_name = agents_mcp_config._section_mcp_server_name
_section_model_provider_name = agents_mcp_config._section_model_provider_name
_resolve_model_provider = agents_mcp_config._resolve_model_provider
_override_model_provider_base_url = agents_mcp_config._override_model_provider_base_url
_filter_mcp_config = agents_mcp_config._filter_mcp_config
_strip_mcp_sections = agents_mcp_config._strip_mcp_sections
_strip_toml_keys = agents_mcp_config._strip_toml_keys


_runtime_root_from_store = agents_mcp_runtime.runtime_root_from_store
_fixed_output_cwd = agents_mcp_runtime.fixed_output_cwd
_resolve_mcp_server_names = agents_mcp_runtime.resolve_mcp_server_names


def _materialize_worker_codex_home(
    store: RunStore,
    run_id: str,
    task_id: str,
    tool_set: list[str],
    role: str | None,
    worktree_path: Path,
    skip_role_prompt: bool,
    runtime_provider: str | None = None,
) -> Path:
    return agents_mcp_runtime.materialize_worker_codex_home(
        store,
        run_id,
        task_id,
        tool_set,
        role,
        worktree_path,
        skip_role_prompt,
        resolve_codex_base_url=_resolve_codex_base_url,
        runtime_provider=runtime_provider,
    )


_probe_mcp_ready = agents_mcp_runtime.probe_mcp_ready
_resolve_run_id = runner_common.resolve_run_id
_dummy_result = runner_common.dummy_result
_failure_result = runner_common.failure_result
_normalize_status = runner_common.normalize_status


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_now_ts = agents_events.now_ts
_build_evidence_refs = runner_common.build_evidence_refs
_coerce_task_result = runner_common.coerce_task_result
_is_valid_thread_id = agents_session.is_valid_thread_id
_is_codex_reply_thread_id = agents_session.is_codex_reply_thread_id
_extract_instruction = runner_common.extract_instruction
_extract_required_output = runner_common.extract_required_output


_mock_output_path = agents_runtime_helpers.mock_output_path
_path_allowed = agents_runtime_helpers.path_allowed


_resolve_roles_root = agents_prompting.resolve_roles_root
_load_role_prompt = agents_prompting.load_role_prompt
_resolve_role_prompt_path = agents_prompting.resolve_role_prompt_path
_output_schema_name_for_role = agents_prompting.output_schema_name_for_role
_output_schema_role_key = agents_prompting.output_schema_role_key
_resolve_output_schema_artifact = agents_prompting.resolve_output_schema_artifact


def _resolve_output_schema_path(
    contract: dict[str, Any],
    role: str | None,
    worktree_path: Path,
    schema_root: Path,
) -> Path:
    del worktree_path
    return agents_prompting.resolve_output_schema_path(contract, role, schema_root)


_load_output_schema = agents_prompting.load_output_schema
_is_fixed_json_template = agents_prompting.is_fixed_json_template
_extract_fixed_json_payload = agents_prompting.extract_fixed_json_payload
_decorate_instruction = agents_prompting.decorate_instruction
_build_codex_payload = agents_prompting.build_codex_payload

_codex_allowed = agents_runner_phase2_helpers.codex_allowed
_resolve_assigned_agent = agents_runner_phase2_helpers.resolve_assigned_agent


_resolve_profile = agents_runtime_helpers.resolve_profile

_resolve_agents_model = agents_runtime_helpers.resolve_agents_model
_resolve_agents_store = agents_runtime_helpers.resolve_agents_store
_resolve_agents_base_url = agents_runtime_helpers.resolve_agents_base_url


def _resolve_codex_base_url() -> str:
    explicit = os.getenv("OPENVIBECODING_CODEX_BASE_URL", "").strip()
    if explicit:
        return explicit

    agents_base_url = _resolve_agents_base_url().strip()
    if agents_base_url:
        return agents_base_url

    fallback_base_url = _resolve_equilibrium_base_url()
    if _equilibrium_healthcheck(fallback_base_url):
        return fallback_base_url

    return ""


_resolve_equilibrium_base_url = agents_runtime_helpers.resolve_equilibrium_base_url
_equilibrium_health_url = agents_runtime_helpers.equilibrium_health_url
_equilibrium_healthcheck = agents_runtime_helpers.equilibrium_healthcheck
_is_local_base_url = agents_runtime_helpers.is_local_base_url


_strip_model_input_ids = agents_mcp_runtime.strip_model_input_ids
_resolve_mcp_timeout_seconds = mcp_server_lifecycle.resolve_mcp_timeout_seconds
_resolve_mcp_connect_timeout_sec = mcp_server_lifecycle.resolve_mcp_connect_timeout_sec
_resolve_mcp_cleanup_timeout_sec = mcp_server_lifecycle.resolve_mcp_cleanup_timeout_sec

_agent_role = agents_runner_phase2_helpers.agent_role
_shell_policy = agents_runner_phase2_helpers.shell_policy


_validate_handoff_chain = agents_handoff._validate_handoff_chain


_handoff_required = agents_handoff._handoff_required


_handoff_chain_roles = agents_handoff._handoff_chain_roles


def _handoff_instructions(owner_role: str, assigned_role: str) -> str:
    return (
        "You are the orchestrated handoff agent. "
        "Summarize the contract-authoritative handoff for the next agent without rewriting execution instructions. "
        "Output JSON only with fields: summary and risks. "
        "summary is a one-sentence handoff note. "
        "risks is an array of short strings.\n\n"
        f"owner_role={owner_role}\n"
        f"assigned_role={assigned_role}"
    )


_handoff_prompt = agents_handoff._handoff_prompt


_parse_handoff_payload = agents_handoff._parse_handoff_payload


_resolve_session_binding = agents_binding._resolve_session_binding


_extract_evidence_refs = agents_binding._extract_evidence_refs


_extract_binding_from_result = agents_binding._extract_binding_from_result


_agent_instructions = agents_prompting.agent_instructions
_user_prompt = agents_prompting.user_prompt


_append_agents_transcript = agents_events.append_agents_transcript
_append_agents_raw_event = agents_events.append_agents_raw_event
_summarize_mcp_stream_item = agents_mcp_runtime.mcp_streaming.summarize_mcp_stream_item
_summarize_mcp_tool_result = agents_mcp_runtime.mcp_streaming.summarize_mcp_tool_result
_resolve_mcp_tool_timeout_sec = mcp_server_lifecycle.resolve_mcp_tool_timeout_sec
_resolve_stream_log_every = agents_mcp_runtime.mcp_streaming.resolve_stream_log_every
_result_snapshot = agents_events.result_snapshot


_safe_json_value = agents_payload._safe_json_value


_extract_first = agents_payload._extract_first


_extract_structured_content = agents_payload._extract_structured_content


def _extract_thread_id(snapshot: dict[str, Any]) -> str | None:
    return agents_session.extract_thread_id(snapshot, _extract_first)

_is_tool_call_dict = agents_payload._is_tool_call_dict


_contains_shell_request = agents_payload._contains_shell_request


_build_output_schema_binding = agents_runner_phase2_helpers.build_output_schema_binding
_resolve_tool_dispatch = agents_runner_phase2_helpers.resolve_tool_dispatch
_extract_structured_thread_id = agents_runner_phase2_helpers.extract_structured_thread_id
_build_tool_result_event = agents_runner_phase2_helpers.build_tool_result_event
_build_tool_call = agents_runner_phase2_helpers.build_tool_call
_normalize_final_output = agents_runner_phase2_helpers.normalize_final_output
_final_output_sha_source = agents_runner_phase2_helpers.final_output_sha_source


class AgentsRunner:
    def __init__(self, run_store: RunStore) -> None:
        self._store = run_store

    @trace_span("agents_runner.run_contract")
    def run_contract(
        self,
        contract: dict[str, Any],
        worktree_path: Path,
        schema_path: Path,
        mock_mode: bool = False,
    ) -> dict[str, Any]:
        run_id = _resolve_run_id(contract)
        instruction = _extract_instruction(contract, worktree_path)
        task_id = contract.get("task_id", "task")
        transcript_recorder = agents_events.TranscriptRecorder(self._store, run_id, task_id)
        _record_transcript = transcript_recorder.record
        _flush_transcript = transcript_recorder.flush
        if not instruction:
            return _failure_result(contract, "missing instruction")

        if not _codex_allowed(contract):
            self._store.append_event(
                run_id,
                {
                    "level": "ERROR",
                    "event": "MCP_TOOL_DENIED",
                    "run_id": run_id,
                    "meta": {"tool": "codex"},
                },
            )
            return _failure_result(contract, "codex mcp tool not allowed")

        schema_path = schema_path.resolve()
        if not schema_path.exists():
            return _failure_result(contract, "schema path missing", {"schema_path": str(schema_path)})

        validator = ContractValidator(schema_root=schema_path.parent)
        try:
            validator.validate_contract(contract)
        except Exception as exc:  # noqa: BLE001
            self._store.append_event(
                run_id,
                {
                    "level": "ERROR",
                    "event": "CONTRACT_SCHEMA_INVALID",
                    "run_id": run_id,
                    "meta": {"error": str(exc)},
                },
            )
            return _failure_result(contract, "contract schema validation failed", {"error": str(exc)})

        shell_policy = _shell_policy(contract)

        ok, reason = _validate_handoff_chain(contract)
        if not ok:
            self._store.append_event(
                run_id,
                {
                    "level": "ERROR",
                    "event": "AGENT_HANDOFF_INVALID",
                    "run_id": run_id,
                    "meta": {"reason": reason},
                },
            )
            return _failure_result(contract, reason)

        if mock_mode:
            tool_permissions = contract.get("tool_permissions") if isinstance(contract, dict) else {}
            filesystem = ""
            if isinstance(tool_permissions, dict):
                raw_fs = tool_permissions.get("filesystem")
                if isinstance(raw_fs, str):
                    filesystem = raw_fs.strip().lower()
            if filesystem == "read-only":
                self._store.append_event(
                    run_id,
                    {
                        "level": "INFO",
                        "event": "AGENTS_MOCK_EVENT",
                        "run_id": run_id,
                        "meta": {
                            "path": "",
                            "instruction": instruction,
                            "read_only": True,
                            "note": "mock mode skips file writes under read-only sandbox",
                        },
                    },
                )
                return _dummy_result(contract)

            rel_path = _mock_output_path(contract)
            target = worktree_path / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("mock", encoding="utf-8")
            self._store.append_event(
                run_id,
                {
                    "level": "INFO",
                    "event": "AGENTS_MOCK_EVENT",
                    "run_id": run_id,
                    "meta": {"path": str(target), "instruction": instruction},
                },
            )
            return _dummy_result(contract)

        return execute_agents_contract(
            module=sys.modules[__name__],
            store=self._store,
            contract=contract,
            worktree_path=worktree_path,
            schema_path=schema_path,
            run_id=run_id,
            task_id=task_id,
            instruction=instruction,
            shell_policy=shell_policy,
            validator=validator,
            record_transcript=_record_transcript,
            flush_transcript=_flush_transcript,
            failure_result=lambda reason, evidence: _failure_result(contract, reason, evidence),
        )
