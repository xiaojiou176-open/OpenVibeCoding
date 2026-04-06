from __future__ import annotations

import re
from typing import Any


def _normalize_mcp_tool_set(tool_set: Any) -> list[str]:
    if not isinstance(tool_set, list):
        return []
    normalized: list[str] = []
    for item in tool_set:
        if not isinstance(item, str):
            continue
        value = item.strip()
        if value and value not in normalized:
            normalized.append(value)
    return normalized


def _tool_set_disabled(tool_set: list[str]) -> bool:
    if len(tool_set) != 1:
        return False
    value = tool_set[0].strip().lower()
    return value in {"none", "no-tools", "no_tools", "disabled"}


def _extract_mcp_server_names(config_text: str) -> list[str]:
    names: list[str] = []
    for raw in config_text.splitlines():
        line = raw.strip()
        if not (line.startswith("[") and line.endswith("]")):
            continue
        section = line[1:-1].strip()
        if not section.startswith("mcp_servers."):
            continue
        name = _section_mcp_server_name(section)
        if name and name not in names:
            names.append(name)
    return names


def _section_mcp_server_name(section: str) -> str | None:
    if not section.startswith("mcp_servers."):
        return None
    remainder = section[len("mcp_servers.") :]
    if not remainder:
        return None
    if remainder.startswith('"'):
        end = remainder.find('"', 1)
        if end <= 1:
            return None
        return remainder[1:end]
    for idx, ch in enumerate(remainder):
        if ch == ".":
            return remainder[:idx]
    return remainder


def _section_model_provider_name(section: str) -> str | None:
    if not section.startswith("model_providers."):
        return None
    remainder = section[len("model_providers.") :]
    if not remainder:
        return None
    if remainder.startswith('"'):
        end = remainder.find('"', 1)
        if end <= 1:
            return None
        return remainder[1:end]
    for idx, ch in enumerate(remainder):
        if ch == ".":
            return remainder[:idx]
    return remainder


def _resolve_model_provider(config_text: str) -> str | None:
    for raw in config_text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if not line.startswith("model_provider"):
            continue
        if "=" not in line:
            continue
        _, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        return value or None
    return None


def _override_model_provider_base_url(
    config_text: str,
    provider: str | None,
    base_url: str | None,
) -> str:
    if not provider or not base_url:
        return config_text
    lines = config_text.splitlines()
    output: list[str] = []
    in_section = False
    replaced = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_section and not replaced:
                output.append(f'base_url = "{base_url}"')
                replaced = True
            section_name = _section_model_provider_name(stripped[1:-1].strip())
            in_section = section_name == provider
            output.append(line)
            continue
        if in_section and stripped.startswith("base_url") and "=" in stripped:
            output.append(f'base_url = "{base_url}"')
            replaced = True
            continue
        output.append(line)
    if in_section and not replaced:
        output.append(f'base_url = "{base_url}"')
    return "\n".join(output) + "\n"


def _override_model_provider_api_key(
    config_text: str,
    provider: str | None,
    api_key: str | None,
) -> str:
    if not provider or not api_key:
        return config_text
    lines = config_text.splitlines()
    output: list[str] = []
    in_section = False
    replaced = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_section and not replaced:
                output.append(f'experimental_bearer_token = "{api_key}"')
                replaced = True
            section_name = _section_model_provider_name(stripped[1:-1].strip())
            in_section = section_name == provider
            output.append(line)
            continue
        if in_section and (
            stripped.startswith("experimental_bearer_token") or stripped.startswith("api_key")
        ) and "=" in stripped:
            output.append(f'experimental_bearer_token = "{api_key}"')
            replaced = True
            continue
        output.append(line)
    if in_section and not replaced:
        output.append(f'experimental_bearer_token = "{api_key}"')
    return "\n".join(output) + "\n"


def _strip_model_provider_secret_fields(config_text: str) -> str:
    return _strip_toml_keys(
        config_text,
        {
            "experimental_bearer_token",
            "api_key",
            "env_key",
            "password",
            "secret",
            "access_token",
            "refresh_token",
            "token",
            "bearer_token",
        },
    )


def assert_model_provider_secret_fields_removed(config_text: str) -> None:
    forbidden_patterns = (
        re.compile(r"^[ \t]*experimental_bearer_token[ \t]*=", re.M),
        re.compile(r"^[ \t]*api_key[ \t]*=", re.M),
        re.compile(r"^[ \t]*env_key[ \t]*=", re.M),
    )
    if any(pattern.search(config_text) for pattern in forbidden_patterns):
        raise ValueError("model provider secret fields remained after config sanitization")


def _filter_mcp_config(config_text: str, allowed: set[str], include_non_mcp: bool = True) -> str:
    output: list[str] = []
    keep = include_non_mcp
    for raw in config_text.splitlines():
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            if section.startswith("mcp_servers."):
                name = _section_mcp_server_name(section)
                keep = bool(name and name in allowed)
            else:
                keep = include_non_mcp
        if keep:
            output.append(raw)
    return "\n".join(output) + "\n"


def _strip_mcp_sections(config_text: str) -> str:
    return _filter_mcp_config(config_text, set(), include_non_mcp=True)


def _strip_toml_sections_with_prefix(config_text: str, prefixes: set[str]) -> str:
    if not prefixes:
        return config_text
    output: list[str] = []
    skip = False
    for raw in config_text.splitlines():
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            skip = any(section == prefix or section.startswith(f"{prefix}.") for prefix in prefixes)
            if skip:
                continue
        if skip:
            continue
        output.append(raw)
    return "\n".join(output) + "\n"


def _strip_toml_keys(config_text: str, keys: set[str]) -> str:
    if not keys:
        return config_text
    patterns = [re.compile(rf"^[ \t]*{re.escape(key)}[ \t]*=") for key in keys]
    output: list[str] = []
    skip_block = False
    end_token: str | None = None
    for raw in config_text.splitlines():
        if skip_block:
            if end_token and end_token in raw:
                skip_block = False
                end_token = None
            continue
        if any(pattern.match(raw) for pattern in patterns):
            if '"""' in raw or "'''" in raw:
                token = '"""' if '"""' in raw else "'''"
                if raw.count(token) < 2:
                    skip_block = True
                    end_token = token
            continue
        output.append(raw)
    return "\n".join(output) + "\n"
