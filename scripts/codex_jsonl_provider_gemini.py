#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any


def _extract_status_code(exc: Exception) -> int | None:
    for attr in ("status_code", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value

    response = getattr(exc, "response", None)
    if response is not None:
        response_code = getattr(response, "status_code", None)
        if isinstance(response_code, int):
            return response_code

    match = re.search(r"\b(4\d\d|5\d\d)\b", str(exc))
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def _is_retryable_error(exc: Exception) -> bool:
    status_code = _extract_status_code(exc)
    if status_code in {429, 500, 502, 503, 504}:
        return True

    text = str(exc).lower()
    if "timeout" in text or "timed out" in text:
        return True
    if "connection" in text or "temporarily unavailable" in text:
        return True
    return False


def _jsonable(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        try:
            return value.model_dump(exclude_none=True)
        except Exception:  # noqa: BLE001
            return str(value)
    if hasattr(value, "to_dict"):
        try:
            return value.to_dict()
        except Exception:  # noqa: BLE001
            return str(value)
    if isinstance(value, (dict, list, str, int, float, bool)):
        return value
    return str(value)


def run_gemini_once(
    *,
    prompt: str,
    md_path: Path,
    gemini_model: str,
    gemini_api_key_env: str,
    timeout_sec: int,
    dry_run: bool,
    print_lock: threading.Lock,
    display_name: str,
    max_output_tokens: int,
    max_retries: int,
    backoff_sec: float,
    semaphore: threading.Semaphore | None,
) -> tuple[bool, str, dict[str, Any]]:
    if dry_run:
        with print_lock:
            print(f"[DRY-RUN] gemini sdk generate_content model={gemini_model} file={display_name}")
        return True, "dry-run", {"provider": "gemini", "dry_run": True}

    api_key = (os.environ.get(gemini_api_key_env, "") or "").strip()
    if not api_key:
        return (
            False,
            f"missing Gemini API key env: {gemini_api_key_env}",
            {"provider": "gemini", "error_type": "missing_api_key"},
        )

    try:
        from google import genai
        from google.genai import types
    except Exception as exc:  # noqa: BLE001
        return (
            False,
            f"google-genai sdk unavailable: {exc}",
            {"provider": "gemini", "error_type": "sdk_import_error", "error": str(exc)},
        )

    client = genai.Client(api_key=api_key)
    max_attempts = max(1, max_retries + 1)
    generation_config = types.GenerateContentConfig(
        temperature=0.2,
        max_output_tokens=max(256, max_output_tokens),
    )

    def _run_call() -> tuple[bool, str, dict[str, Any]]:
        last_exc: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                response = client.models.generate_content(
                    model=gemini_model,
                    contents=prompt,
                    config=generation_config,
                )

                candidates = list(getattr(response, "candidates", []) or [])
                finish_reasons = [
                    str(getattr(candidate, "finish_reason", ""))
                    for candidate in candidates
                    if getattr(candidate, "finish_reason", None) is not None
                ]
                finish_messages = [
                    str(getattr(candidate, "finish_message", ""))
                    for candidate in candidates
                    if getattr(candidate, "finish_message", None)
                ]

                prompt_feedback_raw = getattr(response, "prompt_feedback", None)
                prompt_feedback = _jsonable(prompt_feedback_raw)

                md_text = (getattr(response, "text", "") or "").strip()
                meta: dict[str, Any] = {
                    "provider": "gemini",
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "finish_reasons": finish_reasons,
                    "finish_messages": finish_messages,
                    "prompt_feedback": prompt_feedback,
                    "model": gemini_model,
                    "max_output_tokens": max(256, max_output_tokens),
                }

                if not md_text:
                    detail = {
                        "finish_reasons": finish_reasons,
                        "finish_messages": finish_messages,
                        "prompt_feedback": prompt_feedback,
                    }
                    return False, f"gemini returned empty content: {json.dumps(detail, ensure_ascii=False)}", meta

                md_path.write_text(md_text, encoding="utf-8")
                return True, "ok", meta

            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                retryable = _is_retryable_error(exc)
                status_code = _extract_status_code(exc)
                if retryable and attempt < max_attempts:
                    sleep_sec = max(0.1, backoff_sec) * (2 ** (attempt - 1))
                    time.sleep(sleep_sec)
                    continue

                meta = {
                    "provider": "gemini",
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "status_code": status_code,
                    "retryable": retryable,
                    "error": str(exc),
                    "model": gemini_model,
                }
                return False, f"gemini request failed: {exc}", meta

        if last_exc is None:
            return (
                False,
                "gemini request failed: unknown error",
                {"provider": "gemini", "error_type": "unknown"},
            )
        return (
            False,
            f"gemini request failed: {last_exc}",
            {
                "provider": "gemini",
                "error_type": "unknown",
                "error": str(last_exc),
            },
        )

    if semaphore is None:
        return _run_call()

    with semaphore:
        return _run_call()
