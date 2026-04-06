from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

from fastapi.testclient import TestClient

from cortexpilot_orch.api import main as api_main


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _agent_registry_payload() -> dict:
    return {
        "version": "v1",
        "role_contracts": {
            "WORKER": {
                "purpose": "Execute the contracted change inside allowed_paths and produce structured evidence.",
                "system_prompt_ref": "policies/agents/codex/roles/50_worker_core.md",
                "skills_bundle_ref": "policies/skills_bundle_registry.json#bundles.worker_delivery_core_v1",
                "mcp_bundle_ref": "policies/agent_registry.json#agents(role=WORKER).capabilities.mcp_tools",
                "handoff_eligible": True,
                "required_downstream_roles": ["REVIEWER", "TEST_RUNNER"],
                "fail_closed_conditions": [
                    "Writes outside allowed_paths fail closed",
                ],
            },
            "TECH_LEAD": {
                "purpose": "Split product intent into executable contracts.",
                "system_prompt_ref": "policies/agents/codex/roles/20_tech_lead.md",
                "skills_bundle_ref": "policies/skills_bundle_registry.json#bundles.tech_lead_contract_bridge_v1",
                "mcp_bundle_ref": None,
                "handoff_eligible": True,
                "required_downstream_roles": ["WORKER"],
                "fail_closed_conditions": [
                    "Ambiguous contracts fail closed",
                ],
            },
        },
        "agents": [
            {
                "agent_id": "agent-1",
                "role": "WORKER",
                "codex_home": "$HOME/.codex-homes/cortexpilot-worker-core",
                "defaults": {
                    "sandbox": "workspace-write",
                    "approval_policy": "never",
                    "network": "deny",
                },
                "capabilities": {
                    "mcp_tools": ["codex", "search-01-tavily"],
                    "notes": "default worker",
                },
            },
            {
                "agent_id": "agent-1",
                "role": "TECH_LEAD",
                "codex_home": "$HOME/.codex-homes/cortexpilot-techlead",
                "defaults": {
                    "sandbox": "read-only",
                    "approval_policy": "never",
                    "network": "deny",
                },
            },
        ],
    }


def _skills_bundle_registry_payload() -> dict:
    return {
        "version": "v1",
        "bundles": {
            "worker_delivery_core_v1": {
                "bundle_id": "worker_delivery_core_v1",
                "summary": "Worker skills",
                "skills": ["contract_alignment"],
            },
            "tech_lead_contract_bridge_v1": {
                "bundle_id": "tech_lead_contract_bridge_v1",
                "summary": "Tech lead skills",
                "skills": ["contract_lock"],
            },
        },
    }


def _role_config_registry_payload() -> dict:
    return {
        "version": "v1",
        "roles": {
            "WORKER": {
                "system_prompt_ref": "policies/agents/codex/roles/50_worker_core.md",
                "skills_bundle_ref": "policies/skills_bundle_registry.json#bundles.worker_delivery_core_v1",
                "mcp_bundle_ref": "policies/agent_registry.json#agents(role=WORKER).capabilities.mcp_tools",
                "runtime_binding": {
                    "runner": None,
                    "provider": None,
                    "model": None,
                },
            },
        },
    }


def test_role_config_routes_preview_and_apply(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    _write_json(repo_root / "policies" / "agent_registry.json", _agent_registry_payload())
    _write_json(repo_root / "policies" / "skills_bundle_registry.json", _skills_bundle_registry_payload())
    role_config_path = repo_root / "policies" / "role_config_registry.json"
    _write_json(role_config_path, _role_config_registry_payload())

    monkeypatch.setenv("CORTEXPILOT_AGENT_REGISTRY", str(repo_root / "policies" / "agent_registry.json"))
    monkeypatch.setenv("CORTEXPILOT_ROLE_CONFIG_REGISTRY", str(role_config_path))
    monkeypatch.delenv("CORTEXPILOT_PROVIDER_BASE_URL", raising=False)
    monkeypatch.delenv("CORTEXPILOT_CODEX_MODEL", raising=False)
    monkeypatch.delenv("CORTEXPILOT_PROVIDER_MODEL", raising=False)

    client = TestClient(api_main.app)

    get_response = client.get("/api/agents/roles/worker/config")
    assert get_response.status_code == 200
    get_payload = get_response.json()
    assert get_payload["authority"] == "repo-owned-role-config"
    assert get_payload["execution_authority"] == "task_contract"
    assert get_payload["editable_now"]["system_prompt_ref"] == "policies/agents/codex/roles/50_worker_core.md"
    assert get_payload["field_modes"]["purpose"] == "reserved-for-later"

    preview_response = client.post(
        "/api/agents/roles/worker/config/preview",
        json={
            "system_prompt_ref": "policies/agents/codex/roles/50_worker_core.md",
            "skills_bundle_ref": "policies/skills_bundle_registry.json#bundles.worker_delivery_core_v1",
            "mcp_bundle_ref": "policies/agent_registry.json#agents(role=WORKER).capabilities.mcp_tools",
            "runtime_binding": {
                "runner": "codex",
                "provider": "anthropic",
                "model": "claude-3-5-sonnet",
            },
        },
    )
    assert preview_response.status_code == 200
    preview_payload = preview_response.json()
    assert preview_payload["role"] == "WORKER"
    assert preview_payload["can_apply"] is True
    assert any(item["field"] == "runtime_binding.runner" for item in preview_payload["changes"])
    assert preview_payload["preview_surface"]["runtime_capability"]["provider_status"] == "allowlisted"

    missing_role = client.post(
        "/api/agents/roles/worker/config/apply",
        json={
            "system_prompt_ref": "policies/agents/codex/roles/50_worker_core.md",
            "skills_bundle_ref": "policies/skills_bundle_registry.json#bundles.worker_delivery_core_v1",
            "mcp_bundle_ref": "policies/agent_registry.json#agents(role=WORKER).capabilities.mcp_tools",
            "runtime_binding": {
                "runner": "codex",
                "provider": "anthropic",
                "model": "claude-3-5-sonnet",
            },
        },
    )
    assert missing_role.status_code == 403
    assert missing_role.json()["detail"]["code"] == "ROLE_REQUIRED"

    apply_response = client.post(
        "/api/agents/roles/worker/config/apply",
        headers={"x-cortexpilot-role": "TECH_LEAD"},
        json={
            "system_prompt_ref": "policies/agents/codex/roles/50_worker_core.md",
            "skills_bundle_ref": "policies/skills_bundle_registry.json#bundles.worker_delivery_core_v1",
            "mcp_bundle_ref": "policies/agent_registry.json#agents(role=WORKER).capabilities.mcp_tools",
            "runtime_binding": {
                "runner": "codex",
                "provider": "anthropic",
                "model": "claude-3-5-sonnet",
            },
        },
    )
    assert apply_response.status_code == 200
    apply_payload = apply_response.json()
    assert apply_payload["saved"] is True
    assert apply_payload["surface"]["editable_now"]["runtime_binding"]["runner"] == "codex"
    assert apply_payload["surface"]["runtime_capability"]["tool_execution"] == "provider-path-required"

    written = json.loads(role_config_path.read_text(encoding="utf-8"))
    assert written["roles"]["WORKER"]["runtime_binding"] == {
        "runner": "codex",
        "provider": "anthropic",
        "model": "claude-3-5-sonnet",
    }


def test_role_config_routes_fail_closed_on_invalid_provider(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    _write_json(repo_root / "policies" / "agent_registry.json", _agent_registry_payload())
    _write_json(repo_root / "policies" / "skills_bundle_registry.json", _skills_bundle_registry_payload())
    _write_json(repo_root / "policies" / "role_config_registry.json", _role_config_registry_payload())

    monkeypatch.setenv("CORTEXPILOT_AGENT_REGISTRY", str(repo_root / "policies" / "agent_registry.json"))
    monkeypatch.setenv("CORTEXPILOT_ROLE_CONFIG_REGISTRY", str(repo_root / "policies" / "role_config_registry.json"))

    client = TestClient(api_main.app)
    preview_response = client.post(
        "/api/agents/roles/worker/config/preview",
        json={
            "system_prompt_ref": "policies/agents/codex/roles/50_worker_core.md",
            "skills_bundle_ref": "policies/skills_bundle_registry.json#bundles.worker_delivery_core_v1",
            "mcp_bundle_ref": "policies/agent_registry.json#agents(role=WORKER).capabilities.mcp_tools",
            "runtime_binding": {
                "runner": "agents",
                "provider": "not-a-real-provider",
                "model": None,
            },
        },
    )
    assert preview_response.status_code == 400
    assert preview_response.json()["detail"]["code"] == "ROLE_CONFIG_PREVIEW_INVALID"


def test_role_config_runtime_capability_import_stays_lightweight(tmp_path: Path) -> None:
    probe = tmp_path / "probe_role_config_import.py"
    probe.write_text(
        textwrap.dedent(
            """
            import builtins
            import importlib

            original_import = builtins.__import__

            def blocked_import(name, globals=None, locals=None, fromlist=(), level=0):
                if name == "httpx":
                    raise ModuleNotFoundError("No module named 'httpx'")
                return original_import(name, globals, locals, fromlist, level)

            builtins.__import__ = blocked_import

            module = importlib.import_module("cortexpilot_orch.contract.role_config_registry")
            summary = module.build_runtime_capability_summary(
                {
                    "runner": "codex",
                    "provider": "anthropic",
                    "model": "claude-3-5-sonnet",
                }
            )
            assert summary["provider_status"] == "allowlisted"
            assert summary["tool_execution"] == "provider-path-required"
            """
        ),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(api_main.__file__).resolve().parents[2])
    result = subprocess.run(
        [sys.executable, str(probe)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
