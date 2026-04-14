from __future__ import annotations

from typing import Any

from openvibecoding_orch.contract.validator import ContractValidator
from openvibecoding_orch.gates.tests_gate import run_acceptance_tests
from openvibecoding_orch.replay import replay_helpers as _helpers
from openvibecoding_orch.replay import replayer_reexecute_helpers as _reexecute_helpers
from openvibecoding_orch.replay import replayer_verify_helpers as _verify_helpers
from openvibecoding_orch.store.run_store import RunStore
from openvibecoding_orch.worktrees import manager as worktree_manager

_REPORT_SCHEMA_MAP = {
    "test_report.json": "test_report.v1.json",
    "review_report.json": "review_report.v1.json",
    "task_result.json": "task_result.v1.json",
}


_now_ts = _helpers._now_ts
_sha256_text = _helpers._sha256_text
_sha256_file = _helpers._sha256_file
_hash_events = _helpers._hash_events
_hmac_sha256 = _helpers._hmac_sha256
_verify_contract_signature = _helpers._verify_contract_signature
_verify_hashchain = _helpers._verify_hashchain
_normalize_acceptance_cmds = _helpers._normalize_acceptance_cmds
_extract_report_cmds = _helpers._extract_report_cmds
_git = _helpers._git
_git_allow_nonzero = _helpers._git_allow_nonzero
_collect_diff_text = _helpers._collect_diff_text
_extract_diff_names_from_patch = _helpers._extract_diff_names_from_patch
_collect_evidence_hashes = _helpers._collect_evidence_hashes
_load_baseline_hashes = _helpers._load_baseline_hashes
_load_llm_params = _helpers._load_llm_params
_load_llm_snapshot = _helpers._load_llm_snapshot
_load_events = _helpers._load_events
_parse_ts = _helpers._parse_ts
_load_acceptance_commands = _helpers._load_acceptance_commands
_is_allowed = _helpers._is_allowed
_load_changed_files = _helpers._load_changed_files
_load_json_dict = _helpers._load_json_dict
_expected_reports = _helpers._expected_reports


class ReplayRunner:
    def __init__(self, store: RunStore, validator: ContractValidator | None = None) -> None:
        self._store = store
        self._validator = validator or ContractValidator()

    def replay(self, run_id: str, baseline_run_id: str | None = None) -> dict[str, Any]:
        run_dir = self._store._runs_root / run_id
        manifest_path = run_dir / "manifest.json"
        events_path = run_dir / "events.jsonl"
        reports_dir = run_dir / "reports"

        if not manifest_path.exists():
            raise FileNotFoundError(f"manifest not found for run_id={run_id}")
        if not events_path.exists():
            raise FileNotFoundError(f"events.jsonl not found for run_id={run_id}")

        self._store.append_event(
            run_id,
            {
                "level": "INFO",
                "event": "REPLAY_START",
                "run_id": run_id,
                "meta": {"run_id": run_id},
            },
        )

        if baseline_run_id is None:
            baseline_run_id = run_id

        baseline_dir = self._store._runs_root / baseline_run_id
        if not baseline_dir.exists():
            raise FileNotFoundError(f"baseline run not found: {baseline_run_id}")

        baseline_hashes = _load_baseline_hashes(baseline_dir)

        events = _load_events(events_path)
        expected_reports = sorted(_expected_reports(events))
        manifest_hash = _sha256_file(manifest_path)
        current_hashes = _collect_evidence_hashes(run_dir)

        report_checks: dict[str, dict[str, Any]] = {}
        report_hashes: dict[str, str] = {}
        missing_reports: list[str] = []

        for report_name in expected_reports:
            if not (reports_dir / report_name).exists():
                missing_reports.append(report_name)

        for report_path in reports_dir.glob("*.json"):
            if report_path.name == "replay_report.json":
                continue
            schema_name = _REPORT_SCHEMA_MAP.get(report_path.name)
            report_hashes[report_path.name] = _sha256_file(report_path)
            if not schema_name:
                report_checks[report_path.name] = {"schema": "", "ok": True, "error": ""}
                continue
            try:
                self._validator.validate_report_file(report_path, schema_name)
                report_checks[report_path.name] = {"schema": schema_name, "ok": True, "error": ""}
            except Exception as exc:  # noqa: BLE001
                report_checks[report_path.name] = {"schema": schema_name, "ok": False, "error": str(exc)}

        mismatched: list[dict[str, str]] = []
        missing_hashes: list[str] = []
        extra_hashes: list[str] = []

        for key, base_hash in baseline_hashes.items():
            current = current_hashes.get(key)
            if current is None:
                missing_hashes.append(key)
            elif current != base_hash:
                mismatched.append({"key": key, "baseline": base_hash, "current": current})

        for key in current_hashes.keys():
            if key not in baseline_hashes:
                extra_hashes.append(key)

        non_blocking = {
            "events.jsonl",
            "events.hashchain.jsonl",
            "reports/events_summary.json",
        }
        blocking_missing = [key for key in missing_hashes if key not in non_blocking]
        blocking_extra = [key for key in extra_hashes if key not in non_blocking]
        blocking_mismatched = [
            item for item in mismatched if item.get("key") not in non_blocking
        ]
        evidence_ok = (
            len(blocking_missing) == 0
            and len(blocking_extra) == 0
            and len(blocking_mismatched) == 0
        )

        baseline_llm = _load_llm_params(baseline_dir)
        current_llm = _load_llm_params(run_dir)
        llm_missing: list[str] = []
        llm_extra: list[str] = []
        llm_mismatched: list[dict[str, Any]] = []
        for key, base_value in baseline_llm.items():
            if key not in current_llm:
                llm_missing.append(key)
            elif current_llm.get(key) != base_value:
                llm_mismatched.append(
                    {"key": key, "baseline": base_value, "current": current_llm.get(key)}
                )
        for key in current_llm.keys():
            if key not in baseline_llm:
                llm_extra.append(key)
        llm_ok = len(llm_missing) == 0 and len(llm_extra) == 0 and len(llm_mismatched) == 0

        baseline_snapshot = _load_llm_snapshot(baseline_dir)
        current_snapshot = _load_llm_snapshot(run_dir)
        snapshot_missing: list[str] = []
        snapshot_extra: list[str] = []
        snapshot_mismatched: list[dict[str, Any]] = []
        for key, base_value in baseline_snapshot.items():
            if key not in current_snapshot:
                snapshot_missing.append(key)
            elif current_snapshot.get(key) != base_value:
                snapshot_mismatched.append(
                    {"key": key, "baseline": base_value, "current": current_snapshot.get(key)}
                )
        for key in current_snapshot.keys():
            if key not in baseline_snapshot:
                snapshot_extra.append(key)
        snapshot_ok = (
            len(snapshot_missing) == 0 and len(snapshot_extra) == 0 and len(snapshot_mismatched) == 0
        )

        status = "ok"
        if missing_reports or any(not item.get("ok", False) for item in report_checks.values()):
            status = "fail"
        if not evidence_ok:
            status = "fail"
        if not llm_ok:
            status = "fail"
        if not snapshot_ok:
            status = "fail"

        compare_summary = {
            "mismatched_count": len(mismatched),
            "missing_count": len(missing_hashes),
            "extra_count": len(extra_hashes),
            "missing_reports_count": len(missing_reports),
            "failed_report_checks_count": sum(1 for item in report_checks.values() if not item.get("ok", False)),
            "evidence_ok": evidence_ok,
            "llm_params_ok": llm_ok,
            "llm_snapshot_ok": snapshot_ok,
        }

        self._store.append_event(
            run_id,
            {
                "level": "INFO",
                "event": "REPLAY_AUDIT",
                "run_id": run_id,
                "meta": {
                    "baseline_run_id": baseline_run_id,
                    "status": status,
                    "evidence_ok": evidence_ok,
                    "mismatched_keys": [item["key"] for item in mismatched],
                    "missing_keys": missing_hashes,
                    "extra_keys": extra_hashes,
                    "llm_params_ok": llm_ok,
                    "llm_snapshot_ok": snapshot_ok,
                },
            },
        )

        replay_report = {
            "run_id": run_id,
            "baseline_run_id": baseline_run_id,
            "status": status,
            "replay_ts": _now_ts(),
            "manifest_hash": manifest_hash,
            "events_count": len(events),
            "expected_reports": expected_reports,
            "missing_reports": missing_reports,
            "report_checks": report_checks,
            "report_hashes": report_hashes,
            "compare_summary": compare_summary,
            "evidence_hashes": {
                "baseline": baseline_hashes,
                "current": current_hashes,
                "missing": missing_hashes,
                "extra": extra_hashes,
                "mismatched": mismatched,
                "ok": evidence_ok,
            },
            "llm_params": {
                "baseline": baseline_llm,
                "current": current_llm,
                "missing": llm_missing,
                "extra": llm_extra,
                "mismatched": llm_mismatched,
                "ok": llm_ok,
            },
            "llm_snapshot": {
                "baseline": baseline_snapshot,
                "current": current_snapshot,
                "missing": snapshot_missing,
                "extra": snapshot_extra,
                "mismatched": snapshot_mismatched,
                "ok": snapshot_ok,
            },
        }

        run_compare_report = {
            "report_type": "run_compare_report",
            "run_id": run_id,
            "baseline_run_id": baseline_run_id,
            "status": status,
            "compare_summary": compare_summary,
        }

        self._store.write_report(run_id, "replay_report", replay_report)
        self._store.write_report(run_id, "run_compare_report", run_compare_report)
        self._store.append_event(
            run_id,
            {
                "level": "INFO",
                "event": "REPLAY_DONE",
                "run_id": run_id,
                "meta": {
                    "status": status,
                    "missing_reports": missing_reports,
                    "events_count": len(events),
                },
            },
        )
        return replay_report

    def verify(self, run_id: str, strict: bool = True) -> dict[str, Any]:
        run_dir = self._store._runs_root / run_id
        report = _verify_helpers.build_verify_report(
            run_dir=run_dir,
            run_id=run_id,
            strict=strict,
            validator=self._validator,
        )
        self._store.write_report(run_id, "replay_verify", report)
        self._store.append_event(
            run_id,
            {
                "level": "INFO" if report["status"] == "pass" else "ERROR",
                "event": "REPLAY_VERIFY",
                "run_id": run_id,
                "meta": {
                    "status": report["status"],
                    "errors": report["errors"],
                    "warnings": report["warnings"],
                },
            },
        )
        return report

    def reexecute(self, run_id: str, strict: bool = True) -> dict[str, Any]:
        run_dir = self._store._runs_root / run_id
        report = _reexecute_helpers.build_reexecute_report(
            run_dir=run_dir,
            run_id=run_id,
            strict=strict,
            validator=self._validator,
            run_acceptance_tests_fn=run_acceptance_tests,
            worktree_manager_module=worktree_manager,
            collect_diff_text_fn=_collect_diff_text,
        )

        self._store.write_report(run_id, "reexec_report", report)
        self._store.append_event(
            run_id,
            {
                "level": "INFO" if report["status"] == "pass" else "ERROR",
                "event": "REEXEC_RESULT",
                "run_id": run_id,
                "meta": report,
            },
        )
        return report


__all__ = ["ReplayRunner"]
