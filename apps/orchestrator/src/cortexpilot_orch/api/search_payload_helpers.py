from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

_ReadArtifactFn = Callable[[str, str], object | None]
_ReadReportFn = Callable[[str, str], object | None]


def extract_search_queries(contract: dict) -> list[str]:
    inputs = contract.get("inputs") if isinstance(contract, dict) else {}
    artifacts = inputs.get("artifacts") if isinstance(inputs, dict) else []
    if not isinstance(artifacts, list):
        return []
    for item in artifacts:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if name not in {"search_requests.json", "search_queries.json"}:
            continue
        uri = item.get("uri")
        if not isinstance(uri, str) or not uri.strip():
            continue
        path = Path(uri)
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, list):
            return [str(q).strip() for q in payload if str(q).strip()]
        if isinstance(payload, dict):
            raw = payload.get("queries") or payload.get("query") or []
            if isinstance(raw, str):
                raw = [raw]
            if isinstance(raw, list):
                return [str(q).strip() for q in raw if str(q).strip()]
    return []


def build_search_payload(
    run_id: str,
    *,
    read_artifact_fn: _ReadArtifactFn,
    read_report_fn: _ReadReportFn,
) -> dict[str, object | None]:
    return {
        "run_id": run_id,
        "raw": read_artifact_fn(run_id, "search_results.json"),
        "raw_history": read_artifact_fn(run_id, "search_results.jsonl"),
        "verification": read_artifact_fn(run_id, "verification.json"),
        "verification_history": read_artifact_fn(run_id, "verification.jsonl"),
        "purified": read_artifact_fn(run_id, "purified_summary.json"),
        "search_summary": read_artifact_fn(run_id, "search_summary.json"),
        "verification_ai": read_artifact_fn(run_id, "verification_ai.json"),
        "browser_results": read_artifact_fn(run_id, "browser_results.json"),
        "news_digest_result": read_report_fn(run_id, "news_digest_result.json"),
        "topic_brief_result": read_report_fn(run_id, "topic_brief_result.json"),
        "page_brief_result": read_report_fn(run_id, "page_brief_result.json"),
        "evidence_bundle": read_report_fn(run_id, "evidence_bundle.json"),
    }
