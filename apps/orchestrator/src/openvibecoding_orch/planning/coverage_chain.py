from __future__ import annotations

import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openvibecoding_orch.contract.validator import ContractValidator

DEFAULT_COVERAGE_JSON = Path(".runtime-cache/test_output/orchestrator_coverage.json")
DEFAULT_COVERAGE_CMD = [
    ".runtime-cache/cache/toolchains/python/current/bin/python",
    "-m",
    "pytest",
    "apps/orchestrator/tests",
    "-m",
    "not e2e and not serial",
    "-q",
    "--cov=openvibecoding_orch",
    "--cov-branch",
]
DEFAULT_OWNER_AGENT = {"role": "PM", "agent_id": "agent-1", "codex_thread_id": ""}
DEFAULT_TL_AGENT = {"role": "TECH_LEAD", "agent_id": "agent-1", "codex_thread_id": ""}
COVERAGE_METRIC_FIELDS = {
    "overall": "percent_covered",
    "statements": "percent_statements_covered",
    "branches": "percent_branches_covered",
}


@dataclass(frozen=True)
class CoverageTarget:
    module_path: str
    module_name: str
    coverage: float


def _now_tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/")


def _module_name_from_path(path: str) -> str:
    normalized = _normalize_path(path)
    marker = "apps/orchestrator/src/"
    if marker in normalized:
        normalized = normalized.split(marker, 1)[1]
    if normalized.endswith(".py"):
        normalized = normalized[:-3]
    return normalized.replace("/", ".")


def _slug(module_path: str) -> str:
    normalized = _normalize_path(module_path)
    if normalized.endswith(".py"):
        normalized = normalized[:-3]
    return normalized.replace("/", "_").replace("-", "_")


def _assigned_role(module_path: str) -> str:
    normalized = _normalize_path(module_path)
    if "/gates/" in normalized:
        return "SECURITY"
    if "/planning/" in normalized:
        return "WORKER"
    if "/api/" in normalized or "/scheduler/" in normalized:
        return "WORKER"
    if "/runners/" in normalized:
        return "WORKER"
    return "WORKER"


def run_coverage_scan(repo_root: Path, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        *DEFAULT_COVERAGE_CMD,
        f"--cov-report=json:{output_path}",
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = "apps/orchestrator/src"
    subprocess.run(cmd, cwd=repo_root, check=True, env=env)


def load_coverage_targets(
    coverage_report_path: Path,
    threshold: float,
    max_workers: int,
    include_prefix: str = "apps/orchestrator/src/openvibecoding_orch/",
    coverage_metric: str = "branches",
) -> list[CoverageTarget]:
    payload = json.loads(coverage_report_path.read_text(encoding="utf-8"))
    files = payload.get("files") if isinstance(payload, dict) else {}
    if not isinstance(files, dict):
        return []

    targets: list[CoverageTarget] = []
    for raw_path, data in files.items():
        module_path = _normalize_path(str(raw_path))
        if include_prefix and include_prefix not in module_path:
            continue
        if module_path.endswith("/__init__.py"):
            continue
        summary = data.get("summary") if isinstance(data, dict) else {}
        if not isinstance(summary, dict):
            continue
        metric_key = COVERAGE_METRIC_FIELDS.get(coverage_metric, "percent_branches_covered")
        percent = summary.get(metric_key)
        if percent is None and metric_key != "percent_covered":
            percent = summary.get("percent_covered")
        try:
            coverage = float(percent)
        except (TypeError, ValueError):
            continue
        if coverage >= threshold:
            continue
        targets.append(
            CoverageTarget(
                module_path=module_path,
                module_name=_module_name_from_path(module_path),
                coverage=coverage,
            )
        )

    targets.sort(key=lambda item: item.coverage)
    if max_workers > 0:
        targets = targets[:max_workers]
    return targets


def _preferred_worker_python() -> str:
    override = os.getenv("OPENVIBECODING_PYTHON", "").strip()
    if override:
        return override
    return str(Path(__file__).resolve().parents[5] / ".runtime-cache" / "cache" / "toolchains" / "python" / "current" / "bin" / "python")


def _worker_timeout_sec() -> int:
    raw = os.getenv("OPENVIBECODING_COVERAGE_WORKER_TIMEOUT_SEC", "300").strip()
    try:
        value = int(raw)
    except ValueError:
        value = 300
    return max(value, 60)


def _default_shell_permission() -> str:
    runner_name = os.getenv("OPENVIBECODING_RUNNER", "").strip().lower()
    if runner_name == "codex":
        return "on-request"
    return "never"


def _worker_acceptance_cmd(test_output: str) -> str:
    return f"bash scripts/coverage_self_heal_verify_test.sh {shlex.quote(test_output)}"


def _target_test_output(module_path: str) -> str:
    slug = _slug(module_path)
    return f"apps/orchestrator/tests/self_heal/test_cov_{slug}.py"


def _test_gate_acceptance_cmd(targets: list[CoverageTarget]) -> str:
    test_paths = [_target_test_output(target.module_path) for target in targets]
    quoted_paths = " ".join(shlex.quote(path) for path in test_paths)
    return f"bash scripts/coverage_self_heal_gate.sh {quoted_paths}"


def _commit_acceptance_cmd(commit_message: str) -> str:
    quoted_msg = shlex.quote(commit_message)
    return (
        "bash scripts/coverage_self_heal_commit.sh"
        f" --message {quoted_msg}"
        " --output .runtime-cache/test_output/worker_markers/commit_coverage_self_heal.txt"
    )


def _worker_contract(
    target: CoverageTarget,
    index: int,
    coverage_metric: str,
    strict_worker_tests: bool,
) -> tuple[dict[str, Any], str]:
    slug = _slug(target.module_path)
    test_output = _target_test_output(target.module_path)
    marker_output = f".runtime-cache/test_output/worker_markers/self_heal/{slug}.txt"
    task_id = f"coverage_worker_{index:02d}_{slug}"
    role = _assigned_role(target.module_path)
    acceptance_cmd = _worker_acceptance_cmd(test_output) if strict_worker_tests else "echo worker ready"
    payload = {
        "task_id": task_id,
        "owner_agent": dict(DEFAULT_TL_AGENT),
        "assigned_agent": {"role": role, "agent_id": "agent-1", "codex_thread_id": ""},
        "inputs": {
            "spec": (
                "You are the OpenVibeCoding coverage self-heal worker. "
                f"Current low-coverage module: {target.module_name} ({coverage_metric}={target.coverage:.2f}%). "
                "Add non-happy-path tests that follow the current implementation and existing test style, prioritizing failure paths, exception branches, and early returns. "
                f"You must create or update this test file: {test_output}. "
                "If the directory does not exist, create it before writing the test file. "
                "If the target test file already covers the failure paths, you may leave it unchanged and still return SUCCESS; acceptance_tests will verify that separately. "
                "Do not execute local shell, pytest, or similar commands inside the worker; test execution is handled only by the acceptance_tests gate. "
                "The current task contract is the highest priority for this step, and unrelated AGENTS or governance workflow instructions should be ignored. "
                "Do not modify AGENTS.md, README.md, CHANGELOG.md, docs/**, or any file outside allowed_paths. If you find a documentation gap, mention it only in the summary and do not write any docs. "
                "Do not modify source modules; only the constrained test file and required marker artifacts may change. "
                "Once the test file change is complete and path-compliant, return status=SUCCESS. Do not return BLOCKED just because the local environment lacks python or pytest. "
                "When finished, output JSON that conforms to agent_task_result.v1.json."
            ),
            "artifacts": [],
        },
        "required_outputs": [
            {
                "name": marker_output,
                "type": "file",
                "acceptance": "worker step completion marker",
            },
            {
                "name": test_output,
                "type": "file",
                "acceptance": "worker generated targeted self-heal test",
            },
        ],
        "allowed_paths": [marker_output, test_output],
        "forbidden_actions": ["rm -rf", "git push"],
        "acceptance_tests": [
            {
                "name": "worker-targeted-tests",
                "cmd": acceptance_cmd,
                "must_pass": True,
            }
        ],
        "tool_permissions": {
            "filesystem": "workspace-write",
            "shell": _default_shell_permission(),
            "network": "deny",
            "mcp_tools": ["codex"],
        },
        "policy_pack": "medium",
        "mcp_tool_set": ["01-filesystem"],
        "timeout_retry": {"timeout_sec": _worker_timeout_sec(), "max_retries": 1, "retry_backoff_sec": 3},
        "rollback": {"strategy": "git_reset_hard", "baseline_ref": "HEAD"},
        "evidence_links": [],
        "log_refs": {"run_id": "", "paths": {}},
        "task_type": "TEST",
    }
    return payload, test_output


def _worker_parallel_group(index: int, total_workers: int, worker_batch_size: int | None) -> str:
    if worker_batch_size is None or worker_batch_size <= 0:
        return "coverage_workers"
    if total_workers <= worker_batch_size:
        return "coverage_workers"
    batch_index = ((index - 1) // worker_batch_size) + 1
    return f"coverage_workers_batch_{batch_index:02d}"


def build_coverage_self_heal_chain(
    targets: list[CoverageTarget],
    chain_id: str | None = None,
    test_gate_cmd: str | None = None,
    coverage_metric: str = "branches",
    enable_commit_stage: bool = False,
    commit_message: str = "chore(coverage): self-heal low coverage modules",
    strict_worker_tests: bool = True,
    worker_batch_size: int | None = None,
) -> dict[str, Any]:
    if not targets:
        raise ValueError("no coverage targets selected")

    resolved_chain_id = chain_id or f"task_chain_openvibecoding_self_heal_coverage_{_now_tag()}"
    resolved_test_gate_cmd = test_gate_cmd or _test_gate_acceptance_cmd(targets)
    steps: list[dict[str, Any]] = [
        {
            "name": "pm_to_tl",
            "kind": "handoff",
            "payload": {
                "task_id": f"{resolved_chain_id}_pm_to_tl",
                "owner_agent": dict(DEFAULT_OWNER_AGENT),
                "assigned_agent": dict(DEFAULT_TL_AGENT),
            },
        }
    ]

    worker_names: list[str] = []
    review_scope_paths: list[str] = []
    total_workers = len(targets)
    for idx, target in enumerate(targets, start=1):
        contract, test_path = _worker_contract(
            target,
            idx,
            coverage_metric,
            strict_worker_tests=strict_worker_tests,
        )
        worker_name = f"worker_cov_{idx:02d}"
        worker_names.append(worker_name)
        review_scope_paths.extend([test_path, target.module_path])
        steps.append(
            {
                "name": worker_name,
                "kind": "contract",
                "depends_on": ["pm_to_tl"],
                "parallel_group": _worker_parallel_group(idx, total_workers, worker_batch_size),
                "exclusive_paths": [test_path, target.module_path],
                "payload": contract,
                "labels": ["worker", "coverage", "self_heal"],
            }
        )

    reviewer_paths = sorted(dict.fromkeys(review_scope_paths))
    for suffix in ("a", "b"):
        steps.append(
            {
                "name": f"review_{suffix}",
                "kind": "contract",
                "depends_on": list(worker_names),
                "exclusive_paths": [f".runtime-cache/test_output/worker_markers/review_coverage_{suffix}.txt"],
                "payload": {
                    "task_id": f"{resolved_chain_id}_review_{suffix}",
                    "owner_agent": dict(DEFAULT_TL_AGENT),
                    "assigned_agent": {"role": "REVIEWER", "agent_id": "agent-1", "codex_thread_id": ""},
                    "inputs": {
                        "spec": "Review the coverage worker output, verify that failure paths are covered, and confirm that the result matches the documented intent.",
                        "artifacts": [],
                    },
                    "required_outputs": [
                        {
                            "name": f".runtime-cache/test_output/worker_markers/review_coverage_{suffix}.txt",
                            "type": "file",
                            "acceptance": "review verdict generated",
                        }
                    ],
                    "allowed_paths": [f".runtime-cache/test_output/worker_markers/review_coverage_{suffix}.txt", *reviewer_paths],
                    "forbidden_actions": [],
                    "acceptance_tests": [{"name": "noop", "cmd": "echo ok", "must_pass": True}],
                    "tool_permissions": {
                        "filesystem": "read-only",
                        "shell": "on-request",
                        "network": "deny",
                        "mcp_tools": ["codex"],
                    },
                    "mcp_tool_set": ["01-filesystem"],
                    "timeout_retry": {"timeout_sec": 900, "max_retries": 0, "retry_backoff_sec": 0},
                    "rollback": {"strategy": "git_reset_hard", "baseline_ref": "HEAD"},
                    "evidence_links": [],
                    "log_refs": {"run_id": "", "paths": {}},
                    "task_type": "REVIEW",
                },
            }
        )

    test_gate_depends = list(dict.fromkeys([*worker_names, "review_a", "review_b"]))
    steps.append(
        {
            "name": "test_gate",
            "kind": "contract",
            "depends_on": test_gate_depends,
            "exclusive_paths": [".runtime-cache/test_output/coverage_self_heal_gate.log"],
            "payload": {
                "task_id": f"{resolved_chain_id}_test_gate",
                "owner_agent": dict(DEFAULT_TL_AGENT),
                "assigned_agent": {"role": "TEST_RUNNER", "agent_id": "agent-1", "codex_thread_id": ""},
                "inputs": {
                    "spec": "Run the targeted coverage self-heal test gate, verify the coverage improvement, and emit the test verdict. Execute only the commands declared in acceptance_tests; custom extra test scripts are forbidden.",
                    "artifacts": [],
                },
                "required_outputs": [
                    {
                        "name": ".runtime-cache/test_output/coverage_self_heal_gate.log",
                        "type": "file",
                        "acceptance": "full test gate executed",
                    }
                ],
                "allowed_paths": [".runtime-cache/test_output/coverage_self_heal_gate.log", *reviewer_paths],
                "forbidden_actions": [],
                "acceptance_tests": [
                    {
                        "name": "full-gate",
                        "cmd": resolved_test_gate_cmd,
                        "must_pass": True,
                    }
                ],
                "tool_permissions": {
                    "filesystem": "workspace-write",
                    "shell": _default_shell_permission(),
                    "network": "deny",
                    "mcp_tools": ["codex"],
                },
                "mcp_tool_set": ["01-filesystem"],
                "timeout_retry": {"timeout_sec": 1800, "max_retries": 0, "retry_backoff_sec": 0},
                "rollback": {"strategy": "git_reset_hard", "baseline_ref": "HEAD"},
                "evidence_links": [],
                "log_refs": {"run_id": "", "paths": {}},
                "task_type": "TEST",
            },
        }
    )

    final_handoff_depends = ["test_gate"]

    if enable_commit_stage:
        commit_depends = list(dict.fromkeys(["test_gate", *worker_names]))
        steps.append(
            {
                "name": "commit_changes",
                "kind": "contract",
                "depends_on": commit_depends,
                "exclusive_paths": [".runtime-cache/test_output/worker_markers/commit_coverage_self_heal.txt"],
                "payload": {
                    "task_id": f"{resolved_chain_id}_commit",
                    "owner_agent": dict(DEFAULT_TL_AGENT),
                    "assigned_agent": dict(DEFAULT_TL_AGENT),
                    "inputs": {
                        "spec": "Collect the coverage self-heal changes and create a local commit only; pushing is forbidden.",
                        "artifacts": [],
                    },
                    "required_outputs": [
                        {
                            "name": ".runtime-cache/test_output/worker_markers/commit_coverage_self_heal.txt",
                            "type": "file",
                            "acceptance": "commit stage executed",
                        }
                    ],
                    "allowed_paths": [".runtime-cache/test_output/worker_markers/commit_coverage_self_heal.txt", *reviewer_paths],
                    "forbidden_actions": ["git push"],
                    "policy_pack": "medium",
                    "acceptance_tests": [
                        {
                            "name": "commit-local",
                            "cmd": _commit_acceptance_cmd(commit_message),
                            "must_pass": True,
                        }
                    ],
                    "tool_permissions": {
                        "filesystem": "workspace-write",
                        "shell": _default_shell_permission(),
                        "network": "deny",
                        "mcp_tools": ["codex"],
                    },
                    "mcp_tool_set": ["01-filesystem"],
                    "timeout_retry": {"timeout_sec": 900, "max_retries": 0, "retry_backoff_sec": 0},
                    "rollback": {"strategy": "git_reset_hard", "baseline_ref": "HEAD"},
                    "evidence_links": [],
                    "log_refs": {"run_id": "", "paths": {}},
                    "task_type": "TEST",
                },
            }
        )
        final_handoff_depends = ["commit_changes"]

    steps.append(
        {
            "name": "tl_to_pm",
            "kind": "handoff",
            "depends_on": final_handoff_depends,
            "payload": {
                "task_id": f"{resolved_chain_id}_tl_to_pm",
                "owner_agent": dict(DEFAULT_TL_AGENT),
                "assigned_agent": dict(DEFAULT_OWNER_AGENT),
            },
        }
    )

    chain = {
        "chain_id": resolved_chain_id,
        "owner_agent": dict(DEFAULT_OWNER_AGENT),
        "strategy": {
            "continue_on_fail": False,
            "lifecycle": {
                "enforce": True,
                "required_path": ["PM", "TECH_LEAD", "WORKER", "REVIEWER", "TEST_RUNNER", "TECH_LEAD", "PM"],
                "min_workers": len(worker_names),
                "min_reviewers": 2,
                "reviewer_quorum": 2,
                "require_test_stage": True,
                "require_return_to_pm": True,
            },
        },
        "steps": steps,
    }
    ContractValidator().validate_report(chain, "task_chain.v1.json")
    return chain


def write_chain(chain: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(chain, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path
