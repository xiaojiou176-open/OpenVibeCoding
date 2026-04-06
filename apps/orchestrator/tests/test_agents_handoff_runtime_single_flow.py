from __future__ import annotations

from pathlib import Path
from typing import Any

from cortexpilot_orch.runners import agents_handoff_runtime


class _Store:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []
        self.artifacts: list[tuple[str, str, dict[str, Any]]] = []
        self.codex_events: list[tuple[str, str, str]] = []

    def append_event(self, run_id: str, payload: dict[str, Any]) -> None:
        self.events.append((run_id, payload))

    def append_artifact_jsonl(self, run_id: str, name: str, payload: dict[str, Any]) -> None:
        self.artifacts.append((run_id, name, payload))

    def append_codex_event(self, run_id: str, task_id: str, payload: str) -> None:
        self.codex_events.append((run_id, task_id, payload))


class _Agent:
    def __init__(self, name: str, instructions: str, mcp_servers: list[Any]) -> None:
        self.name = name
        self.instructions = instructions
        self.mcp_servers = mcp_servers


class _Result:
    def __init__(self, final_output: Any) -> None:
        self.final_output = final_output


def _failure_result(_contract: dict[str, Any], reason: str, evidence: dict[str, Any] | None) -> dict[str, Any]:
    return {"status": "FAILED", "reason": reason, "evidence": evidence}


def _sha256_text(value: str) -> str:
    return f"sha::{value}"


def _handoff_instructions(from_role: str, to_role: str) -> str:
    return f"{from_role}->{to_role}"


def test_handoff_timeout_helpers(monkeypatch) -> None:
    monkeypatch.setenv("CORTEXPILOT_AGENTS_HANDOFF_TIMEOUT_FAIL_OPEN", "yes")
    assert agents_handoff_runtime._handoff_timeout_fail_open_enabled() is True

    monkeypatch.delenv("CORTEXPILOT_AGENTS_HANDOFF_TIMEOUT_FAIL_OPEN", raising=False)
    assert agents_handoff_runtime._handoff_timeout_fail_open_enabled() is False

    assert agents_handoff_runtime._is_timeout_like_error(RuntimeError("timed out while waiting")) is True
    assert agents_handoff_runtime._is_timeout_like_error(RuntimeError("")) is False


def test_chain_handoff_invalid_max_handoffs_uses_default(monkeypatch, tmp_path: Path) -> None:
    store = _Store()
    transcripts: list[dict[str, Any]] = []
    flushed: list[str] = []

    monkeypatch.setattr(agents_handoff_runtime.agents_handoff, "_handoff_prompt", lambda _task_id, text: text)
    monkeypatch.setattr(
        agents_handoff_runtime.agents_handoff,
        "_parse_handoff_payload",
        lambda _output, instruction_sha256=None: (
            {"summary": "ok", "risks": [], "instruction_sha256": instruction_sha256 or ""},
            {"summary": "ok", "risks": [], "instruction_sha256": instruction_sha256 or ""},
        ),
    )

    class _Validator:
        def __init__(self, schema_root: Path) -> None:
            self.schema_root = schema_root

        def validate_report(self, payload: dict[str, Any], _schema: str) -> None:
            assert payload["summary"] == "ok"

    monkeypatch.setattr(agents_handoff_runtime, "ContractValidator", _Validator)

    async def _run_streamed(_agent: _Agent, _prompt: str) -> _Result:
        return _Result("handoff-output")

    instruction, refs, failure = agents_handoff_runtime.execute_handoff_flow(
        store=store,
        contract={"task_id": "task-1", "handoff_chain": {"max_handoffs": "NaN"}},
        run_id="run-1",
        task_id="task-1",
        instruction="initial",
        owner_agent={"role": "PM"},
        assigned_agent={"role": "WORKER"},
        owner_role="PM",
        assigned_role="WORKER",
        chain_roles=["PM", "WORKER"],
        schema_root=tmp_path,
        agent_cls=_Agent,
        run_streamed=_run_streamed,
        handoff_instructions=_handoff_instructions,
        record_transcript=transcripts.append,
        flush_transcript=lambda: flushed.append("flush"),
        failure_result=_failure_result,
        sha256_text=_sha256_text,
    )

    assert instruction == "initial"
    assert refs["handoff_chain"] == ["PM", "WORKER"]
    assert failure is None
    assert not flushed


def test_chain_handoff_missing_output_fails_closed(monkeypatch, tmp_path: Path) -> None:
    store = _Store()
    transcripts: list[dict[str, Any]] = []
    flushed: list[str] = []

    monkeypatch.setattr(agents_handoff_runtime.agents_handoff, "_handoff_prompt", lambda _task_id, text: text)
    monkeypatch.setattr(
        agents_handoff_runtime.agents_handoff,
        "_parse_handoff_payload",
        lambda _output: ("", {"error": "invalid"}),
    )
    monkeypatch.setattr(
        agents_handoff_runtime,
        "ContractValidator",
        lambda schema_root: type("_V", (), {"validate_report": lambda *_a, **_k: None})(),
    )

    async def _run_streamed(_agent: _Agent, _prompt: str) -> _Result:
        return _Result(None)

    instruction, refs, failure = agents_handoff_runtime.execute_handoff_flow(
        store=store,
        contract={"task_id": "task-1", "handoff_chain": {"max_handoffs": 2}},
        run_id="run-1",
        task_id="task-1",
        instruction="initial",
        owner_agent={"role": "PM"},
        assigned_agent={"role": "WORKER"},
        owner_role="PM",
        assigned_role="WORKER",
        chain_roles=["PM", "WORKER"],
        schema_root=tmp_path,
        agent_cls=_Agent,
        run_streamed=_run_streamed,
        handoff_instructions=_handoff_instructions,
        record_transcript=transcripts.append,
        flush_transcript=lambda: flushed.append("flush"),
        failure_result=_failure_result,
        sha256_text=_sha256_text,
    )

    assert instruction == "initial"
    assert refs == {}
    assert failure is not None
    assert failure["reason"] == "agents sdk handoff failed"
    assert flushed == ["flush"]


def test_single_handoff_not_required_returns_unchanged(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(agents_handoff_runtime.agents_handoff, "_handoff_required", lambda _contract: False)

    instruction, refs, failure = agents_handoff_runtime.execute_handoff_flow(
        store=_Store(),
        contract={"task_id": "task-1"},
        run_id="run-1",
        task_id="task-1",
        instruction="keep",
        owner_agent={"role": "PM"},
        assigned_agent={"role": "WORKER"},
        owner_role="PM",
        assigned_role="WORKER",
        chain_roles=[],
        schema_root=tmp_path,
        agent_cls=_Agent,
        run_streamed=lambda *_args, **_kwargs: _Result("unused"),  # type: ignore[arg-type]
        handoff_instructions=_handoff_instructions,
        record_transcript=lambda _payload: None,
        flush_transcript=lambda: None,
        failure_result=_failure_result,
        sha256_text=_sha256_text,
    )

    assert instruction == "keep"
    assert refs == {}
    assert failure is None


def test_single_handoff_success(monkeypatch, tmp_path: Path) -> None:
    store = _Store()
    transcripts: list[dict[str, Any]] = []

    monkeypatch.setattr(agents_handoff_runtime.agents_handoff, "_handoff_required", lambda _contract: True)
    monkeypatch.setattr(agents_handoff_runtime.agents_handoff, "_handoff_prompt", lambda _task_id, text: text)
    monkeypatch.setattr(
        agents_handoff_runtime.agents_handoff,
        "_parse_handoff_payload",
        lambda _output, instruction_sha256=None: (
            {"summary": "ok", "risks": ["r1"], "instruction_sha256": instruction_sha256 or ""},
            {"summary": "ok", "risks": ["r1"], "instruction_sha256": instruction_sha256 or ""},
        ),
    )

    class _Validator:
        def __init__(self, schema_root: Path) -> None:
            self.schema_root = schema_root

        def validate_report(self, payload: dict[str, Any], _schema: str) -> None:
            assert payload["summary"] == "ok"

    monkeypatch.setattr(agents_handoff_runtime, "ContractValidator", _Validator)

    async def _run_streamed(_agent: _Agent, _prompt: str) -> _Result:
        return _Result("raw-output")

    instruction, refs, failure = agents_handoff_runtime.execute_handoff_flow(
        store=store,
        contract={"task_id": "task-1"},
        run_id="run-1",
        task_id="task-1",
        instruction="initial",
        owner_agent={"role": "PM"},
        assigned_agent={"role": "WORKER"},
        owner_role="PM",
        assigned_role="WORKER",
        chain_roles=[],
        schema_root=tmp_path,
        agent_cls=_Agent,
        run_streamed=_run_streamed,
        handoff_instructions=_handoff_instructions,
        record_transcript=transcripts.append,
        flush_transcript=lambda: None,
        failure_result=_failure_result,
        sha256_text=_sha256_text,
    )

    assert instruction == "initial"
    assert refs["handoff_chain"] == ["PM", "WORKER"]
    assert refs["instruction_sha256"] == "sha::initial"
    assert refs["instruction_final_sha256"] == "sha::initial"
    assert failure is None
    assert transcripts[-1]["kind"] == "handoff_result"


def test_single_handoff_legacy_payload_translates_to_schema_compliant_payload(monkeypatch, tmp_path: Path) -> None:
    store = _Store()

    monkeypatch.setattr(agents_handoff_runtime.agents_handoff, "_handoff_required", lambda _contract: True)
    monkeypatch.setattr(agents_handoff_runtime.agents_handoff, "_handoff_prompt", lambda _task_id, text: text)

    def _legacy_parse(_output: str) -> tuple[str, dict[str, Any]]:
        return (
            "legacy instruction",
            {"summary": "ok", "risks": ["r1"], "instruction": "legacy instruction"},
        )

    monkeypatch.setattr(agents_handoff_runtime.agents_handoff, "_parse_handoff_payload", _legacy_parse)

    class _Validator:
        def __init__(self, schema_root: Path) -> None:
            self.schema_root = schema_root

        def validate_report(self, payload: dict[str, Any], _schema: str) -> None:
            assert payload["summary"] == "ok"
            assert payload["risks"] == ["r1"]
            assert payload["instruction_sha256"] == "sha::initial"
            assert "instruction" not in payload

    monkeypatch.setattr(agents_handoff_runtime, "ContractValidator", _Validator)

    async def _run_streamed(_agent: _Agent, _prompt: str) -> _Result:
        return _Result("raw-output")

    instruction, refs, failure = agents_handoff_runtime.execute_handoff_flow(
        store=store,
        contract={"task_id": "task-1"},
        run_id="run-1",
        task_id="task-1",
        instruction="initial",
        owner_agent={"role": "PM"},
        assigned_agent={"role": "WORKER"},
        owner_role="PM",
        assigned_role="WORKER",
        chain_roles=[],
        schema_root=tmp_path,
        agent_cls=_Agent,
        run_streamed=_run_streamed,
        handoff_instructions=_handoff_instructions,
        record_transcript=lambda _payload: None,
        flush_transcript=lambda: None,
        failure_result=_failure_result,
        sha256_text=_sha256_text,
    )

    assert instruction == "initial"
    assert refs["instruction_sha256"] == "sha::initial"
    assert refs["instruction_final_sha256"] == "sha::initial"
    assert failure is None


def test_single_handoff_timeout_fail_open(monkeypatch, tmp_path: Path) -> None:
    store = _Store()
    transcripts: list[dict[str, Any]] = []

    monkeypatch.setenv("CORTEXPILOT_AGENTS_HANDOFF_TIMEOUT_FAIL_OPEN", "1")
    monkeypatch.setattr(agents_handoff_runtime.agents_handoff, "_handoff_required", lambda _contract: True)
    monkeypatch.setattr(agents_handoff_runtime.agents_handoff, "_handoff_prompt", lambda _task_id, text: text)

    async def _run_streamed(_agent: _Agent, _prompt: str) -> _Result:
        raise RuntimeError("Request timed out.")

    instruction, refs, failure = agents_handoff_runtime.execute_handoff_flow(
        store=store,
        contract={"task_id": "task-1"},
        run_id="run-1",
        task_id="task-1",
        instruction="initial",
        owner_agent={"role": "PM"},
        assigned_agent={"role": "WORKER"},
        owner_role="PM",
        assigned_role="WORKER",
        chain_roles=[],
        schema_root=tmp_path,
        agent_cls=_Agent,
        run_streamed=_run_streamed,
        handoff_instructions=_handoff_instructions,
        record_transcript=transcripts.append,
        flush_transcript=lambda: None,
        failure_result=_failure_result,
        sha256_text=_sha256_text,
    )

    assert instruction == "initial"
    assert refs == {}
    assert failure is None
    assert transcripts[-1]["kind"] == "handoff_timeout_fail_open"


def test_single_handoff_error_missing_output_invalid_and_schema(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("CORTEXPILOT_AGENTS_HANDOFF_TIMEOUT_FAIL_OPEN", raising=False)
    monkeypatch.setattr(agents_handoff_runtime.agents_handoff, "_handoff_required", lambda _contract: True)
    monkeypatch.setattr(agents_handoff_runtime.agents_handoff, "_handoff_prompt", lambda _task_id, text: text)

    # generic error
    transcripts_error: list[dict[str, Any]] = []
    flushed_error: list[str] = []

    async def _run_error(_agent: _Agent, _prompt: str) -> _Result:
        raise RuntimeError("boom")

    _, _, failure_error = agents_handoff_runtime.execute_handoff_flow(
        store=_Store(),
        contract={"task_id": "task-1"},
        run_id="run-1",
        task_id="task-1",
        instruction="initial",
        owner_agent={"role": "PM"},
        assigned_agent={"role": "WORKER"},
        owner_role="PM",
        assigned_role="WORKER",
        chain_roles=[],
        schema_root=tmp_path,
        agent_cls=_Agent,
        run_streamed=_run_error,
        handoff_instructions=_handoff_instructions,
        record_transcript=transcripts_error.append,
        flush_transcript=lambda: flushed_error.append("flush"),
        failure_result=_failure_result,
        sha256_text=_sha256_text,
    )
    assert failure_error is not None
    assert failure_error["reason"] == "agents sdk handoff failed"
    assert transcripts_error[-1]["kind"] == "handoff_error"
    assert flushed_error == ["flush"]

    # missing output
    transcripts_missing: list[dict[str, Any]] = []
    flushed_missing: list[str] = []

    async def _run_missing(_agent: _Agent, _prompt: str) -> _Result:
        return _Result(None)

    _, _, failure_missing = agents_handoff_runtime.execute_handoff_flow(
        store=_Store(),
        contract={"task_id": "task-1"},
        run_id="run-1",
        task_id="task-1",
        instruction="initial",
        owner_agent={"role": "PM"},
        assigned_agent={"role": "WORKER"},
        owner_role="PM",
        assigned_role="WORKER",
        chain_roles=[],
        schema_root=tmp_path,
        agent_cls=_Agent,
        run_streamed=_run_missing,
        handoff_instructions=_handoff_instructions,
        record_transcript=transcripts_missing.append,
        flush_transcript=lambda: flushed_missing.append("flush"),
        failure_result=_failure_result,
        sha256_text=_sha256_text,
    )
    assert failure_missing is not None
    assert failure_missing["reason"] == "handoff output missing"
    assert transcripts_missing[-1]["kind"] == "handoff_output_missing"
    assert flushed_missing == ["flush"]

    # invalid payload
    store_invalid = _Store()
    transcripts_invalid: list[dict[str, Any]] = []
    flushed_invalid: list[str] = []
    monkeypatch.setattr(
        agents_handoff_runtime.agents_handoff,
        "_parse_handoff_payload",
        lambda _output, instruction_sha256=None: (None, {"error": "invalid handoff payload"}),
    )

    async def _run_invalid(_agent: _Agent, _prompt: str) -> _Result:
        return _Result("raw-output")

    _, _, failure_invalid = agents_handoff_runtime.execute_handoff_flow(
        store=store_invalid,
        contract={"task_id": "task-1"},
        run_id="run-1",
        task_id="task-1",
        instruction="initial",
        owner_agent={"role": "PM"},
        assigned_agent={"role": "WORKER"},
        owner_role="PM",
        assigned_role="WORKER",
        chain_roles=[],
        schema_root=tmp_path,
        agent_cls=_Agent,
        run_streamed=_run_invalid,
        handoff_instructions=_handoff_instructions,
        record_transcript=transcripts_invalid.append,
        flush_transcript=lambda: flushed_invalid.append("flush"),
        failure_result=_failure_result,
        sha256_text=_sha256_text,
    )
    assert failure_invalid is not None
    assert failure_invalid["reason"] == "invalid handoff payload"
    assert any(event[1]["event"] == "AGENT_HANDOFF_INVALID" for event in store_invalid.events)
    assert flushed_invalid == ["flush"]

    # schema invalid
    transcripts_schema: list[dict[str, Any]] = []
    flushed_schema: list[str] = []
    monkeypatch.setattr(
        agents_handoff_runtime.agents_handoff,
        "_parse_handoff_payload",
        lambda _output, instruction_sha256=None: (
            {"summary": "ok", "risks": [], "instruction_sha256": instruction_sha256 or ""},
            {"summary": "ok", "risks": [], "instruction_sha256": instruction_sha256 or ""},
        ),
    )

    class _BadValidator:
        def __init__(self, schema_root: Path) -> None:
            self.schema_root = schema_root

        def validate_report(self, _payload: dict[str, Any], _schema: str) -> None:
            raise ValueError("schema invalid")

    monkeypatch.setattr(agents_handoff_runtime, "ContractValidator", _BadValidator)

    _, _, failure_schema = agents_handoff_runtime.execute_handoff_flow(
        store=_Store(),
        contract={"task_id": "task-1"},
        run_id="run-1",
        task_id="task-1",
        instruction="initial",
        owner_agent={"role": "PM"},
        assigned_agent={"role": "WORKER"},
        owner_role="PM",
        assigned_role="WORKER",
        chain_roles=[],
        schema_root=tmp_path,
        agent_cls=_Agent,
        run_streamed=_run_invalid,
        handoff_instructions=_handoff_instructions,
        record_transcript=transcripts_schema.append,
        flush_transcript=lambda: flushed_schema.append("flush"),
        failure_result=_failure_result,
        sha256_text=_sha256_text,
    )
    assert failure_schema is not None
    assert failure_schema["reason"] == "handoff schema invalid"
    assert flushed_schema == ["flush"]
