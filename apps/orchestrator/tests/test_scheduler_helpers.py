import json
import threading
import time
from pathlib import Path

import pytest

from cortexpilot_orch.runners.app_server_runner import AppServerRunner
from cortexpilot_orch.scheduler import scheduler as sched
from cortexpilot_orch.scheduler import scheduler_bridge_runtime as bridge_runtime
from cortexpilot_orch.store.run_store import RunStore


def test_human_approval_flow_reads_events(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    store = RunStore(runs_root=runs_root)
    run_id = store.create_run("task")
    events_path = runs_root / run_id / "events.jsonl"
    events_path.write_text(json.dumps({"event": "HUMAN_APPROVAL_COMPLETED"}) + "\n", encoding="utf-8")

    monkeypatch.setenv("CORTEXPILOT_GOD_MODE_TIMEOUT_SEC", "2")
    approved = sched._await_human_approval(run_id, store)
    assert approved is True


def test_requires_human_approval_respects_env(monkeypatch) -> None:
    contract = {"tool_permissions": {"network": "deny", "shell": "on-request"}}
    monkeypatch.setenv("CORTEXPILOT_GOD_MODE_REQUIRED", "1")
    assert sched._requires_human_approval(contract, requires_network=False) is True
    monkeypatch.setenv("CORTEXPILOT_GOD_MODE_REQUIRED", "0")
    monkeypatch.setenv("CORTEXPILOT_GOD_MODE_ON_REQUEST", "1")
    assert sched._requires_human_approval(contract, requires_network=False) is True


def test_safe_artifact_path_and_json_loader(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))

    repo_file = repo_root / "artifact.json"
    repo_file.write_text(json.dumps({"ok": True}), encoding="utf-8")
    runtime_file = runtime_root / "artifact.json"
    runtime_file.write_text(json.dumps({"ok": False}), encoding="utf-8")

    assert sched._safe_artifact_path(str(repo_file), repo_root) == repo_file.resolve()
    assert sched._safe_artifact_path(str(runtime_file), repo_root) == runtime_file.resolve()
    assert sched._safe_artifact_path("/etc/passwd", repo_root) is None

    payload, error, path = sched._load_json_artifact({"uri": str(repo_file)}, repo_root)
    assert error is None
    assert payload == {"ok": True}
    assert path == repo_file.resolve()

    bad_file = repo_root / "bad.json"
    bad_file.write_text("{", encoding="utf-8")
    payload, error, path = sched._load_json_artifact({"uri": str(bad_file)}, repo_root)
    assert payload is None
    assert "artifact json invalid" in error
    assert path == bad_file.resolve()


def test_load_search_requests_variants(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(tmp_path / "runtime"))

    list_path = repo_root / "search_requests.json"
    list_path.write_text(json.dumps(["q1", "q2"]), encoding="utf-8")
    contract_list = {"inputs": {"artifacts": [{"name": "search_requests.json", "uri": str(list_path)}]}}
    payload, error = sched._load_search_requests(contract_list, repo_root)
    assert error is None
    assert payload["queries"] == ["q1", "q2"]
    assert payload["providers"] == ["chatgpt_web", "grok_web"]

    dict_path = repo_root / "search_queries.json"
    dict_path.write_text(json.dumps({"queries": ["q3"], "repeat": 3, "parallel": 1, "providers": ["duckduckgo"]}), encoding="utf-8")
    contract_dict = {"inputs": {"artifacts": [{"name": "search_queries.json", "uri": str(dict_path)}]}}
    payload, error = sched._load_search_requests(contract_dict, repo_root)
    assert error is None
    assert payload["repeat"] == 3
    assert payload["parallel"] == 1
    assert payload["providers"] == ["duckduckgo"]

    bad_path = repo_root / "bad.json"
    bad_path.write_text(json.dumps({"queries": []}), encoding="utf-8")
    contract_bad = {"inputs": {"artifacts": [{"name": "search_requests.json", "uri": str(bad_path)}]}}
    payload, error = sched._load_search_requests(contract_bad, repo_root)
    assert payload is None
    assert error == "search queries empty"


def test_load_browser_and_tampermonkey_tasks(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    browser_path = repo_root / "browser_tasks.json"
    browser_path.write_text(json.dumps({"headless": True, "tasks": [{"url": "https://example.com", "script": ""}]}), encoding="utf-8")
    contract_browser = {"inputs": {"artifacts": [{"name": "browser_tasks.json", "uri": str(browser_path)}]}}
    payload, error = sched._load_browser_tasks(contract_browser, repo_root)
    assert error is None
    assert payload["tasks"][0]["url"] == "https://example.com"

    tamper_path = repo_root / "tampermonkey_tasks.json"
    tamper_path.write_text(json.dumps([{"script": "foo", "raw_output": "bar"}]), encoding="utf-8")
    contract_tamper = {"inputs": {"artifacts": [{"name": "tampermonkey_tasks.json", "uri": str(tamper_path)}]}}
    payload, error = sched._load_tampermonkey_tasks(contract_tamper, repo_root)
    assert error is None
    assert payload["tasks"][0]["script"] == "foo"


def test_run_browser_and_tamper_tasks(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    store = RunStore(runs_root=runs_root)
    run_id = store.create_run("task_browser")

    class DummyToolRunner:
        def run_browser(self, url: str, script: str, task_id: str, headless=None, browser_policy=None, policy_audit=None):
            return {
                "ok": True,
                "url": url,
                "script": script,
                "task_id": task_id,
                "headless": headless,
                "browser_policy": browser_policy,
                "policy_audit": policy_audit,
            }

    result = sched._run_browser_tasks(
        run_id,
        DummyToolRunner(),
        store,
        {"tasks": [{"url": "https://example.com", "script": ""}], "headless": True},
    )
    assert result["ok"] is True
    assert result["failures"] == []
    artifacts_path = runs_root / run_id / "artifacts" / "browser_results.json"
    assert artifacts_path.exists()

    calls: list[dict] = []

    def _fake_tamper(
        run_id: str,
        script: str,
        raw_output: str,
        parsed=None,
        task_id: str = "",
        url: str = "",
        script_content: str = "",
        browser_policy=None,
    ):
        del run_id, raw_output, parsed, url, script_content, browser_policy
        calls.append({"script": script, "task_id": task_id})

    monkeypatch.setattr(sched, "run_tampermonkey", _fake_tamper)
    tamper = sched._run_tampermonkey_tasks(
        run_id,
        {"tasks": [{"script": "foo", "raw_output": "bar", "parsed": {"ok": True}}]},
        store,
    )
    assert tamper["tasks"] == 1
    assert tamper["ok"] is True
    assert calls[0]["script"] == "foo"

    class FailingToolRunner:
        def run_browser(self, url: str, script: str, task_id: str, headless=None, browser_policy=None, policy_audit=None):
            return {
                "ok": False,
                "url": url,
                "script": script,
                "task_id": task_id,
                "headless": headless,
                "browser_policy": browser_policy,
                "policy_audit": policy_audit,
            }

    failed = sched._run_browser_tasks(
        run_id,
        FailingToolRunner(),
        store,
        {"tasks": [{"url": "https://example.com", "script": ""}], "headless": True},
    )
    assert failed["ok"] is False
    assert failed["failures"]
    browser_payload = json.loads(artifacts_path.read_text(encoding="utf-8"))
    entries = browser_payload.get("entries", [])
    assert len(entries) == 2
    latest = browser_payload.get("latest", {})
    summary = latest.get("summary", {})
    assert summary.get("failures")

    def _fail_tamper(*args, **kwargs):
        raise RuntimeError("tamper failed")

    monkeypatch.setattr(sched, "run_tampermonkey", _fail_tamper)
    tamper_failed = sched._run_tampermonkey_tasks(
        run_id,
        {"tasks": [{"script": "foo", "raw_output": "bar"}]},
        store,
    )
    assert tamper_failed["ok"] is False


def test_scheduler_misc_helpers(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "README.md").write_text("hello", encoding="utf-8")

    run_id = "run_misc"
    log_refs = sched._build_log_refs(run_id, "task", repo_root, "trace")
    assert log_refs["run_id"] == run_id

    assert sched._tool_version(["/nonexistent"]) == "unknown"
    assert sched._resolve_baseline_ref({"rollback": {"baseline_ref": "HEAD"}}, "base") == "base"
    assert sched._resolve_baseline_ref({"rollback": {"baseline_ref": "abc"}}, "base") == "abc"

    assert sched._max_retries({"timeout_retry": {"max_retries": "2"}}) == 2
    assert sched._max_retries({"timeout_retry": {"max_retries": "bad"}}) == 0
    assert sched._retry_backoff({"timeout_retry": {"retry_backoff_sec": "3"}}) == 3

    assert isinstance(sched._select_runner({}, RunStore(runs_root=tmp_path)), object)
    assert isinstance(
        sched._select_runner({"runtime_options": {"runner": "app_server"}}, RunStore(runs_root=tmp_path / "runs_alias")),
        AppServerRunner,
    )


def test_select_runner_does_not_probe_adapter_for_agents_or_app_server(tmp_path: Path, monkeypatch) -> None:
    store = RunStore(runs_root=tmp_path / "runs")

    def _forbidden_import(name: str):
        if name == "cortexpilot_orch.runners.execution_adapter":
            raise AssertionError("execution adapter must not be resolved for agents/app-server")
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(bridge_runtime, "import_module", _forbidden_import)

    monkeypatch.setenv("CORTEXPILOT_RUNNER", "agents")
    assert sched._select_runner({}, store).__class__.__name__ == "AgentsRunner"

    monkeypatch.setenv("CORTEXPILOT_RUNNER", "app-server")
    assert isinstance(sched._select_runner({}, store), AppServerRunner)


def test_run_search_pipeline_with_verify(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runs_root))
    store = RunStore(runs_root=runs_root)
    run_id = store.create_run("task_search")

    class DummyToolRunner:
        def run_search(self, query: str, provider: str = "chatgpt_web", browser_policy=None, policy_audit=None):
            del browser_policy, policy_audit
            if provider == "fail":
                return {"ok": False, "provider": provider, "results": []}
            return {
                "ok": True,
                "provider": provider,
                "results": [{"href": f"https://{provider}.example.com/{query}"}],
                "verification": {"consistent": True},
            }

    request = {
        "queries": ["alpha"],
        "repeat": 2,
        "parallel": 2,
        "providers": ["chatgpt_web", "grok_web"],
        "verify": {"providers": ["chatgpt_web"], "repeat": 1},
    }
    result = sched._run_search_pipeline(
        run_id,
        DummyToolRunner(),
        request,
        {"role": "SEARCHER", "agent_id": "agent-1"},
    )
    assert result["ok"] is True

    request["providers"] = ["chatgpt_web", "grok_web", "fail"]
    failing = sched._run_search_pipeline(
        run_id,
        DummyToolRunner(),
        request,
        {"role": "SEARCHER", "agent_id": "agent-1"},
    )
    assert failing["ok"] is False

    request["providers"] = ["chatgpt_web", "grok_web"]
    request["verify"] = {"providers": ["fail"], "repeat": 1}
    verify_failing = sched._run_search_pipeline(
        run_id,
        DummyToolRunner(),
        request,
        {"role": "SEARCHER", "agent_id": "agent-1"},
    )
    assert verify_failing["ok"] is False
    assert verify_failing.get("verify_failures")


def test_run_search_pipeline_serializes_allow_profile_browser_sessions(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runs_root))
    store = RunStore(runs_root=runs_root)
    run_id = store.create_run("task_search_serialized")

    lock = threading.Lock()
    active_calls = 0
    max_concurrent = 0

    class DummyToolRunner:
        def run_search(self, query: str, provider: str = "chatgpt_web", browser_policy=None, policy_audit=None):
            nonlocal active_calls, max_concurrent
            del query, browser_policy, policy_audit
            with lock:
                active_calls += 1
                max_concurrent = max(max_concurrent, active_calls)
            time.sleep(0.01)
            with lock:
                active_calls -= 1
            return {
                "ok": True,
                "provider": provider,
                "results": [{"href": f"https://{provider}.example.com/result"}],
                "verification": {"consistent": True},
            }

    request = {
        "queries": ["alpha"],
        "repeat": 2,
        "parallel": 4,
        "providers": ["chatgpt_web", "grok_web"],
        "verify": {"providers": ["chatgpt_web"], "repeat": 1},
        "browser_policy": {"profile_mode": "allow_profile"},
    }
    result = sched._run_search_pipeline(
        run_id,
        DummyToolRunner(),
        request,
        {"role": "SEARCHER", "agent_id": "agent-1"},
    )
    assert result["ok"] is True
    assert max_concurrent == 1


def test_orchestrator_replay_error_paths(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runs_root))
    orch = sched.Orchestrator(repo_root)

    run_id = RunStore(runs_root=runs_root).create_run("task_replay")
    (runs_root / run_id / "manifest.json").write_text("{}", encoding="utf-8")

    replay = orch.replay_run(run_id, baseline_run_id="missing")
    assert replay["status"] == "fail"

    verify = orch.replay_verify(run_id, strict=True)
    assert verify["status"] == "fail"


def test_scheduler_evidence_hashes(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_hash"
    (run_dir / "reports").mkdir(parents=True, exist_ok=True)
    (run_dir / "tasks").mkdir(parents=True, exist_ok=True)
    (run_dir / "results").mkdir(parents=True, exist_ok=True)
    (run_dir / "reviews").mkdir(parents=True, exist_ok=True)
    (run_dir / "ci").mkdir(parents=True, exist_ok=True)
    (run_dir / "git").mkdir(parents=True, exist_ok=True)
    (run_dir / "tests").mkdir(parents=True, exist_ok=True)
    (run_dir / "trace").mkdir(parents=True, exist_ok=True)

    (run_dir / "events.jsonl").write_text(
        "\n".join([json.dumps({"event": "REPLAY_START"}), json.dumps({"event": "CUSTOM"})]) + "\n",
        encoding="utf-8",
    )
    (run_dir / "patch.diff").write_text("diff --git a/a b/a\n", encoding="utf-8")
    (run_dir / "reports" / "test.json").write_text("{}", encoding="utf-8")
    (run_dir / "tasks" / "task.json").write_text("{}", encoding="utf-8")
    (run_dir / "results" / "out.json").write_text("{}", encoding="utf-8")
    (run_dir / "reviews" / "review.json").write_text("{}", encoding="utf-8")
    (run_dir / "ci" / "ci.json").write_text("{}", encoding="utf-8")
    (run_dir / "git" / "patch.diff").write_text("diff --git a/a b/a\n", encoding="utf-8")
    (run_dir / "tests" / "stdout.log").write_text("ok", encoding="utf-8")
    (run_dir / "trace" / "trace.txt").write_text("trace", encoding="utf-8")

    hashes = sched._collect_evidence_hashes(run_dir)
    assert "events.jsonl" in hashes
    assert "patch.diff" in hashes
