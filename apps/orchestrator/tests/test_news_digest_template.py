import json
from pathlib import Path

from openvibecoding_orch.scheduler.tool_execution_pipeline import run_browser_tasks, run_search_pipeline
from openvibecoding_orch.runners.tool_runner import ToolRunner
from openvibecoding_orch.store.run_store import RunStore
from openvibecoding_orch.api import search_payload_helpers
from openvibecoding_orch.planning import intake
from tooling.page_brief_pipeline import DEFAULT_PAGE_BRIEF_FOCUS, build_page_brief_result
from tooling import search_pipeline


def test_news_digest_intake_builds_contract_artifact(monkeypatch, tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runtime_root / "runs"))

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
    assert "handoff_chain" not in contract
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
    assert digest["summary"].startswith("Collected 2 public-source result(s)")
    assert "Title A, Title B." in digest["summary"]

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


def test_topic_brief_build_contract_writes_browser_provider_defaults(monkeypatch, tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runtime_root / "runs"))

    service = intake.IntakeService()
    payload = {
        "objective": "Create a topic brief",
        "allowed_paths": ["apps/dashboard"],
        "task_template": "topic_brief",
        "template_payload": {
            "topic": "Seattle AI",
            "time_range": "24h",
            "max_results": 3,
        },
        "requester_role": "PM",
    }

    response = service.create(payload)
    monkeypatch.setattr(
        intake,
        "compile_plan",
        lambda _plan: {
            "task_id": "task-topic-brief",
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
            "plan": {"plan_id": "p", "task_id": "task-topic-brief"},
        },
    )
    contract = service.build_contract(response["intake_id"])
    artifact = next(item for item in contract["inputs"]["artifacts"] if item["name"] == "search_requests.json")
    artifact_payload = json.loads(Path(artifact["uri"]).read_text(encoding="utf-8"))
    assert artifact_payload["task_template"] == "topic_brief"
    assert artifact_payload["providers"] == ["browser_ddg"]
    assert artifact_payload["verify"] == {"providers": ["browser_ddg"], "repeat": 1}


def test_topic_brief_fail_closes_when_only_provider_homepages_are_captured() -> None:
    search_request = {
        "task_template": "topic_brief",
        "template_payload": {
            "topic": "Seattle AI",
            "time_range": "24h",
            "max_results": 3,
        },
    }
    results = [
        {
            "provider": "gemini_web",
            "results": [
                {
                    "title": "gemini_web response",
                    "href": "https://gemini.google.com/",
                    "snippet": "Gemini 与 Gemini 对话 你说 Seattle AI",
                }
            ],
        },
        {
            "provider": "grok_web",
            "results": [
                {
                    "title": "grok_web response",
                    "href": "https://grok.com/",
                    "snippet": "登录 注册 Seattle AI",
                }
            ],
        },
    ]
    brief = search_pipeline.build_topic_brief_result(search_request, results)
    assert brief is not None
    assert brief["status"] == "FAILED"
    assert "provider outputs stayed on provider shell pages" in brief["summary"]
    assert "provider 壳页" in brief["failure_reason_zh"]


def test_page_brief_intake_builds_browser_contract_artifact(monkeypatch, tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runtime_root / "runs"))

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
        "mode": "playwright",
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
            "screenshot": "/tmp/run-page-brief/artifacts/browser/example.png",
            "source": "/tmp/run-page-brief/artifacts/browser/example.html",
        },
    }

    brief = build_page_brief_result(
        request,
        browser_result,
        requested_by={"role": "SEARCHER", "agent_id": "searcher-1"},
    )
    assert brief is not None
    assert brief["task_template"] == "page_brief"
    assert brief["status"] == "SUCCESS"
    assert brief["resolved_url"] == "https://example.com/"
    assert brief["page_title"] == "Example Domain"
    assert brief["capture_mode"] == "playwright"
    assert brief["screenshot_artifact"] == "artifacts/browser/example.png"
    assert brief["source_artifact"] == "artifacts/browser/example.html"
    assert brief["evidence_refs"]["browser_results"] == "artifacts/browser_results.json"
    assert brief["evidence_refs"]["browser_screenshot"] == "artifacts/browser/example.png"
    assert brief["evidence_refs"]["browser_source"] == "artifacts/browser/example.html"
    assert brief["evidence_refs"]["evidence_bundle"] == "reports/evidence_bundle.json"
    assert brief["requested_by"] == {"role": "SEARCHER", "agent_id": "searcher-1"}

    payload = search_payload_helpers.build_search_payload(
        "run-page-brief",
        read_artifact_fn=lambda _run_id, name: (
            {
                "latest": {
                    "summary": {
                        "results": [
                            {
                                "ok": True,
                                "mode": "playwright",
                                "url": "https://example.com/",
                                "artifacts": {
                                    "screenshot": "artifacts/browser/example.png",
                                    "source": "artifacts/browser/example.html",
                                },
                            }
                        ]
                    }
                }
            }
            if name == "browser_results.json"
            else None
        ),
        read_report_fn=lambda _run_id, name: brief if name == "page_brief_result.json" else None,
    )
    assert payload["browser_results"]["latest"]["summary"]["results"][0]["mode"] == "playwright"
    assert payload["page_brief_result"] == brief
    assert payload["evidence_bundle"] is None


def test_page_brief_browser_task_writes_failed_report(monkeypatch, tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runtime_root / "runs"))

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
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runtime_root / "runs"))

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
    assert digest_payload["summary"].startswith("The news digest for 'Seattle AI' did not complete successfully.")
    assert "来源链路失败" in digest_payload["failure_reason_zh"]


def test_topic_brief_run_search_pipeline_requires_browser_public_source_provider(monkeypatch, tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runtime_root / "runs"))

    store = RunStore()
    run_id = store.create_run("topic-brief-provider-homepage-only")

    class ProviderHomepageOnlyToolRunner(ToolRunner):
        def __init__(self) -> None:
            super().__init__(run_id=run_id, store=store)

        def run_search(self, query: str, provider: str | None = None, browser_policy=None, policy_audit=None) -> dict:
            normalized_provider = "gemini_web" if provider == "chatgpt_web" else str(provider or "")
            href = "https://gemini.google.com/" if normalized_provider == "gemini_web" else "https://grok.com/"
            return {
                "ok": True,
                "provider": normalized_provider,
                "results": [{"title": f"{normalized_provider} response", "href": href, "snippet": f"{query} provider shell"}],
                "verification": {"consistent": True},
            }

    request = {
        "queries": ["Seattle AI"],
        "providers": ["chatgpt_web", "grok_web"],
        "verify": {"providers": ["chatgpt_web"], "repeat": 1},
        "task_template": "topic_brief",
        "template_payload": {
            "topic": "Seattle AI",
            "time_range": "24h",
            "max_results": 3,
        },
    }

    result = run_search_pipeline(
        run_id,
        ProviderHomepageOnlyToolRunner(),
        store,
        request,
        requested_by={"role": "PM", "agent_id": "pm-1"},
    )
    assert result["ok"] is False
    assert result["reason"] == "missing required providers"
    assert result["missing"] == ["browser_ddg"]
