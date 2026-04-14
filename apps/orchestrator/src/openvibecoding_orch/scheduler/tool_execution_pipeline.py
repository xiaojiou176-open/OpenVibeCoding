from __future__ import annotations

import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from openvibecoding_orch.policy.browser_policy_resolver import resolve_browser_policy
from openvibecoding_orch.runners.tool_runner import ToolRunner
from openvibecoding_orch.store.run_store import RunStore
from tooling.page_brief_pipeline import write_page_brief_result
from tooling.search.ai_verifier import verify_search_results_ai
from tooling.search_pipeline import (
    write_ai_verification,
    write_evidence_bundle,
    write_news_digest_result,
    write_topic_brief_result,
    write_purified_summary,
    write_search_results,
    write_verification,
)
from tooling.tampermonkey.runner import run_tampermonkey


def _append_policy_events(store: RunStore, run_id: str, source: str, events: Any) -> None:
    if not isinstance(events, list):
        return
    for item in events:
        if not isinstance(item, dict):
            continue
        event_name = item.get("event")
        if not isinstance(event_name, str) or not event_name.strip():
            continue
        meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
        store.append_event(
            run_id,
            {
                "level": item.get("level", "INFO"),
                "event": event_name,
                "run_id": run_id,
                "meta": {"source": source, **meta},
            },
        )


def _policy_audit_compact(audit: dict[str, Any]) -> dict[str, Any]:
    return {
        "requested_policy": audit.get("requested_policy"),
        "effective_policy": audit.get("effective_policy"),
        "policy_source": audit.get("policy_source"),
        "fallback_chain": audit.get("fallback_chain", []),
    }


def _is_policy_kwargs_compat_error(exc: TypeError) -> bool:
    message = str(exc)
    if "unexpected keyword argument" not in message:
        return False
    return "browser_policy" in message or "policy_audit" in message


def _call_with_policy_kwargs_compat(
    fn: Callable[..., Any],
    /,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    fallback_kwargs: dict[str, Any],
) -> Any:
    try:
        return fn(*args, **kwargs)
    except TypeError as exc:
        if not _is_policy_kwargs_compat_error(exc):
            raise
        return fn(*args, **fallback_kwargs)


def _call_store_aware_writer(
    fn: Callable[..., Any],
    /,
    args: tuple[Any, ...],
    store: RunStore,
) -> Any:
    try:
        return fn(*args, store=store)
    except TypeError as exc:
        if "unexpected keyword argument 'store'" not in str(exc):
            raise
        return fn(*args)


def _summarize_news_digest_failure(
    failures: list[dict[str, Any]],
    verify_failures: list[dict[str, Any]],
) -> str:
    primary = failures[0] if failures else verify_failures[0] if verify_failures else {}
    provider = str(primary.get("provider") or primary.get("resolved_provider") or "unknown").strip()
    error = str(primary.get("error") or "").strip()
    if error:
        return f"来源链路失败（provider={provider}）：{error}"
    if failures and verify_failures:
        return "来源链路失败：主检索与校验链路都未通过，请查看高级证据中的 failures / verify_failures。"
    if failures:
        return f"来源链路失败（provider={provider}）：主检索链路未通过，请查看高级证据中的 failures。"
    if verify_failures:
        return f"来源链路失败（provider={provider}）：校验链路未通过，请查看高级证据中的 verify_failures。"
    return "来源链路失败：检索链路未通过，请查看高级证据。"


def _summarize_page_brief_failure(result: dict[str, Any]) -> str:
    error = str(result.get("error") or "").strip()
    if error:
        return f"页面抓取失败：{error}"
    return "页面抓取失败：浏览器任务未返回可用结果。"


def _write_public_task_result(
    run_id: str,
    request: dict[str, Any],
    results: list[dict[str, Any]],
    *,
    store: RunStore,
    status_override: str | None = None,
    failure_reason_zh: str | None = None,
) -> None:
    task_template = str(request.get("task_template") or "").strip().lower()
    if task_template == "topic_brief":
        write_topic_brief_result(
            run_id,
            request,
            results,
            store=store,
            status_override=status_override,
            failure_reason_zh=failure_reason_zh,
        )
        return
    write_news_digest_result(
        run_id,
        request,
        results,
        store=store,
        status_override=status_override,
        failure_reason_zh=failure_reason_zh,
    )


def _profile_mode_from_policy(policy: dict[str, Any] | None) -> str:
    if not isinstance(policy, dict):
        return ""
    value = str(policy.get("profile_mode") or "").strip().lower()
    return value


def run_search_pipeline(
    run_id: str,
    tool_runner: ToolRunner,
    store: RunStore,
    request: dict[str, Any],
    requested_by: dict[str, Any],
    contract_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    def _normalize_provider(raw: Any) -> str:
        value = str(raw).strip().lower()
        mapping = {
            "ddg": "duckduckgo",
            "duck": "duckduckgo",
            "browser": "browser_ddg",
            "gemini": "gemini_web",
            "chatgpt": "gemini_web",
            "chatgpt_web": "gemini_web",
            "grok": "grok_web",
        }
        return mapping.get(value, value)

    queries = request.get("queries", [])
    repeat = int(request.get("repeat", 2))
    parallel = int(request.get("parallel", 2))
    raw_providers = request.get("providers") or ["gemini_web", "grok_web"]
    providers = [_normalize_provider(item) for item in raw_providers]
    required_providers = {"gemini_web", "grok_web"}
    provider_set = {_normalize_provider(item) for item in providers}
    missing = sorted(required_providers - provider_set)
    policy_adjustments: dict[str, Any] = {}
    if missing:
        store.append_event(
            run_id,
            {
                "level": "ERROR",
                "event": "SEARCH_PARALLEL_POLICY",
                "run_id": run_id,
                "meta": {"error": "missing required providers", "missing": missing, "providers": providers},
            },
        )
        return {"ok": False, "reason": "missing required providers", "missing": missing}
    if repeat < 2:
        policy_adjustments["repeat"] = {"from": repeat, "to": 2}
        repeat = 2
    if parallel < 2:
        policy_adjustments["parallel"] = {"from": parallel, "to": 2}
        parallel = 2
    verify = request.get("verify") or {}
    verify_providers = [_normalize_provider(item) for item in (verify.get("providers") or ["gemini_web"])]
    verify_repeat = int(verify.get("repeat", 1))
    if "gemini_web" not in {str(item) for item in verify_providers}:
        verify_providers = [*verify_providers, "gemini_web"]
        policy_adjustments["verify_providers"] = "gemini_web added"
    if verify_repeat < 1:
        policy_adjustments["verify_repeat"] = {"from": verify_repeat, "to": 1}
        verify_repeat = 1

    request_policy = request.get("browser_policy") if isinstance(request.get("browser_policy"), dict) else None
    effective_profile_mode = (
        _profile_mode_from_policy(request_policy)
        or _profile_mode_from_policy(contract_policy)
    )
    if effective_profile_mode == "allow_profile" and parallel > 1:
        policy_adjustments["parallel"] = {
            "from": parallel,
            "to": 1,
            "reason": "allow_profile browser sessions are serialized to avoid shared-context flake",
        }
        parallel = 1

    tasks: list[tuple[str, str, dict[str, Any] | None, str]] = []
    task_index = 0
    for query in queries:
        for provider in providers:
            for _ in range(max(1, repeat)):
                task_index += 1
                task_id = f"search_{task_index}"
                tasks.append((query, str(provider), request_policy, task_id))

    def _run_search_task(job: tuple[str, str, dict[str, Any] | None, str]) -> dict[str, Any]:
        query, provider, task_policy, task_id = job
        audit = resolve_browser_policy(
            contract_policy=contract_policy,
            task_policy=task_policy,
            requested_by=requested_by,
            source="search",
            task_id=task_id,
        )
        result = _call_with_policy_kwargs_compat(
            tool_runner.run_search,
            args=(query,),
            kwargs={
                "provider": provider,
                "browser_policy": audit.get("effective_policy"),
                "policy_audit": audit,
            },
            fallback_kwargs={"provider": provider},
        )
        if isinstance(result, dict):
            result.setdefault("policy_audit", _policy_audit_compact(audit))
        return result

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, parallel)) as pool:
        for item in pool.map(_run_search_task, tasks):
            results.append(item)

    verify_results: list[dict[str, Any]] = []
    if verify_providers:
        verify_tasks: list[tuple[str, str, dict[str, Any] | None, str]] = []
        verify_index = 0
        for query in queries:
            for provider in verify_providers:
                for _ in range(max(1, verify_repeat)):
                    verify_index += 1
                    task_id = f"search_verify_{verify_index}"
                    verify_tasks.append((query, str(provider), request_policy, task_id))
        with ThreadPoolExecutor(max_workers=max(1, parallel)) as pool:
            for item in pool.map(_run_search_task, verify_tasks):
                verify_results.append(item)

    domain_counts: dict[str, int] = {}
    provider_counts: dict[str, int] = {}
    for item in results:
        provider = item.get("provider") or item.get("resolved_provider") or item.get("mode") or "unknown"
        provider_counts[str(provider)] = provider_counts.get(str(provider), 0) + 1
        for result in item.get("results", []) or []:
            href = result.get("href") if isinstance(result, dict) else ""
            if not href:
                continue
            domain = href.split("/")[2] if "://" in href else ""
            if domain:
                domain_counts[domain] = domain_counts.get(domain, 0) + 1
    consensus_domains = [domain for domain, count in domain_counts.items() if count >= 2]

    verification = {
        "queries": queries,
        "runs": len(results),
        "providers": provider_counts,
        "consensus_domains": consensus_domains,
        "verification_runs": len(verify_results),
        "all_consistent": all(r.get("verification", {}).get("consistent") for r in results),
    }
    if policy_adjustments:
        verification["policy_adjustments"] = policy_adjustments
    _call_store_aware_writer(write_search_results, (run_id, results), store=store)
    _call_store_aware_writer(write_verification, (run_id, verification), store=store)
    _call_store_aware_writer(write_purified_summary, (run_id, results, verification), store=store)
    raw_question = "; ".join(queries) if queries else "search"
    verify_ai_cfg = request.get("verify_ai") if isinstance(request, dict) else {}
    verify_ai_enabled = os.getenv("OPENVIBECODING_SEARCH_VERIFY_AI", "").strip().lower() in {"1", "true", "yes"}
    if isinstance(verify_ai_cfg, dict):
        if verify_ai_cfg.get("enabled") is True:
            verify_ai_enabled = True
        elif verify_ai_cfg.get("enabled") is False:
            verify_ai_enabled = False
    if verify_ai_enabled:
        ai_model = verify_ai_cfg.get("model") if isinstance(verify_ai_cfg, dict) else None
        ai_result = verify_search_results_ai(raw_question, results, verification, model=ai_model)
        store.append_event(
            run_id,
            {
                "level": "INFO" if ai_result.get("ok") else "WARN",
                "event": "SEARCH_VERIFICATION_AI_RESULT",
                "run_id": run_id,
                "meta": ai_result,
            },
        )
        if ai_result.get("ok") and isinstance(ai_result.get("report"), dict):
            _call_store_aware_writer(write_ai_verification, (run_id, ai_result["report"]), store=store)
    refined_prompt = raw_question
    freshness_days = request.get("freshness_requirement_days")
    if freshness_days is None:
        freshness_days = request.get("freshness_days")
    write_evidence_bundle(
        run_id,
        raw_question,
        refined_prompt,
        results,
        requested_by=requested_by,
        freshness_requirement_days=freshness_days if isinstance(freshness_days, int) else None,
        store=store,
    )
    failures = [item for item in results if isinstance(item, dict) and not item.get("ok", True)]
    verify_failures = [item for item in verify_results if isinstance(item, dict) and not item.get("ok", True)]
    verification["failure_count"] = len(failures)
    verification["verify_failure_count"] = len(verify_failures)
    if failures or verify_failures:
        _write_public_task_result(
            run_id,
            request,
            results,
            store=store,
            status_override="FAILED",
            failure_reason_zh=_summarize_news_digest_failure(failures, verify_failures),
        )
        return {
            "ok": False,
            "runs": len(results),
            "verification_runs": len(verify_results),
            "failures": failures,
            "verify_failures": verify_failures,
        }
    _write_public_task_result(run_id, request, results, store=store)
    return {"ok": True, "runs": len(results), "verification_runs": len(verify_results)}


def run_sampling_requests(
    run_id: str,
    tool_runner: ToolRunner,
    store: RunStore,
    request: dict[str, Any],
) -> dict[str, Any]:
    from tooling.mcp.sampling_runner import run_sampling

    requests = request.get("requests", [])
    results: list[dict[str, Any]] = []
    adapter_tools = {"aider", "continue", "open_interpreter"}
    for item in requests:
        tool = str(item.get("tool") or "sampling").strip().lower()
        if tool == "open-interpreter":
            tool = "open_interpreter"
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {"input": item.get("input"), "model": item.get("model")}

        if tool == "sampling":
            gate = tool_runner.run_mcp("sampling", payload)
            gate_error = str(gate.get("error") or "").strip().lower()
            gate_reason = str(gate.get("reason") or "").strip().lower()
            unsupported_non_adapter = (
                gate_error == "non-adapter mcp execution is not supported"
                or gate_reason == "non-adapter mcp execution is not supported"
            )
            if not gate.get("ok") and not unsupported_non_adapter:
                failure = {"ok": False, "tool": "sampling", "error": gate.get("error") or "sampling gate denied"}
                reason = gate.get("reason")
                if isinstance(reason, str) and reason.strip():
                    failure["reason"] = reason
                results.append(failure)
                return {"ok": False, "count": len(results), "results": results}
            sampling_outcome = run_sampling(payload)
            outcome = sampling_outcome if isinstance(sampling_outcome, dict) else {"ok": False, "error": "sampling returned invalid response"}
            outcome.setdefault("tool", "sampling")
            results.append(outcome)
            if not outcome.get("ok", True):
                outcome.setdefault("error", "sampling request failed")
                return {"ok": False, "count": len(results), "results": results}
            continue

        if tool not in adapter_tools:
            results.append(
                {
                    "ok": False,
                    "tool": tool or "unknown",
                    "error": f"unsupported sampling request tool: {tool or 'unknown'}",
                    "reason": "unsupported tool",
                }
            )
            return {"ok": False, "count": len(results), "results": results}

        adapter_outcome = tool_runner.run_mcp(tool, payload)
        outcome = adapter_outcome if isinstance(adapter_outcome, dict) else {"ok": False, "error": "adapter mcp returned invalid response"}
        outcome.setdefault("tool", tool)
        results.append(outcome)
        if not outcome.get("ok", True):
            outcome.setdefault("error", f"{tool} request failed")
            outcome.setdefault("reason", "adapter execution failed")
            return {"ok": False, "count": len(results), "results": results}

    summary = {
        "ok": all(item.get("ok", False) for item in results),
        "count": len(results),
        "results": results,
    }
    artifact_path = store.write_artifact(run_id, "sampling_results.json", json.dumps(summary, ensure_ascii=False))
    summary["artifact"] = str(artifact_path)
    return summary


def append_browser_results(
    store: RunStore,
    run_id: str,
    summary: dict[str, Any],
    now_ts: Callable[[], str],
) -> Path:
    artifact_path = store._run_dir(run_id) / "artifacts" / "browser_results.json"
    history: list[dict[str, Any]] = []
    if artifact_path.exists():
        try:
            existing = json.loads(artifact_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            existing = None
        if isinstance(existing, dict) and isinstance(existing.get("entries"), list):
            history = [item if isinstance(item, dict) else {"data": item} for item in existing["entries"]]
        elif existing is not None:
            if isinstance(existing, dict):
                history = [existing]
            else:
                history = [{"data": existing}]
    entry = {"entry_id": uuid.uuid4().hex, "ts": now_ts(), "summary": summary}
    payload = {"latest": entry, "entries": history + [entry]}
    return store.write_artifact(run_id, "browser_results.json", json.dumps(payload, ensure_ascii=False, indent=2))


def run_browser_tasks(
    run_id: str,
    tool_runner: ToolRunner,
    store: RunStore,
    request: dict[str, Any],
    now_ts: Callable[[], str],
    contract_policy: dict[str, Any] | None = None,
    requested_by: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tasks = request.get("tasks", [])
    headless = request.get("headless")
    results: list[dict[str, Any]] = []
    for index, task in enumerate(tasks):
        url = task.get("url", "")
        script = task.get("script", "")
        task_id = f"browser_{index}"
        task_policy = task.get("browser_policy") if isinstance(task.get("browser_policy"), dict) else None
        audit = resolve_browser_policy(
            contract_policy=contract_policy,
            task_policy=task_policy,
            requested_by=requested_by,
            source="browser",
            task_id=task_id,
        )
        result = _call_with_policy_kwargs_compat(
            tool_runner.run_browser,
            args=(url, script),
            kwargs={
                "task_id": task_id,
                "headless": headless,
                "browser_policy": audit.get("effective_policy"),
                "policy_audit": audit,
            },
            fallback_kwargs={
                "task_id": task_id,
                "headless": headless,
            },
        )
        if isinstance(result, dict):
            result.setdefault("task_id", task_id)
            result.setdefault("policy_audit", _policy_audit_compact(audit))
        results.append(result)
    failures = [item for item in results if isinstance(item, dict) and not item.get("ok", True)]
    summary = {"tasks": len(tasks), "results": results, "failures": failures}
    path = append_browser_results(store, run_id, summary, now_ts)
    task_template = str(request.get("task_template") or "").strip().lower()
    if task_template == "page_brief" and results:
        primary_result = next((item for item in results if isinstance(item, dict)), {})
        write_page_brief_result(
            run_id,
            request,
            primary_result,
            store=store,
            status_override="FAILED" if failures else None,
            failure_reason_zh=_summarize_page_brief_failure(primary_result) if failures else None,
        )
    store.append_event(
        run_id,
        {
            "level": "INFO",
            "event": "BROWSER_RESULTS",
            "run_id": run_id,
            "meta": {"ref": str(path)},
        },
    )
    return {"ok": not failures, "tasks": len(tasks), "failures": failures}


def run_tampermonkey_tasks(
    run_id: str,
    request: dict[str, Any],
    store: RunStore,
    run_tampermonkey_fn: Callable[..., Any] = run_tampermonkey,
    contract_policy: dict[str, Any] | None = None,
    requested_by: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tasks = request.get("tasks", [])
    failures: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    for index, task in enumerate(tasks):
        task_id = f"tamper_{index}"
        task_policy = task.get("browser_policy") if isinstance(task.get("browser_policy"), dict) else None
        audit = resolve_browser_policy(
            contract_policy=contract_policy,
            task_policy=task_policy,
            requested_by=requested_by,
            source="tampermonkey",
            task_id=task_id,
        )
        _append_policy_events(store, run_id, source="tampermonkey", events=audit.get("events"))
        try:
            result = _call_with_policy_kwargs_compat(
                run_tampermonkey_fn,
                args=(
                    run_id,
                    task.get("script", ""),
                    task.get("raw_output", ""),
                ),
                kwargs={
                    "parsed": task.get("parsed"),
                    "task_id": task_id,
                    "url": task.get("url", ""),
                    "script_content": task.get("script_content", ""),
                    "browser_policy": audit.get("effective_policy"),
                },
                fallback_kwargs={
                    "parsed": task.get("parsed"),
                    "task_id": task_id,
                    "url": task.get("url", ""),
                    "script_content": task.get("script_content", ""),
                },
            )
            if isinstance(result, dict):
                results.append(
                    {
                        "task_id": task_id,
                        "ok": bool(result.get("ok", False)),
                        "error": result.get("error"),
                        "execution": result.get("execution"),
                        "policy_audit": _policy_audit_compact(audit),
                    }
                )
            if isinstance(result, dict) and result.get("ok") is False:
                error = result.get("error") or "tampermonkey execution failed"
                failures.append({"task_id": task_id, "error": error})
                store.append_event(
                    run_id,
                    {
                        "level": "ERROR",
                        "event": "TAMPERMONKEY_FAILURE",
                        "run_id": run_id,
                        "meta": {"task_id": task_id, "error": error},
                    },
                )
        except Exception as exc:  # noqa: BLE001
            failures.append({"task_id": task_id, "error": str(exc)})
            results.append(
                {
                    "task_id": task_id,
                    "ok": False,
                    "error": str(exc),
                    "execution": None,
                    "policy_audit": _policy_audit_compact(audit),
                }
            )
            store.append_event(
                run_id,
                {
                    "level": "ERROR",
                    "event": "TAMPERMONKEY_FAILURE",
                    "run_id": run_id,
                    "meta": {"task_id": task_id, "error": str(exc)},
                },
            )
    summary = {"ok": not failures, "tasks": len(tasks), "results": results, "failures": failures}
    artifact = store.write_artifact(run_id, "tampermonkey_results.json", json.dumps(summary, ensure_ascii=False, indent=2))
    summary["artifact"] = str(artifact)
    return summary
