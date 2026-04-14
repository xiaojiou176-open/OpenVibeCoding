from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError


_FORBIDDEN_PATH_MARKERS = {"*", "**", ".", "/"}
_GLOB_CHARS = {"*", "?", "["}
_WIDE_PATH_MARKERS = {"src", "docs"}
_REPO_ROOT = Path(__file__).resolve().parents[5]
_AGENT_REGISTRY_ENV = "OPENVIBECODING_AGENT_REGISTRY"
_SCHEMA_REGISTRY_FILE = "schema_registry.json"
_SUPERPOWERS_GATE_ENV = "OPENVIBECODING_SUPERPOWERS_GATE_ENFORCE"
_SUPERPOWERS_GATE_MARKERS = {
    "superpowers://required",
    "superpowers:required",
    "gate:superpowers",
    "openvibecoding://superpowers-gate",
}
_PLAN_STAGE_MARKERS = {
    "plan",
    "roadmap",
    "milestone",
    "\u6b65\u9aa4",
    "\u65b9\u6848",
    "\u8ba1\u5212",
}
_TRIVIAL_TEST_COMMANDS = {"true", ":"}
_FRAGMENT_REF_LABEL_SUFFIXES = ("mcp_bundle_ref", "skills_bundle_ref")
_FRAGMENT_REF_MAX_BYTES = 256 * 1024
_FRAGMENT_REF_ALLOWED_PATHS = {
    "role_contract.mcp_bundle_ref": {"policies/agent_registry.json"},
    "role_contract.skills_bundle_ref": {"policies/skills_bundle_registry.json"},
    "role_config.mcp_bundle_ref": {"policies/agent_registry.json"},
    "role_config.skills_bundle_ref": {"policies/skills_bundle_registry.json"},
}
_ROLE_SELECTOR_RE = re.compile(r"^(?P<name>[A-Za-z0-9_:-]+)\(role=(?P<role>[A-Za-z0-9_:-]+)\)$")


def resolve_agent_registry_path(repo_root: Path | None = None) -> Path:
    root = repo_root or _REPO_ROOT
    override = os.getenv(_AGENT_REGISTRY_ENV, "").strip()
    if override:
        path = Path(override).expanduser()
        return (root / path).resolve() if not path.is_absolute() else path
    preferred = root / "policies" / "agent_registry.json"
    return preferred


def _agent_registry_path() -> Path:
    return resolve_agent_registry_path()


def _load_agent_registry() -> dict[str, Any]:
    path = _agent_registry_path()
    if not path.exists():
        raise ValueError(f"agent_registry missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"agent_registry invalid: {exc}") from exc
    schema_path = _REPO_ROOT / "schemas" / "agent_registry.v1.json"
    if not schema_path.exists():
        raise ValueError(f"agent_registry schema missing: {schema_path}")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    try:
        validator.validate(payload)
    except ValidationError as exc:
        detail = f"{exc.message} (path={list(exc.path)})"
        raise ValueError(f"agent_registry schema validation failed: {detail}") from exc
    return payload if isinstance(payload, dict) else {}


def _schema_root(schema_root: Path | None = None) -> Path:
    if schema_root is not None:
        return schema_root
    return _REPO_ROOT / "schemas"


def _schema_registry_path(schema_root: Path | None = None) -> Path:
    return _schema_root(schema_root) / _SCHEMA_REGISTRY_FILE


def _schema_hash(path: Path) -> str:
    payload = path.read_bytes()
    return hashlib.sha256(payload).hexdigest()


_OUTPUT_SCHEMA_BY_ROLE: dict[str, str] = {
    "REVIEWER": "review_report.v1.json",
    "TEST_RUNNER": "test_report.v1.json",
    "TEST": "test_report.v1.json",
}


def _output_schema_name_for_role(role: str | None) -> str:
    role_key = (role or "").strip().upper()
    return _OUTPUT_SCHEMA_BY_ROLE.get(role_key, "agent_task_result.v1.json")


def _output_schema_role_key(role: str | None) -> str:
    role_key = (role or "").strip().lower()
    return role_key or "worker"


def _resolve_output_schema_artifact(artifacts: list[Any], role: str | None) -> dict[str, Any] | None:
    role_key = _output_schema_role_key(role)
    candidates = {f"output_schema.{role_key}", "output_schema"}
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        name = artifact.get("name")
        if isinstance(name, str) and name.strip().lower() in candidates:
            return artifact
    return None


def _resolve_output_schema_path(
    artifact: dict[str, Any],
    schema_root: Path,
    repo_root: Path,
    expected_name: str,
) -> Path:
    uri = artifact.get("uri")
    if not isinstance(uri, str) or not uri.strip():
        raise ValueError("Contract validation failed: output_schema uri missing")
    raw = Path(uri)
    candidate = raw if raw.is_absolute() else (repo_root / raw)
    candidate = candidate.resolve()
    if not candidate.exists():
        raise ValueError(f"Contract validation failed: output_schema not found: {candidate}")
    try:
        if not candidate.is_relative_to(schema_root.resolve()):
            raise ValueError(
                f"Contract validation failed: output_schema must live under {schema_root}"
            )
    except AttributeError:
        if not str(candidate).startswith(str(schema_root.resolve())):
            raise ValueError(
                f"Contract validation failed: output_schema must live under {schema_root}"
            )
    if candidate.name != expected_name:
        raise ValueError(
            "Contract validation failed: output_schema mismatch for role "
            f"(expected {expected_name}, got {candidate.name})"
        )
    return candidate


def _compute_schema_hashes(schema_root: Path | None = None) -> dict[str, str]:
    root = _schema_root(schema_root)
    hashes: dict[str, str] = {}
    for path in sorted(root.glob("*.json")):
        if path.name == _SCHEMA_REGISTRY_FILE:
            continue
        hashes[path.name] = _schema_hash(path)
    return hashes


def check_schema_registry(schema_root: Path | None = None) -> dict[str, Any]:
    root = _schema_root(schema_root)
    registry_path = _schema_registry_path(root)
    computed = _compute_schema_hashes(root)
    if not registry_path.exists():
        return {
            "status": "missing",
            "registry_path": str(registry_path),
            "computed_count": len(computed),
            "mismatched": [],
            "missing": [],
            "extra": [],
        }
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "status": "invalid",
            "registry_path": str(registry_path),
            "error": str(exc),
            "computed_count": len(computed),
            "mismatched": [],
            "missing": [],
            "extra": [],
        }
    declared = registry.get("schemas") if isinstance(registry, dict) else {}
    declared = declared if isinstance(declared, dict) else {}
    mismatched: list[str] = []
    missing: list[str] = []
    extra: list[str] = []
    for name, sha in computed.items():
        declared_entry = declared.get(name)
        declared_sha = declared_entry.get("sha256") if isinstance(declared_entry, dict) else None
        if declared_entry is None:
            missing.append(name)
            continue
        if declared_sha != sha:
            mismatched.append(name)
    for name in declared.keys():
        if name not in computed:
            extra.append(name)
    status = "ok" if not (mismatched or missing or extra) else "mismatch"
    return {
        "status": status,
        "registry_path": str(registry_path),
        "registry_version": registry.get("version") if isinstance(registry, dict) else None,
        "computed_count": len(computed),
        "mismatched": mismatched,
        "missing": missing,
        "extra": extra,
    }


def _ensure_agent_in_registry(registry: dict[str, Any], agent: object, label: str) -> None:
    if not isinstance(agent, dict):
        raise ValueError(f"agent_registry validation failed: {label} invalid")
    agent_id = agent.get("agent_id")
    role = agent.get("role")
    if not isinstance(agent_id, str) or not agent_id.strip():
        raise ValueError(f"agent_registry validation failed: {label}.agent_id missing")
    if not isinstance(role, str) or not role.strip():
        raise ValueError(f"agent_registry validation failed: {label}.role missing")
    entries = registry.get("agents") if isinstance(registry, dict) else []
    match = False
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if entry.get("agent_id") == agent_id and entry.get("role") == role:
                match = True
                break
    if not match:
        raise ValueError(f"agent_registry validation failed: {label} not registered")


def _normalize_allowed_path(path: str) -> str:
    return Path(path).as_posix().lstrip("./")


def find_invalid_allowed_paths(allowed_paths: Iterable[object]) -> list[str]:
    invalid: list[str] = []
    for raw in allowed_paths:
        if not isinstance(raw, str):
            invalid.append(str(raw))
            continue
        candidate = raw.strip()
        if not candidate:
            invalid.append(raw)
            continue
        normalized = _normalize_allowed_path(candidate)
        if not normalized or normalized in _FORBIDDEN_PATH_MARKERS:
            invalid.append(candidate)
            continue
        if normalized.startswith("/") or normalized.startswith("../") or "/../" in normalized:
            invalid.append(candidate)
            continue
        if normalized.startswith(".runtime-cache"):
            invalid.append(candidate)
            continue
        if any(ch in normalized for ch in _GLOB_CHARS):
            invalid.append(candidate)
            continue
    return invalid


def is_wide_path(path: str) -> bool:
    if not isinstance(path, str):
        return False
    candidate = path.strip()
    if not candidate:
        return True
    normalized = _normalize_allowed_path(candidate)
    if not normalized:
        return True
    if normalized in _FORBIDDEN_PATH_MARKERS:
        return True
    if normalized.startswith(".runtime-cache"):
        return True
    if normalized.rstrip("/") in _WIDE_PATH_MARKERS:
        return True
    return False


def find_wide_paths(allowed_paths: Iterable[object]) -> list[str]:
    wide: list[str] = []
    for raw in allowed_paths:
        if not isinstance(raw, str):
            continue
        if is_wide_path(raw):
            wide.append(raw)
    return wide


def _normalize_contract_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    inputs = normalized.get("inputs") if isinstance(normalized.get("inputs"), dict) else {}
    if isinstance(inputs, dict):
        inputs_copy = dict(inputs)
        artifacts = inputs_copy.get("artifacts")
        if isinstance(artifacts, dict):
            inputs_copy["artifacts"] = [artifacts]
        normalized["inputs"] = inputs_copy

    mcp_tool_set = normalized.get("mcp_tool_set")
    if not isinstance(mcp_tool_set, list):
        tool_permissions = normalized.get("tool_permissions") if isinstance(normalized.get("tool_permissions"), dict) else {}
        legacy_mcp_tools = tool_permissions.get("mcp_tools") if isinstance(tool_permissions.get("mcp_tools"), list) else []
        if legacy_mcp_tools:
            normalized["mcp_tool_set"] = legacy_mcp_tools
    return normalized


def _validate_ref_path(raw: Any, label: str) -> None:
    if raw is None:
        return
    if not isinstance(raw, str):
        raise ValueError(f"Contract validation failed: {label} must be string or null")
    value = raw.strip()
    if not value:
        raise ValueError(f"Contract validation failed: {label} invalid")
    path_text, fragment = (value.split("#", 1) + [""])[:2]
    path_text = path_text.strip()
    fragment = fragment.strip()
    if not path_text:
        raise ValueError(f"Contract validation failed: {label} invalid")
    path = Path(path_text)
    if path.is_absolute():
        raise ValueError(f"Contract validation failed: {label} must be a repo-relative path")
    repo_root = _REPO_ROOT.resolve()
    candidate = (repo_root / path).resolve()
    try:
        common = os.path.commonpath([str(repo_root), str(candidate)])
    except ValueError as exc:
        raise ValueError(
            f"Contract validation failed: {label} must stay within the repository"
        ) from exc
    if common != str(repo_root):
        raise ValueError(
            f"Contract validation failed: {label} must stay within the repository"
        )
    if not candidate.exists():
        raise ValueError(f"Contract validation failed: {label} not found: {path_text}")
    if not candidate.is_file():
        raise ValueError(f"Contract validation failed: {label} must reference a file: {path_text}")
    if "#" not in value:
        return
    if not any(label.endswith(suffix) for suffix in _FRAGMENT_REF_LABEL_SUFFIXES):
        raise ValueError(f"Contract validation failed: {label} fragments not allowed")
    if not fragment:
        raise ValueError(f"Contract validation failed: {label} fragment missing")
    normalized_path = _normalize_allowed_path(path_text)
    allowed_paths = _FRAGMENT_REF_ALLOWED_PATHS.get(label)
    if not allowed_paths or normalized_path not in allowed_paths:
        raise ValueError(
            f"Contract validation failed: {label} fragment source must be allowlisted"
        )
    try:
        file_size = candidate.stat().st_size
    except OSError as exc:
        raise ValueError(f"Contract validation failed: {label} unreadable: {path_text}") from exc
    if file_size > _FRAGMENT_REF_MAX_BYTES:
        raise ValueError(
            f"Contract validation failed: {label} fragment source too large: {path_text}"
        )
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"Contract validation failed: {label} unreadable: {path_text}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Contract validation failed: {label} fragment requires json document"
        ) from exc
    try:
        resolved = _resolve_ref_fragment(payload, fragment)
    except ValueError as exc:
        raise ValueError(
            f"Contract validation failed: {label} fragment invalid: {fragment}"
        ) from exc
    if label.endswith("mcp_bundle_ref"):
        if not isinstance(resolved, list) or not any(
            isinstance(item, str) and item.strip() for item in resolved
        ):
            raise ValueError(
                f"Contract validation failed: {label} must resolve to non-empty mcp_tools list"
            )
    if label.endswith("skills_bundle_ref"):
        skills = resolved.get("skills") if isinstance(resolved, dict) else None
        if not isinstance(skills, list) or not any(
            isinstance(item, str) and item.strip() for item in skills
        ):
            raise ValueError(
                f"Contract validation failed: {label} must resolve to non-empty skills list"
            )


def validate_role_config_fields(payload: dict[str, Any], *, label_prefix: str = "role_config") -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError(f"{label_prefix} must be an object")
    system_prompt_ref = payload.get("system_prompt_ref")
    skills_bundle_ref = payload.get("skills_bundle_ref")
    mcp_bundle_ref = payload.get("mcp_bundle_ref")
    runtime_binding = payload.get("runtime_binding")
    _validate_ref_path(system_prompt_ref, f"{label_prefix}.system_prompt_ref")
    if skills_bundle_ref is not None:
        _validate_ref_path(skills_bundle_ref, f"{label_prefix}.skills_bundle_ref")
    _validate_ref_path(mcp_bundle_ref, f"{label_prefix}.mcp_bundle_ref")
    if not isinstance(runtime_binding, dict):
        raise ValueError(f"{label_prefix}.runtime_binding must be an object")
    normalized_runtime_binding: dict[str, str | None] = {}
    for key in ("runner", "provider", "model"):
        value = runtime_binding.get(key)
        if value is None:
            normalized_runtime_binding[key] = None
            continue
        if not isinstance(value, str):
            raise ValueError(f"{label_prefix}.runtime_binding.{key} must be string or null")
        normalized = value.strip() or None
        normalized_runtime_binding[key] = normalized
    return {
        "system_prompt_ref": str(system_prompt_ref).strip() if isinstance(system_prompt_ref, str) and system_prompt_ref.strip() else None,
        "skills_bundle_ref": str(skills_bundle_ref).strip() if isinstance(skills_bundle_ref, str) and skills_bundle_ref.strip() else None,
        "mcp_bundle_ref": str(mcp_bundle_ref).strip() if isinstance(mcp_bundle_ref, str) and mcp_bundle_ref.strip() else None,
        "runtime_binding": normalized_runtime_binding,
    }


def _resolve_ref_fragment(payload: Any, fragment: str) -> Any:
    if fragment.startswith("/"):
        return _resolve_json_pointer(payload, fragment)
    return _resolve_registry_fragment(payload, fragment)


def _resolve_json_pointer(payload: Any, fragment: str) -> Any:
    current = payload
    for raw_part in fragment.lstrip("/").split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            if part not in current:
                raise ValueError(f"fragment segment missing: {part}")
            current = current[part]
            continue
        if isinstance(current, list) and part.isdigit():
            index = int(part)
            if index >= len(current):
                raise ValueError(f"fragment index out of range: {part}")
            current = current[index]
            continue
        raise ValueError(f"fragment segment invalid: {part}")
    return current


def _resolve_registry_fragment(payload: Any, fragment: str) -> Any:
    current = payload
    for part in fragment.split("."):
        token = part.strip()
        if not token:
            raise ValueError("fragment segment invalid")
        selector = _ROLE_SELECTOR_RE.match(token)
        if selector:
            if not isinstance(current, dict):
                raise ValueError(f"fragment selector parent invalid: {token}")
            entries = current.get(selector.group("name"))
            if not isinstance(entries, list):
                raise ValueError(f"fragment selector target invalid: {token}")
            role = selector.group("role").strip().upper()
            matched = next(
                (
                    entry
                    for entry in entries
                    if isinstance(entry, dict)
                    and str(entry.get("role") or "").strip().upper() == role
                ),
                None,
            )
            if matched is None:
                raise ValueError(f"fragment selector missing role: {role}")
            current = matched
            continue
        if isinstance(current, dict):
            if token not in current:
                raise ValueError(f"fragment segment missing: {token}")
            current = current[token]
            continue
        if isinstance(current, list) and token.isdigit():
            index = int(token)
            if index >= len(current):
                raise ValueError(f"fragment index out of range: {token}")
            current = current[index]
            continue
        raise ValueError(f"fragment segment invalid: {token}")
    return current


def _validate_role_contract(payload: dict[str, Any]) -> None:
    role_contract = payload.get("role_contract")
    if role_contract is None:
        return
    if not isinstance(role_contract, dict):
        raise ValueError("Contract validation failed: role_contract invalid")
    assigned = payload.get("assigned_agent") if isinstance(payload.get("assigned_agent"), dict) else {}
    identity = role_contract.get("identity") if isinstance(role_contract.get("identity"), dict) else {}
    assigned_role = str(assigned.get("role") or "").strip().upper()
    assigned_agent_id = str(assigned.get("agent_id") or "").strip()
    if str(identity.get("role") or "").strip().upper() != assigned_role:
        raise ValueError("Contract validation failed: role_contract.identity.role mismatch")
    if str(identity.get("agent_id") or "").strip() != assigned_agent_id:
        raise ValueError("Contract validation failed: role_contract.identity.agent_id mismatch")
    _validate_ref_path(role_contract.get("system_prompt_ref"), "role_contract.system_prompt_ref")
    skills_ref = role_contract.get("skills_bundle_ref")
    if skills_ref is not None:
        _validate_ref_path(skills_ref, "role_contract.skills_bundle_ref")
    _validate_ref_path(role_contract.get("mcp_bundle_ref"), "role_contract.mcp_bundle_ref")
    role_tool_permissions = role_contract.get("tool_permissions")
    tool_permissions = payload.get("tool_permissions") if isinstance(payload.get("tool_permissions"), dict) else {}
    if not isinstance(role_tool_permissions, dict):
        raise ValueError("Contract validation failed: role_contract.tool_permissions invalid")
    for key in ("filesystem", "shell", "network"):
        if str(role_tool_permissions.get(key) or "").strip() != str(tool_permissions.get(key) or "").strip():
            raise ValueError(f"Contract validation failed: role_contract.tool_permissions.{key} mismatch")
    resolved_tools = role_contract.get("resolved_mcp_tool_set")
    if not isinstance(resolved_tools, list):
        raise ValueError("Contract validation failed: role_contract.resolved_mcp_tool_set invalid")
    expected_tools = [
        str(item).strip()
        for item in payload.get("mcp_tool_set", [])
        if isinstance(item, str) and item.strip()
    ]
    if resolved_tools != expected_tools:
        raise ValueError("Contract validation failed: role_contract.resolved_mcp_tool_set mismatch")
    runtime_binding = role_contract.get("runtime_binding")
    runtime_options = payload.get("runtime_options") if isinstance(payload.get("runtime_options"), dict) else {}
    if not isinstance(runtime_binding, dict):
        raise ValueError("Contract validation failed: role_contract.runtime_binding invalid")
    for key in ("runner", "provider"):
        expected_value = str(runtime_options.get(key) or "").strip()
        actual_value = str(runtime_binding.get(key) or "").strip()
        if expected_value != actual_value:
            if expected_value or actual_value:
                raise ValueError(f"Contract validation failed: role_contract.runtime_binding.{key} mismatch")
    handoff = role_contract.get("handoff")
    chain = payload.get("handoff_chain") if isinstance(payload.get("handoff_chain"), dict) else {}
    if not isinstance(handoff, dict):
        raise ValueError("Contract validation failed: role_contract.handoff invalid")
    actual_chain_roles = [
        str(item).strip().upper()
        for item in chain.get("roles", [])
        if isinstance(item, str) and item.strip()
    ]
    summary_chain_roles = [
        str(item).strip().upper()
        for item in handoff.get("chain_roles", [])
        if isinstance(item, str) and item.strip()
    ]
    if summary_chain_roles != actual_chain_roles:
        raise ValueError("Contract validation failed: role_contract.handoff.chain_roles mismatch")
    actual_max_handoffs = chain.get("max_handoffs")
    summary_max_handoffs = handoff.get("max_handoffs")
    if actual_max_handoffs is None:
        if summary_max_handoffs is not None:
            raise ValueError("Contract validation failed: role_contract.handoff.max_handoffs mismatch")
    else:
        if summary_max_handoffs != actual_max_handoffs:
            raise ValueError("Contract validation failed: role_contract.handoff.max_handoffs mismatch")


def _is_truthy(raw: str | None) -> bool:
    if raw is None:
        return False
    return raw.strip().lower() in {"1", "true", "yes", "on", "strict", "enforce"}


def _contains_plan_marker(raw: object) -> bool:
    if not isinstance(raw, str):
        return False
    candidate = raw.strip().lower()
    if not candidate:
        return False
    return any(marker in candidate for marker in _PLAN_STAGE_MARKERS)


def _normalize_command(raw: object) -> str:
    if not isinstance(raw, str):
        return ""
    return " ".join(raw.strip().lower().split())


def _is_trivial_acceptance_command(command: str) -> bool:
    if not command:
        return True
    if command in _TRIVIAL_TEST_COMMANDS:
        return True
    if command.startswith("echo ") and "&&" not in command and ";" not in command and "|" not in command:
        return True
    return False


def is_superpowers_gate_required(payload: dict[str, Any]) -> bool:
    if _is_truthy(os.getenv(_SUPERPOWERS_GATE_ENV)):
        return True
    links = payload.get("evidence_links")
    if not isinstance(links, list):
        return False
    for link in links:
        if not isinstance(link, str):
            continue
        normalized = link.strip().lower()
        if normalized in _SUPERPOWERS_GATE_MARKERS:
            return True
    return False


def evaluate_superpowers_gate(payload: dict[str, Any]) -> dict[str, Any]:
    required = is_superpowers_gate_required(payload)
    inputs = payload.get("inputs") if isinstance(payload.get("inputs"), dict) else {}
    spec = inputs.get("spec") if isinstance(inputs.get("spec"), str) else ""
    artifacts = inputs.get("artifacts") if isinstance(inputs.get("artifacts"), list) else []
    required_outputs = (
        payload.get("required_outputs") if isinstance(payload.get("required_outputs"), list) else []
    )
    handoff_chain = payload.get("handoff_chain") if isinstance(payload.get("handoff_chain"), dict) else {}
    acceptance_tests = (
        payload.get("acceptance_tests") if isinstance(payload.get("acceptance_tests"), list) else []
    )

    roles_raw = handoff_chain.get("roles") if isinstance(handoff_chain.get("roles"), list) else []
    handoff_roles = {
        str(role).strip().upper()
        for role in roles_raw
        if isinstance(role, str) and role.strip()
    }

    spec_ok = bool(spec.strip())
    plan_ok = False
    for item in required_outputs:
        if not isinstance(item, dict):
            continue
        if _contains_plan_marker(item.get("name")) or _contains_plan_marker(item.get("acceptance")):
            plan_ok = True
            break
    if not plan_ok:
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            if _contains_plan_marker(artifact.get("name")):
                plan_ok = True
                break

    subagent_ok = (
        bool(handoff_chain.get("enabled"))
        and "TECH_LEAD" in handoff_roles
        and "WORKER" in handoff_roles
        and int(handoff_chain.get("max_handoffs", 1) or 1) >= 1
    )
    review_ok = "REVIEWER" in handoff_roles

    non_trivial_tests = 0
    for case in acceptance_tests:
        if not isinstance(case, dict):
            continue
        if not case.get("must_pass"):
            continue
        command = _normalize_command(case.get("cmd"))
        if _is_trivial_acceptance_command(command):
            continue
        non_trivial_tests += 1
    test_ok = non_trivial_tests > 0 and ("TEST_RUNNER" in handoff_roles or "TEST" in handoff_roles)

    stages = {
        "spec": {"ok": spec_ok},
        "plan": {"ok": plan_ok},
        "subagent": {"ok": subagent_ok},
        "review": {"ok": review_ok},
        "test": {"ok": test_ok, "non_trivial_acceptance_tests": non_trivial_tests},
    }
    violations: list[dict[str, str]] = []
    if required:
        if not spec_ok:
            violations.append(
                {
                    "stage": "spec",
                    "code": "missing_spec",
                    "message": "inputs.spec must be non-empty",
                }
            )
        if not plan_ok:
            violations.append(
                {
                    "stage": "plan",
                    "code": "missing_plan_evidence",
                    "message": "required_outputs or inputs.artifacts must declare plan evidence",
                }
            )
        if not subagent_ok:
            violations.append(
                {
                    "stage": "subagent",
                    "code": "invalid_handoff_chain",
                    "message": "handoff_chain must enable TECH_LEAD->WORKER collaboration",
                }
            )
        if not review_ok:
            violations.append(
                {
                    "stage": "review",
                    "code": "missing_reviewer_stage",
                    "message": "handoff_chain.roles must include REVIEWER",
                }
            )
        if not test_ok:
            violations.append(
                {
                    "stage": "test",
                    "code": "missing_test_stage",
                    "message": "handoff_chain.roles must include TEST/TEST_RUNNER and acceptance_tests must be non-trivial",
                }
            )
    return {
        "required": required,
        "mode": "enforce" if required else "off",
        "ok": (not required) or (len(violations) == 0),
        "stages": stages,
        "violations": violations,
    }


class ContractValidator:
    def __init__(self, schema_root: Path | None = None) -> None:
        if schema_root is None:
            schema_root = Path(__file__).resolve().parents[5] / "schemas"
        self._schema_root = schema_root

    def _load_schema(self, schema_name: str) -> dict[str, Any]:
        schema_path = self._schema_root / schema_name
        if not schema_path.exists():
            fallback = _REPO_ROOT / "schemas" / schema_name
            if fallback.exists():
                schema_path = fallback
            else:
                raise FileNotFoundError(f"Schema not found: {schema_path}")
        return json.loads(schema_path.read_text(encoding="utf-8"))

    def _validate(self, payload: dict[str, Any], schema_name: str) -> dict[str, Any]:
        schema = self._load_schema(schema_name)
        validator = Draft202012Validator(schema)
        try:
            validator.validate(payload)
        except ValidationError as exc:
            detail = f"{exc.message} (path={list(exc.path)})"
            raise ValueError(f"Schema validation failed: {schema_name}: {detail}") from exc
        return payload

    def _enforce_contract_rules(self, payload: dict[str, Any]) -> None:
        allowed_paths = payload.get("allowed_paths", [])
        if not isinstance(allowed_paths, list) or len(allowed_paths) == 0:
            raise ValueError("Contract validation failed: allowed_paths is empty")
        invalid = find_invalid_allowed_paths(allowed_paths)
        if invalid:
            raise ValueError(
                "Contract validation failed: allowed_paths contains invalid entries"
            )
        rollback = payload.get("rollback", {})
        if isinstance(rollback, dict) and rollback.get("strategy") == "git_revert_commit":
            target_ref = rollback.get("target_ref")
            if target_ref is not None and (not isinstance(target_ref, str) or not target_ref.strip()):
                raise ValueError("Contract validation failed: rollback.target_ref invalid")
        policy_pack = payload.get("policy_pack")
        if policy_pack is not None:
            if not isinstance(policy_pack, str) or policy_pack.strip().lower() not in {"low", "medium", "high"}:
                raise ValueError("Contract validation failed: policy_pack invalid")
        mcp_tool_set = payload.get("mcp_tool_set")
        if not isinstance(mcp_tool_set, list) or not any(
            isinstance(item, str) and item.strip() for item in mcp_tool_set
        ):
            tool_permissions = payload.get("tool_permissions") if isinstance(payload.get("tool_permissions"), dict) else {}
            legacy_mcp_tools = tool_permissions.get("mcp_tools") if isinstance(tool_permissions.get("mcp_tools"), list) else []
            if not any(isinstance(item, str) and item.strip() for item in legacy_mcp_tools):
                raise ValueError("Contract validation failed: mcp_tool_set missing or empty")

        inputs = payload.get("inputs") if isinstance(payload.get("inputs"), dict) else {}
        artifacts = inputs.get("artifacts") if isinstance(inputs.get("artifacts"), list) else []
        assigned = payload.get("assigned_agent") if isinstance(payload.get("assigned_agent"), dict) else {}
        role = assigned.get("role") if isinstance(assigned.get("role"), str) else None
        artifact = _resolve_output_schema_artifact(artifacts, role)
        if artifact:
            expected_name = _output_schema_name_for_role(role)
            schema_path = _resolve_output_schema_path(
                artifact,
                self._schema_root,
                _REPO_ROOT,
                expected_name,
            )
            declared_sha = artifact.get("sha256")
            expected_sha = _schema_hash(schema_path)
            if declared_sha != expected_sha:
                raise ValueError("Contract validation failed: output_schema sha256 mismatch")
        registry = _load_agent_registry()
        _ensure_agent_in_registry(registry, payload.get("owner_agent"), "owner_agent")
        _ensure_agent_in_registry(registry, payload.get("assigned_agent"), "assigned_agent")
        _validate_role_contract(payload)

        superpowers_gate = evaluate_superpowers_gate(payload)
        if superpowers_gate.get("required") and not superpowers_gate.get("ok"):
            codes = ", ".join(
                str(item.get("code", "unknown"))
                for item in superpowers_gate.get("violations", [])
                if isinstance(item, dict)
            )
            raise ValueError(
                "Contract validation failed: superpowers gate violation"
                + (f" ({codes})" if codes else "")
            )

    def validate_contract(self, payload: dict[str, Any]) -> dict[str, Any]:
        payload = _normalize_contract_payload(payload)
        payload = self._validate(payload, "task_contract.v1.json")
        self._enforce_contract_rules(payload)
        return payload

    def validate_report(self, payload: dict[str, Any], schema_name: str) -> dict[str, Any]:
        return self._validate(payload, schema_name)

    def validate_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._validate(payload, "orchestrator_event.v1.json")

    def validate_contract_file(self, contract_path: Path) -> dict[str, Any]:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        return self.validate_contract(contract)

    def validate_report_file(self, report_path: Path, schema_name: str) -> dict[str, Any]:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        return self.validate_report(report, schema_name)


def validate_contract(contract_path: Path) -> dict[str, Any]:
    return ContractValidator().validate_contract_file(contract_path)


def validate_report(report_path: Path, schema_name: str) -> dict[str, Any]:
    return ContractValidator().validate_report_file(report_path, schema_name)


def hash_contract(contract: dict[str, Any]) -> str:
    payload = json.dumps(contract, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
