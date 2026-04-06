from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from cortexpilot_orch.store.run_store import RunStore

DEFAULT_PAGE_BRIEF_FOCUS = "Summarize the page for a first-time reader."
PAGE_BRIEF_BROWSER_SCRIPT = r"""
() => {
  const normalize = (value, maxLength = 0) => {
    const text = String(value || "").replace(/\s+/g, " ").trim();
    if (!maxLength || text.length <= maxLength) return text;
    return `${text.slice(0, maxLength - 1)}…`;
  };

  const pickText = (selector, limit = 6) =>
    Array.from(document.querySelectorAll(selector))
      .map((node) => normalize(node.textContent || "", 220))
      .filter(Boolean)
      .slice(0, limit);

  const paragraphs = pickText("main p, article p, [role='main'] p, p", 6).filter((item) => item.length >= 40);
  const headings = pickText("h1, h2, h3", 8);
  const listItems = pickText("main li, article li, [role='main'] li, li", 8).filter((item) => item.length >= 16);
  const metaDescription = normalize(
    document.querySelector("meta[name='description']")?.getAttribute("content") || "",
    320,
  );
  const bodyText = normalize(document.body?.innerText || "", 2400);

  return {
    title: normalize(document.title || "", 180),
    url: window.location.href,
    meta_description: metaDescription,
    headings,
    paragraphs,
    list_items: listItems,
    body_excerpt: bodyText,
  };
}
"""


def _now_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _shorten(text: str, max_length: int) -> str:
    value = " ".join(str(text or "").split()).strip()
    if not value:
        return ""
    if len(value) <= max_length:
        return value
    return f"{value[: max_length - 1].rstrip()}…"


def _first_non_empty(*values: Any) -> str:
    for value in values:
        text = _shorten(str(value or ""), 4000)
        if text:
            return text
    return ""


def _unique_points(items: list[str], limit: int = 5) -> list[str]:
    seen: set[str] = set()
    points: list[str] = []
    for raw in items:
        value = _shorten(raw, 220)
        if not value:
            continue
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        points.append(value)
        if len(points) >= limit:
            break
    return points


def _hostname_label(url: str) -> str:
    try:
        parsed = urlparse(url)
        host = parsed.netloc.strip()
        return host or url
    except Exception:  # noqa: BLE001
        return url


def _build_summary(
    *,
    page_title: str,
    focus: str,
    meta_description: str,
    paragraphs: list[str],
    headings: list[str],
    body_excerpt: str,
) -> str:
    summary_source = _first_non_empty(meta_description, paragraphs[0] if paragraphs else "", body_excerpt)
    if not summary_source:
        return ""
    lead = _first_non_empty(page_title, headings[0] if headings else "")
    if lead:
        return _shorten(f"{lead}: {summary_source}", 480)
    if focus:
        return _shorten(f"{focus} {summary_source}", 480)
    return _shorten(summary_source, 480)


def _failure_reason(browser_result: dict[str, Any], override: str | None) -> str:
    if isinstance(override, str) and override.strip():
        return override.strip()
    error = str(browser_result.get("error") or "").strip()
    if error:
        return f"页面抓取失败：{error}"
    return "页面抓取失败：浏览器执行未返回可用结果。"


def build_page_brief_result(
    request: dict[str, Any],
    browser_result: dict[str, Any],
    *,
    status_override: str | None = None,
    failure_reason_zh: str | None = None,
) -> dict[str, Any] | None:
    if str(request.get("task_template") or "").strip().lower() != "page_brief":
        return None

    template_payload = request.get("template_payload") if isinstance(request.get("template_payload"), dict) else {}
    requested_url = str(template_payload.get("url") or "").strip()
    focus = str(template_payload.get("focus") or DEFAULT_PAGE_BRIEF_FOCUS).strip() or DEFAULT_PAGE_BRIEF_FOCUS
    result_payload = browser_result.get("result") if isinstance(browser_result.get("result"), dict) else {}
    artifacts = browser_result.get("artifacts") if isinstance(browser_result.get("artifacts"), dict) else {}

    resolved_url = _first_non_empty(result_payload.get("url"), browser_result.get("url"), requested_url)
    page_title = _shorten(str(result_payload.get("title") or ""), 180)
    meta_description = _shorten(str(result_payload.get("meta_description") or ""), 320)
    headings = [str(item).strip() for item in result_payload.get("headings", []) if str(item).strip()]
    paragraphs = [str(item).strip() for item in result_payload.get("paragraphs", []) if str(item).strip()]
    list_items = [str(item).strip() for item in result_payload.get("list_items", []) if str(item).strip()]
    body_excerpt = _shorten(str(result_payload.get("body_excerpt") or ""), 1200)

    key_points = _unique_points([*headings, *list_items, *paragraphs])
    summary = _build_summary(
        page_title=page_title,
        focus=focus,
        meta_description=meta_description,
        paragraphs=paragraphs,
        headings=headings,
        body_excerpt=body_excerpt,
    )

    status = str(status_override or ("SUCCESS" if browser_result.get("ok", True) else "FAILED")).strip().upper()
    if status == "SUCCESS" and not summary and not key_points:
        status = "EMPTY"
    if status == "EMPTY" and not summary:
        summary = "页面已成功抓取，但未提取到足够的可读正文。"
    if status == "FAILED" and not summary:
        summary = f"未能生成 {page_title or _hostname_label(resolved_url or requested_url)} 的页面简报。"

    payload: dict[str, Any] = {
        "task_template": "page_brief",
        "generated_at": _now_ts(),
        "status": status,
        "url": requested_url,
        "resolved_url": resolved_url,
        "page_title": page_title or _hostname_label(resolved_url or requested_url),
        "focus": focus,
        "summary": summary,
        "key_points": key_points,
        "screenshot_artifact": artifacts.get("screenshot"),
    }

    if status == "FAILED":
        payload["failure_reason_zh"] = _failure_reason(browser_result, failure_reason_zh)

    return payload


def write_page_brief_result(
    run_id: str,
    request: dict[str, Any],
    browser_result: dict[str, Any],
    *,
    store: RunStore | None = None,
    status_override: str | None = None,
    failure_reason_zh: str | None = None,
) -> Any:
    store = store or RunStore()
    payload = build_page_brief_result(
        request,
        browser_result,
        status_override=status_override,
        failure_reason_zh=failure_reason_zh,
    )
    if payload is None:
        raise ValueError("page_brief result requested for non-page_brief task")
    return store.write_report(run_id, "page_brief_result", payload)
