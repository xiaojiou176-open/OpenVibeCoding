from __future__ import annotations

from typing import Any

from openvibecoding_orch.scheduler import approval_flow, artifact_pipeline, policy_pipeline
from openvibecoding_orch.scheduler.runtime_utils import schema_root
from openvibecoding_orch.scheduler.scheduler_bridge_contract import (
    ContractStateWriter,
    notify_temporal_start_and_fail_if_required,
    persist_contract_state,
    write_running_contract_manifest,
)
from openvibecoding_orch.scheduler.scheduler_bridge_finalize import finalize_execute_task_run, finalize_run
from openvibecoding_orch.scheduler.scheduler_bridge_runtime import (
    apply_rollback,
    execute_replay_action,
    max_retries,
    retry_backoff,
    run_browser_tasks,
    run_optional_tool_requests,
    run_sampling_requests,
    run_search_pipeline,
    run_tampermonkey_tasks,
    scoped_revert,
    select_runner,
)


def apply_role_defaults(
    contract: dict[str, Any],
    registry: dict[str, Any] | None,
    filesystem_order: dict[str, int],
    shell_order: dict[str, int],
    network_order: dict[str, int],
) -> tuple[dict[str, Any], list[str]]:
    return policy_pipeline.apply_role_defaults(
        contract=contract,
        registry=registry,
        filesystem_order=filesystem_order,
        shell_order=shell_order,
        network_order=network_order,
    )


def requires_human_approval(contract: dict[str, Any], requires_network: bool) -> bool:
    return approval_flow.requires_human_approval(
        requires_network=requires_network,
        filesystem_policy=policy_pipeline.filesystem_policy(contract),
        network_policy=policy_pipeline.network_policy(contract),
        shell_policy=policy_pipeline.shell_policy(contract),
    )


def await_human_approval(
    run_id: str,
    store: Any,
    reason: list[str] | None = None,
    actions: list[str] | None = None,
    verify_steps: list[str] | None = None,
    resume_step: str | None = None,
) -> bool:
    return approval_flow.await_human_approval(
        run_id=run_id,
        store=store,
        reason=reason,
        actions=actions,
        verify_steps=verify_steps,
        resume_step=resume_step,
    )


def safe_artifact_path(uri: str, repo_root: Any) -> Any:
    return artifact_pipeline.safe_artifact_path(uri, repo_root)


def load_json_artifact(artifact: dict[str, Any], repo_root: Any) -> tuple[object | None, str | None, Any]:
    return artifact_pipeline.load_json_artifact(artifact, repo_root)


def load_search_requests(contract: dict[str, Any], repo_root: Any) -> tuple[dict[str, Any] | None, str | None]:
    return artifact_pipeline.load_search_requests(contract, repo_root, schema_root())


def load_browser_tasks(contract: dict[str, Any], repo_root: Any) -> tuple[dict[str, Any] | None, str | None]:
    return artifact_pipeline.load_browser_tasks(contract, repo_root, schema_root())


def load_tampermonkey_tasks(contract: dict[str, Any], repo_root: Any) -> tuple[dict[str, Any] | None, str | None]:
    return artifact_pipeline.load_tampermonkey_tasks(contract, repo_root, schema_root())
