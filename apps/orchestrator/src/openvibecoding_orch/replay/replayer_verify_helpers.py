from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from openvibecoding_orch.contract.validator import ContractValidator
from openvibecoding_orch.replay import replay_helpers as _helpers

_sha256_file = _helpers._sha256_file
_hash_events = _helpers._hash_events
_verify_contract_signature = _helpers._verify_contract_signature
_verify_hashchain = _helpers._verify_hashchain
_extract_report_cmds = _helpers._extract_report_cmds
_load_events = _helpers._load_events
_parse_ts = _helpers._parse_ts
_load_acceptance_commands = _helpers._load_acceptance_commands
_is_allowed = _helpers._is_allowed
_load_changed_files = _helpers._load_changed_files
_load_json_dict = _helpers._load_json_dict


def _value(obj: dict[str, Any], key: str) -> str | None:
    value = obj.get(key)
    return value if isinstance(value, str) and value.strip() else None


def build_verify_report(
    *,
    run_dir: Path,
    run_id: str,
    strict: bool,
    validator: ContractValidator,
) -> dict[str, Any]:
    contract_path = run_dir / "contract.json"
    events_path = run_dir / "events.jsonl"
    manifest_path = run_dir / "manifest.json"
    patch_path = run_dir / "patch.diff"
    review_path = run_dir / "reports" / "review_report.json"
    test_path = run_dir / "reports" / "test_report.json"

    errors: list[dict[str, str]] = []
    warnings: list[str] = []

    if not contract_path.exists():
        errors.append(
            {
                "code": "contract_missing",
                "message": "contract.json missing",
                "path": "contract.json",
            }
        )
        contract = {}
    else:
        try:
            contract = validator.validate_contract_file(contract_path)
        except Exception as exc:  # noqa: BLE001
            errors.append(
                {
                    "code": "contract_invalid",
                    "message": f"contract schema invalid: {exc}",
                    "path": "contract.json",
                }
            )
            contract = {}

    sig_path = run_dir / "contract.sig"
    if sig_path.exists():
        ok, reason = _verify_contract_signature(contract_path, sig_path)
        if not ok:
            if strict:
                errors.append(
                    {
                        "code": "contract_signature_invalid",
                        "message": reason,
                        "path": "contract.sig",
                    }
                )
            else:
                warnings.append(f"contract signature invalid: {reason}")
    else:
        if os.getenv("OPENVIBECODING_CONTRACT_HMAC_KEY", "").strip():
            if strict:
                errors.append(
                    {
                        "code": "contract_signature_missing",
                        "message": "contract.sig missing",
                        "path": "contract.sig",
                    }
                )
            else:
                warnings.append("contract signature missing")

    if not events_path.exists():
        errors.append({"code": "events_missing", "message": "events.jsonl missing", "path": "events.jsonl"})
    else:
        events = _load_events(events_path)
        last_ts = None
        for idx, ev in enumerate(events):
            if "raw" in ev:
                errors.append(
                    {
                        "code": "event_not_json",
                        "message": f"events.jsonl line {idx + 1} not json",
                        "path": "events.jsonl",
                    }
                )
                continue
            try:
                validator.validate_event(ev)
            except Exception as exc:  # noqa: BLE001
                errors.append(
                    {
                        "code": "event_invalid",
                        "message": f"event schema invalid at line {idx + 1}: {exc}",
                        "path": "events.jsonl",
                    }
                )
            ts_val = ev.get("ts")
            if not _parse_ts(ts_val):
                errors.append(
                    {
                        "code": "event_ts_invalid",
                        "message": f"event ts invalid at line {idx + 1}",
                        "path": "events.jsonl",
                    }
                )
            if isinstance(ts_val, str):
                if last_ts and ts_val < last_ts:
                    errors.append(
                        {
                            "code": "event_order_invalid",
                            "message": "events.jsonl not ordered by ts",
                            "path": "events.jsonl",
                        }
                    )
                last_ts = ts_val
            if ev.get("event_type") == "SCHEMA_DRIFT_DETECTED":
                warnings.append("schema drift detected in events.jsonl")
        chain_path = run_dir / "events.hashchain.jsonl"
        ok, reason = _verify_hashchain(events_path, chain_path)
        if not ok:
            if reason == "hashchain missing":
                if strict:
                    errors.append(
                        {
                            "code": "events_hashchain_missing",
                            "message": "events hashchain missing",
                            "path": "events.hashchain.jsonl",
                        }
                    )
                else:
                    warnings.append("events hashchain missing")
            elif strict:
                errors.append(
                    {
                        "code": "events_hashchain_invalid",
                        "message": reason,
                        "path": "events.hashchain.jsonl",
                    }
                )
            else:
                warnings.append(f"events hashchain invalid: {reason}")

    if not manifest_path.exists():
        errors.append({"code": "manifest_missing", "message": "manifest.json missing", "path": "manifest.json"})
        manifest = {}
    else:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(
                {
                    "code": "manifest_invalid",
                    "message": f"manifest.json invalid: {exc}",
                    "path": "manifest.json",
                }
            )
            manifest = {}

    evidence_hashes = manifest.get("evidence_hashes", {}) if isinstance(manifest, dict) else {}
    if not isinstance(evidence_hashes, dict) or not evidence_hashes:
        errors.append(
            {
                "code": "manifest_hashes_missing",
                "message": "manifest missing evidence_hashes",
                "path": "manifest.json",
            }
        )
    else:
        if not patch_path.exists():
            errors.append({"code": "patch_missing", "message": "patch.diff missing", "path": "patch.diff"})
        else:
            patch_hash = _sha256_file(patch_path)
            expected_hash = evidence_hashes.get("patch.diff")
            if expected_hash and patch_hash != expected_hash:
                errors.append(
                    {
                        "code": "patch_hash_mismatch",
                        "message": "patch.diff hash mismatch",
                        "path": "patch.diff",
                    }
                )

    review_report: dict[str, Any] = {}
    if review_path.exists():
        try:
            review_report = validator.validate_report_file(review_path, "review_report.v1.json")
            if review_report.get("produced_diff") is not False:
                errors.append(
                    {
                        "code": "review_produced_diff",
                        "message": "review_report produced_diff must be false",
                        "path": "reports/review_report.json",
                    }
                )
        except Exception as exc:  # noqa: BLE001
            errors.append(
                {
                    "code": "review_invalid",
                    "message": f"review_report invalid: {exc}",
                    "path": "reports/review_report.json",
                }
            )
            review_report = _load_json_dict(review_path)
    else:
        errors.append(
            {
                "code": "review_missing",
                "message": "review_report.json missing",
                "path": "reports/review_report.json",
            }
        )

    test_report: dict[str, Any] = {}
    if test_path.exists():
        try:
            test_report = validator.validate_report_file(test_path, "test_report.v1.json")
            acceptance_cmds = _load_acceptance_commands(contract)
            commands = _extract_report_cmds(test_report)
            if commands:
                for cmd in commands:
                    if tuple(cmd) not in acceptance_cmds:
                        errors.append(
                            {
                                "code": "test_command_outside_acceptance",
                                "message": "test_report command not in acceptance_tests",
                                "path": "reports/test_report.json",
                            }
                        )
                        break
        except Exception as exc:  # noqa: BLE001
            errors.append(
                {
                    "code": "test_invalid",
                    "message": f"test_report invalid: {exc}",
                    "path": "reports/test_report.json",
                }
            )
            test_report = _load_json_dict(test_path)
    else:
        errors.append(
            {
                "code": "test_missing",
                "message": "test_report.json missing",
                "path": "reports/test_report.json",
            }
        )

    allowed_paths = contract.get("allowed_paths", []) if isinstance(contract, dict) else []
    changed_files = _load_changed_files(run_dir)
    diff_names_path = run_dir / "diff_name_only.txt"
    if not changed_files and allowed_paths:
        warnings.append("diff_name_only.txt missing; diff gate recheck skipped")
        if strict and not diff_names_path.exists():
            errors.append(
                {
                    "code": "diff_name_only_missing",
                    "message": "diff_name_only.txt missing for strict diff gate recheck",
                    "path": "diff_name_only.txt",
                }
            )
    elif changed_files:
        violations = [name for name in changed_files if not _is_allowed(name, allowed_paths)]
        if violations:
            errors.append(
                {
                    "code": "diff_gate_violation",
                    "message": "diff gate violations detected",
                    "path": "diff_name_only.txt",
                }
            )

    if strict:
        contract_task_id = _value(contract, "task_id")
        if not contract_task_id:
            errors.append(
                {
                    "code": "task_id_missing",
                    "message": "contract task_id missing",
                    "path": "contract.json",
                }
            )

        reports_dir = run_dir / "reports"
        task_result_path = reports_dir / "task_result.json"
        task_result: dict[str, Any] = {}
        if task_result_path.exists():
            try:
                task_result = validator.validate_report_file(task_result_path, "task_result.v1.json")
            except Exception as exc:  # noqa: BLE001
                errors.append(
                    {
                        "code": "task_result_invalid",
                        "message": f"task_result invalid: {exc}",
                        "path": "reports/task_result.json",
                    }
                )
                task_result = _load_json_dict(task_result_path)
        else:
            errors.append(
                {
                    "code": "task_result_missing",
                    "message": "task_result.json missing",
                    "path": "reports/task_result.json",
                }
            )

        if contract_task_id:
            for label, payload in [
                ("task_result", task_result),
                ("review_report", review_report),
                ("test_report", test_report),
            ]:
                if payload and payload.get("task_id") != contract_task_id:
                    errors.append({"code": "task_id_mismatch", "message": f"{label} task_id mismatch"})

        run_id_values = []
        for payload in [task_result, review_report, test_report]:
            if payload:
                run_id_values.append(payload.get("run_id"))
        run_id_values = [val for val in run_id_values if isinstance(val, str) and val.strip()]
        if len(run_id_values) < 3:
            errors.append({"code": "run_id_missing", "message": "run_id missing in reports/results"})
        elif len(set(run_id_values)) != 1:
            errors.append({"code": "run_id_mismatch", "message": "run_id mismatch across reports/results"})
        elif run_id_values[0] != run_id:
            errors.append({"code": "run_id_target_mismatch", "message": "run_id mismatch against verify target"})

        manifest_run_id = _value(manifest, "run_id") if isinstance(manifest, dict) else None
        if manifest_run_id and manifest_run_id != run_id:
            errors.append({"code": "manifest_run_id_mismatch", "message": "manifest run_id mismatch against verify target"})

        attempt_values = []
        for payload in [task_result, review_report, test_report]:
            if not payload:
                continue
            attempt = payload.get("attempt")
            if isinstance(attempt, int):
                attempt_values.append(attempt)
        if len(attempt_values) < 3:
            errors.append({"code": "attempt_missing", "message": "attempt missing in reports/results"})
        elif len(set(attempt_values)) != 1:
            errors.append({"code": "attempt_mismatch", "message": "attempt mismatch across reports/results"})

        baseline_ref = None
        rollback = contract.get("rollback") if isinstance(contract, dict) else None
        if isinstance(rollback, dict):
            baseline_ref = _value(rollback, "baseline_ref")
        if not baseline_ref and isinstance(manifest, dict):
            repo_meta = manifest.get("repo")
            if isinstance(repo_meta, dict):
                baseline_ref = _value(repo_meta, "baseline_ref")
        if not baseline_ref:
            errors.append({"code": "baseline_missing", "message": "baseline_ref missing"})
        elif isinstance(task_result, dict):
            git_meta = task_result.get("git")
            if isinstance(git_meta, dict):
                task_baseline_ref = _value(git_meta, "baseline_ref")
                if task_baseline_ref and task_baseline_ref != baseline_ref:
                    errors.append({"code": "baseline_mismatch", "message": "baseline_ref mismatch across artifacts"})

        head_ref = None
        if isinstance(task_result, dict):
            git_meta = task_result.get("git")
            if isinstance(git_meta, dict):
                head_ref = _value(git_meta, "head_ref")
        if not head_ref and isinstance(manifest, dict):
            repo_meta = manifest.get("repo")
            if isinstance(repo_meta, dict):
                head_ref = _value(repo_meta, "final_ref")
        if not head_ref:
            errors.append({"code": "head_missing", "message": "head_ref missing"})
        else:
            manifest_head_ref = None
            if isinstance(manifest, dict):
                repo_meta = manifest.get("repo")
                if isinstance(repo_meta, dict):
                    manifest_head_ref = _value(repo_meta, "final_ref")
            if manifest_head_ref and manifest_head_ref != head_ref:
                errors.append({"code": "head_mismatch", "message": "head_ref mismatch across artifacts"})

        required_keys = [
            "contract.json",
            "patch.diff",
            "diff_name_only.txt",
            "reports/review_report.json",
            "reports/test_report.json",
        ]
        for key in required_keys:
            expected = evidence_hashes.get(key) if isinstance(evidence_hashes, dict) else None
            if not expected:
                errors.append(
                    {
                        "code": "manifest_hash_missing",
                        "message": f"manifest missing hash for {key}",
                        "path": key,
                    }
                )
                continue
            path = run_dir / key
            if not path.exists():
                errors.append(
                    {"code": "evidence_missing", "message": f"evidence file missing: {key}", "path": key}
                )
                continue
            current_hash = _hash_events(path) if key == "events.jsonl" else _sha256_file(path)
            if current_hash != expected:
                errors.append(
                    {
                        "code": "manifest_hash_mismatch",
                        "message": f"hash mismatch: {key}",
                        "path": key,
                    }
                )

    status = "pass" if not errors else "fail"
    return {
        "run_id": run_id,
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "checks": {
            "contract": contract_path.exists(),
            "events": events_path.exists(),
            "manifest": manifest_path.exists(),
            "patch": patch_path.exists(),
            "review_report": review_path.exists(),
            "test_report": test_path.exists(),
        },
    }
