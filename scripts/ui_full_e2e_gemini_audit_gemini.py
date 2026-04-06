from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from contextlib import contextmanager

try:
    import fcntl
except Exception:  # noqa: BLE001
    fcntl = None

from scripts.ui_full_e2e_gemini_audit_common import (
    INTERACTION_ANALYSIS_PROMPT,
    PAGE_ANALYSIS_PROMPT,
    PROJECT_CONTEXT,
    parse_json_response,
)
from scripts.ui_full_e2e_gemini_audit_targets import target_label

try:
    from PIL import Image
except Exception:  # noqa: BLE001
    Image = None

_OBJECTIVE_BLOCKER_KEYWORDS = (
    "无法",
    "不可",
    "未响应",
    "不能",
    "失败",
    "错误",
    "崩溃",
    "空白",
    "断链",
    "缺失关键",
    "404",
    "500",
    "blocked",
    "cannot",
    "broken",
    "missing critical",
)

_SUBJECTIVE_STYLE_KEYWORDS = (
    "冗余",
    "认知负担",
    "术语",
    "视觉",
    "噪音",
    "占据",
    "分层",
    "风格",
    "建议",
    "可进一步",
    "是否应",
    "设计",
    "layout",
    "style",
    "density",
    "consistency",
)

_AUTH_OPTIONAL_KEYWORDS = (
    "403",
    "forbidden",
    "权限",
    "未授权",
    "unauthorized",
    "god-mode/pending",
    "/api/god-mode",
)

VALID_VERDICTS = {"pass", "warn", "fail"}

_MODEL_ALIAS_MAP: dict[str, list[str]] = {
    "gemini-3-flash": ["gemini-3.0-flash", "gemini-3-flash-preview", "gemini-2.5-flash"],
    "gemini-3.0-flash": ["gemini-3-flash-preview", "gemini-2.5-flash"],
    "gemini-3-flash-preview": ["gemini-2.5-flash"],
}

_EXTREME_TALL_ASPECT_RATIO = 7.5
_EXTREME_TALL_MIN_HEIGHT_PX = 4096


@contextmanager
def _gemini_request_lock() -> Any:
    if fcntl is None:
        yield
        return
    lock_path = Path(
        os.environ.get(
            "CORTEXPILOT_UI_GEMINI_REQUEST_LOCK",
            ".runtime-cache/cortexpilot/locks/ui_gemini_request.lock",
        )
    )
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _respect_gemini_min_interval() -> None:
    raw = str(os.environ.get("CORTEXPILOT_UI_GEMINI_MIN_INTERVAL_SEC", "2.5")).strip()
    try:
        min_interval = max(0.0, float(raw))
    except Exception:  # noqa: BLE001
        min_interval = 2.5
    if min_interval <= 0:
        return
    stamp_path = Path(
        os.environ.get(
            "CORTEXPILOT_UI_GEMINI_REQUEST_STAMP",
            ".runtime-cache/cortexpilot/locks/ui_gemini_request.timestamp",
        )
    )
    stamp_path.parent.mkdir(parents=True, exist_ok=True)
    now = time.time()
    try:
        last = float(stamp_path.read_text(encoding="utf-8").strip() or "0")
    except Exception:
        last = 0.0
    remaining = min_interval - max(0.0, now - last)
    if remaining > 0:
        time.sleep(remaining)
    stamp_path.write_text(str(time.time()), encoding="utf-8")


def _model_candidates(primary: str) -> list[str]:
    normalized = str(primary or "").strip()
    if not normalized:
        return ["gemini-3.1-pro-preview", "gemini-3.0-flash", "gemini-2.5-flash"]
    candidates = [normalized]
    for item in _MODEL_ALIAS_MAP.get(normalized, []):
        if item not in candidates:
            candidates.append(item)
    return candidates


def _is_retryable_gemini_error(exc: Exception) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    if isinstance(exc, urllib.error.HTTPError):
        return int(getattr(exc, "code", 0) or 0) in {408, 409, 425, 429, 500, 502, 503, 504}
    if isinstance(exc, urllib.error.URLError):
        reason = str(getattr(exc, "reason", "") or "").lower()
        return any(
            token in reason
            for token in (
                "timed out",
                "timeout",
                "temporary failure",
                "connection reset",
                "connection refused",
                "service unavailable",
            )
        )
    message = str(exc).lower()
    return any(
        token in message
        for token in (
            "http error 503",
            "service unavailable",
            "http error 429",
            "too many requests",
            "deadline exceeded",
            "temporarily unavailable",
            "temporarily",
            "timeout",
            "timed out",
            "no route to host",
        )
    )


def _retry_delay_sec(exc: Exception, attempt: int) -> float:
    delay = min(60.0, 3.0 * (2 ** max(0, int(attempt) - 1)))
    if isinstance(exc, urllib.error.HTTPError):
        retry_after = str((exc.headers or {}).get("Retry-After", "")).strip()
        if retry_after.isdigit():
            delay = max(delay, min(30.0, float(retry_after)))
        if int(getattr(exc, "code", 0) or 0) == 429:
            delay = max(delay, 45.0)
    elif "http error 429" in str(exc).lower() or "too many requests" in str(exc).lower():
        delay = max(delay, 45.0)
    return delay

_ROUTE_BUSINESS_OBJECTIVES: list[tuple[str, str]] = [
    (
        r"^/$",
        "总览首页：用户应能快速理解当前运行态势，并以 PM 发起任务作为主入口，再按需跳转指挥塔或运行记录。",
    ),
    (
        r"^/pm$",
        "PM 入口页：用户应能发起/继续会话，完成 Discover→Clarify→Execute→Verify 的任务编排闭环。",
    ),
    (
        r"^/command-tower($|/)",
        "指挥塔：用户应能实时监控会话/风险/执行链路，并能触发筛选、暂停、恢复、审计等关键操作。",
    ),
    (
        r"^/diff-gate($|/)",
        "Diff Gate：用户应能查看变更差异并执行高风险决策（批准/拒绝/回滚），且反馈可审计。",
    ),
    (
        r"^/agents($|/)",
        "Agents 面板：用户应能查看 Agent 状态、角色分工与执行健康度，并可进行必要的监控交互。",
    ),
]


def _route_business_objective(route: str) -> str:
    normalized = str(route or "").strip() or "/"
    for pattern, objective in _ROUTE_BUSINESS_OBJECTIVES:
        if re.search(pattern, normalized):
            return objective
    return "该页面应支持核心任务流可达、状态反馈一致、关键入口可操作且不误导。"


def _interaction_business_acceptance(*, expected_effect: str, observed: dict[str, Any]) -> str:
    click_ok = bool(observed.get("click_ok", False))
    url_changed = bool(observed.get("url_changed", False))
    api_calls_count = int(observed.get("api_calls_count", 0) or 0)
    return (
        "验收口径：\n"
        f"1) 预期业务效果：{expected_effect}\n"
        "2) 至少出现一种可信反馈：路由变化 / 可见状态变化 / 业务请求触发 / 明确错误提示。\n"
        f"3) 运行观测快照：click_ok={click_ok}, url_changed={url_changed}, api_calls_count={api_calls_count}\n"
        "4) 若无有效反馈或反馈与预期相反，应判定为 warn/fail 并指出业务影响。"
    )


def _is_explicit_non_blocking_issue(merged: str, *, has_objective_blocker: bool) -> bool:
    has_subjective_style = any(token.lower() in merged for token in _SUBJECTIVE_STYLE_KEYWORDS)
    has_optional_auth_denied = any(token.lower() in merged for token in _AUTH_OPTIONAL_KEYWORDS)
    return has_optional_auth_denied or (has_subjective_style and not has_objective_blocker)


def normalize_page_analysis(payload: dict[str, Any]) -> dict[str, Any]:
    issues_raw = payload.get("issues")
    issues: list[dict[str, Any]] = []
    if isinstance(issues_raw, list):
        for item in issues_raw:
            if isinstance(item, dict):
                issues.append(item)
    payload["issues"] = issues

    major_or_critical = False
    explicit_non_blocking_only = bool(issues)
    for issue in issues:
        severity = str(issue.get("severity", "")).strip().lower()
        title = str(issue.get("title", ""))
        detail = str(issue.get("detail", ""))
        merged = f"{title} {detail}".lower()
        has_objective_blocker = any(token.lower() in merged for token in _OBJECTIVE_BLOCKER_KEYWORDS)
        explicit_non_blocking = _is_explicit_non_blocking_issue(
            merged,
            has_objective_blocker=has_objective_blocker,
        )
        explicit_non_blocking_only = explicit_non_blocking_only and explicit_non_blocking

        if severity in {"major", "critical"} and explicit_non_blocking:
            issue["severity"] = "minor"
            severity = "minor"
        if severity in {"major", "critical"}:
            major_or_critical = True

    verdict = str(payload.get("verdict", "")).strip().lower()
    if verdict == "warn" and not major_or_critical and explicit_non_blocking_only:
        payload["verdict"] = "pass"
        payload["normalization_note"] = "warn downgraded to pass for explicitly non-blocking issues only"

    return payload


def normalize_interaction_analysis(payload: dict[str, Any]) -> dict[str, Any]:
    issues_raw = payload.get("issues")
    issues: list[dict[str, Any]] = []
    if isinstance(issues_raw, list):
        for item in issues_raw:
            if isinstance(item, dict):
                issues.append(item)
    payload["issues"] = issues

    major_or_critical = False
    explicit_non_blocking_only = bool(issues)
    for issue in issues:
        severity = str(issue.get("severity", "")).strip().lower()
        title = str(issue.get("title", ""))
        detail = str(issue.get("detail", ""))
        merged = f"{title} {detail}".lower()
        has_objective_blocker = any(token.lower() in merged for token in _OBJECTIVE_BLOCKER_KEYWORDS)
        explicit_non_blocking = _is_explicit_non_blocking_issue(
            merged,
            has_objective_blocker=has_objective_blocker,
        )
        explicit_non_blocking_only = explicit_non_blocking_only and explicit_non_blocking

        if severity in {"major", "critical"} and explicit_non_blocking:
            issue["severity"] = "minor"
            severity = "minor"
        if severity in {"major", "critical"}:
            major_or_critical = True

    verdict = str(payload.get("verdict", "")).strip().lower()
    if verdict == "warn" and not major_or_critical and explicit_non_blocking_only:
        payload["verdict"] = "pass"
        payload["normalization_note"] = "warn downgraded to pass for explicitly non-blocking issues only"
    return payload


def fallback_page_analysis(
    *,
    route: str,
    reason: str,
    error: str = "",
    verdict: str = "fail",
) -> dict[str, Any]:
    resolved_verdict = verdict if verdict in VALID_VERDICTS else "fail"
    severity = "major" if resolved_verdict == "fail" else "minor"
    detail = f"route={route}; reason={reason}"
    if error:
        detail = f"{detail}; error={error}"
    return {
        "verdict": resolved_verdict,
        "confidence": 0.0,
        "summary": f"页面分析降级：{reason}",
        "information_architecture": {
            "stage_clarity": "unclear",
            "primary_action_clarity": "unclear",
            "noise_level": "high",
            "notes": "Gemini 页面分析未产出有效结构，已降级记录。",
        },
        "visual_ux": {
            "hierarchy": "poor",
            "readability": "poor",
            "feedback_signal": "poor",
            "notes": "请结合 route.errors 与截图复核。此条为结构化降级结果。",
        },
        "issues": [
            {
                "severity": severity,
                "title": "页面分析降级",
                "detail": detail,
            }
        ],
        "recommendations": [
            "复查该路由截图与 route.errors，确认页面可渲染与可交互。",
            "重试 Gemini 调用并核对网络/凭证/配额是否稳定。",
        ],
        "_degraded": True,
        "_degrade_reason": reason,
        "_route": route,
        "_error": error,
    }


def fallback_interaction_analysis(
    *,
    route: str,
    target: dict[str, Any],
    reason: str,
    error: str = "",
    verdict: str = "fail",
) -> dict[str, Any]:
    resolved_verdict = verdict if verdict in VALID_VERDICTS else "fail"
    severity = "major" if resolved_verdict == "fail" else "minor"
    detail = f"route={route}; target={target_label(target)}; reason={reason}"
    if error:
        detail = f"{detail}; error={error}"
    return {
        "verdict": resolved_verdict,
        "confidence": 0.0,
        "expected_match": "no" if resolved_verdict == "fail" else "partial",
        "summary": f"交互分析降级：{reason}",
        "functional_assessment": {
            "state_change_visible": False,
            "feedback_present": False,
            "error_signal_quality": "poor",
            "notes": "Gemini 交互分析未产出有效结构，已降级记录。",
        },
        "ux_assessment": {
            "affordance": "mixed",
            "consistency": "mixed",
            "cognitive_load": "high",
            "notes": "请结合 before/after 截图与 entry.errors 复核。",
        },
        "issues": [
            {
                "severity": severity,
                "title": "交互分析降级",
                "detail": detail,
            }
        ],
        "recommendations": [
            "复查 before/after 截图与 observed 字段，确认交互反馈是否符合预期。",
            "重试 Gemini 交互分析并检查截图文件完整性。",
        ],
        "_degraded": True,
        "_degrade_reason": reason,
        "_route": route,
        "_target_label": target_label(target),
        "_error": error,
    }


def ensure_page_analysis_payload(
    payload: dict[str, Any] | None,
    *,
    route: str,
    fallback_reason: str,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return fallback_page_analysis(route=route, reason=fallback_reason, error="payload is not object")
    normalized = dict(payload)
    verdict = str(normalized.get("verdict", "")).strip().lower()
    if verdict not in VALID_VERDICTS:
        return fallback_page_analysis(
            route=route,
            reason=fallback_reason,
            error=f"invalid verdict={verdict or 'empty'}",
            verdict="warn",
        )
    normalized["verdict"] = verdict
    normalized.setdefault("confidence", 0.5)
    normalized.setdefault("summary", "")
    if not isinstance(normalized.get("issues"), list):
        normalized["issues"] = []
    if not isinstance(normalized.get("recommendations"), list):
        normalized["recommendations"] = []
    if not isinstance(normalized.get("information_architecture"), dict):
        normalized["information_architecture"] = {
            "stage_clarity": "partial",
            "primary_action_clarity": "partial",
            "noise_level": "medium",
            "notes": "",
        }
    if not isinstance(normalized.get("visual_ux"), dict):
        normalized["visual_ux"] = {
            "hierarchy": "mixed",
            "readability": "mixed",
            "feedback_signal": "mixed",
            "notes": "",
        }
    return normalized


def ensure_interaction_analysis_payload(
    payload: dict[str, Any] | None,
    *,
    route: str,
    target: dict[str, Any],
    fallback_reason: str,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return fallback_interaction_analysis(
            route=route,
            target=target,
            reason=fallback_reason,
            error="payload is not object",
        )
    normalized = dict(payload)
    verdict = str(normalized.get("verdict", "")).strip().lower()
    if verdict not in VALID_VERDICTS:
        return fallback_interaction_analysis(
            route=route,
            target=target,
            reason=fallback_reason,
            error=f"invalid verdict={verdict or 'empty'}",
            verdict="warn",
        )
    normalized["verdict"] = verdict
    normalized.setdefault("confidence", 0.5)
    normalized.setdefault("expected_match", "partial")
    normalized.setdefault("summary", "")
    if not isinstance(normalized.get("issues"), list):
        normalized["issues"] = []
    if not isinstance(normalized.get("recommendations"), list):
        normalized["recommendations"] = []
    if not isinstance(normalized.get("functional_assessment"), dict):
        normalized["functional_assessment"] = {
            "state_change_visible": False,
            "feedback_present": False,
            "error_signal_quality": "mixed",
            "notes": "",
        }
    if not isinstance(normalized.get("ux_assessment"), dict):
        normalized["ux_assessment"] = {
            "affordance": "mixed",
            "consistency": "mixed",
            "cognitive_load": "medium",
            "notes": "",
        }
    return normalized


def read_image_bytes(path: Path) -> tuple[bytes, str]:
    raw = path.read_bytes()
    if Image is None:
        return raw, "image/png"
    try:
        with Image.open(io.BytesIO(raw)) as img:
            optimized = img.convert("RGB")
            width, height = optimized.size
            longest = max(width, height)
            max_edge = 1280
            if longest > max_edge:
                ratio = max_edge / float(longest)
                optimized = optimized.resize(
                    (max(1, int(width * ratio)), max(1, int(height * ratio))),
                    Image.LANCZOS,
                )
            buf = io.BytesIO()
            optimized.save(buf, format="JPEG", quality=72, optimize=True)
            return buf.getvalue(), "image/jpeg"
    except Exception:
        return raw, "image/png"


def _parse_float_env(name: str, default: float) -> float:
    raw = str(os.environ.get(name, "")).strip()
    if not raw:
        return default
    try:
        return float(raw)
    except Exception:
        return default


def _parse_int_env(name: str, default: int) -> int:
    raw = str(os.environ.get(name, "")).strip()
    if not raw:
        return default
    try:
        return int(raw)
    except Exception:
        return default


def _image_geometry(path: Path) -> dict[str, float] | None:
    if Image is None:
        return None
    try:
        with Image.open(path) as img:
            width, height = img.size
    except Exception:
        return None
    width = max(1, int(width))
    height = max(1, int(height))
    ratio = float(height) / float(width)
    return {"width": float(width), "height": float(height), "ratio": ratio}


def _diagnose_extreme_tall_images(image_paths: list[Path]) -> dict[str, Any] | None:
    ratio_threshold = max(
        1.0,
        _parse_float_env("CORTEXPILOT_UI_GEMINI_EXTREME_TALL_RATIO", _EXTREME_TALL_ASPECT_RATIO),
    )
    min_height_px = max(
        1,
        _parse_int_env("CORTEXPILOT_UI_GEMINI_EXTREME_TALL_MIN_HEIGHT_PX", _EXTREME_TALL_MIN_HEIGHT_PX),
    )
    findings: list[dict[str, Any]] = []
    for path in image_paths:
        geometry = _image_geometry(path)
        if not geometry:
            continue
        width = int(geometry["width"])
        height = int(geometry["height"])
        ratio = float(geometry["ratio"])
        if height >= min_height_px and ratio >= ratio_threshold:
            findings.append(
                {
                    "path": str(path),
                    "width": width,
                    "height": height,
                    "aspect_ratio_h_over_w": round(ratio, 3),
                }
            )
    if not findings:
        return None
    return {
        "diagnosis": "extreme_tall_screenshot",
        "kind": "page_structure_issue",
        "ratio_threshold": ratio_threshold,
        "min_height_px": min_height_px,
        "findings": findings,
    }


def _raise_http_400_with_image_diagnosis(*, stage: str, exc: urllib.error.HTTPError, image_paths: list[Path]) -> None:
    if int(getattr(exc, "code", 0) or 0) != 400:
        raise exc
    diagnosis = _diagnose_extreme_tall_images(image_paths)
    if diagnosis:
        details = ",".join(
            f"{item['path']}[{item['width']}x{item['height']},r={item['aspect_ratio_h_over_w']}]"
            for item in diagnosis.get("findings", [])
            if isinstance(item, dict)
        )
        raise RuntimeError(
            "gemini_http_400_extreme_tall_screenshot "
            f"stage={stage} diagnosis=page_structure_issue details={details}"
        ) from exc
    raise RuntimeError(f"gemini_http_400_bad_request stage={stage} error={exc}") from exc


@dataclass
class GeminiAnalyzer:
    api_key: str
    model: str
    request_timeout_sec: int = 75
    max_attempts: int = 3
    base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    thinking_level: str = "HIGH"
    _resolved_model: str | None = None
    _last_cache_hit: bool = False

    def _extract_text_from_response(self, payload: dict[str, Any]) -> str:
        candidates = payload.get("candidates", [])
        if not isinstance(candidates, list) or not candidates:
            return ""
        first = candidates[0] if isinstance(candidates[0], dict) else {}
        content = first.get("content", {}) if isinstance(first, dict) else {}
        parts = content.get("parts", []) if isinstance(content, dict) else []
        if not isinstance(parts, list):
            return ""
        texts: list[str] = []
        for part in parts:
            if not isinstance(part, dict):
                continue
            text = part.get("text")
            if isinstance(text, str):
                texts.append(text)
        return "\n".join(texts).strip()

    def _generate_once_with_timeout(self, *, prompt: str, images: list[tuple[bytes, str]], model: str) -> str:
        timeout_sec = max(1, int(self.request_timeout_sec))
        base_url = str(self.base_url or "").strip() or "https://generativelanguage.googleapis.com/v1beta"
        endpoint = f"{base_url.rstrip('/')}/models/{model}:generateContent"
        query = urllib.parse.urlencode({"key": self.api_key})
        url = f"{endpoint}?{query}"

        parts: list[dict[str, Any]] = [{"text": prompt}]
        for image, mime_type in images:
            parts.append(
                {
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": base64.b64encode(image).decode("ascii"),
                    }
                }
            )

        generation_config: dict[str, Any] = {"temperature": 1.0, "maxOutputTokens": 4096}
        if "gemini-3" in model:
            thinking_level = str(self.thinking_level or "").strip()
            if thinking_level:
                generation_config["thinkingConfig"] = {"thinkingLevel": thinking_level.upper()}
        body = {
            "contents": [{"parts": parts}],
            "generationConfig": generation_config,
        }
        req = urllib.request.Request(
            url,
            method="POST",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with _gemini_request_lock():
            _respect_gemini_min_interval()
            with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                raw = resp.read().decode("utf-8")
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("gemini response payload is not an object")
        text = self._extract_text_from_response(parsed)
        if not text:
            raise ValueError("gemini response text is empty")
        return text

    def _generate_with_retry(
        self,
        *,
        prompt: str,
        images: list[tuple[bytes, str]],
        model: str,
        max_attempts: int | None = None,
    ) -> str:
        attempts = max(1, int(max_attempts or self.max_attempts))
        last_exc: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                return self._generate_once_with_timeout(prompt=prompt, images=images, model=model)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt >= attempts:
                    break
                if _is_retryable_gemini_error(exc):
                    time.sleep(_retry_delay_sec(exc, attempt))
                    continue
                break
        if last_exc is None:
            raise RuntimeError("gemini call failed without explicit exception")
        raise last_exc

    def _cache_enabled(self) -> bool:
        return str(os.environ.get("CORTEXPILOT_GEMINI_CONTEXT_CACHE", "1")).strip().lower() not in {"0", "false", "no", "off"}

    def _cache_root(self) -> Path:
        raw = str(os.environ.get("CORTEXPILOT_GEMINI_CONTEXT_CACHE_DIR", "")).strip()
        if raw:
            return Path(raw).expanduser()
        return Path(".runtime-cache/cache/gemini_ui_audit")

    def _cache_key(self, *, prompt: str, images: list[tuple[bytes, str]], model: str) -> str:
        digest = hashlib.sha256()
        digest.update(model.encode("utf-8"))
        digest.update(b"\n")
        digest.update(prompt.encode("utf-8"))
        for raw, mime in images:
            digest.update(b"\n--img--\n")
            digest.update(str(mime).encode("utf-8"))
            digest.update(b"\n")
            digest.update(raw)
        return digest.hexdigest()

    def _read_cache(self, *, key: str) -> str | None:
        path = self._cache_root() / f"{key}.json"
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            text = payload.get("text")
            if isinstance(text, str) and text.strip():
                return text
        except Exception:
            return None
        return None

    def _write_cache(self, *, key: str, text: str, model: str) -> None:
        path = self._cache_root() / f"{key}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"model": model, "text": text, "cached_at": int(time.time())}
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def _generate_for_model_candidates(self, *, prompt: str, images: list[tuple[bytes, str]]) -> str:
        preferred = self._resolved_model or self.model
        last_exc: Exception | None = None
        self._last_cache_hit = False
        for candidate in _model_candidates(preferred):
            cache_key = self._cache_key(prompt=prompt, images=images, model=candidate)
            if self._cache_enabled():
                cached = self._read_cache(key=cache_key)
                if cached is not None:
                    self._resolved_model = candidate
                    self._last_cache_hit = True
                    return cached
            try:
                text = self._generate_with_retry(prompt=prompt, images=images, model=candidate)
                self._resolved_model = candidate
                if self._cache_enabled():
                    self._write_cache(key=cache_key, text=text, model=candidate)
                return text
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                message = str(exc).lower()
                # 404 model-not-found style errors are eligible for model fallback.
                if "404" in message or "not found" in message:
                    continue
                raise
        if last_exc is None:
            raise RuntimeError("gemini call failed without explicit exception")
        raise last_exc

    def analyze_page(self, *, route: str, screenshot_path: Path) -> dict[str, Any]:
        business_objective = _route_business_objective(route)
        prompt = (
            f"{PROJECT_CONTEXT}\n\n"
            f"当前页面路由: {route}\n"
            f"页面业务目标: {business_objective}\n"
            "截图说明: 该截图是该路由当前可见状态的真实页面快照。\n"
            "请优先按“业务目标是否可达、关键动作是否可执行、状态反馈是否可信”进行判断。\n"
            "任务: 对该页面做 UI/UX 与信息架构审计。\n\n"
            f"{PAGE_ANALYSIS_PROMPT}"
        )
        try:
            text = self._generate_for_model_candidates(
                prompt=prompt,
                images=[read_image_bytes(screenshot_path)],
            ).strip()
        except urllib.error.HTTPError as exc:
            _raise_http_400_with_image_diagnosis(
                stage="page",
                exc=exc,
                image_paths=[screenshot_path],
            )
        payload = parse_json_response(text)
        payload = normalize_page_analysis(payload)
        payload = ensure_page_analysis_payload(payload, route=route, fallback_reason="gemini_page_payload_invalid")
        payload["_raw"] = text
        payload["_context_cache_hit"] = bool(self._last_cache_hit)
        return payload

    def analyze_interaction(
        self,
        *,
        route: str,
        target: dict[str, Any],
        expected_effect: str,
        observed: dict[str, Any],
        before_path: Path,
        after_path: Path,
    ) -> dict[str, Any]:
        business_objective = _route_business_objective(route)
        acceptance_block = _interaction_business_acceptance(expected_effect=expected_effect, observed=observed)
        context = {
            "route": route,
            "target": target,
            "expected_effect": expected_effect,
            "observed_effect": observed,
        }
        prompt = (
            f"{PROJECT_CONTEXT}\n\n"
            "你正在审计一次真实 E2E 交互。\n"
            f"页面业务目标: {business_objective}\n"
            "截图说明: 第一张是点击前（before），第二张是点击后（after）。\n"
            "请判断该交互是否推动了预期业务流程，而不是仅比较视觉差异。\n"
            f"{acceptance_block}\n\n"
            f"交互上下文(JSON):\n{json.dumps(context, ensure_ascii=False, indent=2)}\n\n"
            f"{INTERACTION_ANALYSIS_PROMPT}"
        )
        try:
            text = self._generate_for_model_candidates(
                prompt=prompt,
                images=[read_image_bytes(before_path), read_image_bytes(after_path)],
            ).strip()
        except urllib.error.HTTPError as exc:
            _raise_http_400_with_image_diagnosis(
                stage="interaction",
                exc=exc,
                image_paths=[before_path, after_path],
            )
        payload = parse_json_response(text)
        payload = normalize_interaction_analysis(payload)
        payload = ensure_interaction_analysis_payload(
            payload,
            route=route,
            target=target,
            fallback_reason="gemini_interaction_payload_invalid",
        )
        payload["_raw"] = text
        payload["_context_cache_hit"] = bool(self._last_cache_hit)
        return payload
