from __future__ import annotations

from collections.abc import Callable
import json
from pathlib import Path
from typing import Any

from cortexpilot_orch.contract.compiler import build_prompt_artifact, build_role_binding_summary
from cortexpilot_orch.store.run_store import RunStore


class ContractStateWriter:
    def __init__(
        self,
        *,
        store: RunStore,
        run_id: str,
        task_id: str,
        contract: dict[str, Any],
        manifest: dict[str, Any] | None,
        hash_contract_fn: Callable[[dict[str, Any]], str],
        write_manifest_fn: Callable[[RunStore, str, dict[str, Any]], None],
        write_contract_signature_fn: Callable[[RunStore, str, Path], tuple[str | None, str | None]],
        now_ts_fn: Callable[[], str],
    ) -> None:
        self._store = store
        self._run_id = run_id
        self._task_id = task_id
        self._contract = contract
        self._manifest = manifest
        self._hash_contract_fn = hash_contract_fn
        self._write_manifest_fn = write_manifest_fn
        self._write_contract_signature_fn = write_contract_signature_fn
        self._now_ts_fn = now_ts_fn

    def persist(
        self,
        *,
        mark_failure_manifest: bool = False,
        failure_reason: str = "",
        baseline_ref_for_manifest: str = "",
        baseline_commit: str = "",
        write_signature: bool = False,
        ensure_evidence_bundle_fn: Callable[[RunStore, str, dict[str, Any], str], None] | None = None,
    ) -> None:
        persist_contract_state(
            store=self._store,
            run_id=self._run_id,
            task_id=self._task_id,
            contract=self._contract,
            manifest=self._manifest,
            hash_contract_fn=self._hash_contract_fn,
            write_manifest_fn=self._write_manifest_fn,
            write_contract_signature_fn=self._write_contract_signature_fn,
            now_ts_fn=self._now_ts_fn,
            mark_failure_manifest=mark_failure_manifest,
            failure_reason=failure_reason,
            baseline_ref_for_manifest=baseline_ref_for_manifest,
            baseline_commit=baseline_commit,
            write_signature=write_signature,
            ensure_evidence_bundle_fn=ensure_evidence_bundle_fn,
        )


def notify_temporal_start_and_fail_if_required(
    *,
    run_id: str,
    task_id: str,
    runner_name: str,
    trace_id: str,
    store: RunStore,
    manifest: dict[str, Any],
    now_ts_fn: Callable[[], str],
    write_manifest_fn: Callable[[RunStore, str, dict[str, Any]], None],
    notify_run_started_fn: Callable[[str, dict[str, Any]], dict[str, Any]],
    temporal_required_fn: Callable[[], bool],
) -> bool:
    temporal_start = notify_run_started_fn(
        run_id,
        {
            "run_id": run_id,
            "task_id": task_id,
            "runner": runner_name,
            "trace_id": trace_id,
        },
    )
    store.append_event(
        run_id,
        {
            "level": "INFO" if temporal_start.get("ok") else "ERROR",
            "event": "TEMPORAL_NOTIFY_START",
            "run_id": run_id,
            "meta": temporal_start,
        },
    )
    if not temporal_start.get("ok") and temporal_required_fn():
        manifest["status"] = "FAILURE"
        manifest["failure_reason"] = "temporal notify failed"
        manifest["end_ts"] = now_ts_fn()
        write_manifest_fn(store, run_id, manifest)
        return True
    return False


def write_running_contract_manifest(
    *,
    store: RunStore,
    run_id: str,
    task_id: str,
    manifest: dict[str, Any] | None,
    assigned_agent: dict[str, Any],
    run_dir: Path,
    manifest_task_role_fn: Callable[[dict[str, Any] | None], str],
    artifact_ref_from_path_fn: Callable[..., dict[str, Any]],
    write_manifest_fn: Callable[[RunStore, str, dict[str, Any]], None],
) -> None:
    if manifest is None:
        return
    contract_ref = artifact_ref_from_path_fn(
        "contract.json",
        run_dir,
        "contract.json",
        media_type="application/json",
    )
    manifest["tasks"] = [
        {
            "task_id": task_id,
            "role": manifest_task_role_fn(assigned_agent),
            "assigned_agent_id": assigned_agent.get("agent_id", ""),
            "thread_id": assigned_agent.get("codex_thread_id", ""),
            "status": "RUNNING",
            "contract": contract_ref,
        }
    ]
    manifest["artifacts"] = [contract_ref]
    write_manifest_fn(store, run_id, manifest)


def persist_contract_state(
    *,
    store: RunStore,
    run_id: str,
    task_id: str,
    contract: dict[str, Any],
    manifest: dict[str, Any] | None,
    hash_contract_fn: Callable[[dict[str, Any]], str],
    write_manifest_fn: Callable[[RunStore, str, dict[str, Any]], None],
    write_contract_signature_fn: Callable[[RunStore, str, Path], tuple[str | None, str | None]],
    now_ts_fn: Callable[[], str],
    mark_failure_manifest: bool = False,
    failure_reason: str = "",
    baseline_ref_for_manifest: str = "",
    baseline_commit: str = "",
    write_signature: bool = False,
    ensure_evidence_bundle_fn: Callable[[RunStore, str, dict[str, Any], str], None] | None = None,
) -> None:
    if manifest is not None:
        if baseline_ref_for_manifest and isinstance(manifest.get("repo"), dict):
            manifest["repo"]["baseline_ref"] = baseline_ref_for_manifest
        integrity = manifest.get("integrity") if isinstance(manifest.get("integrity"), dict) else {}
        integrity["contract_sha256"] = hash_contract_fn(contract)
        manifest["integrity"] = integrity
        manifest["role_binding_summary"] = build_role_binding_summary(contract)
        if mark_failure_manifest:
            manifest["status"] = "FAILURE"
            manifest["failure_reason"] = failure_reason
            manifest["end_ts"] = now_ts_fn()
        write_manifest_fn(store, run_id, manifest)
    if baseline_commit:
        store.write_git_baseline(run_id, baseline_commit)
    contract_path_written = store.write_contract(run_id, contract)
    if write_signature:
        sig_path, sig_value = write_contract_signature_fn(store, run_id, contract_path_written)
        if sig_path and manifest is not None:
            integrity = manifest.get("integrity") if isinstance(manifest.get("integrity"), dict) else {}
            integrity["contract_signature_path"] = sig_path
            if sig_value:
                integrity["contract_signature_sha256"] = sig_value
            manifest["integrity"] = integrity
            write_manifest_fn(store, run_id, manifest)
            store.append_event(
                run_id,
                {
                    "level": "INFO",
                    "event": "CONTRACT_SIGNATURE_WRITTEN",
                    "run_id": run_id,
                    "meta": {"path": sig_path},
                },
            )
        elif sig_path is None and sig_value is None:
            store.append_event(
                run_id,
                {
                    "level": "WARN",
                    "event": "CONTRACT_SIGNATURE_SKIPPED",
                    "run_id": run_id,
                    "meta": {"reason": "hmac key missing or signature skipped"},
                },
            )
        elif sig_path is None and sig_value:
            store.append_event(
                run_id,
                {
                    "level": "ERROR",
                    "event": "CONTRACT_SIGNATURE_SKIPPED",
                    "run_id": run_id,
                    "meta": {"reason": sig_value},
                },
            )
    store.write_task_contract(run_id, task_id, contract)
    store.write_active_contract(run_id, contract)
    prompt_artifact = build_prompt_artifact(contract, run_id=run_id, task_id=task_id)
    prompt_artifact_path = store.write_artifact(
        run_id,
        "prompt_artifact.json",
        json.dumps(prompt_artifact, ensure_ascii=False, indent=2),
    )
    store.append_event(
        run_id,
        {
            "level": "INFO",
            "event": "PROMPT_ARTIFACT_WRITTEN",
            "run_id": run_id,
            "task_id": task_id,
            "meta": {"path": str(prompt_artifact_path.relative_to(store.run_dir(run_id)))},
        },
    )
    if ensure_evidence_bundle_fn is not None and failure_reason:
        ensure_evidence_bundle_fn(store, run_id, contract, failure_reason)
