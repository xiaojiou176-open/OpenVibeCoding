from __future__ import annotations

import json
import logging
import os
import shutil
import tomllib
from pathlib import Path
from typing import Any, Callable

from openvibecoding_orch.runners import agents_mcp_config, agents_prompting, mcp_streaming as _mcp_streaming
from openvibecoding_orch.runners.provider_resolution import (
    ProviderResolutionError,
    resolve_preferred_api_key,
    resolve_provider_credentials,
    resolve_runtime_provider,
    resolve_runtime_provider_from_env,
)
from openvibecoding_orch.runners.agents_mcp_execution_helpers import run_worker_execution
from openvibecoding_orch.runners.agents_mcp_runtime_helpers import (
    MCPMessageArchive,
    bind_mcp_log_paths,
)
from openvibecoding_orch.store.run_store import RunStore


_logger = logging.getLogger(__name__)
mcp_streaming = _mcp_streaming
_PROVIDER_TO_MODEL_PROVIDER = {
    "gemini": "gemini",
    "google": "gemini",
    "google-genai": "gemini",
    "google_genai": "gemini",
    "openai": "openai",
    "anthropic": "anthropic",
    "claude": "anthropic",
    "anthropic-claude": "anthropic",
    "anthropic_claude": "anthropic",
    "equilibrium": "codex_equilibrium",
    "codex_equilibrium": "codex_equilibrium",
}
_WORKER_CONFIG_SECRET_PREFIXES = (
    "experimental_bearer_token",
    "api_key",
    "env_key",
    "password",
    "secret",
    "access_token",
    "refresh_token",
    "token",
    "bearer_token",
)


def _normalize_provider_name(provider: str) -> str:
    normalized = str(provider or "").strip().lower().replace("-", "_")
    if normalized == "google_genai":
        return "gemini"
    return normalized


def _resolve_preferred_api_key_for_provider(credentials: Any, provider: str) -> str:
    provider_name = str(provider or "").strip()
    try:
        candidate = resolve_preferred_api_key(credentials, provider_name)  # type: ignore[call-arg]
    except ProviderResolutionError:
        candidate = ""
    except (TypeError, AttributeError):
        candidate = resolve_preferred_api_key(credentials)
    except Exception as exc:  # noqa: BLE001
        _logger.debug("agents_mcp_runtime: resolve_preferred_api_key fallback: %s", exc)
        candidate = ""
    resolved = str(candidate or "").strip()
    if resolved:
        return resolved
    normalized = _normalize_provider_name(provider_name)
    for attr in (
        f"{normalized}_api_key",
        "gemini_api_key",
        "openai_api_key",
        "anthropic_api_key",
        "equilibrium_api_key",
    ):
        value = str(getattr(credentials, attr, "") or "").strip()
        if value:
            return value
    return ""


def _override_top_level_toml_key(config_text: str, key: str, value: str) -> str:
    if not value:
        return config_text
    lines = config_text.splitlines()
    output: list[str] = []
    replaced = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if not replaced:
                output.append(f'{key} = "{value}"')
                replaced = True
            output.append(line)
            continue
        if "=" in stripped and stripped.split("=", 1)[0].strip() == key:
            output.append(f'{key} = "{value}"')
            replaced = True
            continue
        output.append(line)
    if not replaced:
        output.append(f'{key} = "{value}"')
    return "\n".join(output) + "\n"


def _extract_model_provider_section(config_text: str, provider: str) -> str:
    if not provider:
        return ""
    target_headers = {
        f"model_providers.{provider}",
        f'model_providers."{provider}"',
    }
    lines = config_text.splitlines()
    collecting = False
    collected: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            header = stripped[1:-1].strip()
            if collecting:
                break
            if header in target_headers:
                collecting = True
        if collecting:
            collected.append(line)
    if not collected:
        return ""
    return "\n".join(collected).rstrip() + "\n"


def _looks_like_worker_config_secret_key(key: str) -> bool:
    return str(key).strip().lower().replace("-", "_") in _WORKER_CONFIG_SECRET_PREFIXES


def _format_toml_key(key: str) -> str:
    return key if key and all(ch.isalnum() or ch in {"_", "-"} for ch in key) else json.dumps(key, ensure_ascii=False)


def _format_toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ", ".join(_format_toml_value(item) for item in value) + "]"
    raise TypeError(f"unsupported TOML value type: {type(value).__name__}")


def _sanitize_worker_config_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        sanitized: dict[str, Any] = {}
        for key, value in payload.items():
            if _looks_like_worker_config_secret_key(str(key)):
                continue
            sanitized[str(key)] = _sanitize_worker_config_payload(value)
        return sanitized
    if isinstance(payload, list):
        return [_sanitize_worker_config_payload(item) for item in payload]
    return payload


def _dump_toml_table(payload: dict[str, Any], prefix: tuple[str, ...] = ()) -> list[str]:
    scalar_lines: list[str] = []
    child_blocks: list[list[str]] = []
    for key, value in payload.items():
        key_name = str(key)
        if isinstance(value, dict):
            child_blocks.append(_dump_toml_table(value, (*prefix, key_name)))
            continue
        scalar_lines.append(f"{_format_toml_key(key_name)} = {_format_toml_value(value)}")

    lines: list[str] = []
    if prefix:
        header = ".".join(_format_toml_key(part) for part in prefix)
        lines.append(f"[{header}]")
    lines.extend(scalar_lines)
    for block in child_blocks:
        if lines:
            lines.append("")
        lines.extend(block)
    return lines


def _build_write_safe_worker_config(config_text: str) -> str:
    stripped_config = agents_mcp_config._strip_model_provider_secret_fields(config_text)
    config_payload = tomllib.loads(stripped_config)
    safe_payload = _sanitize_worker_config_payload(config_payload)
    if not isinstance(safe_payload, dict):
        raise TypeError("worker config payload must be table-shaped")
    write_safe_config = "\n".join(_dump_toml_table(safe_payload)).rstrip() + "\n"
    agents_mcp_config.assert_model_provider_secret_fields_removed(write_safe_config)
    return write_safe_config


def runtime_root_from_store(store: RunStore) -> Path:
    fallback = store._runs_root.parent
    return Path(os.getenv("OPENVIBECODING_RUNTIME_ROOT", str(fallback)))


def fixed_output_cwd(store: RunStore) -> str:
    return str(runtime_root_from_store(store).resolve())


def resolve_mcp_server_names(tool_set: list[str], available: set[str]) -> tuple[list[str], list[str]]:
    resolved: list[str] = []
    missing: list[str] = []
    canonical_aliases = {
        "filesystem": ["devtools-04-filesystem", "vcs-01-filesystem", "01-filesystem"],
        "ripgrep": ["devtools-02-ripgrep", "ctx-short-02-ripgrep"],
        "github": ["devtools-05-github", "vcs-02-github-ro"],
        "playwright": ["browser-01-playwright", "browser-02-playwright"],
    }

    for raw_name in tool_set:
        name = raw_name.strip()
        if not name:
            continue

        candidates: list[str] = [name]
        lowered = name.lower()
        canonical_name = lowered
        if "-" in name:
            prefix, remainder = name.split("-", 1)
            if prefix.isdigit() and remainder:
                candidates.append(remainder)
                canonical_name = remainder.lower()
        if name.startswith("vcs-") and "-" in name[4:]:
            sub_prefix, sub_remainder = name[4:].split("-", 1)
            if sub_prefix.isdigit() and sub_remainder:
                candidates.append(sub_remainder)
        if lowered == "codex":
            candidates.extend(
                [
                    "vcs-01-filesystem",
                    "01-filesystem",
                    "devtools-04-filesystem",
                    "filesystem",
                ]
            )
        elif lowered == "search":
            candidates.extend(
                [
                    "ctx-short-02-ripgrep",
                    "ctx-short-03-pageindex",
                    "ctx-long-01-context7",
                    "ctx-long-02-openai-developer-docs",
                    "ctx-long-04-r2r-openai",
                    "ctx-long-05-r2r-openvibecoding",
                    "vcs-02-github-ro",
                ]
            )
        elif lowered == "browser":
            candidates.extend(
                ["browser-01-playwright", "browser-02-chrome-devtools", "browser-03-midscene"]
            )

        if name.startswith("vcs-"):
            candidates.append(name[len("vcs-") :])
        else:
            candidates.append(f"vcs-{name}")
        for alias in canonical_aliases.get(lowered, []):
            if alias not in candidates:
                candidates.append(alias)
        if canonical_name != lowered:
            for alias in canonical_aliases.get(canonical_name, []):
                if alias not in candidates:
                    candidates.append(alias)

        selected = next((candidate for candidate in candidates if candidate in available), None)
        if not selected:
            missing.append(name)
            continue
        if selected not in resolved:
            resolved.append(selected)

    return resolved, missing


def materialize_worker_codex_home(
    store: RunStore,
    run_id: str,
    task_id: str,
    tool_set: list[str],
    role: str | None,
    worktree_path: Path,
    skip_role_prompt: bool,
    *,
    resolve_codex_base_url: Callable[[], str] | None = None,
    runtime_provider: str | None = None,
) -> Path:
    role_home = os.getenv("CODEX_HOME", "").strip()
    if role_home:
        role_home = str(Path(role_home).expanduser())
    else:
        role_home = str(Path.home() / ".codex")
    role_home = Path(role_home)
    role_config_path = role_home / "config.toml"
    if not role_config_path.exists():
        raise RuntimeError(f"codex role config missing: {role_config_path}")

    catalog_home_raw = os.getenv("OPENVIBECODING_CODEX_BASE_HOME", "").strip()
    if catalog_home_raw:
        catalog_home = Path(Path(catalog_home_raw).expanduser())
    else:
        catalog_home = role_home

    def _load_catalog(path: Path) -> tuple[str, list[str], list[str]]:
        config_path = path / "config.toml"
        if not config_path.exists():
            raise RuntimeError(f"codex base config missing: {config_path}")
        text = config_path.read_text(encoding="utf-8")
        available_names = set(agents_mcp_config._extract_mcp_server_names(text))
        resolved_names, unresolved = resolve_mcp_server_names(tool_set, available_names)
        return text, resolved_names, unresolved

    role_text = role_config_path.read_text(encoding="utf-8")
    role_text = agents_mcp_config._strip_mcp_sections(role_text)
    role_text = agents_mcp_config._strip_toml_sections_with_prefix(role_text, {"agents"})

    catalog_text, resolved_tool_set, missing = _load_catalog(catalog_home)
    if missing and not catalog_home_raw:
        fallback_home = Path.home() / ".codex"
        if fallback_home != catalog_home:
            try:
                fallback_text, fallback_resolved_tool_set, fallback_missing = _load_catalog(fallback_home)
            except RuntimeError:
                fallback_missing = missing
            else:
                if not fallback_missing:
                    catalog_home = fallback_home
                    catalog_text = fallback_text
                    resolved_tool_set = fallback_resolved_tool_set
                    missing = []
                    store.append_event(
                        run_id,
                        {
                            "level": "INFO",
                            "event": "MCP_BASE_HOME_FALLBACK",
                            "run_id": run_id,
                            "meta": {
                                "task_id": task_id,
                                "from": str(role_home),
                                "to": str(fallback_home),
                            },
                        },
                    )

    if missing:
        raise RuntimeError("mcp_tool_set missing in base config " f"(set OPENVIBECODING_CODEX_BASE_HOME): {missing}")

    runtime_root = runtime_root_from_store(store)
    target = runtime_root / "codex-homes" / run_id / task_id
    target.mkdir(parents=True, exist_ok=True)

    filtered_mcp = agents_mcp_config._filter_mcp_config(catalog_text, set(resolved_tool_set), include_non_mcp=False)
    strip_keys = {"model_instructions_file", "developer_instructions"}
    if skip_role_prompt:
        strip_keys.update({"project_doc_fallback_filenames", "project_doc_max_bytes"})
    role_text = agents_mcp_config._strip_toml_keys(role_text, strip_keys)

    merged = role_text.rstrip()
    if filtered_mcp.strip():
        merged = f"{merged}\n\n{filtered_mcp.strip()}\n"
    else:
        merged = f"{merged}\n"

    role_prompt_path = agents_prompting.resolve_role_prompt_path(role or "WORKER", worktree_path)
    if role_prompt_path and not skip_role_prompt:
        role_prompt_path = role_prompt_path.resolve()
        merged = f"{merged.rstrip()}\nmodel_instructions_file = \"{role_prompt_path}\"\n"
    merged = f"{merged.rstrip()}\ndeveloper_instructions = \"\"\n"
    if skip_role_prompt:
        merged = f"{merged.rstrip()}\nproject_doc_fallback_filenames = []\nproject_doc_max_bytes = 0\n"
    try:
        if isinstance(runtime_provider, str) and runtime_provider.strip():
            runtime_provider = resolve_runtime_provider(runtime_provider)
        else:
            runtime_provider = resolve_runtime_provider_from_env()
    except ProviderResolutionError as exc:
        raise RuntimeError(str(exc)) from exc
    normalized_provider = _normalize_provider_name(runtime_provider)
    # For custom OpenAI-compatible providers, keep provider name as-is so worker
    # CODEX_HOME can materialize `model_provider=<custom>` plus matching section.
    target_model_provider = _PROVIDER_TO_MODEL_PROVIDER.get(normalized_provider, normalized_provider or "")
    if target_model_provider:
        merged = _override_top_level_toml_key(merged, "model_provider", target_model_provider)
        if not agents_mcp_config._resolve_model_provider(merged):
            provider_section = _extract_model_provider_section(catalog_text, target_model_provider)
            if provider_section:
                merged = f"{merged.rstrip()}\n\n{provider_section}"
        elif f"[model_providers.{target_model_provider}]" not in merged and (
            f'[model_providers."{target_model_provider}"]' not in merged
        ):
            provider_section = _extract_model_provider_section(catalog_text, target_model_provider)
            if provider_section:
                merged = f"{merged.rstrip()}\n\n{provider_section}"
    runtime_model = (
        os.getenv("OPENVIBECODING_CODEX_MODEL", "").strip()
        or os.getenv("OPENVIBECODING_PROVIDER_MODEL", "").strip()
    )
    if runtime_model:
        merged = _override_top_level_toml_key(merged, "model", runtime_model)
    if callable(resolve_codex_base_url):
        codex_base_url = resolve_codex_base_url()
        if codex_base_url:
            provider_name = agents_mcp_config._resolve_model_provider(merged)
            merged = agents_mcp_config._override_model_provider_base_url(merged, provider_name, codex_base_url)
    write_safe_config_toml = _build_write_safe_worker_config(merged)
    (target / "config.toml").write_text(write_safe_config_toml, encoding="utf-8")
    for name in ("requirements.toml",):
        src = role_home / name
        if src.exists():
            shutil.copy2(src, target / name)
    return target


def patch_mcp_codex_event_notifications() -> tuple[bool, str]:
    """Allow codex/event notifications to pass MCP validation."""
    try:
        import mcp.types as mcp_types
        from pydantic import RootModel
        from typing import Any, Literal
    except Exception as exc:  # noqa: BLE001
        return False, f"mcp import failed: {exc}"

    if getattr(mcp_types, "_OPENVIBECODING_CODEX_EVENT_PATCHED", False):
        return True, "already patched"

    try:
        mcp_types.ServerNotification.model_validate(
            {"jsonrpc": "2.0", "method": "codex/event", "params": {"msg": {}}}
        )
        mcp_types._OPENVIBECODING_CODEX_EVENT_PATCHED = True
        return True, "already supported"
    except Exception as exc:  # noqa: BLE001
        _logger.debug("agents_mcp_runtime: codex/event not natively supported, patching: %s", exc)

    class CodexEventNotification(
        mcp_types.Notification[dict[str, Any] | None, Literal["codex/event"]]
    ):
        method: Literal["codex/event"] = "codex/event"
        params: dict[str, Any] | None = None

    try:
        server_type = mcp_types.ServerNotificationType | CodexEventNotification

        class PatchedServerNotification(RootModel[server_type]):  # type: ignore[name-defined]
            pass

        mcp_types.ServerNotificationType = server_type
        mcp_types.ServerNotification = PatchedServerNotification
        mcp_types._OPENVIBECODING_CODEX_EVENT_PATCHED = True
        return True, "patched"
    except Exception as exc:  # noqa: BLE001
        return False, f"patch failed: {exc}"


def patch_mcp_initialized_notification() -> tuple[bool, str]:
    """Skip notifications/initialized for Codex MCP servers to avoid protocol warnings."""
    try:
        import mcp.client.session as mcp_session
        import mcp.types as mcp_types
        from mcp.shared.version import SUPPORTED_PROTOCOL_VERSIONS
    except Exception as exc:  # noqa: BLE001
        return False, f"mcp import failed: {exc}"

    if getattr(mcp_session, "_OPENVIBECODING_INITIALIZED_PATCHED", False):
        return True, "already patched"

    original_initialize = mcp_session.ClientSession.initialize

    async def _patched_initialize(self: Any) -> mcp_types.InitializeResult:
        sampling = (
            (self._sampling_capabilities or mcp_types.SamplingCapability())
            if self._sampling_callback is not mcp_session._default_sampling_callback
            else None
        )
        elicitation = (
            mcp_types.ElicitationCapability(
                form=mcp_types.FormElicitationCapability(),
                url=mcp_types.UrlElicitationCapability(),
            )
            if self._elicitation_callback is not mcp_session._default_elicitation_callback
            else None
        )
        roots = (
            mcp_types.RootsCapability(listChanged=True)
            if self._list_roots_callback is not mcp_session._default_list_roots_callback
            else None
        )

        result = await self.send_request(
            mcp_types.ClientRequest(
                mcp_types.InitializeRequest(
                    params=mcp_types.InitializeRequestParams(
                        protocolVersion=mcp_types.LATEST_PROTOCOL_VERSION,
                        capabilities=mcp_types.ClientCapabilities(
                            sampling=sampling,
                            elicitation=elicitation,
                            experimental=None,
                            roots=roots,
                            tasks=self._task_handlers.build_capability(),
                        ),
                        clientInfo=self._client_info,
                    ),
                )
            ),
            mcp_types.InitializeResult,
        )

        if result.protocolVersion not in SUPPORTED_PROTOCOL_VERSIONS:
            raise RuntimeError(f"Unsupported protocol version from the server: {result.protocolVersion}")

        self._server_capabilities = result.capabilities
        server_name = (getattr(result.serverInfo, "name", "") or "").lower()
        if "codex" not in server_name:
            await self.send_notification(mcp_types.ClientNotification(mcp_types.InitializedNotification()))
        return result

    mcp_session.ClientSession.initialize = _patched_initialize  # type: ignore[assignment]
    mcp_session._OPENVIBECODING_INITIALIZED_PATCHED = True
    mcp_session._OPENVIBECODING_INITIALIZED_ORIGINAL = original_initialize
    return True, "patched"


async def probe_mcp_ready(server: Any, tool_set: list[str]) -> dict[str, Any]:
    list_tools = getattr(server, "list_tools", None)
    if not callable(list_tools):
        return {
            "tools_count": 0,
            "servers": [],
            "mcp_tool_set": tool_set,
            "probe": "skipped",
            "reason": "list_tools_unavailable",
        }

    tools = await list_tools()
    tool_names: list[str] = []
    server_names: set[str] = set()
    for tool in tools:
        name = getattr(tool, "name", None)
        if not isinstance(name, str) or not name.strip():
            continue
        tool_names.append(name)
        if "." in name:
            server_names.add(name.split(".", 1)[0])
        elif "/" in name:
            server_names.add(name.split("/", 1)[0])
        else:
            server_names.add(name)
    return {
        "tools_count": len(tool_names),
        "servers": sorted(server_names),
        "mcp_tool_set": tool_set,
        "probe": "ok" if tool_names else "empty",
    }


def strip_model_input_ids(payload: Any) -> Any:
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
