from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cortexpilot_orch.chain import chain_lifecycle
from cortexpilot_orch.store.run_store import RunStore

TERMINAL_RUN_STATUSES = {
    "SUCCESS",
    "FAILURE",
    "PASS",
    "FAIL",
    "ERROR",
    "BLOCKED",
    "CANCELLED",
    "CANCELED",
    "TIMEOUT",
    "TIMED_OUT",
    "INTERRUPTED",
    "PARTIAL",
}

_SCHEMA_KEYS_CACHE: dict[str, set[str]] = {}


def now_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_manifest(runs_root: Path, run_id: str) -> dict[str, Any]:
    manifest_path = runs_root / run_id / "manifest.json"
    if not manifest_path.exists():
        return {}
    return load_json(manifest_path)


def normalize_run_status(status: Any) -> str:
    normalized = str(status or "").strip().upper()
    return normalized or "UNKNOWN"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()


def merge_artifacts(payload: dict[str, Any], artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    if not artifacts:
        return payload
    updated = dict(payload)
    existing = updated.get("artifacts")
    if not isinstance(existing, list):
        existing = []
    updated["artifacts"] = [*existing, *artifacts]
    return updated


def schema_allowed_keys(schema_root: Path, schema_name: str) -> set[str]:
    cache_key = f"{schema_root}:{schema_name}"
    cached = _SCHEMA_KEYS_CACHE.get(cache_key)
    if cached is not None:
        return cached
    schema_path = schema_root / schema_name
    payload = json.loads(schema_path.read_text(encoding="utf-8"))
    props = payload.get("properties") if isinstance(payload, dict) else {}
    keys = set(props.keys()) if isinstance(props, dict) else set()
    _SCHEMA_KEYS_CACHE[cache_key] = keys
    return keys


def deep_merge_payload(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    if not override:
        return base
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge_payload(merged[key], value)
        else:
            merged[key] = value
    return merged


def filter_payload_keys(payload: dict[str, Any], allowed: set[str]) -> dict[str, Any]:
    if not allowed:
        return payload
    return {key: value for key, value in payload.items() if key in allowed}


def output_schema_name_for_role(role: str | None) -> str:
    role_key = (role or "").strip().upper()
    if role_key == "REVIEWER":
        return "review_report.v1.json"
    if role_key in {"TEST_RUNNER", "TEST"}:
        return "test_report.v1.json"
    return "agent_task_result.v1.json"


def output_schema_role_key(role: str | None) -> str:
    role_key = (role or "").strip().lower()
    return role_key or "worker"


def ensure_output_schema_artifact(contract: dict[str, Any]) -> dict[str, Any]:
    inputs = contract.get("inputs")
    if not isinstance(inputs, dict):
        inputs = {}
        contract["inputs"] = inputs
    artifacts = inputs.get("artifacts")
    if not isinstance(artifacts, list):
        artifacts = []
        inputs["artifacts"] = artifacts
    role = None
    assigned = contract.get("assigned_agent")
    if isinstance(assigned, dict):
        role = assigned.get("role")
    role_key = output_schema_role_key(role)
    candidates = {f"output_schema.{role_key}", "output_schema"}
    for artifact in artifacts:
        if isinstance(artifact, dict):
            name = artifact.get("name")
            if isinstance(name, str) and name.strip().lower() in candidates:
                return contract
    schema_root = Path(__file__).resolve().parents[5] / "schemas"
    schema_name = output_schema_name_for_role(role)
    schema_path = schema_root / schema_name
    if not schema_path.exists():
        return contract
    sha = hashlib.sha256(schema_path.read_bytes()).hexdigest()
    artifacts.append(
        {
            "name": f"output_schema.{role_key}",
            "uri": f"schemas/{schema_name}",
            "sha256": sha,
        }
    )
    return contract


def dependency_artifact(store: RunStore, dep_name: str, dep_run_id: str) -> dict[str, Any] | None:
    if not dep_run_id:
        return None
    task_result_path = store._run_dir(dep_run_id) / "reports" / "task_result.json"
    if not task_result_path.exists():
        return None
    return {
        "name": f"dependency:{dep_name}:task_result.json",
        "uri": str(task_result_path),
        "sha256": sha256_file(task_result_path),
    }


def dependency_patch_artifact(store: RunStore, dep_name: str, dep_run_id: str) -> dict[str, Any] | None:
    if not dep_run_id:
        return None
    patch_path = store._run_dir(dep_run_id) / "patch.diff"
    if not patch_path.exists():
        return None
    return {
        "name": f"dependency:{dep_name}:patch.diff",
        "uri": str(patch_path),
        "sha256": sha256_file(patch_path),
    }


def should_propagate_dependency_patch(step: dict[str, Any]) -> bool:
    kind = str(step.get("kind", "")).strip().lower()
    if kind != "contract":
        return False
    payload = step.get("payload") if isinstance(step.get("payload"), dict) else {}
    assigned = payload.get("assigned_agent") if isinstance(payload.get("assigned_agent"), dict) else {}
    role = chain_lifecycle._agent_role(assigned)
    task_type = str(payload.get("task_type", "")).strip().upper()
    if role in {"REVIEWER", "TEST", "TEST_RUNNER"}:
        return False
    if task_type in {"REVIEW", "TEST"}:
        return False
    return True


def resolve_contract_from_dependency(
    task_result: dict[str, Any] | None,
    contract_index: int | None,
) -> dict[str, Any] | None:
    if not isinstance(task_result, dict):
        return None
    evidence_refs = task_result.get("evidence_refs")
    if not isinstance(evidence_refs, dict):
        return None
    contracts = evidence_refs.get("contracts")
    if not isinstance(contracts, list) or not contracts:
        return None
    index = 0
    if contract_index is not None:
        try:
            index = int(contract_index)
        except (TypeError, ValueError):
            index = 0
    if index < 0 or index >= len(contracts):
        return None
    candidate = contracts[index]
    return candidate if isinstance(candidate, dict) else None


def merge_contract_overrides(contract: dict[str, Any], overrides: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(overrides, dict) or not overrides:
        return contract
    merged = dict(contract)
    for key, value in overrides.items():
        merged[key] = value
    return merged


def is_fanin_step(step: dict[str, Any]) -> bool:
    name = str(step.get("name", "")).strip().lower()
    labels = step.get("labels") if isinstance(step.get("labels"), list) else []
    return name == "fan_in" or any(str(item).strip().lower() == "fan_in" for item in labels)


def normalize_fanin_summary(summary: str, dep_runs: list[str]) -> str:
    base = {
        "format": "cortexpilot.fanin.summary.v1",
        "inconsistencies": [],
        "duplicates": [],
        "stats": {"total": 0, "high": 0, "medium": 0, "low": 0},
        "dependency_run_ids": dep_runs,
        "notes": "",
    }
    payload: dict[str, Any] | None = None
    if isinstance(summary, str) and summary.strip():
        try:
            parsed = json.loads(summary)
        except json.JSONDecodeError:
            base["notes"] = summary
        else:
            if isinstance(parsed, dict):
                payload = parsed
            elif isinstance(parsed, list):
                base["inconsistencies"] = parsed
            else:
                base["notes"] = summary
    if payload:
        base.update(payload)
        if "notes" not in base:
            base["notes"] = ""
        if "duplicates" not in base:
            base["duplicates"] = []
        if "inconsistencies" not in base:
            base["inconsistencies"] = []
    normalized_dep_runs = [item.strip() for item in dep_runs if isinstance(item, str) and item.strip()]
    candidate_dep_runs = base.get("dependency_run_ids")
    if isinstance(candidate_dep_runs, list):
        candidate_dep_runs = [
            item.strip()
            for item in candidate_dep_runs
            if isinstance(item, str) and item.strip()
        ]
    else:
        candidate_dep_runs = []
    base["dependency_run_ids"] = candidate_dep_runs or normalized_dep_runs
    inconsistencies = base.get("inconsistencies")
    if not isinstance(inconsistencies, list):
        inconsistencies = []
    normalized_items = []
    counts = {"high": 0, "medium": 0, "low": 0}
    for item in inconsistencies:
        if isinstance(item, str):
            entry = {"id": item, "title": item, "severity": "medium"}
        elif isinstance(item, dict):
            entry = dict(item)
            if not entry.get("id"):
                entry["id"] = entry.get("title") or f"issue_{len(normalized_items)+1}"
            if not entry.get("title"):
                entry["title"] = str(entry.get("id"))
            if entry.get("severity") not in {"high", "medium", "low"}:
                entry["severity"] = "medium"
        else:
            continue
        severity = entry.get("severity", "medium")
        counts[severity] = counts.get(severity, 0) + 1
        normalized_items.append(entry)
    base["inconsistencies"] = normalized_items
    base["stats"] = {
        "total": len(normalized_items),
        "high": counts.get("high", 0),
        "medium": counts.get("medium", 0),
        "low": counts.get("low", 0),
    }
    return json.dumps(base, ensure_ascii=False)


def normalize_fanin_task_result(
    store: RunStore,
    chain_run_id: str,
    step_name: str,
    step_run_id: str,
    dep_runs: list[str],
) -> None:
    if not step_run_id:
        return
    run_dir = store._run_dir(step_run_id)
    payload: dict[str, Any] | None = None
    for candidate in (
        run_dir / "reports" / "task_result.json",
        run_dir / "artifacts" / "agent_task_result.json",
    ):
        if not candidate.exists():
            continue
        try:
            loaded = json.loads(candidate.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(loaded, dict):
            payload = loaded
            break
    if not isinstance(payload, dict):
        return
    normalized_dep_runs = [item.strip() for item in dep_runs if isinstance(item, str) and item.strip()]
    summary = payload.get("summary", "")
    payload["summary"] = normalize_fanin_summary(str(summary or ""), normalized_dep_runs)
    evidence_refs = payload.get("evidence_refs")
    if not isinstance(evidence_refs, dict):
        evidence_refs = {}
    evidence_refs["dependency_run_ids"] = normalized_dep_runs
    payload["evidence_refs"] = evidence_refs
    task_id = payload.get("task_id") or step_name
    store.write_report(step_run_id, "task_result", payload)
    store.write_task_result(step_run_id, str(task_id), payload)
    store.append_event(
        chain_run_id,
        {
            "level": "INFO",
            "event": "CHAIN_FANIN_SUMMARY_NORMALIZED",
            "run_id": chain_run_id,
            "meta": {"step": step_name, "fan_in_run_id": step_run_id},
        },
    )


def artifact_names(contract: dict[str, Any]) -> list[str]:
    inputs = contract.get("inputs") if isinstance(contract, dict) else None
    if not isinstance(inputs, dict):
        return []
    artifacts = inputs.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    names = []
    for item in artifacts:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    return names


def is_purified_name(name: str) -> bool:
    lowered = name.lower()
    return "summary" in lowered or "purified" in lowered or lowered.endswith("task_result.json")


def is_raw_name(name: str) -> bool:
    lowered = name.lower()
    raw_markers = [
        "search_results",
        "verification",
        "tampermonkey_raw",
        "browser_results",
        "raw",
    ]
    return any(marker in lowered for marker in raw_markers)


def apply_context_policy(
    contract: dict[str, Any],
    policy: dict[str, Any],
    owner_role: str,
    step_name: str,
) -> tuple[dict[str, Any], list[str], list[str]]:
    violations: list[str] = []
    truncations: list[str] = []
    inputs = contract.get("inputs")
    if not isinstance(inputs, dict):
        inputs = {"spec": "", "artifacts": []}
        contract["inputs"] = inputs

    spec = str(inputs.get("spec", ""))
    artifacts = inputs.get("artifacts")
    if not isinstance(artifacts, list):
        artifacts = []
        inputs["artifacts"] = artifacts

    mode = str(policy.get("mode", "inherit")).strip().lower()
    if owner_role == "PM":
        mode = "summary-only"

    allow_names = policy.get("allow_artifact_names") or []
    if isinstance(allow_names, str):
        allow_names = [allow_names]
    allow_names = [str(item).strip() for item in allow_names if str(item).strip()]

    deny_substrings = policy.get("deny_artifact_substrings") or []
    if isinstance(deny_substrings, str):
        deny_substrings = [deny_substrings]
    deny_substrings = [str(item).strip().lower() for item in deny_substrings if str(item).strip()]

    require_summary = bool(policy.get("require_summary", False))

    if mode == "isolated":
        if artifacts:
            violations.append("context isolated: artifacts must be empty")
    elif mode == "summary-only":
        if not artifacts:
            violations.append("summary-only requires artifacts")
        non_schema_names: list[str] = []
        for item in artifacts:
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            if name.lower().startswith("output_schema"):
                continue
            non_schema_names.append(name)
            if is_raw_name(name):
                violations.append(f"summary-only forbids raw artifact: {name}")
            if not is_purified_name(name):
                violations.append(f"summary-only requires purified artifact: {name}")
        if not non_schema_names:
            violations.append("summary-only requires dependency summary artifacts")
    elif mode != "inherit":
        violations.append(f"unknown context_policy mode: {mode}")

    for item in artifacts:
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        if allow_names and name not in allow_names:
            violations.append(f"artifact not allowed: {name}")
        if deny_substrings and any(token in name.lower() for token in deny_substrings):
            violations.append(f"artifact denied by policy: {name}")
        if require_summary and not is_purified_name(name):
            violations.append(f"summary required: {name}")

    max_artifacts = policy.get("max_artifacts")
    try:
        max_artifacts = int(max_artifacts) if max_artifacts is not None else None
    except (TypeError, ValueError):
        max_artifacts = None
    if max_artifacts is not None and max_artifacts >= 0 and len(artifacts) > max_artifacts:
        inputs["artifacts"] = artifacts[:max_artifacts]
        truncations.append(f"artifacts truncated to {max_artifacts}")

    max_spec_chars = policy.get("max_spec_chars")
    try:
        max_spec_chars = int(max_spec_chars) if max_spec_chars is not None else None
    except (TypeError, ValueError):
        max_spec_chars = None
    if max_spec_chars is not None and max_spec_chars > 0 and len(spec) > max_spec_chars:
        inputs["spec"] = spec[:max_spec_chars]
        truncations.append(f"spec truncated to {max_spec_chars} chars")

    if violations:
        violations = [f"{step_name}: {item}" for item in violations]
    if truncations:
        truncations = [f"{step_name}: {item}" for item in truncations]
    return contract, violations, truncations
