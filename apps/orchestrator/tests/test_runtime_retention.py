import os
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cortexpilot_orch.config as config_module
from cortexpilot_orch.config import load_config
from cortexpilot_orch.runtime.retention import apply_retention_plan, build_retention_plan, write_retention_report


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix:
        path.write_text("x", encoding="utf-8")
    else:
        path.mkdir(parents=True, exist_ok=True)


def _age(path: Path, *, days: int = 0, hours: int = 0) -> None:
    ts = (datetime.now(timezone.utc) - timedelta(days=days, hours=hours)).timestamp()
    os.utime(path, (ts, ts))


def test_retention_dry_plan_and_apply(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    runtime_root = repo_root / ".runtime-cache" / "cortexpilot"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"
    logs_root = repo_root / ".runtime-cache" / "logs"
    cache_root = repo_root / ".runtime-cache" / "cache"

    monkeypatch.setenv("CORTEXPILOT_REPO_ROOT", str(repo_root))
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("CORTEXPILOT_WORKTREE_ROOT", str(worktree_root))
    monkeypatch.setenv("CORTEXPILOT_LOGS_ROOT", str(logs_root))
    monkeypatch.setenv("CORTEXPILOT_CACHE_ROOT", str(cache_root))
    monkeypatch.setenv("CORTEXPILOT_MACHINE_CACHE_ROOT", str(tmp_path / "machine-cache"))
    monkeypatch.setenv("CORTEXPILOT_RETENTION_RUN_DAYS", "1")
    monkeypatch.setenv("CORTEXPILOT_RETENTION_MAX_RUNS", "1")
    monkeypatch.setenv("CORTEXPILOT_RETENTION_LOG_DAYS", "1")
    monkeypatch.setenv("CORTEXPILOT_RETENTION_WORKTREE_DAYS", "1")
    monkeypatch.setenv("CORTEXPILOT_RETENTION_LOG_MAX_FILES", "1")
    monkeypatch.setenv("CORTEXPILOT_RETENTION_CACHE_HOURS", "1")

    run_old = runs_root / "run_old"
    run_new = runs_root / "run_new"
    _touch(run_old)
    _touch(run_new)

    worktree_old = worktree_root / "run_old"
    _touch(worktree_old)

    log_old = logs_root / "runtime" / "old.log"
    log_new = logs_root / "runtime" / "new.log"
    _touch(log_old)
    _touch(log_new)

    cache_old = cache_root / "runtime" / "stale.bin"
    cache_non_contract_old = cache_root / "stale-runs" / "stale.bin"
    _touch(cache_old)
    _touch(cache_non_contract_old)

    _age(run_old, days=2)
    _age(worktree_old, days=2)
    _age(log_old, days=2)
    _age(cache_old, hours=2)
    _age(cache_non_contract_old, hours=2)

    cfg = load_config()
    plan = build_retention_plan(cfg)
    assert plan.total_candidates >= 1
    report_path = write_retention_report(cfg, plan, applied=False, apply_result=None)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["cleanup_scope"]["included_roots"]["cache"] == str(cache_root)
    assert payload["cleanup_scope"]["protected_live_roots"]["active_contract"] == str(runtime_root / "active")
    assert payload["cache_namespace_summary"]["candidate_bucket_counts"]["runtime"] >= 1
    assert payload["cache_namespace_summary"]["candidate_bucket_counts"]["stale-runs"] >= 1
    assert "stale-runs" in payload["cache_namespace_summary"]["non_contract_buckets"]
    assert set(payload["log_lane_summary"]) == {"runtime", "error", "access", "e2e", "ci", "governance"}
    assert payload["log_lane_summary"]["runtime"]["file_count"] >= 1
    assert payload["space_bridge"]["exists"] is False

    result = apply_retention_plan(cfg, plan)
    assert result["removed_total"] >= 1
    assert (
        not run_old.exists()
        or not worktree_old.exists()
        or not log_old.exists()
        or not cache_old.exists()
        or not cache_non_contract_old.exists()
    )
    assert "cache" in result["removed"]


def test_machine_cache_summary_excludes_repo_browser_root_from_cap_pressure(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    runtime_root = repo_root / ".runtime-cache" / "cortexpilot"
    machine_root = tmp_path / "machine-cache"
    browser_profile = machine_root / "browser" / "chrome-user-data" / "Profile 1"
    playwright_root = machine_root / "playwright"

    monkeypatch.setenv("CORTEXPILOT_REPO_ROOT", str(repo_root))
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_MACHINE_CACHE_ROOT", str(machine_root))
    monkeypatch.setenv("CORTEXPILOT_RETENTION_MACHINE_CACHE_CAP_BYTES", "50")
    config_module._ENV_LOADED = False
    config_module._CONFIG_CACHE = None

    (repo_root / "scripts").mkdir(parents=True, exist_ok=True)
    (repo_root / "scripts" / "bootstrap.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    (repo_root / "package.json").write_text(json.dumps({"scripts": {"bootstrap": "echo ok"}}), encoding="utf-8")
    (repo_root / "configs").mkdir(parents=True, exist_ok=True)
    (repo_root / "configs" / "space_governance_policy.json").write_text(
        json.dumps(
            {
                "version": 1,
                "recent_activity_hours": 24,
                "apply_gate_max_age_minutes": 15,
                    "machine_cache_retention_policy": {
                        "default_cap_bytes": 50,
                        "auto_prune_interval_sec": 1800,
                        "protected_prefixes": [
                            "${CORTEXPILOT_MACHINE_CACHE_ROOT}/browser",
                        ],
                        "cap_excluded_prefixes": [
                            "${CORTEXPILOT_MACHINE_CACHE_ROOT}/browser",
                    ],
                },
                "shared_realpath_prefixes": [],
                "process_groups": {"python": {"patterns": ["\\bpython\\b"]}},
                "rebuild_commands": [
                    {
                        "id": "bootstrap_playwright",
                        "kind": "shell_script",
                        "path": "scripts/bootstrap.sh",
                        "args": ["playwright"],
                        "description": "Playwright bootstrap",
                    }
                ],
                "layers": {
                    "repo_internal": [],
                    "shared_observation": [],
                    "repo_external_related": [
                        {
                            "id": "external_playwright",
                            "path": "${CORTEXPILOT_MACHINE_CACHE_ROOT}/playwright",
                            "type": "machine-scoped Playwright browser cache",
                            "ownership": "repo-controlled external browser download root",
                            "ownership_confidence": "High",
                            "sharedness": "repo_machine_shared",
                            "summary_role": "breakdown_only",
                            "rebuildability": "rebuildable by Playwright install",
                            "recommendation": "needs_verification",
                            "cleanup_mode": "remove-path",
                            "retention_auto_cleanup": True,
                            "retention_ttl_hours": 168,
                            "risk": "low_medium",
                            "rebuild_command_ids": ["bootstrap_playwright"],
                            "post_cleanup_command_ids": ["bootstrap_playwright"],
                            "apply_serial_only": True,
                            "evidence": ["scripts/bootstrap.sh"],
                            "notes": "Repo-owned browser cache.",
                        }
                    ],
                },
                "wave_targets": {
                    "wave1": {
                        "target_ids": ["external_playwright"],
                        "process_groups": ["python"],
                        "required_rebuild_commands": ["bootstrap_playwright"],
                    }
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    browser_profile.mkdir(parents=True, exist_ok=True)
    (browser_profile / "Cookies").write_text("x" * 200, encoding="utf-8")
    playwright_root.mkdir(parents=True, exist_ok=True)
    (playwright_root / "marker.txt").write_text("y" * 80, encoding="utf-8")
    _age(playwright_root / "marker.txt", hours=200)

    cfg = load_config()
    plan = build_retention_plan(cfg)
    report_path = write_retention_report(cfg, plan, applied=False, apply_result=None)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    machine_cache_summary = payload["machine_cache_summary"]

    assert machine_cache_summary["total_size_bytes"] >= 230
    assert machine_cache_summary["cap_tracked_total_bytes"] == 80
    assert machine_cache_summary["cap_excluded_total_bytes"] >= 200
    assert machine_cache_summary["over_cap_bytes"] == 30
    assert machine_cache_summary["candidate_count"] == 1
    assert machine_cache_summary["candidates"][0]["policy_entry_id"] == "external_playwright"
    assert machine_cache_summary["entries"][0]["protected"] is False
    assert machine_cache_summary["entries"][0]["cap_excluded"] is False
