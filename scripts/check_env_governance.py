#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


REQUIRED_REGISTRY_FIELDS = (
    "name",
    "scope",
    "secret",
    "required",
    "default",
    "owner",
    "description",
    "consumers",
)

SCAN_ROOTS = (
    "apps/orchestrator/src/openvibecoding_orch",
    "apps/dashboard",
    "apps/desktop",
    "scripts",
    "tools",
    "packages",
)

SCAN_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".mjs",
    ".cjs",
    ".sh",
    ".bash",
    ".zsh",
    ".md",
}

EXCLUDED_PARTS = {
    "node_modules",
    ".next",
    ".runtime-cache",
    ".git",
    ".venv",
    "dist",
    "build",
    "coverage",
    "target",
}

ENV_KEY_ALLOW_PATTERN = re.compile(
    r"^(OPENVIBECODING_|OPENAI_|NEXT_PUBLIC_|VITE_|GEMINI_|DASHBOARD_VITEST_|DESKTOP_VITEST_|VITEST_|CI$|NODE_ENV$)"
)

ENV_CAPTURE_PATTERNS = (
    re.compile(r"os\.getenv\(\s*[\"']([A-Z0-9_]+)[\"']"),
    re.compile(r"os\.environ\.get\(\s*[\"']([A-Z0-9_]+)[\"']"),
    re.compile(r"os\.environ\[\s*[\"']([A-Z0-9_]+)[\"']\s*\]\s*="),
    re.compile(r"os\.environ\.setdefault\(\s*[\"']([A-Z0-9_]+)[\"']"),
    re.compile(r"os\.environ\.pop\(\s*[\"']([A-Z0-9_]+)[\"']"),
    re.compile(r"process\.env\.([A-Z0-9_]+)"),
    re.compile(r"import\.meta\.env\.([A-Z0-9_]+)"),
    re.compile(r"\$\{([A-Z][A-Z0-9_]+)(?::[-=?][^}]*)?\}"),
)

BACKEND_DIRECT_READ_SCAN_ROOTS = (
    "apps/orchestrator/src/openvibecoding_orch",
    "tools",
)

BACKEND_DIRECT_READ_SCAN_SUFFIXES = {".py"}

DIRECT_ENV_READ_PATTERNS = (
    ("os.getenv", re.compile(r"os\.getenv\(\s*(?P<arg>[^),]+)")),
    ("os.environ.get", re.compile(r"os\.environ\.get\(\s*(?P<arg>[^),]+)")),
    ("os.environ[]", re.compile(r"os\.environ\s*\[\s*(?P<arg>[^\]]+)\]")),
)
DIRECT_ENV_LITERAL_ARG_PATTERN = re.compile(r"""^["']([A-Z0-9_]+)["']$""")
DIRECT_READ_ALLOWLIST_PATH = "configs/env_direct_read_allowlist.json"
ENV_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")

REGISTRY_DESCRIPTION_EXACT_BLOCKLIST = {
    "Auto-discovered from source usage; document precise semantics before changing.",
}
REGISTRY_DESCRIPTION_PATTERN_BLOCKLIST = (
    re.compile(r"\bauto[- ]?discovered\b", re.IGNORECASE),
    re.compile(r"\bdocument precise semantics\b", re.IGNORECASE),
    re.compile(r"^\s*(todo|tbd|placeholder|n/?a|null|none)\s*$", re.IGNORECASE),
)

GITIGNORE_REQUIRED_LINES = (
    ".env.local",
    "**/.env.local",
    "**/.env.*.local",
)

LEGACY_LLM_KEYS = (
    "OPENAI_API_KEY",
    "OPENVIBECODING_EQUILIBRIUM_API_KEY",
)

ALLOWED_TIERS = {"core", "profile", "advanced", "deprecated"}
REQUIRED_TIERS = {"core", "profile", "advanced", "deprecated"}


@dataclass
class Issue:
    code: str
    message: str


@dataclass
class DirectEnvRead:
    path: str
    line: int
    key: str | None
    source: str


@dataclass
class EnvHelperSpec:
    name: str
    positional_params: tuple[str, ...]
    key_params: set[str]
    vararg_name: str | None


def _load_registry(registry_path: Path) -> list[dict]:
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        maybe_items = payload.get("variables")
        if isinstance(maybe_items, list):
            return maybe_items
    raise ValueError("registry payload must be a list or {'variables': [...]} object")


def _load_tiers_config(tiers_path: Path) -> dict:
    payload = json.loads(tiers_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("tiers config payload must be an object")
    return payload


def _resolve_tier(name: str, prefix_rules: list[dict], overrides: dict[str, str], default_tier: str | None) -> str | None:
    override = overrides.get(name)
    if override:
        return override
    for rule in prefix_rules:
        prefix = str(rule.get("prefix", ""))
        tier = str(rule.get("tier", ""))
        if not prefix or not tier:
            continue
        exact = bool(rule.get("exact", False))
        if (exact and name == prefix) or (not exact and name.startswith(prefix)):
            return tier
    return default_tier


def _iter_scan_files(root: Path):
    for relative in SCAN_ROOTS:
        base = root / relative
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(root)
            if any(part in EXCLUDED_PARTS for part in rel.parts):
                continue
            if path.suffix.lower() not in SCAN_SUFFIXES:
                continue
            yield path


def _collect_source_keys(root: Path) -> dict[str, set[str]]:
    refs: dict[str, set[str]] = {}
    for path in _iter_scan_files(root):
        text = path.read_text(encoding="utf-8", errors="ignore")
        rel = str(path.relative_to(root))
        for pattern in ENV_CAPTURE_PATTERNS:
            for match in pattern.finditer(text):
                key = match.group(1)
                if not ENV_KEY_ALLOW_PATTERN.match(key):
                    continue
                refs.setdefault(key, set()).add(rel)
    return refs


def _check_registry_shape(entries: list[dict]) -> list[Issue]:
    issues: list[Issue] = []
    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            issues.append(Issue("registry.invalid_entry", f"Entry #{idx} is not an object"))
            continue
        missing = [field for field in REQUIRED_REGISTRY_FIELDS if field not in entry]
        if missing:
            issues.append(
                Issue("registry.missing_fields", f"Entry #{idx} missing fields: {', '.join(missing)}")
            )
            continue
        name = str(entry.get("name") or "")
        if not name:
            issues.append(Issue("registry.invalid_name", f"Entry #{idx} has empty name"))
        consumers = entry.get("consumers")
        if not isinstance(consumers, list):
            issues.append(Issue("registry.invalid_consumers", f"{name or f'Entry #{idx}'} consumers must be a list"))
    return issues


def _is_registry_description_quality_fail(description: str) -> bool:
    normalized = " ".join(description.split())
    if not normalized:
        return True
    if normalized in REGISTRY_DESCRIPTION_EXACT_BLOCKLIST:
        return True
    for pattern in REGISTRY_DESCRIPTION_PATTERN_BLOCKLIST:
        if pattern.search(normalized):
            return True
    return False


def _check_registry_description_quality(entries: list[dict]) -> list[Issue]:
    issues: list[Issue] = []
    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or f"Entry #{idx}")
        description = str(entry.get("description") or "")
        if _is_registry_description_quality_fail(description):
            issues.append(
                Issue(
                    "registry.invalid_description",
                    f"{name} has low-quality description; provide concrete operational semantics",
                )
            )
    return issues


def _check_secret_prefix_guard(entries: list[dict]) -> list[Issue]:
    issues: list[Issue] = []
    for entry in entries:
        name = str(entry.get("name") or "")
        is_secret = bool(entry.get("secret"))
        if is_secret and name.startswith(("NEXT_PUBLIC_", "VITE_")):
            issues.append(
                Issue(
                    "registry.public_secret_conflict",
                    f"{name} is marked secret but uses public frontend prefix",
                )
            )
    return issues


def _check_legacy_llm_key_contract(entries: list[dict]) -> list[Issue]:
    issues: list[Issue] = []
    indexed = {str(entry.get("name") or ""): entry for entry in entries if isinstance(entry, dict)}
    for name in LEGACY_LLM_KEYS:
        entry = indexed.get(name)
        if entry is None:
            continue
        if bool(entry.get("required")):
            issues.append(
                Issue(
                    "registry.legacy_llm_key_required_forbidden",
                    f"{name} must remain optional (required=false) in gemini-only mode",
                )
            )
        if entry.get("default") is not None:
            issues.append(
                Issue(
                    "registry.legacy_llm_key_default_forbidden",
                    f"{name} must keep default=null in gemini-only mode",
                )
            )
    return issues


def _check_registry_coverage(entries: list[dict], refs: dict[str, set[str]]) -> list[Issue]:
    issues: list[Issue] = []
    names = {str(entry.get("name") or "") for entry in entries}
    names.discard("")
    missing = sorted(set(refs) - names)
    for key in missing:
        issues.append(
            Issue(
                "registry.missing_key",
                f"{key} is used but not registered (consumers: {', '.join(sorted(refs[key]))})",
            )
        )
    return issues


def _load_direct_read_allowlist(allowlist_path: Path) -> dict[str, set[str]]:
    payload = json.loads(allowlist_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("allowlist payload must be an object")
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise ValueError("allowlist payload must include a list field 'entries'")

    allowlist: dict[str, set[str]] = {}
    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"allowlist entry #{idx} must be an object")
        raw_path = str(entry.get("path") or "").strip().replace("\\", "/")
        if not raw_path:
            raise ValueError(f"allowlist entry #{idx} missing path")
        if raw_path.startswith("/"):
            raise ValueError(f"allowlist entry #{idx} path must be repo-relative: {raw_path}")
        keys = entry.get("keys")
        if not isinstance(keys, list) or not keys:
            raise ValueError(f"allowlist entry #{idx} keys must be a non-empty list")
        normalized_keys: set[str] = set()
        for key in keys:
            key_text = str(key).strip()
            if key_text == "*":
                normalized_keys.add(key_text)
                continue
            if not ENV_KEY_PATTERN.match(key_text):
                raise ValueError(f"allowlist entry #{idx} has invalid key '{key_text}'")
            normalized_keys.add(key_text)
        allowlist[raw_path] = normalized_keys
    return allowlist


def _ast_attr_chain(node: ast.AST) -> str:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return ".".join(reversed(parts))


def _collect_ast_string_constants(tree: ast.AST) -> tuple[dict[str, str], dict[str, tuple[str, ...]]]:
    const_strings: dict[str, str] = {}
    const_sequences: dict[str, tuple[str, ...]] = {}

    def _collect_assignment(name: str, value: ast.AST | None) -> None:
        if value is None:
            return
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            const_strings[name] = value.value
            return
        if isinstance(value, (ast.Tuple, ast.List)):
            items: list[str] = []
            for item in value.elts:
                if not (isinstance(item, ast.Constant) and isinstance(item.value, str)):
                    return
                items.append(item.value)
            const_sequences[name] = tuple(items)

    for node in getattr(tree, "body", []):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            _collect_assignment(node.targets[0].id, node.value)
            continue
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            _collect_assignment(node.target.id, node.value)
    return const_strings, const_sequences


def _resolve_ast_env_keys(
    expr: ast.AST | None,
    const_strings: dict[str, str],
    const_sequences: dict[str, tuple[str, ...]],
) -> list[str]:
    if expr is None:
        return []
    if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
        return [expr.value] if ENV_KEY_PATTERN.match(expr.value) else []
    if isinstance(expr, ast.Name):
        if expr.id in const_strings:
            value = const_strings[expr.id]
            return [value] if ENV_KEY_PATTERN.match(value) else []
        if expr.id in const_sequences:
            return [item for item in const_sequences[expr.id] if ENV_KEY_PATTERN.match(item)]
        return []
    if isinstance(expr, ast.Starred):
        return _resolve_ast_env_keys(expr.value, const_strings, const_sequences)
    if isinstance(expr, (ast.Tuple, ast.List)):
        keys: list[str] = []
        for item in expr.elts:
            keys.extend(_resolve_ast_env_keys(item, const_strings, const_sequences))
        return keys
    return []


def _iter_direct_env_call_sites(node: ast.AST):
    if isinstance(node, ast.Call):
        chain = _ast_attr_chain(node.func)
        if chain in {"os.getenv", "os.environ.get"}:
            key_expr = node.args[0] if node.args else None
            yield chain, key_expr, node.lineno
    if isinstance(node, ast.Subscript):
        if _ast_attr_chain(node.value) == "os.environ":
            yield "os.environ[]", node.slice, node.lineno


def _collect_env_helper_specs(tree: ast.AST) -> dict[str, EnvHelperSpec]:
    specs: dict[str, EnvHelperSpec] = {}
    for node in getattr(tree, "body", []):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        positional_params = tuple(arg.arg for arg in node.args.args)
        all_params = {arg.arg for arg in node.args.args}
        all_params.update(arg.arg for arg in node.args.kwonlyargs)
        if node.args.vararg is not None:
            all_params.add(node.args.vararg.arg)
        loop_alias_to_param: dict[str, str] = {}
        for inner in ast.walk(node):
            if (
                isinstance(inner, ast.For)
                and isinstance(inner.target, ast.Name)
                and isinstance(inner.iter, ast.Name)
                and inner.iter.id in all_params
            ):
                loop_alias_to_param[inner.target.id] = inner.iter.id
        key_params: set[str] = set()
        for inner in ast.walk(node):
            for _, key_expr, _ in _iter_direct_env_call_sites(inner):
                if not isinstance(key_expr, ast.Name):
                    continue
                if key_expr.id in all_params:
                    key_params.add(key_expr.id)
                    continue
                mapped = loop_alias_to_param.get(key_expr.id)
                if mapped:
                    key_params.add(mapped)
        if key_params:
            specs[node.name] = EnvHelperSpec(
                name=node.name,
                positional_params=positional_params,
                key_params=key_params,
                vararg_name=node.args.vararg.arg if node.args.vararg is not None else None,
            )
    return specs


def _collect_backend_direct_reads_ast(path: Path, rel: str) -> list[DirectEnvRead]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []

    const_strings, const_sequences = _collect_ast_string_constants(tree)
    helper_specs = _collect_env_helper_specs(tree)
    reads: list[DirectEnvRead] = []
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    def _enclosing_function_name(node: ast.AST) -> str | None:
        cursor: ast.AST | None = node
        while cursor is not None:
            if isinstance(cursor, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return cursor.name
            cursor = parents.get(cursor)
        return None

    for node in ast.walk(tree):
        for source_name, key_expr, line_no in _iter_direct_env_call_sites(node):
            if isinstance(key_expr, ast.Name):
                function_name = _enclosing_function_name(node)
                spec = helper_specs.get(function_name or "")
                if spec is not None and key_expr.id in spec.key_params:
                    continue
            keys = _resolve_ast_env_keys(key_expr, const_strings, const_sequences)
            if keys:
                for key in sorted(set(keys)):
                    reads.append(DirectEnvRead(path=rel, line=line_no, key=key, source=source_name))
            else:
                reads.append(DirectEnvRead(path=rel, line=line_no, key=None, source=source_name))

        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name):
            continue
        spec = helper_specs.get(node.func.id)
        if spec is None:
            continue
        helper_keys: set[str] = set()
        saw_dynamic = False
        for index, arg_expr in enumerate(node.args):
            param_name: str | None = None
            if index < len(spec.positional_params):
                param_name = spec.positional_params[index]
            elif spec.vararg_name is not None:
                param_name = spec.vararg_name
            if param_name not in spec.key_params:
                continue
            resolved = _resolve_ast_env_keys(arg_expr, const_strings, const_sequences)
            if resolved:
                helper_keys.update(resolved)
            else:
                saw_dynamic = True
        for keyword in node.keywords:
            if keyword.arg not in spec.key_params:
                continue
            resolved = _resolve_ast_env_keys(keyword.value, const_strings, const_sequences)
            if resolved:
                helper_keys.update(resolved)
            else:
                saw_dynamic = True
        if helper_keys:
            for key in sorted(helper_keys):
                reads.append(
                    DirectEnvRead(
                        path=rel,
                        line=node.lineno,
                        key=key,
                        source=f"helper:{spec.name}",
                    )
                )
        if saw_dynamic:
            reads.append(
                DirectEnvRead(
                    path=rel,
                    line=node.lineno,
                    key=None,
                    source=f"helper:{spec.name}",
                )
            )
    return reads


def _iter_backend_direct_read_files(root: Path):
    for relative in BACKEND_DIRECT_READ_SCAN_ROOTS:
        base = root / relative
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(root)
            if any(part in EXCLUDED_PARTS for part in rel.parts):
                continue
            if path.suffix.lower() not in BACKEND_DIRECT_READ_SCAN_SUFFIXES:
                continue
            yield path


def _collect_backend_direct_reads(root: Path) -> dict[str, list[DirectEnvRead]]:
    reads: dict[str, list[DirectEnvRead]] = {}
    for path in _iter_backend_direct_read_files(root):
        rel = str(path.relative_to(root)).replace("\\", "/")
        file_reads = _collect_backend_direct_reads_ast(path, rel)
        if file_reads:
            reads[rel] = file_reads
            continue

        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line_no, line in enumerate(lines, start=1):
            for source_name, pattern in DIRECT_ENV_READ_PATTERNS:
                for match in pattern.finditer(line):
                    raw_arg = match.group("arg").strip()
                    literal_match = DIRECT_ENV_LITERAL_ARG_PATTERN.match(raw_arg)
                    key = literal_match.group(1) if literal_match else None
                    reads.setdefault(rel, []).append(
                        DirectEnvRead(path=rel, line=line_no, key=key, source=source_name)
                    )
    return reads


def _check_backend_direct_reads(root: Path, allowlist: dict[str, set[str]]) -> list[Issue]:
    issues: list[Issue] = []
    reads_by_file = _collect_backend_direct_reads(root)

    for rel, reads in reads_by_file.items():
        allowed_keys = allowlist.get(rel)
        if allowed_keys is None:
            issues.append(
                Issue(
                    "guard.direct_env_read_unallowlisted_file",
                    f"{rel} contains direct env reads but is not present in {DIRECT_READ_ALLOWLIST_PATH}",
                )
            )
            continue
        wildcard_allowed = "*" in allowed_keys
        for read in reads:
            if read.key is None:
                if not wildcard_allowed:
                    issues.append(
                        Issue(
                            "guard.direct_env_read_dynamic",
                            f"{rel}:{read.line} uses dynamic {read.source}; allowlist this file with '*' or refactor to config access",
                        )
                    )
                continue
            if not wildcard_allowed and read.key not in allowed_keys:
                issues.append(
                    Issue(
                        "guard.direct_env_read_key_not_allowlisted",
                        f"{rel}:{read.line} reads {read.key} via {read.source} but key is not allowlisted",
                    )
                )

    for rel, keys in sorted(allowlist.items()):
        path = root / rel
        if not path.exists():
            issues.append(
                Issue(
                    "guard.allowlist_path_missing",
                    f"{DIRECT_READ_ALLOWLIST_PATH} includes missing path: {rel}",
                )
            )
            continue
        if not keys:
            issues.append(
                Issue(
                    "guard.allowlist_empty_keys",
                    f"{DIRECT_READ_ALLOWLIST_PATH} entry for {rel} must include at least one key",
                )
            )
        if "*" in keys:
            issues.append(
                Issue(
                    "guard.allowlist_wildcard_forbidden",
                    f"{DIRECT_READ_ALLOWLIST_PATH} entry for {rel} must not use wildcard '*'; enumerate keys explicitly",
                )
            )
    return issues


def _check_env_template_files(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    required = (
        root / ".env.example",
        root / "apps/orchestrator/.env.example",
    )
    for path in required:
        if not path.exists():
            issues.append(Issue("template.missing", f"Missing env template: {path.relative_to(root)}"))
    return issues


def _check_gitignore_lines(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    gitignore = root / ".gitignore"
    if not gitignore.exists():
        return [Issue("gitignore.missing", ".gitignore not found")]
    lines = {line.strip() for line in gitignore.read_text(encoding="utf-8").splitlines()}
    for expected in GITIGNORE_REQUIRED_LINES:
        if expected not in lines:
            issues.append(Issue("gitignore.missing_rule", f".gitignore missing rule: {expected}"))
    return issues


def _check_tiers_contract(
    entries: list[dict],
    tiers_cfg: dict,
    *,
    max_deprecated_count: int,
    max_deprecated_ratio: float,
) -> tuple[list[Issue], dict[str, float | int]]:
    issues: list[Issue] = []
    prefix_rules = tiers_cfg.get("prefix_rules", [])
    overrides = tiers_cfg.get("overrides", {})
    default_tier = tiers_cfg.get("default_tier")
    declared_tiers = tiers_cfg.get("tiers", [])

    if not isinstance(prefix_rules, list):
        issues.append(Issue("tier.invalid_prefix_rules", "env_tiers.prefix_rules must be a list"))
        prefix_rules = []
    if not isinstance(overrides, dict):
        issues.append(Issue("tier.invalid_overrides", "env_tiers.overrides must be an object"))
        overrides = {}
    if not isinstance(declared_tiers, list) or not all(isinstance(x, str) for x in declared_tiers):
        issues.append(Issue("tier.invalid_declared_tiers", "env_tiers.tiers must be a string array"))
        declared_tiers = []

    declared_set = set(declared_tiers)
    illegal_declared = sorted(declared_set - ALLOWED_TIERS)
    missing_required = sorted(REQUIRED_TIERS - declared_set)
    if illegal_declared:
        issues.append(Issue("tier.illegal_declared", f"env_tiers.tiers contains illegal values: {', '.join(illegal_declared)}"))
    if missing_required:
        issues.append(Issue("tier.missing_required", f"env_tiers.tiers missing required values: {', '.join(missing_required)}"))
    if default_tier is not None and default_tier not in ALLOWED_TIERS:
        issues.append(Issue("tier.invalid_default", f"env_tiers.default_tier is illegal: {default_tier}"))

    for idx, rule in enumerate(prefix_rules):
        if not isinstance(rule, dict):
            issues.append(Issue("tier.invalid_prefix_rule", f"env_tiers.prefix_rules[{idx}] must be an object"))
            continue
        prefix = str(rule.get("prefix") or "")
        tier = str(rule.get("tier") or "")
        if not prefix:
            issues.append(Issue("tier.empty_prefix", f"env_tiers.prefix_rules[{idx}].prefix must be non-empty"))
        if tier not in ALLOWED_TIERS:
            issues.append(Issue("tier.illegal_prefix_tier", f"env_tiers.prefix_rules[{idx}].tier is illegal: {tier}"))

    for key, tier in overrides.items():
        if not isinstance(key, str) or not key:
            issues.append(Issue("tier.invalid_override_key", "env_tiers.overrides contains empty/non-string key"))
            continue
        if str(tier) not in ALLOWED_TIERS:
            issues.append(Issue("tier.illegal_override_tier", f"env_tiers.overrides[{key}] is illegal: {tier}"))

    resolved_counter: Counter[str] = Counter()
    unresolved_total = 0
    illegal_resolved_total = 0
    total_named = 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "")
        if not name:
            continue
        total_named += 1
        resolved = _resolve_tier(name, prefix_rules, overrides, default_tier)
        if resolved is None:
            unresolved_total += 1
            issues.append(Issue("tier.unresolved", f"{name} cannot resolve tier from env_tiers config"))
            continue
        if resolved not in ALLOWED_TIERS:
            illegal_resolved_total += 1
            issues.append(Issue("tier.resolved_illegal", f"{name} resolved to illegal tier: {resolved}"))
            continue
        resolved_counter[resolved] += 1

    deprecated_count = resolved_counter.get("deprecated", 0)
    deprecated_ratio = (deprecated_count / total_named) if total_named else 0.0
    if deprecated_count > max_deprecated_count:
        issues.append(
            Issue(
                "tier.deprecated_budget_exceeded",
                (
                    f"deprecated tier count {deprecated_count} exceeds budget {max_deprecated_count} "
                    f"(set --max-deprecated-count to adjust deliberately)"
                ),
            )
        )
    if deprecated_ratio > max_deprecated_ratio:
        issues.append(
            Issue(
                "tier.deprecated_ratio_exceeded",
                (
                    f"deprecated tier ratio {deprecated_ratio:.6f} exceeds budget {max_deprecated_ratio:.6f} "
                    f"(set --max-deprecated-ratio to adjust deliberately)"
                ),
            )
        )

    return issues, {
        "registry_total": total_named,
        "deprecated_count": deprecated_count,
        "deprecated_ratio": round(deprecated_ratio, 6),
        "resolved_total": sum(resolved_counter.values()),
        "unresolved_total": unresolved_total,
        "illegal_resolved_total": illegal_resolved_total,
        "max_deprecated_count": max_deprecated_count,
        "max_deprecated_ratio": max_deprecated_ratio,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="OpenVibeCoding env governance checker")
    parser.add_argument("--mode", choices=("warn", "gate"), default="gate")
    parser.add_argument(
        "--max-deprecated-count",
        type=int,
        default=10,
        help="Max allowed deprecated-tier env key count before gate fails",
    )
    parser.add_argument(
        "--max-deprecated-ratio",
        type=float,
        default=0.03,
        help="Max allowed deprecated-tier env key ratio before gate fails",
    )
    args = parser.parse_args()
    if args.max_deprecated_count < 0:
        print("[FAIL] --max-deprecated-count must be >= 0")
        return 1
    if args.max_deprecated_ratio < 0 or args.max_deprecated_ratio > 1:
        print("[FAIL] --max-deprecated-ratio must be within [0, 1]")
        return 1

    root = Path(__file__).resolve().parents[1]
    registry_path = root / "configs/env.registry.json"
    tiers_path = root / "configs/env_tiers.json"
    direct_read_allowlist_path = root / DIRECT_READ_ALLOWLIST_PATH
    issues: list[Issue] = []
    tier_audit: dict[str, float | int] = {
        "registry_total": 0,
        "deprecated_count": 0,
        "deprecated_ratio": 0.0,
        "resolved_total": 0,
        "unresolved_total": 0,
        "illegal_resolved_total": 0,
        "max_deprecated_count": args.max_deprecated_count,
        "max_deprecated_ratio": args.max_deprecated_ratio,
    }

    if not registry_path.exists():
        issues.append(Issue("registry.missing", "configs/env.registry.json does not exist"))
        entries = []
    else:
        try:
            entries = _load_registry(registry_path)
        except Exception as exc:  # noqa: BLE001
            issues.append(Issue("registry.invalid_json", f"Failed to parse registry: {exc}"))
            entries = []
        issues.extend(_check_registry_shape(entries))
        issues.extend(_check_registry_description_quality(entries))
        issues.extend(_check_secret_prefix_guard(entries))
        issues.extend(_check_legacy_llm_key_contract(entries))
        refs = _collect_source_keys(root)
        issues.extend(_check_registry_coverage(entries, refs))

    if not tiers_path.exists():
        issues.append(Issue("tier.config_missing", "configs/env_tiers.json does not exist"))
    else:
        try:
            tiers_cfg = _load_tiers_config(tiers_path)
        except Exception as exc:  # noqa: BLE001
            issues.append(Issue("tier.invalid_json", f"Failed to parse tiers config: {exc}"))
            tiers_cfg = {}
        tier_issues, tier_audit = _check_tiers_contract(
            entries,
            tiers_cfg,
            max_deprecated_count=args.max_deprecated_count,
            max_deprecated_ratio=args.max_deprecated_ratio,
        )
        issues.extend(tier_issues)

    if not direct_read_allowlist_path.exists():
        issues.append(
            Issue(
                "guard.allowlist_missing",
                f"{DIRECT_READ_ALLOWLIST_PATH} does not exist",
            )
        )
    else:
        try:
            direct_read_allowlist = _load_direct_read_allowlist(direct_read_allowlist_path)
        except Exception as exc:  # noqa: BLE001
            issues.append(
                Issue(
                    "guard.allowlist_invalid",
                    f"Failed to parse {DIRECT_READ_ALLOWLIST_PATH}: {exc}",
                )
            )
            direct_read_allowlist = {}
        issues.extend(_check_backend_direct_reads(root, direct_read_allowlist))

    issues.extend(_check_env_template_files(root))
    issues.extend(_check_gitignore_lines(root))
    print(
        "[INFO] env governance summary: "
        f"registry_total={tier_audit['registry_total']}, "
        f"resolved_total={tier_audit['resolved_total']}, "
        f"unresolved_total={tier_audit['unresolved_total']}, "
        f"illegal_resolved_total={tier_audit['illegal_resolved_total']}, "
        f"deprecated_count={tier_audit['deprecated_count']}, "
        f"deprecated_ratio={float(tier_audit['deprecated_ratio']):.6f}, "
        f"max_deprecated_count={tier_audit['max_deprecated_count']}, "
        f"max_deprecated_ratio={float(tier_audit['max_deprecated_ratio']):.6f}"
    )

    if issues:
        header = "WARN" if args.mode == "warn" else "FAIL"
        print(f"[{header}] env governance issues: {len(issues)}")
        for issue in issues:
            print(f"- [{issue.code}] {issue.message}")
        if args.mode == "gate":
            return 1
        return 0

    print("[PASS] env governance checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
