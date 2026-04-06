from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass

try:
    from mcp.shared.version import LATEST_PROTOCOL_VERSION
    from mcp.shared.version import SUPPORTED_PROTOCOL_VERSIONS
except Exception:  # noqa: BLE001
    LATEST_PROTOCOL_VERSION = "2025-11-25"
    SUPPORTED_PROTOCOL_VERSIONS = [LATEST_PROTOCOL_VERSION]

from cortexpilot_orch.transport.mcp_jsonl import JsonlStream, send_json


# === MCP STDIO CONFIG ===
MCP_CONFIG_ATTEMPTS: list[tuple[str, list[str]]] = [
    ("default", []),
    ("model_o3", ['model="o3"']),
    ("model_o3_sandbox_permissions", ['model="o3"', 'sandbox_permissions=["disk-full-read-access"]']),
    ("model_gpt_4_1_mini", ['model="gpt-4.1-mini"']),
    ("sandbox_permissions_only", ['sandbox_permissions=["disk-full-read-access"]']),
    ("sandbox_read_only", ['sandbox="read-only"']),
]


# === MCP STDIO HANDLE ===
@dataclass
class McpServerHandle:
    proc: subprocess.Popen[str]
    stream: JsonlStream
    label: str
    codex_home_dir: str | None = None


def list_tools(handle: McpServerHandle, request_id: int) -> list[str]:
    methods = ["tools/list", "tooling/list"]
    last_error: dict | None = None
    for offset, method in enumerate(methods):
        current_request_id = request_id + offset
        send_json(
            handle.proc,
            {"jsonrpc": "2.0", "id": current_request_id, "method": method, "params": {}},
        )
        tools_resp = handle.stream.read_until_id(current_request_id, 5.0)
        if "error" in tools_resp:
            last_error = tools_resp
            continue
        result = tools_resp.get("result", {})
        if isinstance(result, dict):
            tools = result.get("tools") or []
        elif isinstance(result, list):
            tools = result
        else:
            tools = []
        return [item.get("name") for item in tools if isinstance(item, dict)]
    raise RuntimeError(f"tool list failed: {last_error}")


def probe_initialize(
    handle: McpServerHandle,
    request_id: int = 4,
    client_name: str = "cortexpilot_test_b",
    timeout: float = 2.0,
) -> dict | None:
    send_json(
        handle.proc,
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "initialize",
            "params": {
                "protocolVersion": LATEST_PROTOCOL_VERSION,
                "clientInfo": {"name": client_name, "version": "0.1.0"},
                "capabilities": {},
            },
        },
    )
    try:
        return handle.stream.read_until_id(request_id, timeout)
    except RuntimeError:
        return None


# === MCP STDIO SPAWN ===
def _build_isolated_codex_env() -> tuple[dict[str, str], str]:
    codex_home = tempfile.mkdtemp(prefix="cortexpilot_mcp_home_")
    env = os.environ.copy()
    env["CODEX_HOME"] = codex_home
    env["CORTEXPILOT_CODEX_BASE_HOME"] = codex_home
    return env, codex_home


def _start_server(config_args: list[str], env: dict[str, str] | None = None) -> subprocess.Popen[str]:
    cmd = ["codex", "mcp-server"]
    for entry in config_args:
        cmd += ["-c", entry]
    return subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=env,
    )


def _terminate(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def initialize_with_protocol(
    handle: McpServerHandle,
    protocol_version: str,
    request_id: int = 1,
    client_name: str = "cortexpilot_test",
    timeout: float = 5.0,
) -> dict:
    send_json(
        handle.proc,
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "initialize",
            "params": {
                "protocolVersion": protocol_version,
                "clientInfo": {"name": client_name, "version": "0.1.0"},
                "capabilities": {},
            },
        },
    )
    init_resp = handle.stream.read_until_id(request_id, timeout)
    if "error" not in init_resp:
        send_json(handle.proc, {"jsonrpc": "2.0", "method": "initialized", "params": {}})
    return init_resp


def start_mcp_server_with_configs(
    config_attempts: list[tuple[str, list[str]]] | None = None,
    initialize: bool = True,
) -> McpServerHandle:
    attempts = config_attempts or MCP_CONFIG_ATTEMPTS
    errors: list[str] = []
    for label, config_args in attempts:
        proc: subprocess.Popen[str] | None = None
        codex_home_dir: str | None = None
        try:
            env, codex_home_dir = _build_isolated_codex_env()
            proc = _start_server(config_args, env=env)
            if proc.poll() is not None:
                stderr = proc.stderr.read() if proc.stderr else ""
                raise RuntimeError(
                    f"process exited early (code={proc.returncode}) stderr={stderr.strip()}"
                )
            stream = JsonlStream(proc)
            handle = McpServerHandle(
                proc=proc,
                stream=stream,
                label=label,
                codex_home_dir=codex_home_dir,
            )
            if initialize:
                init_resp = initialize_with_protocol(handle, LATEST_PROTOCOL_VERSION)
                if "error" in init_resp:
                    raise RuntimeError(f"initialize failed: {init_resp}")
            return handle
        except Exception as exc:  # noqa: BLE001
            if proc is not None:
                _terminate(proc)
            if codex_home_dir:
                shutil.rmtree(codex_home_dir, ignore_errors=True)
            errors.append(f"{label}: {exc}")
    raise RuntimeError("all config attempts failed: " + " | ".join(errors))


def terminate_mcp_server(handle: McpServerHandle) -> None:
    _terminate(handle.proc)
    if handle.codex_home_dir:
        shutil.rmtree(handle.codex_home_dir, ignore_errors=True)


def assert_protocol_supported(protocol_version: str) -> None:
    if protocol_version not in SUPPORTED_PROTOCOL_VERSIONS:
        raise AssertionError(f"protocol drift detected: {protocol_version} not in supported list")
