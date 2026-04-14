from __future__ import annotations

import json
import re
import uuid
from typing import Any

from .intake_policy_helpers import _ensure_agent, _normalize_constraints

_DEFAULT_OWNER = {"role": "PM", "agent_id": "agent-1"}
_PLAN_TYPES = ["UI_UX", "TEST", "BACKEND", "FRONTEND", "OPS", "SECURITY", "AI"]
_BUNDLE_DEFAULT_TOOL_PERMS = {
    "filesystem": "workspace-write",
    "shell": "never",
    "network": "deny",
    "mcp_tools": ["codex"],
}
_PLAN_KEYS = {
    "plan_id",
    "task_id",
    "parent_task_id",
    "plan_type",
    "owner_agent",
    "assigned_agent",
    "task_type",
    "spec",
    "artifacts",
    "required_outputs",
    "allowed_paths",
    "forbidden_actions",
    "acceptance_tests",
    "tool_permissions",
    "mcp_tool_set",
    "audit_only",
    "timeout_retry",
    "rollback",
    "evidence_links",
    "labels",
}
_DEFAULT_NONTRIVIAL_ACCEPTANCE_TEST = {
    "name": "repo_hygiene",
    "cmd": "bash scripts/check_repo_hygiene.sh",
    "must_pass": True,
}
_VALID_ASSIGNED_ROLES = {
    "PM",
    "TECH_LEAD",
    "WORKER",
    "REVIEWER",
    "TEST_RUNNER",
    "SEARCHER",
    "RESEARCHER",
    "UI_UX",
    "FRONTEND",
    "BACKEND",
    "AI",
    "SECURITY",
    "INFRA",
    "TEST",
    "OPS",
}


def _build_plan_fallback(payload: dict[str, Any], answers: list[str]) -> dict[str, Any]:
    plan_id = f"plan-{uuid.uuid4().hex[:8]}"
    task_id = f"task-{uuid.uuid4().hex[:8]}"
    objective = str(payload.get("objective", "")).strip()
    allowed_paths = payload.get("allowed_paths", [])
    constraints = _normalize_constraints(payload.get("constraints"))
    acceptance_tests = payload.get("acceptance_tests") or []
    if not acceptance_tests:
        acceptance_tests = [dict(_DEFAULT_NONTRIVIAL_ACCEPTANCE_TEST)]
    mcp_tool_set = payload.get("mcp_tool_set")
    if not isinstance(mcp_tool_set, list) or not any(str(item).strip() for item in mcp_tool_set):
        raise ValueError("mcp_tool_set missing from intake payload")
    owner_agent = _ensure_agent(payload.get("owner_agent"), _DEFAULT_OWNER)
    assigned_agent = {"role": "WORKER", "agent_id": "agent-1"}
    spec_parts = [objective] if objective else []
    if constraints:
        spec_parts.append("Constraints: " + "; ".join(constraints))
    if answers:
        spec_parts.append("Answers: " + "; ".join(answers))
    spec = "\n".join(spec_parts).strip() or "pending objective"
    plan = {
        "plan_id": plan_id,
        "task_id": task_id,
        "plan_type": payload.get("plan_type") or "BACKEND",
        "owner_agent": owner_agent,
        "assigned_agent": assigned_agent,
        "task_type": "IMPLEMENT",
        "spec": spec,
        "artifacts": [],
        "required_outputs": [
            {
                "name": "patch.diff",
                "type": "patch",
                "acceptance": "generate auditable code changes",
            }
        ],
        "allowed_paths": allowed_paths,
        "forbidden_actions": payload.get("forbidden_actions") or [],
        "acceptance_tests": acceptance_tests,
        "tool_permissions": payload.get("tool_permissions")
        or {
            "filesystem": "workspace-write",
            "shell": "on-request",
            "network": "deny",
            "mcp_tools": ["codex"],
        },
        "mcp_tool_set": mcp_tool_set,
        "timeout_retry": payload.get("timeout_retry")
        or {
            "timeout_sec": 900,
            "max_retries": 0,
            "retry_backoff_sec": 0,
        },
        "rollback": payload.get("rollback") or {"strategy": "git_reset_hard", "baseline_ref": "HEAD"},
        "evidence_links": payload.get("evidence_links") or [],
    }
    audit_only = payload.get("audit_only")
    if isinstance(audit_only, bool):
        plan["audit_only"] = audit_only
    return plan


def _clone_plan(plan: dict[str, Any], plan_type: str) -> dict[str, Any]:
    clone = json.loads(json.dumps(plan, ensure_ascii=False))
    plan_id = str(clone.get("plan_id") or f"plan-{uuid.uuid4().hex[:8]}")
    suffix = plan_type.lower()
    if not plan_id.endswith(suffix):
        clone["plan_id"] = f"{plan_id}-{suffix}"
    clone["plan_type"] = plan_type
    labels = clone.get("labels") if isinstance(clone.get("labels"), list) else []
    clone["labels"] = list({*(str(item) for item in labels if str(item).strip()), plan_type})
    return clone


def _paths_overlap(left: str, right: str) -> bool:
    left = left.strip()
    right = right.strip()
    if not left or not right:
        return True
    left_prefix = left.split("*", 1)[0].split("?", 1)[0]
    right_prefix = right.split("*", 1)[0].split("?", 1)[0]
    if not left_prefix or not right_prefix:
        return True
    if left_prefix == right_prefix:
        return True
    if left_prefix.startswith(right_prefix.rstrip("/") + "/"):
        return True
    if right_prefix.startswith(left_prefix.rstrip("/") + "/"):
        return True
    return False


def _normalize_bundle_plan(
    plan: dict[str, Any],
    owner_agent: dict[str, str],
    acceptance_tests: list[dict[str, Any]],
    plan_type: str | None,
) -> dict[str, Any]:
    updated = {key: plan[key] for key in _PLAN_KEYS if key in plan}
    plan_id = str(updated.get("plan_id", "")).strip()
    if not plan_id or len(plan_id) < 8:
        updated["plan_id"] = f"plan-{uuid.uuid4().hex[:8]}"
    task_id = str(updated.get("task_id", "")).strip()
    if not task_id or len(task_id) < 8:
        updated["task_id"] = f"task-{uuid.uuid4().hex[:8]}"
    spec_value = updated.get("spec")
    if isinstance(spec_value, str):
        if not spec_value.strip():
            updated["spec"] = "pending objective"
    elif spec_value is not None:
        updated["spec"] = json.dumps(spec_value, ensure_ascii=False)
    else:
        updated["spec"] = "pending objective"
    if plan_type and not str(updated.get("plan_type", "")).strip():
        updated["plan_type"] = plan_type
    normalized_plan_type = str(updated.get("plan_type", "")).strip()
    if normalized_plan_type not in _PLAN_TYPES:
        if plan_type in _PLAN_TYPES:
            updated["plan_type"] = plan_type
        else:
            updated["plan_type"] = "BACKEND"
    updated["owner_agent"] = _ensure_agent(updated.get("owner_agent"), owner_agent)
    if isinstance(updated.get("owner_agent"), dict):
        updated["owner_agent"]["agent_id"] = "agent-1"
    assigned = updated.get("assigned_agent")
    if not isinstance(assigned, dict):
        assigned = {}
    assigned_role = str(assigned.get("role", "")).strip().upper() or "WORKER"
    assigned_agent_id = str(assigned.get("agent_id") or "agent-1").strip() or "agent-1"
    if assigned_role not in _VALID_ASSIGNED_ROLES:
        assigned_role = "WORKER"
    updated["assigned_agent"] = {"role": assigned_role, "agent_id": assigned_agent_id}
    task_type = str(updated.get("task_type", "")).strip().upper()
    if task_type not in {"PLAN", "IMPLEMENT", "REVIEW", "TEST", "SEARCH"}:
        updated["task_type"] = "IMPLEMENT"
    else:
        updated["task_type"] = task_type
    paths = updated.get("allowed_paths")
    if not isinstance(paths, list) or not any(str(item).strip() for item in paths):
        raise ValueError("plan bundle requires non-empty allowed_paths")
    updated["allowed_paths"] = [str(item).strip() for item in paths if str(item).strip()]
    tests = updated.get("acceptance_tests")
    if not isinstance(tests, list) or not tests:
        updated["acceptance_tests"] = acceptance_tests
    tool_permissions = updated.get("tool_permissions")
    if not isinstance(tool_permissions, dict):
        tool_permissions = {}
    merged_tool_permissions = dict(_BUNDLE_DEFAULT_TOOL_PERMS)
    merged_tool_permissions.update(tool_permissions)
    updated["tool_permissions"] = merged_tool_permissions
    if not str(updated.get("task_type", "")).strip():
        updated["task_type"] = "IMPLEMENT"
    return updated


def _extract_parallelism(constraints: list[str] | None) -> int | None:
    if not isinstance(constraints, list):
        return None
    for item in constraints:
        text = str(item)
        if not text:
            continue
        match = re.search(r"(?:parallelism|\u5e76\u884c\u5ea6)\s*=\s*(\d+)", text)
        if match:
            try:
                value = int(match.group(1))
            except (TypeError, ValueError):
                continue
            if value > 0:
                return value
    return None


def _rebalance_bundle_paths(
    plans: list[dict[str, Any]],
    allowed_paths: list[str],
    desired_parallelism: int | None,
) -> list[dict[str, Any]]:
    if not allowed_paths:
        return plans
    target_count = len(plans)
    if desired_parallelism:
        target_count = min(desired_parallelism, len(allowed_paths))
    else:
        target_count = min(target_count, len(allowed_paths))
    if target_count <= 0:
        return plans
    trimmed = plans[:target_count]
    buckets: list[list[str]] = [[] for _ in range(target_count)]
    for idx, path in enumerate(allowed_paths):
        buckets[idx % target_count].append(path)
    for plan, bucket in zip(trimmed, buckets):
        plan["allowed_paths"] = bucket
    return trimmed


def _validate_plan_bundle_paths(plans: list[dict[str, Any]]) -> None:
    resolved: list[tuple[str, list[str]]] = []
    for idx, plan in enumerate(plans):
        name = str(plan.get("plan_id") or f"plan_{idx}")
        paths = plan.get("allowed_paths") if isinstance(plan, dict) else []
        if not isinstance(paths, list) or not paths:
            raise ValueError(f"plan bundle missing allowed_paths: {name}")
        resolved.append((name, [str(item).strip() for item in paths if str(item).strip()]))
    for idx, (left_name, left_paths) in enumerate(resolved):
        for right_name, right_paths in resolved[idx + 1 :]:
            for left in left_paths:
                for right in right_paths:
                    if _paths_overlap(left, right):
                        raise ValueError(f"plan bundle allowed_paths overlap: {left_name} vs {right_name}")
