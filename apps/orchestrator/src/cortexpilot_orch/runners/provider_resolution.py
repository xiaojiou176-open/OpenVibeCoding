from __future__ import annotations

import importlib
import os
import time
from dataclasses import dataclass
from typing import Any, Mapping
from uuid import uuid4

import httpx

from cortexpilot_orch.runners import provider_capability as provider_capability_module
from cortexpilot_orch.runners.provider_capability import (
    PROVIDER_UNSUPPORTED_ERROR,
    _is_switchyard_runtime_base_url,
    _provider_gateway_ids,
    ProviderResolutionError,
    resolve_runtime_provider,
)

_PROVIDER_ENV_KEYS = (
    "CORTEXPILOT_PROVIDER",
)
_PROVIDER_MODEL_ENV_KEYS = (
    "CORTEXPILOT_PROVIDER_MODEL",
)
_PROVIDER_DEFAULT_MODELS = {
    "gemini": "gemini-2.5-flash",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-sonnet-latest",
}
_LITELLM_ENABLE_ENV_KEYS = ("CORTEXPILOT_PROVIDER_USE_LITELLM",)
_SWITCHYARD_RUNTIME_INVOKE_PATH = "/v1/runtime/invoke"
_SWITCHYARD_WEB_PROVIDERS = {"chatgpt", "gemini", "claude", "grok", "qwen"}


def resolve_compat_api_mode(default_api: str | None, *, base_url: str | None = None) -> str:
    return provider_capability_module.resolve_compat_api_mode(default_api, base_url=base_url)


def resolve_runtime_base_url_from_env(env: Mapping[str, str] | None = None) -> str:
    return provider_capability_module.resolve_runtime_base_url_from_env(env)


@dataclass(frozen=True)
class ProviderCredentials:
    # Runtime credential source supports Gemini/OpenAI/Anthropic providers.
    gemini_api_key: str
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    equilibrium_api_key: str = ""


@dataclass(frozen=True)
class LiteLLMCompatClient:
    # Minimal compatibility wrapper to indicate LiteLLM route is active.
    api_key: str
    base_url: str | None = None
    timeout: float | None = None
    max_retries: int | None = None


class _SwitchyardChatCompletionStream:
    def __init__(self, chunk: Any) -> None:
        self._chunk = chunk

    def __aiter__(self):
        return self._stream()

    async def _stream(self):
        yield self._chunk


class _SwitchyardChatCompletionsResource:
    def __init__(self, client: "SwitchyardCompatClient") -> None:
        self._client = client

    async def create(self, **kwargs: Any) -> Any:
        return await self._client.create_chat_completion(**kwargs)


class _SwitchyardChatResource:
    def __init__(self, client: "SwitchyardCompatClient") -> None:
        self.completions = _SwitchyardChatCompletionsResource(client)


class SwitchyardCompatClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        provider: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.provider = provider or ""
        self.timeout = timeout
        self.max_retries = max_retries
        self.chat = _SwitchyardChatResource(self)

    async def create_chat_completion(self, **kwargs: Any) -> Any:
        stream = bool(kwargs.get("stream"))
        tools = kwargs.get("tools")
        if tools not in (None, [], (), ""):
            raise RuntimeError(
                "Switchyard runtime-first adapter does not support tool calling yet."
            )

        system_text, input_text = _switchyard_messages_to_prompt(kwargs.get("messages"))
        target_provider, target_model, lane = _resolve_switchyard_target(
            str(kwargs.get("model", "")).strip(),
            provider=self.provider,
        )
        if system_text and lane == "web":
            input_text = _prepend_system_instructions(system_text, input_text)
        output_text, response_id = await _invoke_switchyard_runtime(
            base_url=self.base_url,
            provider=target_provider,
            model=target_model,
            lane=lane,
            input_text=input_text,
            system_text=system_text,
            timeout=self.timeout,
            max_retries=self.max_retries,
        )
        completion = _build_switchyard_chat_completion(
            model=str(kwargs.get("model", "")).strip() or target_model,
            output_text=output_text,
            response_id=response_id,
        )
        if not stream:
            return completion
        return _SwitchyardChatCompletionStream(
            _build_switchyard_chat_completion_chunk(
                completion=completion,
                output_text=output_text,
            )
        )


def resolve_compat_api_key(
    credentials: ProviderCredentials,
    provider: str | None = None,
    *,
    base_url: str | None = None,
) -> str:
    preferred = resolve_preferred_api_key(credentials, provider)
    if preferred:
        return preferred
    if _is_switchyard_runtime_base_url(base_url):
        for candidate in (
            credentials.openai_api_key,
            credentials.gemini_api_key,
            credentials.anthropic_api_key,
            credentials.equilibrium_api_key,
        ):
            value = str(candidate or "").strip()
            if value:
                return value
        return "switchyard-local"
    return ""


def _extract_message_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                stripped = item.strip()
                if stripped:
                    parts.append(stripped)
                continue
            if isinstance(item, Mapping):
                text = str(item.get("text") or "").strip()
                if text:
                    parts.append(text)
        return "\n".join(parts).strip()
    if isinstance(content, Mapping):
        return str(content.get("text") or "").strip()
    return ""


def _switchyard_messages_to_prompt(messages: Any) -> tuple[str | None, str]:
    if not isinstance(messages, list):
        text = str(messages or "").strip()
        return None, text

    system_lines: list[str] = []
    transcript_lines: list[str] = []
    last_user_text = ""

    for entry in messages:
        if isinstance(entry, Mapping):
            role = str(entry.get("role") or "").strip().lower()
            content = _extract_message_text(entry.get("content"))
        else:
            role = str(getattr(entry, "role", "") or "").strip().lower()
            content = _extract_message_text(getattr(entry, "content", ""))
        if not content:
            continue
        if role == "system":
            system_lines.append(content)
            continue
        if role == "user":
            last_user_text = content
        label = role or "user"
        transcript_lines.append(f"{label}: {content}")

    if last_user_text and len(transcript_lines) <= 1:
        prompt = last_user_text
    else:
        prompt = "\n\n".join(transcript_lines).strip()
    system_text = "\n\n".join(system_lines).strip() or None
    return system_text, prompt


def _resolve_switchyard_target(model: str, *, provider: str | None = None) -> tuple[str, str, str]:
    raw_model = str(model or "").strip()
    if "/" in raw_model:
        candidate_provider, runtime_model = raw_model.split("/", 1)
        normalized_provider = candidate_provider.strip().lower()
        if normalized_provider in _SWITCHYARD_WEB_PROVIDERS and runtime_model.strip():
            return normalized_provider, runtime_model.strip(), "web"

    normalized_provider = str(provider or "").strip().lower()
    if normalized_provider in {"openai", "anthropic", "gemini"}:
        if not raw_model:
            raise RuntimeError("Switchyard adapter requires a non-empty model name.")
        return normalized_provider, raw_model, "byok"

    lowered_model = raw_model.lower()
    if lowered_model.startswith(("gpt-", "o1", "o3", "o4")):
        return "chatgpt", raw_model, "web"
    if lowered_model.startswith("gemini"):
        return "gemini", raw_model, "web"
    if lowered_model.startswith("claude"):
        return "claude", raw_model, "web"
    if lowered_model.startswith("grok"):
        return "grok", raw_model, "web"
    if lowered_model.startswith("qwen"):
        return "qwen", raw_model, "web"

    raise RuntimeError(
        "Switchyard adapter could not infer a runtime provider. "
        "Use `provider/model` for web providers or keep a supported runtime provider in CortexPilot config."
    )


def _prepend_system_instructions(system_text: str, input_text: str) -> str:
    instructions = system_text.strip()
    body = input_text.strip()
    if not instructions:
        return body
    if not body:
        return f"System instructions:\n{instructions}"
    return f"System instructions:\n{instructions}\n\nUser request:\n{body}"


async def _invoke_switchyard_runtime(
    *,
    base_url: str,
    provider: str,
    model: str,
    lane: str,
    input_text: str,
    system_text: str | None,
    timeout: float | None,
    max_retries: int | None,
) -> tuple[str, str]:
    payload: dict[str, Any] = {
        "provider": provider,
        "model": model,
        "input": input_text,
        "lane": lane,
        "stream": False,
    }
    if system_text and lane == "byok":
        payload["system"] = system_text
    timeout_value = timeout if timeout is not None else 180.0
    attempts = max(1, 1 + max(0, int(max_retries or 0)))
    last_error: Exception | None = None
    body: Mapping[str, Any] | dict[str, Any] = {}
    response: httpx.Response | None = None
    for attempt in range(attempts):
        try:
            async with httpx.AsyncClient(timeout=timeout_value) as client:
                response = await client.post(base_url, json=payload)
        except httpx.HTTPError as exc:
            last_error = exc
            if attempt + 1 >= attempts:
                raise RuntimeError(
                    f"Switchyard runtime invoke failed after {attempts} attempt(s): {exc}"
                ) from exc
            continue

        try:
            parsed = response.json()
        except Exception:
            parsed = {}
        body = parsed if isinstance(parsed, Mapping) else {}

        if response.status_code < 500:
            break
        error_message = "Switchyard runtime invoke failed."
        error = body.get("error") if isinstance(body, Mapping) else None
        if isinstance(error, Mapping):
            error_message = str(error.get("message") or error_message)
        if attempt + 1 >= attempts:
            raise RuntimeError(
                f"Switchyard runtime invoke failed with HTTP {response.status_code}: {error_message}"
            )
    if response is None:
        if last_error is not None:
            raise RuntimeError(
                f"Switchyard runtime invoke failed after {attempts} attempt(s): {last_error}"
            ) from last_error
        raise RuntimeError("Switchyard runtime invoke failed before receiving a response.")
    if response.status_code >= 400:
        error_message = "Switchyard runtime invoke failed."
        if isinstance(body, Mapping):
            error = body.get("error")
            if isinstance(error, Mapping):
                error_message = str(error.get("message") or error_message)
        raise RuntimeError(
            f"Switchyard runtime invoke failed with HTTP {response.status_code}: {error_message}"
        )
    if not isinstance(body, Mapping):
        raise RuntimeError("Switchyard runtime returned a non-object JSON payload.")
    output_text = str(body.get("outputText") or body.get("text") or "").strip()
    if not output_text:
        raise RuntimeError("Switchyard runtime invoke returned no output text.")
    response_id = str(body.get("providerMessageId") or f"switchyard-{uuid4()}")
    return output_text, response_id


def _build_switchyard_chat_completion(*, model: str, output_text: str, response_id: str) -> Any:
    openai_chat_module = importlib.import_module("openai.types.chat")
    chat_completion_cls = getattr(openai_chat_module, "ChatCompletion")
    return chat_completion_cls.model_validate(
        {
            "id": response_id,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": output_text,
                    },
                }
            ],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        }
    )


def _build_switchyard_chat_completion_chunk(*, completion: Any, output_text: str) -> Any:
    openai_chat_module = importlib.import_module("openai.types.chat")
    chat_chunk_cls = getattr(openai_chat_module, "ChatCompletionChunk")
    return chat_chunk_cls.model_validate(
        {
            "id": completion.id,
            "object": "chat.completion.chunk",
            "created": completion.created,
            "model": completion.model,
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "role": "assistant",
                        "content": output_text,
                    },
                    "finish_reason": "stop",
                }
            ],
        }
    )

def resolve_provider_credentials(env: Mapping[str, str] | None = None) -> ProviderCredentials:
    source = os.environ if env is None else env
    gemini_api_key = str(source.get("GEMINI_API_KEY", "")).strip()
    openai_api_key = str(source.get("OPENAI_API_KEY", "")).strip()
    anthropic_api_key = str(source.get("ANTHROPIC_API_KEY", "")).strip()
    equilibrium_api_key = str(source.get("CORTEXPILOT_EQUILIBRIUM_API_KEY", "")).strip()
    return ProviderCredentials(
        gemini_api_key=gemini_api_key,
        openai_api_key=openai_api_key,
        anthropic_api_key=anthropic_api_key,
        equilibrium_api_key=equilibrium_api_key,
    )


def resolve_preferred_api_key(credentials: ProviderCredentials, provider: str | None = None) -> str:
    requested_provider = resolve_runtime_provider(provider or resolve_runtime_provider_from_env())
    ordered_keys: tuple[str, ...]
    if requested_provider == "openai":
        ordered_keys = (
            credentials.openai_api_key,
            credentials.gemini_api_key,
            credentials.anthropic_api_key,
        )
    elif requested_provider == "anthropic":
        ordered_keys = (
            credentials.anthropic_api_key,
            credentials.gemini_api_key,
            credentials.openai_api_key,
        )
    elif requested_provider not in {"gemini", "openai", "anthropic"}:
        # Custom providers are OpenAI-compatible by contract; prefer gateway/openai-style key first.
        ordered_keys = (
            credentials.equilibrium_api_key,
            credentials.openai_api_key,
            credentials.gemini_api_key,
            credentials.anthropic_api_key,
        )
    else:
        ordered_keys = (
            credentials.gemini_api_key,
            credentials.openai_api_key,
            credentials.anthropic_api_key,
        )
    for key in ordered_keys:
        if str(key).strip():
            return str(key).strip()
    return ""


def merge_provider_credentials(primary: ProviderCredentials, fallback: ProviderCredentials) -> ProviderCredentials:
    return ProviderCredentials(
        gemini_api_key=primary.gemini_api_key or fallback.gemini_api_key,
        openai_api_key=primary.openai_api_key or fallback.openai_api_key,
        anthropic_api_key=primary.anthropic_api_key or fallback.anthropic_api_key,
        equilibrium_api_key=primary.equilibrium_api_key or fallback.equilibrium_api_key,
    )

def resolve_provider_inventory_id(provider: str | None) -> str:
    normalized = resolve_runtime_provider(provider)
    if normalized in {"gemini", "openai", "anthropic"}:
        return f"provider:{normalized}"
    if normalized in _provider_gateway_ids():
        return f"provider-gateway:{normalized}"
    raise ProviderResolutionError(
        PROVIDER_UNSUPPORTED_ERROR,
        f"provider `{normalized}` is not registered in configs/upstream_inventory.json",
    )


def resolve_runtime_provider_from_env(env: Mapping[str, str] | None = None) -> str:
    source = os.environ if env is None else env
    for key in _PROVIDER_ENV_KEYS:
        candidate = str(source.get(key, "")).strip()
        if candidate:
            return resolve_runtime_provider(candidate)
    return "gemini"


def resolve_runtime_provider_from_contract(
    contract: Mapping[str, Any] | None,
    env: Mapping[str, str] | None = None,
) -> str:
    runtime_options = contract.get("runtime_options") if isinstance(contract, Mapping) else None
    if isinstance(runtime_options, Mapping):
        candidate = str(runtime_options.get("provider", "")).strip()
        if candidate:
            return resolve_runtime_provider(candidate)
    return resolve_runtime_provider_from_env(env)

def resolve_runtime_model_from_env(provider: str | None = None, env: Mapping[str, str] | None = None) -> str:
    source = os.environ if env is None else env
    for key in _PROVIDER_MODEL_ENV_KEYS:
        value = str(source.get(key, "")).strip()
        if value:
            return value
    return _PROVIDER_DEFAULT_MODELS.get(resolve_runtime_provider(provider), _PROVIDER_DEFAULT_MODELS["gemini"])


def _env_flag(
    name: str,
    *,
    default: bool = False,
    env: Mapping[str, str] | None = None,
) -> bool:
    source = os.environ if env is None else env
    raw = str(source.get(name, "")).strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def use_litellm_provider_path(env: Mapping[str, str] | None = None) -> bool:
    for key in _LITELLM_ENABLE_ENV_KEYS:
        if _env_flag(key, env=env):
            return True
    return False


def _build_litellm_compat_client(
    *,
    api_key: str,
    base_url: str | None = None,
    timeout: float | None = None,
    max_retries: int | None = None,
) -> LiteLLMCompatClient | None:
    try:
        litellm_module = importlib.import_module("litellm")
    except Exception:
        return None
    # Guard: litellm package import is required before declaring LiteLLM route active.
    if getattr(litellm_module, "acompletion", None) is None and getattr(litellm_module, "completion", None) is None:
        return None
    # Agents SDK requires an AsyncOpenAI-compatible client with `.responses.create(...)`.
    # LiteLLM package import alone does not provide such an object here, so keep fallback path.
    return None


def build_llm_compat_client(
    *,
    api_key: str,
    base_url: str | None = None,
    timeout: float | None = None,
    max_retries: int | None = None,
    env: Mapping[str, str] | None = None,
    provider: str | None = None,
) -> Any | None:
    if _is_switchyard_runtime_base_url(base_url):
        return SwitchyardCompatClient(
            api_key=api_key,
            base_url=str(base_url),
            provider=provider,
            timeout=timeout,
            max_retries=max_retries,
        )
    if use_litellm_provider_path(env):
        litellm_client = _build_litellm_compat_client(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
        )
        if litellm_client is not None:
            return litellm_client
    try:
        openai_module = importlib.import_module("openai")
    except Exception:
        return None
    async_openai = getattr(openai_module, "AsyncOpenAI", None)
    if async_openai is None:
        return None
    kwargs: dict[str, Any] = {"api_key": api_key, "base_url": base_url}
    if timeout is not None:
        kwargs["timeout"] = timeout
    if max_retries is not None:
        kwargs["max_retries"] = max_retries
    return async_openai(**kwargs)


def build_openai_compatible_client(
    *,
    api_key: str,
    base_url: str | None = None,
    timeout: float | None = None,
    max_retries: int | None = None,
) -> Any | None:
    # Backward-compatible alias; keep OpenAI naming scoped to compatibility layer.
    return build_llm_compat_client(
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
        max_retries=max_retries,
    )
