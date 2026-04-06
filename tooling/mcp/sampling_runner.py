from __future__ import annotations

import os
import time
from typing import Any


def _mode() -> str:
    raw = os.getenv("CORTEXPILOT_SAMPLING_MODE", "mock").strip().lower()
    return raw if raw in {"mock", "echo", "llm", "gemini"} else "mock"


def _resolve_provider(payload: dict[str, Any], mode: str) -> str:
    if mode == "gemini":
        return mode
    provider = (
        os.getenv("CORTEXPILOT_SAMPLING_PROVIDER", "").strip().lower()
        or str(payload.get("provider", "")).strip().lower()
        or "gemini"
    )
    if provider == "gemini":
        return provider
    return "gemini"


def _resolve_model(payload: dict[str, Any], provider: str) -> str:
    payload_model = payload.get("model")
    if isinstance(payload_model, str) and payload_model.strip():
        return payload_model.strip()
    env_model = os.getenv("CORTEXPILOT_SAMPLING_MODEL", "").strip()
    if env_model:
        return env_model
    return "gemini-2.0-flash"


def _extract_text(response: Any) -> str:
    if hasattr(response, "output_text"):
        text = getattr(response, "output_text")
        if isinstance(text, str):
            return text
    if isinstance(response, dict):
        if isinstance(response.get("output_text"), str):
            return response["output_text"]
        if isinstance(response.get("output"), list):
            parts = []
            for item in response.get("output", []):
                if isinstance(item, dict) and isinstance(item.get("content"), list):
                    for chunk in item.get("content", []):
                        if isinstance(chunk, dict) and isinstance(chunk.get("text"), str):
                            parts.append(chunk.get("text"))
            if parts:
                return "\n".join(parts)
    return str(response)


def run_sampling(payload: dict[str, Any]) -> dict[str, Any]:
    start = time.monotonic()
    prompt = payload.get("input") if isinstance(payload, dict) else ""
    if not isinstance(prompt, str):
        prompt = ""
    payload = payload if isinstance(payload, dict) else {}
    model = payload.get("model")
    mode = _mode()

    if mode in {"mock", "echo"}:
        return {
            "ok": True,
            "mode": mode,
            "model": model or "mock-model",
            "input": prompt,
            "output": f"[sampling:{mode}] {prompt}",
            "duration_ms": int((time.monotonic() - start) * 1000),
        }

    if mode in {"llm", "gemini"}:
        provider = _resolve_provider(payload, mode)
        sampling_model = _resolve_model(payload, provider)
        if provider != "gemini":
            return {
                "ok": False,
                "mode": mode,
                "provider": provider,
                "error": "unsupported provider (gemini only)",
                "duration_ms": int((time.monotonic() - start) * 1000),
            }
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            return {
                "ok": False,
                "mode": mode,
                "provider": provider,
                "error": "missing provider API key (GEMINI_API_KEY)",
                "duration_ms": int((time.monotonic() - start) * 1000),
            }
        try:
            from google import genai

            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(model=sampling_model, contents=prompt)
            output_text = str(getattr(response, "text", "") or "").strip()
            return {
                "ok": True,
                "mode": mode,
                "provider": provider,
                "model": sampling_model,
                "input": prompt,
                "output": output_text,
                "duration_ms": int((time.monotonic() - start) * 1000),
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "mode": mode,
                "provider": provider,
                "model": sampling_model,
                "error": str(exc),
                "duration_ms": int((time.monotonic() - start) * 1000),
            }

    return {
        "ok": False,
        "mode": mode,
        "error": "sampling mode not supported",
        "duration_ms": int((time.monotonic() - start) * 1000),
    }
