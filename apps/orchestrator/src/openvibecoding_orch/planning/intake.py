from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import os
import re
from functools import lru_cache
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openvibecoding_orch.contract.compiler import compile_plan, sync_role_contract
from openvibecoding_orch.contract.role_config_registry import build_runtime_capability_summary
from openvibecoding_orch.contract.validator import ContractValidator
from openvibecoding_orch.config import get_runner_config
from openvibecoding_orch.scheduler import approval_flow
from openvibecoding_orch.runners.provider_resolution import (
    build_llm_compat_client,
    merge_provider_credentials,
    ProviderResolutionError,
    resolve_compat_api_mode,
    ProviderCredentials,
    resolve_preferred_api_key,
    resolve_provider_credentials,
    resolve_runtime_provider_from_env,
)
from openvibecoding_orch.store.intake_store import IntakeStore

from . import intake_generation_helpers as _generation_helpers
from . import intake_plan_bundle_helpers as _bundle_helpers
from . import intake_policy_helpers as _policy_helpers
from tooling.page_brief_pipeline import DEFAULT_PAGE_BRIEF_FOCUS, PAGE_BRIEF_BROWSER_SCRIPT


# -------------------------------------------------------------------
# Defaults
# -------------------------------------------------------------------

_DEFAULT_OWNER = _bundle_helpers._DEFAULT_OWNER
_DEFAULT_TL = {"role": "TECH_LEAD", "agent_id": "agent-1"}
_PLAN_TYPES = _bundle_helpers._PLAN_TYPES
_FANIN_ALLOWED_PATHS = ["__fan_in__/"]
_PLAN_BUNDLE_KEYS = {"bundle_id", "created_at", "objective", "owner_agent", "plans"}


# -------------------------------------------------------------------
# Helper aliases
# -------------------------------------------------------------------

_ensure_agent = _policy_helpers._ensure_agent
_normalize_answers = _policy_helpers._normalize_answers
_normalize_constraints = _policy_helpers._normalize_constraints
_normalize_browser_policy = _policy_helpers._normalize_browser_policy
_compact_browser_policy = _policy_helpers._compact_browser_policy
_resolve_intake_browser_policy = _policy_helpers._resolve_intake_browser_policy
_default_questions = _policy_helpers._default_questions

_clone_plan = _bundle_helpers._clone_plan
_paths_overlap = _bundle_helpers._paths_overlap
_normalize_bundle_plan = _bundle_helpers._normalize_bundle_plan
_extract_parallelism = _bundle_helpers._extract_parallelism
_rebalance_bundle_paths = _bundle_helpers._rebalance_bundle_paths
_validate_plan_bundle_paths = _bundle_helpers._validate_plan_bundle_paths
_build_plan_fallback = _bundle_helpers._build_plan_fallback


# -------------------------------------------------------------------
# Fallbacks
# -------------------------------------------------------------------


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


_SENSITIVE_ANSWER_RE = re.compile(
    r"(?i)\b(password|token|secret|key|credential|auth|cert|private)\b\s*[:=]\s*([^\s,;]+)"
)
_PROVIDER_API_KEY_ENV_HINTS = {
    "gemini": "GEMINI_API_KEY",
    "google": "GEMINI_API_KEY",
    "google-genai": "GEMINI_API_KEY",
    "google_genai": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
    "anthropic-claude": "ANTHROPIC_API_KEY",
    "anthropic_claude": "ANTHROPIC_API_KEY",
    "equilibrium": "OPENVIBECODING_EQUILIBRIUM_API_KEY",
    "codex_equilibrium": "OPENVIBECODING_EQUILIBRIUM_API_KEY",
}
_NEWS_DIGEST_TEMPLATE = "news_digest"
_TOPIC_BRIEF_TEMPLATE = "topic_brief"
_PAGE_BRIEF_TEMPLATE = "page_brief"
_NEWS_DIGEST_TIME_RANGES = {"24h", "7d", "30d"}
_PACKS_ROOT = Path(__file__).resolve().parents[5] / "contracts" / "packs"
_CONTROL_PLANE_POLICY_REF = "policies/control_plane_runtime_policy.json"
_WAVE_PLAN_POLICY_REF = f"{_CONTROL_PLANE_POLICY_REF}#/wave_completion_policy"
_WAKE_POLICY_REF = f"{_CONTROL_PLANE_POLICY_REF}#/wake_policy"


def _missing_llm_api_key_message(provider: str) -> str:
    env_key = _PROVIDER_API_KEY_ENV_HINTS.get(provider, "GEMINI_API_KEY")
    return f"missing LLM API key ({env_key})"


def _resolve_preferred_api_key_for_provider(
    credentials: ProviderCredentials,
    provider: str,
    *,
    base_url: str = "",
) -> str:
    provider_name = str(provider or "").strip()
    normalized = provider_name.lower().replace("-", "_")
    if normalized == "google_genai":
        normalized = "gemini"
    if normalized == "codex_equilibrium":
        normalized = "equilibrium"
    provider_attr = {
        "gemini": "gemini_api_key",
        "openai": "openai_api_key",
        "anthropic": "anthropic_api_key",
        "equilibrium": "gemini_api_key",
    }
    attr = provider_attr.get(normalized)
    if attr:
        value = str(getattr(credentials, attr, "") or "").strip()
        if value:
            return value
        if normalized == "equilibrium":
            equilibrium_key = str(getattr(credentials, "equilibrium_api_key", "") or "").strip()
            if equilibrium_key:
                return equilibrium_key
        if normalized == "gemini" and _is_local_base_url(base_url):
            equilibrium_key = str(getattr(credentials, "equilibrium_api_key", "") or "").strip()
            if equilibrium_key:
                return equilibrium_key

    try:
        candidate = resolve_preferred_api_key(credentials, provider_name)  # type: ignore[call-arg]
    except ProviderResolutionError:
        candidate = ""
    except (TypeError, AttributeError):
        candidate = resolve_preferred_api_key(credentials)
    except Exception:
        candidate = ""
    resolved = str(candidate or "").strip()
    if resolved:
        return resolved
    for fallback_attr in (
        "openai_api_key",
        "gemini_api_key",
        "anthropic_api_key",
        "equilibrium_api_key",
    ):
        value = str(getattr(credentials, fallback_attr, "") or "").strip()
        if value:
            return value
    if resolve_compat_api_mode("responses", base_url=base_url) == "chat_completions":
        return "switchyard-local"
    return ""


def _redact_answer(value: str) -> str:
    return _SENSITIVE_ANSWER_RE.sub(r"\1=[REDACTED]", value)


def _normalize_news_digest_payload(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("news_digest template_payload must be an object")
    topic = str(raw.get("topic") or "").strip()
    if not topic:
        raise ValueError("news_digest topic is required")
    raw_sources = raw.get("sources")
    if not isinstance(raw_sources, list):
        raise ValueError("news_digest sources must be a non-empty array")
    sources = [str(item).strip() for item in raw_sources if str(item).strip()]
    if not sources:
        raise ValueError("news_digest sources must be a non-empty array")
    time_range = str(raw.get("time_range") or "24h").strip().lower() or "24h"
    if time_range not in _NEWS_DIGEST_TIME_RANGES:
        raise ValueError("news_digest time_range must be one of 24h/7d/30d")
    try:
        max_results = int(raw.get("max_results", 5))
    except (TypeError, ValueError) as exc:
        raise ValueError("news_digest max_results must be an integer") from exc
    max_results = max(1, min(max_results, 10))
    return {
        "topic": topic,
        "sources": sources,
        "time_range": time_range,
        "max_results": max_results,
    }


def _build_news_digest_objective(payload: dict[str, Any]) -> str:
    topic = str(payload.get("topic") or "").strip()
    sources = [str(item).strip() for item in payload.get("sources", []) if str(item).strip()]
    time_range = str(payload.get("time_range") or "24h").strip().lower() or "24h"
    source_text = ", ".join(sources) if sources else "public web sources"
    return (
        f"Build a public-read-only news digest about '{topic}' using {source_text} "
        f"for the last {time_range}. Return a concise summary, source list, and auditable evidence."
    )


def _build_news_digest_queries(payload: dict[str, Any]) -> list[str]:
    topic = str(payload.get("topic") or "").strip()
    sources = [str(item).strip() for item in payload.get("sources", []) if str(item).strip()]
    queries: list[str] = []
    for source in sources:
        if "." in source:
            queries.append(f"{topic} site:{source}")
        else:
            queries.append(f"{topic} {source}")
    return queries or [topic]


def _normalize_topic_brief_payload(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("topic_brief template_payload must be an object")
    topic = str(raw.get("topic") or "").strip()
    if not topic:
        raise ValueError("topic_brief topic is required")
    time_range = str(raw.get("time_range") or "24h").strip().lower() or "24h"
    if time_range not in _NEWS_DIGEST_TIME_RANGES:
        raise ValueError("topic_brief time_range must be one of 24h/7d/30d")
    try:
        max_results = int(raw.get("max_results", 5))
    except (TypeError, ValueError) as exc:
        raise ValueError("topic_brief max_results must be an integer") from exc
    max_results = max(1, min(max_results, 10))
    return {
        "topic": topic,
        "time_range": time_range,
        "max_results": max_results,
    }


def _is_public_http_url(value: str) -> bool:
    try:
        from urllib.parse import urlparse

        parsed = urlparse(value)
    except Exception:  # noqa: BLE001
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").strip().lower()
    if not host or host == "localhost":
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True
    return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved)


def _normalize_page_brief_payload(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("page_brief template_payload must be an object")
    url = str(raw.get("url") or "").strip()
    if not url:
        raise ValueError("page_brief url is required")
    if not _is_public_http_url(url):
        raise ValueError("page_brief url must be a public http/https webpage")
    focus = str(raw.get("focus") or DEFAULT_PAGE_BRIEF_FOCUS).strip() or DEFAULT_PAGE_BRIEF_FOCUS
    return {
        "url": url,
        "focus": focus,
    }


@lru_cache(maxsize=1)
def _task_pack_registry() -> dict[str, dict[str, Any]]:
    manifests: dict[str, dict[str, Any]] = {}
    if not _PACKS_ROOT.exists():
        return manifests
    for manifest_path in sorted(_PACKS_ROOT.glob("*/manifest.json")):
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        ContractValidator().validate_report(payload, "task_pack_manifest.v1.json")
        task_template = str(payload.get("task_template") or "").strip().lower()
        if not task_template:
            continue
        manifests[task_template] = payload
    return manifests


def _supported_task_templates() -> set[str]:
    registry = _task_pack_registry()
    if registry:
        return set(registry.keys())
    return {_NEWS_DIGEST_TEMPLATE, _TOPIC_BRIEF_TEMPLATE, _PAGE_BRIEF_TEMPLATE}


def list_task_packs() -> list[dict[str, Any]]:
    registry = _task_pack_registry()
    manifests = [dict(payload) for payload in registry.values()]
    manifests.sort(key=lambda payload: (str(payload.get("title") or payload.get("task_template") or "").lower(), str(payload.get("task_template") or "").lower()))
    return manifests


def _build_page_brief_objective(payload: dict[str, Any]) -> str:
    url = str(payload.get("url") or "").strip()
    focus = str(payload.get("focus") or DEFAULT_PAGE_BRIEF_FOCUS).strip() or DEFAULT_PAGE_BRIEF_FOCUS
    return (
        f"Build a public-read-only page brief for '{url}'. "
        f"Focus: {focus} Return a concise summary, key points, screenshot, and auditable evidence."
    )


def _build_topic_brief_objective(payload: dict[str, Any]) -> str:
    topic = str(payload.get("topic") or "").strip()
    time_range = str(payload.get("time_range") or "24h").strip().lower() or "24h"
    return (
        f"Build a public-read-only topic brief about '{topic}' "
        f"for the last {time_range}. Return a concise summary, source list, and auditable evidence."
    )


def _build_topic_brief_queries(payload: dict[str, Any]) -> list[str]:
    topic = str(payload.get("topic") or "").strip()
    return [topic] if topic else []


def _task_pack_handler(task_template: str) -> dict[str, Any]:
    handlers: dict[str, dict[str, Any]] = {
        _NEWS_DIGEST_TEMPLATE: {
            "normalize_payload": _normalize_news_digest_payload,
            "build_objective": _build_news_digest_objective,
            "build_search_queries": _build_news_digest_queries,
        },
        _TOPIC_BRIEF_TEMPLATE: {
            "normalize_payload": _normalize_topic_brief_payload,
            "build_objective": _build_topic_brief_objective,
            "build_search_queries": _build_topic_brief_queries,
        },
        _PAGE_BRIEF_TEMPLATE: {
            "normalize_payload": _normalize_page_brief_payload,
            "build_objective": _build_page_brief_objective,
            "build_search_queries": lambda _payload: [],
        },
    }
    handler = handlers.get(task_template)
    if handler is None:
        raise ValueError(f"unsupported task_template: {task_template}")
    return handler


def _predicted_reports_for_task_template(task_template: str) -> list[str]:
    reports = [
        "task_result.json",
        "review_report.json",
        "test_report.json",
        "evidence_bundle.json",
        "evidence_report.json",
    ]
    normalized = task_template.strip().lower()
    primary_report = (
        _task_pack_registry()
        .get(normalized, {})
        .get("evidence_contract", {})
        .get("primary_report")
    )
    if isinstance(primary_report, str) and primary_report.strip() and primary_report not in reports:
        reports.append(primary_report.strip())
    return reports


def _predicted_artifacts_for_payload(payload: dict[str, Any]) -> list[str]:
    predicted = ["contract.json", "manifest.json", "events.jsonl", "patch.diff", "diff_name_only.txt"]
    task_template = str(payload.get("task_template") or "").strip().lower()
    search_queries = payload.get("search_queries")
    evidence_contract = _task_pack_registry().get(task_template, {}).get("evidence_contract", {})
    requires_browser_requests = bool(evidence_contract.get("requires_browser_requests"))
    requires_search_requests = bool(evidence_contract.get("requires_search_requests"))
    if requires_browser_requests and "browser_requests.json" not in predicted:
        predicted.append("browser_requests.json")
    if requires_search_requests and "search_requests.json" not in predicted:
        predicted.append("search_requests.json")
    elif isinstance(search_queries, list) and any(str(item).strip() for item in search_queries):
        predicted.append("search_requests.json")
    return predicted


def _build_execution_plan_summary(
    *,
    task_template: str,
    objective: str,
    assigned_role: str,
    requires_human_approval: bool,
    predicted_reports: list[str],
) -> str:
    normalized_template = task_template.strip().lower() or "general"
    approval_text = "manual approval likely" if requires_human_approval else "no manual approval expected"
    return (
        f"{normalized_template} will compile into a {assigned_role.lower()}-owned execution contract for "
        f"'{objective}'. {approval_text}. Expected report surface: {len(predicted_reports)} item(s)."
    )


def _normalize_prompt_reading_list(plan: dict[str, Any], payload: dict[str, Any]) -> dict[str, list[str]]:
    artifacts = plan.get("artifacts") if isinstance(plan.get("artifacts"), list) else []
    required: list[str] = []
    for item in artifacts:
        if not isinstance(item, dict):
            continue
        label = str(item.get("uri") or item.get("name") or "").strip()
        if label and label not in required:
            required.append(label)
    if not required:
        required = [
            "contract_preview",
            "role_contract_summary",
            "allowed_paths",
            "acceptance_tests",
        ]
    optional: list[str] = []
    for raw in payload.get("search_queries", []) if isinstance(payload.get("search_queries"), list) else []:
        label = str(raw or "").strip()
        if label and label not in optional:
            optional.append(label)
    return {"required": required, "optional": optional}


def _summarize_acceptance_tests(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    checks: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            label = str(item.get("name") or item.get("cmd") or "").strip()
        else:
            label = str(item or "").strip()
        if label:
            checks.append(label)
    return checks


def _summarize_allowed_actions(plan: dict[str, Any]) -> list[str]:
    tool_permissions = plan.get("tool_permissions") if isinstance(plan.get("tool_permissions"), dict) else {}
    actions: list[str] = []
    filesystem = str(tool_permissions.get("filesystem") or "").strip()
    shell = str(tool_permissions.get("shell") or "").strip()
    network = str(tool_permissions.get("network") or "").strip()
    if filesystem:
        actions.append(f"filesystem:{filesystem}")
    if shell:
        actions.append(f"shell:{shell}")
    if network:
        actions.append(f"network:{network}")
    for raw in plan.get("mcp_tool_set", []) if isinstance(plan.get("mcp_tool_set"), list) else []:
        tool = str(raw or "").strip()
        if tool:
            actions.append(f"mcp:{tool}")
    return actions


def _build_wave_plan(plan_bundle: dict[str, Any]) -> dict[str, Any]:
    plans = plan_bundle.get("plans") if isinstance(plan_bundle.get("plans"), list) else []
    worker_plans: list[dict[str, Any]] = []
    for index, plan in enumerate(plans):
        if not isinstance(plan, dict):
            continue
        prompt_contract_id = str(plan.get("plan_id") or f"worker-{index + 1}").strip() or f"worker-{index + 1}"
        assigned_agent = plan.get("assigned_agent") if isinstance(plan.get("assigned_agent"), dict) else {}
        worker_plans.append(
            {
                "prompt_contract_id": prompt_contract_id,
                "assigned_role": str(assigned_agent.get("role") or "WORKER").strip() or "WORKER",
                "spec": str(plan.get("spec") or "").strip() or "No scope summary provided.",
                "allowed_paths": [
                    str(item).strip()
                    for item in plan.get("allowed_paths", [])
                    if str(item).strip()
                ],
                "acceptance_checks": _summarize_acceptance_tests(plan.get("acceptance_tests")),
                "mcp_tools": [
                    str(item).strip()
                    for item in plan.get("mcp_tool_set", [])
                    if str(item).strip()
                ],
            }
        )
    owner_agent = plan_bundle.get("owner_agent") if isinstance(plan_bundle.get("owner_agent"), dict) else {}
    return {
        "version": "v1",
        "wave_id": str(plan_bundle.get("bundle_id") or "wave-preview").strip() or "wave-preview",
        "objective": str(plan_bundle.get("objective") or "").strip() or "No objective provided.",
        "owner_agent": {
            "role": str(owner_agent.get("role") or "PM").strip() or "PM",
            "agent_id": str(owner_agent.get("agent_id") or "agent-1").strip() or "agent-1",
        },
        "execution_mode": "long_running",
        "wake_policy_ref": _WAKE_POLICY_REF,
        "completion_policy_ref": _WAVE_PLAN_POLICY_REF,
        "worker_count": max(len(worker_plans), 1),
        "worker_plans": worker_plans or [
            {
                "prompt_contract_id": "worker-preview-1",
                "assigned_role": "WORKER",
                "spec": "No worker plan generated.",
                "allowed_paths": ["."],
                "acceptance_checks": [],
                "mcp_tools": [],
            }
        ],
    }


def _build_worker_prompt_contracts(plan_bundle: dict[str, Any], payload: dict[str, Any]) -> list[dict[str, Any]]:
    plans = plan_bundle.get("plans") if isinstance(plan_bundle.get("plans"), list) else []
    objective = str(plan_bundle.get("objective") or payload.get("objective") or "").strip() or "No objective provided."
    contracts: list[dict[str, Any]] = []
    for index, plan in enumerate(plans):
        if not isinstance(plan, dict):
            continue
        assigned_agent = plan.get("assigned_agent") if isinstance(plan.get("assigned_agent"), dict) else {}
        acceptance_checks = _summarize_acceptance_tests(plan.get("acceptance_tests"))
        required_outputs = plan.get("required_outputs") if isinstance(plan.get("required_outputs"), list) else []
        deliverables = []
        for item in required_outputs:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            deliverable_type = str(item.get("type") or "").strip()
            if name and deliverable_type:
                deliverables.append({"name": name, "type": deliverable_type})
        contract_id = str(plan.get("plan_id") or f"worker-{index + 1}").strip() or f"worker-{index + 1}"
        contracts.append(
            {
                "version": "v1",
                "prompt_contract_id": contract_id,
                "objective": objective,
                "scope": str(plan.get("spec") or "").strip() or "No scope summary provided.",
                "assigned_agent": {
                    "role": str(assigned_agent.get("role") or "WORKER").strip() or "WORKER",
                    "agent_id": str(assigned_agent.get("agent_id") or "agent-1").strip() or "agent-1",
                },
                "reading_list": _normalize_prompt_reading_list(plan, payload),
                "done_definition": {
                    "summary": "Complete the scoped worker assignment, satisfy acceptance checks, and do not stop at a half-done status update.",
                    "acceptance_checks": acceptance_checks or ["repo_hygiene"],
                },
                "constraints": [
                    str(item).strip()
                    for item in payload.get("constraints", [])
                    if str(item).strip()
                ],
                "allowed_actions": _summarize_allowed_actions(plan),
                "blocked_when": [
                    "scope evidence is insufficient",
                    "required reads are missing",
                    "reply auditor marks the work incomplete",
                    "an external blocker requires an L0-managed unblock task"
                ],
                "deliverables": deliverables or [{"name": "task_result.json", "type": "report"}],
                "escalation_policy": {
                    "owner": "L0",
                    "trigger": "scope blocker or authority mismatch"
                },
                "continuation_policy": {
                    "on_incomplete": "reply_auditor_reprompt_and_continue_same_session",
                    "on_blocked": "spawn_independent_temporary_unblock_task"
                },
                "verification_requirements": acceptance_checks or ["repo_hygiene"],
                "forbidden_actions": [
                    str(item).strip()
                    for item in plan.get("forbidden_actions", [])
                    if str(item).strip()
                ],
            }
        )
    return contracts


def _build_unblock_tasks_from_worker_contracts(worker_contracts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for contract in worker_contracts:
        if not isinstance(contract, dict):
            continue
        continuation_policy = contract.get("continuation_policy") if isinstance(contract.get("continuation_policy"), dict) else {}
        on_blocked = str(continuation_policy.get("on_blocked") or "").strip()
        if on_blocked != "spawn_independent_temporary_unblock_task":
            continue
        assigned_agent = contract.get("assigned_agent") if isinstance(contract.get("assigned_agent"), dict) else {}
        blocked_when = contract.get("blocked_when") if isinstance(contract.get("blocked_when"), list) else []
        reason = next(
            (
                str(item).strip()
                for item in blocked_when
                if str(item).strip() and (
                    "external blocker" in str(item).lower()
                    or "unblock task" in str(item).lower()
                )
            ),
            "an external blocker requires an L0-managed unblock task",
        )
        prompt_contract_id = str(contract.get("prompt_contract_id") or "").strip() or "worker-preview-1"
        tasks.append(
            {
                "version": "v1",
                "unblock_task_id": f"unblock-{prompt_contract_id}",
                "source_prompt_contract_id": prompt_contract_id,
                "objective": f"Unblock the scoped worker assignment for {contract.get('objective') or 'the current wave'}",
                "scope_hint": str(contract.get("scope") or "").strip() or "No scope summary provided.",
                "assigned_agent": {
                    "role": str(assigned_agent.get("role") or "WORKER").strip() or "WORKER",
                    "agent_id": str(assigned_agent.get("agent_id") or "agent-1").strip() or "agent-1",
                },
                "owner": "L0",
                "mode": "independent_temporary_task",
                "status": "proposed",
                "trigger": on_blocked,
                "reason": reason,
                "verification_requirements": [
                    str(item).strip()
                    for item in contract.get("verification_requirements", [])
                    if str(item).strip()
                ]
                or ["repo_hygiene"],
            }
        )
    return tasks


def _apply_intake_contract_overrides(
    contract: dict[str, Any],
    intake_payload: dict[str, Any],
    *,
    intake_dir: Path | None = None,
) -> dict[str, Any]:
    owner_role = (
        str(contract.get("owner_agent", {}).get("role", "")).strip().upper()
        if isinstance(contract.get("owner_agent"), dict)
        else ""
    )
    if owner_role == "PM":
        contract["handoff_chain"] = {"enabled": True, "roles": ["PM", "TECH_LEAD", "WORKER"]}
    task_template = intake_payload.get("task_template")
    template_payload = intake_payload.get("template_payload")
    if isinstance(task_template, str) and task_template.strip():
        contract["task_template"] = task_template.strip()
    if isinstance(template_payload, dict) and template_payload:
        contract["template_payload"] = template_payload
    browser_policy = intake_payload.get("browser_policy")
    if isinstance(browser_policy, dict):
        contract["browser_policy"] = _compact_browser_policy(browser_policy)
    search_queries = intake_payload.get("search_queries")
    if isinstance(task_template, str) and task_template.strip().lower() == _PAGE_BRIEF_TEMPLATE and intake_dir is not None:
        browser_path = intake_dir / "browser_requests.json"
        browser_payload: dict[str, Any] = {
            "headless": True,
            "task_template": _PAGE_BRIEF_TEMPLATE,
            "template_payload": template_payload if isinstance(template_payload, dict) else {},
            "tasks": [
                {
                    "url": str((template_payload or {}).get("url") or "").strip(),
                    "script": PAGE_BRIEF_BROWSER_SCRIPT,
                }
            ],
        }
        browser_text = json.dumps(browser_payload, ensure_ascii=False, indent=2)
        browser_path.write_text(browser_text, encoding="utf-8")
        sha = _sha256_text(browser_text)
        contract.setdefault("inputs", {})
        artifacts = contract["inputs"].get("artifacts") if isinstance(contract["inputs"], dict) else []
        if not isinstance(artifacts, list):
            artifacts = []
        contract["inputs"]["artifacts"] = artifacts
        contract["inputs"]["artifacts"].append(
            {
                "name": "browser_requests.json",
                "uri": str(browser_path),
                "sha256": sha,
            }
        )
        return sync_role_contract(contract)
    if isinstance(search_queries, list) and search_queries:
        if intake_dir is not None:
            search_path = intake_dir / "search_requests.json"
            payload: dict[str, Any] = {"queries": search_queries}
            if isinstance(task_template, str) and task_template.strip():
                payload["task_template"] = task_template.strip()
            if isinstance(template_payload, dict) and template_payload:
                payload["template_payload"] = template_payload
            search_text = json.dumps(payload, ensure_ascii=False, indent=2)
            search_path.write_text(search_text, encoding="utf-8")
            sha = _sha256_text(search_text)
            contract.setdefault("inputs", {})
            artifacts = contract["inputs"].get("artifacts") if isinstance(contract["inputs"], dict) else []
            if not isinstance(artifacts, list):
                artifacts = []
            contract["inputs"]["artifacts"] = artifacts
            contract["inputs"]["artifacts"].append(
                {
                    "name": "search_requests.json",
                    "uri": str(search_path),
                    "sha256": sha,
                }
            )
        assigned_agent = contract.get("assigned_agent") if isinstance(contract.get("assigned_agent"), dict) else {}
        search_agent_id = str(assigned_agent.get("agent_id") or "agent-1").strip() or "agent-1"
        owner_agent = contract.get("owner_agent") if isinstance(contract.get("owner_agent"), dict) else {}
        if str(owner_agent.get("role") or "").strip().upper() == "PM":
            contract["owner_agent"] = {
                **owner_agent,
                "role": "TECH_LEAD",
                "agent_id": search_agent_id,
            }
        contract["assigned_agent"] = {
            **assigned_agent,
            "role": "SEARCHER",
            "agent_id": search_agent_id,
        }
        tool_permissions = (
            contract.get("tool_permissions") if isinstance(contract.get("tool_permissions"), dict) else {}
        )
        allowed_mcp_tools = tool_permissions.get("mcp_tools") if isinstance(tool_permissions.get("mcp_tools"), list) else []
        normalized_mcp_tools = [str(item).strip() for item in allowed_mcp_tools if str(item).strip()]
        if "codex" not in normalized_mcp_tools:
            normalized_mcp_tools.append("codex")
        if "search" not in normalized_mcp_tools:
            normalized_mcp_tools.append("search")
        contract["tool_permissions"] = {
            **tool_permissions,
            "network": "allow",
            "mcp_tools": normalized_mcp_tools,
        }
        contract_mcp_tools = contract.get("mcp_tool_set") if isinstance(contract.get("mcp_tool_set"), list) else []
        normalized_contract_mcp_tools = [str(item).strip() for item in contract_mcp_tools if str(item).strip()]
        if "search" not in normalized_contract_mcp_tools:
            normalized_contract_mcp_tools.append("search")
        contract["mcp_tool_set"] = normalized_contract_mcp_tools
        contract.pop("handoff_chain", None)
    return sync_role_contract(contract)


def _apply_task_template_defaults(payload: dict[str, Any]) -> dict[str, Any]:
    task_template = str(payload.get("task_template") or "").strip().lower()
    if not task_template:
        return payload
    if task_template not in _supported_task_templates():
        raise ValueError(f"unsupported task_template: {task_template}")
    handler = _task_pack_handler(task_template)
    template_payload = handler["normalize_payload"](payload.get("template_payload"))
    payload["task_template"] = task_template
    payload["template_payload"] = template_payload

    objective = str(payload.get("objective") or "").strip()
    if not objective:
        payload["objective"] = handler["build_objective"](template_payload)

    search_queries = payload.get("search_queries")
    if not isinstance(search_queries, list) or not any(str(item).strip() for item in search_queries):
        payload["search_queries"] = handler["build_search_queries"](template_payload)

    raw_constraints = payload.get("constraints")
    constraints = [str(item).strip() for item in raw_constraints if str(item).strip()] if isinstance(raw_constraints, list) else []
    for entry in (
        f"task_template={task_template}",
        "public-read-only-sources",
        "no-login-required",
        "no-shopping-or-transactions",
    ):
        if entry not in constraints:
            constraints.append(entry)
    payload["constraints"] = constraints
    return payload


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _execute_chain(chain_path: Path, mock_mode: bool) -> dict[str, Any]:
    from openvibecoding_orch.scheduler.scheduler import Orchestrator

    orch = Orchestrator(_repo_root())
    return orch.execute_chain(chain_path, mock_mode=mock_mode)


def _build_plan_bundle_fallback(payload: dict[str, Any], answers: list[str]) -> dict[str, Any]:
    return _generation_helpers.build_plan_bundle_fallback(
        payload,
        answers,
        generate_plan=generate_plan,
        clone_plan=_clone_plan,
        plan_types=_PLAN_TYPES,
        ensure_agent=_ensure_agent,
        default_tl=_DEFAULT_TL,
        normalize_bundle_plan=_normalize_bundle_plan,
        extract_parallelism=_extract_parallelism,
        normalize_constraints=_normalize_constraints,
        rebalance_bundle_paths=_rebalance_bundle_paths,
        now_ts=_now_ts,
        validator_factory=ContractValidator,
    )


# -------------------------------------------------------------------
# Agents SDK helpers
# -------------------------------------------------------------------


def _agents_available() -> bool:
    smoke_flags = (
        os.getenv("OPENVIBECODING_ORCHESTRATION_SMOKE_MODE", "").strip().lower(),
        os.getenv("OPENVIBECODING_E2E_ORCHESTRATION_SMOKE_MODE", "").strip().lower(),
    )
    if any(flag in {"1", "true", "yes", "y", "on"} for flag in smoke_flags):
        return False
    try:
        import agents  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def _resolve_agents_store() -> bool:
    raw = os.getenv("OPENVIBECODING_AGENTS_STORE", "").strip().lower()
    if raw in {"1", "true", "yes"}:
        return True
    if raw in {"0", "false", "no"}:
        return False
    return False


def _strip_model_input_ids(payload: Any) -> Any:
    try:
        from agents.run import ModelInputData
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"ModelInputData missing: {exc}") from exc

    model_data = getattr(payload, "model_data", None)
    if model_data is None:
        return ModelInputData(input=[], instructions=None)
    sanitized: list[Any] = []
    for item in list(getattr(model_data, "input", []) or []):
        if isinstance(item, dict):
            cleaned = dict(item)
            cleaned.pop("id", None)
            cleaned.pop("response_id", None)
            sanitized.append(cleaned)
        else:
            sanitized.append(item)
    return ModelInputData(input=sanitized, instructions=getattr(model_data, "instructions", None))


def _is_local_base_url(base_url: str) -> bool:
    base = base_url.strip().lower()
    return base.startswith("http://127.0.0.1") or base.startswith("http://localhost") or base.startswith(
        "http://0.0.0.0"
    )


def _run_agent(prompt: str, instructions: str) -> dict[str, Any]:
    from agents import (
        Agent,
        ModelSettings,
        RunConfig,
        Runner,
    )
    runner_cfg = get_runner_config()
    base_url = runner_cfg.agents_base_url
    try:
        provider = resolve_runtime_provider_from_env()
    except ProviderResolutionError as exc:
        raise RuntimeError(str(exc)) from exc
    provider_credentials = merge_provider_credentials(
        ProviderCredentials(
            gemini_api_key=str(getattr(runner_cfg, "gemini_api_key", "") or "").strip(),
            openai_api_key=str(getattr(runner_cfg, "openai_api_key", "") or "").strip(),
            anthropic_api_key=str(getattr(runner_cfg, "anthropic_api_key", "") or "").strip(),
            equilibrium_api_key=str(getattr(runner_cfg, "equilibrium_api_key", "") or "").strip(),
        ),
        resolve_provider_credentials(),
    )
    api_key = _resolve_preferred_api_key_for_provider(provider_credentials, provider, base_url=base_url)
    if not api_key:
        raise RuntimeError(_missing_llm_api_key_message(provider))
    compat_client = build_llm_compat_client(
        api_key=api_key,
        base_url=base_url or None,
        provider=provider,
    )
    try:
        from agents import set_default_openai_api

        set_default_openai_api(
            resolve_compat_api_mode(
                str(getattr(runner_cfg, "agents_api", "") or "responses"),
                base_url=base_url,
            )
        )
    except Exception:  # noqa: BLE001
        pass
    if compat_client is not None:
        try:
            from agents import set_default_openai_client

            if callable(set_default_openai_client):
                set_default_openai_client(compat_client)
        except Exception:  # noqa: BLE001
            pass
    agent = Agent(name="OpenVibeCodingPlanner", instructions=instructions, mcp_servers=[])

    async def _run() -> Any:
        model_name = get_runner_config().agents_model or "gemini-2.5-flash"
        result = Runner.run_streamed(
            agent,
            prompt,
            run_config=RunConfig(
                model=model_name,
                tracing_disabled=True,
                model_settings=ModelSettings(
                    extra_headers={"x-openvibecoding-intake": "plan_bundle"},
                    store=_resolve_agents_store(),
                ),
                call_model_input_filter=_strip_model_input_ids,
            ),
        )
        if hasattr(result, "stream_events"):
            async for _ in result.stream_events():
                pass
        return result

    result = asyncio.run(_run())
    output = getattr(result, "final_output", None)
    if not isinstance(output, str) or not output.strip():
        raise RuntimeError("planner output missing")
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"planner output not json: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("planner output not object")
    return payload


# -------------------------------------------------------------------
# Public API
# -------------------------------------------------------------------


def generate_questions(payload: dict[str, Any]) -> list[str]:
    return _generation_helpers.generate_questions(
        payload,
        normalize_constraints=_normalize_constraints,
        default_questions=_default_questions,
        agents_available=_agents_available,
        run_agent=_run_agent,
    )


def generate_plan(payload: dict[str, Any], answers: list[str]) -> dict[str, Any]:
    return _generation_helpers.generate_plan(
        payload,
        answers,
        ensure_agent=_ensure_agent,
        default_owner=_DEFAULT_OWNER,
        normalize_constraints=_normalize_constraints,
        build_plan_fallback=_build_plan_fallback,
        agents_available=_agents_available,
        run_agent=_run_agent,
        validator_factory=ContractValidator,
    )


def generate_plan_bundle(payload: dict[str, Any], answers: list[str]) -> tuple[dict[str, Any], str]:
    return _generation_helpers.generate_plan_bundle(
        payload,
        answers,
        agents_available=_agents_available,
        run_agent=_run_agent,
        build_plan_bundle_fallback=_build_plan_bundle_fallback,
        normalize_constraints=_normalize_constraints,
        ensure_agent=_ensure_agent,
        default_tl=_DEFAULT_TL,
        plan_bundle_keys=_PLAN_BUNDLE_KEYS,
        now_ts=_now_ts,
        normalize_bundle_plan=_normalize_bundle_plan,
        extract_parallelism=_extract_parallelism,
        validate_plan_bundle_paths=_validate_plan_bundle_paths,
        rebalance_bundle_paths=_rebalance_bundle_paths,
        validator_factory=ContractValidator,
    )


def build_task_chain_from_bundle(plan_bundle: dict[str, Any], owner_agent: dict[str, str]) -> dict[str, Any]:
    return _generation_helpers.build_task_chain_from_bundle(
        plan_bundle,
        owner_agent,
        ensure_agent=_ensure_agent,
        default_tl=_DEFAULT_TL,
        fanin_allowed_paths=_FANIN_ALLOWED_PATHS,
    )


# -------------------------------------------------------------------
# Intake Service
# -------------------------------------------------------------------


class IntakeService:
    def __init__(self) -> None:
        self._store = IntakeStore()
        self._validator = ContractValidator()

    def list_task_packs(self) -> list[dict[str, Any]]:
        return list_task_packs()

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized_payload = dict(payload)
        _apply_task_template_defaults(normalized_payload)
        self._validator.validate_report(normalized_payload, "pm_intake_request.v1.json")
        preset, effective_policy, policy_notes = _resolve_intake_browser_policy(normalized_payload)
        normalized_payload["browser_policy_preset"] = preset
        normalized_payload["browser_policy"] = effective_policy
        normalized_payload["policy_notes"] = policy_notes
        intake_id = self._store.create(normalized_payload)
        questions = generate_questions(normalized_payload)
        response = {
            "intake_id": intake_id,
            "status": "NEEDS_INPUT",
            "questions": questions,
            "browser_policy_preset": preset,
            "effective_browser_policy": effective_policy,
            "policy_notes": policy_notes,
        }
        if isinstance(normalized_payload.get("task_template"), str) and str(normalized_payload.get("task_template")).strip():
            response["task_template"] = str(normalized_payload.get("task_template")).strip()
        if isinstance(normalized_payload.get("template_payload"), dict) and normalized_payload.get("template_payload"):
            response["template_payload"] = normalized_payload.get("template_payload")
        self._validator.validate_report(response, "pm_intake_response.v1.json")
        self._store.write_response(intake_id, response)
        return response

    def answer(self, intake_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._store.intake_exists(intake_id):
            return {"intake_id": intake_id, "status": "FAILED", "questions": [], "notes": "intake missing"}
        intake = self._store.read_intake(intake_id)
        if not intake:
            return {"intake_id": intake_id, "status": "FAILED", "questions": [], "notes": "intake missing"}
        answers = _normalize_answers(payload.get("answers") if isinstance(payload, dict) else None)
        redacted_answers = [_redact_answer(item) for item in answers]
        self._store.append_event(
            intake_id,
            {
                "event": "INTAKE_ANSWER",
                "context": {"answers": redacted_answers},
            },
        )
        plan = generate_plan(intake, answers)
        plan_bundle, bundle_note = generate_plan_bundle(intake, answers)
        auto_run_chain = True
        mock_chain = False
        if isinstance(payload, dict):
            if payload.get("auto_run_chain") is False:
                auto_run_chain = False
            mock_chain = bool(payload.get("mock_chain", False))
        try:
            self._validator.validate_report(plan, "plan.schema.json")
            self._validator.validate_report(plan_bundle, "plan_bundle.v1.json")
        except Exception as exc:  # noqa: BLE001
            response = {
                "intake_id": intake_id,
                "status": "FAILED",
                "questions": [],
                "notes": str(exc),
            }
            self._store.write_response(intake_id, response)
            return response
        task_chain: dict[str, Any] | None = None
        try:
            owner_agent = _ensure_agent(
                intake.get("owner_agent") if isinstance(intake, dict) else None,
                _DEFAULT_OWNER,
            )
            chain = build_task_chain_from_bundle(plan_bundle, owner_agent)
            self._validator.validate_report(chain, "task_chain.v1.json")
            task_chain = chain
        except Exception:
            task_chain = None
        response = {
            "intake_id": intake_id,
            "status": "READY",
            "questions": [],
            "plan": plan,
            "plan_bundle": plan_bundle,
            "browser_policy_preset": intake.get("browser_policy_preset") if isinstance(intake, dict) else "safe",
            "effective_browser_policy": intake.get("browser_policy") if isinstance(intake, dict) else None,
            "policy_notes": intake.get("policy_notes") if isinstance(intake, dict) else "",
        }
        if isinstance(intake, dict):
            if isinstance(intake.get("task_template"), str) and str(intake.get("task_template")).strip():
                response["task_template"] = str(intake.get("task_template")).strip()
            if isinstance(intake.get("template_payload"), dict) and intake.get("template_payload"):
                response["template_payload"] = intake.get("template_payload")
        if task_chain:
            response["task_chain"] = task_chain
            chain_path = self._store._intake_dir(intake_id) / "task_chain.json"
            chain_path.write_text(json.dumps(task_chain, ensure_ascii=False, indent=2), encoding="utf-8")
            response["task_chain_path"] = str(chain_path)
            if auto_run_chain:
                snapshot_env = dict(os.environ)
                try:
                    if not os.getenv("OPENVIBECODING_RUNNER"):
                        os.environ["OPENVIBECODING_RUNNER"] = "agents"
                    try:
                        chain_report = _execute_chain(chain_path, mock_chain)
                        response["chain_run_id"] = chain_report.get("run_id", "")
                        self._store.append_event(
                            intake_id,
                            {"event": "INTAKE_CHAIN_RUN", "run_id": response["chain_run_id"]},
                        )
                    except Exception as exc:  # noqa: BLE001
                        response["notes"] = f"{response.get('notes','')}\nchain_run_failed: {exc}".strip()
                finally:
                    os.environ.clear()
                    os.environ.update(snapshot_env)
        if bundle_note:
            existing = response.get("notes", "")
            response["notes"] = f"{existing}\n{bundle_note}".strip() if existing else bundle_note
        self._validator.validate_report(response, "pm_intake_response.v1.json")
        self._store.write_response(intake_id, response)
        return response

    def preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized_payload = dict(payload)
        _apply_task_template_defaults(normalized_payload)
        self._validator.validate_report(normalized_payload, "pm_intake_request.v1.json")
        preset, effective_policy, policy_notes = _resolve_intake_browser_policy(normalized_payload)
        normalized_payload["browser_policy_preset"] = preset
        normalized_payload["browser_policy"] = effective_policy
        normalized_payload["policy_notes"] = policy_notes
        answers = _normalize_answers(payload.get("answers") if isinstance(payload, dict) else None)
        plan = generate_plan(normalized_payload, answers)
        plan_bundle, bundle_note = generate_plan_bundle(normalized_payload, answers)
        owner_agent = _ensure_agent(normalized_payload.get("owner_agent"), _DEFAULT_OWNER)
        task_chain = build_task_chain_from_bundle(plan_bundle, owner_agent)
        self._validator.validate_report(plan, "plan.schema.json")
        self._validator.validate_report(plan_bundle, "plan_bundle.v1.json")
        self._validator.validate_report(task_chain, "task_chain.v1.json")
        contract_preview = _apply_intake_contract_overrides(compile_plan(plan), normalized_payload)
        task_template = str(normalized_payload.get("task_template") or "general").strip() or "general"
        search_queries = normalized_payload.get("search_queries")
        search_query_list = [str(item).strip() for item in search_queries if str(item).strip()] if isinstance(search_queries, list) else []
        evidence_contract = _task_pack_registry().get(task_template.lower(), {}).get("evidence_contract", {})
        tool_permissions = contract_preview.get("tool_permissions") if isinstance(contract_preview.get("tool_permissions"), dict) else {}
        filesystem_policy = str(tool_permissions.get("filesystem") or "workspace-write").strip() or "workspace-write"
        network_policy = str(tool_permissions.get("network") or "deny").strip() or "deny"
        shell_policy = str(tool_permissions.get("shell") or "deny").strip() or "deny"
        requires_network = (
            bool(search_query_list)
            or bool(evidence_contract.get("requires_search_requests"))
            or bool(evidence_contract.get("requires_browser_requests"))
        )
        requires_human_approval = approval_flow.requires_human_approval(
            requires_network=requires_network,
            filesystem_policy=filesystem_policy,
            network_policy=network_policy,
            shell_policy=shell_policy,
        )
        assigned_agent = contract_preview.get("assigned_agent") if isinstance(contract_preview.get("assigned_agent"), dict) else {}
        assigned_role = str(assigned_agent.get("role") or "WORKER").strip() or "WORKER"
        predicted_reports = _predicted_reports_for_task_template(task_template)
        predicted_artifacts = _predicted_artifacts_for_payload(normalized_payload)
        worker_prompt_contracts = _build_worker_prompt_contracts(plan_bundle, normalized_payload)
        unblock_tasks = _build_unblock_tasks_from_worker_contracts(worker_prompt_contracts)
        if unblock_tasks and "planning_unblock_tasks.json" not in predicted_artifacts:
            predicted_artifacts.append("planning_unblock_tasks.json")
        warnings: list[str] = []
        if requires_human_approval:
            warnings.append("Current policies suggest the run may require manual approval before execution can continue.")
        if not contract_preview.get("allowed_paths"):
            warnings.append("The compiled contract preview has no allowed_paths. Execution would fail closed until this is resolved.")
        notes = [policy_notes] if policy_notes else []
        if bundle_note:
            notes.append(bundle_note)
        response = {
            "report_type": "execution_plan_report",
            "generated_at": _now_ts(),
            "task_template": task_template,
            "objective": str(normalized_payload.get("objective") or "").strip(),
            "summary": _build_execution_plan_summary(
                task_template=task_template,
                objective=str(normalized_payload.get("objective") or "").strip(),
                assigned_role=assigned_role,
                requires_human_approval=requires_human_approval,
                predicted_reports=predicted_reports,
            ),
            "browser_policy_preset": preset,
            "effective_browser_policy": effective_policy,
            "questions": generate_questions(normalized_payload),
            "warnings": warnings,
            "notes": notes,
            "assigned_role": assigned_role,
            "assigned_agent_id": str(assigned_agent.get("agent_id") or "").strip(),
            "allowed_paths": contract_preview.get("allowed_paths") if isinstance(contract_preview.get("allowed_paths"), list) else [],
            "acceptance_tests": contract_preview.get("acceptance_tests") if isinstance(contract_preview.get("acceptance_tests"), list) else [],
            "search_queries": search_query_list,
            "predicted_reports": predicted_reports,
            "predicted_artifacts": predicted_artifacts,
            "runtime_capability_summary": build_runtime_capability_summary(
                (
                    contract_preview.get("role_contract", {}).get("runtime_binding")
                    if isinstance(contract_preview.get("role_contract"), dict)
                    else {}
                )
            ),
            "requires_human_approval": requires_human_approval,
            "plan": plan,
            "plan_bundle": plan_bundle,
            "task_chain": task_chain,
            "wave_plan": _build_wave_plan(plan_bundle),
            "worker_prompt_contracts": worker_prompt_contracts,
            "unblock_tasks": unblock_tasks,
            "role_contract_summary": contract_preview.get("role_contract") if isinstance(contract_preview.get("role_contract"), dict) else {},
            "contract_preview": contract_preview,
        }
        self._validator.validate_report(response["wave_plan"], "wave_plan.v1.json")
        for contract in worker_prompt_contracts:
            self._validator.validate_report(contract, "worker_prompt_contract.v1.json")
        for unblock_task in unblock_tasks:
            self._validator.validate_report(unblock_task, "unblock_task.v1.json")
        self._validator.validate_report(response, "execution_plan_report.v1.json")
        return response

    def build_contract(self, intake_id: str) -> dict[str, Any] | None:
        if not self._store.intake_exists(intake_id):
            return None
        response = self._store.read_response(intake_id)
        plan = response.get("plan") if isinstance(response, dict) else None
        if not isinstance(plan, dict):
            return None
        contract = compile_plan(plan)
        intake = self._store.read_intake(intake_id)
        if not isinstance(intake, dict):
            intake = {}
        contract = _apply_intake_contract_overrides(
            contract,
            intake,
            intake_dir=self._store._intake_dir(intake_id),
        )
        return contract
