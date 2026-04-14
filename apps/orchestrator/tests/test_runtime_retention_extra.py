import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import openvibecoding_orch.config as config_module
import openvibecoding_orch.runtime.space_governance as space_governance_module
from openvibecoding_orch.config import load_config
from openvibecoding_orch.runtime.retention import (
    RetentionPlan,
    _overflow_log_candidates,
    _safe_remove_path,
    apply_retention_plan,
    build_retention_plan,
    write_retention_report,
)


def _reset_config_state() -> None:
    config_module._ENV_LOADED = False
    config_module.reset_cached_config()


def _touch_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="utf-8")


def _set_age(path: Path, *, days: int = 0, hours: int = 0) -> None:
    ts = (datetime.now(timezone.utc) - timedelta(days=days, hours=hours)).timestamp()
    os.utime(path, (ts, ts))


def _write_space_policy(repo_root: Path) -> None:
    policy = {
        "version": 1,
        "recent_activity_hours": 24,
        "apply_gate_max_age_minutes": 15,
        "shared_realpath_prefixes": [],
        "process_groups": {
            "node": {"patterns": ["\\bnode\\b"]},
        },
        "rebuild_commands": [
            {"id": "bootstrap", "kind": "npm_script", "script": "bootstrap", "description": "bootstrap"},
            {"id": "dashboard_deps", "kind": "shell_script", "path": "scripts/install_dashboard_deps.sh", "description": "dashboard deps"},
            {"id": "docker_ci_test_quick", "kind": "shell_script", "path": "scripts/docker_ci.sh", "description": "docker ci quick"},
        ],
        "layers": {
            "repo_internal": [],
            "repo_external_related": [
                {
                    "id": "external_tmp_docker_ci_runner_temp",
                    "path": "${OPENVIBECODING_MACHINE_CACHE_ROOT}/tmp/docker-ci/runner-temp-*",
                    "type": "docker ci temp",
                    "ownership": "repo-owned docker ci temp",
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
                    "process_command_hints": ["scripts/docker_ci.sh", "runner-temp"],
                    "evidence": ["scripts/docker_ci.sh"],
                },
                {
                    "id": "external_pnpm_store_v10",
                    "path": "${OPENVIBECODING_MACHINE_CACHE_ROOT}/pnpm-store/v10",
                    "type": "pnpm v10",
                    "ownership": "repo-controlled pnpm store",
                    "ownership_confidence": "High",
                    "sharedness": "repo_machine_shared",
                    "summary_role": "breakdown_only",
                    "rebuildability": "rebuildable",
                    "recommendation": "needs_verification",
                    "cleanup_mode": "remove-path",
                    "retention_auto_cleanup": True,
                    "retention_ttl_hours": 336,
                    "risk": "medium",
                    "rebuild_command_ids": ["dashboard_deps"],
                    "post_cleanup_command_ids": ["dashboard_deps"],
                    "evidence": ["scripts/install_dashboard_deps.sh"],
                },
                {
                    "id": "external_pnpm_store_dashboard",
                    "path": "${OPENVIBECODING_MACHINE_CACHE_ROOT}/pnpm-store/dashboard",
                    "type": "pnpm dashboard",
                    "ownership": "repo-controlled dashboard pnpm store",
                    "ownership_confidence": "High",
                    "sharedness": "repo_machine_shared",
                    "summary_role": "breakdown_only",
                    "rebuildability": "rebuildable",
                    "recommendation": "needs_verification",
                    "cleanup_mode": "remove-path",
                    "retention_auto_cleanup": True,
                    "retention_ttl_hours": 168,
                    "risk": "medium",
                    "rebuild_command_ids": ["dashboard_deps"],
                    "post_cleanup_command_ids": ["dashboard_deps"],
                    "evidence": ["scripts/install_dashboard_deps.sh"],
                },
                {
                    "id": "external_playwright",
                    "path": "${OPENVIBECODING_MACHINE_CACHE_ROOT}/playwright",
                    "type": "playwright cache",
                    "ownership": "repo-controlled playwright cache",
                    "ownership_confidence": "High",
                    "sharedness": "repo_machine_shared",
                    "summary_role": "breakdown_only",
                    "rebuildability": "rebuildable",
                    "recommendation": "needs_verification",
                    "cleanup_mode": "remove-path",
                    "retention_auto_cleanup": True,
                    "retention_ttl_hours": 168,
                    "risk": "medium",
                    "rebuild_command_ids": ["bootstrap"],
                    "post_cleanup_command_ids": ["bootstrap"],
                    "evidence": ["scripts/bootstrap.sh"],
                },
                {
                    "id": "external_python_toolchain_current",
                    "path": "${OPENVIBECODING_MACHINE_CACHE_ROOT}/toolchains/python/current",
                    "type": "python toolchain current",
                    "ownership": "repo-related python current",
                    "ownership_confidence": "High",
                    "sharedness": "repo_machine_shared",
                    "summary_role": "breakdown_only",
                    "rebuildability": "unknown",
                    "recommendation": "observe_only",
                    "cleanup_mode": "observe-only",
                    "risk": "high",
                    "rebuild_command_ids": ["bootstrap"],
                    "evidence": ["scripts/lib/toolchain_env.sh"],
                },
            ],
            "shared_observation": [],
        },
        "wave_targets": {
            "wave1": {"target_ids": ["external_tmp_docker_ci_runner_temp"], "process_groups": ["node"]},
            "wave2": {"target_ids": ["external_pnpm_store_dashboard"], "process_groups": ["node"]},
            "wave3": {
                "target_ids": [
                    "external_tmp_docker_ci_runner_temp",
                    "external_pnpm_store_v10",
                    "external_pnpm_store_dashboard",
                    "external_playwright",
                    "external_python_toolchain_current",
                ],
                "process_groups": ["node"],
            },
        },
    }
    policy_path = repo_root / "configs" / "space_governance_policy.json"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(json.dumps(policy, ensure_ascii=False, indent=2), encoding="utf-8")


def test_retention_helpers_overflow_and_safe_remove(tmp_path: Path) -> None:
    logs_root = tmp_path / "logs"
    runtime_dir = logs_root / "runtime"
    e2e_dir = logs_root / "e2e"
    newest_runtime = runtime_dir / "new.log"
    oldest_runtime = runtime_dir / "old.log"
    newest_e2e = e2e_dir / "new.log"
    oldest_e2e = e2e_dir / "old.log"

    for path in [newest_runtime, oldest_runtime, newest_e2e, oldest_e2e]:
        _touch_file(path)

    _set_age(oldest_runtime, days=2)
    _set_age(oldest_e2e, days=2)

    assert _overflow_log_candidates(logs_root, 0) == []

    overflow = _overflow_log_candidates(logs_root, 1)
    assert sorted(str(item.relative_to(logs_root)) for item in overflow) == sorted(
        [
            "runtime/old.log",
            "e2e/old.log",
        ]
    )

    inside_root = tmp_path / "inside"
    outside_file = tmp_path / "outside" / "file.log"
    _touch_file(outside_file)
    assert _safe_remove_path(outside_file, inside_root) is False

    nested_dir = inside_root / "a" / "b"
    _touch_file(nested_dir / "leaf.txt")
    assert _safe_remove_path(inside_root / "a", inside_root) is True
    assert not (inside_root / "a").exists()

    missing = inside_root / "missing.log"
    assert _safe_remove_path(missing, inside_root) is False


def test_build_retention_plan_and_write_report_for_empty_roots(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    runtime_root = repo_root / ".runtime-cache" / "openvibecoding"
    monkeypatch.setenv("OPENVIBECODING_REPO_ROOT", str(repo_root))
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runtime_root / "runs"))
    monkeypatch.setenv("OPENVIBECODING_WORKTREE_ROOT", str(runtime_root / "worktrees"))
    monkeypatch.setenv("OPENVIBECODING_LOGS_ROOT", str(runtime_root / "logs"))
    monkeypatch.setenv("OPENVIBECODING_CACHE_ROOT", str(runtime_root / "cache"))
    monkeypatch.setenv("OPENVIBECODING_MACHINE_CACHE_ROOT", str(tmp_path / "machine-cache"))

    cfg = load_config()
    plan = build_retention_plan(cfg)
    assert plan == RetentionPlan([], [], [], [], [], [], [])

    report_path = write_retention_report(cfg, plan, applied=False, apply_result=None)
    payload = report_path.read_text(encoding="utf-8")
    assert '"applied": false' in payload.lower()
    assert '"total": 0' in payload
    assert '"removed_total": 0' in payload
    assert '"protected_live_roots"' in payload


def test_retention_report_space_bridge_reads_latest_space_audit(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    runtime_root = repo_root / ".runtime-cache" / "openvibecoding"
    monkeypatch.setenv("OPENVIBECODING_REPO_ROOT", str(repo_root))
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runtime_root / "runs"))
    monkeypatch.setenv("OPENVIBECODING_WORKTREE_ROOT", str(runtime_root / "worktrees"))
    monkeypatch.setenv("OPENVIBECODING_LOGS_ROOT", str(runtime_root / "logs"))
    monkeypatch.setenv("OPENVIBECODING_CACHE_ROOT", str(runtime_root / "cache"))
    monkeypatch.setenv("OPENVIBECODING_MACHINE_CACHE_ROOT", str(tmp_path / "machine-cache"))

    space_report = runtime_root / "reports" / "space_governance" / "report.json"
    space_report.parent.mkdir(parents=True, exist_ok=True)
    space_report.write_text(
        json.dumps(
            {
                "generated_at": "2026-03-28T12:00:00+00:00",
                "summary": {
                    "repo_internal_total_bytes": 123,
                    "repo_external_related_total_bytes": 456,
                    "shared_observation_total_bytes": 789,
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    cfg = load_config()
    plan = build_retention_plan(cfg)
    report_path = write_retention_report(cfg, plan, applied=False, apply_result=None)
    payload = json.loads(report_path.read_text(encoding="utf-8"))

    assert payload["space_bridge"]["exists"] is True
    assert payload["space_bridge"]["latest_space_audit_generated_at"] == "2026-03-28T12:00:00+00:00"
    assert payload["space_bridge"]["repo_internal_total_bytes"] == 123


def test_machine_cache_retention_honors_policy_ttl_and_cap(tmp_path: Path, monkeypatch) -> None:
    _reset_config_state()
    repo_root = tmp_path / "repo"
    runtime_root = repo_root / ".runtime-cache" / "openvibecoding"
    machine_cache_root = tmp_path / "machine-cache"

    monkeypatch.setenv("OPENVIBECODING_REPO_ROOT", str(repo_root))
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runtime_root / "runs"))
    monkeypatch.setenv("OPENVIBECODING_WORKTREE_ROOT", str(runtime_root / "worktrees"))
    monkeypatch.setenv("OPENVIBECODING_LOGS_ROOT", str(repo_root / ".runtime-cache" / "logs"))
    monkeypatch.setenv("OPENVIBECODING_CACHE_ROOT", str(repo_root / ".runtime-cache" / "cache"))
    monkeypatch.setenv("OPENVIBECODING_MACHINE_CACHE_ROOT", str(machine_cache_root))
    monkeypatch.setenv("OPENVIBECODING_RETENTION_MACHINE_CACHE_CAP_BYTES", "200")

    _write_space_policy(repo_root)

    docker_temp = machine_cache_root / "tmp" / "docker-ci" / "runner-temp-1000"
    pnpm_v10 = machine_cache_root / "pnpm-store" / "v10"
    pnpm_dashboard = machine_cache_root / "pnpm-store" / "dashboard"
    playwright_root = machine_cache_root / "playwright"
    toolchain_current = machine_cache_root / "toolchains" / "python" / "current"

    _touch_file(docker_temp / "marker.txt")
    _touch_file(pnpm_v10 / "pkg" / "artifact.tgz")
    _touch_file(pnpm_dashboard / "pkg" / "artifact.tgz")
    _touch_file(playwright_root / "chromium" / "chrome.zip")
    _touch_file(toolchain_current / "bin" / "python")

    (docker_temp / "marker.txt").write_text("d" * 40, encoding="utf-8")
    (pnpm_v10 / "pkg" / "artifact.tgz").write_text("v" * 50, encoding="utf-8")
    (pnpm_dashboard / "pkg" / "artifact.tgz").write_text("p" * 60, encoding="utf-8")
    (playwright_root / "chromium" / "chrome.zip").write_text("w" * 20, encoding="utf-8")
    (toolchain_current / "bin" / "python").write_text("t" * 180, encoding="utf-8")

    _set_age(docker_temp, hours=30)
    _set_age(pnpm_v10, days=15)
    _set_age(pnpm_dashboard, days=2)
    _set_age(playwright_root, hours=12)

    cfg = load_config()
    plan = build_retention_plan(cfg)

    machine_cache_candidates = {str(item.path): item for item in plan.machine_cache_candidates}
    assert str(docker_temp) in machine_cache_candidates
    assert machine_cache_candidates[str(docker_temp)].selection_reason == "ttl_expired"
    assert str(pnpm_v10) in machine_cache_candidates
    assert machine_cache_candidates[str(pnpm_v10)].selection_reason == "ttl_expired"
    assert str(pnpm_dashboard) in machine_cache_candidates
    assert machine_cache_candidates[str(pnpm_dashboard)].selection_reason == "cap_pressure"
    assert str(playwright_root) not in machine_cache_candidates
    assert str(toolchain_current) not in machine_cache_candidates

    report_path = write_retention_report(cfg, plan, applied=False, apply_result=None)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["machine_cache_summary"]["cap_bytes"] == 200
    assert payload["machine_cache_summary"]["candidate_reason_counts"] == {
        "cap_pressure": 1,
        "ttl_expired": 2,
    }
    assert payload["machine_cache_auto_prune"] is None
    assert payload["cleanup_scope"]["protected_live_roots"]["machine_cache_python_current"] == str(toolchain_current)
    apply_result = apply_retention_plan(cfg, plan)
    assert set(apply_result["removed"]["machine_cache"]) == {
        str(docker_temp),
        str(pnpm_v10),
        str(pnpm_dashboard),
    }
    assert docker_temp.exists() is False
    assert pnpm_v10.exists() is False
    assert pnpm_dashboard.exists() is False
    assert playwright_root.exists() is True
    assert toolchain_current.exists() is True


def test_machine_cache_retention_skips_entries_with_active_repo_scoped_processes(
    tmp_path: Path, monkeypatch
) -> None:
    _reset_config_state()
    repo_root = tmp_path / "repo"
    runtime_root = repo_root / ".runtime-cache" / "openvibecoding"
    machine_cache_root = tmp_path / "machine-cache"

    monkeypatch.setenv("OPENVIBECODING_REPO_ROOT", str(repo_root))
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runtime_root / "runs"))
    monkeypatch.setenv("OPENVIBECODING_WORKTREE_ROOT", str(runtime_root / "worktrees"))
    monkeypatch.setenv("OPENVIBECODING_LOGS_ROOT", str(repo_root / ".runtime-cache" / "logs"))
    monkeypatch.setenv("OPENVIBECODING_CACHE_ROOT", str(repo_root / ".runtime-cache" / "cache"))
    monkeypatch.setenv("OPENVIBECODING_MACHINE_CACHE_ROOT", str(machine_cache_root))
    monkeypatch.setenv("OPENVIBECODING_RETENTION_MACHINE_CACHE_CAP_BYTES", "1024")

    _write_space_policy(repo_root)
    docker_temp = machine_cache_root / "tmp" / "docker-ci" / "runner-temp-1000"
    _touch_file(docker_temp / "marker.txt")
    (docker_temp / "marker.txt").write_text("d" * 40, encoding="utf-8")
    _set_age(docker_temp, hours=30)

    original_collect = space_governance_module.collect_process_matches

    def _fake_collect_process_matches(*, entries=None, **kwargs):
        if entries and str(entries[0].get("policy_entry_id", "")) == "external_tmp_docker_ci_runner_temp":
            return {
                "node": [
                    {
                        "pid": 123,
                        "command": "node scripts/docker_ci.sh lane ci-core-tests",
                        "scope": "repo_scoped",
                        "relevance_reasons": ["repo_command_hint"],
                    }
                ]
            }
        return original_collect(entries=entries, **kwargs)

    monkeypatch.setattr(space_governance_module, "collect_process_matches", _fake_collect_process_matches)

    cfg = load_config()
    plan = build_retention_plan(cfg)
    assert not plan.machine_cache_candidates

    report_path = write_retention_report(cfg, plan, applied=False, apply_result=None)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["machine_cache_summary"]["process_blocked_count"] == 1
    assert payload["machine_cache_summary"]["entries"][0]["cleanup_candidate"] is False
    assert payload["machine_cache_summary"]["entries"][0]["process_blocked"] is True


def test_machine_cache_auto_prune_summary_is_embedded_in_retention_report(tmp_path: Path, monkeypatch) -> None:
    _reset_config_state()
    repo_root = tmp_path / "repo"
    runtime_root = repo_root / ".runtime-cache" / "openvibecoding"
    machine_cache_root = tmp_path / "machine-cache"

    monkeypatch.setenv("OPENVIBECODING_REPO_ROOT", str(repo_root))
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runtime_root / "runs"))
    monkeypatch.setenv("OPENVIBECODING_WORKTREE_ROOT", str(runtime_root / "worktrees"))
    monkeypatch.setenv("OPENVIBECODING_LOGS_ROOT", str(repo_root / ".runtime-cache" / "logs"))
    monkeypatch.setenv("OPENVIBECODING_CACHE_ROOT", str(repo_root / ".runtime-cache" / "cache"))
    monkeypatch.setenv("OPENVIBECODING_MACHINE_CACHE_ROOT", str(machine_cache_root))

    _write_space_policy(repo_root)
    state_path = machine_cache_root / "retention-auto-prune" / "state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "generated_at": "2026-04-04T12:00:00+00:00",
                "last_attempt_epoch": 123,
                "reason": "bootstrap:full",
                "status": "pass",
                "note": "cleanup_runtime apply completed",
                "interval_sec": 1800,
            }
        ),
        encoding="utf-8",
    )

    cfg = load_config()
    plan = build_retention_plan(cfg)
    report_path = write_retention_report(cfg, plan, applied=False, apply_result=None)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["machine_cache_auto_prune"]["status"] == "pass"
    assert payload["machine_cache_auto_prune"]["reason"] == "bootstrap:full"


def test_config_fails_when_explicit_env_file_missing(monkeypatch) -> None:
    config_module._ENV_LOADED = False
    monkeypatch.setenv("OPENVIBECODING_ENV_FILE", "/tmp/openvibecoding-env-file-should-not-exist.env")
    with pytest.raises(RuntimeError, match="OPENVIBECODING_ENV_FILE not found"):
        load_config()


def test_config_ignores_legacy_base_url_alias_and_keeps_canonical(monkeypatch) -> None:
    config_module._ENV_LOADED = False
    monkeypatch.delenv("OPENVIBECODING_ENV_FILE", raising=False)
    monkeypatch.setenv("OPENVIBECODING_PROVIDER_BASE_URL", "https://api.primary.local/v1")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.shadow.local/v1")
    cfg = load_config()
    assert cfg.runner.agents_base_url == "https://api.primary.local/v1"
