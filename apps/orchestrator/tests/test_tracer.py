import importlib
import sys
import types


def test_tracer_with_fake_otel(monkeypatch) -> None:
    captured = {"provider": None}

    class DummySpan:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class DummyTracer:
        def start_as_current_span(self, name: str):
            return DummySpan()

    def set_tracer_provider(provider):
        captured["provider"] = provider

    def get_tracer(name: str):
        return DummyTracer()

    trace_mod = types.SimpleNamespace(
        set_tracer_provider=set_tracer_provider,
        get_tracer=get_tracer,
    )

    class DummyResource:
        @staticmethod
        def create(attrs):
            return {"attrs": attrs}

    class DummyTracerProvider:
        def __init__(self, resource=None):
            self.resource = resource
            self.processors = []

        def add_span_processor(self, processor):
            self.processors.append(processor)

    class DummyBatchSpanProcessor:
        def __init__(self, exporter):
            self.exporter = exporter

    class DummyConsoleExporter:
        pass

    class DummyOtlpExporter:
        def __init__(self, endpoint=None, headers=None):
            self.endpoint = endpoint
            self.headers = headers

    otel = types.ModuleType("opentelemetry")
    otel_trace = types.ModuleType("opentelemetry.trace")
    otel_trace.set_tracer_provider = trace_mod.set_tracer_provider
    otel_trace.get_tracer = trace_mod.get_tracer
    otel_sdk_resources = types.ModuleType("opentelemetry.sdk.resources")
    otel_sdk_resources.Resource = DummyResource
    otel_sdk_trace = types.ModuleType("opentelemetry.sdk.trace")
    otel_sdk_trace.TracerProvider = DummyTracerProvider
    otel_sdk_export = types.ModuleType("opentelemetry.sdk.trace.export")
    otel_sdk_export.BatchSpanProcessor = DummyBatchSpanProcessor
    otel_sdk_export.ConsoleSpanExporter = DummyConsoleExporter
    otel_otlp = types.ModuleType("opentelemetry.exporter.otlp.proto.grpc.trace_exporter")
    otel_otlp.OTLPSpanExporter = DummyOtlpExporter

    monkeypatch.setitem(sys.modules, "opentelemetry", otel)
    monkeypatch.setitem(sys.modules, "opentelemetry.trace", otel_trace)
    monkeypatch.setitem(sys.modules, "opentelemetry.sdk.resources", otel_sdk_resources)
    monkeypatch.setitem(sys.modules, "opentelemetry.sdk.trace", otel_sdk_trace)
    monkeypatch.setitem(sys.modules, "opentelemetry.sdk.trace.export", otel_sdk_export)
    monkeypatch.setitem(
        sys.modules,
        "opentelemetry.exporter.otlp.proto.grpc.trace_exporter",
        otel_otlp,
    )

    tracer_module = importlib.reload(importlib.import_module("cortexpilot_orch.observability.tracer"))

    assert tracer_module.get_tracer() is not None

    @tracer_module.trace_span("demo")
    def _work(x: int) -> int:
        return x + 1

    assert _work(1) == 2
    assert captured["provider"] is not None


def test_tracer_otlp_and_console(monkeypatch) -> None:
    captured = {"provider": None}

    class DummyTracer:
        def start_as_current_span(self, name: str):
            class DummySpan:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

            return DummySpan()

    def set_tracer_provider(provider):
        captured["provider"] = provider

    def get_tracer(name: str):
        return DummyTracer()

    trace_mod = types.SimpleNamespace(
        set_tracer_provider=set_tracer_provider,
        get_tracer=get_tracer,
    )

    class DummyResource:
        @staticmethod
        def create(attrs):
            return {"attrs": attrs}

    class DummyTracerProvider:
        def __init__(self, resource=None):
            self.resource = resource
            self.processors = []

        def add_span_processor(self, processor):
            self.processors.append(processor)

    class DummyBatchSpanProcessor:
        def __init__(self, exporter):
            self.exporter = exporter

    class DummyConsoleExporter:
        pass

    class DummyOtlpExporter:
        def __init__(self, endpoint=None, headers=None):
            self.endpoint = endpoint
            self.headers = headers

    otel = types.ModuleType("opentelemetry")
    otel_trace = types.ModuleType("opentelemetry.trace")
    otel_trace.set_tracer_provider = trace_mod.set_tracer_provider
    otel_trace.get_tracer = trace_mod.get_tracer
    otel_sdk_resources = types.ModuleType("opentelemetry.sdk.resources")
    otel_sdk_resources.Resource = DummyResource
    otel_sdk_trace = types.ModuleType("opentelemetry.sdk.trace")
    otel_sdk_trace.TracerProvider = DummyTracerProvider
    otel_sdk_export = types.ModuleType("opentelemetry.sdk.trace.export")
    otel_sdk_export.BatchSpanProcessor = DummyBatchSpanProcessor
    otel_sdk_export.ConsoleSpanExporter = DummyConsoleExporter
    otel_otlp = types.ModuleType("opentelemetry.exporter.otlp.proto.grpc.trace_exporter")
    otel_otlp.OTLPSpanExporter = DummyOtlpExporter

    monkeypatch.setitem(sys.modules, "opentelemetry", otel)
    monkeypatch.setitem(sys.modules, "opentelemetry.trace", otel_trace)
    monkeypatch.setitem(sys.modules, "opentelemetry.sdk.resources", otel_sdk_resources)
    monkeypatch.setitem(sys.modules, "opentelemetry.sdk.trace", otel_sdk_trace)
    monkeypatch.setitem(sys.modules, "opentelemetry.sdk.trace.export", otel_sdk_export)
    monkeypatch.setitem(
        sys.modules,
        "opentelemetry.exporter.otlp.proto.grpc.trace_exporter",
        otel_otlp,
    )

    monkeypatch.setenv("CORTEXPILOT_OTLP_ENDPOINT", "http://localhost:4317")
    tracer_module = importlib.reload(importlib.import_module("cortexpilot_orch.observability.tracer"))
    assert tracer_module.get_tracer() is not None


def test_tracer_none_and_no_otel(monkeypatch) -> None:
    import cortexpilot_orch.observability.tracer as tracer

    monkeypatch.setattr(tracer, "_HAS_OTEL", False)
    assert tracer.get_tracer() is None

    monkeypatch.setattr(tracer, "_HAS_OTEL", True)
    monkeypatch.setattr(tracer, "get_tracer", lambda: None)

    @tracer.trace_span("noop")
    def _work() -> int:
        return 2

    assert _work() == 2
