from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

BuildResultFn = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class PreflightOps:
    find_wide_paths: Callable[..., list[str]]
    validate_integrated_tools: Callable[..., dict[str, Any]]
    validate_mcp_concurrency: Callable[..., dict[str, Any]]
    validate_mcp_tools: Callable[..., dict[str, Any]]
    requires_network_items: Callable[..., bool]
    validate_network_policy: Callable[..., dict[str, Any]]
    validate_sampling_policy: Callable[..., dict[str, Any]]
    validate_command: Callable[..., dict[str, Any]]
    acquire_lock_with_cleanup: Callable[..., tuple[bool, list[str], list[str]]]
    release_lock: Callable[..., Any]
    resolve_lock_ttl: Callable[..., tuple[int, str]]
    detect_agents_overrides: Callable[..., list[str]]
    collect_patch_artifacts: Callable[..., list[Path]]
    should_apply_dependency_patches: Callable[..., bool]
    apply_dependency_patches: Callable[..., bool]
    load_sampling_requests: Callable[..., tuple[dict[str, Any] | None, str | None]]
    load_search_requests: Callable[..., tuple[dict[str, Any] | None, str | None]]
    load_browser_tasks: Callable[..., tuple[dict[str, Any] | None, str | None]]
    load_tampermonkey_tasks: Callable[..., tuple[dict[str, Any] | None, str | None]]
    requires_human_approval: Callable[..., bool]
    await_human_approval: Callable[..., bool]
    auto_lock_cleanup_requested: Callable[[], bool]
    force_unlock_requested: Callable[[], bool]
    god_mode_timeout_sec: Callable[[], int]
    allowed_paths: Callable[..., list[str]]
    agent_role: Callable[..., str]
    is_search_role: Callable[..., bool]
    network_policy: Callable[..., str]
    filesystem_policy: Callable[..., str]
    mcp_tools: Callable[..., list[str]]
    forbidden_actions: Callable[..., list[str]]


@dataclass
class PreflightState:
    failure_reason: str = ""
    policy_gate_result: dict[str, Any] | None = None
    integrated_gate: dict[str, Any] | None = None
    network_gate: dict[str, Any] | None = None
    mcp_gate: dict[str, Any] | None = None
    sampling_gate: dict[str, Any] | None = None
    tool_gate: dict[str, Any] | None = None
    human_approval_required: bool = False
    human_approved: bool | None = None
    search_request: dict[str, Any] | None = None
    browser_request: dict[str, Any] | None = None
    tamper_request: dict[str, Any] | None = None
    sampling_request: dict[str, Any] | None = None
    worktree_path: Path | None = None
    locked: bool = False
    allowed_paths: list[str] = field(default_factory=list)
    override_paths: list[str] = field(default_factory=list)
    wide_paths: list[str] = field(default_factory=list)
