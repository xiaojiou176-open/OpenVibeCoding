import json
import importlib
from pathlib import Path

from cortexpilot_orch.runners.tool_runner import ToolRunner
from cortexpilot_orch.store.run_store import RunStore
import hashlib
import sys


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


def _write_active_contract(store: RunStore, run_id: str, mcp_tools: list[str], monkeypatch) -> None:
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(store._runs_root.parent))
    contract = {
        "task_id": "tool_task",
        "owner_agent": {"role": "TECH_LEAD", "agent_id": "owner"},
        "assigned_agent": {"role": "WORKER", "agent_id": "worker"},
        "inputs": {"spec": "spec", "artifacts": _output_schema_artifacts("worker")},
        "required_outputs": [{"name": "patch", "type": "patch", "acceptance": "ok"}],
        "allowed_paths": ["README.md"],
        "forbidden_actions": ["rm -rf"],
        "acceptance_tests": [{"name": "noop", "cmd": "echo ok", "must_pass": True}],
        "tool_permissions": {
            "filesystem": "workspace-write",
            "shell": "on-request",
            "network": "deny",
            "mcp_tools": mcp_tools,
        },
        "mcp_tool_set": ["01-filesystem"],
        "timeout_retry": {"timeout_sec": 1, "max_retries": 0, "retry_backoff_sec": 0},
        "rollback": {"strategy": "worktree_drop", "baseline_ref": "HEAD"},
        "evidence_links": [],
        "log_refs": {"run_id": run_id, "paths": {}},
    }
    store.write_active_contract(run_id, contract)


def _read_events(tmp_path: Path, run_id: str) -> list[dict]:
    events_path = tmp_path / run_id / "events.jsonl"
    return [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _first_event(events: list[dict], event_name: str) -> dict:
    for entry in events:
        if entry.get("event") == event_name:
            return entry
    raise AssertionError(f"missing event: {event_name}")


def test_tool_runner_browser_failure(tmp_path: Path, monkeypatch) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("run_browser_fail")

    class DummyBrowser:
        def __init__(self, run_dir, headless=None, browser_policy=None):
            self.run_dir = run_dir

        def run_script(self, script, url):
            raise RuntimeError("boom")

    monkeypatch.setattr("cortexpilot_orch.runners.tool_runner.BrowserRunner", DummyBrowser)

    task_id = "task_browser_fail"
    runner = ToolRunner(run_id, store)
    result = runner.run_browser("https://example.com", "return 1;", task_id=task_id)
    assert result["ok"] is False

    events = _read_events(tmp_path, run_id)
    failure_event = _first_event(events, "TOOL_FAILURE")
    assert failure_event.get("meta", {}).get("tool") == "playwright"
    assert failure_event.get("meta", {}).get("task_id") == task_id


def test_tool_runner_browser_error_payload(tmp_path: Path, monkeypatch) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("run_browser_error_payload")

    class DummyBrowser:
        def __init__(self, run_dir, headless=None, browser_policy=None):
            self.run_dir = run_dir

        def run_script(self, script, url):
            return {
                "ok": False,
                "mode": "playwright",
                "error": "browser failed",
                "artifacts": {"error": "error.txt"},
                "policy_events": [
                    {"event": "BROWSER_PROFILE_MODE_SELECTED", "level": "INFO", "meta": {"mode": "ephemeral"}},
                    {"event": "BROWSER_STEALTH_FALLBACK", "level": "WARN", "meta": {"requested_mode": "plugin"}},
                ],
            }

    monkeypatch.setattr("cortexpilot_orch.runners.tool_runner.BrowserRunner", DummyBrowser)

    task_id = "task_browser_payload"
    runner = ToolRunner(run_id, store)
    result = runner.run_browser("https://example.com", "return 1;", task_id=task_id)
    assert result["ok"] is False

    events = _read_events(tmp_path, run_id)
    failure_event = _first_event(events, "TOOL_FAILURE")
    assert failure_event.get("meta", {}).get("task_id") == task_id
    assert failure_event.get("meta", {}).get("error") == "browser failed"
    assert _first_event(events, "BROWSER_PROFILE_MODE_SELECTED")
    assert _first_event(events, "BROWSER_STEALTH_FALLBACK")


def test_tool_runner_search_failure(tmp_path: Path, monkeypatch) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("run_search_fail")

    def _raise(*args, **kwargs):
        raise RuntimeError("search down")

    monkeypatch.setattr("cortexpilot_orch.runners.tool_runner.search_verify", _raise)

    runner = ToolRunner(run_id, store)
    result = runner.run_search("cortexpilot", provider="duckduckgo")
    assert result["ok"] is False

    events = _read_events(tmp_path, run_id)
    failure_event = _first_event(events, "TOOL_FAILURE")
    assert failure_event.get("meta", {}).get("tool") == "search"
    assert failure_event.get("meta", {}).get("task_id")


def test_tool_runner_search_result_ok_false_logs_failure(tmp_path: Path, monkeypatch) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("run_search_fail_payload")

    def _fake(*args, **kwargs):
        return {"ok": False, "mode": "web", "error": "blocked"}

    monkeypatch.setattr("cortexpilot_orch.runners.tool_runner.search_verify", _fake)

    runner = ToolRunner(run_id, store)
    result = runner.run_search("cortexpilot", provider="chatgpt_web")
    assert result["ok"] is False

    events = _read_events(tmp_path, run_id)
    failure_event = _first_event(events, "TOOL_FAILURE")
    assert failure_event.get("meta", {}).get("task_id")
    assert failure_event.get("meta", {}).get("error") == "blocked"


def test_tool_runner_browser_ddg_fail_closed_logs_explicit_browser_error(tmp_path: Path, monkeypatch) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("run_search_browser_ddg_fail_closed")

    def _fake(*args, **kwargs):
        return {
            "ok": False,
            "mode": "browser",
            "resolved_provider": "browser_ddg",
            "error": "browser_ddg_failed: singleton attach failed",
            "results": [],
        }

    monkeypatch.setattr("cortexpilot_orch.runners.tool_runner.search_verify", _fake)

    runner = ToolRunner(run_id, store)
    result = runner.run_search("cortexpilot", provider="browser")
    assert result["ok"] is False
    assert result["resolved_provider"] == "browser_ddg"

    events = _read_events(tmp_path, run_id)
    failure_event = _first_event(events, "TOOL_FAILURE")
    assert failure_event.get("meta", {}).get("task_id")
    assert failure_event.get("meta", {}).get("tool") == "search"
    assert failure_event.get("meta", {}).get("error") == "browser_ddg_failed: singleton attach failed"


def test_tool_runner_mcp_failure(tmp_path: Path, monkeypatch) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("run_mcp_fail")
    _write_active_contract(store, run_id, ["codex"], monkeypatch)

    def _raise(*args, **kwargs):
        raise RuntimeError("mcp down")

    monkeypatch.setattr("cortexpilot_orch.runners.tool_runner.mcp_adapter.record_mcp_call", _raise)

    runner = ToolRunner(run_id, store)
    result = runner.run_mcp("codex", {"payload": {}})
    assert result["ok"] is False

    events = _read_events(tmp_path, run_id)
    failure_event = _first_event(events, "TOOL_FAILURE")
    assert failure_event.get("meta", {}).get("tool") == "mcp"
    assert failure_event.get("meta", {}).get("task_id") == "tool_task"


def test_tool_runner_mcp_denied_when_not_allowed(tmp_path: Path, monkeypatch) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("run_mcp_denied")
    _write_active_contract(store, run_id, ["codex"], monkeypatch)

    runner = ToolRunner(run_id, store)
    result = runner.run_mcp("sampling", {"payload": {}})
    assert result["ok"] is False

    events = _read_events(tmp_path, run_id)
    denied_event = _first_event(events, "MCP_TOOL_DENIED")
    assert denied_event.get("meta", {}).get("task_id") == "tool_task"
    assert denied_event.get("meta", {}).get("denied_reason") == "tool not allowed"


def test_tool_runner_sampling_requires_approval(tmp_path: Path, monkeypatch) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("run_sampling_blocked")
    _write_active_contract(store, run_id, ["codex", "sampling"], monkeypatch)

    monkeypatch.delenv("CORTEXPILOT_SAMPLING_APPROVED", raising=False)

    runner = ToolRunner(run_id, store)
    result = runner.run_mcp("sampling", {"payload": {"query": "ping"}})
    assert result["ok"] is False
    assert result["error"] == "sampling requires explicit approval"

    events = _read_events(tmp_path, run_id)
    gate_event = _first_event(events, "MCP_SAMPLING_GATE_RESULT")
    assert gate_event.get("meta", {}).get("task_id") == "tool_task"
    assert gate_event.get("meta", {}).get("reason") == "sampling requires explicit approval"


def test_tool_runner_sampling_approved(tmp_path: Path, monkeypatch) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("run_sampling_ok")
    _write_active_contract(store, run_id, ["codex", "sampling"], monkeypatch)

    monkeypatch.setenv("CORTEXPILOT_SAMPLING_APPROVED", "true")

    runner = ToolRunner(run_id, store)
    result = runner.run_mcp("sampling", {"payload": {"query": "ping"}})
    assert result["ok"] is False
    assert result["reason"] == "non-adapter mcp execution is not supported"
    assert result["error"] == "non-adapter mcp execution is not supported"

    events = (tmp_path / run_id / "events.jsonl").read_text(encoding="utf-8")
    assert "MCP_SAMPLING_REQUEST" in events
    assert "MCP_TOOL_EXECUTION_UNAVAILABLE" in events


def test_tool_runner_browser_init_typeerror_policy_compat_fallback(tmp_path: Path, monkeypatch) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("run_browser_policy_compat")

    class CompatBrowser:
        def __init__(self, run_dir, headless=None):
            self.run_dir = run_dir

        def run_script(self, script, url):
            return {"ok": True, "mode": "playwright", "duration_ms": 3, "artifacts": {"trace": "t.zip"}}

    monkeypatch.setattr("cortexpilot_orch.runners.tool_runner.BrowserRunner", CompatBrowser)

    runner = ToolRunner(run_id, store)
    result = runner.run_browser(
        "https://example.com",
        "return 1;",
        task_id="task_browser_compat",
        browser_policy={"stealth_mode": "none"},
    )
    assert result["ok"] is True

    events = _read_events(tmp_path, run_id)
    used_event = _first_event(events, "TOOL_USED")
    assert used_event.get("meta", {}).get("task_id") == "task_browser_compat"
    assert used_event.get("meta", {}).get("tool") == "playwright"


def test_tool_runner_search_typeerror_policy_compat_fallback(tmp_path: Path, monkeypatch) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("run_search_policy_compat")
    calls = {"count": 0}

    def _search(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise TypeError("unexpected keyword argument 'browser_policy'")
        return {"ok": True, "mode": "web", "duration_ms": 5, "meta": {"artifacts": {}}}

    monkeypatch.setattr("cortexpilot_orch.runners.tool_runner.search_verify", _search)

    runner = ToolRunner(run_id, store)
    result = runner.run_search("cortexpilot", provider="codex_web", browser_policy={"profile_mode": "ephemeral"})
    assert result["ok"] is True
    assert calls["count"] == 2

    events = _read_events(tmp_path, run_id)
    used_event = _first_event(events, "TOOL_USED")
    assert used_event.get("meta", {}).get("tool") == "search"
    assert used_event.get("meta", {}).get("args", {}).get("provider") == "codex_web"


def test_tool_runner_policy_events_filters_invalid_entries(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("run_policy_filters")
    runner = ToolRunner(run_id, store)

    runner._append_policy_events(  # type: ignore[attr-defined]
        [
            "bad-entry",
            {"event": "   ", "level": "WARN"},
            {"event": "SEARCH_POLICY_OK", "level": "INFO", "meta": {"mode": "safe"}},
        ],
        source="search",
        task_id=None,
    )
    runner._append_policy_audit(  # type: ignore[attr-defined]
        {"events": [{"event": "SEARCH_AUDIT_APPLIED", "level": "INFO", "meta": {"strict": True}}]},
        source="search",
        task_id=None,
    )

    events = _read_events(tmp_path, run_id)
    policy_event = _first_event(events, "SEARCH_POLICY_OK")
    assert policy_event.get("meta", {}).get("source") == "search"
    assert "task_id" not in policy_event.get("meta", {})
    audit_event = _first_event(events, "SEARCH_AUDIT_APPLIED")
    assert audit_event.get("meta", {}).get("strict") is True
    assert len([entry for entry in events if entry.get("event") == "SEARCH_POLICY_OK"]) == 1


def test_tool_runner_resolve_task_id_contract_blank_falls_back_default(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("run_task_id_fallback")
    runner = ToolRunner(run_id, store)

    resolved = runner._resolve_task_id(  # type: ignore[attr-defined]
        None,
        default_task_id="search_default",
        contract={"task_id": "   "},
    )
    assert resolved == "search_default"


def test_tool_runner_module_import_keeps_sys_path_when_root_already_present(monkeypatch) -> None:
    module_name = "cortexpilot_orch.runners.tool_runner"
    module = importlib.import_module(module_name)
    root_str = str(module.ROOT)
    if root_str not in sys.path:
        sys.path.append(root_str)
    before_len = len(sys.path)
    reloaded = importlib.reload(module)
    assert str(reloaded.ROOT) in sys.path
    assert len(sys.path) == before_len
