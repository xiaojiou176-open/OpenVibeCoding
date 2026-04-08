from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from cortexpilot_orch.mcp_readonly_server import CortexPilotReadonlyMcpServer
from cortexpilot_orch.transport.mcp_jsonl import JsonlStream, send_json

from .helpers.api_main_test_io import _write_contract, _write_events, _write_manifest, _write_report


def test_mcp_readonly_server_lists_tools_and_calls_with_structured_content() -> None:
    class _FakeReadService:
        def list_runs(self) -> list[dict]:
            return [{"run_id": "run-1", "status": "FAILED"}]

        def get_run(self, run_id: str) -> dict:
            return {"run_id": run_id, "status": "FAILED"}

        def get_run_events(self, run_id: str) -> list[dict]:
            return [{"event": "RUN_FAILED", "run_id": run_id}]

        def get_run_reports(self, run_id: str) -> list[dict]:
            return [{"name": "proof_pack.json", "data": {"run_id": run_id}}]

        def list_workflows(self) -> list[dict]:
            return [{"workflow_id": "wf-1"}]

        def get_workflow(self, workflow_id: str) -> dict:
            return {"workflow": {"workflow_id": workflow_id}, "runs": [], "events": []}

        def list_queue(self, *, workflow_id: str | None = None, status: str | None = None) -> list[dict]:
            return [{"workflow_id": workflow_id or "", "status": status or "PENDING"}]

        def get_pending_approvals(self, *, run_id: str | None = None) -> list[dict]:
            return [{"run_id": run_id or "run-1"}]

        def get_diff_gate_state(self, *, run_id: str | None = None) -> list[dict]:
            return [{"run_id": run_id or "run-1", "status": "FAILED"}]

        def get_compare_summary(self, run_id: str) -> dict:
            return {"run_id": run_id, "mismatched_count": 1}

        def get_proof_summary(self, run_id: str) -> dict:
            return {"run_id": run_id, "summary": "proof ready"}

        def get_incident_summary(self, run_id: str) -> dict:
            return {"run_id": run_id, "summary": "gate blocked"}

    server = CortexPilotReadonlyMcpServer(read_service=_FakeReadService())  # type: ignore[arg-type]

    init_response = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-11-25", "clientInfo": {"name": "test", "version": "0.1.0"}},
        }
    )
    tools_response = server.handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    call_response = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "get_compare_summary", "arguments": {"run_id": "run-1"}},
        }
    )

    assert init_response is not None
    assert init_response["result"]["serverInfo"]["name"] == "cortexpilot-readonly"
    assert tools_response is not None
    tool_names = [item["name"] for item in tools_response["result"]["tools"]]
    assert "list_runs" in tool_names
    assert "get_compare_summary" in tool_names
    assert call_response is not None
    assert call_response["result"]["structuredContent"]["compare_summary"]["mismatched_count"] == 1
    assert call_response["result"]["isError"] is False


def _start_mcp_subprocess(repo_root: Path, env: dict[str, str]) -> subprocess.Popen[str]:
    uv_bin = shutil.which("uv") or "uv"
    requirements_path = repo_root / "apps" / "orchestrator" / "requirements.txt"
    return subprocess.Popen(
        [
            uv_bin,
            "run",
            "--no-project",
            "--with-requirements",
            str(requirements_path),
            "python",
            "-m",
            "cortexpilot_orch.cli",
            "mcp-readonly-server",
        ],
        cwd=repo_root,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )


def _terminate_subprocess(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_mcp_readonly_server_cli_supports_runs_reports_and_keeps_read_only(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    run_dir = runs_root / "run_alpha"
    _write_manifest(
        run_dir,
        {
            "run_id": "run_alpha",
            "task_id": "task_alpha",
            "status": "FAILURE",
            "created_at": "2026-03-31T10:00:00Z",
            "failure_reason": "diff gate rejected",
            "role_binding_summary": {
                "authority": "contract-derived-read-model",
                "source": "persisted from contract",
                "execution_authority": "task_contract",
                "skills_bundle_ref": {
                    "status": "registry-backed",
                    "ref": "policies/skills_bundle_registry.json#bundles.worker_delivery_core_v1",
                    "bundle_id": "worker_delivery_core_v1",
                    "resolved_skill_set": [
                        "contract_alignment",
                        "bounded_change_execution",
                        "artifact_hygiene",
                        "verification_evidence"
                    ],
                    "validation": "fail-closed"
                },
                "mcp_bundle_ref": {
                    "status": "registry-backed",
                    "ref": "policies/agent_registry.json#agents(role=SEARCHER).capabilities.mcp_tools",
                    "resolved_mcp_tool_set": ["search-01-tavily"],
                    "validation": "fail-closed"
                },
                "runtime_binding": {
                    "status": "contract-derived",
                    "authority_scope": "contract-derived-read-model",
                    "source": {
                        "runner": "runtime_options.runner",
                        "provider": "runtime_options.provider",
                        "model": "role_contract.runtime_binding.model"
                    },
                    "summary": {"runner": "agents", "provider": "cliproxyapi", "model": "gpt-5.4"}
                }
            },
            "workflow": {
                "workflow_id": "wf-alpha",
                "status": "FAILED",
                "task_queue": "cortexpilot-orch",
                "namespace": "default",
            },
        },
    )
    _write_contract(
        run_dir,
        {
            "task_id": "task_alpha",
            "allowed_paths": ["apps/dashboard"],
            "role_contract": {
                "skills_bundle_ref": "policies/skills_bundle_registry.json#bundles.worker_delivery_core_v1",
                "mcp_bundle_ref": "policies/agent_registry.json#agents(role=SEARCHER).capabilities.mcp_tools",
                "runtime_binding": {"runner": "agents", "provider": "cliproxyapi", "model": "gpt-5.4"},
                "resolved_mcp_tool_set": ["search-01-tavily"],
            },
        },
    )
    _write_events(
        run_dir,
        [
            json.dumps({"event": "WORKFLOW_BOUND", "context": {"workflow_id": "wf-alpha"}}),
            json.dumps({"event": "DIFF_GATE_RESULT", "context": {"result": "REJECTED"}}),
        ],
    )
    _write_report(run_dir, "run_compare_report.json", {"compare_summary": {"mismatched_count": 2}})
    _write_report(run_dir, "proof_pack.json", {"summary": "proof blocked"})
    _write_report(run_dir, "incident_pack.json", {"summary": "incident blocked"})

    workflow_case_path = runtime_root / "workflow-cases" / "wf-alpha" / "case.json"
    queue_path = runtime_root / "queue.jsonl"
    assert not workflow_case_path.exists()
    assert not queue_path.exists()

    env = os.environ.copy()
    pythonpath = str(repo_root / "apps/orchestrator/src")
    existing_pythonpath = env.get("PYTHONPATH", "").strip()
    env["PYTHONPATH"] = pythonpath if not existing_pythonpath else f"{pythonpath}{os.pathsep}{existing_pythonpath}"
    env["CORTEXPILOT_RUNTIME_ROOT"] = str(runtime_root)
    env["CORTEXPILOT_RUNS_ROOT"] = str(runs_root)

    proc = _start_mcp_subprocess(repo_root, env)
    try:
        stream = JsonlStream(proc)
        send_json(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-11-25", "clientInfo": {"name": "pytest", "version": "0.1.0"}},
            },
        )
        init_response = stream.read_until_id(1, 15.0)
        assert "error" not in init_response

        send_json(proc, {"jsonrpc": "2.0", "method": "initialized", "params": {}})
        send_json(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tools_response = stream.read_until_id(2, 15.0)
        tool_names = [item["name"] for item in tools_response["result"]["tools"]]
        assert "list_runs" in tool_names
        assert "get_workflow" in tool_names
        assert "list_queue" in tool_names

        send_json(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "get_run", "arguments": {"run_id": "run_alpha"}},
            },
        )
        run_response = stream.read_until_id(3, 15.0)
        role_binding = run_response["result"]["structuredContent"]["run"]["role_binding_read_model"]
        assert role_binding["authority"] == "contract-derived-read-model"
        assert role_binding["execution_authority"] == "task_contract"
        assert role_binding["mcp_bundle_ref"]["resolved_mcp_tool_set"] == ["search-01-tavily"]

        send_json(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "get_run_reports", "arguments": {"run_id": "run_alpha"}},
            },
        )
        reports_response = stream.read_until_id(4, 15.0)
        reports = reports_response["result"]["structuredContent"]["reports"]
        assert any(item["name"] == "run_compare_report.json" for item in reports)

        send_json(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {"name": "get_workflow", "arguments": {"workflow_id": "wf-alpha"}},
            },
        )
        workflow_response = stream.read_until_id(5, 15.0)
        assert workflow_response["result"]["structuredContent"]["workflow_detail"]["workflow"]["workflow_id"] == "wf-alpha"
        workflow_case_read_model = workflow_response["result"]["structuredContent"]["workflow_detail"]["workflow"][
            "workflow_case_read_model"
        ]
        assert workflow_case_read_model["workflow_id"] == "wf-alpha"
        assert workflow_case_read_model["source_run_id"] == "run_alpha"
        assert workflow_case_read_model["role_binding_summary"]["execution_authority"] == "task_contract"

        send_json(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 6,
                "method": "tools/call",
                "params": {"name": "list_queue", "arguments": {}},
            },
        )
        queue_response = stream.read_until_id(6, 15.0)
        assert queue_response["result"]["structuredContent"]["queue"] == []
    finally:
        _terminate_subprocess(proc)

    assert not workflow_case_path.exists()
    assert not queue_path.exists()
