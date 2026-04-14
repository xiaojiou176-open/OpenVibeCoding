from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from openvibecoding_orch.runtime.space_governance import (
    build_space_governance_report,
    evaluate_cleanup_gate,
    load_space_governance_policy,
    policy_hash,
    resolve_policy_path,
)

SCRIPT_ROOT = Path(__file__).resolve().parents[3]


def _load_gate_script_module():
    spec = importlib.util.spec_from_file_location(
        "openvibecoding_check_space_cleanup_gate",
        SCRIPT_ROOT / "scripts" / "check_space_cleanup_gate.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_inventory_script_module():
    spec = importlib.util.spec_from_file_location(
        "openvibecoding_check_space_governance_inventory",
        SCRIPT_ROOT / "scripts" / "check_space_governance_inventory.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_file(path: Path, content: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _age(path: Path, *, hours: int) -> None:
    ts = (datetime.now(timezone.utc) - timedelta(hours=hours)).timestamp()
    os.utime(path, (ts, ts), follow_symlinks=False)


def _base_policy(repo_root: Path, home_root: Path) -> dict:
    return {
        "version": 1,
        "recent_activity_hours": 24,
        "apply_gate_max_age_minutes": 15,
        "shared_realpath_prefixes": [str(home_root / ".cache" / "jarvis")],
        "process_groups": {
            "node": {"patterns": ["\\bnode\\b"]},
            "python": {"patterns": ["\\bpython\\b"]},
        },
        "rebuild_commands": [
            {"id": "bootstrap", "kind": "npm_script", "script": "bootstrap", "description": "bootstrap"},
            {
                "id": "dashboard_deps",
                "kind": "shell_script",
                "path": "scripts/install_dashboard_deps.sh",
                "description": "dashboard deps",
            },
        ],
        "layers": {
            "repo_internal": [
                {
                    "id": "dashboard_node_modules",
                    "path": "apps/dashboard/node_modules",
                    "type": "dependency",
                    "ownership": "repo local",
                    "ownership_confidence": "High",
                    "sharedness": "repo_local",
                    "rebuildability": "rebuildable",
                    "recommendation": "cautious_cleanup",
                    "cleanup_mode": "remove-path",
                    "risk": "medium",
                    "rebuild_command_ids": ["dashboard_deps", "bootstrap"],
                    "evidence": ["scripts/install_dashboard_deps.sh"],
                    "notes": "repo local dependency copy",
                },
                {
                    "id": "runtime_test_output",
                    "path": ".runtime-cache/test_output",
                    "type": "evidence",
                    "ownership": "repo local",
                    "ownership_confidence": "High",
                    "sharedness": "repo_local",
                    "rebuildability": "rebuildable",
                    "recommendation": "needs_verification",
                    "cleanup_mode": "aged-children",
                    "cleanup_scan_depth": 1,
                    "cleanup_min_age_hours": 48,
                    "risk": "medium",
                    "rebuild_command_ids": ["bootstrap"],
                    "evidence": ["scripts/test_quick.sh"],
                    "notes": "stale evidence only",
                },
            ],
            "repo_external_related": [
                {
                    "id": "external_python_toolchain_current",
                    "path": str(home_root / ".cache" / "openvibecoding" / "toolchains" / "python" / "current"),
                    "type": "toolchain symlink",
                    "ownership": "repo related",
                    "ownership_confidence": "Medium",
                    "sharedness": "repo_machine_shared",
                    "rebuildability": "unknown",
                    "recommendation": "needs_verification",
                    "cleanup_mode": "observe-only",
                    "risk": "high",
                    "rebuild_command_ids": ["bootstrap"],
                    "evidence": ["scripts/lib/toolchain_env.sh"],
                    "notes": "must not be single-repo cleanup target if it resolves into jarvis",
                }
            ],
            "shared_observation": [],
        },
        "wave_targets": {
            "wave1": {
                "target_ids": ["runtime_test_output"],
                "process_groups": ["node", "python"],
                "required_rebuild_commands": ["bootstrap"],
            },
            "wave2": {
                "target_ids": ["dashboard_node_modules"],
                "process_groups": ["node"],
                "required_rebuild_commands": ["dashboard_deps", "bootstrap"],
            },
            "wave3": {
                "target_ids": ["external_python_toolchain_current"],
                "process_groups": ["python"],
                "required_rebuild_commands": ["bootstrap"],
            },
        },
    }


def test_toolchain_env_machine_tmp_root_defaults_ci_and_override(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    helper_path = SCRIPT_ROOT / "scripts" / "lib" / "toolchain_env.sh"
    home_root = tmp_path / "home"

    env = os.environ.copy()
    env["HOME"] = str(home_root)
    env.pop("XDG_CACHE_HOME", None)
    env.pop("OPENVIBECODING_MACHINE_CACHE_ROOT", None)
    env.pop("CI", None)
    env.pop("GITHUB_ACTIONS", None)
    env.pop("RUNNER_TEMP", None)

    proc = subprocess.run(
        ["bash", "-lc", f"source '{helper_path}' && openvibecoding_machine_tmp_root '{repo_root}'"],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    assert proc.stdout.strip() == str(home_root / ".cache" / "openvibecoding" / "tmp")

    env["RUNNER_TEMP"] = str(tmp_path / "runner-temp")
    env["CI"] = "1"
    env["GITHUB_ACTIONS"] = "true"
    proc = subprocess.run(
        ["bash", "-lc", f"source '{helper_path}' && openvibecoding_machine_tmp_root '{repo_root}'"],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    assert proc.stdout.strip() == str(tmp_path / "runner-temp" / "openvibecoding-machine-cache" / "tmp")

    env["OPENVIBECODING_MACHINE_CACHE_ROOT"] = str(tmp_path / "machine-cache")
    proc = subprocess.run(
        ["bash", "-lc", f"source '{helper_path}' && openvibecoding_machine_tmp_root '{repo_root}'"],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    assert proc.stdout.strip() == str(tmp_path / "machine-cache" / "tmp")


def test_resolve_policy_path_uses_machine_cache_root_placeholder_defaults_and_override(
    tmp_path: Path, monkeypatch
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    home_root = tmp_path / "home"

    monkeypatch.setenv("HOME", str(home_root))
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.delenv("OPENVIBECODING_MACHINE_CACHE_ROOT", raising=False)

    resolved = resolve_policy_path(
        raw_path="${OPENVIBECODING_MACHINE_CACHE_ROOT}/tmp/docker-ci/runner-temp-1000",
        repo_root=repo_root,
    )
    assert resolved == home_root / ".cache" / "openvibecoding" / "tmp" / "docker-ci" / "runner-temp-1000"

    monkeypatch.setenv("OPENVIBECODING_MACHINE_CACHE_ROOT", str(tmp_path / "machine-cache"))
    resolved = resolve_policy_path(
        raw_path="${OPENVIBECODING_MACHINE_CACHE_ROOT}/tmp/clean-room-machine-cache.test",
        repo_root=repo_root,
    )
    assert resolved == tmp_path / "machine-cache" / "tmp" / "clean-room-machine-cache.test"


def test_space_governance_report_marks_shared_symlink_targets(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    home_root = tmp_path / "home"
    _write_file(repo_root / "package.json", json.dumps({"scripts": {"bootstrap": "echo ok"}}))
    _write_file(repo_root / "scripts" / "install_dashboard_deps.sh", "#!/usr/bin/env bash\n")
    _write_file(repo_root / "apps" / "dashboard" / "node_modules" / "pkg" / "index.js", "console.log('x')")

    jarvis_target = home_root / ".cache" / "jarvis" / "toolchains" / "python" / "current"
    _write_file(jarvis_target / "bin" / "python", "python")
    symlink_path = home_root / ".cache" / "openvibecoding" / "toolchains" / "python" / "current"
    symlink_path.parent.mkdir(parents=True, exist_ok=True)
    symlink_path.symlink_to(jarvis_target, target_is_directory=True)

    policy_path = tmp_path / "space_policy.json"
    policy_path.write_text(json.dumps(_base_policy(repo_root, home_root), ensure_ascii=False, indent=2), encoding="utf-8")

    policy = load_space_governance_policy(policy_path)
    report = build_space_governance_report(repo_root=repo_root, policy=policy, ps_lines=[])

    entry = next(item for item in report["entries"] if item["policy_entry_id"] == "external_python_toolchain_current")
    assert entry["path_is_symlink"] is True
    assert entry["shared_realpath_escape"] is True
    assert any(item["policy_entry_id"] == "external_python_toolchain_current" for item in report["needs_verification"])


def test_cleanup_gate_blocks_active_processes_and_requires_recent_confirmation(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    home_root = tmp_path / "home"
    _write_file(repo_root / "package.json", json.dumps({"scripts": {"bootstrap": "echo ok"}}))
    _write_file(repo_root / "scripts" / "install_dashboard_deps.sh", "#!/usr/bin/env bash\n")
    node_modules_file = repo_root / "apps" / "dashboard" / "node_modules" / "pkg" / "index.js"
    _write_file(node_modules_file, "console.log('x')")

    policy_path = tmp_path / "space_policy.json"
    policy_path.write_text(json.dumps(_base_policy(repo_root, home_root), ensure_ascii=False, indent=2), encoding="utf-8")
    policy = load_space_governance_policy(policy_path)

    report_blocked = build_space_governance_report(
        repo_root=repo_root,
        policy=policy,
        ps_lines=[f"123 node {repo_root}/apps/dashboard/node_modules/.bin/next dev"],
    )
    gate_blocked = evaluate_cleanup_gate(
        repo_root=repo_root,
        policy=policy,
        report=report_blocked,
        wave="wave2",
        ps_lines=[f"123 node {repo_root}/apps/dashboard/node_modules/.bin/next dev"],
    )
    assert gate_blocked["status"] == "blocked"
    assert gate_blocked["blocked_reasons"]

    report_recent = build_space_governance_report(repo_root=repo_root, policy=policy, ps_lines=[])
    gate_recent = evaluate_cleanup_gate(
        repo_root=repo_root,
        policy=policy,
        report=report_recent,
        wave="wave2",
        ps_lines=[],
    )
    assert gate_recent["status"] == "manual_confirmation_required"
    assert any("recent activity" in item for item in gate_recent["manual_reasons"])


def test_cleanup_gate_does_not_hard_block_unrelated_global_processes(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    home_root = tmp_path / "home"
    _write_file(repo_root / "package.json", json.dumps({"scripts": {"bootstrap": "echo ok"}}))
    _write_file(repo_root / "scripts" / "install_dashboard_deps.sh", "#!/usr/bin/env bash\n")
    node_modules_file = repo_root / "apps" / "dashboard" / "node_modules" / "pkg" / "index.js"
    _write_file(node_modules_file, "console.log('x')")
    _age(node_modules_file, hours=96)

    policy_path = tmp_path / "space_policy.json"
    policy_path.write_text(json.dumps(_base_policy(repo_root, home_root), ensure_ascii=False, indent=2), encoding="utf-8")
    policy = load_space_governance_policy(policy_path)

    report = build_space_governance_report(
        repo_root=repo_root,
        policy=policy,
        ps_lines=["123 node /opt/homebrew/bin/RunnerService.js"],
    )
    gate = evaluate_cleanup_gate(
        repo_root=repo_root,
        policy=policy,
        report=report,
        wave="wave2",
        ps_lines=["123 node /opt/homebrew/bin/RunnerService.js"],
    )

    assert gate["status"] == "manual_confirmation_required"
    assert not gate["blocked_reasons"]
    assert gate["manual_confirmation_findings"]
    assert gate["manual_confirmation_findings"][0]["evidence_scope"] == "unknown"


def test_wave3_does_not_promote_unrelated_playwright_or_cargo_processes_to_target_scoped(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    home_root = tmp_path / "home"
    _write_file(repo_root / "package.json", json.dumps({"scripts": {"bootstrap": "echo ok"}}))
    _write_file(repo_root / "scripts" / "install_dashboard_deps.sh", "#!/usr/bin/env bash\n")
    _write_file(home_root / ".cache" / "openvibecoding" / "playwright" / "browsers.json", "{}")
    _age(home_root / ".cache" / "openvibecoding" / "playwright" / "browsers.json", hours=96)

    policy_path = tmp_path / "space_policy.json"
    policy_payload = _base_policy(repo_root, home_root)
    policy_payload["process_groups"]["playwright"] = {"patterns": ["playwright"]}
    policy_payload["process_groups"]["cargo"] = {"patterns": ["\\bcargo\\b"]}
    policy_payload["layers"]["repo_external_related"].append(
        {
            "id": "external_playwright_cache",
            "path": str(home_root / ".cache" / "openvibecoding" / "playwright"),
            "type": "playwright cache",
            "ownership": "repo related",
            "ownership_confidence": "High",
            "sharedness": "repo_machine_shared",
            "rebuildability": "rebuildable",
                    "recommendation": "needs_verification",
                    "cleanup_mode": "remove-path",
                    "retention_auto_cleanup": True,
                    "retention_ttl_hours": 24,
                    "risk": "medium",
            "rebuild_command_ids": ["bootstrap"],
            "evidence": ["scripts/bootstrap.sh"],
        }
    )
    policy_payload["wave_targets"]["wave3"] = {
        "target_ids": ["external_playwright_cache"],
        "process_groups": ["playwright", "cargo"],
        "process_path_hints": [str(home_root / ".cache" / "openvibecoding" / "playwright")],
        "process_command_hints": ["playwright", "cargo"],
        "required_rebuild_commands": ["bootstrap"],
    }
    policy_path.write_text(json.dumps(policy_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    policy = load_space_governance_policy(policy_path)

    report = build_space_governance_report(
        repo_root=repo_root,
        policy=policy,
        ps_lines=[
            "111 node /opt/homebrew/bin/pnpm exec playwright test",
            "222 cargo test --workspace",
        ],
    )
    gate = evaluate_cleanup_gate(
        repo_root=repo_root,
        policy=policy,
        report=report,
        wave="wave3",
        ps_lines=[
            "111 node /opt/homebrew/bin/pnpm exec playwright test",
            "222 cargo test --workspace",
        ],
    )

    assert gate["status"] == "manual_confirmation_required"
    assert not gate["blocked_reasons"]
    assert all(
        finding["blocking_reason_kind"] == "unknown"
        for finding in gate["manual_confirmation_findings"]
        if finding.get("process_group") in {"playwright", "cargo"}
    )


def test_wave1_does_not_promote_other_repo_runtime_cache_processes_to_target_scoped(tmp_path: Path) -> None:
    repo_root = tmp_path / "openvibecoding_repo"
    home_root = tmp_path / "home"
    _write_file(repo_root / "package.json", json.dumps({"scripts": {"bootstrap": "echo ok"}}))
    _write_file(repo_root / "scripts" / "install_dashboard_deps.sh", "#!/usr/bin/env bash\n")
    stale_file = repo_root / ".runtime-cache" / "test_output" / "stale.json"
    _write_file(stale_file, "{}")
    _age(stale_file, hours=96)

    policy_path = tmp_path / "space_policy.json"
    policy_payload = _base_policy(repo_root, home_root)
    policy_payload["process_groups"]["docker"] = {"patterns": ["\\bdocker\\b"]}
    policy_payload["wave_targets"]["wave1"]["process_groups"] = ["docker", "node", "python"]
    policy_payload["wave_targets"]["wave1"]["process_path_hints"] = [".runtime-cache"]
    policy_payload["wave_targets"]["wave1"]["process_command_hints"] = ["OpenVibeCoding", ".runtime-cache"]
    policy_path.write_text(json.dumps(policy_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    policy = load_space_governance_policy(policy_path)

    foreign_command = (
        "123 docker compose -f /runner-root/work/other-repo/docker/compose.yml "
        "run --rm -v /runner-root/work/other-repo:/workspace "
        "-e UI_RUNTIME_CACHE_ROOT=/workspace/.runtime-cache ci-gate bash -lc 'echo test'"
    )

    report = build_space_governance_report(repo_root=repo_root, policy=policy, ps_lines=[foreign_command])
    gate = evaluate_cleanup_gate(
        repo_root=repo_root,
        policy=policy,
        report=report,
        wave="wave1",
        ps_lines=[foreign_command],
    )

    assert gate["status"] == "manual_confirmation_required"
    assert not gate["blocked_reasons"]
    assert gate["manual_confirmation_findings"]
    assert gate["manual_confirmation_findings"][0]["evidence_scope"] == "unknown"


def test_space_governance_report_collects_only_stale_cleanup_candidates(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    home_root = tmp_path / "home"
    _write_file(repo_root / "package.json", json.dumps({"scripts": {"bootstrap": "echo ok"}}))
    _write_file(repo_root / "scripts" / "install_dashboard_deps.sh", "#!/usr/bin/env bash\n")
    stale_file = repo_root / ".runtime-cache" / "test_output" / "stale.json"
    fresh_file = repo_root / ".runtime-cache" / "test_output" / "fresh.json"
    _write_file(stale_file, "{}")
    _write_file(fresh_file, "{}")
    _age(stale_file, hours=96)

    policy_path = tmp_path / "space_policy.json"
    policy_path.write_text(json.dumps(_base_policy(repo_root, home_root), ensure_ascii=False, indent=2), encoding="utf-8")
    policy = load_space_governance_policy(policy_path)

    report = build_space_governance_report(repo_root=repo_root, policy=policy, ps_lines=[])
    entry = next(item for item in report["entries"] if item["policy_entry_id"] == "runtime_test_output")
    candidate_paths = {item["path"] for item in entry["cleanup_candidates"]}
    assert str(stale_file) in candidate_paths
    assert str(fresh_file) not in candidate_paths

    gate = evaluate_cleanup_gate(
        repo_root=repo_root,
        policy=policy,
        report=report,
        wave="wave1",
        allow_recent=False,
    )
    eligible_paths = {item["path"] for item in gate["eligible_targets"]}
    assert str(stale_file) in eligible_paths
    assert str(fresh_file) not in eligible_paths


def test_space_governance_report_uses_exclusive_summary_for_external_rollup(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    home_root = tmp_path / "home"
    _write_file(repo_root / "package.json", json.dumps({"scripts": {"bootstrap": "echo ok"}}))
    _write_file(repo_root / "scripts" / "install_dashboard_deps.sh", "#!/usr/bin/env bash\n")
    pnpm_store_file = home_root / ".cache" / "openvibecoding" / "pnpm-store" / "pkg" / "artifact.tgz"
    _write_file(pnpm_store_file, "x" * 1024)

    policy_path = tmp_path / "space_policy.json"
    policy_payload = _base_policy(repo_root, home_root)
    policy_payload["layers"]["repo_external_related"].insert(
        0,
        {
            "id": "external_machine_cache_root",
            "path": str(home_root / ".cache" / "openvibecoding"),
            "type": "machine cache root",
            "ownership": "repo external root",
            "ownership_confidence": "High",
            "sharedness": "repo_machine_shared",
            "summary_role": "rollup_root",
            "rebuildability": "rebuildable",
            "recommendation": "needs_verification",
            "cleanup_mode": "observe-only",
            "risk": "medium",
            "rebuild_command_ids": ["bootstrap"],
            "evidence": ["scripts/lib/toolchain_env.sh"],
        },
    )
    policy_payload["layers"]["repo_external_related"].insert(
        1,
        {
            "id": "external_pnpm_store",
            "path": str(home_root / ".cache" / "openvibecoding" / "pnpm-store"),
            "type": "pnpm store",
            "ownership": "repo external pnpm store",
            "ownership_confidence": "High",
            "sharedness": "repo_machine_shared",
            "summary_role": "breakdown_only",
            "rebuildability": "rebuildable",
                    "recommendation": "needs_verification",
                    "cleanup_mode": "remove-path",
                    "retention_auto_cleanup": True,
                    "retention_ttl_hours": 24,
                    "risk": "medium",
            "rebuild_command_ids": ["dashboard_deps"],
            "evidence": ["scripts/install_dashboard_deps.sh"],
        },
    )
    policy_path.write_text(json.dumps(policy_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    policy = load_space_governance_policy(policy_path)

    report = build_space_governance_report(repo_root=repo_root, policy=policy, ps_lines=[])
    root_entry = next(item for item in report["entries"] if item["policy_entry_id"] == "external_machine_cache_root")
    child_entry = next(item for item in report["entries"] if item["policy_entry_id"] == "external_pnpm_store")

    assert report["summary"]["bucket_counting_mode"] == "exclusive"
    assert report["summary"]["repo_external_related_total_bytes"] == root_entry["size_bytes"]
    assert root_entry["counted_in_summary"] is True
    assert child_entry["counted_in_summary"] is False
    assert child_entry["summary_exclusion_reason"] == "breakdown-only"


def test_wave3_reports_machine_tmp_entries_with_producer_and_lifecycle(
    tmp_path: Path, monkeypatch
) -> None:
    repo_root = tmp_path / "repo"
    home_root = tmp_path / "home"
    _write_file(
        repo_root / "package.json",
        json.dumps({"scripts": {"bootstrap": "echo ok", "test:quick": "echo quick"}}),
    )
    _write_file(repo_root / "scripts" / "docker_ci.sh", "#!/usr/bin/env bash\n")
    _write_file(repo_root / "scripts" / "check_clean_room_recovery.sh", "#!/usr/bin/env bash\n")

    docker_runner_file = (
        home_root / ".cache" / "openvibecoding" / "tmp" / "docker-ci" / "runner-temp-1000" / "marker.txt"
    )
    clean_room_file = (
        home_root / ".cache" / "openvibecoding" / "tmp" / "clean-room-machine-cache.ABCD" / "marker.txt"
    )
    preserve_file = (
        home_root / ".cache" / "openvibecoding" / "tmp" / "clean-room-preserve.WXYZ" / "marker.txt"
    )
    _write_file(docker_runner_file, "runner")
    _write_file(clean_room_file, "clean-room")
    _write_file(preserve_file, "preserve")
    _age(docker_runner_file.parent, hours=96)
    _age(clean_room_file.parent, hours=96)
    _age(preserve_file.parent, hours=96)

    monkeypatch.setenv("HOME", str(home_root))
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.delenv("OPENVIBECODING_MACHINE_CACHE_ROOT", raising=False)

    policy_payload = _base_policy(repo_root, home_root)
    policy_payload["rebuild_commands"].extend(
        [
            {
                "id": "docker_ci_test_quick",
                "kind": "shell_script",
                "path": "scripts/docker_ci.sh",
                "args": ["test-quick"],
                "description": "docker_ci quick",
            },
            {
                "id": "clean_room_recovery",
                "kind": "shell_script",
                "path": "scripts/check_clean_room_recovery.sh",
                "args": ["--skip-governance-scorecard"],
                "description": "clean room recovery",
            },
        ]
    )
    policy_payload["layers"]["repo_external_related"].insert(
        0,
        {
            "id": "external_machine_cache_root",
            "path": "${OPENVIBECODING_MACHINE_CACHE_ROOT}",
            "type": "machine cache root",
            "ownership": "repo external root",
            "ownership_confidence": "High",
            "sharedness": "repo_machine_shared",
            "summary_role": "rollup_root",
            "rebuildability": "rebuildable",
            "recommendation": "needs_verification",
            "cleanup_mode": "observe-only",
            "risk": "medium",
            "rebuild_command_ids": ["bootstrap"],
            "evidence": ["scripts/lib/toolchain_env.sh"],
        },
    )
    policy_payload["layers"]["repo_external_related"].extend(
        [
            {
                "id": "external_tmp_docker_ci_runner_temp",
                "path": "${OPENVIBECODING_MACHINE_CACHE_ROOT}/tmp/docker-ci/runner-temp-*",
                "type": "docker_ci runner temp",
                "ownership": "repo-owned docker_ci temp",
                "ownership_confidence": "High",
                "sharedness": "repo_machine_shared",
                "summary_role": "breakdown_only",
                "rebuildability": "rebuildable",
                "recommendation": "needs_verification",
                "cleanup_mode": "remove-path",
                "retention_auto_cleanup": True,
                "retention_ttl_hours": 24,
                "risk": "medium",
                "rebuild_command_ids": ["docker_ci_test_quick"],
                "post_cleanup_command_ids": ["docker_ci_test_quick"],
                "apply_serial_only": True,
                "producer": "docker_ci_runner_temp",
                "lifecycle": "machine_tmp",
                "evidence": ["scripts/docker_ci.sh"],
                "notes": "repo-owned docker_ci tmp",
            },
            {
                "id": "external_tmp_clean_room_machine_cache",
                "path": "${OPENVIBECODING_MACHINE_CACHE_ROOT}/tmp/clean-room-machine-cache.*",
                "type": "clean-room machine cache",
                "ownership": "repo-owned clean-room temp",
                "ownership_confidence": "High",
                "sharedness": "repo_machine_shared",
                "summary_role": "breakdown_only",
                "rebuildability": "rebuildable",
                "recommendation": "needs_verification",
                "cleanup_mode": "remove-path",
                "retention_auto_cleanup": True,
                "retention_ttl_hours": 24,
                "risk": "medium",
                "rebuild_command_ids": ["clean_room_recovery"],
                "post_cleanup_command_ids": ["clean_room_recovery"],
                "apply_serial_only": True,
                "producer": "clean_room_recovery",
                "lifecycle": "machine_tmp",
                "evidence": ["scripts/check_clean_room_recovery.sh"],
                "notes": "repo-owned clean-room machine cache",
            },
            {
                "id": "external_tmp_clean_room_preserve",
                "path": "${OPENVIBECODING_MACHINE_CACHE_ROOT}/tmp/clean-room-preserve.*",
                "type": "clean-room preserve temp",
                "ownership": "repo-owned clean-room preserve temp",
                "ownership_confidence": "High",
                "sharedness": "repo_machine_shared",
                "summary_role": "breakdown_only",
                "rebuildability": "rebuildable",
                "recommendation": "needs_verification",
                "cleanup_mode": "remove-path",
                "retention_auto_cleanup": True,
                "retention_ttl_hours": 24,
                "risk": "medium",
                "rebuild_command_ids": ["clean_room_recovery"],
                "post_cleanup_command_ids": ["clean_room_recovery"],
                "apply_serial_only": True,
                "producer": "clean_room_recovery",
                "lifecycle": "machine_tmp",
                "evidence": ["scripts/check_clean_room_recovery.sh"],
                "notes": "repo-owned clean-room preserve temp",
            },
        ]
    )
    policy_payload["wave_targets"]["wave3"] = {
        "target_ids": [
            "external_tmp_docker_ci_runner_temp",
            "external_tmp_clean_room_machine_cache",
            "external_tmp_clean_room_preserve",
        ],
        "process_groups": ["node", "python"],
        "process_path_hints": ["${OPENVIBECODING_MACHINE_CACHE_ROOT}/tmp"],
        "process_command_hints": ["scripts/docker_ci.sh", "scripts/check_clean_room_recovery.sh"],
        "required_rebuild_commands": ["docker_ci_test_quick", "clean_room_recovery"],
    }
    policy_path = tmp_path / "space_policy.json"
    policy_path.write_text(json.dumps(policy_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    policy = load_space_governance_policy(policy_path)

    report = build_space_governance_report(repo_root=repo_root, policy=policy, ps_lines=[])
    docker_entry = next(item for item in report["entries"] if item["policy_entry_id"] == "external_tmp_docker_ci_runner_temp")
    clean_room_entry = next(
        item for item in report["entries"] if item["policy_entry_id"] == "external_tmp_clean_room_machine_cache"
    )
    preserve_entry = next(
        item for item in report["entries"] if item["policy_entry_id"] == "external_tmp_clean_room_preserve"
    )

    assert docker_entry["layer"] == "repo_external_related"
    assert docker_entry["producer"] == "docker_ci_runner_temp"
    assert docker_entry["lifecycle"] == "machine_tmp"
    assert docker_entry["retention_auto_cleanup"] is True
    assert docker_entry["retention_ttl_hours"] == 24
    assert clean_room_entry["producer"] == "clean_room_recovery"
    assert clean_room_entry["lifecycle"] == "machine_tmp"
    assert clean_room_entry["retention_ttl_hours"] == 24
    assert preserve_entry["producer"] == "clean_room_recovery"
    assert preserve_entry["retention_ttl_hours"] == 24

    gate = evaluate_cleanup_gate(
        repo_root=repo_root,
        policy=policy,
        report=report,
        wave="wave3",
        allow_recent=True,
        allow_shared=True,
        ps_lines=[],
    )
    assert gate["status"] == "pass"
    eligible = {item["entry_id"]: item for item in gate["eligible_targets"]}
    deferred_ids = {item["entry_id"] for item in gate["deferred_targets"]}
    surfaced_ids = set(eligible) | deferred_ids
    assert surfaced_ids == {
        "external_tmp_docker_ci_runner_temp",
        "external_tmp_clean_room_machine_cache",
        "external_tmp_clean_room_preserve",
    }
    for item in gate["eligible_targets"]:
        assert item["lifecycle"] == "machine_tmp"
        assert item["producer"] in {"docker_ci_runner_temp", "clean_room_recovery"}


def test_space_governance_report_embeds_machine_cache_retention_snapshot(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    runtime_root = repo_root / ".runtime-cache" / "openvibecoding"
    reports_root = runtime_root / "reports"
    reports_root.mkdir(parents=True, exist_ok=True)
    retention_payload = {
        "generated_at": "2026-04-04T12:00:00+00:00",
        "result": {"removed_total": 3},
        "machine_cache_summary": {
            "cap_bytes": 21474836480,
            "candidate_count": 2,
            "candidate_reclaim_bytes": 1024,
        },
        "machine_cache_auto_prune": {
            "status": "pass",
            "reason": "install_dashboard_deps",
        },
    }
    (reports_root / "retention_report.json").write_text(json.dumps(retention_payload), encoding="utf-8")
    home_root = tmp_path / "home"
    _write_file(repo_root / "package.json", json.dumps({"scripts": {"bootstrap": "echo ok"}}))
    _write_file(repo_root / "scripts" / "install_dashboard_deps.sh", "#!/usr/bin/env bash\n")

    policy_path = tmp_path / "space_policy.json"
    policy_path.write_text(json.dumps(_base_policy(repo_root, home_root), ensure_ascii=False, indent=2), encoding="utf-8")
    policy = load_space_governance_policy(policy_path)

    report = build_space_governance_report(repo_root=repo_root, policy=policy, ps_lines=[])

    assert report["retention_summary"]["machine_cache_summary"]["candidate_count"] == 2
    assert report["retention_summary"]["machine_cache_auto_prune"]["status"] == "pass"


def test_space_governance_report_backfills_auto_prune_state_when_retention_report_lacks_it(
    tmp_path: Path, monkeypatch
) -> None:
    repo_root = tmp_path / "repo"
    runtime_root = repo_root / ".runtime-cache" / "openvibecoding"
    reports_root = runtime_root / "reports"
    reports_root.mkdir(parents=True, exist_ok=True)
    (reports_root / "retention_report.json").write_text(
        json.dumps({"generated_at": "2026-04-04T12:00:00+00:00", "result": {"removed_total": 0}}),
        encoding="utf-8",
    )
    machine_cache_root = tmp_path / "machine-cache"
    state_path = machine_cache_root / "retention-auto-prune" / "state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps({"status": "pass", "reason": "manual-proof", "last_attempt_epoch": 123}),
        encoding="utf-8",
    )

    monkeypatch.setenv("OPENVIBECODING_REPO_ROOT", str(repo_root))
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_MACHINE_CACHE_ROOT", str(machine_cache_root))

    home_root = tmp_path / "home"
    _write_file(repo_root / "package.json", json.dumps({"scripts": {"bootstrap": "echo ok"}}))
    _write_file(repo_root / "scripts" / "install_dashboard_deps.sh", "#!/usr/bin/env bash\n")
    policy_path = tmp_path / "space_policy.json"
    policy_path.write_text(json.dumps(_base_policy(repo_root, home_root), ensure_ascii=False, indent=2), encoding="utf-8")
    policy = load_space_governance_policy(policy_path)

    report = build_space_governance_report(repo_root=repo_root, policy=policy, ps_lines=[])

    assert report["retention_summary"]["machine_cache_auto_prune"]["reason"] == "manual-proof"


def test_space_governance_report_embeds_docker_runtime_summary(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    runtime_root = repo_root / ".runtime-cache" / "openvibecoding"
    reports_root = runtime_root / "reports" / "space_governance"
    reports_root.mkdir(parents=True, exist_ok=True)
    (runtime_root / "reports" / "retention_report.json").write_text(
        json.dumps({"generated_at": "2026-04-04T12:00:00+00:00"}),
        encoding="utf-8",
    )
    (reports_root / "docker_runtime.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-04-04T12:10:00+00:00",
                "status": "ok",
                "managed_totals": {"managed_total_human": "1.0 GiB"},
                "plan": {"planned_reclaim_human": "256.0 MiB"},
            }
        ),
        encoding="utf-8",
    )
    home_root = tmp_path / "home"
    _write_file(repo_root / "package.json", json.dumps({"scripts": {"bootstrap": "echo ok"}}))
    _write_file(repo_root / "scripts" / "install_dashboard_deps.sh", "#!/usr/bin/env bash\n")
    policy_path = tmp_path / "space_policy.json"
    policy_path.write_text(json.dumps(_base_policy(repo_root, home_root), ensure_ascii=False, indent=2), encoding="utf-8")
    policy = load_space_governance_policy(policy_path)

    report = build_space_governance_report(repo_root=repo_root, policy=policy, ps_lines=[])

    assert report["docker_runtime_summary"]["status"] == "ok"
    assert report["docker_runtime_summary"]["plan"]["planned_reclaim_human"] == "256.0 MiB"


def test_cleanup_gate_defers_additional_serial_only_targets(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    home_root = tmp_path / "home"
    _write_file(repo_root / "package.json", json.dumps({"scripts": {"bootstrap": "echo ok"}}))
    _write_file(repo_root / "scripts" / "install_dashboard_deps.sh", "#!/usr/bin/env bash\n")
    _write_file(repo_root / "scripts" / "install_desktop_deps.sh", "#!/usr/bin/env bash\n")
    dashboard_file = repo_root / "apps" / "dashboard" / "node_modules" / "pkg" / "index.js"
    desktop_file = repo_root / "apps" / "desktop" / "node_modules" / "pkg" / "index.js"
    _write_file(dashboard_file, "console.log('dashboard')")
    _write_file(desktop_file, "console.log('desktop')")
    _age(dashboard_file, hours=96)
    _age(desktop_file, hours=96)

    policy_payload = _base_policy(repo_root, home_root)
    policy_payload["rebuild_commands"].append(
        {
            "id": "desktop_deps",
            "kind": "shell_script",
            "path": "scripts/install_desktop_deps.sh",
            "description": "desktop deps",
        }
    )
    policy_payload["layers"]["repo_internal"][0]["post_cleanup_command_ids"] = ["dashboard_deps"]
    policy_payload["layers"]["repo_internal"][0]["apply_serial_only"] = True
    policy_payload["layers"]["repo_internal"].append(
        {
            "id": "desktop_node_modules",
            "path": "apps/desktop/node_modules",
            "type": "dependency",
            "ownership": "repo local",
            "ownership_confidence": "High",
            "sharedness": "repo_local",
            "rebuildability": "rebuildable",
            "recommendation": "cautious_cleanup",
            "cleanup_mode": "remove-path",
            "risk": "medium",
            "rebuild_command_ids": ["desktop_deps"],
            "post_cleanup_command_ids": ["desktop_deps"],
            "apply_serial_only": True,
            "evidence": ["scripts/install_desktop_deps.sh"],
        }
    )
    policy_payload["wave_targets"]["wave2"]["target_ids"] = ["dashboard_node_modules", "desktop_node_modules"]
    policy_payload["wave_targets"]["wave2"]["required_rebuild_commands"] = ["dashboard_deps", "desktop_deps", "bootstrap"]
    policy_path = tmp_path / "space_policy.json"
    policy_path.write_text(json.dumps(policy_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    policy = load_space_governance_policy(policy_path)

    report = build_space_governance_report(repo_root=repo_root, policy=policy, ps_lines=[])
    gate = evaluate_cleanup_gate(
        repo_root=repo_root,
        policy=policy,
        report=report,
        wave="wave2",
        allow_recent=True,
        ps_lines=[],
    )

    assert gate["status"] == "pass"
    assert len(gate["eligible_targets"]) == 1
    assert gate["deferred_targets"]
    assert gate["execution_order"][0]["entry_id"] == gate["eligible_targets"][0]["entry_id"]
    assert gate["eligible_targets"][0]["apply_serial_only"] is True
    assert gate["expected_reclaim_bytes"] == gate["eligible_targets"][0]["expected_reclaim_bytes"]


def test_inventory_consistency_script_catches_undeclared_cleanup_target(tmp_path: Path, monkeypatch) -> None:
    runtime_policy = {
        "version": 1,
        "runtime_roots": {"runtime_root": ".runtime-cache/openvibecoding"},
        "namespaces": {},
        "machine_managed_repo_local_roots": ["apps/dashboard/node_modules"],
        "space_governance_gray_zone_roots": [],
        "ephemeral_repo_local_roots": [],
        "workspace_pollution_scan_roots": [],
        "workspace_forbidden_dirnames": [],
        "workspace_forbidden_file_globs": [],
        "machine_cache_roots": ["~/.cache/openvibecoding"],
        "cleanup_policy": {},
        "forbidden_top_level_outputs": ["node_modules", ".pnp.cjs", ".pnp.loader.mjs", "Users"],
        "legacy_runtime_paths": [],
    }
    space_policy = {
        "version": 1,
        "recent_activity_hours": 24,
        "apply_gate_max_age_minutes": 15,
        "shared_realpath_prefixes": [],
        "process_groups": {"node": {"patterns": ["\\bnode\\b"]}},
        "rebuild_commands": [{"id": "dashboard_deps", "kind": "shell_script", "path": "scripts/install_dashboard_deps.sh"}],
        "layers": {
            "repo_internal": [
                {
                    "id": "dashboard_node_modules",
                    "path": "apps/dashboard/node_modules",
                    "type": "dependency",
                    "ownership": "repo local",
                    "ownership_confidence": "High",
                    "sharedness": "repo_local",
                    "rebuildability": "rebuildable",
                    "recommendation": "cautious_cleanup",
                    "cleanup_mode": "remove-path",
                    "risk": "medium",
                    "rebuild_command_ids": ["dashboard_deps"],
                    "post_cleanup_command_ids": ["dashboard_deps"],
                    "evidence": ["scripts/install_dashboard_deps.sh"],
                }
            ],
            "repo_external_related": [],
            "shared_observation": [],
        },
        "wave_targets": {"wave2": {"target_ids": ["dashboard_node_modules"], "process_groups": ["node"], "required_rebuild_commands": ["dashboard_deps"]}},
    }
    cleanup_script = tmp_path / "cleanup_workspace_modules.sh"
    cleanup_script.write_text(
        "\n".join(
            [
                '#!/usr/bin/env bash',
                'cleanup_target "apps/dashboard/node_modules"',
                'cleanup_target "packages/frontend-api-contract/node_modules"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    runtime_policy_path = tmp_path / "runtime.json"
    runtime_policy_path.write_text(json.dumps(runtime_policy, ensure_ascii=False, indent=2), encoding="utf-8")
    space_policy_path = tmp_path / "space.json"
    space_policy_path.write_text(json.dumps(space_policy, ensure_ascii=False, indent=2), encoding="utf-8")

    inventory_module = _load_inventory_script_module()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "check_space_governance_inventory.py",
            "--runtime-policy",
            str(runtime_policy_path),
            "--space-policy",
            str(space_policy_path),
            "--cleanup-script",
            str(cleanup_script),
        ],
    )

    rc = inventory_module.main()
    assert rc == 1


def test_apply_cleanup_rejects_stale_gate_json(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    home_root = tmp_path / "home"
    _write_file(repo_root / "package.json", json.dumps({"scripts": {"bootstrap": "echo ok"}}))
    _write_file(repo_root / "scripts" / "install_dashboard_deps.sh", "#!/usr/bin/env bash\n")
    target_path = repo_root / "apps" / "dashboard" / "node_modules" / "pkg" / "index.js"
    _write_file(target_path, "console.log('x')")
    _age(target_path, hours=96)

    policy_payload = _base_policy(repo_root, home_root)
    policy_path = tmp_path / "space_policy.json"
    policy_path.write_text(json.dumps(policy_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    gate_path = tmp_path / "cleanup_gate.json"
    result_path = tmp_path / "cleanup_result.json"
    gate_path.write_text(
        json.dumps(
            {
                "wave": "wave2",
                "status": "pass",
                "repo_root": str(repo_root),
                "policy_hash": policy_hash(policy_payload),
                "generated_at": (datetime.now(timezone.utc) - timedelta(minutes=120)).isoformat(),
                "gate_max_age_minutes": 15,
                "allow_recent": True,
                "allow_shared": False,
                "eligible_targets": [
                    {
                        "entry_id": "dashboard_node_modules",
                        "path": str(repo_root / "apps" / "dashboard" / "node_modules"),
                        "target_kind": "path",
                        "size_bytes": 0,
                        "classification": "cautious_cleanup",
                        "rebuild_entrypoints": [{"command_id": "dashboard_deps"}],
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_ROOT / "scripts" / "apply_space_cleanup.py"),
            "--repo-root",
            str(repo_root),
            "--policy",
            str(policy_path),
            "--gate-json",
            str(gate_path),
            "--result-json",
            str(result_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 1
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["status"] == "rejected"
    assert any("stale" in item for item in payload["gate_errors"])


def test_apply_cleanup_rejects_symlink_realpath_escape(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    home_root = tmp_path / "home"
    _write_file(repo_root / "package.json", json.dumps({"scripts": {"bootstrap": "echo ok"}}))
    target_outside_repo = tmp_path / "outside" / "danger.txt"
    _write_file(target_outside_repo, "danger")
    symlink_path = repo_root / "safe-link"
    symlink_path.parent.mkdir(parents=True, exist_ok=True)
    symlink_path.symlink_to(target_outside_repo)

    policy_payload = {
        "version": 1,
        "recent_activity_hours": 24,
        "apply_gate_max_age_minutes": 15,
        "shared_realpath_prefixes": [],
        "process_groups": {"node": {"patterns": ["\\bnode\\b"]}},
        "rebuild_commands": [{"id": "bootstrap", "kind": "npm_script", "script": "bootstrap", "description": "bootstrap"}],
        "layers": {
            "repo_internal": [
                {
                    "id": "repo_symlink_target",
                    "path": "safe-link",
                    "type": "repo-local symlink",
                    "ownership": "repo local",
                    "ownership_confidence": "High",
                    "sharedness": "repo_local",
                    "summary_role": "leaf",
                    "rebuildability": "rebuildable",
                    "recommendation": "cautious_cleanup",
                    "cleanup_mode": "remove-path",
                    "risk": "medium",
                    "rebuild_command_ids": ["bootstrap"],
                    "evidence": ["tests"],
                }
            ],
            "repo_external_related": [],
            "shared_observation": [],
        },
        "wave_targets": {
            "wave2": {
                "target_ids": ["repo_symlink_target"],
                "process_groups": ["node"],
                "required_rebuild_commands": ["bootstrap"],
            }
        },
    }
    policy_path = tmp_path / "space_policy.json"
    policy_path.write_text(json.dumps(policy_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    gate_path = tmp_path / "cleanup_gate.json"
    result_path = tmp_path / "cleanup_result.json"
    gate_path.write_text(
        json.dumps(
            {
                "wave": "wave2",
                "status": "pass",
                "repo_root": str(repo_root),
                "policy_hash": policy_hash(policy_payload),
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "gate_max_age_minutes": 15,
                "allow_recent": True,
                "allow_shared": False,
                "eligible_targets": [
                    {
                        "entry_id": "repo_symlink_target",
                        "path": str(symlink_path),
                        "target_kind": "path",
                        "size_bytes": 0,
                        "classification": "cautious_cleanup",
                        "rebuild_entrypoints": [{"command_id": "bootstrap"}],
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_ROOT / "scripts" / "apply_space_cleanup.py"),
            "--repo-root",
            str(repo_root),
            "--policy",
            str(policy_path),
            "--gate-json",
            str(gate_path),
            "--result-json",
            str(result_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 1
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["status"] == "rejected"
    assert payload["rejected_targets"]
    assert "escapes repo root" in payload["rejected_targets"][0]["revalidation_reason"]


def test_apply_cleanup_records_post_cleanup_verification_failure(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    target_path = repo_root / "apps" / "dashboard" / "node_modules"
    _write_file(target_path / "pkg" / "index.js", "console.log('x')")
    failing_script = repo_root / "scripts" / "fail_verify.sh"
    _write_file(
        failing_script,
        "#!/usr/bin/env bash\nexit 7\n",
    )
    failing_script.chmod(0o755)

    policy_payload = {
        "version": 1,
        "recent_activity_hours": 24,
        "apply_gate_max_age_minutes": 15,
        "shared_realpath_prefixes": [],
        "process_groups": {"node": {"patterns": ["\\bnode\\b"]}},
        "rebuild_commands": [
            {"id": "fail_verify", "kind": "shell_script", "path": "scripts/fail_verify.sh", "description": "fail verify"}
        ],
        "layers": {
            "repo_internal": [
                {
                    "id": "dashboard_node_modules",
                    "path": "apps/dashboard/node_modules",
                    "type": "dependency",
                    "ownership": "repo local",
                    "ownership_confidence": "High",
                    "sharedness": "repo_local",
                    "rebuildability": "rebuildable",
                    "recommendation": "cautious_cleanup",
                    "cleanup_mode": "remove-path",
                    "risk": "medium",
                    "rebuild_command_ids": ["fail_verify"],
                    "post_cleanup_command_ids": ["fail_verify"],
                    "evidence": ["scripts/fail_verify.sh"],
                }
            ],
            "repo_external_related": [],
            "shared_observation": [],
        },
        "wave_targets": {"wave2": {"target_ids": ["dashboard_node_modules"], "process_groups": ["node"], "required_rebuild_commands": ["fail_verify"]}},
    }
    policy_path = tmp_path / "space_policy.json"
    policy_path.write_text(json.dumps(policy_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    gate_path = tmp_path / "cleanup_gate.json"
    result_path = tmp_path / "cleanup_result.json"
    gate_path.write_text(
        json.dumps(
            {
                "wave": "wave2",
                "status": "pass",
                "repo_root": str(repo_root),
                "policy_hash": policy_hash(policy_payload),
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "gate_max_age_minutes": 15,
                "allow_recent": True,
                "allow_shared": False,
                "eligible_targets": [
                    {
                        "entry_id": "dashboard_node_modules",
                        "path": str(target_path),
                        "target_kind": "path",
                        "size_bytes": 0,
                        "expected_reclaim_bytes": 0,
                        "classification": "cautious_cleanup",
                        "rebuild_entrypoints": [{"command_id": "fail_verify", "argv": ["bash", str(failing_script)], "available": True}],
                        "post_cleanup_verification_commands": [{"command_id": "fail_verify", "argv": ["bash", str(failing_script)], "available": True}],
                        "apply_serial_only": True,
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_ROOT / "scripts" / "apply_space_cleanup.py"),
            "--repo-root",
            str(repo_root),
            "--policy",
            str(policy_path),
            "--gate-json",
            str(gate_path),
            "--result-json",
            str(result_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 1
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["status"] == "verification_failed"
    assert payload["verification_failures"]
    assert payload["removed_targets"][0]["verification_failed"] is True


def test_space_cleanup_gate_rebuilds_stale_compatible_report(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    home_root = tmp_path / "home"
    _write_file(repo_root / "package.json", json.dumps({"scripts": {"bootstrap": "echo ok"}}))
    _write_file(repo_root / "scripts" / "install_dashboard_deps.sh", "#!/usr/bin/env bash\n")
    node_modules_file = repo_root / "apps" / "dashboard" / "node_modules" / "pkg" / "index.js"
    _write_file(node_modules_file, "console.log('x')")
    _age(node_modules_file, hours=96)

    policy_payload = _base_policy(repo_root, home_root)
    policy_path = tmp_path / "space_policy.json"
    policy_path.write_text(json.dumps(policy_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    policy = load_space_governance_policy(policy_path)

    stale_report = build_space_governance_report(repo_root=repo_root, policy=policy, ps_lines=[])
    stale_report["generated_at"] = (datetime.now(timezone.utc) - timedelta(minutes=120)).isoformat()
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(stale_report, ensure_ascii=False, indent=2), encoding="utf-8")
    output_path = tmp_path / "cleanup_gate.json"

    gate_module = _load_gate_script_module()
    monkeypatch.setattr(gate_module, "ROOT", repo_root)

    rebuild_called = {"count": 0}

    def _rebuild(*, repo_root: Path, policy: dict):
        rebuild_called["count"] += 1
        return build_space_governance_report(repo_root=repo_root, policy=policy, ps_lines=[])

    def _evaluate(*, repo_root: Path, policy: dict, report: dict, wave: str, allow_recent: bool = False, allow_shared: bool = False):
        return evaluate_cleanup_gate(
            repo_root=repo_root,
            policy=policy,
            report=report,
            wave=wave,
            allow_recent=allow_recent,
            allow_shared=allow_shared,
            ps_lines=[],
        )

    monkeypatch.setattr(gate_module, "build_space_governance_report", _rebuild)
    monkeypatch.setattr(gate_module, "evaluate_cleanup_gate", _evaluate)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "check_space_cleanup_gate.py",
            "--policy",
            str(policy_path),
            "--report-json",
            str(report_path),
            "--output-json",
            str(output_path),
            "--wave",
            "wave2",
            "--allow-recent",
        ],
    )

    rc = gate_module.main()

    assert rc == 0
    assert rebuild_called["count"] == 1
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "pass"
