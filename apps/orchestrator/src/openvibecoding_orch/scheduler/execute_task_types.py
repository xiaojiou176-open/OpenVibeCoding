from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openvibecoding_orch.store.run_store import RunStore


@dataclass
class ExecutionSetup:
    store: RunStore
    contract: dict[str, Any]
    run_id: str
    task_id: str
    trace_id: str
    manifest: dict[str, Any]
    state_writer: Any
    runner_name: str
    allow_codex_exec: bool
    mcp_only: bool
    workflow_id: str
    workflow_info: dict[str, Any] | None
    assigned_agent: dict[str, Any]
    policy_pack: str
    profile: str
    start_ts: str
    codex_version: str
    git_version: str
    trace_url: str
    diagnostic_mode: bool


@dataclass
class ExecutionRuntimeState:
    worktree_path: Path | None = None
    locked: bool = False
    allowed_paths: list[str] = field(default_factory=list)
    status: str = "FAILURE"
    failure_reason: str = ""
    baseline_ref: str = ""
    attempt: int = 0
    runner_summary: str = ""
    diff_gate_result: dict[str, Any] | None = None
    tests_result: dict[str, Any] | None = None
    review_report: dict[str, Any] | None = None
    task_result: dict[str, Any] | None = None
    test_report: dict[str, Any] | None = None
    review_gate_result: dict[str, Any] | None = None
    policy_gate_result: dict[str, Any] | None = None
    integrated_gate: dict[str, Any] | None = None
    network_gate: dict[str, Any] | None = None
    mcp_gate: dict[str, Any] | None = None
    sampling_gate: dict[str, Any] | None = None
    tool_gate: dict[str, Any] | None = None
    head_ref: str = ""
    human_approval_required: bool = False
    human_approved: bool | None = None
    search_request: dict[str, Any] | None = None
    browser_request: dict[str, Any] | None = None
    tamper_request: dict[str, Any] | None = None
    sampling_request: dict[str, Any] | None = None
