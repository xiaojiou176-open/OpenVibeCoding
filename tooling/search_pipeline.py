from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cortexpilot_orch.store.run_store import RunStore
from cortexpilot_orch.contract.validator import ContractValidator


def _now_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _append_jsonl(store: RunStore, run_id: str, filename: str, entry: dict) -> Path:
    return store.append_artifact_jsonl(run_id, filename, entry)


def _write_latest(store: RunStore, run_id: str, filename: str, entry: dict) -> Path:
    payload = {"latest": entry}
    return store.write_artifact(
        run_id,
        filename,
        json.dumps(payload, ensure_ascii=False, indent=2),
    )


def _domain_from_href(href: str) -> str:
    if not isinstance(href, str) or not href.strip():
        return ""
    try:
        from urllib.parse import urlparse
        return urlparse(href).netloc
    except Exception:  # noqa: BLE001
        return ""


def _build_sources(results: list[dict]) -> list[dict]:
    sources: list[dict] = []
    retrieved_at = _now_ts()
    for item in results:
        if not isinstance(item, dict):
            continue
        hits = item.get("results") if isinstance(item.get("results"), list) else []
        for hit in hits:
            if not isinstance(hit, dict):
                continue
            title = str(hit.get("title") or hit.get("name") or hit.get("href") or "").strip()
            href = str(hit.get("href") or "").strip()
            if not title and not href:
                continue
            publisher = _domain_from_href(href)
            sources.append(
                {
                    "source_id": uuid.uuid4().hex,
                    "kind": "webpage",
                    "title": title or href or "untitled",
                    "url": href,
                    "retrieved_at": retrieved_at,
                    "publisher": publisher,
                    "content_sha256": _sha256_text(href or title or "source"),
                }
            )
    if not sources:
        sources.append(
            {
                "source_id": uuid.uuid4().hex,
                "kind": "other",
                "title": "search results missing",
                "url": "",
                "retrieved_at": retrieved_at,
                "publisher": "",
                "content_sha256": _sha256_text("empty"),
                "notes": "no results captured",
            }
        )
    return sources


def _purify_results(results: list[dict], verification: dict | None = None) -> dict:
    domain_counts: dict[str, int] = {}
    provider_counts: dict[str, int] = {}
    top_results: list[dict] = []
    missing_href = 0
    for item in results:
        if not isinstance(item, dict):
            continue
        provider = (
            item.get("provider")
            or item.get("resolved_provider")
            or item.get("mode")
            or "unknown"
        )
        provider_counts[str(provider)] = provider_counts.get(str(provider), 0) + 1
        hits = item.get("results") if isinstance(item.get("results"), list) else []
        if hits:
            first = hits[0]
            if isinstance(first, dict):
                top_results.append(
                    {
                        "provider": str(provider),
                        "title": str(first.get("title", "")),
                        "href": str(first.get("href", "")),
                    }
                )
        for hit in hits:
            if not isinstance(hit, dict):
                continue
            href = hit.get("href", "")
            if not href:
                missing_href += 1
                continue
            domain = _domain_from_href(str(href))
            if domain:
                domain_counts[domain] = domain_counts.get(domain, 0) + 1
    consensus_domains = [domain for domain, count in domain_counts.items() if count >= 2]
    divergent_domains = [domain for domain, count in domain_counts.items() if count == 1]
    return {
        "total_runs": len(results),
        "provider_counts": provider_counts,
        "domain_counts": domain_counts,
        "consensus_domains": consensus_domains,
        "divergent_domains": divergent_domains,
        "top_results": top_results,
        "missing_href_count": missing_href,
        "verification": verification or {},
    }


def _build_claims(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for idx, source in enumerate(sources):
        source_id = source.get("source_id", f"src-{idx}")
        title = str(source.get("title") or source.get("url") or "source").strip()
        if not title:
            title = "source"
        claims.append(
            {
                "claim_id": f"claim-{idx}",
                "text": title,
                "status": "UNVERIFIED",
                "confidence": 0.3,
                "supporting_source_ids": [source_id],
                "contradicting_source_ids": [],
                "verification_notes": "auto-generated",
                "risk_if_wrong": "LOW",
            }
        )
    return claims


def _build_consensus(summary: dict[str, Any]) -> dict[str, Any]:
    agreements = [
        f"multiple sources referenced {domain}"
        for domain in summary.get("consensus_domains", [])
    ]
    disagreements = [
        f"single-source domain {domain}"
        for domain in summary.get("divergent_domains", [])
    ]
    needs_verification: list[str] = []
    missing = summary.get("missing_href_count", 0)
    if isinstance(missing, int) and missing > 0:
        needs_verification.append("some results missing href")
    if not agreements:
        needs_verification.append("no consensus domains identified")
    return {
        "agreements": agreements,
        "disagreements": disagreements,
        "needs_verification": needs_verification,
    }


def build_evidence_bundle(
    raw_question: str,
    refined_prompt: str,
    results: list[dict],
    requested_by: dict | None = None,
    freshness_requirement_days: int | None = None,
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    query: dict[str, Any] = {"raw_question": raw_question, "refined_prompt": refined_prompt}
    if isinstance(freshness_requirement_days, int) and freshness_requirement_days >= 0:
        query["freshness_requirement_days"] = freshness_requirement_days
    requested = _sanitize_requested_by(requested_by)
    sources = _build_sources(results)
    summary = _purify_results(results)
    bundle = {
        "bundle_id": uuid.uuid4().hex,
        "created_at": _now_ts(),
        "requested_by": requested,
        "query": query,
        "sources": sources,
        "claims": _build_claims(sources),
        "consensus": _build_consensus(summary),
        "limitations": limitations or ["auto-generated evidence bundle"],
    }
    validator = ContractValidator()
    validator.validate_report(bundle, "evidence_bundle.v1.json")
    return bundle


def write_evidence_bundle(
    run_id: str,
    raw_question: str,
    refined_prompt: str,
    results: list[dict],
    requested_by: dict | None = None,
    freshness_requirement_days: int | None = None,
    limitations: list[str] | None = None,
    store: RunStore | None = None,
) -> Path:
    store = store or RunStore()
    bundle = build_evidence_bundle(
        raw_question=raw_question,
        refined_prompt=refined_prompt,
        results=results,
        requested_by=requested_by,
        freshness_requirement_days=freshness_requirement_days,
        limitations=limitations,
    )
    return store.write_report(run_id, "evidence_bundle", bundle)


def _build_digest_result(
    *,
    task_template: str,
    topic: str,
    time_range: str,
    requested_sources: list[str],
    max_results: int,
    results: list[dict[str, Any]],
    status_override: str | None = None,
    failure_reason_zh: str | None = None,
) -> dict[str, Any]:
    digest_sources: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for provider_entry in results:
        if not isinstance(provider_entry, dict):
            continue
        provider = str(
            provider_entry.get("provider")
            or provider_entry.get("resolved_provider")
            or provider_entry.get("mode")
            or "unknown"
        ).strip()
        hits = provider_entry.get("results") if isinstance(provider_entry.get("results"), list) else []
        for hit in hits:
            if not isinstance(hit, dict):
                continue
            href = str(hit.get("href") or "").strip()
            if href and href in seen_urls:
                continue
            if href:
                seen_urls.add(href)
            digest_sources.append(
                {
                    "title": str(hit.get("title") or hit.get("name") or href or "result").strip() or "result",
                    "url": href,
                    "publisher": _domain_from_href(href),
                    "provider": provider,
                    "snippet": str(hit.get("snippet") or hit.get("summary") or "").strip(),
                }
            )
            if len(digest_sources) >= max_results:
                break
        if len(digest_sources) >= max_results:
            break

    normalized_status = str(status_override or "").strip().upper()
    template_label = "资讯摘要" if task_template == "news_digest" else "主题简报"

    if normalized_status == "FAILED":
        summary = (
            f"“{topic}”{template_label}未能完成。"
            f" {failure_reason_zh or '检索链路未通过，请查看高级证据获取详细失败上下文。'}"
        ).strip()
        status = "FAILED"
    elif digest_sources:
        preview = "、".join(item["title"] for item in digest_sources[:3])
        summary = (
            f"已围绕“{topic}”汇总 {len(digest_sources)} 条公开来源，覆盖最近 {time_range} 的检索结果。"
            f" 当前优先可读来源包括：{preview}。"
        )
        status = "SUCCESS"
        failure_reason_zh = None
    else:
        summary = f"未检索到与“{topic}”相关的公开来源结果，请稍后重试或调整检索范围。"
        status = "EMPTY"
        failure_reason_zh = failure_reason_zh or "未检索到公开来源结果"

    return {
        "task_template": task_template,
        "generated_at": _now_ts(),
        "status": status,
        "topic": topic,
        "time_range": time_range,
        "requested_sources": requested_sources,
        "max_results": max_results,
        "summary": summary,
        "sources": digest_sources,
        "evidence_refs": {
            "raw": "artifacts/search_results.json",
            "purified": "artifacts/purified_summary.json",
            "verification": "artifacts/verification.json",
            "evidence_bundle": "reports/evidence_bundle.json",
        },
        "failure_reason_zh": failure_reason_zh,
    }


def build_news_digest_result(
    search_request: dict[str, Any],
    results: list[dict[str, Any]],
    *,
    status_override: str | None = None,
    failure_reason_zh: str | None = None,
) -> dict[str, Any] | None:
    if str(search_request.get("task_template") or "").strip().lower() != "news_digest":
        return None
    template_payload = search_request.get("template_payload")
    if not isinstance(template_payload, dict):
        return None

    topic = str(template_payload.get("topic") or "").strip()
    time_range = str(template_payload.get("time_range") or "24h").strip().lower() or "24h"
    requested_sources = [str(item).strip() for item in template_payload.get("sources", []) if str(item).strip()]
    try:
        max_results = int(template_payload.get("max_results", 5))
    except (TypeError, ValueError):
        max_results = 5
    max_results = max(1, min(max_results, 10))

    return _build_digest_result(
        task_template="news_digest",
        topic=topic,
        time_range=time_range,
        requested_sources=requested_sources,
        max_results=max_results,
        results=results,
        status_override=status_override,
        failure_reason_zh=failure_reason_zh,
    )


def build_topic_brief_result(
    search_request: dict[str, Any],
    results: list[dict[str, Any]],
    *,
    status_override: str | None = None,
    failure_reason_zh: str | None = None,
) -> dict[str, Any] | None:
    if str(search_request.get("task_template") or "").strip().lower() != "topic_brief":
        return None
    template_payload = search_request.get("template_payload")
    if not isinstance(template_payload, dict):
        return None

    topic = str(template_payload.get("topic") or "").strip()
    time_range = str(template_payload.get("time_range") or "24h").strip().lower() or "24h"
    try:
        max_results = int(template_payload.get("max_results", 5))
    except (TypeError, ValueError):
        max_results = 5
    max_results = max(1, min(max_results, 10))

    return _build_digest_result(
        task_template="topic_brief",
        topic=topic,
        time_range=time_range,
        requested_sources=[],
        max_results=max_results,
        results=results,
        status_override=status_override,
        failure_reason_zh=failure_reason_zh,
    )


def write_news_digest_result(
    run_id: str,
    search_request: dict[str, Any],
    results: list[dict[str, Any]],
    store: RunStore | None = None,
    *,
    status_override: str | None = None,
    failure_reason_zh: str | None = None,
) -> Path | None:
    payload = build_news_digest_result(
        search_request,
        results,
        status_override=status_override,
        failure_reason_zh=failure_reason_zh,
    )
    if payload is None:
        return None
    store = store or RunStore()
    return store.write_report(run_id, "news_digest_result", payload)


def write_topic_brief_result(
    run_id: str,
    search_request: dict[str, Any],
    results: list[dict[str, Any]],
    store: RunStore | None = None,
    *,
    status_override: str | None = None,
    failure_reason_zh: str | None = None,
) -> Path | None:
    payload = build_topic_brief_result(
        search_request,
        results,
        status_override=status_override,
        failure_reason_zh=failure_reason_zh,
    )
    if payload is None:
        return None
    store = store or RunStore()
    return store.write_report(run_id, "topic_brief_result", payload)


def _sanitize_requested_by(requested_by: dict | None) -> dict[str, str]:
    if not isinstance(requested_by, dict):
        return {"role": "ORCHESTRATOR", "agent_id": "search_pipeline"}
    role = str(requested_by.get("role", "")).strip()
    agent_id = str(requested_by.get("agent_id", "")).strip()
    allowed_roles = {"PM", "TECH_LEAD", "SEARCHER", "ORCHESTRATOR"}
    if role not in allowed_roles:
        role = "ORCHESTRATOR"
    if not agent_id:
        agent_id = "search_pipeline"
    return {"role": role, "agent_id": agent_id}


def _build_sources(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for idx, item in enumerate(results):
        if not isinstance(item, dict):
            continue
        provider = item.get("provider") or item.get("resolved_provider") or item.get("mode") or "unknown"
        hits = item.get("results") if isinstance(item.get("results"), list) else []
        source_id = f"src-{idx}"
        if hits:
            first = hits[0]
            if isinstance(first, dict):
                title = str(first.get("title") or provider or "search result")
                href = str(first.get("href") or "")
                sources.append(
                    {
                        "source_id": source_id,
                        "kind": "webpage" if href else "other",
                        "title": title,
                        "url": href or None,
                        "retrieved_at": _now_ts(),
                        "publisher": str(first.get("publisher") or ""),
                    }
                )
                continue
        sources.append(
            {
                "source_id": source_id,
                "kind": "other",
                "title": str(provider),
                "retrieved_at": _now_ts(),
            }
        )
    if not sources:
        sources.append(
            {
                "source_id": "src-0",
                "kind": "other",
                "title": "search results",
                "retrieved_at": _now_ts(),
            }
        )
    return sources


def write_search_results(run_id: str, results: list[dict], store: RunStore | None = None) -> Path:
    store = store or RunStore()
    entry = {
        "entry_id": uuid.uuid4().hex,
        "ts": _now_ts(),
        "results": results,
    }
    try:
        _append_jsonl(store, run_id, "search_results.jsonl", entry)
        path = _write_latest(store, run_id, "search_results.json", entry)
        store.append_event(run_id, {
            "level": "INFO",
            "event": "SEARCH_RESULTS",
            "run_id": run_id,
            "task_id": "",
            "context": {"ref": str(path)},
        })
    except Exception as exc:
        raise RuntimeError(f"search_results_write_failed: {exc}") from exc
    return path


def write_verification(run_id: str, verification: dict, store: RunStore | None = None) -> Path:
    store = store or RunStore()
    entry = {
        "entry_id": uuid.uuid4().hex,
        "ts": _now_ts(),
        "verification": verification,
    }
    try:
        _append_jsonl(store, run_id, "verification.jsonl", entry)
        path = _write_latest(store, run_id, "verification.json", entry)
        store.append_event(run_id, {
            "level": "INFO",
            "event": "SEARCH_VERIFICATION",
            "run_id": run_id,
            "task_id": "",
            "context": {"ref": str(path)},
        })
    except Exception as exc:
        raise RuntimeError(f"verification_write_failed: {exc}") from exc
    return path


def write_purified_summary(
    run_id: str,
    results: list[dict],
    verification: dict | None = None,
    store: RunStore | None = None,
) -> Path:
    store = store or RunStore()
    summary = _purify_results(results, verification or {})
    entry = {
        "entry_id": uuid.uuid4().hex,
        "ts": _now_ts(),
        "summary": summary,
    }
    try:
        _append_jsonl(store, run_id, "purified_summary.jsonl", entry)
        _write_latest(store, run_id, "purified_summary.json", entry)
        path = store.write_artifact(
            run_id,
            "search_summary.json",
            json.dumps({"latest": entry}, ensure_ascii=False, indent=2),
        )
        store.append_event(
            run_id,
            {
                "level": "INFO",
                "event": "SEARCH_PURIFIED",
                "run_id": run_id,
                "task_id": "",
                "context": {"ref": str(path)},
            },
        )
    except Exception as exc:
        raise RuntimeError(f"purified_summary_write_failed: {exc}") from exc
    return path


def write_ai_verification(run_id: str, report: dict, store: RunStore | None = None) -> Path:
    store = store or RunStore()
    entry = {
        "entry_id": uuid.uuid4().hex,
        "ts": _now_ts(),
        "report": report,
    }
    try:
        _append_jsonl(store, run_id, "verification_ai.jsonl", entry)
        path = _write_latest(store, run_id, "verification_ai.json", entry)
        store.append_event(
            run_id,
            {
                "level": "INFO",
                "event": "SEARCH_VERIFICATION_AI",
                "run_id": run_id,
                "task_id": "",
                "context": {"ref": str(path)},
            },
        )
    except Exception as exc:
        raise RuntimeError(f"verification_ai_write_failed: {exc}") from exc
    return path
