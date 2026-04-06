import hashlib
import json
import subprocess
from pathlib import Path

from cortexpilot_orch.scheduler import scheduler as sched
from cortexpilot_orch.scheduler.scheduler import Orchestrator
from cortexpilot_orch.store.run_store import RunStore


def _git(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(["git", "init"], repo)
    _git(["git", "config", "user.email", "test@example.com"], repo)
    _git(["git", "config", "user.name", "tester"], repo)
    (repo / "README.md").write_text("hello", encoding="utf-8")
    _git(["git", "add", "README.md"], repo)
    _git(["git", "commit", "-m", "init"], repo)


def _contract(task_id: str) -> dict:
    schema_root = Path(__file__).resolve().parents[3] / "schemas"
    schema_name = "agent_task_result.v1.json"
    schema_path = schema_root / schema_name
    sha = hashlib.sha256(schema_path.read_bytes()).hexdigest()
    return {
        "task_id": task_id,
        "owner_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "assigned_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "inputs": {
            "spec": "spec",
            "artifacts": [
                {
                    "name": "output_schema.worker",
                    "uri": f"schemas/{schema_name}",
                    "sha256": sha,
                }
            ],
        },
        "required_outputs": [{"name": "README.md", "type": "file", "acceptance": "ok"}],
        "allowed_paths": ["README.md"],
        "forbidden_actions": [],
        "acceptance_tests": [{"name": "noop", "cmd": "echo ok", "must_pass": True}],
        "tool_permissions": {
            "filesystem": "workspace-write",
            "shell": "on-request",
            "network": "deny",
            "mcp_tools": ["codex"],
        },
        "mcp_tool_set": ["01-filesystem"],
        "timeout_retry": {"timeout_sec": 1, "max_retries": 0, "retry_backoff_sec": 0},
        "rollback": {"strategy": "git_reset_hard", "baseline_ref": "HEAD"},
        "evidence_links": [],
        "log_refs": {"run_id": "", "paths": {}},
    }


def _write_contract(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_scheduler_wrapper_functions_delegate(monkeypatch, tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path / "runs")

    monkeypatch.setattr(sched.policy_pipeline, "apply_role_defaults", lambda **kwargs: ({"ok": True}, ["x"]))
    monkeypatch.setattr(sched.approval_flow, "requires_human_approval", lambda **kwargs: True)
    monkeypatch.setattr(sched.approval_flow, "await_human_approval", lambda **kwargs: False)
    monkeypatch.setattr(sched.artifact_pipeline, "safe_artifact_path", lambda uri, repo_root: repo_root / uri)
    monkeypatch.setattr(sched.artifact_pipeline, "load_json_artifact", lambda artifact, repo_root: ({"x": 1}, None, repo_root / "a.json"))
    monkeypatch.setattr(sched.artifact_pipeline, "load_search_requests", lambda contract, repo_root, schema_root: ({"queries": ["q"]}, None))
    monkeypatch.setattr(sched.artifact_pipeline, "load_browser_tasks", lambda contract, repo_root, schema_root: ({"tasks": []}, None))
    monkeypatch.setattr(sched.artifact_pipeline, "load_tampermonkey_tasks", lambda contract, repo_root, schema_root: ({"tasks": []}, None))
    monkeypatch.setattr(sched.tool_execution_pipeline, "run_sampling_requests", lambda **kwargs: {"ok": True, "kind": "sampling"})
    monkeypatch.setattr(sched.rollback_pipeline, "scoped_revert", lambda worktree, paths: {"ok": True, "paths": paths})

    assert sched._apply_role_defaults({}, {}) == ({"ok": True}, ["x"])
    assert sched._requires_human_approval({}, requires_network=True) is True
    assert sched._await_human_approval("run-x", store) is False
    assert sched._safe_artifact_path("a/b.txt", tmp_path) == tmp_path / "a/b.txt"
    assert sched._load_json_artifact({}, tmp_path)[0] == {"x": 1}
    assert sched._load_search_requests({}, tmp_path)[0] == {"queries": ["q"]}
    assert sched._load_browser_tasks({}, tmp_path)[0] == {"tasks": []}
    assert sched._load_tampermonkey_tasks({}, tmp_path)[0] == {"tasks": []}
    assert sched._run_sampling_requests("run-x", object(), store, {})["kind"] == "sampling"
    assert sched._scoped_revert(tmp_path, ["README.md"]) == {"ok": True, "paths": ["README.md"]}


def test_scheduler_mcp_only_block_branch(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"
    monkeypatch.chdir(repo)
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("CORTEXPILOT_WORKTREE_ROOT", str(worktree_root))

    monkeypatch.setenv("CORTEXPILOT_MCP_ONLY", "1")
    monkeypatch.setenv("CORTEXPILOT_RUNNER", "codex")
    monkeypatch.setenv("CORTEXPILOT_ALLOW_CODEX_EXEC", "0")

    monkeypatch.setattr(sched, "ensure_tracing", lambda: {"enabled": True, "backend": "off"})
    monkeypatch.setattr(sched, "check_schema_registry", lambda *_args, **_kwargs: {"status": "ok"})

    contract_path = repo / "contract.json"
    _write_contract(contract_path, _contract("task_mcp_only_block"))

    orch = Orchestrator(repo)
    run_id = orch.execute_task(contract_path, mock_mode=False)

    manifest = json.loads((runs_root / run_id / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "FAILURE"
    assert "mcp-only enforced" in manifest["failure_reason"]


def test_scheduler_temporal_notify_required_failure_and_diagnostic_root(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo_diag"
    _init_repo(repo)

    runtime_root = tmp_path / "runtime_diag"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"
    diagnostic_root = runtime_root / "runs_diagnostic"
    monkeypatch.chdir(repo)
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("CORTEXPILOT_WORKTREE_ROOT", str(worktree_root))
    monkeypatch.setenv("CORTEXPILOT_DIAGNOSTIC_RUNS_ROOT", str(diagnostic_root))

    monkeypatch.setenv("CORTEXPILOT_RUNNER", "codex")
    monkeypatch.setenv("CORTEXPILOT_ALLOW_CODEX_EXEC", "1")
    monkeypatch.setenv("CORTEXPILOT_MCP_ONLY", "0")

    monkeypatch.setattr(sched, "ensure_tracing", lambda: {"enabled": True, "backend": "off"})
    monkeypatch.setattr(sched, "check_schema_registry", lambda *_args, **_kwargs: {"status": "ok"})
    monkeypatch.setattr(sched, "notify_run_started", lambda *_args, **_kwargs: {"ok": False, "error": "forced"})
    monkeypatch.setattr(sched, "temporal_required", lambda: True)

    contract_path = repo / "contract_diag.json"
    _write_contract(contract_path, _contract("task_temporal_notify_fail"))

    orch = Orchestrator(repo)
    run_id = orch.execute_task(contract_path, mock_mode=True)

    manifest_path = diagnostic_root / run_id / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "FAILURE"
    assert manifest["failure_reason"] == "temporal notify failed"


def test_scheduler_chain_child_skips_diagnostic_root(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo_chain_child"
    _init_repo(repo)

    runtime_root = tmp_path / "runtime_chain_child"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"
    diagnostic_root = runtime_root / "runs_diagnostic"
    monkeypatch.chdir(repo)
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("CORTEXPILOT_WORKTREE_ROOT", str(worktree_root))
    monkeypatch.setenv("CORTEXPILOT_DIAGNOSTIC_RUNS_ROOT", str(diagnostic_root))

    monkeypatch.setenv("CORTEXPILOT_RUNNER", "codex")
    monkeypatch.setenv("CORTEXPILOT_ALLOW_CODEX_EXEC", "1")
    monkeypatch.setenv("CORTEXPILOT_MCP_ONLY", "0")

    monkeypatch.setattr(sched, "ensure_tracing", lambda: {"enabled": True})
    monkeypatch.setattr(sched, "check_schema_registry", lambda *_args, **_kwargs: {"status": "ok"})
    monkeypatch.setattr(sched, "validate_command", lambda *_args, **_kwargs: {"ok": True})

    payload = _contract("task_chain_child")
    payload["parent_task_id"] = "task_parent_chain"
    contract_path = repo / "contract_chain_child.json"
    _write_contract(contract_path, payload)

    orch = Orchestrator(repo)
    run_id = orch.execute_task(contract_path, mock_mode=True)

    manifest_path = runs_root / run_id / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] in {"SUCCESS", "FAILURE"}
    if manifest["status"] == "FAILURE":
        assert manifest.get("failure_reason")
    assert not (diagnostic_root / run_id / "manifest.json").exists()


def _init_repo_with_policy(repo: Path) -> None:
    _init_repo(repo)
    policies = repo / "policies"
    policies.mkdir(parents=True, exist_ok=True)
    codex_home = repo / "codex_home"
    codex_home.mkdir(parents=True, exist_ok=True)
    tools_dir = repo / "tooling"
    tools_dir.mkdir(parents=True, exist_ok=True)

    (tools_dir / "registry.json").write_text(
        json.dumps({"installed": ["codex", "search", "sampling"], "integrated": ["codex", "search", "sampling"]}),
        encoding="utf-8",
    )
    (policies / "command_allowlist.json").write_text(
        json.dumps(
            {
                "version": "v1",
                "allow": [
                    {"exec": "codex", "argv_prefixes": [["codex", "exec"]]},
                    {"exec": "git", "argv_prefixes": [["git"]]},
                    {"exec": "echo", "argv_prefixes": [["echo"]]},
                ],
                "deny_substrings": ["rm -rf", "sudo", "ssh ", "scp ", "sftp ", "curl ", "wget "],
            }
        ),
        encoding="utf-8",
    )
    (policies / "agent_registry.json").write_text(
        json.dumps(
            {
                "version": "v1",
                "agents": [
                    {
                        "agent_id": "agent-1",
                        "role": "WORKER",
                        "codex_home": "codex_home",
                        "defaults": {
                            "sandbox": "workspace-write",
                            "approval_policy": "on-request",
                            "network": "deny",
                        },
                    },
                    {
                        "agent_id": "agent-1",
                        "role": "PM",
                        "codex_home": "codex_home",
                        "defaults": {
                            "sandbox": "workspace-write",
                            "approval_policy": "on-request",
                            "network": "deny",
                        },
                    },
                    {
                        "agent_id": "agent-1",
                        "role": "SEARCHER",
                        "codex_home": "codex_home",
                        "defaults": {
                            "sandbox": "workspace-write",
                            "approval_policy": "on-request",
                            "network": "allow",
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )


def _prepare_runtime_env(monkeypatch, repo: Path, tmp_path: Path, suffix: str) -> tuple[Path, Path, Path]:
    runtime_root = tmp_path / f"runtime_{suffix}"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"
    monkeypatch.chdir(repo)
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("CORTEXPILOT_WORKTREE_ROOT", str(worktree_root))
    monkeypatch.setenv("CORTEXPILOT_RUNNER", "agents")
    return runtime_root, runs_root, worktree_root


def _read_manifest(runs_root: Path, run_id: str) -> dict:
    return json.loads((runs_root / run_id / "manifest.json").read_text(encoding="utf-8"))


def _read_events(runs_root: Path, run_id: str) -> list[dict]:
    events_path = runs_root / run_id / "events.jsonl"
    if not events_path.exists():
        return []
    rows: list[dict] = []
    for line in events_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def test_scheduler_integrated_gate_sampling_branch(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo_integrated_gate"
    _init_repo_with_policy(repo)
    _, runs_root, _ = _prepare_runtime_env(monkeypatch, repo, tmp_path, "integrated")

    monkeypatch.setattr(sched, "ensure_tracing", lambda: {"enabled": True, "backend": "off"})
    monkeypatch.setattr(sched, "check_schema_registry", lambda *_args, **_kwargs: {"status": "ok"})
    monkeypatch.setattr(
        sched.artifact_pipeline,
        "load_sampling_requests",
        lambda *_args, **_kwargs: ({"inputs": [{"x": 1}]}, None),
    )
    monkeypatch.setattr(
        sched,
        "validate_integrated_tools",
        lambda *_args, **_kwargs: {"ok": False, "missing": ["sampling"], "registry": "forced"},
    )

    contract_path = repo / "contract_integrated.json"
    _write_contract(contract_path, _contract("task_integrated_gate"))

    orch = Orchestrator(repo)
    run_id = orch.execute_task(contract_path, mock_mode=True)

    manifest = _read_manifest(runs_root, run_id)
    assert manifest["status"] == "FAILURE"
    assert manifest["failure_reason"] == "tool not integrated"

    events = _read_events(runs_root, run_id)
    gate_event = next((item for item in events if item.get("event") == "INTEGRATED_GATE_RESULT"), None)
    assert gate_event is not None
    assert gate_event.get("level") == "ERROR"


def test_scheduler_human_approval_force_unlock_denied(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo_force_unlock"
    _init_repo_with_policy(repo)
    _, runs_root, _ = _prepare_runtime_env(monkeypatch, repo, tmp_path, "force_unlock")

    monkeypatch.setenv("CORTEXPILOT_FORCE_UNLOCK", "1")
    monkeypatch.setenv("CORTEXPILOT_GOD_MODE_TIMEOUT_SEC", "2")
    monkeypatch.setattr(sched, "_await_human_approval", lambda *args, **kwargs: False)

    contract_path = repo / "contract_force_unlock.json"
    _write_contract(contract_path, _contract("task_force_unlock"))

    orch = Orchestrator(repo)
    run_id = orch.execute_task(contract_path, mock_mode=True)

    manifest = _read_manifest(runs_root, run_id)
    assert manifest["status"] == "FAILURE"
    assert manifest["failure_reason"] == "force unlock requires approval"


def test_scheduler_human_approval_override_paths_denied(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo_override_paths"
    _init_repo_with_policy(repo)
    _, runs_root, _ = _prepare_runtime_env(monkeypatch, repo, tmp_path, "override")

    monkeypatch.setenv("CORTEXPILOT_GOD_MODE_TIMEOUT_SEC", "2")
    monkeypatch.setattr(sched, "_await_human_approval", lambda *args, **kwargs: False)
    monkeypatch.setattr(sched, "_detect_agents_overrides", lambda *_args, **_kwargs: ["apps/orchestrator/src"])

    contract_path = repo / "contract_override_paths.json"
    _write_contract(contract_path, _contract("task_override_paths"))

    orch = Orchestrator(repo)
    run_id = orch.execute_task(contract_path, mock_mode=True)

    manifest = _read_manifest(runs_root, run_id)
    assert manifest["status"] == "FAILURE"
    assert manifest["failure_reason"] == "agents override requires approval"


def test_scheduler_human_approval_danger_fs_denied(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo_danger_fs"
    _init_repo_with_policy(repo)
    _, runs_root, _ = _prepare_runtime_env(monkeypatch, repo, tmp_path, "danger_fs")

    monkeypatch.setenv("CORTEXPILOT_GOD_MODE_TIMEOUT_SEC", "2")
    monkeypatch.setattr(sched, "_await_human_approval", lambda *args, **kwargs: False)
    monkeypatch.setattr(sched.policy_pipeline, "filesystem_policy", lambda _contract: "danger-full-access")

    contract_path = repo / "contract_danger_fs.json"
    _write_contract(contract_path, _contract("task_danger_fs"))

    orch = Orchestrator(repo)
    run_id = orch.execute_task(contract_path, mock_mode=True)

    manifest = _read_manifest(runs_root, run_id)
    assert manifest["status"] == "FAILURE"
    assert manifest["failure_reason"] == "danger-full-access requires approval"


def test_scheduler_human_approval_wide_paths_denied(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo_wide_paths"
    _init_repo_with_policy(repo)
    _, runs_root, _ = _prepare_runtime_env(monkeypatch, repo, tmp_path, "wide_paths")

    monkeypatch.setenv("CORTEXPILOT_GOD_MODE_TIMEOUT_SEC", "2")
    monkeypatch.setattr(sched, "_await_human_approval", lambda *args, **kwargs: False)
    monkeypatch.setattr(sched, "find_wide_paths", lambda _paths: ["**/*"])

    contract_path = repo / "contract_wide_paths.json"
    _write_contract(contract_path, _contract("task_wide_paths"))

    orch = Orchestrator(repo)
    run_id = orch.execute_task(contract_path, mock_mode=True)

    manifest = _read_manifest(runs_root, run_id)
    assert manifest["status"] == "FAILURE"
    assert manifest["failure_reason"] == "wide paths require human approval"


def test_scheduler_dependency_patch_apply_failed_branch(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo_patch_fail"
    _init_repo_with_policy(repo)
    _, runs_root, _ = _prepare_runtime_env(monkeypatch, repo, tmp_path, "patch_fail")

    monkeypatch.setattr(sched, "_collect_patch_artifacts", lambda *_args, **_kwargs: [tmp_path / "dep.patch"])
    monkeypatch.setattr(sched, "_should_apply_dependency_patches", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(sched, "_apply_dependency_patches", lambda *_args, **_kwargs: False)

    contract_path = repo / "contract_patch_fail.json"
    _write_contract(contract_path, _contract("task_patch_fail"))

    orch = Orchestrator(repo)
    run_id = orch.execute_task(contract_path, mock_mode=True)

    manifest = _read_manifest(runs_root, run_id)
    assert manifest["status"] == "FAILURE"
    assert manifest["failure_reason"] == "dependency patch apply failed"


def test_scheduler_lock_auto_cleanup_released_event(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo_lock_cleanup"
    _init_repo_with_policy(repo)
    _, runs_root, _ = _prepare_runtime_env(monkeypatch, repo, tmp_path, "lock_cleanup")

    monkeypatch.setenv("CORTEXPILOT_LOCK_AUTO_CLEANUP", "1")
    monkeypatch.setenv("CORTEXPILOT_LOCK_TTL_SEC", "30")
    monkeypatch.setattr(sched, "acquire_lock_with_cleanup", lambda *_args, **_kwargs: (True, ["README.md"], []))
    monkeypatch.setattr(sched, "validate_integrated_tools", lambda *_args, **_kwargs: {"ok": False, "missing": ["codex"]})

    contract_path = repo / "contract_lock_cleanup.json"
    _write_contract(contract_path, _contract("task_lock_cleanup"))

    orch = Orchestrator(repo)
    run_id = orch.execute_task(contract_path, mock_mode=True)

    events = _read_events(runs_root, run_id)
    assert any(item.get("event") == "LOCK_AUTO_CLEANUP_RELEASED" for item in events)


def test_scheduler_search_pipeline_failed_branch(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo_search_fail"
    _init_repo_with_policy(repo)
    _, runs_root, _ = _prepare_runtime_env(monkeypatch, repo, tmp_path, "search_fail")

    payload = _contract("task_search_pipeline_fail")
    payload["owner_agent"]["role"] = "SEARCHER"
    payload["assigned_agent"]["role"] = "SEARCHER"
    payload["tool_permissions"]["network"] = "allow"

    monkeypatch.setattr(
        sched.artifact_pipeline,
        "load_search_requests",
        lambda *_args, **_kwargs: ({"queries": ["cortexpilot"], "verify": False}, None),
    )
    monkeypatch.setattr(sched, "_run_search_pipeline", lambda *_args, **_kwargs: {"ok": False, "error": "forced"})

    contract_path = repo / "contract_search_fail.json"
    _write_contract(contract_path, payload)

    orch = Orchestrator(repo)
    run_id = orch.execute_task(contract_path, mock_mode=True)

    manifest = _read_manifest(runs_root, run_id)
    assert manifest["status"] == "FAILURE"
    assert manifest["failure_reason"] == "search pipeline failed"
