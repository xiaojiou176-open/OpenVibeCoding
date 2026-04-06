from __future__ import annotations

import json
from typing import Any

from cortexpilot_orch.chain.parsers import _as_int, _is_subsequence
from cortexpilot_orch.store.run_store import RunStore

_HANDOFF_ROLE_ORDER = [
    "PM",
    "TECH_LEAD",
    "SEARCHER",
    "RESEARCHER",
    "UI_UX",
    "FRONTEND",
    "BACKEND",
    "AI",
    "SECURITY",
    "INFRA",
    "OPS",
    "WORKER",
    "REVIEWER",
    "TEST",
    "TEST_RUNNER",
]
_PRIMARY_HANDOFF_ORDER = ["PM", "TECH_LEAD", "WORKER", "REVIEWER", "TEST_RUNNER"]
_DEFAULT_LIFECYCLE_PATH = [
    "PM",
    "TECH_LEAD",
    "WORKER",
    "REVIEWER",
    "TEST_RUNNER",
    "TECH_LEAD",
    "PM",
]
_WORKER_LIKE_ROLES = {"WORKER", "FRONTEND", "BACKEND", "AI", "SECURITY", "INFRA", "OPS"}
_TEST_LIKE_ROLES = {"TEST", "TEST_RUNNER"}
_LIFECYCLE_ROLE_ALIASES = {
    "TEST": "TEST_RUNNER",
}


def _agent_role(agent: dict[str, Any]) -> str:
    role = agent.get("role") if isinstance(agent, dict) else ""
    return str(role).strip().upper()


def _validate_handoff_chain(contract: dict[str, Any]) -> tuple[bool, str]:
    chain = contract.get("handoff_chain") if isinstance(contract, dict) else {}
    if not isinstance(chain, dict):
        return True, ""
    enabled = bool(chain.get("enabled", False))
    raw_roles = chain.get("roles") if isinstance(chain.get("roles"), list) else []
    roles = [str(item).strip().upper() for item in raw_roles if str(item).strip()]
    if enabled and not roles:
        return False, "handoff_chain.enabled requires roles"
    if roles:
        last_idx = -1
        for role in roles:
            if role not in _HANDOFF_ROLE_ORDER:
                return False, f"handoff_chain role invalid: {role}"
            idx = _HANDOFF_ROLE_ORDER.index(role)
            if idx <= last_idx:
                return False, "handoff_chain roles out of order"
            last_idx = idx
        primary_present = {role for role in roles if role in _PRIMARY_HANDOFF_ORDER}
        for idx, role in enumerate(_PRIMARY_HANDOFF_ORDER):
            if role in primary_present:
                missing = [r for r in _PRIMARY_HANDOFF_ORDER[:idx] if r not in primary_present]
                if missing:
                    return False, f"handoff_chain missing required roles before {role}: {missing}"
        owner_role = _agent_role(contract.get("owner_agent", {}))
        assigned_role = _agent_role(contract.get("assigned_agent", {}))
        if owner_role and roles[0] != owner_role:
            return False, "handoff_chain must start with owner role"
        if assigned_role and roles[-1] != assigned_role:
            return False, "handoff_chain must end with assigned role"
    return True, ""


def _normalize_required_path(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        raw = list(_DEFAULT_LIFECYCLE_PATH)
    normalized = [str(item).strip().upper() for item in raw if str(item).strip()]
    normalized = [_LIFECYCLE_ROLE_ALIASES.get(role, role) for role in normalized]
    return normalized or list(_DEFAULT_LIFECYCLE_PATH)


def _step_roles(step_report: dict[str, Any]) -> list[str]:
    roles: list[str] = []
    owner = _agent_role(step_report.get("owner_agent", {}))
    assigned = _agent_role(step_report.get("assigned_agent", {}))
    if owner:
        roles.append(owner)
    if assigned and (not roles or assigned != roles[-1]):
        roles.append(assigned)
    return roles


def _load_report_payload(store: RunStore, run_id: str, report_name: str) -> dict[str, Any] | None:
    if not run_id:
        return None
    path = store._run_dir(run_id) / "reports" / report_name
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(payload, dict):
        return payload
    return None


def _load_task_result(store: RunStore, run_id: str) -> dict[str, Any] | None:
    if not run_id:
        return None
    run_dir = store._run_dir(run_id)
    agent_result_path = run_dir / "artifacts" / "agent_task_result.json"
    task_result_path = run_dir / "reports" / "task_result.json"
    target = agent_result_path if agent_result_path.exists() else task_result_path
    if not target.exists():
        return None
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _reviewer_verdict(store: RunStore, run_id: str) -> str:
    report = _load_report_payload(store, run_id, "review_report.json")
    if isinstance(report, dict):
        verdict = str(report.get("verdict", "")).strip().upper()
        if verdict in {"PASS", "FAIL", "BLOCKED"}:
            return verdict
    task_result = _load_task_result(store, run_id)
    if isinstance(task_result, dict):
        verdict = str(task_result.get("verdict", "")).strip().upper()
        if verdict in {"PASS", "FAIL", "BLOCKED"}:
            return verdict
        status = str(task_result.get("status", "")).strip().upper()
        if status in {"SUCCESS", "PASS"}:
            return "PASS"
        if status in {"FAILURE", "FAIL", "ERROR", "BLOCKED"}:
            return "FAIL"
    return "UNKNOWN"


def _test_stage_status(store: RunStore, run_id: str) -> str:
    report = _load_report_payload(store, run_id, "test_report.json")
    if isinstance(report, dict):
        status = str(report.get("status", "")).strip().upper()
        if status:
            return status
    task_result = _load_task_result(store, run_id)
    if isinstance(task_result, dict):
        status = str(task_result.get("status", "")).strip().upper()
        if status:
            return status
    return "UNKNOWN"


def _build_lifecycle_summary(
    store: RunStore,
    chain_owner_agent: dict[str, Any],
    step_reports: list[dict[str, Any]],
    strategy: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    lifecycle_cfg = strategy.get("lifecycle") if isinstance(strategy.get("lifecycle"), dict) else {}
    enforce = bool(lifecycle_cfg.get("enforce", False))
    required_path = _normalize_required_path(lifecycle_cfg.get("required_path"))
    min_workers = _as_int(lifecycle_cfg.get("min_workers"), 1)
    min_reviewers = _as_int(lifecycle_cfg.get("min_reviewers"), 1)
    reviewer_quorum = _as_int(lifecycle_cfg.get("reviewer_quorum"), min_reviewers)
    require_test_stage = bool(lifecycle_cfg.get("require_test_stage", True))
    require_return_to_pm = bool(lifecycle_cfg.get("require_return_to_pm", True))

    observed_path: list[str] = []
    chain_owner_role = _agent_role(chain_owner_agent)
    if chain_owner_role:
        observed_path.append(chain_owner_role)

    worker_steps = 0
    reviewer_steps = 0
    test_steps = 0
    test_pass_steps = 0
    reviewer_counts = {"PASS": 0, "FAIL": 0, "BLOCKED": 0, "UNKNOWN": 0}

    ordered_steps = sorted(step_reports, key=lambda item: int(item.get("index", 0)))
    for step in ordered_steps:
        if str(step.get("status", "")).strip().upper() != "SUCCESS":
            continue

        for role in _step_roles(step):
            role = _LIFECYCLE_ROLE_ALIASES.get(role, role)
            if not observed_path or observed_path[-1] != role:
                observed_path.append(role)

        assigned_role = _agent_role(step.get("assigned_agent", {}))
        run_id = str(step.get("run_id", "")).strip()

        if assigned_role in _WORKER_LIKE_ROLES:
            worker_steps += 1

        if assigned_role == "REVIEWER":
            reviewer_steps += 1
            verdict = _reviewer_verdict(store, run_id)
            reviewer_counts[verdict if verdict in reviewer_counts else "UNKNOWN"] += 1

        if assigned_role in _TEST_LIKE_ROLES:
            test_steps += 1
            test_status = _test_stage_status(store, run_id)
            if test_status in {"PASS", "SUCCESS"}:
                test_pass_steps += 1

    path_ok = _is_subsequence(required_path, observed_path)
    workers_ok = worker_steps >= min_workers
    reviewers_ok = reviewer_steps >= min_reviewers
    reviewer_quorum_ok = reviewer_counts["PASS"] >= reviewer_quorum
    test_ok = (test_pass_steps > 0) if require_test_stage else True
    return_to_pm_ok = True
    if require_return_to_pm and "PM" in required_path:
        return_to_pm_ok = bool(observed_path and observed_path[-1] == "PM")

    missing_required_roles: list[str] = []
    observed_set = set(observed_path)
    for role in required_path:
        if role not in observed_set and role not in missing_required_roles:
            missing_required_roles.append(role)

    violations: list[str] = []
    if not path_ok:
        violations.append("required lifecycle path not satisfied")
    if not workers_ok:
        violations.append(f"insufficient worker steps: {worker_steps} < {min_workers}")
    if not reviewers_ok:
        violations.append(f"insufficient reviewer steps: {reviewer_steps} < {min_reviewers}")
    if not reviewer_quorum_ok:
        violations.append(f"reviewer quorum not met: PASS {reviewer_counts['PASS']} < {reviewer_quorum}")
    if not test_ok:
        violations.append("test stage missing PASS result")
    if not return_to_pm_ok:
        violations.append("final lifecycle role is not PM")

    summary = {
        "enforce": enforce,
        "required_path": required_path,
        "observed_path": observed_path,
        "missing_required_roles": missing_required_roles,
        "is_complete": path_ok and workers_ok and reviewers_ok and reviewer_quorum_ok and test_ok and return_to_pm_ok,
        "workers": {"required": min_workers, "observed": worker_steps, "ok": workers_ok},
        "reviewers": {
            "required": min_reviewers,
            "observed": reviewer_steps,
            "quorum": reviewer_quorum,
            "pass": reviewer_counts["PASS"],
            "fail": reviewer_counts["FAIL"],
            "blocked": reviewer_counts["BLOCKED"],
            "unknown": reviewer_counts["UNKNOWN"],
            "quorum_met": reviewer_quorum_ok,
            "ok": reviewers_ok,
        },
        "tests": {
            "require_test_stage": require_test_stage,
            "observed": test_steps,
            "pass": test_pass_steps,
            "ok": test_ok,
        },
        "return_to_pm": {"required": require_return_to_pm, "ok": return_to_pm_ok},
    }
    return summary, violations
