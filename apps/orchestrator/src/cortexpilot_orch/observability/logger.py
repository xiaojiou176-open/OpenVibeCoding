from __future__ import annotations

import json
import logging
import re
import shutil
import gzip
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from cortexpilot_orch.config import get_logging_config, get_runtime_config


def _now_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


_SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "authorization",
    "credential",
    "private_key",
    "gemini_api_key",
    "equilibrium_api_key",
    "openai_api_key",
}
_SENSITIVE_KEY_PARTS = ("token", "secret", "key", "password", "credential", "auth", "cert")
_SENSITIVE_VALUE_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9]{12,}\b"),
    re.compile(r"\bbearer\s+[A-Za-z0-9._\-]{12,}\b", re.IGNORECASE),
    re.compile(r"([?&](?:access_token|token|key|secret|password|credential|auth|cert)=)[^&\s]+", re.IGNORECASE),
]
_REDACTION_VERSION = "redaction.v1"
_ALLOWED_DOMAINS = {"runtime", "api", "ui", "desktop", "ci", "e2e", "test", "governance"}
_ALLOWED_SURFACES = {"backend", "dashboard", "desktop", "ci", "tooling"}
_ALLOWED_SOURCE_KINDS = {"app_log", "test_log", "ci_log", "artifact_manifest", "event_stream"}
_ALLOWED_LANES = {"runtime", "error", "access", "e2e", "ci", "governance"}
_ALLOWED_CORRELATION_KINDS = {"run", "session", "test", "request", "trace", "none"}


def _redact_text(value: str) -> str:
    text = value
    for pattern in _SENSITIVE_VALUE_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def _is_sensitive_key(key: str) -> bool:
    normalized = key.strip().lower()
    if normalized in _SENSITIVE_KEYS:
        return True
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def _sanitize_payload(value: Any, parent_key: str = "") -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_lower = str(key).strip().lower()
            if _is_sensitive_key(key_lower):
                sanitized[str(key)] = "[REDACTED]"
                continue
            sanitized[str(key)] = _sanitize_payload(item, parent_key=key_lower)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_payload(item, parent_key=parent_key) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_payload(item, parent_key=parent_key) for item in value)
    if isinstance(value, str):
        if _is_sensitive_key(parent_key):
            return "[REDACTED]"
        return _redact_text(value)
    return value


def _normalize_string(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return ""
    return str(value).strip()


def _normalize_required_string(value: Any, *, field: str) -> str:
    normalized = _normalize_string(value)
    if not normalized:
        raise ValueError(f"{field} must be a non-empty string")
    return normalized


def _normalize_enum(value: Any, *, field: str, allowed: set[str], fallback: str) -> str:
    candidate = _normalize_string(value) or fallback
    if candidate not in allowed:
        raise ValueError(f"{field} must be one of: {', '.join(sorted(allowed))}")
    return candidate


class _LevelAtLeastFilter(logging.Filter):
    def __init__(self, min_level: int) -> None:
        super().__init__()
        self._min_level = min_level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno >= self._min_level


class _AccessEventFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        event = str(getattr(record, "event", "") or "").upper()
        component = str(getattr(record, "component", "") or "").lower()
        return component == "api" or event.startswith("HTTP_") or event.startswith("API_")


def _resolve_logs_root() -> Path:
    return get_runtime_config().logs_root.resolve()


def _infer_domain(component: str, event: str) -> str:
    normalized_component = component.strip().lower()
    normalized_event = event.strip().lower()
    if normalized_component == "api" or normalized_event.startswith("http_") or normalized_event.startswith("api_"):
        return "api"
    if normalized_component == "e2e":
        return "e2e"
    if normalized_component in {"dashboard", "ui"}:
        return "ui"
    if normalized_component == "desktop":
        return "desktop"
    if normalized_component in {"ci", "governance"}:
        return normalized_component
    if normalized_component == "test":
        return "test"
    return "runtime"


def _infer_surface(component: str) -> str:
    normalized_component = component.strip().lower()
    if normalized_component in {"dashboard", "ui"}:
        return "dashboard"
    if normalized_component == "desktop":
        return "desktop"
    if normalized_component in {"ci", "governance"}:
        return "ci"
    if normalized_component == "e2e":
        return "tooling"
    return "backend"


def _infer_service(surface: str, component: str) -> str:
    if surface == "dashboard":
        return "cortexpilot-dashboard"
    if surface == "desktop":
        return "cortexpilot-desktop"
    if surface == "ci":
        return "cortexpilot-ci"
    if component.strip().lower() == "api":
        return "cortexpilot-orchestrator"
    return "cortexpilot-tooling"


def _infer_lane(component: str, event: str, level: str) -> str:
    normalized_component = component.strip().lower()
    normalized_event = event.strip().upper()
    normalized_level = level.strip().upper()
    if normalized_component == "e2e":
        return "e2e"
    if normalized_component in {"ci", "governance"}:
        return "governance" if normalized_component == "governance" else "ci"
    if normalized_component == "api" or normalized_event.startswith("HTTP_") or normalized_event.startswith("API_"):
        return "access"
    if normalized_level in {"WARNING", "ERROR", "CRITICAL"}:
        return "error"
    return "runtime"


def _infer_correlation_kind(payload: dict[str, str]) -> str:
    for field, correlation in (
        ("run_id", "run"),
        ("session_id", "session"),
        ("test_id", "test"),
        ("request_id", "request"),
        ("trace_id", "trace"),
    ):
        if payload.get(field, "").strip():
            return correlation
    return "none"


def _build_log_targets() -> dict[str, Path]:
    root = _resolve_logs_root()
    return {
        "runtime": root / "runtime" / "cortexpilot-runtime.jsonl",
        "error": root / "error" / "cortexpilot-error.jsonl",
        "access": root / "access" / "cortexpilot-access.jsonl",
        "e2e": root / "e2e" / "cortexpilot-e2e.jsonl",
        "governance": root / "governance" / "cortexpilot-governance.jsonl",
    }


class _GzipRotatingFileHandler(RotatingFileHandler):
    def doRollover(self) -> None:
        super().doRollover()
        for idx in range(self.backupCount, 0, -1):
            rotated = Path(f"{self.baseFilename}.{idx}")
            if not rotated.exists() or rotated.suffix == ".gz":
                continue
            compressed = Path(f"{rotated}.gz")
            with rotated.open("rb") as src, gzip.open(compressed, "wb") as dst:
                shutil.copyfileobj(src, dst)
            rotated.unlink()


def _make_file_handler(path: Path, level: int) -> logging.FileHandler:
    path.parent.mkdir(parents=True, exist_ok=True)
    logging_cfg = get_logging_config()
    max_bytes = int(logging_cfg.max_bytes)
    backup_count = int(logging_cfg.backup_count)
    handler = _GzipRotatingFileHandler(path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8")
    handler.setLevel(level)
    handler.setFormatter(JsonLineFormatter())
    return handler


class JsonLineFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        meta = getattr(record, "meta", {})
        if not isinstance(meta, dict):
            raise ValueError("meta must be an object")
        meta = _sanitize_payload(meta)
        request_id = getattr(record, "request_id", "") or meta.get("request_id", "")
        trace_id = getattr(record, "trace_id", "") or meta.get("trace_id", "") or get_logging_config().trace_id
        event_name = _normalize_required_string(
            _sanitize_payload(getattr(record, "event", record.getMessage())),
            field="event",
        )
        component = _normalize_required_string(getattr(record, "component", "system"), field="component")
        domain = _normalize_enum(
            getattr(record, "domain", "") or meta.get("domain", "") or _infer_domain(component, event_name),
            field="domain",
            allowed=_ALLOWED_DOMAINS,
            fallback="runtime",
        )
        surface = _normalize_enum(
            getattr(record, "surface", "") or meta.get("surface", "") or _infer_surface(component),
            field="surface",
            allowed=_ALLOWED_SURFACES,
            fallback="backend",
        )
        service = _normalize_required_string(
            getattr(record, "service", "") or meta.get("service", "") or _infer_service(surface, component),
            field="service",
        )
        source_kind = _normalize_enum(
            getattr(record, "source_kind", "") or meta.get("source_kind", "app_log"),
            field="source_kind",
            allowed=_ALLOWED_SOURCE_KINDS,
            fallback="app_log",
        )
        payload = {
            "ts": _now_ts(),
            "level": record.levelname,
            "domain": domain,
            "surface": surface,
            "service": service,
            "component": component,
            "event": event_name,
            "lane": _normalize_enum(
                getattr(record, "lane", "") or meta.get("lane", "") or _infer_lane(component, event_name, record.levelname),
                field="lane",
                allowed=_ALLOWED_LANES,
                fallback="runtime",
            ),
            "run_id": _normalize_string(getattr(record, "run_id", "")),
            "request_id": _normalize_string(request_id),
            "trace_id": _normalize_string(trace_id),
            "session_id": _normalize_string(getattr(record, "session_id", "") or meta.get("session_id", "")),
            "test_id": _normalize_string(getattr(record, "test_id", "") or meta.get("test_id", "")),
            "source_kind": source_kind,
            "artifact_kind": _normalize_string(getattr(record, "artifact_kind", "") or meta.get("artifact_kind", "")),
            "correlation_kind": "",
            "meta": meta,
            "redaction_version": _REDACTION_VERSION,
            "schema_version": get_logging_config().schema_version,
        }
        payload["correlation_kind"] = _normalize_enum(
            getattr(record, "correlation_kind", "") or meta.get("correlation_kind", "") or _infer_correlation_kind(payload),
            field="correlation_kind",
            allowed=_ALLOWED_CORRELATION_KINDS,
            fallback="none",
        )
        return json.dumps(payload, ensure_ascii=False)


def _resolve_log_level() -> int:
    return logging.DEBUG


def get_logger() -> logging.Logger:
    logger = logging.getLogger("cortexpilot")
    if logger.handlers:
        return logger
    logger.setLevel(_resolve_log_level())

    handler = logging.StreamHandler()
    handler.setLevel(_resolve_log_level())
    handler.setFormatter(JsonLineFormatter())
    logger.addHandler(handler)

    targets = _build_log_targets()

    runtime_handler = _make_file_handler(targets["runtime"], logging.DEBUG)
    logger.addHandler(runtime_handler)

    error_handler = _make_file_handler(targets["error"], logging.WARNING)
    error_handler.addFilter(_LevelAtLeastFilter(logging.WARNING))
    logger.addHandler(error_handler)

    access_handler = _make_file_handler(targets["access"], logging.INFO)
    access_handler.addFilter(_AccessEventFilter())
    logger.addHandler(access_handler)

    e2e_handler = _make_file_handler(targets["e2e"], logging.INFO)
    e2e_handler.addFilter(lambda record: str(getattr(record, "component", "")).lower() == "e2e")
    logger.addHandler(e2e_handler)

    governance_handler = _make_file_handler(targets["governance"], logging.INFO)
    governance_handler.addFilter(
        lambda record: str(getattr(record, "lane", "")).lower() == "governance"
        or str(getattr(record, "component", "")).lower() == "governance"
    )
    logger.addHandler(governance_handler)

    return logger


def log_event(
    level: str,
    component: str,
    event: str,
    run_id: str = "",
    meta: dict[str, Any] | None = None,
    request_id: str = "",
    trace_id: str = "",
    session_id: str = "",
    test_id: str = "",
    domain: str = "",
    surface: str = "",
    source_kind: str = "app_log",
    artifact_kind: str = "",
) -> None:
    logger = get_logger()
    metadata = _sanitize_payload(meta or {})
    resolved_domain = domain or metadata.get("domain", "") or _infer_domain(component, event)
    resolved_surface = surface or metadata.get("surface", "") or _infer_surface(component)
    resolved_service = metadata.get("service", "") or _infer_service(str(resolved_surface), component)
    resolved_lane = metadata.get("lane", "") or _infer_lane(component, event, level)
    extra = {
        "component": component,
        "event": _sanitize_payload(event),
        "run_id": run_id,
        "request_id": request_id or metadata.get("request_id", ""),
        "trace_id": trace_id or metadata.get("trace_id", "") or get_logging_config().trace_id,
        "session_id": session_id or metadata.get("session_id", ""),
        "test_id": test_id or metadata.get("test_id", ""),
        "domain": resolved_domain,
        "surface": resolved_surface,
        "service": resolved_service,
        "lane": resolved_lane,
        "source_kind": source_kind or metadata.get("source_kind", "app_log"),
        "artifact_kind": artifact_kind or metadata.get("artifact_kind", ""),
        "correlation_kind": _infer_correlation_kind(
            {
                "run_id": run_id,
                "session_id": session_id or metadata.get("session_id", ""),
                "test_id": test_id or metadata.get("test_id", ""),
                "request_id": request_id or metadata.get("request_id", ""),
                "trace_id": trace_id or metadata.get("trace_id", "") or get_logging_config().trace_id,
            }
        ),
        "meta": metadata,
    }
    logger.log(getattr(logging, level.upper(), logging.INFO), event, extra=extra)
