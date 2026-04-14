from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable

from openvibecoding_orch.chain import chain_lifecycle, chain_reporting
from openvibecoding_orch.chain.helpers import _check_exclusive_paths, _normalize_depends, _step_task_id
from openvibecoding_orch.chain.runner_execution_helpers import (
    execute_chain_step as _execute_chain_step,
    execute_task_subprocess as _execute_task_subprocess_helper,
)
from openvibecoding_orch.chain.runtime_helpers import (
    _SCHEMA_KEYS_CACHE,
    TERMINAL_RUN_STATUSES as _TERMINAL_RUN_STATUSES,
    apply_context_policy as _apply_context_policy,
    artifact_names as _artifact_names,
    deep_merge_payload as _deep_merge_payload,
    dependency_artifact as _dependency_artifact,
    dependency_patch_artifact as _dependency_patch_artifact,
    filter_payload_keys as _filter_payload_keys,
    is_fanin_step as _is_fanin_step,
    load_json as _load_json,
    load_manifest as _load_manifest,
    merge_artifacts as _merge_artifacts,
    merge_contract_overrides as _merge_contract_overrides,
    is_purified_name as _is_purified_name,
    is_raw_name as _is_raw_name,
    normalize_fanin_summary as _normalize_fanin_summary,
    normalize_fanin_task_result as _normalize_fanin_task_result,
    normalize_run_status as _normalize_run_status,
    now_ts as _now_ts,
    output_schema_name_for_role as _output_schema_name_for_role,
    output_schema_role_key as _output_schema_role_key,
    resolve_contract_from_dependency as _resolve_contract_from_dependency,
    schema_allowed_keys as _schema_allowed_keys,
    sha256_file as _sha256_file,
    should_propagate_dependency_patch as _should_propagate_dependency_patch,
)
from openvibecoding_orch.contract.validator import ContractValidator
from openvibecoding_orch.store.run_store import RunStore


_HANDOFF_ROLE_ORDER = chain_lifecycle._HANDOFF_ROLE_ORDER
_agent_role = chain_lifecycle._agent_role
_validate_handoff_chain = chain_lifecycle._validate_handoff_chain
_normalize_required_path = chain_lifecycle._normalize_required_path
_step_roles = chain_lifecycle._step_roles
_reviewer_verdict = chain_lifecycle._reviewer_verdict
_test_stage_status = chain_lifecycle._test_stage_status
_build_lifecycle_summary = chain_lifecycle._build_lifecycle_summary
_collect_chain_timeout_summary = chain_reporting._collect_chain_timeout_summary
_load_task_result = chain_lifecycle._load_task_result


def _ensure_output_schema_artifact(contract: dict[str, Any]) -> dict[str, Any]:
    inputs = contract.get("inputs")
    if not isinstance(inputs, dict):
        inputs = {}
        contract["inputs"] = inputs
    artifacts = inputs.get("artifacts")
    if not isinstance(artifacts, list):
        artifacts = []
        inputs["artifacts"] = artifacts
    role = None
    assigned = contract.get("assigned_agent")
    if isinstance(assigned, dict):
        role = assigned.get("role")
    role_key = _output_schema_role_key(role)
    candidates = {f"output_schema.{role_key}", "output_schema"}
    for artifact in artifacts:
        if isinstance(artifact, dict):
            name = artifact.get("name")
            if isinstance(name, str) and name.strip().lower() in candidates:
                return contract
    schema_root = Path(__file__).resolve().parents[5] / "schemas"
    schema_name = _output_schema_name_for_role(role)
    schema_path = schema_root / schema_name
    if not schema_path.exists():
        return contract
    sha = hashlib.sha256(schema_path.read_bytes()).hexdigest()
    artifacts.append(
        {
            "name": f"output_schema.{role_key}",
            "uri": f"schemas/{schema_name}",
            "sha256": sha,
        }
    )
    return contract


class ChainRunner:
    def __init__(
        self,
        repo_root: Path,
        store: RunStore,
        execute_task: Callable[[Path, bool], str],
    ) -> None:
        self._repo_root = repo_root
        self._store = store
        self._execute_task = execute_task
        self._validator = ContractValidator()

    def _chain_exec_mode(self) -> str:
        return os.getenv("OPENVIBECODING_CHAIN_EXEC_MODE", "inline").strip().lower()

    def _resolve_chain_subprocess_timeout_sec(self) -> float | None:
        raw = os.getenv("OPENVIBECODING_CHAIN_SUBPROCESS_TIMEOUT_SEC", "").strip()
        if not raw:
            return None
        try:
            value = float(raw)
        except ValueError:
            return None
        if value <= 0:
            return None
        return value

    def _execute_task_subprocess(
        self,
        chain_run_id: str,
        contract_ref: Path,
        mock_mode: bool,
    ) -> str:
        return _execute_task_subprocess_helper(
            store=self._store,
            repo_root=self._repo_root,
            chain_run_id=chain_run_id,
            contract_ref=contract_ref,
            mock_mode=mock_mode,
            timeout_sec=self._resolve_chain_subprocess_timeout_sec(),
        )

    def run_chain(self, chain_path: Path, mock_mode: bool = False) -> dict[str, Any]:
        chain_path = chain_path.resolve()
        chain = self._validator.validate_report(_load_json(chain_path), "task_chain.v1.json")
        chain_id = str(chain.get("chain_id", "")).strip() or "chain"
        steps = chain.get("steps") or []
        strategy = chain.get("strategy") or {}
        continue_on_fail = bool(strategy.get("continue_on_fail", False))

        run_id = self._store.create_run(chain_id)
        start_ts = _now_ts()
        manifest = {
            "run_id": run_id,
            "task_id": chain_id,
            "chain_id": chain_id,
            "start_ts": start_ts,
            "end_ts": "",
            "status": "RUNNING",
        }
        self._store.write_manifest(run_id, manifest)

        chain_ref = self._store.write_artifact(
            run_id,
            "chain.json",
            json.dumps(chain, ensure_ascii=False, indent=2),
        )
        self._store.append_event(
            run_id,
            {
                "level": "INFO",
                "event": "CHAIN_SPEC_RECORDED",
                "run_id": run_id,
                "meta": {"ref": str(chain_ref)},
            },
        )
        self._store.append_event(
            run_id,
            {
                "level": "INFO",
                "event": "CHAIN_STARTED",
                "run_id": run_id,
                "meta": {"steps": len(steps), "continue_on_fail": continue_on_fail},
            },
        )

        step_payloads: list[dict[str, Any]] = []
        for step in steps:
            payload = step.get("payload")
            if isinstance(payload, dict):
                step_payloads.append(payload)
            else:
                step_payloads.append({})

        conflicts = _check_exclusive_paths(steps, step_payloads)
        if conflicts:
            self._store.append_event(
                run_id,
                {
                    "level": "ERROR",
                    "event": "CHAIN_EXCLUSIVE_PATH_CONFLICT",
                    "run_id": run_id,
                    "meta": {"conflicts": conflicts},
                },
            )
            report = {
                "chain_id": chain_id,
                "run_id": run_id,
                "status": "FAILURE",
                "steps": [],
                "timestamps": {"started_at": start_ts, "finished_at": _now_ts()},
            }
            self._store.write_report(run_id, "chain_report", report)
            self._store.append_event(
                run_id,
                {
                    "level": "INFO",
                    "event": "CHAIN_COMPLETED",
                    "run_id": run_id,
                    "meta": {"status": "FAILURE", "steps": 0},
                },
            )
            manifest["end_ts"] = _now_ts()
            manifest["status"] = "FAILURE"
            self._store.write_manifest(run_id, manifest)
            return report

        step_reports: list[dict[str, Any]] = []
        completed_runs: dict[str, str] = {}
        completed_results: dict[str, dict[str, Any]] = {}
        chain_status = "SUCCESS"
        successful_steps = 0

        def _emit_final_report(
            final_status: str,
            *,
            interrupted: bool = False,
            interruption_reason: str = "",
        ) -> dict[str, Any]:
            return chain_reporting.emit_chain_final_report(
                store=self._store,
                validator=self._validator,
                manifest=manifest,
                run_id=run_id,
                chain_id=chain_id,
                steps=steps,
                step_reports=step_reports,
                strategy=strategy,
                chain_owner_agent=chain.get("owner_agent", {}),
                start_ts=start_ts,
                final_status=final_status,
                interrupted=interrupted,
                interruption_reason=interruption_reason,
                now_ts_factory=_now_ts,
            )

        name_map = {}
        for index, step in enumerate(steps):
            name = str(step.get("name", f"step_{index}"))
            if name in name_map:
                raise ValueError(f"duplicate step name: {name}")
            name_map[name] = index

        try:
            if chain_status != "FAILURE":
                pending = set(name_map.keys())
                completed: set[str] = set()
                while pending:
                    ready = [
                        name
                        for name in pending
                        if set(_normalize_depends(steps[name_map[name]].get("depends_on"))) <= completed
                    ]
                    if not ready:
                        chain_status = "FAILURE"
                        break
                    groups: dict[str, list[str]] = {}
                    for name in ready:
                        step = steps[name_map[name]]
                        group = str(step.get("parallel_group") or f"__solo__{name}").strip()
                        groups.setdefault(group, []).append(name)

                    for group in sorted(groups.keys()):
                        batch = groups[group]
                        exec_mode = self._chain_exec_mode()
                        # Mock chains must stay in-process for deterministic tests and local simulation.
                        use_subprocess = (not mock_mode) and exec_mode == "subprocess" and len(batch) > 1

                        for name in batch:
                            step = steps[name_map[name]]
                            payload = step.get("payload")
                            task_id = _step_task_id(str(step.get("kind", "")), payload or {})
                            if not task_id:
                                task_id = f"chain_step_{name}"
                            for dep in _normalize_depends(step.get("depends_on")):
                                dep_step = steps[name_map[dep]]
                                dep_task_id = _step_task_id(str(dep_step.get("kind", "")), dep_step.get("payload") or {})
                                self._store.append_event(
                                    run_id,
                                    {
                                        "level": "INFO",
                                        "event": "CHAIN_HANDOFF",
                                        "run_id": run_id,
                                        "meta": {"from": dep_task_id, "to": task_id},
                                    },
                                )

                        def _run_one(step_name: str) -> dict[str, Any]:
                            return _execute_chain_step(
                                step_name=step_name,
                                steps=steps,
                                name_map=name_map,
                                group=group,
                                chain_run_id=run_id,
                                completed_runs=completed_runs,
                                completed_results=completed_results,
                                store=self._store,
                                validator=self._validator,
                                execute_task=self._execute_task,
                                execute_task_subprocess=self._execute_task_subprocess,
                                mock_mode=mock_mode,
                                use_subprocess=use_subprocess,
                                ensure_output_schema_artifact_fn=_ensure_output_schema_artifact,
                            )
    
                        results: list[dict[str, Any]] = []
                        if len(batch) == 1:
                            results.append(_run_one(batch[0]))
                        else:
                            from concurrent.futures import ThreadPoolExecutor

                            with ThreadPoolExecutor(max_workers=len(batch)) as pool:
                                for item in pool.map(_run_one, batch):
                                    results.append(item)

                        for result in results:
                            step_status = _normalize_run_status(result.get("status"))
                            result["status"] = step_status
                            step_reports.append(result)
                            name = result.get("name")
                            run_ref = result.get("run_id")
                            if isinstance(name, str) and isinstance(run_ref, str) and run_ref:
                                completed_runs[name] = run_ref
                            self._store.append_event(
                                run_id,
                                {
                                    "level": "INFO",
                                    "event": "CHAIN_STEP_RESULT",
                                    "run_id": run_id,
                                    "meta": {
                                        "index": result.get("index"),
                                        "task_id": result.get("task_id"),
                                        "run_id": result.get("run_id"),
                                        "status": result.get("status"),
                                        "failure_reason": result.get("failure_reason"),
                                    },
                                },
                            )
                            name = result.get("name")
                            if isinstance(name, str) and name in pending:
                                pending.remove(name)
                                completed.add(name)
                            if step_status == "SUCCESS":
                                successful_steps += 1
                            else:
                                # Only explicit execution failures can continue under continue_on_fail.
                                if continue_on_fail and step_status in {"FAILURE", "FAIL", "ERROR"}:
                                    chain_status = "PARTIAL"
                                else:
                                    chain_status = "FAILURE"
                                    break
                            if chain_status == "FAILURE":
                                break
                        if chain_status == "FAILURE":
                            break
                    if chain_status == "FAILURE":
                        break
            if chain_status == "PARTIAL" and successful_steps == 0:
                chain_status = "FAILURE"
            return _emit_final_report(chain_status)
        except KeyboardInterrupt as exc:
            self._store.append_event(
                run_id,
                {
                    "level": "WARN",
                    "event": "CHAIN_INTERRUPTED",
                    "run_id": run_id,
                    "meta": {
                        "reason": str(exc) or "KeyboardInterrupt",
                        "steps_recorded": len(step_reports),
                    },
                },
            )
            return _emit_final_report(
                "FAILURE",
                interrupted=True,
                interruption_reason=str(exc) or "KeyboardInterrupt",
            )
