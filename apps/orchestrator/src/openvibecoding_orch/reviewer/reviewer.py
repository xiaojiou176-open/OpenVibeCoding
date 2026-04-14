from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openvibecoding_orch.contract.validator import ContractValidator
from openvibecoding_orch.observability.codex_event_parser import parse_codex_event_line
from openvibecoding_orch.gates.path_match import is_allowed_path


def _now_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _review_schema_path() -> Path:
    return Path(__file__).resolve().parents[5] / "schemas" / "review_report.v1.json"


def _is_allowed_path(path: str, allowed_paths: list[str]) -> bool:
    return is_allowed_path(path, allowed_paths)


def _is_runtime_artifact_file(path: str) -> bool:
    normalized = path.strip().replace("\\", "/").lstrip("./")
    if "/" in normalized:
        return False
    return normalized in {"patch.diff", "diff_name_only.txt", "mock_output.txt"}


def _extract_diff_files(diff_text: str) -> list[str]:
    files: list[str] = []
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4:
                raw = parts[3]
                path = raw[2:] if raw.startswith(("a/", "b/")) else raw
                if path:
                    files.append(path)
        elif line.startswith("rename to "):
            path = line.replace("rename to ", "", 1).strip()
            if path:
                files.append(path)
    seen: set[str] = set()
    ordered: list[str] = []
    for item in files:
        if _is_runtime_artifact_file(item):
            continue
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _contract_alignment(
    contract: dict[str, Any],
    diff_text: str,
    inputs_meta: dict[str, Any] | None,
) -> dict[str, Any]:
    violations: list[str] = []
    allowed_paths = contract.get("allowed_paths", [])
    if not isinstance(allowed_paths, list) or len(allowed_paths) == 0:
        violations.append("allowed_paths empty or invalid")
        allowed_paths = []

    diff_files = _extract_diff_files(diff_text) if diff_text.strip() else []
    if allowed_paths and diff_files:
        out_of_scope = [name for name in diff_files if not _is_allowed_path(name, allowed_paths)]
        if out_of_scope:
            violations.append(f"diff touches outside allowed_paths: {out_of_scope}")

    if inputs_meta:
        if not str(inputs_meta.get("baseline_ref", "")).strip():
            violations.append("baseline_ref missing")
        if not str(inputs_meta.get("head_ref", "")).strip():
            violations.append("head_ref missing")

    return {"passed": len(violations) == 0, "violations": violations}


def _diff_policy(contract: dict[str, Any]) -> dict[str, Any]:
    tool_permissions = contract.get("tool_permissions")
    filesystem = ""
    if isinstance(tool_permissions, dict):
        filesystem = str(tool_permissions.get("filesystem", "")).strip().lower()
    task_type = str(contract.get("task_type", "")).strip().upper()
    if task_type in {"PLAN", "SEARCH", "REVIEW", "TEST"}:
        return {"requires_diff": False, "forbid_diff": False, "reason": f"task_type={task_type}"}
    required_outputs = contract.get("required_outputs")
    wants_patch = False
    if isinstance(required_outputs, list):
        for item in required_outputs:
            if not isinstance(item, dict):
                continue
            output_type = str(item.get("type", "")).strip().lower()
            if output_type in {"patch", "commit"}:
                wants_patch = True
                break
    if filesystem == "read-only":
        return {"requires_diff": False, "forbid_diff": True, "reason": "filesystem=read-only"}
    if wants_patch:
        return {"requires_diff": True, "forbid_diff": False, "reason": "required_outputs=patch|commit"}
    return {"requires_diff": False, "forbid_diff": False, "reason": "required_outputs_without_patch"}


def _build_evidence(test_report: dict[str, Any]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    artifacts = test_report.get("artifacts")
    if isinstance(artifacts, list):
        for item in artifacts:
            if isinstance(item, dict) and item.get("name") and item.get("path") and item.get("sha256"):
                evidence.append(item)
    return evidence


class Reviewer:
    def review_task(
        self,
        contract: dict[str, Any],
        diff_text: str,
        test_report: dict[str, Any],
        reviewer_meta: dict[str, Any] | None = None,
        inputs_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        issues: list[str] = []

        policy = _diff_policy(contract)
        has_diff = bool(diff_text.strip())
        if not has_diff and policy.get("requires_diff"):
            issues.append("diff is empty; no auditable code change was produced")
        if has_diff and policy.get("forbid_diff"):
            issues.append("read-only tasks must not produce a diff")

        test_status = str(test_report.get("status", "")).upper()
        task_type = str(contract.get("task_type", "")).strip().upper()
        test_artifacts = test_report.get("artifacts") if isinstance(test_report, dict) else None
        missing_tests = test_status in {"", "ERROR"} and not test_artifacts
        if not (task_type == "REVIEW" and missing_tests):
            if not test_status:
                issues.append("test result is missing")
            elif test_status != "PASS":
                issues.append("tests did not pass")

        scope_check = _contract_alignment(contract, diff_text, inputs_meta)
        if not scope_check.get("passed", False):
            issues.extend([f"contract alignment: {item}" for item in scope_check.get("violations", [])])

        verdict = "PASS" if len(issues) == 0 else "FAIL"
        reviewer_payload = {
            "role": "REVIEWER",
            "agent_id": reviewer_meta.get("agent_id", "reviewer") if reviewer_meta else "reviewer",
        }
        if reviewer_meta and reviewer_meta.get("codex_thread_id"):
            reviewer_payload["codex_thread_id"] = reviewer_meta.get("codex_thread_id")

        report: dict[str, Any] = {
            "task_id": contract.get("task_id"),
            "reviewer": reviewer_payload,
            "reviewed_at": _now_ts(),
            "verdict": verdict,
            "summary": "review passed" if verdict == "PASS" else "; ".join(issues),
            "scope_check": scope_check,
            "evidence": _build_evidence(test_report),
            "produced_diff": False,
        }
        if issues:
            report["notes"] = "; ".join(issues)
        return report


class CodexReviewer:
    def __init__(self) -> None:
        self._validator = ContractValidator(schema_root=_review_schema_path().parent)

    def review_task(
        self,
        contract: dict[str, Any],
        diff_text: str,
        test_report: dict[str, Any],
        worktree_path: Path,
        reviewer_meta: dict[str, Any] | None = None,
        inputs_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        task_id = contract.get("task_id", "task")
        policy = _diff_policy(contract)
        tool_permissions = contract.get("tool_permissions") if isinstance(contract.get("tool_permissions"), dict) else {}
        required_outputs = contract.get("required_outputs") if isinstance(contract.get("required_outputs"), list) else []
        instruction = (
            "You are a strict code reviewer. You must remain read-only and must not modify files. "
            "Return a ReviewReport JSON based on the diff and test results, and it must satisfy the schema. "
            "produced_diff must be false.\n\n"
            "contract_summary:\n"
            f"- task_type: {contract.get('task_type', '')}\n"
            f"- tool_permissions.filesystem: {tool_permissions.get('filesystem', '')}\n"
            f"- required_outputs: {json.dumps(required_outputs, ensure_ascii=False)}\n"
            f"- diff_policy: {json.dumps(policy, ensure_ascii=False)}\n\n"
            f"task_id: {task_id}\n"
            f"diff:\n{diff_text}\n\n"
            f"test_report:\n{json.dumps(test_report, ensure_ascii=False)}"
        )

        schema_path = _review_schema_path().resolve()
        cmd = [
            "codex",
            "exec",
            "--json",
            "--sandbox",
            "read-only",
        ]
        use_output_schema = os.getenv("OPENVIBECODING_CODEX_USE_OUTPUT_SCHEMA", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if use_output_schema:
            cmd.extend(["--output-schema", str(schema_path)])
        model = os.getenv("OPENVIBECODING_CODEX_MODEL", "").strip()
        if model:
            cmd.extend(["--model", model])
        cmd.append(instruction)

        proc = subprocess.Popen(
            cmd,
            cwd=worktree_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        final_report: dict[str, Any] | None = None
        if proc.stdout is not None:
            for line in proc.stdout:
                if not line.strip():
                    continue
                parsed = parse_codex_event_line(line)
                if parsed.is_json:
                    payload = parsed.payload
                    try:
                        self._validator.validate_report(payload, "review_report.v1.json")
                        final_report = payload
                    except Exception:
                        continue

        stderr_text = ""
        if proc.stderr is not None:
            stderr_text = proc.stderr.read()
        exit_code = proc.wait()
        if exit_code != 0:
            raise RuntimeError(f"codex reviewer failed: {stderr_text.strip() or exit_code}")

        if final_report is None:
            raise RuntimeError("codex reviewer missing review report")

        if final_report.get("produced_diff") is not False:
            raise RuntimeError("codex reviewer produced_diff must be false")

        scope_check = _contract_alignment(contract, diff_text, inputs_meta)
        final_report["scope_check"] = scope_check
        if not final_report.get("evidence"):
            final_report["evidence"] = _build_evidence(test_report)

        audit_only = contract.get("audit_only") is True
        if not diff_text.strip():
            if audit_only:
                final_report["verdict"] = "PASS"
                final_report["summary"] = "diff is empty; no-change review is allowed"
                final_report["notes"] = "This task produced no code change and passes under the audit-only rule."
            else:
                final_report["verdict"] = "FAIL"
                final_report["summary"] = "diff is empty; approval is not authorized"
                final_report["notes"] = "Strict mode forbids empty diffs unless audit_only=true."

        reviewer_payload = {
            "role": "REVIEWER",
            "agent_id": reviewer_meta.get("agent_id", "reviewer") if reviewer_meta else "reviewer",
        }
        if reviewer_meta and reviewer_meta.get("codex_thread_id"):
            reviewer_payload["codex_thread_id"] = reviewer_meta.get("codex_thread_id")
        final_report["reviewer"] = reviewer_payload
        final_report.setdefault("reviewed_at", _now_ts())
        return final_report


def run_review(contract: dict[str, Any], diff_text: str, test_report: dict[str, Any]) -> dict[str, Any]:
    return Reviewer().review_task(contract, diff_text, test_report)
