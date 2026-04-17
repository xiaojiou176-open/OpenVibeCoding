from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from openvibecoding_orch.scheduler import tool_execution_pipeline


class _Store:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.events: list[dict[str, Any]] = []

    def append_event(self, run_id: str, payload: dict[str, Any]) -> None:
        self.events.append({"run_id": run_id, **payload})

    def _run_dir(self, run_id: str) -> Path:
        path = self.root / run_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write_artifact(self, run_id: str, name: str, content: str) -> Path:
        path = self._run_dir(run_id) / "artifacts" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path


class _ToolRunner:
    def __init__(self, fail_provider: str | None = None) -> None:
        self.fail_provider = fail_provider

    def run_search(
        self,
        query: str,
        provider: str = "chatgpt_web",
        browser_policy: dict[str, Any] | None = None,
        policy_audit: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if provider == self.fail_provider:
            return {"ok": False, "provider": provider, "results": []}
        return {
            "ok": True,
            "provider": provider,
            "results": [
                {"href": f"https://{provider}.example.com/{query}"},
                {"title": "no href"},
            ],
            "verification": {"consistent": True},
            "policy_audit": policy_audit or {},
            "effective_browser_policy": browser_policy or {},
        }

    def run_mcp(self, _tool: str, _payload: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True}

    def run_browser(
        self,
        url: str,
        script: str,
        task_id: str,
        headless=None,
        browser_policy: dict[str, Any] | None = None,
        policy_audit: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "ok": True,
            "url": url,
            "script": script,
            "task_id": task_id,
            "headless": headless,
            "browser_policy": browser_policy or {},
            "policy_audit": policy_audit or {},
        }


def test_run_search_pipeline_missing_required_provider(tmp_path: Path) -> None:
    store = _Store(tmp_path)
    result = tool_execution_pipeline.run_search_pipeline(
        run_id="run-1",
        tool_runner=_ToolRunner(),
        store=store,
        request={"queries": ["q"], "providers": ["duckduckgo"]},
        requested_by={"role": "SEARCHER", "agent_id": "a-1"},
    )
    assert result["ok"] is False
    assert "missing" in result
    assert store.events and store.events[-1]["event"] == "SEARCH_PARALLEL_POLICY"


def test_run_search_pipeline_adjustments_and_ai_enabled(tmp_path: Path, monkeypatch) -> None:
    store = _Store(tmp_path)
    captured: dict[str, Any] = {}

    monkeypatch.setattr(tool_execution_pipeline, "write_search_results", lambda run_id, results: captured.setdefault("results", results))
    monkeypatch.setattr(tool_execution_pipeline, "write_verification", lambda run_id, verification: captured.setdefault("verification", verification))
    monkeypatch.setattr(tool_execution_pipeline, "write_purified_summary", lambda run_id, results, verification: captured.setdefault("summary", True))
    monkeypatch.setattr(tool_execution_pipeline, "write_evidence_bundle", lambda *args, **kwargs: captured.setdefault("evidence", True))
    monkeypatch.setattr(tool_execution_pipeline, "write_ai_verification", lambda run_id, report: captured.setdefault("ai_report", report))
    monkeypatch.setattr(
        tool_execution_pipeline,
        "verify_search_results_ai",
        lambda raw_question, results, verification, model=None: {"ok": True, "report": {"score": 1}},
    )
    monkeypatch.setenv("OPENVIBECODING_SEARCH_VERIFY_AI", "1")

    result = tool_execution_pipeline.run_search_pipeline(
        run_id="run-2",
        tool_runner=_ToolRunner(),
        store=store,
        request={
            "queries": ["alpha"],
            "providers": ["chatgpt", "grok"],
            "repeat": 1,
            "parallel": 1,
            "verify": {"providers": ["grok"], "repeat": 0},
            "verify_ai": {"enabled": True, "model": "mock-model"},
            "freshness_days": 3,
        },
        requested_by={"role": "SEARCHER", "agent_id": "a-2"},
    )

    assert result["ok"] is True
    assert captured.get("results")
    assert captured.get("verification")
    assert captured.get("evidence") is True
    assert captured.get("ai_report") == {"score": 1}
    assert captured["verification"]["policy_adjustments"]["repeat"] == {"from": 1, "to": 2}
    assert captured["verification"]["policy_adjustments"]["parallel"] == {"from": 1, "to": 2}
    assert captured["verification"]["policy_adjustments"]["verify_repeat"] == {"from": 0, "to": 1}


def test_run_search_pipeline_ai_disabled_and_failure_paths(tmp_path: Path, monkeypatch) -> None:
    store = _Store(tmp_path)

    monkeypatch.setattr(tool_execution_pipeline, "write_search_results", lambda *args, **kwargs: None)
    monkeypatch.setattr(tool_execution_pipeline, "write_verification", lambda *args, **kwargs: None)
    monkeypatch.setattr(tool_execution_pipeline, "write_purified_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr(tool_execution_pipeline, "write_evidence_bundle", lambda *args, **kwargs: None)

    def _should_not_call(*args, **kwargs):  # pragma: no cover - assertion helper
        raise AssertionError("verify_search_results_ai should not be called when verify_ai.enabled=false")

    monkeypatch.setattr(tool_execution_pipeline, "verify_search_results_ai", _should_not_call)
    monkeypatch.setenv("OPENVIBECODING_SEARCH_VERIFY_AI", "1")

    result = tool_execution_pipeline.run_search_pipeline(
        run_id="run-3",
        tool_runner=_ToolRunner(fail_provider="grok_web"),
        store=store,
        request={
            "queries": ["beta"],
            "providers": ["chatgpt_web", "grok_web"],
            "repeat": 2,
            "parallel": 2,
            "verify": {"providers": ["chatgpt_web"], "repeat": 1},
            "verify_ai": {"enabled": False},
        },
        requested_by={"role": "SEARCHER", "agent_id": "a-3"},
    )

    assert result["ok"] is False
    assert result["failures"]


def test_run_search_pipeline_topic_brief_defaults_to_browser_public_source_chain(
    tmp_path: Path, monkeypatch
) -> None:
    store = _Store(tmp_path)
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        tool_execution_pipeline,
        "write_search_results",
        lambda run_id, results: captured.setdefault("results", results),
    )
    monkeypatch.setattr(
        tool_execution_pipeline,
        "write_verification",
        lambda run_id, verification: captured.setdefault("verification", verification),
    )
    monkeypatch.setattr(tool_execution_pipeline, "write_purified_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr(tool_execution_pipeline, "write_evidence_bundle", lambda *args, **kwargs: None)

    result = tool_execution_pipeline.run_search_pipeline(
        run_id="run-topic-brief-browser",
        tool_runner=_ToolRunner(),
        store=store,
        request={
            "task_template": "topic_brief",
            "queries": ["Seattle AI"],
            "providers": ["browser"],
            "repeat": 1,
            "parallel": 1,
            "verify": {"repeat": 0},
        },
        requested_by={"role": "SEARCHER", "agent_id": "topic-brief-check"},
    )

    assert result["ok"] is True
    assert captured["verification"]["providers"] == {"browser_ddg": 2}
    assert captured["verification"]["verification_runs"] == 1
    assert captured["verification"]["public_source_receipt_missing"] is False
    assert captured["verification"]["policy_adjustments"]["repeat"] == {"from": 1, "to": 2}
    assert captured["verification"]["policy_adjustments"]["parallel"] == {"from": 1, "to": 2}
    assert captured["verification"]["policy_adjustments"]["verify_repeat"] == {"from": 0, "to": 1}
    assert "verify_providers" not in captured["verification"]["policy_adjustments"]


def test_run_sampling_requests_gate_and_sampling_outcomes(tmp_path: Path, monkeypatch) -> None:
    store = _Store(tmp_path)

    class _GateFailRunner(_ToolRunner):
        def run_mcp(self, _tool: str, _payload: dict[str, Any]) -> dict[str, Any]:
            return {"ok": False, "error": "gate denied"}

    gate_fail = tool_execution_pipeline.run_sampling_requests(
        run_id="run-4",
        tool_runner=_GateFailRunner(),
        store=store,
        request={"requests": [{"input": "x", "model": "m"}]},
    )
    assert gate_fail["ok"] is False
    assert gate_fail["results"][0]["error"] == "gate denied"

    monkeypatch.setattr("tooling.mcp.sampling_runner.run_sampling", lambda payload: {"ok": False, "error": "sample fail"})
    sample_fail = tool_execution_pipeline.run_sampling_requests(
        run_id="run-5",
        tool_runner=_ToolRunner(),
        store=store,
        request={"requests": [{"input": "y", "model": "m"}]},
    )
    assert sample_fail["ok"] is False
    assert sample_fail["results"][0]["error"] == "sample fail"

    monkeypatch.setattr("tooling.mcp.sampling_runner.run_sampling", lambda payload: {"ok": True, "output": payload["input"]})
    sample_ok = tool_execution_pipeline.run_sampling_requests(
        run_id="run-6",
        tool_runner=_ToolRunner(),
        store=store,
        request={"requests": [{"input": "a", "model": "m"}, {"input": "b", "model": "m"}]},
    )
    assert sample_ok["ok"] is True
    assert sample_ok["count"] == 2
    artifact = Path(sample_ok["artifact"])
    assert artifact.exists()
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["count"] == 2


def test_run_sampling_requests_adapter_tool_success_and_failure(tmp_path: Path) -> None:
    store = _Store(tmp_path)

    class _AdapterRunner(_ToolRunner):
        def __init__(self, fail_tool: str | None = None) -> None:
            super().__init__()
            self.fail_tool = fail_tool
            self.calls: list[dict[str, Any]] = []

        def run_mcp(self, tool: str, payload: dict[str, Any]) -> dict[str, Any]:
            self.calls.append({"tool": tool, "payload": payload})
            if tool == self.fail_tool:
                return {"ok": False, "tool": tool, "error": f"{tool} failed", "reason": "adapter execution failed"}
            return {"ok": True, "tool": tool, "output": payload.get("input")}

    adapter_ok_runner = _AdapterRunner()
    adapter_ok = tool_execution_pipeline.run_sampling_requests(
        run_id="run-6-adapter-ok",
        tool_runner=adapter_ok_runner,
        store=store,
        request={"requests": [{"tool": "aider", "payload": {"input": "adapter-call"}}]},
    )
    assert adapter_ok["ok"] is True
    assert adapter_ok["count"] == 1
    assert adapter_ok["results"][0]["tool"] == "aider"
    assert adapter_ok_runner.calls[0]["tool"] == "aider"

    adapter_fail_runner = _AdapterRunner(fail_tool="continue")
    adapter_fail = tool_execution_pipeline.run_sampling_requests(
        run_id="run-6-adapter-fail",
        tool_runner=adapter_fail_runner,
        store=store,
        request={"requests": [{"tool": "continue", "payload": {"input": "adapter-call"}}]},
    )
    assert adapter_fail["ok"] is False
    assert adapter_fail["count"] == 1
    assert adapter_fail["results"][0]["tool"] == "continue"
    assert adapter_fail["results"][0]["error"] == "continue failed"


def test_append_browser_results_handles_invalid_and_non_dict_history(tmp_path: Path) -> None:
    store = _Store(tmp_path)
    run_id = "run-7"
    artifacts_dir = store._run_dir(run_id) / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    history_file = artifacts_dir / "browser_results.json"

    # invalid json path -> except branch
    history_file.write_text("{", encoding="utf-8")
    out1 = tool_execution_pipeline.append_browser_results(
        store=store,
        run_id=run_id,
        summary={"tasks": 1},
        now_ts=lambda: "2026-02-08T00:00:00Z",
    )
    payload1 = json.loads(out1.read_text(encoding="utf-8"))
    assert len(payload1["entries"]) == 1

    # non-dict json path -> convert to history data wrapper branch
    history_file.write_text(json.dumps(["legacy-item"]), encoding="utf-8")
    out2 = tool_execution_pipeline.append_browser_results(
        store=store,
        run_id=run_id,
        summary={"tasks": 2},
        now_ts=lambda: "2026-02-08T00:00:01Z",
    )
    payload2 = json.loads(out2.read_text(encoding="utf-8"))
    assert payload2["entries"][0] == {"data": ["legacy-item"]}


def test_run_browser_and_tamper_tasks_integration(tmp_path: Path) -> None:
    store = _Store(tmp_path)

    browser_result = tool_execution_pipeline.run_browser_tasks(
        run_id="run-8",
        tool_runner=_ToolRunner(),
        store=store,
        request={"tasks": [{"url": "https://example.com", "script": ""}], "headless": True},
        now_ts=lambda: "2026-02-08T00:00:02Z",
    )
    assert browser_result["ok"] is True
    assert browser_result["tasks"] == 1
    assert any(event.get("event") == "BROWSER_RESULTS" for event in store.events)

    def _ok_tamper(*args, **kwargs):
        return {"ok": True, "execution": {"step": "ok"}}

    tamper_ok = tool_execution_pipeline.run_tampermonkey_tasks(
        run_id="run-9",
        request={"tasks": [{"script": "a", "raw_output": "b"}]},
        store=store,
        run_tampermonkey_fn=_ok_tamper,
    )
    assert tamper_ok["ok"] is True

    def _fail_tamper(*args, **kwargs):
        return {"ok": False, "error": "failed"}

    tamper_fail = tool_execution_pipeline.run_tampermonkey_tasks(
        run_id="run-10",
        request={"tasks": [{"script": "a", "raw_output": "b"}]},
        store=store,
        run_tampermonkey_fn=_fail_tamper,
    )
    assert tamper_fail["ok"] is False

    def _raise_tamper(*args, **kwargs):
        raise RuntimeError("boom")

    tamper_exc = tool_execution_pipeline.run_tampermonkey_tasks(
        run_id="run-11",
        request={"tasks": [{"script": "a", "raw_output": "b"}]},
        store=store,
        run_tampermonkey_fn=_raise_tamper,
    )
    assert tamper_exc["ok"] is False
    assert any(event.get("event") == "TAMPERMONKEY_FAILURE" for event in store.events)


def test_run_browser_tasks_policy_resolver_applies(tmp_path: Path) -> None:
    store = _Store(tmp_path)
    result = tool_execution_pipeline.run_browser_tasks(
        run_id="run-policy-browser",
        tool_runner=_ToolRunner(),
        store=store,
        request={
            "tasks": [
                {
                    "url": "https://example.com",
                    "script": "",
                    "browser_policy": {
                        "stealth_mode": "plugin",
                        "human_behavior": {"enabled": True, "level": "high"},
                        "profile_mode": "allow_profile",
                    },
                }
            ],
            "headless": True,
        },
        now_ts=lambda: "2026-02-09T00:00:00Z",
        contract_policy={
            "profile_mode": "ephemeral",
            "stealth_mode": "none",
            "human_behavior": {"enabled": False, "level": "low"},
        },
        requested_by={"role": "SEARCHER", "agent_id": "a-1"},
    )
    assert result["ok"] is True
    artifact = tmp_path / "run-policy-browser" / "artifacts" / "browser_results.json"
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    policy_audit = payload["latest"]["summary"]["results"][0]["policy_audit"]
    assert policy_audit["effective_policy"]["stealth_mode"] == "plugin"
    assert policy_audit["effective_policy"]["profile_mode"] == "ephemeral"


def test_run_tamper_tasks_passes_effective_policy(tmp_path: Path) -> None:
    store = _Store(tmp_path)
    captured: dict[str, Any] = {}

    def _capture_tamper(*args, **kwargs):
        captured["browser_policy"] = kwargs.get("browser_policy")
        return {"ok": True, "execution": {"captured": True}}

    result = tool_execution_pipeline.run_tampermonkey_tasks(
        run_id="run-policy-tamper",
        request={
            "tasks": [
                {
                    "script": "s",
                    "raw_output": "o",
                    "browser_policy": {
                        "stealth_mode": "lite",
                        "human_behavior": {"enabled": True, "level": "medium"},
                    },
                }
            ]
        },
        store=store,
        run_tampermonkey_fn=_capture_tamper,
        contract_policy={
            "profile_mode": "ephemeral",
            "stealth_mode": "none",
            "human_behavior": {"enabled": False, "level": "low"},
        },
        requested_by={"role": "SEARCHER", "agent_id": "a-2"},
    )
    assert result["ok"] is True
    assert captured["browser_policy"]["stealth_mode"] == "lite"
    assert captured["browser_policy"]["human_behavior"]["level"] == "medium"
