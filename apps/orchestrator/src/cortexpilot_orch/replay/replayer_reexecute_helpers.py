from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from cortexpilot_orch.contract.validator import ContractValidator
from cortexpilot_orch.replay import replay_helpers as _helpers

_now_ts = _helpers._now_ts
_sha256_text = _helpers._sha256_text
_load_changed_files = _helpers._load_changed_files
_git = _helpers._git
_extract_diff_names_from_patch = _helpers._extract_diff_names_from_patch


def _value(obj: dict[str, Any], key: str) -> str | None:
    value = obj.get(key)
    return value if isinstance(value, str) and value.strip() else None


def build_reexecute_report(
    *,
    run_dir: Path,
    run_id: str,
    strict: bool,
    validator: ContractValidator,
    run_acceptance_tests_fn: Callable[..., dict[str, Any]],
    worktree_manager_module: Any,
    collect_diff_text_fn: Callable[[Path, str], str],
) -> dict[str, Any]:
    contract_path = run_dir / "contract.json"
    manifest_path = run_dir / "manifest.json"
    task_result_path = run_dir / "reports" / "task_result.json"
    test_report_path = run_dir / "reports" / "test_report.json"

    errors: list[str] = []
    hard_diffs: list[dict[str, Any]] = []
    soft_diffs: list[dict[str, Any]] = []

    if not contract_path.exists():
        errors.append("contract.json missing")
        contract = {}
    else:
        try:
            contract = validator.validate_contract_file(contract_path)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"contract invalid: {exc}")
            contract = {}

    manifest: dict[str, Any] = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"manifest invalid: {exc}")

    baseline_ref = None
    rollback = contract.get("rollback") if isinstance(contract, dict) else None
    if isinstance(rollback, dict):
        baseline_ref = rollback.get("baseline_ref")
    if not baseline_ref and isinstance(manifest, dict):
        repo_meta = manifest.get("repo")
        if isinstance(repo_meta, dict):
            baseline_ref = repo_meta.get("baseline_ref")
    baseline_ref = baseline_ref if isinstance(baseline_ref, str) and baseline_ref.strip() else None
    if not baseline_ref:
        errors.append("baseline_ref missing")

    head_ref = None
    task_result: dict[str, Any] = {}
    if task_result_path.exists():
        try:
            task_result = json.loads(task_result_path.read_text(encoding="utf-8"))
            git_meta = task_result.get("git") if isinstance(task_result, dict) else None
            if isinstance(git_meta, dict):
                head_ref = _value(git_meta, "head_ref")
        except json.JSONDecodeError:
            errors.append("task_result invalid")
    if not head_ref and isinstance(manifest, dict):
        repo_meta = manifest.get("repo")
        if isinstance(repo_meta, dict):
            head_ref = _value(repo_meta, "final_ref")
    if not head_ref:
        errors.append("head_ref missing")

    expected_patch_path = run_dir / "patch.diff"
    expected_diff_names = _load_changed_files(run_dir)
    expected_test_report: dict[str, Any] = {}
    if test_report_path.exists():
        try:
            expected_test_report = json.loads(test_report_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            errors.append("test_report invalid")

    if strict:
        manifest_run_id = _value(manifest, "run_id") if isinstance(manifest, dict) else None
        if manifest_run_id and manifest_run_id != run_id:
            errors.append("manifest run_id mismatch against reexec target")

        run_id_values: list[str] = []
        task_run_id = _value(task_result, "run_id") if isinstance(task_result, dict) else None
        if task_run_id:
            run_id_values.append(task_run_id)
        test_run_id = _value(expected_test_report, "run_id")
        if test_run_id:
            run_id_values.append(test_run_id)
        if run_id_values and len(set(run_id_values)) != 1:
            errors.append("run_id mismatch across reexec reports/results")
        elif run_id_values and run_id_values[0] != run_id:
            errors.append("run_id mismatch against reexec target")

        task_git = task_result.get("git") if isinstance(task_result, dict) else None
        if isinstance(task_git, dict):
            task_baseline_ref = _value(task_git, "baseline_ref")
            if baseline_ref and task_baseline_ref and task_baseline_ref != baseline_ref:
                errors.append("baseline_ref mismatch across reexec artifacts")
            task_head_ref = _value(task_git, "head_ref")
            if head_ref and task_head_ref and task_head_ref != head_ref:
                errors.append("head_ref mismatch across reexec artifacts")

        if isinstance(manifest, dict):
            repo_meta = manifest.get("repo")
            if isinstance(repo_meta, dict):
                manifest_baseline_ref = _value(repo_meta, "baseline_ref")
                if baseline_ref and manifest_baseline_ref and manifest_baseline_ref != baseline_ref:
                    errors.append("baseline_ref mismatch across reexec artifacts")
                manifest_head_ref = _value(repo_meta, "final_ref")
                if head_ref and manifest_head_ref and manifest_head_ref != head_ref:
                    errors.append("head_ref mismatch across reexec artifacts")

    reexec_id = f"reexec-{run_id}"
    actual_patch = ""
    actual_names: list[str] = []
    tests_result: dict[str, Any] = {"ok": False, "reports": [], "reason": "not executed"}

    if baseline_ref and head_ref:
        worktree_path = None
        task_id = None
        try:
            task_id = contract.get("task_id") if isinstance(contract, dict) else None
            worktree_path = worktree_manager_module.create_worktree(
                reexec_id,
                task_id or reexec_id,
                head_ref,
            )
            diff_text = collect_diff_text_fn(worktree_path, baseline_ref)
            diff_names = _git(["git", "diff", "--name-only", f"{baseline_ref}..HEAD"], cwd=worktree_path)
            status = _git(["git", "status", "--porcelain"], cwd=worktree_path)
            untracked = [line[3:] for line in status.splitlines() if line.startswith("?? ")]
            actual_patch = diff_text
            actual_names = [line.strip() for line in diff_names.splitlines() if line.strip()]
            actual_names.extend([name for name in untracked if name])
            network_policy = contract.get("tool_permissions", {}).get("network", "deny")
            tests_result = run_acceptance_tests_fn(
                worktree_path,
                contract.get("acceptance_tests", []),
                forbidden_actions=contract.get("forbidden_actions", []),
                network_policy=network_policy,
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"reexec failed: {exc}")
        finally:
            if worktree_path is not None:
                worktree_manager_module.remove_worktree(reexec_id, task_id or reexec_id)

    allow_uncommitted = baseline_ref == head_ref if baseline_ref and head_ref else False

    expected_patch = expected_patch_path.read_text(encoding="utf-8") if expected_patch_path.exists() else ""
    if expected_patch_path.exists():
        expected_hash = _sha256_text(expected_patch)
        actual_hash = _sha256_text(actual_patch)
        if expected_hash != actual_hash:
            diff_item = {"key": "patch.diff", "expected": expected_hash, "actual": actual_hash}
            patch_names = _extract_diff_names_from_patch(expected_patch)
            patch_matches_expected = bool(patch_names) and (
                set(patch_names) == set(expected_diff_names or patch_names)
            )
            if allow_uncommitted and patch_matches_expected:
                soft_diffs.append(diff_item)
            else:
                hard_diffs.append(diff_item)
    elif strict and not allow_uncommitted:
        errors.append("patch.diff missing")

    if expected_diff_names or actual_names:
        if expected_diff_names != actual_names:
            diff_item = {
                "key": "diff_name_only.txt",
                "expected": expected_diff_names,
                "actual": actual_names,
            }
            (soft_diffs if allow_uncommitted else hard_diffs).append(diff_item)
    elif strict and not allow_uncommitted:
        errors.append("diff_name_only.txt missing")

    expected_status = expected_test_report.get("status") if isinstance(expected_test_report, dict) else None
    if expected_status:
        actual_status = "PASS" if tests_result.get("ok") else "FAIL"
        if expected_status != actual_status:
            hard_diffs.append({"key": "tests", "expected": expected_status, "actual": actual_status})
    elif strict:
        errors.append("test_report status missing")

    hard_equal_pass = len(hard_diffs) == 0 and not errors
    status = "pass" if hard_equal_pass else "fail"

    return {
        "run_id": run_id,
        "status": status,
        "reexec_ts": _now_ts(),
        "hard_equal_pass": hard_equal_pass,
        "soft_equal_pass": True if not soft_diffs else False,
        "hard_diffs": hard_diffs,
        "soft_diffs": soft_diffs,
        "errors": errors,
    }
