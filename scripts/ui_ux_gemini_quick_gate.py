#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / ".runtime-cache" / "test_output" / "ui_ux_gemini_quick_gate"
MODEL_DEFAULT = "gemini-3.0-flash"
KEY_ENV_SELECTOR = "CORTEXPILOT_UI_GEMINI_KEY_ENV"
KEY_ENV_DEFAULT = "GEMINI_API_KEY"
MODEL_ENV = "CORTEXPILOT_UI_GEMINI_MODEL"
REQUEST_TIMEOUT_ENV = "CORTEXPILOT_UI_GEMINI_TIMEOUT_SEC"
REQUEST_TIMEOUT_DEFAULT = 45
MAX_FILE_CHARS = 8000
MAX_TOTAL_CHARS = 32000
ALLOWED_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx", ".css", ".scss"}
ALLOWED_PREFIXES = ("apps/dashboard/", "apps/desktop/")


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_filename(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-") or "report"


def _load_dotenv_value(dotenv_path: Path, key: str) -> str:
    if not dotenv_path.exists():
        return ""
    try:
        for line in dotenv_path.read_text(encoding="utf-8", errors="replace").splitlines():
            raw = line.strip()
            if not raw or raw.startswith("#") or "=" not in raw:
                continue
            lhs, rhs = raw.split("=", 1)
            if lhs.strip() != key:
                continue
            return rhs.strip().strip('"').strip("'")
    except Exception:
        return ""
    return ""


def _resolve_api_key(key_env_name: str) -> str:
    env_value = os.environ.get(key_env_name, "").strip()
    if env_value:
        return env_value

    for env_name in (".env.local", ".env"):
        resolved = _load_dotenv_value(ROOT / env_name, key_env_name).strip()
        if resolved:
            os.environ[key_env_name] = resolved
            return resolved

    try:
        result = subprocess.run(
            ["zsh", "-lc", f"printenv {key_env_name} 2>/dev/null || true"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return ""
    resolved = (result.stdout or "").strip().splitlines()
    if not resolved:
        return ""
    candidate = resolved[0].strip()
    if candidate:
        os.environ[key_env_name] = candidate
    return candidate


def _run_git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {msg}")
    return proc.stdout


def _is_target_ui_file(path: str) -> bool:
    normalized = path.strip()
    if not normalized or not normalized.endswith(tuple(ALLOWED_EXTENSIONS)):
        return False
    return normalized.startswith(ALLOWED_PREFIXES)


def _staged_ui_files() -> list[str]:
    raw = _run_git("diff", "--cached", "--name-only", "--diff-filter=ACMR")
    candidates = [line.strip() for line in raw.splitlines() if line.strip()]
    return [path for path in candidates if _is_target_ui_file(path)]


def _prepush_ui_files() -> list[str]:
    """
    pre-push commonly has no staged files.
    To avoid blocking on historical debt, default to latest-commit scope.
    Optional override: CORTEXPILOT_UI_GEMINI_QUICK_SCOPE=upstream_range.
    """
    scope = (os.environ.get("CORTEXPILOT_UI_GEMINI_QUICK_SCOPE", "head_commit") or "head_commit").strip().lower()
    candidates: list[str] = []
    if scope == "upstream_range":
        try:
            raw = _run_git("diff", "--name-only", "--diff-filter=ACMR", "@{upstream}...HEAD")
            candidates = [line.strip() for line in raw.splitlines() if line.strip()]
            return [path for path in candidates if _is_target_ui_file(path)]
        except Exception:
            candidates = []
    # Default and fallback: latest commit only.
    try:
        raw = _run_git("diff", "--name-only", "--diff-filter=ACMR", "HEAD^..HEAD")
        candidates = [line.strip() for line in raw.splitlines() if line.strip()]
    except Exception:
        try:
            raw = _run_git("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD")
            candidates = [line.strip() for line in raw.splitlines() if line.strip()]
        except Exception:
            candidates = []
    return [path for path in candidates if _is_target_ui_file(path)]


def _read_staged_file(path: str) -> str:
    proc = subprocess.run(
        ["git", "show", f":{path}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        return proc.stdout
    fallback = ROOT / path
    if fallback.exists():
        return fallback.read_text(encoding="utf-8", errors="replace")
    msg = (proc.stderr or "").strip()
    raise RuntimeError(f"cannot read staged file {path}: {msg}")


def _build_code_payload(paths: list[str]) -> tuple[list[dict[str, Any]], int]:
    total = 0
    results: list[dict[str, Any]] = []
    for path in paths:
        content = _read_staged_file(path)
        original_len = len(content)
        budget_left = max(0, MAX_TOTAL_CHARS - total)
        if budget_left <= 0:
            break
        capped = min(MAX_FILE_CHARS, budget_left)
        sampled = content[:capped]
        total += len(sampled)
        results.append(
            {
                "path": path,
                "original_chars": original_len,
                "sampled_chars": len(sampled),
                "truncated": len(sampled) < original_len,
                "content": sampled,
            }
        )
    return results, total


def _extract_text_from_gemini_payload(payload: dict[str, Any]) -> str:
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return ""
    first = candidates[0] if isinstance(candidates[0], dict) else {}
    content = first.get("content") if isinstance(first, dict) else {}
    parts = content.get("parts") if isinstance(content, dict) else None
    if not isinstance(parts, list):
        return ""
    fragments: list[str] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        text = part.get("text")
        if isinstance(text, str):
            fragments.append(text)
    return "\n".join(fragments).strip()


def _parse_json_object(raw_text: str) -> dict[str, Any]:
    candidate = raw_text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```[a-zA-Z]*\n?", "", candidate)
        candidate = candidate.rstrip("`").strip()
    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    match = re.search(r"\{[\s\S]*\}", candidate)
    if not match:
        raise ValueError("gemini response is not valid JSON object")
    parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("gemini response JSON is not object")
    return parsed


def _build_prompt(file_payload: list[dict[str, Any]]) -> str:
    rules = [
        "Focus on semantic UI/UX quality for product readiness.",
        "Prioritize blockers over style preferences.",
        "Check accessibility, interaction semantics, state feedback, and user guidance.",
        "Report issue severity as one of: error, warn, info.",
        "Only use severity=error for true blockers that can break key user journeys.",
    ]
    schema = {
        "summary": "short overall conclusion",
        "findings": [
            {
                "severity": "error|warn|info",
                "file": "relative path",
                "line": "optional line number or null",
                "title": "brief issue title",
                "detail": "concrete issue detail",
                "recommendation": "actionable fix",
            }
        ],
    }
    return (
        "You are a strict UI/UX gate reviewer for CortexPilot frontend code. "
        "Audit only the provided staged snippets and return JSON only.\n\n"
        f"Rules:\n- " + "\n- ".join(rules) + "\n\n"
        f"Expected JSON schema:\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
        f"Staged snippets:\n{json.dumps(file_payload, ensure_ascii=False)}"
    )


def _gemini_generate_content(*, api_key: str, model: str, prompt: str, timeout_sec: int) -> dict[str, Any]:
    base_url = "https://generativelanguage.googleapis.com/v1beta"
    endpoint = f"{base_url}/models/{model}:generateContent"
    query = urllib.parse.urlencode({"key": api_key})
    url = f"{endpoint}?{query}"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 4096,
            "responseMimeType": "application/json",
        },
    }
    req = urllib.request.Request(
        url,
        method="POST",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=max(1, timeout_sec)) as resp:
        raw = resp.read().decode("utf-8")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("gemini response payload is not an object")
    return parsed


def _resolve_model_candidates(model: str) -> list[str]:
    primary = (model or "").strip() or MODEL_DEFAULT
    # Keep user-requested model first, then fall back to widely available flash variants.
    candidates = [primary, "gemini-3-flash-preview", "gemini-2.5-flash"]
    deduped: list[str] = []
    for item in candidates:
        if item and item not in deduped:
            deduped.append(item)
    return deduped


def _normalize_findings(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    findings: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        severity = str(item.get("severity", "")).strip().lower()
        if severity not in {"error", "warn", "info"}:
            severity = "warn"
        findings.append(
            {
                "severity": severity,
                "file": str(item.get("file", "")).strip(),
                "line": item.get("line"),
                "title": str(item.get("title", "")).strip(),
                "detail": str(item.get("detail", "")).strip(),
                "recommendation": str(item.get("recommendation", "")).strip(),
            }
        )
    return findings


def _persist_report(report: dict[str, Any]) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = _safe_filename(_now_iso().replace(":", "-"))
    path = OUTPUT_DIR / f"report-{ts}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUTPUT_DIR / "latest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> int:
    key_env_name = os.environ.get(KEY_ENV_SELECTOR, KEY_ENV_DEFAULT).strip() or KEY_ENV_DEFAULT
    model = os.environ.get(MODEL_ENV, MODEL_DEFAULT).strip() or MODEL_DEFAULT
    timeout_sec = int(os.environ.get(REQUEST_TIMEOUT_ENV, str(REQUEST_TIMEOUT_DEFAULT)))

    try:
        paths = _staged_ui_files()
        source = "staged"
        if not paths:
            paths = _prepush_ui_files()
            source = "prepush_range"
    except Exception as exc:
        report = {"status": "error", "reason": "staged_files_discovery_failed", "error": str(exc), "generated_at": _now_iso()}
        _persist_report(report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2

    if not paths:
        report = {
            "status": "skipped",
            "reason": "no_frontend_ui_files_in_scope",
            "model": model,
            "key_env_name": key_env_name,
            "generated_at": _now_iso(),
        }
        _persist_report(report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    api_key = _resolve_api_key(key_env_name)
    if not api_key:
        report = {
            "status": "error",
            "reason": "missing_api_key",
            "key_env_name": key_env_name,
            "model": model,
            "generated_at": _now_iso(),
        }
        _persist_report(report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2

    snippets, sampled_total = _build_code_payload(paths)
    prompt = _build_prompt(snippets)
    selected_model = model
    try:
        payload: dict[str, Any] | None = None
        last_http_error: urllib.error.HTTPError | None = None
        for candidate_model in _resolve_model_candidates(model):
            selected_model = candidate_model
            try:
                payload = _gemini_generate_content(
                    api_key=api_key,
                    model=candidate_model,
                    prompt=prompt,
                    timeout_sec=timeout_sec,
                )
                break
            except urllib.error.HTTPError as exc:
                # Auto-fallback only for model-not-found path; all other HTTP failures remain fail-closed.
                if getattr(exc, "code", None) != 404:
                    raise
                last_http_error = exc
        if payload is None:
            if last_http_error is not None:
                raise last_http_error
            raise RuntimeError("no gemini model candidate succeeded")
        text = _extract_text_from_gemini_payload(payload)
        if not text:
            raise ValueError("empty gemini text response")
        parsed = _parse_json_object(text)
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except Exception:
            detail = str(exc)
        report = {
            "status": "error",
            "reason": "gemini_http_error_fail_closed",
            "http_status": getattr(exc, "code", None),
            "detail": detail[:1200],
            "model": selected_model,
            "generated_at": _now_iso(),
        }
        _persist_report(report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2
    except (urllib.error.URLError, TimeoutError) as exc:
        report = {
            "status": "error",
            "reason": "gemini_network_error_fail_closed",
            "detail": str(exc),
            "model": selected_model,
            "generated_at": _now_iso(),
        }
        _persist_report(report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2
    except Exception as exc:
        report = {
            "status": "error",
            "reason": "gemini_unexpected_error_fail_closed",
            "detail": str(exc),
            "model": selected_model,
            "generated_at": _now_iso(),
        }
        _persist_report(report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2

    findings = _normalize_findings(parsed.get("findings"))
    summary = str(parsed.get("summary", "")).strip()
    has_error = any(item.get("severity") == "error" for item in findings)
    report = {
        "status": "fail" if has_error else "pass",
        "summary": summary,
        "source": source,
        "model": selected_model,
        "requested_model": model,
        "key_env_name": key_env_name,
        "staged_files_count": len(paths),
        "sampled_total_chars": sampled_total,
        "findings": findings,
        "generated_at": _now_iso(),
    }
    _persist_report(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if has_error else 0


if __name__ == "__main__":
    sys.exit(main())
