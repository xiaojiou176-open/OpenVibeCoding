from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_module() -> object:
    script_path = Path(__file__).resolve().parents[3] / "scripts" / "check_github_control_plane.py"
    spec = importlib.util.spec_from_file_location("cortexpilot_check_github_control_plane", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _policy_payload() -> dict:
    return {
        "owner": "example",
        "repo": "repo",
        "default_branch": "main",
        "required_actions_permissions": {
            "enabled": True,
            "allowed_actions": "all",
            "sha_pinning_required": True,
        },
        "required_environments": ["owner-approved-sensitive"],
        "required_checks": ["Quick Feedback"],
        "branch_protection_required": True,
        "platform_evidence": {
            "private_vulnerability_reporting": {"required": True, "mode": "api"},
            "vulnerability_alerts": {"required": True, "mode": "api"},
            "secret_scanning": {"required": True, "mode": "api"},
            "secret_scanning_push_protection": {"required": True, "mode": "api"},
            "secret_scanning_non_provider_patterns": {"required": True, "mode": "api"},
            "secret_scanning_validity_checks": {"required": True, "mode": "api"},
            "dependabot_config": {"required": True, "mode": "repo_file", "path": ".github/dependabot.yml"},
            "codeql_workflow": {"required": True, "mode": "repo_file", "path": ".github/workflows/codeql.yml"},
            "codeql_config": {"required": True, "mode": "repo_file", "path": ".github/codeql/codeql-config.yml"},
        },
    }


def _fake_gh_json(secret_non_provider: str, validity_checks: str):
    def _impl(path: str) -> tuple[int, dict]:
        if path == "repos/example/repo":
            return (
                0,
                {
                    "default_branch": "main",
                    "security_and_analysis": {
                        "secret_scanning": {"status": "enabled"},
                        "secret_scanning_push_protection": {"status": "enabled"},
                        "secret_scanning_non_provider_patterns": {"status": secret_non_provider},
                        "secret_scanning_validity_checks": {"status": validity_checks},
                    },
                },
            )
        if path == "repos/example/repo/actions/permissions":
            return 0, {"enabled": True, "allowed_actions": "all", "sha_pinning_required": True}
        if path == "repos/example/repo/branches/main/protection":
            return 0, {"required_status_checks": {"contexts": ["Quick Feedback"]}}
        if path == "repos/example/repo/environments":
            return 0, {"environments": [{"name": "owner-approved-sensitive"}]}
        if path == "repos/example/repo/private-vulnerability-reporting":
            return 0, {"enabled": True}
        if path == "repos/example/repo/vulnerability-alerts":
            return 0, {}
        if path == "repos/example/repo/code-scanning/default-setup":
            return 0, {}
        if path == "repos/example/repo/dependabot/alerts?per_page=1":
            return 0, []
        raise AssertionError(path)

    return _impl


def test_github_control_plane_requires_secret_scanning_subfeatures(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    policy_path = tmp_path / "policy.json"
    output_path = tmp_path / "report.json"
    policy_path.write_text(json.dumps(_policy_payload(), ensure_ascii=False, indent=2), encoding="utf-8")

    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "_gh_json", _fake_gh_json("disabled", "disabled"))
    monkeypatch.setattr(module, "_repo_path_exists", lambda _path: True)
    monkeypatch.setattr(sys, "argv", ["check_github_control_plane.py", "--policy", str(policy_path), "--output", str(output_path)])

    rc = module.main()
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert rc == 1
    assert any("secret_scanning_non_provider_patterns drift" in item for item in report["errors"])
    assert any("secret_scanning_validity_checks drift" in item for item in report["errors"])


def test_github_control_plane_accepts_enabled_secret_scanning_subfeatures(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    policy_path = tmp_path / "policy.json"
    output_path = tmp_path / "report.json"
    policy_path.write_text(json.dumps(_policy_payload(), ensure_ascii=False, indent=2), encoding="utf-8")

    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "_gh_json", _fake_gh_json("enabled", "enabled"))
    monkeypatch.setattr(module, "_repo_path_exists", lambda _path: True)
    monkeypatch.setattr(sys, "argv", ["check_github_control_plane.py", "--policy", str(policy_path), "--output", str(output_path)])

    rc = module.main()
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert rc == 0
    assert report["errors"] == []
    assert report["security_and_analysis"]["secret_scanning_non_provider_patterns"]["status"] == "enabled"
