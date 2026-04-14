from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from openvibecoding_orch.chain import chain_lifecycle
from openvibecoding_orch.chain.helpers import _normalize_depends, _step_task_id
from openvibecoding_orch.chain.parsers import _extract_contracts, _extract_handoff_payload
from openvibecoding_orch.chain.runtime_helpers import (
    TERMINAL_RUN_STATUSES as _TERMINAL_RUN_STATUSES,
    apply_context_policy as _apply_context_policy,
    deep_merge_payload as _deep_merge_payload,
    dependency_artifact as _dependency_artifact,
    dependency_patch_artifact as _dependency_patch_artifact,
    filter_payload_keys as _filter_payload_keys,
    is_fanin_step as _is_fanin_step,
    load_manifest as _load_manifest,
    merge_artifacts as _merge_artifacts,
    merge_contract_overrides as _merge_contract_overrides,
    normalize_fanin_task_result as _normalize_fanin_task_result,
    normalize_run_status as _normalize_run_status,
    resolve_contract_from_dependency as _resolve_contract_from_dependency,
    schema_allowed_keys as _schema_allowed_keys,
    should_propagate_dependency_patch as _should_propagate_dependency_patch,
)
from openvibecoding_orch.contract.compiler import compile_plan
from openvibecoding_orch.contract.validator import ContractValidator
from openvibecoding_orch.store.run_store import RunStore

_HANDOFF_ROLE_ORDER = chain_lifecycle._HANDOFF_ROLE_ORDER
_agent_role = chain_lifecycle._agent_role
_validate_handoff_chain = chain_lifecycle._validate_handoff_chain
_load_task_result = chain_lifecycle._load_task_result


def execute_task_subprocess(
    *,
    store: RunStore,
    repo_root: Path,
    chain_run_id: str,
    contract_ref: Path,
    mock_mode: bool,
    timeout_sec: float | None,
) -> str:
    cmd = [sys.executable, "-m", "openvibecoding_orch.cli", "run", str(contract_ref)]
    if mock_mode:
        cmd.append("--mock")
    env = os.environ.copy()
    py_path = str((repo_root / "apps" / "orchestrator" / "src").resolve())
    if env.get("PYTHONPATH"):
        env["PYTHONPATH"] = f"{py_path}{os.pathsep}{env['PYTHONPATH']}"
    else:
        env["PYTHONPATH"] = py_path
    store.append_event(
        chain_run_id,
        {
            "level": "INFO",
            "event": "CHAIN_SUBPROCESS_LAUNCHED",
            "run_id": chain_run_id,
            "meta": {"cmd": cmd, "cwd": str(repo_root)},
        },
    )

    def _normalize_stream_text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return str(value)

    try:
        result = subprocess.run(
            cmd,
            cwd=repo_root,
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = _normalize_stream_text(exc.stdout)[:2000]
        stderr = _normalize_stream_text(exc.stderr)[:2000]
        store.append_event(
            chain_run_id,
            {
                "level": "ERROR",
                "event": "CHAIN_SUBPROCESS_TIMEOUT",
                "run_id": chain_run_id,
                "meta": {
                    "cmd": cmd,
                    "timeout_sec": timeout_sec,
                    "stdout": stdout,
                    "stderr": stderr,
                },
            },
        )
        return ""
    stdout = _normalize_stream_text(result.stdout)
    stderr = _normalize_stream_text(result.stderr)
    match = re.search(r"run_id=([A-Za-z0-9_\\-]+)", stdout)
    run_id = match.group(1) if match else ""
    store.append_event(
        chain_run_id,
        {
            "level": "INFO" if result.returncode == 0 else "ERROR",
            "event": "CHAIN_SUBPROCESS_COMPLETED",
            "run_id": chain_run_id,
            "meta": {
                "cmd": cmd,
                "exit_code": result.returncode,
                "stdout": stdout[:2000],
                "stderr": stderr[:2000],
                "run_id": run_id,
            },
        },
    )
    return run_id


def execute_chain_step(
    *,
    step_name: str,
    steps: list[dict[str, Any]],
    name_map: dict[str, int],
    group: str,
    chain_run_id: str,
    completed_runs: dict[str, str],
    completed_results: dict[str, dict[str, Any]],
    store: RunStore,
    validator: ContractValidator,
    execute_task: Callable[[Path, bool], str],
    execute_task_subprocess: Callable[[str, Path, bool], str],
    mock_mode: bool,
    use_subprocess: bool,
    ensure_output_schema_artifact_fn: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    idx = name_map[step_name]
    step = steps[idx]
    name = str(step.get("name", f"step_{idx}"))
    kind = str(step.get("kind", "")).strip()
    policy = step.get("context_policy") if isinstance(step, dict) else {}
    if not isinstance(policy, dict):
        policy = {}
    payload = step.get("payload")
    if not isinstance(payload, dict):
        return {
            "index": idx,
            "name": name,
            "kind": kind or "plan",
            "task_id": "unknown",
            "run_id": "",
            "status": "FAILURE",
            "failure_reason": "step payload invalid",
            "owner_agent": {},
            "assigned_agent": {},
        }
    depends = _normalize_depends(step.get("depends_on"))
    dep_artifacts: list[dict[str, Any]] = []
    for dep in depends:
        dep_run_id = completed_runs.get(dep, "")
        artifact = _dependency_artifact(store, dep, dep_run_id)
        if artifact:
            dep_artifacts.append(artifact)
        dep_step = steps[name_map[dep]] if dep in name_map else {}
        if _should_propagate_dependency_patch(dep_step):
            patch_artifact = _dependency_patch_artifact(store, dep, dep_run_id)
            if patch_artifact:
                dep_artifacts.append(patch_artifact)
    if dep_artifacts:
        store.append_event(
            chain_run_id,
            {
                "level": "INFO",
                "event": "CHAIN_DEP_ARTIFACTS_INJECTED",
                "run_id": chain_run_id,
                "meta": {
                    "step": name,
                    "depends_on": depends,
                    "artifacts": [item.get("name") for item in dep_artifacts],
                },
            },
        )
    if kind == "plan":
        payload = _merge_artifacts(payload, dep_artifacts)
        if depends:
            dep_name = depends[-1]
            dep_run_id = completed_runs.get(dep_name, "")
            dep_result = completed_results.get(dep_name)
            if dep_result is None and dep_run_id:
                dep_result = _load_task_result(store, dep_run_id)
            handoff_payload = _extract_handoff_payload(dep_result)
            if handoff_payload:
                allowed_keys = _schema_allowed_keys(
                    validator._schema_root, "plan.schema.json"
                )
                payload = _deep_merge_payload(
                    payload, _filter_payload_keys(handoff_payload, allowed_keys)
                )
        contract = compile_plan(payload)
    elif kind == "handoff":
        owner_agent = payload.get("owner_agent") if isinstance(payload.get("owner_agent"), dict) else {}
        assigned_agent = payload.get("assigned_agent") if isinstance(payload.get("assigned_agent"), dict) else {}
        owner_role = _agent_role(owner_agent)
        assigned_role = _agent_role(assigned_agent)
        if owner_role and owner_role not in _HANDOFF_ROLE_ORDER:
            return {
                "index": idx,
                "name": name,
                "kind": kind,
                "task_id": _step_task_id(kind, payload) or f"handoff_{idx}_{name}",
                "run_id": "",
                "status": "FAILURE",
                "failure_reason": f"handoff owner role invalid: {owner_role}",
                "owner_agent": owner_agent,
                "assigned_agent": assigned_agent,
            }
        if assigned_role and assigned_role not in _HANDOFF_ROLE_ORDER:
            return {
                "index": idx,
                "name": name,
                "kind": kind,
                "task_id": _step_task_id(kind, payload) or f"handoff_{idx}_{name}",
                "run_id": "",
                "status": "FAILURE",
                "failure_reason": f"handoff assigned role invalid: {assigned_role}",
                "owner_agent": owner_agent,
                "assigned_agent": assigned_agent,
            }
        task_id = _step_task_id(kind, payload) or f"handoff_{idx}_{name}"
        store.append_event(
            chain_run_id,
            {
                "level": "INFO",
                "event": "CHAIN_HANDOFF_STEP_MARKED",
                "run_id": chain_run_id,
                "meta": {
                    "index": idx,
                    "name": name,
                    "task_id": task_id,
                    "owner_role": owner_role,
                    "assigned_role": assigned_role,
                    "depends_on": depends,
                },
            },
        )
        return {
            "index": idx,
            "name": name,
            "kind": kind,
            "task_id": task_id,
            "run_id": chain_run_id,
            "status": "SUCCESS",
            "failure_reason": "",
            "owner_agent": owner_agent,
            "assigned_agent": assigned_agent,
        }
    elif kind == "contract":
        contract_from = payload.get("contract_from") if isinstance(payload, dict) else None
        if isinstance(contract_from, str) and contract_from.strip():
            dep_name = contract_from.strip()
            dep_run_id = completed_runs.get(dep_name, "")
            dep_result = completed_results.get(dep_name)
            if dep_result is None and dep_run_id:
                dep_result = _load_task_result(store, dep_run_id)
            contract_index = payload.get("contract_index") if isinstance(payload, dict) else None
            resolved = _resolve_contract_from_dependency(dep_result, contract_index)
            if resolved is None:
                contracts = _extract_contracts(dep_result)
                if contracts:
                    idx_val = 0
                    if contract_index is not None:
                        try:
                            idx_val = int(contract_index)
                        except (TypeError, ValueError):
                            idx_val = 0
                    if 0 <= idx_val < len(contracts):
                        resolved = contracts[idx_val]
            if not resolved:
                return {
                    "index": idx,
                    "name": name,
                    "kind": kind or "contract",
                    "task_id": _step_task_id(kind, payload),
                    "run_id": "",
                    "status": "FAILURE",
                    "failure_reason": "contract_from resolution failed",
                    "owner_agent": payload.get("owner_agent", {}) if isinstance(payload, dict) else {},
                    "assigned_agent": payload.get("assigned_agent", {}) if isinstance(payload, dict) else {},
                }
            overrides = payload.get("contract_overrides") if isinstance(payload, dict) else None
            resolved = _merge_contract_overrides(
                resolved,
                overrides if isinstance(overrides, dict) else None,
            )
            resolved = ensure_output_schema_artifact_fn(resolved)
            contract = validator.validate_contract(resolved)
        else:
            prepared_contract = ensure_output_schema_artifact_fn(dict(payload))
            contract = validator.validate_contract(prepared_contract)
        if dep_artifacts:
            inputs = contract.get("inputs")
            if not isinstance(inputs, dict):
                inputs = {}
            artifacts = inputs.get("artifacts")
            if not isinstance(artifacts, list):
                artifacts = []
            inputs["artifacts"] = [*artifacts, *dep_artifacts]
            contract["inputs"] = inputs
    else:
        return {
            "index": idx,
            "name": name,
            "kind": kind or "plan",
            "task_id": "unknown",
            "run_id": "",
            "status": "FAILURE",
            "failure_reason": f"unsupported step kind: {kind}",
            "owner_agent": {},
            "assigned_agent": {},
        }

    ok, reason = _validate_handoff_chain(contract)
    if not ok:
        store.append_event(
            chain_run_id,
            {
                "level": "ERROR",
                "event": "CHAIN_HANDOFF_INVALID",
                "run_id": chain_run_id,
                "meta": {"step": name, "reason": reason},
            },
        )
        return {
            "index": idx,
            "name": name,
            "kind": kind or "plan",
            "task_id": contract.get("task_id", "unknown"),
            "run_id": "",
            "status": "FAILURE",
            "failure_reason": reason,
            "owner_agent": contract.get("owner_agent", {}),
            "assigned_agent": contract.get("assigned_agent", {}),
        }

    owner_role = _agent_role(contract.get("owner_agent", {}))
    contract, violations, truncations = _apply_context_policy(
        contract,
        policy,
        owner_role,
        name,
    )
    if truncations:
        store.append_event(
            chain_run_id,
            {
                "level": "WARN",
                "event": "CHAIN_CONTEXT_TRUNCATED",
                "run_id": chain_run_id,
                "meta": {"step": name, "items": truncations},
            },
        )
    if violations:
        store.append_event(
            chain_run_id,
            {
                "level": "ERROR",
                "event": "CHAIN_CONTEXT_POLICY_VIOLATION",
                "run_id": chain_run_id,
                "meta": {"step": name, "violations": violations},
            },
        )
        return {
            "index": idx,
            "name": name,
            "kind": kind or "plan",
            "task_id": contract.get("task_id", "unknown"),
            "run_id": "",
            "status": "FAILURE",
            "failure_reason": "context policy violation",
            "owner_agent": contract.get("owner_agent", {}),
            "assigned_agent": contract.get("assigned_agent", {}),
        }

    if depends and not contract.get("parent_task_id"):
        first_dep = depends[0]
        if first_dep in name_map:
            dep_payload = steps[name_map[first_dep]].get("payload") or {}
            contract["parent_task_id"] = _step_task_id(
                str(steps[name_map[first_dep]].get("kind", "")),
                dep_payload,
            )

    task_id = contract.get("task_id", f"task_{idx}")
    store.write_task_contract(chain_run_id, task_id, contract)
    contract_ref = store.write_artifact(
        chain_run_id,
        f"chain_step_{idx}_{task_id}.json",
        json.dumps(contract, ensure_ascii=False, indent=2),
    )
    store.append_event(
        chain_run_id,
        {
            "level": "INFO",
            "event": "CHAIN_STEP_STARTED",
            "run_id": chain_run_id,
            "meta": {
                "index": idx,
                "task_id": task_id,
                "name": name,
                "kind": kind,
                "group": group,
                "depends_on": depends,
                "context_policy": policy,
                "ref": str(contract_ref),
            },
        },
    )

    if use_subprocess:
        step_run_id = execute_task_subprocess(chain_run_id, Path(contract_ref), mock_mode)
    else:
        step_run_id = execute_task(Path(contract_ref), mock_mode)
    step_manifest = _load_manifest(store._runs_root, step_run_id)
    step_status = _normalize_run_status(step_manifest.get("status", "UNKNOWN"))
    failure_reason = step_manifest.get("failure_reason", "")
    if use_subprocess and not step_run_id:
        step_status = "FAILURE"
        if not failure_reason:
            failure_reason = "chain subprocess missing run_id"
    elif not step_run_id:
        step_status = "FAILURE"
        if not failure_reason:
            failure_reason = "step execution returned empty run_id"
    elif step_status not in _TERMINAL_RUN_STATUSES:
        step_status = "FAILURE"
        diagnosis = (
            "step run did not reach terminal status "
            f"(status={_normalize_run_status(step_manifest.get('status'))}), "
            "likely stream interruption"
        )
        failure_reason = (
            f"{failure_reason}; {diagnosis}" if failure_reason else diagnosis
        )
        store.append_event(
            chain_run_id,
            {
                "level": "ERROR",
                "event": "CHAIN_STEP_NON_TERMINAL",
                "run_id": chain_run_id,
                "meta": {
                    "index": idx,
                    "task_id": task_id,
                    "run_id": step_run_id,
                    "observed_status": _normalize_run_status(
                        step_manifest.get("status")
                    ),
                    "failure_reason": failure_reason,
                },
            },
        )
    task_result_payload = _load_task_result(store, step_run_id)
    if isinstance(task_result_payload, dict):
        completed_results[name] = task_result_payload
    if _is_fanin_step(step):
        dep_runs = [completed_runs.get(dep, "") for dep in depends if completed_runs.get(dep, "")]
        _normalize_fanin_task_result(
            store,
            chain_run_id,
            name,
            step_run_id,
            dep_runs,
        )

    return {
        "index": idx,
        "name": name,
        "kind": kind,
        "task_id": task_id,
        "run_id": step_run_id,
        "status": step_status,
        "failure_reason": str(failure_reason) if failure_reason else "",
        "owner_agent": contract.get("owner_agent", {}),
        "assigned_agent": contract.get("assigned_agent", {}),
    }
