from __future__ import annotations

from openvibecoding_orch.runners import agents_binding, agents_handoff, agents_mcp_config, agents_payload
from openvibecoding_orch.runners import agents_runner


def test_handoff_validation_parity() -> None:
    contract = {
        "owner_agent": {"role": "PM"},
        "assigned_agent": {"role": "TEST_RUNNER"},
        "handoff_chain": {"enabled": True, "roles": ["PM", "TECH_LEAD", "WORKER", "REVIEWER", "TEST_RUNNER"]},
    }
    assert agents_runner._validate_handoff_chain(contract) == agents_handoff._validate_handoff_chain(contract)


def test_handoff_payload_parity() -> None:
    payload_text = '{"summary":"ok","risks":["none"]}'
    assert agents_runner._parse_handoff_payload(payload_text) == agents_handoff._parse_handoff_payload(payload_text)


def test_binding_extract_parity() -> None:
    payload = {"evidence_refs": {"thread_id": "123e4567-e89b-12d3-a456-426614174000", "session_id": "session-1"}}
    assert agents_runner._extract_evidence_refs(payload) == agents_binding._extract_evidence_refs(payload)
    assert agents_runner._extract_binding_from_result(payload) == agents_binding._extract_binding_from_result(payload)
    assert agents_binding._is_valid_thread_id(None) is False


def test_payload_shell_detection_parity() -> None:
    payload = {
        "type": "tool_call",
        "tool_name": "shell",
        "arguments": {"cmd": "echo hello"},
    }
    assert agents_runner._is_tool_call_dict(payload) == agents_payload._is_tool_call_dict(payload)
    assert agents_runner._contains_shell_request(payload) == agents_payload._contains_shell_request(payload)


def test_payload_structured_content_parity() -> None:
    snapshot = {"nested": {"structuredContent": {"ok": True}}}
    assert agents_runner._extract_structured_content(snapshot) == agents_payload._extract_structured_content(snapshot)


def test_mcp_config_toolset_and_provider_parity() -> None:
    config_text = """
model_provider = \"openai\"

[mcp_servers.alpha]
command = \"alpha\"

[mcp_servers.beta]
command = \"beta\"

[model_providers.openai]
base_url = \"https://example.local/v1\"
"""
    tool_set = [" alpha ", "beta", "alpha", 123]

    assert agents_runner._normalize_mcp_tool_set(tool_set) == agents_mcp_config._normalize_mcp_tool_set(tool_set)
    assert agents_runner._extract_mcp_server_names(config_text) == agents_mcp_config._extract_mcp_server_names(config_text)
    assert agents_runner._resolve_model_provider(config_text) == agents_mcp_config._resolve_model_provider(config_text)


def test_mcp_config_filter_and_strip_parity() -> None:
    config_text = """
project_doc_fallback_filenames = [\"README.md\"]
project_doc_max_bytes = 4096

[mcp_servers.alpha]
command = \"alpha\"

[mcp_servers.beta]
command = \"beta\"
"""

    assert agents_runner._filter_mcp_config(config_text, {"alpha"}, include_non_mcp=False) == agents_mcp_config._filter_mcp_config(
        config_text,
        {"alpha"},
        include_non_mcp=False,
    )
    assert agents_runner._strip_toml_keys(config_text, {"project_doc_max_bytes"}) == agents_mcp_config._strip_toml_keys(
        config_text,
        {"project_doc_max_bytes"},
    )
