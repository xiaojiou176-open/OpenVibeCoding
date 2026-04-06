from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from cortexpilot_orch.contract.validator import ContractValidator
from cortexpilot_orch.runners.provider_resolution import (
    build_llm_compat_client,
    resolve_provider_credentials,
)


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------


def _agents_available() -> bool:
    try:
        import agents  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def _summarize_results(results: list[dict[str, Any]], limit: int = 6) -> list[dict[str, str]]:
    summarized: list[dict[str, str]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        provider = item.get("provider") or item.get("resolved_provider") or item.get("mode") or "unknown"
        hits = item.get("results") if isinstance(item.get("results"), list) else []
        for hit in hits[:2]:
            if not isinstance(hit, dict):
                continue
            summarized.append(
                {
                    "provider": str(provider),
                    "title": str(hit.get("title", "")),
                    "href": str(hit.get("href", "")),
                }
            )
        if len(summarized) >= limit:
            break
    return summarized


# -------------------------------------------------------------------
# Public API
# -------------------------------------------------------------------


def verify_search_results_ai(
    query: str,
    results: list[dict[str, Any]],
    verification: dict[str, Any] | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    if not _agents_available():
        return {"ok": False, "status": "SKIPPED", "reason": "agents sdk unavailable"}
    requested_provider = (
        (verification or {}).get("provider")
        if isinstance(verification, dict)
        else None
    )
    provider = str(requested_provider or os.getenv("CORTEXPILOT_SEARCH_PROVIDER", "") or "gemini").strip().lower()
    if provider != "gemini":
        return {
            "ok": False,
            "status": "SKIPPED",
            "reason": f"unsupported provider in verifier: {provider} (gemini only)",
        }
    creds = resolve_provider_credentials()
    api_key = creds.gemini_api_key
    if not api_key:
        return {"ok": False, "status": "SKIPPED", "reason": "missing LLM API key (GEMINI_API_KEY)"}

    from agents import Agent, Runner, set_default_openai_api

    set_default_openai_client = None
    try:
        from agents import set_default_openai_client as _set_default_openai_client

        set_default_openai_client = _set_default_openai_client
    except Exception:  # noqa: BLE001
        set_default_openai_client = None

    base_url = os.getenv("CORTEXPILOT_AGENTS_BASE_URL", "").strip()
    if provider == "gemini" and not base_url:
        base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"

    if callable(set_default_openai_client):
        try:
            compat_client = build_llm_compat_client(api_key=api_key, base_url=base_url or None)
            if compat_client is not None:
                set_default_openai_client(compat_client)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "status": "FAILED", "reason": f"verifier client setup failed: {exc}"}
    else:
        set_default_openai_api(api_key)

    api_mode = os.getenv("CORTEXPILOT_AGENTS_API", "").strip()
    if api_mode:
        set_default_openai_api(api_mode)

    resolved_model = (model or os.getenv("CORTEXPILOT_SEARCH_VERIFY_MODEL", "")).strip()
    if not resolved_model:
        resolved_model = "gemini-2.0-flash"
    instructions = (
        "You are a verification agent. Review search results and determine consistency. "
        "Return JSON only with fields: verdict (CONSISTENT|INCONSISTENT|INCONCLUSIVE), "
        "summary, risks (array), followups (array), model."
    )
    agent = Agent(
        name="CortexPilotSearchVerifier",
        instructions=instructions,
        model=resolved_model,
        mcp_servers=[],
    )
    payload = {
        "query": query,
        "verification": verification or {},
        "results": _summarize_results(results),
    }
    prompt = json.dumps(payload, ensure_ascii=False)

    async def _run() -> Any:
        return await Runner.run(agent, prompt)

    try:
        result = asyncio.run(_run())
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "status": "FAILED", "reason": str(exc)}

    output = getattr(result, "final_output", None)
    if not isinstance(output, str) or not output.strip():
        return {"ok": False, "status": "FAILED", "reason": "verifier output missing"}
    try:
        report = json.loads(output)
    except json.JSONDecodeError as exc:
        return {"ok": False, "status": "FAILED", "reason": f"verifier output not json: {exc}"}

    if not isinstance(report, dict):
        return {"ok": False, "status": "FAILED", "reason": "verifier output not object"}
    report.setdefault("model", resolved_model)
    report.setdefault("provider", provider)
    try:
        ContractValidator().validate_report(report, "search_verification_ai.v1.json")
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "status": "FAILED", "reason": str(exc)}
    return {"ok": True, "status": "OK", "report": report}
