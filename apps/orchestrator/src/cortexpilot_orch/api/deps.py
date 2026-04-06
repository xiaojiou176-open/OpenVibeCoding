from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from fastapi import HTTPException, Request


AnyHandler = Callable[..., Any]
RunsDepsProvider = Callable[[], "RunsRouteDeps"]
AdminDepsProvider = Callable[[], "AdminRouteDeps"]


_ROUTE_DEPS_NOT_CONFIGURED_CODE = "ROUTE_DEPS_NOT_CONFIGURED"
_ROUTE_DEPS_NOT_CONFIGURED_ERROR = "route dependencies not configured"


class RouteDepsNotConfiguredError(RuntimeError):
    def __init__(self, group_name: str) -> None:
        self.group_name = group_name
        super().__init__(f"{group_name} routes not configured")


def build_route_deps_not_configured_http_error(*, group_name: str, operation: str) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": _ROUTE_DEPS_NOT_CONFIGURED_CODE,
            "error": _ROUTE_DEPS_NOT_CONFIGURED_ERROR,
            "group": group_name,
            "operation": operation,
        },
    )


@dataclass(frozen=True)
class RunsRouteDeps:
    list_runs: AnyHandler
    list_queue: AnyHandler
    preview_enqueue_run_queue: AnyHandler
    enqueue_run_queue: AnyHandler
    cancel_queue_item: AnyHandler
    run_next_queue: AnyHandler
    list_workflows: AnyHandler
    get_workflow: AnyHandler
    get_workflow_operator_copilot_brief: AnyHandler
    get_run: AnyHandler
    get_events: AnyHandler
    stream_events: AnyHandler
    get_diff: AnyHandler
    get_reports: AnyHandler
    get_artifacts: AnyHandler
    get_search: AnyHandler
    get_operator_copilot_brief: AnyHandler
    promote_evidence: AnyHandler
    rollback_run: AnyHandler
    reject_run: AnyHandler
    list_contracts: AnyHandler
    list_events: AnyHandler
    list_diff_gate: AnyHandler
    list_reviews: AnyHandler
    list_tests: AnyHandler
    list_agents: AnyHandler
    list_agents_status: AnyHandler
    get_role_config: AnyHandler
    preview_role_config: AnyHandler
    apply_role_config: AnyHandler
    list_policies: AnyHandler
    list_locks: AnyHandler
    list_worktrees: AnyHandler
    replay_run: AnyHandler
    verify_run: AnyHandler
    reexec_run: AnyHandler


@dataclass(frozen=True)
class AdminRouteDeps:
    list_pending_approvals: AnyHandler
    approve_god_mode_mutation: AnyHandler
    get_run_events: AnyHandler


_runs_route_deps_provider: RunsDepsProvider | None = None
_admin_route_deps_provider: AdminDepsProvider | None = None


def configure_runs_route_deps_provider(provider: RunsDepsProvider | None) -> None:
    global _runs_route_deps_provider
    _runs_route_deps_provider = provider


def configure_admin_route_deps_provider(provider: AdminDepsProvider | None) -> None:
    global _admin_route_deps_provider
    _admin_route_deps_provider = provider


def _resolve_mapping_from_state(request: Request | None, state_attr: str) -> Mapping[str, Any] | None:
    if request is None:
        return None
    handlers = getattr(request.app.state, state_attr, None)
    if not isinstance(handlers, Mapping):
        return None
    return handlers


def _bind_handler(
    mapping: Mapping[str, Any],
    key: str,
    group_name: str,
    *,
    operation: str | None = None,
) -> AnyHandler:
    operation_name = operation or key

    def _handler(*args: Any, **kwargs: Any) -> Any:
        target = mapping.get(key)
        if not callable(target):
            raise build_route_deps_not_configured_http_error(
                group_name=group_name,
                operation=operation_name,
            )
        return target(*args, **kwargs)

    return _handler


def build_runs_route_deps_from_mapping(mapping: Mapping[str, Any]) -> RunsRouteDeps:
    return RunsRouteDeps(
        list_runs=_bind_handler(mapping, "list_runs", "runs"),
        list_queue=_bind_handler(mapping, "list_queue", "runs"),
        preview_enqueue_run_queue=_bind_handler(mapping, "preview_enqueue_run_queue", "runs"),
        enqueue_run_queue=_bind_handler(mapping, "enqueue_run_queue", "runs"),
        cancel_queue_item=_bind_handler(mapping, "cancel_queue_item", "runs"),
        run_next_queue=_bind_handler(mapping, "run_next_queue", "runs"),
        list_workflows=_bind_handler(mapping, "list_workflows", "runs"),
        get_workflow=_bind_handler(mapping, "get_workflow", "runs"),
        get_workflow_operator_copilot_brief=_bind_handler(mapping, "get_workflow_operator_copilot_brief", "runs"),
        get_run=_bind_handler(mapping, "get_run", "runs"),
        get_events=_bind_handler(mapping, "get_events", "runs"),
        stream_events=_bind_handler(mapping, "stream_events", "runs"),
        get_diff=_bind_handler(mapping, "get_diff", "runs"),
        get_reports=_bind_handler(mapping, "get_reports", "runs"),
        get_artifacts=_bind_handler(mapping, "get_artifacts", "runs"),
        get_search=_bind_handler(mapping, "get_search", "runs"),
        get_operator_copilot_brief=_bind_handler(mapping, "get_operator_copilot_brief", "runs"),
        promote_evidence=_bind_handler(mapping, "promote_evidence", "runs"),
        rollback_run=_bind_handler(mapping, "rollback_run", "runs"),
        reject_run=_bind_handler(mapping, "reject_run", "runs"),
        list_contracts=_bind_handler(mapping, "list_contracts", "runs"),
        list_events=_bind_handler(mapping, "list_events", "runs"),
        list_diff_gate=_bind_handler(mapping, "list_diff_gate", "runs"),
        list_reviews=_bind_handler(mapping, "list_reviews", "runs"),
        list_tests=_bind_handler(mapping, "list_tests", "runs"),
        list_agents=_bind_handler(mapping, "list_agents", "runs"),
        list_agents_status=_bind_handler(mapping, "list_agents_status", "runs"),
        get_role_config=_bind_handler(mapping, "get_role_config", "runs"),
        preview_role_config=_bind_handler(mapping, "preview_role_config", "runs"),
        apply_role_config=_bind_handler(mapping, "apply_role_config", "runs"),
        list_policies=_bind_handler(mapping, "list_policies", "runs"),
        list_locks=_bind_handler(mapping, "list_locks", "runs"),
        list_worktrees=_bind_handler(mapping, "list_worktrees", "runs"),
        replay_run=_bind_handler(mapping, "replay_run", "runs"),
        verify_run=_bind_handler(mapping, "verify_run", "runs"),
        reexec_run=_bind_handler(mapping, "reexec_run", "runs"),
    )


def build_admin_route_deps_from_mapping(mapping: Mapping[str, Any]) -> AdminRouteDeps:
    return AdminRouteDeps(
        list_pending_approvals=_bind_handler(mapping, "list_pending_approvals", "admin"),
        approve_god_mode_mutation=_bind_handler(
            mapping,
            "approve_god_mode_mutation",
            "admin",
            operation="approve_god_mode:mutation",
        ),
        get_run_events=_bind_handler(mapping, "get_run_events", "admin"),
    )


def resolve_runs_route_deps(request: Request | None = None) -> RunsRouteDeps | None:
    if _runs_route_deps_provider is not None:
        return _runs_route_deps_provider()
    mapping = _resolve_mapping_from_state(request, "routes_runs_handlers")
    if mapping is None:
        return None
    return build_runs_route_deps_from_mapping(mapping)


def resolve_admin_route_deps(request: Request | None = None) -> AdminRouteDeps | None:
    if _admin_route_deps_provider is not None:
        return _admin_route_deps_provider()
    mapping = _resolve_mapping_from_state(request, "routes_admin_handlers")
    if mapping is None:
        return None
    return build_admin_route_deps_from_mapping(mapping)


def get_runs_route_deps(request: Request) -> RunsRouteDeps:
    deps = resolve_runs_route_deps(request)
    if deps is None:
        raise build_route_deps_not_configured_http_error(
            group_name="runs",
            operation="depends:get_runs_route_deps",
        )
    return deps


def get_admin_route_deps(request: Request) -> AdminRouteDeps:
    deps = resolve_admin_route_deps(request)
    if deps is None:
        raise build_route_deps_not_configured_http_error(
            group_name="admin",
            operation="depends:get_admin_route_deps",
        )
    return deps
