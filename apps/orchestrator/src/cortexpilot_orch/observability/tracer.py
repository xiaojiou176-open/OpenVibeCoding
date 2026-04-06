from __future__ import annotations

from typing import Callable, TypeVar, Any

from cortexpilot_orch.config import get_tracing_config

try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

    _HAS_OTEL = True
except Exception:  # noqa: BLE001
    _HAS_OTEL = False


T = TypeVar("T")


def _setup_provider() -> None:
    if not _HAS_OTEL:
        return
    tracing_cfg = get_tracing_config()
    resource = Resource.create({"service.name": "cortexpilot-orchestrator"})
    provider = TracerProvider(resource=resource)
    exporter = None

    otlp_endpoint = tracing_cfg.endpoint.strip()
    otlp_protocol = tracing_cfg.protocol.strip().lower() or "grpc"
    headers_raw = tracing_cfg.headers.strip()
    console_enabled = tracing_cfg.console_enabled

    headers: dict[str, str] = {}
    if headers_raw:
        for item in headers_raw.split(","):
            if "=" not in item:
                continue
            key, value = item.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key:
                headers[key] = value

    if otlp_endpoint:
        if otlp_protocol == "http":
            try:
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # type: ignore
                    OTLPSpanExporter as HttpExporter,
                )

                exporter = HttpExporter(endpoint=otlp_endpoint, headers=headers or None)
            except Exception:
                exporter = OTLPSpanExporter(endpoint=otlp_endpoint, headers=headers or None)
        else:
            exporter = OTLPSpanExporter(endpoint=otlp_endpoint, headers=headers or None)
    elif console_enabled:
        exporter = ConsoleSpanExporter()

    if exporter is not None:
        provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)


_setup_provider()


def tracing_status() -> dict[str, Any]:
    tracing_cfg = get_tracing_config()
    otlp_endpoint = tracing_cfg.endpoint.strip()
    otlp_protocol = tracing_cfg.protocol.strip().lower() or "grpc"
    console_enabled = tracing_cfg.console_enabled
    enabled = bool(_HAS_OTEL and (otlp_endpoint or console_enabled))
    return {
        "enabled": enabled,
        "has_otel": _HAS_OTEL,
        "otlp_endpoint": otlp_endpoint or "",
        "otlp_protocol": otlp_protocol,
        "console_enabled": console_enabled,
    }


def ensure_tracing() -> dict[str, Any]:
    required = get_tracing_config().required
    status = tracing_status()
    status["required"] = required
    if required and not status.get("enabled"):
        raise RuntimeError("OTel tracing required but exporter not configured")
    return status


def get_tracer():
    if not _HAS_OTEL:
        return None
    return trace.get_tracer("cortexpilot-orchestrator")


def trace_span(name: str) -> Callable[[Callable[..., T]], Callable[..., T]]:
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        if not _HAS_OTEL:
            return func

        def wrapper(*args, **kwargs):
            tracer = get_tracer()
            if tracer is None:
                return func(*args, **kwargs)
            with tracer.start_as_current_span(name):
                return func(*args, **kwargs)

        return wrapper

    return decorator
