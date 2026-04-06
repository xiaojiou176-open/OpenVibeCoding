import json
from pathlib import Path

from cortexpilot_orch.scheduler.tool_execution_pipeline import run_browser_tasks, run_search_pipeline
from cortexpilot_orch.runners.tool_runner import ToolRunner
from cortexpilot_orch.store.run_store import RunStore
from cortexpilot_orch.api import search_payload_helpers
from cortexpilot_orch.planning import intake
from tooling.page_brief_pipeline import DEFAULT_PAGE_BRIEF_FOCUS, build_page_brief_result
from tooling import search_pipeline


def test_news_digest_intake_builds_contract_artifact(monkeypatch, tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runtime_root / "runs"))

    service = intake.IntakeService()
    payload = {
        "objective": "Create a digest",
        "allowed_paths": ["apps/dashboard"],
        "task_template": "news_digest",
        "template_payload": {
            "topic": "Seattle AI",
            "sources": ["theverge.com", "techcrunch.com"],
            "time_range": "24h",
            "max_results": 4,
        },
        "browser_policy_preset": "safe",
        "requester_role": "PM",
    }

    response = service.create(payload)
    assert response["task_template"] == "news_digest"
    assert response["template_payload"]["topic"] == "Seattle AI"

    monkeypatch.setattr(
        intake,
        "compile_plan",
        lambda _plan: {
            "task_id": "task-news",
            "inputs": {"artifacts": []},
            "owner_agent": {"role": "PM", "agent_id": "pm-1"},
            "assigned_agent": {"role": "TECH_LEAD", "agent_id": "tl-1"},
        },
    )
    service._store.write_response(
        response["intake_id"],
        {
            "intake_id": response["intake_id"],
            "status": "READY",
            "questions": [],
            "plan": {"plan_id": "p", "task_id": "task-news"},
        },
    )
    contract = service.build_contract(response["intake_id"])
    assert contract is not None
    assert contract["task_template"] == "news_digest"
    assert contract["template_payload"]["sources"] == ["theverge.com", "techcrunch.com"]
    assert contract["owner_agent"]["role"] == "TECH_LEAD"
    assert contract["assigned_agent"]["role"] == "SEARCHER"
    assert contract["tool_permissions"]["network"] == "allow"
    assert "search" in contract["tool_permissions"]["mcp_tools"]
    assert "search" in contract["mcp_tool_set"]
    artifacts = contract["inputs"]["artifacts"]
    search_artifact = next(item for item in artifacts if item["name"] == "search_requests.json")
    payload_path = Path(search_artifact["uri"])
    request_payload = json.loads(payload_path.read_text(encoding="utf-8"))
    assert request_payload["task_template"] == "news_digest"
    assert request_payload["template_payload"]["time_range"] == "24h"
    assert request_payload["queries"] == ["Seattle AI site:theverge.com", "Seattle AI site:techcrunch.com"]


def test_news_digest_result_builder_and_search_payload() -> None:
    search_request = {
        "task_template": "news_digest",
        "template_payload": {
            "topic": "Seattle AI",
            "sources": ["theverge.com"],
            "time_range": "7d",
            "max_results": 3,
        },
    }
    results = [
        {
            "provider": "browser_ddg",
            "results": [
                {"title": "Title A", "href": "https://www.theverge.com/a", "snippet": "Snippet A"},
                {"title": "Title B", "href": "https://www.theverge.com/b", "snippet": "Snippet B"},
            ],
        }
    ]
    digest = search_pipeline.build_news_digest_result(search_request, results)
    assert digest is not None
    assert digest["status"] == "SUCCESS"
    assert digest["topic"] == "Seattle AI"
    assert len(digest["sources"]) == 2

    payload = search_payload_helpers.build_search_payload(
        "run-news",
        read_artifact_fn=lambda _run_id, name: None,
        read_report_fn=lambda _run_id, name: {"name": name} if name == "news_digest_result.json" else None,
    )
    assert payload["news_digest_result"] == {"name": "news_digest_result.json"}


def test_topic_brief_intake_and_result_builder() -> None:
    payload = {
        "objective": "Create a topic brief",
        "allowed_paths": ["apps/dashboard"],
        "task_template": "topic_brief",
        "template_payload": {
            "topic": "Seattle AI",
            "time_range": "7d",
            "max_results": 2,
        },
    }
    normalized = intake._apply_task_template_defaults(payload)
    assert normalized["task_template"] == "topic_brief"
    assert normalized["search_queries"] == ["Seattle AI"]

    search_request = {
        "task_template": "topic_brief",
        "template_payload": {
            "topic": "Seattle AI",
            "time_range": "7d",
            "max_results": 2,
        },
    }
    results = [
        {
            "provider": "browser_ddg",
            "results": [
                {"title": "Title A", "href": "https://example.com/a", "snippet": "Snippet A"},
                {"title": "Title B", "href": "https://example.com/b", "snippet": "Snippet B"},
            ],
        }
    ]
    brief = search_pipeline.build_topic_brief_result(search_request, results)
    assert brief is not None
    assert brief["task_template"] == "topic_brief"
    assert brief["status"] == "SUCCESS"
    assert brief["requested_sources"] == []

    search_payload = search_payload_helpers.build_search_payload(
        "run-topic-brief",
        read_artifact_fn=lambda _run_id, name: None,
        read_report_fn=lambda _run_id, name: {"name": name} if name == "topic_brief_result.json" else None,
    )
    assert search_payload["topic_brief_result"] == {"name": "topic_brief_result.json"}


def test_page_brief_intake_builds_browser_contract_artifact(monkeypatch, tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runtime_root / "runs"))

    service = intake.IntakeService()
    payload = {
        "objective": "Create a page brief",
        "allowed_paths": ["apps/dashboard"],
        "task_template": "page_brief",
        "template_payload": {
            "url": "https://example.com",
        },
        "browser_policy_preset": "safe",
        "requester_role": "PM",
    }

    response = service.create(payload)
    assert response["task_template"] == "page_brief"
    assert response["template_payload"]["focus"] == DEFAULT_PAGE_BRIEF_FOCUS

    monkeypatch.setattr(
        intake,
        "compile_plan",
        lambda _plan: {
            "task_id": "task-page-brief",
            "inputs": {"artifacts": []},
            "owner_agent": {"role": "PM", "agent_id": "pm-1"},
            "assigned_agent": {"role": "TECH_LEAD", "agent_id": "tl-1"},
        },
    )
    service._store.write_response(
        response["intake_id"],
        {
            "intake_id": response["intake_id"],
            "status": "READY",
            "questions": [],
            "plan": {"plan_id": "p", "task_id": "task-page-brief"},
        },
    )
    contract = service.build_contract(response["intake_id"])
    assert contract is not None
    assert contract["task_template"] == "page_brief"
    artifacts = contract["inputs"]["artifacts"]
    browser_artifact = next(item for item in artifacts if item["name"] == "browser_requests.json")
    payload_path = Path(browser_artifact["uri"])
    request_payload = json.loads(payload_path.read_text(encoding="utf-8"))
    assert request_payload["task_template"] == "page_brief"
    assert request_payload["template_payload"]["url"] == "https://example.com"
    assert request_payload["tasks"][0]["url"] == "https://example.com"


def test_page_brief_result_builder_and_browser_payload() -> None:
    request = {
        "task_template": "page_brief",
        "template_payload": {
            "url": "https://example.com",
            "focus": "Summarize the landing page",
        },
    }
    browser_result = {
        "ok": True,
        "url": "https://example.com",
        "result": {
            "url": "https://example.com/",
            "title": "Example Domain",
            "meta_description": "Example Domain is used in illustrative examples in documents.",
            "headings": ["Example Domain"],
            "paragraphs": ["This domain is for use in illustrative examples in documents."],
            "list_items": ["You may use this domain in literature without prior coordination."],
            "body_excerpt": "Example Domain This domain is for use in illustrative examples in documents.",
        },
        "artifacts": {
            "screenshot": "artifacts/browser/example.png",
        },
    }

    brief = build_page_brief_result(request, browser_result)
    assert brief is not None
    assert brief["task_template"] == "page_brief"
    assert brief["status"] == "SUCCESS"
    assert brief["resolved_url"] == "https://example.com/"
    assert brief["page_title"] == "Example Domain"
    assert brief["screenshot_artifact"] == "artifacts/browser/example.png"

    payload = search_payload_helpers.build_search_payload(
        "run-page-brief",
        read_artifact_fn=lambda _run_id, name: {"name": name} if name == "browser_results.json" else None,
        read_report_fn=lambda _run_id, name: {"name": name} if name == "page_brief_result.json" else None,
    )
    assert payload["browser_results"] == {"name": "browser_results.json"}
    assert payload["page_brief_result"] == {"name": "page_brief_result.json"}


def test_page_brief_browser_task_writes_failed_report(monkeypatch, tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runtime_root / "runs"))

    store = RunStore()
    run_id = store.create_run("page-brief-failure")

    class FailingBrowserToolRunner(ToolRunner):
        def __init__(self) -> None:
            super().__init__(run_id=run_id, store=store)

        def run_browser(self, url: str, script_content: str, task_id=None, headless=None, browser_policy=None, policy_audit=None) -> dict:
            return {
                "ok": False,
                "url": url,
                "error": "navigation timeout",
                "artifacts": {"error": "artifacts/browser/error.txt"},
            }

    result = run_browser_tasks(
        run_id,
        FailingBrowserToolRunner(),
        store,
        {
            "task_template": "page_brief",
            "template_payload": {
                "url": "https://example.com",
                "focus": DEFAULT_PAGE_BRIEF_FOCUS,
            },
            "tasks": [{"url": "https://example.com", "script": "() => ({})"}],
        },
        intake._now_ts,
    )
    assert result["ok"] is False
    report_path = runtime_root / "runs" / run_id / "reports" / "page_brief_result.json"
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "FAILED"
    assert "页面抓取失败" in report["failure_reason_zh"]


def test_news_digest_result_writes_failed_report_when_search_pipeline_fails(monkeypatch, tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runtime_root / "runs"))

    store = RunStore()
    run_id = store.create_run("news-digest-failure")

    class FailingToolRunner(ToolRunner):
        def __init__(self) -> None:
            super().__init__(run_id=run_id, store=store)

        def run_search(self, query: str, provider: str | None = None, browser_policy=None, policy_audit=None) -> dict:
            return {
                "ok": False if provider == "grok_web" else True,
                "provider": provider,
                "results": [{"title": f"{query}-{provider}", "href": f"https://example.com/{provider}"}],
            }

    request = {
        "queries": ["Seattle AI site:theverge.com"],
        "providers": ["chatgpt_web", "grok_web"],
        "verify": {"providers": ["chatgpt_web"], "repeat": 1},
        "task_template": "news_digest",
        "template_payload": {
            "topic": "Seattle AI",
            "sources": ["theverge.com"],
            "time_range": "24h",
            "max_results": 3,
        },
    }

    result = run_search_pipeline(
        run_id,
        FailingToolRunner(),
        store,
        request,
        requested_by={"role": "PM", "agent_id": "pm-1"},
    )
    assert result["ok"] is False
    run_dir = runtime_root / "runs" / run_id / "reports"
    digest_path = run_dir / "news_digest_result.json"
    assert digest_path.exists()
    digest_payload = json.loads(digest_path.read_text(encoding="utf-8"))
    assert digest_payload["status"] == "FAILED"
    assert "来源链路失败" in digest_payload["failure_reason_zh"]
