#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib import error, request

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[import-not-found]


ROOT = Path(__file__).resolve().parents[1]
TEST_OUTPUT_DIR = ROOT / ".runtime-cache" / "test_output"
DEFAULT_CODEX_CONFIG = Path.home() / ".codex" / "config.toml"

_OPENAI_ALLOWED = {"gpt-5.3-codex", "gpt-5.2"}
_ANTHROPIC_ALLOWED = {
    "anthropic/claude-sonnet-4-5",
    "anthropic/claude-sonnet-4-6",
    "anthropic/claude-opus-4-5",
    "anthropic/claude-opus-4-6",
}
_ANTHROPIC_ALIAS = {
    "claude-sonnet-4-5": "anthropic/claude-sonnet-4-5",
    "claude-sonnet-4-6": "anthropic/claude-sonnet-4-6",
    "claude-opus-4-5": "anthropic/claude-opus-4-5",
    "claude-opus-4-6": "anthropic/claude-opus-4-6",
}
_GEMINI_ALLOWED = {"gemini-3.0-pro", "gemini-3.1-pro"}
_GEMINI_RUNTIME_MAP = {
    "gemini-3.0-pro": "gemini-3-pro-preview",
    "gemini-3.1-pro": "gemini-3-pro-preview",
}

INPUTS = [
    {"input_id": "I1", "task": "validate onboarding command path"},
    {"input_id": "I2", "task": "summarize release risk in one line"},
    {"input_id": "I3", "task": "classify incident severity from text"},
    {"input_id": "I4", "task": "extract rollback trigger keywords"},
    {"input_id": "I5", "task": "tag governance gates in ci stage"},
]


@dataclass
class ProviderLane:
    name: str
    mode: str
    endpoint: str
    model: str
    auth_header: dict[str, str]
    api_style: str  # openai_chat | anthropic_messages | gemini_generate_content


def _load_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        val = val.strip().strip('"').strip("'")
        values[key] = val
    return values


def _load_codex_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _resolve_cfg_provider(config: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    provider_name = str(config.get("model_provider") or "").strip()
    providers = config.get("model_providers")
    if not isinstance(providers, dict):
        return provider_name, {}
    provider_cfg = providers.get(provider_name)
    if not isinstance(provider_cfg, dict):
        return provider_name, {}
    return provider_name, provider_cfg


def _resolve_token(raw: str, env: dict[str, str]) -> str:
    token = raw.strip()
    if token.startswith("${") and token.endswith("}") and len(token) > 3:
        env_key = token[2:-1].strip()
        return env.get(env_key, "").strip()
    return token


def _normalize_base_url(url: str) -> str:
    out = url.strip()
    while out.endswith("/"):
        out = out[:-1]
    return out


def _http_json(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_sec: int = 90,
) -> tuple[int, dict[str, Any], str]:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url=url,
        data=body,
        method="POST",
        headers={**headers, "Content-Type": "application/json"},
    )
    try:
        with request.urlopen(req, timeout=timeout_sec) as resp:
            text = resp.read().decode("utf-8", errors="ignore")
            data = json.loads(text) if text.strip() else {}
            return resp.status, data, text
    except error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="ignore")
        try:
            data = json.loads(text) if text.strip() else {}
        except Exception:
            data = {"raw": text}
        return int(exc.code), data, text


def _extract_text(style: str, data: dict[str, Any]) -> str:
    if style == "openai_chat":
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message", {})
            content = message.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts: list[str] = []
                for item in content:
                    if isinstance(item, dict) and isinstance(item.get("text"), str):
                        parts.append(item["text"])
                return "\n".join(parts)
    if style == "anthropic_messages":
        blocks = data.get("content")
        if isinstance(blocks, list):
            parts = []
            for item in blocks:
                if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                    parts.append(item["text"])
            return "\n".join(parts)
    if style == "gemini_generate_content":
        candidates = data.get("candidates")
        if isinstance(candidates, list) and candidates:
            content = candidates[0].get("content", {})
            parts = content.get("parts")
            if isinstance(parts, list):
                out = []
                for item in parts:
                    if isinstance(item, dict) and isinstance(item.get("text"), str):
                        out.append(item["text"])
                return "\n".join(out)
    return ""


def _extract_usage(style: str, data: dict[str, Any]) -> tuple[int, int, int]:
    if style == "openai_chat":
        usage = data.get("usage", {})
        in_tok = int(usage.get("prompt_tokens") or 0)
        out_tok = int(usage.get("completion_tokens") or 0)
        total = int(usage.get("total_tokens") or (in_tok + out_tok))
        return in_tok, out_tok, total
    if style == "anthropic_messages":
        usage = data.get("usage", {})
        in_tok = int(usage.get("input_tokens") or 0)
        out_tok = int(usage.get("output_tokens") or 0)
        total = in_tok + out_tok
        return in_tok, out_tok, total
    if style == "gemini_generate_content":
        usage = data.get("usageMetadata", {})
        in_tok = int(usage.get("promptTokenCount") or 0)
        out_tok = int(usage.get("candidatesTokenCount") or 0)
        total = int(usage.get("totalTokenCount") or (in_tok + out_tok))
        return in_tok, out_tok, total
    return 0, 0, 0


def _extract_json_object(raw_text: str) -> dict[str, Any] | None:
    text = raw_text.strip()
    if not text:
        return None
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        chunk = text[start : end + 1]
        try:
            obj = json.loads(chunk)
            if isinstance(obj, dict):
                return obj
        except Exception:
            return None
    return None


def _validate_struct(obj: dict[str, Any], expected_provider: str, input_id: str) -> tuple[bool, list[str]]:
    errs: list[str] = []
    if obj.get("provider") != expected_provider:
        errs.append("provider mismatch")
    if obj.get("input_id") != input_id:
        errs.append("input_id mismatch")
    if obj.get("label") not in {"PASS", "FAIL"}:
        errs.append("label invalid")
    score = obj.get("score")
    if not isinstance(score, int) or score < 0 or score > 100:
        errs.append("score invalid")
    tags = obj.get("tags")
    if not isinstance(tags, list) or len(tags) != 2 or not all(isinstance(x, str) and x.islower() for x in tags):
        errs.append("tags invalid")
    return (len(errs) == 0), errs


def _percentile(nums: list[float], p: float) -> float:
    if not nums:
        return 0.0
    if len(nums) == 1:
        return float(nums[0])
    arr = sorted(nums)
    rank = (len(arr) - 1) * p
    low = int(rank)
    high = min(low + 1, len(arr) - 1)
    weight = rank - low
    return float(arr[low] * (1 - weight) + arr[high] * weight)


def _cost_estimate(provider: str, in_tokens: int, out_tokens: int, env: dict[str, str]) -> tuple[float, dict[str, Any]]:
    defaults = {
        "gemini": (0.10, 0.40),
        "openai": (0.15, 0.60),
        "anthropic": (3.00, 15.00),
    }
    in_default, out_default = defaults[provider]
    in_price = float(env.get(f"OPENVIBECODING_EVAL_{provider.upper()}_INPUT_USD_PER_1M", in_default))
    out_price = float(env.get(f"OPENVIBECODING_EVAL_{provider.upper()}_OUTPUT_USD_PER_1M", out_default))
    cost = (in_tokens / 1_000_000.0) * in_price + (out_tokens / 1_000_000.0) * out_price
    meta = {
        "input_usd_per_1m": in_price,
        "output_usd_per_1m": out_price,
        "assumption": "estimated_from_token_usage",
    }
    return cost, meta


def _build_prompt(provider_name: str, input_id: str, task: str) -> tuple[str, str]:
    system = (
        "You output strict minified JSON only. "
        "Schema keys: provider,input_id,label,score,tags. "
        "provider must equal the requested provider. "
        "label in PASS/FAIL. score integer 0..100. tags must be exactly two lowercase words."
    )
    user = (
        f"requested_provider={provider_name}; input_id={input_id}; task={task}. "
        "Return only JSON with no markdown."
    )
    return system, user


def _run_case(lane: ProviderLane, item: dict[str, str], env: dict[str, str]) -> dict[str, Any]:
    system, user = _build_prompt(lane.name, item["input_id"], item["task"])
    if lane.api_style == "openai_chat":
        payload = {
            "model": lane.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
    elif lane.api_style == "anthropic_messages":
        payload = {
            "model": lane.model,
            "max_tokens": 256,
            "temperature": 0,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
    elif lane.api_style == "gemini_generate_content":
        payload = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": 0,
                "maxOutputTokens": 512,
                "responseMimeType": "application/json",
            },
        }
    else:
        raise RuntimeError(f"unsupported api style: {lane.api_style}")

    t0 = time.perf_counter()
    status, data, raw = _http_json(lane.endpoint, lane.auth_header, payload)
    latency_ms = (time.perf_counter() - t0) * 1000.0

    text = _extract_text(lane.api_style, data)
    parsed = _extract_json_object(text)
    struct_ok = False
    struct_errors: list[str] = []
    if parsed is not None:
        struct_ok, struct_errors = _validate_struct(parsed, lane.name, item["input_id"])
    in_tok, out_tok, total_tok = _extract_usage(lane.api_style, data)
    cost_usd, pricing = _cost_estimate(lane.name, in_tok, out_tok, env)
    success = 200 <= status < 300 and parsed is not None

    return {
        "provider": lane.name,
        "input_id": item["input_id"],
        "task": item["task"],
        "status_code": status,
        "success": success,
        "latency_ms": round(latency_ms, 2),
        "structure_pass": struct_ok,
        "structure_errors": struct_errors,
        "response_text_preview": (text or raw)[:280],
        "usage": {
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "total_tokens": total_tok,
        },
        "estimated_cost_usd": round(cost_usd, 8),
        "pricing_assumption": pricing,
    }


def _summarize_provider(cases: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(cases)
    successes = sum(1 for c in cases if c["success"])
    struct_pass = sum(1 for c in cases if c["structure_pass"])
    latencies = [float(c["latency_ms"]) for c in cases]
    input_tokens = sum(int(c["usage"]["input_tokens"]) for c in cases)
    output_tokens = sum(int(c["usage"]["output_tokens"]) for c in cases)
    total_tokens = sum(int(c["usage"]["total_tokens"]) for c in cases)
    cost = sum(float(c["estimated_cost_usd"]) for c in cases)

    return {
        "samples": total,
        "success_rate": round((successes / total) if total else 0.0, 4),
        "structure_consistency_pass_rate": round((struct_pass / total) if total else 0.0, 4),
        "latency_ms": {
            "p50": round(_percentile(latencies, 0.50), 2),
            "p95": round(_percentile(latencies, 0.95), 2),
            "mean": round(statistics.fmean(latencies) if latencies else 0.0, 2),
        },
        "usage_tokens": {
            "input": input_tokens,
            "output": output_tokens,
            "total": total_tokens,
        },
        "estimated_cost_usd": round(cost, 8),
    }


def _read_env() -> dict[str, str]:
    env = dict(os.environ)
    dotenv = _load_dotenv(ROOT / ".env")
    for k, v in dotenv.items():
        env.setdefault(k, v)
    return env


def _build_lanes(env: dict[str, str]) -> tuple[list[ProviderLane], dict[str, Any]]:
    cfg_path = Path(env.get("OPENVIBECODING_CODEX_CONFIG_PATH", str(DEFAULT_CODEX_CONFIG)))
    config = _load_codex_config(cfg_path)
    cfg_provider_name, cfg_provider = _resolve_cfg_provider(config)
    gateway_base = _normalize_base_url(str(cfg_provider.get("base_url") or ""))
    gateway_token_raw = str(cfg_provider.get("experimental_bearer_token") or cfg_provider.get("api_key") or "").strip()
    gateway_token = _resolve_token(gateway_token_raw, env)

    gemini_model_logical = env.get("OPENVIBECODING_EVAL_GEMINI_MODEL", "gemini-3.1-pro").strip()
    openai_model = env.get("OPENVIBECODING_EVAL_OPENAI_MODEL", "gpt-5.3-codex").strip()
    anthropic_model_raw = env.get("OPENVIBECODING_EVAL_ANTHROPIC_MODEL", "anthropic/claude-sonnet-4-6").strip()
    anthropic_model = _ANTHROPIC_ALIAS.get(anthropic_model_raw, anthropic_model_raw)
    gemini_model = _GEMINI_RUNTIME_MAP.get(gemini_model_logical, gemini_model_logical)

    lanes: list[ProviderLane] = []
    gaps: list[str] = []
    creds = {
        "gemini_env": bool(env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY")),
        "openai_env": bool(env.get("OPENAI_API_KEY")),
        "anthropic_env": bool(env.get("ANTHROPIC_API_KEY")),
        "codex_gateway": bool(gateway_base and gateway_token),
        "codex_provider_name": cfg_provider_name or "",
        "codex_base_url": gateway_base,
    }

    gemini_key = (env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY") or "").strip()
    if gemini_model_logical not in _GEMINI_ALLOWED:
        gaps.append(
            f"gemini: model not allowed ({gemini_model_logical}); allowed={sorted(_GEMINI_ALLOWED)}"
        )
    elif gemini_key:
        model = gemini_model
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gemini_key}"
        lanes.append(
            ProviderLane(
                name="gemini",
                mode="direct",
                endpoint=endpoint,
                model=model,
                auth_header={},
                api_style="gemini_generate_content",
            )
        )
    elif gateway_base and gateway_token:
        lanes.append(
            ProviderLane(
                name="gemini",
                mode="gateway_openai_compat",
                endpoint=f"{gateway_base}/chat/completions",
                model=gemini_model,
                auth_header={"Authorization": f"Bearer {gateway_token}"},
                api_style="openai_chat",
            )
        )
    else:
        gaps.append("gemini: missing GEMINI_API_KEY (or GOOGLE_API_KEY) and no codex gateway token/base_url")

    openai_key = (env.get("OPENAI_API_KEY") or "").strip()
    if openai_model not in _OPENAI_ALLOWED:
        gaps.append(
            f"openai: model not allowed ({openai_model}); allowed={sorted(_OPENAI_ALLOWED)}"
        )
    elif openai_key:
        lanes.append(
            ProviderLane(
                name="openai",
                mode="direct",
                endpoint="https://api.openai.com/v1/chat/completions",
                model=openai_model,
                auth_header={"Authorization": f"Bearer {openai_key}"},
                api_style="openai_chat",
            )
        )
    elif gateway_base and gateway_token:
        lanes.append(
            ProviderLane(
                name="openai",
                mode="gateway_openai_compat",
                endpoint=f"{gateway_base}/chat/completions",
                model=openai_model,
                auth_header={"Authorization": f"Bearer {gateway_token}"},
                api_style="openai_chat",
            )
        )
    else:
        gaps.append("openai: missing OPENAI_API_KEY and no codex gateway token/base_url")

    anthropic_key = (env.get("ANTHROPIC_API_KEY") or "").strip()
    if anthropic_model not in _ANTHROPIC_ALLOWED:
        gaps.append(
            f"anthropic: model not allowed ({anthropic_model_raw}); allowed={sorted(_ANTHROPIC_ALLOWED)}"
        )
    elif anthropic_key:
        lanes.append(
            ProviderLane(
                name="anthropic",
                mode="direct",
                endpoint="https://api.anthropic.com/v1/messages",
                model=anthropic_model,
                auth_header={
                    "x-api-key": anthropic_key,
                    "anthropic-version": "2023-06-01",
                },
                api_style="anthropic_messages",
            )
        )
    elif gateway_base and gateway_token:
        lanes.append(
            ProviderLane(
                name="anthropic",
                mode="gateway_openai_compat",
                endpoint=f"{gateway_base}/chat/completions",
                model=anthropic_model,
                auth_header={"Authorization": f"Bearer {gateway_token}"},
                api_style="openai_chat",
            )
        )
    else:
        gaps.append("anthropic: missing ANTHROPIC_API_KEY and no codex gateway token/base_url")

    detection = {
        "credentials_detected": creds,
        "credential_gaps": gaps,
        "injection_commands": [
            "export GEMINI_API_KEY='<real_gemini_key>'",
            "export OPENAI_API_KEY='<real_openai_key>'",
            "export ANTHROPIC_API_KEY='<real_anthropic_key>'",
            "export OPENVIBECODING_CODEX_CONFIG_PATH=\"$HOME/.codex/config.toml\"",
        ],
    }
    return lanes, detection


def _load_trend_snapshot(max_entries: int = 8) -> list[dict[str, Any]]:
    snapshots = sorted(TEST_OUTPUT_DIR.glob("provider_consistency_eval_real_*.json"))
    rows: list[dict[str, Any]] = []
    for path in snapshots[-max_entries:]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        rows.append(
            {
                "run_id": data.get("run_id"),
                "run_utc": data.get("run_utc"),
                "providers": data.get("providers_summary", {}),
                "path": str(path.relative_to(ROOT)),
            }
        )
    return rows


def main() -> int:
    TEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    env = _read_env()
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_utc = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    lanes, detection = _build_lanes(env)
    results_by_provider: dict[str, list[dict[str, Any]]] = {}
    blocked: list[dict[str, Any]] = []
    for provider_name in ("gemini", "openai", "anthropic"):
        lane = next((x for x in lanes if x.name == provider_name), None)
        if lane is None:
            blocked.append({"provider": provider_name, "reason": "credentials_or_route_missing"})
            continue
        cases: list[dict[str, Any]] = []
        for item in INPUTS:
            case = _run_case(lane, item, env)
            cases.append(case)
        results_by_provider[provider_name] = cases

    providers_summary = {name: _summarize_provider(cases) for name, cases in results_by_provider.items()}
    all_cases = [c for cases in results_by_provider.values() for c in cases]
    overall = _summarize_provider(all_cases) if all_cases else _summarize_provider([])
    trend = _load_trend_snapshot()

    payload = {
        "run_id": run_id,
        "run_utc": run_utc,
        "inputs_count": len(INPUTS),
        "inputs": INPUTS,
        "detection": detection,
        "blocked_providers": blocked,
        "provider_lanes": [
            {
                "provider": lane.name,
                "mode": lane.mode,
                "endpoint": lane.endpoint.split("?")[0],
                "model": lane.model,
                "api_style": lane.api_style,
            }
            for lane in lanes
        ],
        "provider_results": results_by_provider,
        "providers_summary": providers_summary,
        "overall_summary": overall,
        "trend_history": trend,
    }

    out_json = TEST_OUTPUT_DIR / f"provider_consistency_eval_real_{run_id}.json"
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    latest = TEST_OUTPUT_DIR / "provider_consistency_eval_real_latest.json"
    latest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"run_id={run_id}")
    print(f"output_json={out_json.relative_to(ROOT)}")
    print(f"providers={','.join(sorted(providers_summary.keys())) if providers_summary else 'none'}")
    print(f"blocked={','.join(item['provider'] for item in blocked) if blocked else 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
