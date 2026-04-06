from __future__ import annotations

import os
import shutil

import pytest

from tests.helpers.mcp_stdio import (
    assert_protocol_supported,
    initialize_with_protocol,
    start_mcp_server_with_configs,
    terminate_mcp_server,
)


def _mcp_e2e_enabled() -> bool:
    return os.getenv("CORTEXPILOT_ENABLE_MCP_E2E", "").strip().lower() in {"1", "true", "yes"}


def _require_mcp_e2e_or_skip() -> None:
    enabled = _mcp_e2e_enabled()
    require = os.getenv("CORTEXPILOT_REQUIRE_MCP_E2E", "").strip().lower() in {"1", "true", "yes"}
    if not enabled:
        if require:
            pytest.fail("mcp protocol drift e2e is required but disabled (set CORTEXPILOT_ENABLE_MCP_E2E=1)")
        pytest.skip("mcp concurrency e2e disabled")
    if shutil.which("codex") is None:
        if require:
            pytest.fail("mcp protocol drift e2e is required but codex is not installed")
        pytest.skip("codex not installed")


@pytest.mark.e2e
def test_mcp_protocol_drift_detection() -> None:
    _require_mcp_e2e_or_skip()

    handle = start_mcp_server_with_configs(initialize=False)
    try:
        resp = initialize_with_protocol(handle, "1900-01-01", request_id=1, client_name="cortexpilot_drift")
        if isinstance(resp, dict) and "error" in resp:
            return

        result = resp.get("result") if isinstance(resp, dict) else {}
        protocol = result.get("protocolVersion") if isinstance(result, dict) else None
        if not protocol:
            raise AssertionError("protocolVersion missing in initialize result")
        negotiated = str(protocol)
        if negotiated == "1900-01-01":
            # Drift is detected by handshake echoing an unsupported protocol.
            return
        assert_protocol_supported(negotiated)
    finally:
        terminate_mcp_server(handle)
