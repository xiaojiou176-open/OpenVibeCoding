import hashlib
import json
import os
import subprocess
import time
from functools import partial
from pathlib import Path

from openvibecoding_orch.config import reset_cached_config
from openvibecoding_orch.scheduler import scheduler as scheduler_module
from openvibecoding_orch.scheduler import scheduler_bridge
from openvibecoding_orch.scheduler.scheduler import Orchestrator


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _git(cmd: list[str], cwd: Path) -> None:
    # Keep nested temp repos hermetic when outer Git-driven flows export state
    # such as GIT_INDEX_FILE for the parent repository.
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True, env=env)


def _init_repo(repo: Path) -> None:
    _git(["git", "init"], repo)
    _git(["git", "config", "user.email", "test@example.com"], repo)
    _git(["git", "config", "user.name", "tester"], repo)
    policies = repo / "policies"
    policies.mkdir(parents=True, exist_ok=True)
    (policies / "command_allowlist.json").write_text(
        json.dumps(
            {
                "version": "v1",
                "allow": [
                    {"exec": "codex", "argv_prefixes": [["codex", "exec"]]},
                    {"exec": "git", "argv_prefixes": [["git"]]},
                    {"exec": "echo", "argv_prefixes": [["echo"]]},
                    {"exec": "python", "argv_prefixes": [["python"], ["python", "-m"]]},
                    {"exec": "python3", "argv_prefixes": [["python3"], ["python3", "-m"]]},
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
                        "role": "SEARCHER",
                        "codex_home": "codex_home",
                        "defaults": {
                            "sandbox": "workspace-write",
                            "approval_policy": "on-request",
                            "network": "allow",
                        },
                    },
                    {
                        "agent_id": "agent-1",
                        "role": "REVIEWER",
                        "codex_home": "codex_home",
                        "defaults": {
                            "sandbox": "workspace-write",
                            "approval_policy": "on-request",
                            "network": "deny",
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )


def _write_json(path: Path, payload: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, ensure_ascii=False, indent=2)
    path.write_text(raw, encoding="utf-8")
    return raw


def _output_schema_artifacts(role: str = "worker") -> list[dict]:
    schema_root = Path(__file__).resolve().parents[3] / "schemas"
    schema_name = "agent_task_result.v1.json"
    if role.lower() in {"reviewer"}:
        schema_name = "review_report.v1.json"
    if role.lower() in {"test", "test_runner"}:
        schema_name = "test_report.v1.json"
    schema_path = schema_root / schema_name
    sha = hashlib.sha256(schema_path.read_bytes()).hexdigest()
    return [
        {
            "name": f"output_schema.{role.lower()}",
            "uri": f"schemas/{schema_name}",
            "sha256": sha,
        }
    ]


def _base_contract(task_id: str, artifacts: list[dict]) -> dict:
    merged_artifacts = [*_output_schema_artifacts("worker"), *artifacts]
    return {
        "task_id": task_id,
        "owner_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "assigned_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "inputs": {"spec": "mock update", "artifacts": merged_artifacts},
        "required_outputs": [{"name": "mock_output.txt", "type": "file", "acceptance": "ok"}],
        "allowed_paths": ["mock_output.txt"],
        "forbidden_actions": [],
        "acceptance_tests": [{"name": "echo", "cmd": "echo ok", "must_pass": True}],
        "tool_permissions": {
            "filesystem": "workspace-write",
            "shell": "on-request",
            "network": "allow",
            "mcp_tools": ["codex"],
        },
        "mcp_tool_set": ["01-filesystem"],
        "timeout_retry": {"timeout_sec": 1, "max_retries": 0, "retry_backoff_sec": 0},
        "rollback": {"strategy": "git_reset_hard", "baseline_ref": "HEAD"},
        "evidence_links": [],
        "log_refs": {"run_id": "", "paths": {}},
    }


def _wait_until(predicate, *, timeout_sec: float = 60.0, interval_sec: float = 0.05) -> None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(interval_sec)
    assert predicate()


def _reset_scheduler_tool_hooks(monkeypatch) -> None:
    monkeypatch.setattr(scheduler_module, "_load_browser_tasks", scheduler_bridge.load_browser_tasks)
    monkeypatch.setattr(scheduler_module, "_load_tampermonkey_tasks", scheduler_bridge.load_tampermonkey_tasks)
    monkeypatch.setattr(scheduler_module, "_run_browser_tasks", scheduler_bridge.run_browser_tasks)
    monkeypatch.setattr(
        scheduler_module,
        "_run_optional_tool_requests",
        scheduler_bridge.run_optional_tool_requests,
    )
    monkeypatch.setattr(
        scheduler_module,
        "_run_tampermonkey_tasks",
        partial(
            scheduler_bridge.run_tampermonkey_tasks,
            run_tampermonkey_fn=lambda *args, **kwargs: scheduler_module.run_tampermonkey(*args, **kwargs),
        ),
    )


def _configure_runtime_roots(monkeypatch, runtime_root: Path, runs_root: Path, worktree_root: Path) -> None:
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("OPENVIBECODING_WORKTREE_ROOT", str(worktree_root))
    # Keep env-driven runtime paths deterministic across xdist workers.
    reset_cached_config()


def _pin_tool_requests(
    monkeypatch,
    *,
    search_request: dict | None = None,
    browser_request: dict | None = None,
    tamper_request: dict | None = None,
) -> None:
    monkeypatch.setattr(
        scheduler_module,
        "_load_search_requests",
        lambda _contract, _repo_root: (search_request, None),
    )
    monkeypatch.setattr(
        scheduler_module,
        "_load_browser_tasks",
        lambda _contract, _repo_root: (browser_request, None),
    )
    monkeypatch.setattr(
        scheduler_module,
        "_load_tampermonkey_tasks",
        lambda _contract, _repo_root: (tamper_request, None),
    )


def test_tool_pipeline_network_gate_denied(tmp_path: Path, monkeypatch) -> None:
    _reset_scheduler_tool_hooks(monkeypatch)
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / "codex_home").mkdir()
    (repo / "README.md").write_text("hello", encoding="utf-8")
    _git(["git", "add", "README.md", "policies/command_allowlist.json"], repo)
    _git(["git", "commit", "-m", "init"], repo)

    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"
    _configure_runtime_roots(monkeypatch, runtime_root, runs_root, worktree_root)
    monkeypatch.setenv("OPENVIBECODING_SEARCH_MODE", "mock")
    monkeypatch.setenv("OPENVIBECODING_CHAIN_EXEC_MODE", "inline")

    search_path = repo / "search_requests.json"
    search_body = _write_json(search_path, {"queries": ["openvibecoding"]})
    artifacts = [
        {
            "name": "search_requests.json",
            "uri": search_path.name,
            "sha256": _sha256_text(search_body),
        }
    ]
    contract = _base_contract("task_tool_gate", artifacts)
    contract["assigned_agent"]["role"] = "SEARCHER"
    contract["tool_permissions"]["network"] = "deny"
    contract_path = repo / "contract.json"
    _write_json(contract_path, contract)

    monkeypatch.chdir(repo)
    orch = Orchestrator(repo)
    run_id = orch.execute_task(contract_path, mock_mode=True)

    manifest_path = runs_root / run_id / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload.get("status") == "FAILURE"
    assert payload.get("failure_reason") == "network gate violation"


def test_tool_pipeline_search_browser_tampermonkey(tmp_path: Path, monkeypatch) -> None:
    _reset_scheduler_tool_hooks(monkeypatch)
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / "README.md").write_text("hello", encoding="utf-8")
    _git(["git", "add", "README.md", "policies/command_allowlist.json"], repo)
    _git(["git", "commit", "-m", "init"], repo)

    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"
    _configure_runtime_roots(monkeypatch, runtime_root, runs_root, worktree_root)
    monkeypatch.setenv("OPENVIBECODING_SEARCH_MODE", "mock")
    monkeypatch.setenv("OPENVIBECODING_CHAIN_EXEC_MODE", "inline")
    class _BrowserOk:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def run_script(self, _script: str, _url: str) -> dict:
            return {"ok": True, "mode": "mock", "artifacts": {}, "duration_ms": 0}

    monkeypatch.setattr("openvibecoding_orch.runners.tool_runner.BrowserRunner", _BrowserOk)

    search_path = repo / "search_requests.json"
    search_body = _write_json(search_path, {"queries": ["openvibecoding"], "repeat": 2, "parallel": 2})

    html_path = repo / "page.html"
    html_path.write_text("<html><body>ok</body></html>", encoding="utf-8")
    browser_path = repo / "browser_tasks.json"
    browser_body = _write_json(
        browser_path,
        {"tasks": [{"url": html_path.as_uri(), "script": "return document.title;"}]},
    )

    tamper_path = repo / "tampermonkey_tasks.json"
    tamper_body = _write_json(
        tamper_path,
        {"tasks": [{"script": "deal_scrape", "raw_output": "ok", "parsed": {"items": 1}}]},
    )
    _pin_tool_requests(
        monkeypatch,
        search_request={"queries": ["openvibecoding"], "repeat": 2, "parallel": 2},
        browser_request={"tasks": [{"url": html_path.as_uri(), "script": "return document.title;"}]},
        tamper_request={"tasks": [{"script": "deal_scrape", "raw_output": "ok", "parsed": {"items": 1}}]},
    )

    artifacts = [
        {
            "name": "search_requests.json",
            "uri": search_path.name,
            "sha256": _sha256_text(search_body),
        },
        {
            "name": "browser_tasks.json",
            "uri": browser_path.name,
            "sha256": _sha256_text(browser_body),
        },
        {
            "name": "tampermonkey_tasks.json",
            "uri": tamper_path.name,
            "sha256": _sha256_text(tamper_body),
        },
    ]

    contract = _base_contract("task_tool_pipeline", artifacts)
    contract["assigned_agent"]["role"] = "SEARCHER"
    contract_path = repo / "contract.json"
    _write_json(contract_path, contract)

    monkeypatch.chdir(repo)
    orch = Orchestrator(repo)
    run_id = orch.execute_task(contract_path, mock_mode=True)

    run_dir = runs_root / run_id
    _wait_until(
        lambda: (
            (run_dir / "artifacts" / "search_results.json").exists()
            and (run_dir / "artifacts" / "verification.json").exists()
            and (run_dir / "artifacts" / "search_results.jsonl").exists()
            and (run_dir / "artifacts" / "verification.jsonl").exists()
            and (run_dir / "artifacts" / "browser_results.json").exists()
            and (run_dir / "artifacts" / "tampermonkey_results.json").exists()
            and (run_dir / "events.jsonl").exists()
            and "SEARCH_RESULTS" in (run_dir / "events.jsonl").read_text(encoding="utf-8")
            and "SEARCH_VERIFICATION" in (run_dir / "events.jsonl").read_text(encoding="utf-8")
            and "BROWSER_RESULTS" in (run_dir / "events.jsonl").read_text(encoding="utf-8")
            and "TAMPERMONKEY_OUTPUT" in (run_dir / "events.jsonl").read_text(encoding="utf-8")
        )
    )


def test_tool_pipeline_searcher_short_circuits_before_codex_runner(tmp_path: Path, monkeypatch) -> None:
    _reset_scheduler_tool_hooks(monkeypatch)
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / "codex_home").mkdir()
    (repo / "README.md").write_text("hello", encoding="utf-8")
    _git(["git", "add", "README.md", "policies/command_allowlist.json"], repo)
    _git(["git", "commit", "-m", "init"], repo)

    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"
    _configure_runtime_roots(monkeypatch, runtime_root, runs_root, worktree_root)
    monkeypatch.setenv("OPENVIBECODING_SEARCH_MODE", "mock")
    monkeypatch.setenv("OPENVIBECODING_CHAIN_EXEC_MODE", "inline")
    monkeypatch.setenv("OPENVIBECODING_RUNNER", "codex")
    monkeypatch.setenv("OPENVIBECODING_MCP_ONLY", "1")
    monkeypatch.setenv("OPENVIBECODING_ALLOW_CODEX_EXEC", "1")

    search_path = repo / "search_requests.json"
    search_body = _write_json(
        search_path,
        {"queries": ["openvibecoding"], "providers": ["chatgpt_web", "grok_web"], "repeat": 2, "parallel": 2},
    )
    _pin_tool_requests(
        monkeypatch,
        search_request={"queries": ["openvibecoding"], "providers": ["chatgpt_web", "grok_web"], "repeat": 2, "parallel": 2},
    )

    artifacts = [
        {
            "name": "search_requests.json",
            "uri": search_path.name,
            "sha256": _sha256_text(search_body),
        }
    ]

    contract = _base_contract("task_search_short_circuit", artifacts)
    contract["assigned_agent"]["role"] = "SEARCHER"
    contract_path = repo / "contract.json"
    _write_json(contract_path, contract)

    monkeypatch.setattr(
        "openvibecoding_orch.runners.codex_runner.CodexRunner.run_contract",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("codex runner should not execute after search pipeline success")),
    )

    monkeypatch.chdir(repo)
    orch = Orchestrator(repo)
    run_id = orch.execute_task(contract_path, mock_mode=False)

    manifest = json.loads((runs_root / run_id / "manifest.json").read_text(encoding="utf-8"))
    run_dir = runs_root / run_id
    assert manifest["status"] == "SUCCESS"
    assert (run_dir / "artifacts" / "search_results.json").exists()
    assert (run_dir / "reports" / "evidence_bundle.json").exists()
    assert (run_dir / "reports" / "task_result.json").exists()


def test_tool_pipeline_browser_failure_marks_run_failed(tmp_path: Path, monkeypatch) -> None:
    _reset_scheduler_tool_hooks(monkeypatch)
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / "README.md").write_text("hello", encoding="utf-8")
    _git(["git", "add", "README.md", "policies/command_allowlist.json"], repo)
    _git(["git", "commit", "-m", "init"], repo)

    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"
    _configure_runtime_roots(monkeypatch, runtime_root, runs_root, worktree_root)
    monkeypatch.setenv("OPENVIBECODING_SEARCH_MODE", "mock")
    monkeypatch.setenv("OPENVIBECODING_CHAIN_EXEC_MODE", "inline")

    browser_path = repo / "browser_tasks.json"
    browser_body = _write_json(
        browser_path,
        {"tasks": [{"url": "https://example.com", "script": ""}]},
    )
    _pin_tool_requests(
        monkeypatch,
        browser_request={"tasks": [{"url": "https://example.com", "script": ""}]},
    )

    artifacts = [
        {
            "name": "browser_tasks.json",
            "uri": browser_path.name,
            "sha256": _sha256_text(browser_body),
        },
    ]

    contract = _base_contract("task_browser_fail", artifacts)
    contract["assigned_agent"]["role"] = "SEARCHER"
    contract_path = repo / "contract.json"
    _write_json(contract_path, contract)

    class _BrowserFail:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def run_script(self, _script: str, _url: str) -> dict:
            return {"ok": False, "mode": "mock", "error": "browser down", "artifacts": {}, "duration_ms": 0}

    monkeypatch.setattr("openvibecoding_orch.runners.tool_runner.BrowserRunner", _BrowserFail)

    monkeypatch.chdir(repo)
    orch = Orchestrator(repo)
    run_id = orch.execute_task(contract_path, mock_mode=True)

    manifest_path = runs_root / run_id / "manifest.json"
    events_path = runs_root / run_id / "events.jsonl"
    _wait_until(
        lambda: (
            manifest_path.exists()
            and json.loads(manifest_path.read_text(encoding="utf-8")).get("status") == "FAILURE"
            and json.loads(manifest_path.read_text(encoding="utf-8")).get("failure_reason") == "browser tasks failed"
            and events_path.exists()
            and "BROWSER_TASKS_RESULT" in events_path.read_text(encoding="utf-8")
        )
    )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload.get("status") == "FAILURE"
    assert payload.get("failure_reason") == "browser tasks failed"


def test_tool_pipeline_tampermonkey_failure_marks_run_failed(tmp_path: Path, monkeypatch) -> None:
    _reset_scheduler_tool_hooks(monkeypatch)
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / "README.md").write_text("hello", encoding="utf-8")
    _git(["git", "add", "README.md", "policies/command_allowlist.json"], repo)
    _git(["git", "commit", "-m", "init"], repo)

    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"
    _configure_runtime_roots(monkeypatch, runtime_root, runs_root, worktree_root)
    monkeypatch.setenv("OPENVIBECODING_SEARCH_MODE", "mock")

    tamper_path = repo / "tampermonkey_tasks.json"
    tamper_body = _write_json(
        tamper_path,
        {"tasks": [{"script": "deal_scrape", "raw_output": "ok"}]},
    )
    artifacts = [
        {
            "name": "tampermonkey_tasks.json",
            "uri": tamper_path.name,
            "sha256": _sha256_text(tamper_body),
        },
    ]

    contract = _base_contract("task_tamper_fail", artifacts)
    contract["assigned_agent"]["role"] = "SEARCHER"
    contract_path = repo / "contract.json"
    _write_json(contract_path, contract)

    def _fail_tamper(*args, **kwargs):
        raise RuntimeError("tamper down")

    monkeypatch.setattr("openvibecoding_orch.scheduler.scheduler.run_tampermonkey", _fail_tamper)

    monkeypatch.chdir(repo)
    orch = Orchestrator(repo)
    run_id = orch.execute_task(contract_path, mock_mode=True)

    manifest_path = runs_root / run_id / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload.get("status") == "FAILURE"
    assert payload.get("failure_reason") == "tampermonkey tasks failed"

    events_text = (runs_root / run_id / "events.jsonl").read_text(encoding="utf-8")
    assert "TAMPERMONKEY_FAILURE" in events_text


def test_tool_pipeline_tampermonkey_exec_failure_marks_run_failed(tmp_path: Path, monkeypatch) -> None:
    _reset_scheduler_tool_hooks(monkeypatch)
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / "README.md").write_text("hello", encoding="utf-8")
    _git(["git", "add", "README.md", "policies/command_allowlist.json"], repo)
    _git(["git", "commit", "-m", "init"], repo)

    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"
    _configure_runtime_roots(monkeypatch, runtime_root, runs_root, worktree_root)
    monkeypatch.setenv("OPENVIBECODING_SEARCH_MODE", "mock")

    tamper_path = repo / "tampermonkey_tasks.json"
    tamper_body = _write_json(
        tamper_path,
        {"tasks": [{"script": "deal_scrape", "raw_output": "ok"}]},
    )
    artifacts = [
        {
            "name": "tampermonkey_tasks.json",
            "uri": tamper_path.name,
            "sha256": _sha256_text(tamper_body),
        },
    ]

    contract = _base_contract("task_tamper_exec_fail", artifacts)
    contract["assigned_agent"]["role"] = "SEARCHER"
    contract_path = repo / "contract.json"
    _write_json(contract_path, contract)

    def _exec_fail(*args, **kwargs):
        return {"ok": False, "error": "execution failed"}

    monkeypatch.setattr("openvibecoding_orch.scheduler.scheduler.run_tampermonkey", _exec_fail)

    monkeypatch.chdir(repo)
    orch = Orchestrator(repo)
    run_id = orch.execute_task(contract_path, mock_mode=True)

    manifest_path = runs_root / run_id / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload.get("status") == "FAILURE"
    assert payload.get("failure_reason") == "tampermonkey tasks failed"

    events_text = (runs_root / run_id / "events.jsonl").read_text(encoding="utf-8")
    assert "TAMPERMONKEY_FAILURE" in events_text
