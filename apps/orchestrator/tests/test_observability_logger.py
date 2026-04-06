import json
import logging
from pathlib import Path
from types import SimpleNamespace

from cortexpilot_orch.observability import logger as logger_module


def test_json_line_formatter_includes_request_id_from_meta() -> None:
    formatter = logger_module.JsonLineFormatter()
    record = logging.LogRecord(
        name="cortexpilot",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="evt",
        args=(),
        exc_info=None,
    )
    record.component = "api"
    record.event = "TEST_EVENT"
    record.run_id = "run_1"
    record.meta = {"request_id": "req_123", "x": 1}

    payload = json.loads(formatter.format(record))
    assert payload["component"] == "api"
    assert payload["event"] == "TEST_EVENT"
    assert payload["run_id"] == "run_1"
    assert payload["request_id"] == "req_123"
    assert payload["meta"]["x"] == 1
    assert payload["surface"] == "backend"
    assert payload["domain"] == "api"
    assert payload["service"] == "cortexpilot-orchestrator"
    assert payload["lane"] == "access"
    assert payload["correlation_kind"] == "run"
    assert payload["redaction_version"] == "redaction.v1"


def test_json_line_formatter_prefers_explicit_request_id() -> None:
    formatter = logger_module.JsonLineFormatter()
    record = logging.LogRecord(
        name="cortexpilot",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="evt",
        args=(),
        exc_info=None,
    )
    record.component = "api"
    record.event = "TEST_EVENT"
    record.run_id = "run_1"
    record.request_id = "req_explicit"
    record.meta = {"request_id": "req_meta"}

    payload = json.loads(formatter.format(record))
    assert payload["request_id"] == "req_explicit"


def test_resolve_log_level_defaults_to_debug(monkeypatch) -> None:
    monkeypatch.delenv("CORTEXPILOT_LOG_LEVEL", raising=False)
    level = logger_module._resolve_log_level()
    assert level == logging.DEBUG


def test_json_line_formatter_handles_non_dict_meta() -> None:
    formatter = logger_module.JsonLineFormatter()
    record = logging.LogRecord(
        name="cortexpilot",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="evt",
        args=(),
        exc_info=None,
    )
    record.meta = "raw-meta"

    try:
        formatter.format(record)
    except ValueError as exc:
        assert "meta must be an object" in str(exc)
    else:  # pragma: no cover - defensive failure branch
        raise AssertionError("expected non-dict meta to raise ValueError")


def test_sanitize_payload_redacts_sensitive_keys_and_values() -> None:
    synthetic_item_secret = "sk-" + "abcdefghijklmnop"
    sanitized = logger_module._sanitize_payload(
        {
            "token": "secret-token",
            "nested": {
                "Authorization": "Bearer abcdefghijklmnop",
                "url": "https://example.com?access_token=abc123456",
            },
            "items": [{"password": "pw"}, synthetic_item_secret],
            "pair": ("public", "secret=abc"),
        }
    )

    assert sanitized["token"] == "[REDACTED]"
    assert sanitized["nested"]["Authorization"] == "[REDACTED]"
    assert sanitized["nested"]["url"].count("[REDACTED]") == 1
    assert sanitized["items"][0]["password"] == "[REDACTED]"
    assert sanitized["items"][1] == "[REDACTED]"
    assert sanitized["pair"][0] == "public"


def test_level_and_access_filters_cover_accept_and_reject_paths() -> None:
    level_filter = logger_module._LevelAtLeastFilter(logging.WARNING)
    low_record = logging.LogRecord("cortexpilot", logging.INFO, __file__, 1, "msg", (), None)
    high_record = logging.LogRecord("cortexpilot", logging.ERROR, __file__, 1, "msg", (), None)
    assert level_filter.filter(low_record) is False
    assert level_filter.filter(high_record) is True

    access_filter = logger_module._AccessEventFilter()
    api_record = logging.LogRecord("cortexpilot", logging.INFO, __file__, 1, "msg", (), None)
    api_record.component = "api"
    assert access_filter.filter(api_record) is True

    http_event = logging.LogRecord("cortexpilot", logging.INFO, __file__, 1, "msg", (), None)
    http_event.event = "HTTP_REQUEST"
    assert access_filter.filter(http_event) is True

    other = logging.LogRecord("cortexpilot", logging.INFO, __file__, 1, "msg", (), None)
    other.component = "worker"
    other.event = "RUN"
    assert access_filter.filter(other) is False


def test_gzip_rotating_file_handler_compresses_rotated_files(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(logger_module.RotatingFileHandler, "doRollover", lambda self: None)
    log_path = tmp_path / "cortexpilot.log"
    rotated = tmp_path / "cortexpilot.log.1"
    rotated.write_text("old-log", encoding="utf-8")

    handler = logger_module._GzipRotatingFileHandler(log_path, maxBytes=1, backupCount=1, encoding="utf-8")
    handler.doRollover()

    assert rotated.exists() is False
    assert (tmp_path / "cortexpilot.log.1.gz").exists() is True


def test_get_logger_initializes_handlers_once(monkeypatch, tmp_path: Path) -> None:
    logger = logging.getLogger("cortexpilot")
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    monkeypatch.setattr(
        logger_module,
        "_build_log_targets",
        lambda: {
            "runtime": tmp_path / "runtime.jsonl",
            "error": tmp_path / "error.jsonl",
            "access": tmp_path / "access.jsonl",
            "e2e": tmp_path / "e2e.jsonl",
            "governance": tmp_path / "governance.jsonl",
        },
    )

    def _fake_make_file_handler(path: Path, level: int) -> logging.Handler:
        handler = logging.NullHandler()
        handler.setLevel(level)
        return handler

    monkeypatch.setattr(logger_module, "_make_file_handler", _fake_make_file_handler)
    first = logger_module.get_logger()
    handler_count = len(first.handlers)
    second = logger_module.get_logger()

    assert first is second
    assert handler_count == len(second.handlers)
    assert handler_count == 6


def test_log_event_sanitizes_metadata_and_uses_level_fallback(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _DummyLogger:
        def log(self, level: int, event: str, extra=None) -> None:
            captured["level"] = level
            captured["event"] = event
            captured["extra"] = extra

    monkeypatch.setattr(logger_module, "get_logger", lambda: _DummyLogger())
    monkeypatch.setattr(
        logger_module,
        "get_logging_config",
        lambda: SimpleNamespace(trace_id="trace-default", max_bytes=1024, backup_count=3),
    )

    logger_module.log_event(
        level="nonexistent",
        component="api",
        event="token=abc123",
        run_id="run-1",
        meta={"request_id": "req-1", "token": "abc"},
    )

    assert captured["level"] == logging.INFO
    extra = captured["extra"]
    assert isinstance(extra, dict)
    assert extra["request_id"] == "req-1"
    assert extra["trace_id"] == "trace-default"
    assert extra["meta"]["token"] == "[REDACTED]"


def test_json_line_formatter_rejects_invalid_surface() -> None:
    formatter = logger_module.JsonLineFormatter()
    record = logging.LogRecord("cortexpilot", logging.INFO, __file__, 1, "evt", (), None)
    record.component = "api"
    record.event = "TEST_EVENT"
    record.surface = "frontend"

    try:
        formatter.format(record)
    except ValueError as exc:
        assert "surface must be one of" in str(exc)
    else:  # pragma: no cover - defensive failure branch
        raise AssertionError("expected invalid surface to raise ValueError")


def test_sanitize_payload_redacts_parent_sensitive_key() -> None:
    assert logger_module._sanitize_payload("plain", parent_key="token") == "[REDACTED]"
    assert logger_module._sanitize_payload("plain", parent_key="safe") == "plain"


def test_resolve_logs_root_and_targets(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        logger_module,
        "get_runtime_config",
        lambda: SimpleNamespace(logs_root=tmp_path / "logs" / ".." / "logs"),
    )
    resolved = logger_module._resolve_logs_root()
    targets = logger_module._build_log_targets()

    assert resolved == (tmp_path / "logs").resolve()
    assert targets["runtime"].name == "cortexpilot-runtime.jsonl"
    assert targets["error"].name == "cortexpilot-error.jsonl"
    assert targets["access"].name == "cortexpilot-access.jsonl"
    assert targets["e2e"].name == "cortexpilot-e2e.jsonl"


def test_gzip_rotating_file_handler_skips_already_compressed(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(logger_module.RotatingFileHandler, "doRollover", lambda self: None)
    log_path = tmp_path / "cortexpilot.log"
    compressed = tmp_path / "cortexpilot.log.1.gz"
    compressed.write_bytes(b"compressed")

    handler = logger_module._GzipRotatingFileHandler(log_path, maxBytes=1, backupCount=1, encoding="utf-8")
    handler.doRollover()

    assert compressed.exists() is True


def test_make_file_handler_uses_config(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        logger_module,
        "get_logging_config",
        lambda: SimpleNamespace(max_bytes=256, backup_count=2, trace_id="trace-id"),
    )

    path = tmp_path / "nested" / "runtime.jsonl"
    handler = logger_module._make_file_handler(path, logging.INFO)

    assert path.parent.exists() is True
    assert handler.level == logging.INFO
    assert isinstance(handler.formatter, logger_module.JsonLineFormatter)
