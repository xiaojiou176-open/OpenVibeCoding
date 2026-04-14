from __future__ import annotations

import json
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from tests.helpers.mcp_stdio import (
    LATEST_PROTOCOL_VERSION,
    list_tools,
    probe_initialize,
    start_mcp_server_with_configs,
    terminate_mcp_server,
)
from tests.helpers.mcp_proxy import ProxyClient, start_proxy, stop_proxy


def _mcp_e2e_enabled() -> bool:
    return os.getenv("OPENVIBECODING_ENABLE_MCP_E2E", "").strip().lower() in {"1", "true", "yes"}


def _require_mcp_e2e_or_skip() -> None:
    enabled = _mcp_e2e_enabled()
    require = os.getenv("OPENVIBECODING_REQUIRE_MCP_E2E", "").strip().lower() in {"1", "true", "yes"}
    if not enabled:
        if require:
            pytest.fail("mcp concurrency e2e is required but disabled (set OPENVIBECODING_ENABLE_MCP_E2E=1)")
        pytest.skip("mcp concurrency e2e disabled")
    if shutil.which("codex") is None:
        if require:
            pytest.fail("mcp concurrency e2e is required but codex is not installed")
        pytest.skip("codex not installed")


@pytest.mark.e2e
def test_mcp_server_multi_process_smoke(tmp_path: Path) -> None:
    _require_mcp_e2e_or_skip()

    handles = []
    try:
        handle_a = start_mcp_server_with_configs()
        handles.append(handle_a)
        handle_b = start_mcp_server_with_configs()
        handles.append(handle_b)

        with ThreadPoolExecutor(max_workers=2) as pool:
            names_a = pool.submit(list_tools, handle_a, 2).result(timeout=10)
            names_b = pool.submit(list_tools, handle_b, 2).result(timeout=10)
        assert "codex" in names_a
        assert "codex" in names_b
        assert handle_a.label
    finally:
        for handle in handles:
            terminate_mcp_server(handle)


@pytest.mark.e2e
def test_mcp_server_single_process_multi_request(tmp_path: Path) -> None:
    _require_mcp_e2e_or_skip()

    handle = start_mcp_server_with_configs()

    try:
        names_a = list_tools(handle, 2)
        names_b = list_tools(handle, 3)
        assert "codex" in names_a
        assert "codex" in names_b

        # stdio transport is single-client; probe secondary initialize for evidence.
        probe_initialize(handle, request_id=4, client_name="openvibecoding_test_b", timeout=2.0)
    finally:
        terminate_mcp_server(handle)


@pytest.mark.e2e
def test_mcp_multi_client_proxy(tmp_path: Path) -> None:
    _require_mcp_e2e_or_skip()

    handle = start_proxy()
    try:
        client_a = ProxyClient(handle, "clientA")
        client_b = ProxyClient(handle, "clientB")

        def _init(client: ProxyClient, name: str) -> None:
            client.call(
                "initialize",
                {
                    "protocolVersion": LATEST_PROTOCOL_VERSION,
                    "clientInfo": {"name": name, "version": "0.1.0"},
                    "capabilities": {},
                },
                timeout=5.0,
            )
            # Initialized notification
            send_payload = {"jsonrpc": "2.0", "method": "initialized", "params": {}}
            if handle.proc.stdin is not None:
                handle.proc.stdin.write(json.dumps(send_payload) + "\n")
                handle.proc.stdin.flush()

        _init(client_a, "openvibecoding_a")
        _init(client_b, "openvibecoding_b")

        def _tools(client: ProxyClient):
            resp = client.call("tools/list", {}, timeout=5.0)
            tools = resp.get("result", {}).get("tools", []) if isinstance(resp.get("result"), dict) else []
            return [item.get("name") for item in tools if isinstance(item, dict)]

        with ThreadPoolExecutor(max_workers=2) as pool:
            names_a = pool.submit(_tools, client_a).result(timeout=10)
            names_b = pool.submit(_tools, client_b).result(timeout=10)
        assert "codex" in names_a
        assert "codex" in names_b
    finally:
        stop_proxy(handle)
