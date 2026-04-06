from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .run_store_primitives import safe_artifact_path, safe_component, write_atomic


def write_manifest(run_dir: Path, manifest_data: dict[str, Any]) -> Path:
    manifest_path = run_dir / "manifest.json"
    payload = json.dumps(manifest_data, ensure_ascii=False, indent=2).encode("utf-8")
    write_atomic(manifest_path, payload)
    return manifest_path


def write_contract(run_dir: Path, contract_data: dict[str, Any]) -> Path:
    contract_path = run_dir / "contract.json"
    payload = json.dumps(contract_data, ensure_ascii=False, indent=2).encode("utf-8")
    write_atomic(contract_path, payload)
    return contract_path


def write_diff(run_dir: Path, diff_text: str) -> Path:
    diff_path = run_dir / "patch.diff"
    write_atomic(diff_path, diff_text.encode("utf-8"))
    return diff_path


def write_diff_names(run_dir: Path, names: list[str]) -> Path:
    content = "\n".join(names)
    root_path = run_dir / "diff_name_only.txt"
    write_atomic(root_path, content.encode("utf-8"))
    git_path = run_dir / "git" / "diff_name_only.txt"
    write_atomic(git_path, content.encode("utf-8"))
    return git_path


def write_report(run_dir: Path, report_type: str, data: dict[str, Any]) -> Path:
    safe_report = safe_component(report_type, "report_type")
    report_path = run_dir / "reports" / f"{safe_report}.json"
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    write_atomic(report_path, payload)
    return report_path


def append_artifact_jsonl(run_dir: Path, filename: str, payload: dict[str, Any]) -> Path:
    safe_name = safe_component(filename, "artifact_name")
    artifact_path = run_dir / "artifacts" / safe_name
    line = json.dumps(payload, ensure_ascii=False)
    with artifact_path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return artifact_path


def write_task_contract(run_dir: Path, task_id: str, contract_data: dict[str, Any]) -> tuple[Path, str]:
    safe_task_id = safe_component(task_id, "task_id")
    path = run_dir / "tasks" / f"{safe_task_id}.json"
    payload = json.dumps(contract_data, ensure_ascii=False, indent=2).encode("utf-8")
    write_atomic(path, payload)
    return path, safe_task_id


def write_task_result(run_dir: Path, task_id: str, data: dict[str, Any]) -> tuple[Path, str]:
    safe_task_id = safe_component(task_id, "task_id")
    path = run_dir / "results" / safe_task_id / "result.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    write_atomic(path, payload)
    return path, safe_task_id


def write_review_report(run_dir: Path, task_id: str, data: dict[str, Any]) -> tuple[Path, str]:
    safe_task_id = safe_component(task_id, "task_id")
    path = run_dir / "reviews" / f"{safe_task_id}.json"
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    write_atomic(path, payload)
    return path, safe_task_id


def write_ci_report(run_dir: Path, task_id: str, data: dict[str, Any]) -> Path:
    safe_task_id = safe_component(task_id, "task_id")
    path = run_dir / "ci" / safe_task_id / "report.json"
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    write_atomic(path, payload)
    return path


def write_git_baseline(run_dir: Path, commit: str) -> Path:
    path = run_dir / "git" / "baseline_commit.txt"
    write_atomic(path, commit.encode("utf-8"))
    return path


def write_worktree_ref(run_dir: Path, worktree: Path) -> Path:
    path = run_dir / "worktree_ref.txt"
    write_atomic(path, str(worktree).encode("utf-8"))
    return path


def write_git_patch(run_dir: Path, task_id: str, diff_text: str) -> Path:
    git_path = run_dir / "git" / "patch.diff"
    payload = diff_text.encode("utf-8")
    write_atomic(git_path, payload)
    safe_task_id = safe_component(task_id, "task_id")
    result_path = run_dir / "results" / safe_task_id / "patch.diff"
    write_atomic(result_path, payload)
    patches_path = run_dir / "patches" / f"{safe_task_id}.diff"
    write_atomic(patches_path, payload)
    return git_path


def write_tests_logs(run_dir: Path, command: str, stdout: str, stderr: str) -> None:
    tests_dir = run_dir / "tests"
    write_atomic(tests_dir / "command.txt", command.encode("utf-8"))
    write_atomic(tests_dir / "stdout.log", stdout.encode("utf-8"))
    write_atomic(tests_dir / "stderr.log", stderr.encode("utf-8"))


def write_trace_id(run_dir: Path, trace_id: str) -> Path:
    path = run_dir / "trace" / "trace_id.txt"
    write_atomic(path, trace_id.encode("utf-8"))
    return path


def write_llm_snapshot(run_dir: Path, snapshot: dict[str, Any]) -> Path:
    path = run_dir / "trace" / "llm_snapshot.json"
    payload = json.dumps(snapshot, ensure_ascii=False, indent=2).encode("utf-8")
    write_atomic(path, payload)
    return path


def write_meta(run_dir: Path, data: dict[str, Any]) -> Path:
    path = run_dir / "meta.json"
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    write_atomic(path, payload)
    return path


def artifact_path(run_dir: Path, filename: str) -> Path:
    return safe_artifact_path(run_dir / "artifacts", filename)


def write_artifact(run_dir: Path, filename: str, content: str) -> Path:
    target_path = artifact_path(run_dir, filename)
    write_atomic(target_path, content.encode("utf-8"))
    return target_path


def write_artifact_bytes(run_dir: Path, filename: str, content: bytes) -> Path:
    target_path = artifact_path(run_dir, filename)
    write_atomic(target_path, content)
    return target_path
