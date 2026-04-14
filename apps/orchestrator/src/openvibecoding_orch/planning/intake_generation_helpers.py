from __future__ import annotations

import json
import uuid
from typing import Any, Callable

_DEFAULT_NONTRIVIAL_ACCEPTANCE_TEST = {
    "name": "repo_hygiene",
    "cmd": "bash scripts/check_repo_hygiene.sh",
    "must_pass": True,
}


def _coerce_acceptance_tests(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list) and raw:
        return raw
    return [dict(_DEFAULT_NONTRIVIAL_ACCEPTANCE_TEST)]


def build_plan_bundle_fallback(
    payload: dict[str, Any],
    answers: list[str],
    *,
    generate_plan: Callable[[dict[str, Any], list[str]], dict[str, Any]],
    clone_plan: Callable[[dict[str, Any], str], dict[str, Any]],
    plan_types: list[str],
    ensure_agent: Callable[[dict[str, Any] | None, dict[str, str]], dict[str, str]],
    default_tl: dict[str, str],
    normalize_bundle_plan: Callable[
        [dict[str, Any], dict[str, str], list[dict[str, Any]], str | None],
        dict[str, Any],
    ],
    extract_parallelism: Callable[[list[str] | None], int | None],
    normalize_constraints: Callable[[Any], list[str]],
    rebalance_bundle_paths: Callable[
        [list[dict[str, Any]], list[str], int | None],
        list[dict[str, Any]],
    ],
    now_ts: Callable[[], str],
    validator_factory: Callable[[], Any],
) -> dict[str, Any]:
    primary = generate_plan(payload, answers)
    owner_agent = ensure_agent(payload.get("owner_agent"), default_tl)
    raw_plans = [
        {
            **clone_plan(primary, plan_type),
            "owner_agent": owner_agent,
        }
        for plan_type in plan_types
    ]
    acceptance_tests = _coerce_acceptance_tests(payload.get("acceptance_tests"))

    plans = [
        normalize_bundle_plan(
            plan,
            owner_agent,
            acceptance_tests,
            str(plan.get("plan_type") or "").strip() or None,
        )
        for plan in raw_plans
    ]

    allowed_paths_raw = payload.get("allowed_paths")
    if not isinstance(allowed_paths_raw, list) or not any(str(item).strip() for item in allowed_paths_raw):
        allowed_paths_raw = primary.get("allowed_paths") if isinstance(primary, dict) else []
    allowed_paths = [str(item).strip() for item in allowed_paths_raw if str(item).strip()]

    desired_parallelism = extract_parallelism(normalize_constraints(payload.get("constraints")))
    if allowed_paths:
        plans = rebalance_bundle_paths(plans, allowed_paths, desired_parallelism)

    bundle = {
        "bundle_id": f"bundle-{uuid.uuid4().hex[:8]}",
        "created_at": now_ts(),
        "objective": str(payload.get("objective", "")).strip(),
        "owner_agent": owner_agent,
        "plans": plans,
    }
    validator = validator_factory()
    validator.validate_report(bundle, "plan_bundle.v1.json")
    return bundle


def generate_questions(
    payload: dict[str, Any],
    *,
    normalize_constraints: Callable[[Any], list[str]],
    default_questions: Callable[[str], list[str]],
    agents_available: Callable[[], bool],
    run_agent: Callable[[str, str], dict[str, Any]],
) -> list[str]:
    objective = str(payload.get("objective", "")).strip()
    constraints = normalize_constraints(payload.get("constraints"))
    if not agents_available():
        return default_questions(objective)

    instructions = (
        "You are a Tech Lead. Produce clarifying questions for the PM. "
        "Return JSON only with field: questions (array of strings)."
    )
    prompt = (
        f"Objective: {objective}\n"
        f"Constraints: {', '.join(constraints) if constraints else 'none'}\n"
    )
    try:
        result = run_agent(prompt, instructions)
        questions = result.get("questions")
        if isinstance(questions, list) and questions:
            return [str(item).strip() for item in questions if str(item).strip()]
    except Exception:
        return default_questions(objective)
    return default_questions(objective)


def generate_plan(
    payload: dict[str, Any],
    answers: list[str],
    *,
    ensure_agent: Callable[[dict[str, Any] | None, dict[str, str]], dict[str, str]],
    default_owner: dict[str, str],
    normalize_constraints: Callable[[Any], list[str]],
    build_plan_fallback: Callable[[dict[str, Any], list[str]], dict[str, Any]],
    agents_available: Callable[[], bool],
    run_agent: Callable[[str, str], dict[str, Any]],
    validator_factory: Callable[[], Any],
) -> dict[str, Any]:
    objective = str(payload.get("objective", "")).strip()
    allowed_paths = payload.get("allowed_paths", [])
    constraints = normalize_constraints(payload.get("constraints"))
    acceptance_tests = _coerce_acceptance_tests(payload.get("acceptance_tests"))
    owner_agent = ensure_agent(payload.get("owner_agent"), default_owner)
    if not agents_available():
        return build_plan_fallback(payload, answers)

    instructions = (
        "You are a Tech Lead. Produce a TaskPlan JSON. "
        "Must include: plan_id, task_id, owner_agent, assigned_agent, task_type, spec, "
        "allowed_paths, acceptance_tests, tool_permissions, mcp_tool_set, timeout_retry, rollback. "
        "Return JSON only, no extra text."
    )
    prompt = (
        f"Objective: {objective}\n"
        f"Allowed paths: {json.dumps(allowed_paths)}\n"
        f"Constraints: {json.dumps(constraints)}\n"
        f"Acceptance tests: {json.dumps(acceptance_tests)}\n"
        f"Answers: {json.dumps(answers)}\n"
        f"Owner agent: {json.dumps(owner_agent)}\n"
        f"Assigned agent: {json.dumps({'role': 'WORKER', 'agent_id': 'agent-1'})}"
    )
    try:
        plan = run_agent(prompt, instructions)
        # If intake explicitly provides acceptance tests, treat them as SSOT for deterministic execution.
        if acceptance_tests:
            plan["acceptance_tests"] = acceptance_tests
        elif not isinstance(plan.get("acceptance_tests"), list) or not plan.get("acceptance_tests"):
            plan["acceptance_tests"] = acceptance_tests
        if "plan_type" not in plan:
            plan["plan_type"] = payload.get("plan_type") or "BACKEND"
        validator = validator_factory()
        validator.validate_report(plan, "plan.schema.json")
        return plan
    except Exception:
        return build_plan_fallback(payload, answers)


def generate_plan_bundle(
    payload: dict[str, Any],
    answers: list[str],
    *,
    agents_available: Callable[[], bool],
    run_agent: Callable[[str, str], dict[str, Any]],
    build_plan_bundle_fallback: Callable[[dict[str, Any], list[str]], dict[str, Any]],
    normalize_constraints: Callable[[Any], list[str]],
    ensure_agent: Callable[[dict[str, Any] | None, dict[str, str]], dict[str, str]],
    default_tl: dict[str, str],
    plan_bundle_keys: set[str],
    now_ts: Callable[[], str],
    normalize_bundle_plan: Callable[
        [dict[str, Any], dict[str, str], list[dict[str, Any]], str | None],
        dict[str, Any],
    ],
    extract_parallelism: Callable[[list[str] | None], int | None],
    validate_plan_bundle_paths: Callable[[list[dict[str, Any]]], None],
    rebalance_bundle_paths: Callable[
        [list[dict[str, Any]], list[str], int | None],
        list[dict[str, Any]],
    ],
    validator_factory: Callable[[], Any],
) -> tuple[dict[str, Any], str]:
    if not agents_available():
        return build_plan_bundle_fallback(payload, answers), "plan_bundle_fallback: agents unavailable"

    objective = str(payload.get("objective", "")).strip()
    allowed_paths = payload.get("allowed_paths", [])
    constraints = normalize_constraints(payload.get("constraints"))
    acceptance_tests = _coerce_acceptance_tests(payload.get("acceptance_tests"))
    owner_agent = ensure_agent(payload.get("owner_agent"), default_tl)
    instructions = (
        "You are a Tech Lead. Produce a PlanBundle JSON that conforms to plan_bundle.v1.json. "
        "Return JSON only, no extra text. Each plan must include: plan_id, plan_type, spec, "
        "allowed_paths, acceptance_tests, tool_permissions, mcp_tool_set, owner_agent, assigned_agent, task_type. "
        "Rules: assigned_agent.role must be an explicit registered execution role; tool_permissions must be "
        '{"filesystem":"workspace-write","shell":"never","network":"deny","mcp_tools":["codex"]}. '
        "All allowed_paths across plans must be mutually exclusive. "
        "Split the objective into parallel worker plans."
    )
    prompt = (
        f"Objective: {objective}\n"
        f"Allowed paths: {json.dumps(allowed_paths)}\n"
        f"Constraints: {json.dumps(constraints)}\n"
        f"Acceptance tests: {json.dumps(acceptance_tests)}\n"
        f"Answers: {json.dumps(answers)}\n"
        f"Owner agent: {json.dumps(owner_agent)}\n"
    )
    try:
        bundle = run_agent(prompt, instructions)
        if not isinstance(bundle, dict):
            raise ValueError("plan bundle output not object")
        bundle = {key: bundle[key] for key in plan_bundle_keys if key in bundle}
        bundle.setdefault("bundle_id", f"bundle-{uuid.uuid4().hex[:8]}")
        bundle.setdefault("created_at", now_ts())
        bundle.setdefault("objective", objective)
        bundle["owner_agent"] = ensure_agent(bundle.get("owner_agent"), owner_agent)
        if isinstance(bundle.get("owner_agent"), dict):
            bundle["owner_agent"]["agent_id"] = "agent-1"
        plans = bundle.get("plans")
        if not isinstance(plans, list) or not plans:
            raise ValueError("plan bundle missing plans")
        normalized: list[dict[str, Any]] = []
        for plan in plans:
            if not isinstance(plan, dict):
                raise ValueError("plan bundle plan not object")
            normalized.append(
                normalize_bundle_plan(
                    plan,
                    bundle["owner_agent"],
                    acceptance_tests,
                    str(plan.get("plan_type") or "").strip() or None,
                )
            )
        desired_parallelism = extract_parallelism(constraints)
        if desired_parallelism and len(normalized) > desired_parallelism:
            normalized = normalized[:desired_parallelism]
        try:
            validate_plan_bundle_paths(normalized)
        except Exception:
            normalized = rebalance_bundle_paths(normalized, allowed_paths, desired_parallelism)
            validate_plan_bundle_paths(normalized)
        bundle["plans"] = normalized
        validator = validator_factory()
        validator.validate_report(bundle, "plan_bundle.v1.json")
        return bundle, ""
    except Exception as exc:  # noqa: BLE001
        return build_plan_bundle_fallback(payload, answers), f"plan_bundle_fallback: {exc}"


def build_task_chain_from_bundle(
    plan_bundle: dict[str, Any],
    owner_agent: dict[str, str],
    *,
    ensure_agent: Callable[[dict[str, Any] | None, dict[str, str]], dict[str, str]],
    default_tl: dict[str, str],
    fanin_allowed_paths: list[str],
) -> dict[str, Any]:
    bundle_id = str(plan_bundle.get("bundle_id", "")).strip() or f"bundle-{uuid.uuid4().hex[:8]}"
    plans = plan_bundle.get("plans")
    if not isinstance(plans, list) or not plans:
        raise ValueError("plan bundle missing plans")
    steps: list[dict[str, Any]] = []
    worker_step_names: list[str] = []
    for idx, plan in enumerate(plans):
        if not isinstance(plan, dict):
            raise ValueError("plan bundle plan invalid")
        plan_id = str(plan.get("plan_id") or f"plan_{idx}")
        step_name = f"worker_{idx}_{plan_id}"
        worker_step_names.append(step_name)
        steps.append(
            {
                "name": step_name,
                "kind": "plan",
                "payload": plan,
                "labels": ["worker", "parallel"],
                "parallel_group": "audit",
                "exclusive_paths": plan.get("allowed_paths") or [],
            }
        )
    fanin_plan = {
        "plan_id": f"fanin-{bundle_id[:8]}",
        "plan_type": "AI",
        "task_type": "PLAN",
        "owner_agent": ensure_agent(plan_bundle.get("owner_agent"), owner_agent),
        "assigned_agent": ensure_agent(default_tl, default_tl),
        "spec": (
            "Aggregate dependency task_result artifacts, de-duplicate inconsistencies, "
            "and output agent_task_result.v1.json. "
            "The summary field MUST be a JSON string with keys: "
            "format, inconsistencies, duplicates, stats, dependency_run_ids, notes. "
            "Each inconsistency must include: id, title, docs_refs, repo_refs, severity."
        ),
        "artifacts": [],
        "required_outputs": [
            {
                "name": "task_result.json",
                "type": "report",
                "acceptance": "deduplicated inconsistency list",
            }
        ],
        "allowed_paths": fanin_allowed_paths,
        "acceptance_tests": [dict(_DEFAULT_NONTRIVIAL_ACCEPTANCE_TEST)],
        "tool_permissions": {
            "filesystem": "read-only",
            "shell": "never",
            "network": "deny",
            "mcp_tools": ["codex"],
        },
    }
    steps.append(
        {
            "name": "fan_in",
            "kind": "plan",
            "payload": fanin_plan,
            "labels": ["fan_in", "tl", "aggregate"],
            "depends_on": worker_step_names,
            "exclusive_paths": fanin_allowed_paths,
        }
    )
    return {
        "chain_id": f"chain-{bundle_id[:8]}",
        "owner_agent": owner_agent,
        "strategy": {"continue_on_fail": False},
        "steps": steps,
    }
