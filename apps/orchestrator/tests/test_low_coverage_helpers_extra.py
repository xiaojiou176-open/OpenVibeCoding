from __future__ import annotations

import asyncio
import builtins
import importlib
import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from cortexpilot_orch.gates import integrated_gate
from cortexpilot_orch.runners import agents_handoff, agents_mcp_config, agents_payload
from cortexpilot_orch.scheduler import artifact_refs, runtime_utils
from cortexpilot_orch.services.orchestration_service import OrchestrationService


def test_orchestration_service_delegates_all_entrypoints(monkeypatch, tmp_path: Path) -> None:
    import cortexpilot_orch.services.orchestration_service as service_module

    cfg = types.SimpleNamespace(repo_root=tmp_path / "repo", runs_root=tmp_path / "runs")
    cfg.repo_root.mkdir(parents=True, exist_ok=True)
    cfg.runs_root.mkdir(parents=True, exist_ok=True)

    captured: dict[str, Any] = {}

    class DummyOrchestrator:
        def __init__(self, repo_root: Path) -> None:
            captured["orch_repo_root"] = repo_root

        def replay_run(self, run_id: str, baseline_run_id: str | None = None) -> dict[str, Any]:
            return {"run_id": run_id, "baseline_run_id": baseline_run_id}

    class DummyRunStore:
        def __init__(self, runs_root: Path) -> None:
            captured["runs_root"] = runs_root

    class DummyReplayRunner:
        def __init__(self, run_store: Any) -> None:
            captured["replayer_store"] = run_store

    monkeypatch.setattr(service_module, "load_config", lambda: cfg)
    monkeypatch.setattr(service_module, "Orchestrator", DummyOrchestrator)
    monkeypatch.setattr(service_module, "RunStore", DummyRunStore)
    monkeypatch.setattr(service_module, "ReplayRunner", DummyReplayRunner)
    monkeypatch.setattr(
        service_module.execute_flow,
        "execute_task_flow",
        lambda orch, contract_path, mock_mode=False: f"run:{contract_path.name}:{mock_mode}",
    )
    monkeypatch.setattr(service_module, "verify_run", lambda replayer, run_id, strict=False: {"ok": True, "strict": strict})
    monkeypatch.setattr(service_module, "reexecute_run", lambda replayer, run_id, strict=True: {"ok": True, "strict": strict})

    svc = OrchestrationService()
    assert svc.execute_task(tmp_path / "contract.json", mock_mode=True) == "run:contract.json:True"
    assert svc.replay_run("run-1", baseline_run_id="run-0") == {"run_id": "run-1", "baseline_run_id": "run-0"}
    assert svc.replay_verify("run-1", strict=True) == {"ok": True, "strict": True}
    assert svc.replay_reexec("run-1", strict=False) == {"ok": True, "strict": False}
    assert captured["orch_repo_root"] == cfg.repo_root.resolve()
    assert captured["runs_root"] == cfg.runs_root

    svc_with_repo = OrchestrationService(repo_root=tmp_path)
    assert svc_with_repo._resolve_repo_root() == tmp_path.resolve()


def test_orchestration_service_write_side_actions(monkeypatch, tmp_path: Path) -> None:
    import cortexpilot_orch.services.orchestration_service as service_module

    cfg = types.SimpleNamespace(repo_root=tmp_path / "repo", runs_root=tmp_path / "runs")
    cfg.repo_root.mkdir(parents=True, exist_ok=True)
    cfg.runs_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(service_module, "load_config", lambda: cfg)
    monkeypatch.setattr(
        service_module.run_store,
        "_default_store",
        service_module.RunStore(runs_root=cfg.runs_root),
    )

    run_id = "run_write_side"
    run_dir = cfg.runs_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text(
        json.dumps({"run_id": run_id, "task_id": "task", "status": "SUCCESS"}),
        encoding="utf-8",
    )

    svc = OrchestrationService()
    bundle = {"summary": {"items": 1}}
    promoted = svc.promote_evidence(run_id, bundle)
    assert promoted["ok"] is True
    assert promoted["bundle"] == bundle

    rejected = svc.reject_run(run_id)
    assert rejected == {"ok": True, "reason": "diff gate rejected"}
    assert svc.reject_run("missing-run") == {"ok": False, "error": "RUN_NOT_FOUND"}

    approved = svc.approve_god_mode(
        run_id,
        {
            "run_id": run_id,
            "approved_by": "ops",
            "token": "svc-raw-token",
            "nested": {"secret": "svc-nested-secret"},
        },
    )
    assert approved == {"ok": True, "run_id": run_id}

    run_invalid_json = "run_invalid_json"
    invalid_dir = cfg.runs_root / run_invalid_json
    invalid_dir.mkdir(parents=True, exist_ok=True)
    (invalid_dir / "manifest.json").write_text("{", encoding="utf-8")
    invalid_reject = svc.reject_run(run_invalid_json)
    assert invalid_reject == {"ok": True, "reason": "diff gate rejected"}

    run_non_dict = "run_non_dict"
    non_dict_dir = cfg.runs_root / run_non_dict
    non_dict_dir.mkdir(parents=True, exist_ok=True)
    (non_dict_dir / "manifest.json").write_text("[]", encoding="utf-8")
    non_dict_reject = svc.reject_run(run_non_dict)
    assert non_dict_reject == {"ok": True, "reason": "diff gate rejected"}

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "FAILURE"
    assert manifest["failure_reason"] == "diff gate rejected"

    events_text = (run_dir / "events.jsonl").read_text(encoding="utf-8")
    assert "SEARCH_PROMOTED" in events_text
    assert "DIFF_GATE_REJECTED" in events_text
    assert "HUMAN_APPROVAL_COMPLETED" in events_text
    assert "svc-raw-token" not in events_text
    assert "svc-nested-secret" not in events_text
    assert "[REDACTED]" in events_text


def test_integrated_gate_load_registry_branches(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)

    fallback_root = tmp_path / "fallback"
    (fallback_root / "tooling").mkdir(parents=True, exist_ok=True)
    (fallback_root / "tooling" / "registry.json").write_text(
        json.dumps({"installed": ["codex"], "integrated": ["codex"]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(integrated_gate, "_REPO_ROOT", fallback_root)

    monkeypatch.setenv("CORTEXPILOT_TOOL_REGISTRY", "configs/registry.json")
    (repo_root / "configs").mkdir(parents=True, exist_ok=True)
    (repo_root / "configs" / "registry.json").write_text("{", encoding="utf-8")
    invalid = integrated_gate.validate_integrated_tools(repo_root, ["codex"])
    assert invalid["ok"] is False
    assert invalid["integrated"] == []

    monkeypatch.setenv("CORTEXPILOT_TOOL_REGISTRY", "configs/missing.json")
    fallback = integrated_gate.validate_integrated_tools(repo_root, ["codex"])
    assert fallback["ok"] is True
    assert fallback["integrated"] == ["codex"]

    monkeypatch.delenv("CORTEXPILOT_TOOL_REGISTRY", raising=False)
    same_root_empty = integrated_gate.validate_integrated_tools(fallback_root, ["missing-tool"])
    assert same_root_empty["ok"] is False
    assert same_root_empty["missing"] == ["missing-tool"]


def _install_fake_otel_modules(monkeypatch, with_http_exporter: bool) -> dict[str, Any]:
    captured: dict[str, Any] = {"provider": None}

    class DummyTracer:
        def start_as_current_span(self, _name: str):
            class _Span:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

            return _Span()

    def set_tracer_provider(provider):
        captured["provider"] = provider

    def get_tracer(_name: str):
        return DummyTracer()

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

    class DummyConsoleSpanExporter:
        pass

    class DummyGrpcExporter:
        def __init__(self, endpoint=None, headers=None):
            self.endpoint = endpoint
            self.headers = headers

    otel = types.ModuleType("opentelemetry")
    otel_trace = types.ModuleType("opentelemetry.trace")
    otel_trace.set_tracer_provider = set_tracer_provider
    otel_trace.get_tracer = get_tracer

    otel_sdk_resources = types.ModuleType("opentelemetry.sdk.resources")
    otel_sdk_resources.Resource = DummyResource

    otel_sdk_trace = types.ModuleType("opentelemetry.sdk.trace")
    otel_sdk_trace.TracerProvider = DummyTracerProvider

    otel_sdk_export = types.ModuleType("opentelemetry.sdk.trace.export")
    otel_sdk_export.BatchSpanProcessor = DummyBatchSpanProcessor
    otel_sdk_export.ConsoleSpanExporter = DummyConsoleSpanExporter

    otel_otlp_grpc = types.ModuleType("opentelemetry.exporter.otlp.proto.grpc.trace_exporter")
    otel_otlp_grpc.OTLPSpanExporter = DummyGrpcExporter

    monkeypatch.setitem(sys.modules, "opentelemetry", otel)
    monkeypatch.setitem(sys.modules, "opentelemetry.trace", otel_trace)
    monkeypatch.setitem(sys.modules, "opentelemetry.sdk.resources", otel_sdk_resources)
    monkeypatch.setitem(sys.modules, "opentelemetry.sdk.trace", otel_sdk_trace)
    monkeypatch.setitem(sys.modules, "opentelemetry.sdk.trace.export", otel_sdk_export)
    monkeypatch.setitem(
        sys.modules,
        "opentelemetry.exporter.otlp.proto.grpc.trace_exporter",
        otel_otlp_grpc,
    )

    if with_http_exporter:
        http_mod = types.ModuleType("opentelemetry.exporter.otlp.proto.http.trace_exporter")
        http_mod.OTLPSpanExporter = DummyGrpcExporter
        monkeypatch.setitem(sys.modules, "opentelemetry.exporter.otlp.proto.http.trace_exporter", http_mod)
    else:
        monkeypatch.setitem(sys.modules, "opentelemetry.exporter.otlp.proto.http.trace_exporter", types.ModuleType("broken_http"))

    return captured


def test_tracer_http_fallback_console_and_required(monkeypatch) -> None:
    captured = _install_fake_otel_modules(monkeypatch, with_http_exporter=False)

    monkeypatch.setenv("CORTEXPILOT_OTLP_ENDPOINT", "http://127.0.0.1:4318/v1/traces")
    monkeypatch.setenv("CORTEXPILOT_OTLP_PROTOCOL", "http")
    monkeypatch.setenv("CORTEXPILOT_OTLP_HEADERS", "token=abc, malformed, x = y")
    tracer_module = importlib.reload(importlib.import_module("cortexpilot_orch.observability.tracer"))

    provider = captured["provider"]
    assert provider is not None
    assert provider.processors
    exporter = provider.processors[0].exporter
    assert exporter.endpoint == "http://127.0.0.1:4318/v1/traces"
    assert exporter.headers == {"token": "abc", "x": "y"}

    status = tracer_module.tracing_status()
    assert status["enabled"] is True
    assert status["otlp_protocol"] == "http"

    monkeypatch.delenv("CORTEXPILOT_OTLP_ENDPOINT", raising=False)
    monkeypatch.setenv("CORTEXPILOT_ENABLE_CONSOLE_TRACE", "true")
    tracer_module = importlib.reload(importlib.import_module("cortexpilot_orch.observability.tracer"))
    assert tracer_module.tracing_status()["console_enabled"] is True

    monkeypatch.setenv("CORTEXPILOT_OTEL_REQUIRED", "true")
    monkeypatch.delenv("CORTEXPILOT_ENABLE_CONSOLE_TRACE", raising=False)
    monkeypatch.setattr(tracer_module, "_HAS_OTEL", False)
    with pytest.raises(RuntimeError, match="OTel tracing required"):
        tracer_module.ensure_tracing()


def test_tracer_http_exporter_branch(monkeypatch) -> None:
    captured = _install_fake_otel_modules(monkeypatch, with_http_exporter=True)

    monkeypatch.setenv("CORTEXPILOT_OTLP_ENDPOINT", "http://127.0.0.1:4318/v1/traces")
    monkeypatch.setenv("CORTEXPILOT_OTLP_PROTOCOL", "http")
    tracer_module = importlib.reload(importlib.import_module("cortexpilot_orch.observability.tracer"))

    provider = captured["provider"]
    assert provider is not None
    exporter = provider.processors[0].exporter
    assert exporter.endpoint == "http://127.0.0.1:4318/v1/traces"
    assert tracer_module.tracing_status()["enabled"] is True


def test_tracer_import_failure_and_trace_span_noop(monkeypatch) -> None:
    original_import = builtins.__import__

    def _raising_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name.startswith("opentelemetry"):
            raise ImportError("simulated")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _raising_import)
    tracer_module = importlib.reload(importlib.import_module("cortexpilot_orch.observability.tracer"))
    assert tracer_module._HAS_OTEL is False

    @tracer_module.trace_span("noop")
    def _work(x: int) -> int:
        return x + 1

    assert _work(2) == 3


def test_agents_mcp_config_branch_matrix() -> None:
    assert agents_mcp_config._normalize_mcp_tool_set("not-list") == []
    assert agents_mcp_config._normalize_mcp_tool_set(["01-filesystem"]) == ["01-filesystem"]
    assert agents_mcp_config._normalize_mcp_tool_set(["codex", "git"]) == ["codex", "git"]
    assert agents_mcp_config._normalize_mcp_tool_set(["filesystem", "filesystem"]) == ["filesystem"]
    assert agents_mcp_config._tool_set_disabled(["NONE"])

    assert agents_mcp_config._section_mcp_server_name("x") is None
    assert agents_mcp_config._section_mcp_server_name("mcp_servers.") is None
    assert agents_mcp_config._section_mcp_server_name('mcp_servers."broken') is None
    assert agents_mcp_config._section_mcp_server_name('mcp_servers."ok"') == "ok"
    assert agents_mcp_config._section_mcp_server_name("mcp_servers.alpha.extra") == "alpha"

    assert agents_mcp_config._section_model_provider_name("x") is None
    assert agents_mcp_config._section_model_provider_name("model_providers.") is None
    assert agents_mcp_config._section_model_provider_name('model_providers."broken') is None
    assert agents_mcp_config._section_model_provider_name('model_providers."openai"') == "openai"
    assert agents_mcp_config._section_model_provider_name("model_providers.custom.extra") == "custom"

    cfg = """
# comment
model_provider
model_provider = ""
"""
    assert agents_mcp_config._resolve_model_provider(cfg) is None

    cfg2 = """
# comment
model_provider = "openai"
"""
    assert agents_mcp_config._resolve_model_provider(cfg2) == "openai"

    base_cfg = """
[model_providers.openai]
api_key_env = "GEMINI_API_KEY"

[mcp_servers.a]
command = "a"
"""
    updated = agents_mcp_config._override_model_provider_base_url(base_cfg, "openai", "http://localhost:1456/v1")
    assert 'base_url = "http://localhost:1456/v1"' in updated
    assert updated.endswith("\n")

    unchanged = agents_mcp_config._override_model_provider_base_url(base_cfg, None, "http://localhost")
    assert unchanged == base_cfg

    key_overridden = agents_mcp_config._override_model_provider_api_key(base_cfg, "openai", "token-123")
    assert 'experimental_bearer_token = "token-123"' in key_overridden or 'api_key = "token-123"' in key_overridden
    assert key_overridden.endswith("\n")

    base_cfg_with_key = """
[model_providers.openai]
experimental_bearer_token = "old-token"
"""
    key_replaced = agents_mcp_config._override_model_provider_api_key(base_cfg_with_key, "openai", "new-token")
    assert 'experimental_bearer_token = "new-token"' in key_replaced

    key_unchanged = agents_mcp_config._override_model_provider_api_key(base_cfg, None, "token-123")
    assert key_unchanged == base_cfg

    filtered = agents_mcp_config._filter_mcp_config(base_cfg, {"a"}, include_non_mcp=False)
    assert "[mcp_servers.a]" in filtered
    assert "[model_providers.openai]" not in filtered

    stripped = agents_mcp_config._strip_mcp_sections(base_cfg)
    assert "[mcp_servers.a]" not in stripped
    assert "[model_providers.openai]" in stripped

    multiline_cfg = (
        'project_doc_max_bytes = """\n'
        "123\n"
        '"""\n'
        "keep_me = true\n"
    )
    output = agents_mcp_config._strip_toml_keys(multiline_cfg, {"project_doc_max_bytes"})
    assert "project_doc_max_bytes" not in output
    assert "keep_me = true" in output


def test_agents_handoff_branch_matrix(monkeypatch) -> None:
    assert agents_handoff._agent_role("not-dict") == ""

    ok, msg = agents_handoff._validate_handoff_chain({"handoff_chain": "x"})
    assert ok is True and msg == ""

    invalid_enabled = {
        "handoff_chain": {"enabled": True, "roles": []},
    }
    ok, msg = agents_handoff._validate_handoff_chain(invalid_enabled)
    assert ok is False and "requires roles" in msg

    invalid_role = {"handoff_chain": {"enabled": True, "roles": ["PM", "UNKNOWN"]}}
    ok, msg = agents_handoff._validate_handoff_chain(invalid_role)
    assert ok is False and "role invalid" in msg

    out_of_order = {"handoff_chain": {"enabled": True, "roles": ["TECH_LEAD", "PM"]}}
    ok, msg = agents_handoff._validate_handoff_chain(out_of_order)
    assert ok is False and "out of order" in msg

    missing_primary = {"handoff_chain": {"enabled": True, "roles": ["WORKER", "REVIEWER"]}}
    ok, msg = agents_handoff._validate_handoff_chain(missing_primary)
    assert ok is False and "missing required roles" in msg

    owner_mismatch = {
        "owner_agent": {"role": "TECH_LEAD"},
        "assigned_agent": {"role": "WORKER"},
        "handoff_chain": {"enabled": True, "roles": ["PM", "TECH_LEAD", "WORKER"]},
    }
    ok, msg = agents_handoff._validate_handoff_chain(owner_mismatch)
    assert ok is False and "start with owner" in msg

    assigned_mismatch = {
        "owner_agent": {"role": "PM"},
        "assigned_agent": {"role": "TEST_RUNNER"},
        "handoff_chain": {"enabled": True, "roles": ["PM", "TECH_LEAD", "WORKER", "REVIEWER"]},
    }
    ok, msg = agents_handoff._validate_handoff_chain(assigned_mismatch)
    assert ok is False and "end with assigned" in msg

    roles = agents_handoff._handoff_chain_roles(
        {
            "owner_agent": {"role": "PM"},
            "assigned_agent": {"role": "TEST_RUNNER"},
            "handoff_chain": {"enabled": True, "roles": ["TECH_LEAD", "WORKER"]},
        }
    )
    assert roles[0] == "PM"
    assert roles[-1] == "TEST_RUNNER"

    assert agents_handoff._handoff_chain_roles({"handoff_chain": {"enabled": False, "roles": []}}) == []

    payload, summary = agents_handoff._parse_handoff_payload('{"summary": "next", "risks": []}')
    assert payload == {"summary": "next", "risks": []}
    assert summary["summary"] == "next"

    bad1, err1 = agents_handoff._parse_handoff_payload("{")
    assert bad1 is None and "not json" in err1["error"]

    bad2, err2 = agents_handoff._parse_handoff_payload("[]")
    assert bad2 is None and "not object" in err2["error"]

    bad3, err3 = agents_handoff._parse_handoff_payload('{"summary": "  ", "risks": []}')
    assert bad3 is None and "missing summary" in err3["error"]

    monkeypatch.setenv("CORTEXPILOT_AGENTS_FORCE_HANDOFF", "true")
    assert agents_handoff._handoff_required({"owner_agent": {"role": "PM"}, "assigned_agent": {"role": "PM"}})


def test_agents_payload_branch_matrix() -> None:
    class Unserializable:
        pass

    assert agents_payload._safe_json_value(Unserializable())

    assert agents_payload._extract_first({"a": {"b": 1}}, ("z",), depth=7, max_depth=6) is None

    snapshot = {"x": [{"y": {"structured_content": {"ok": True}}}]}
    assert agents_payload._extract_structured_content(snapshot) == {"ok": True}

    assert agents_payload._is_tool_call_dict({"call_id": "1"}) is True
    assert agents_payload._is_tool_call_dict({"name": "shell", "args": {"x": 1}}) is True

    assert agents_payload._contains_shell_request({"type": "tool_call", "name": "shell"}) is True
    assert agents_payload._contains_shell_request({"type": "tool_call", "cmd": "echo hi"}) is True
    assert agents_payload._contains_shell_request([{"type": "tool_call", "tool": "bash"}]) is True
    assert agents_payload._contains_shell_request({"output": "shell"}) is False


def test_temporal_workflows_force_import_fallback(monkeypatch) -> None:
    original_import = builtins.__import__

    def _raising_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name.startswith("temporalio"):
            raise ImportError("simulated")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _raising_import)
    workflows = importlib.reload(importlib.import_module("cortexpilot_orch.temporal.workflows"))

    request = workflows.RunRequest(
        repo_root="/tmp/repo",
        contract_path="/tmp/repo/contract.json",
        mock_mode=True,
        workflow_id="wf-fallback",
    )
    with pytest.raises(RuntimeError, match="temporalio not installed"):
        asyncio.run(workflows.run_contract_activity(request))


def test_artifact_refs_wrappers(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(artifact_refs.core_helpers, "artifact_ref", lambda *args, **kwargs: {"kind": "artifact_ref"})
    monkeypatch.setattr(
        artifact_refs.core_helpers,
        "artifact_ref_from_hash",
        lambda *args, **kwargs: {"kind": "artifact_ref_from_hash"},
    )
    monkeypatch.setattr(artifact_refs.core_helpers, "guess_media_type", lambda path: "text/plain")

    assert artifact_refs.artifact_ref("n", "p", "c")["kind"] == "artifact_ref"
    assert artifact_refs.artifact_ref_from_hash("n", "p", "sha", 1)["kind"] == "artifact_ref_from_hash"
    assert artifact_refs.guess_media_type("a.txt") == "text/plain"
