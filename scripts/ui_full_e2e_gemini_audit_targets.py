from __future__ import annotations

from typing import Any

from scripts.ui_full_e2e_gemini_audit_common import escape_css_attr


def target_label(target: dict[str, Any]) -> str:
    return (
        str(target.get("text") or "").strip()
        or str(target.get("aria_label") or "").strip()
        or str(target.get("data_testid") or "").strip()
        or str(target.get("id_attr") or "").strip()
        or str(target.get("instance_id") or "").strip()
        or str(target.get("selector") or "").strip()
        or str(target.get("tag") or "").strip()
        or "unknown"
    )


def build_target_ref(
    target: dict[str, Any] | None,
    *,
    route: str = "",
    interaction_index: int = 0,
) -> str:
    if not isinstance(target, dict):
        target = {}
    selector = str(target.get("selector") or "").strip()
    if selector:
        return selector
    id_attr = str(target.get("id_attr") or "").strip()
    if id_attr:
        return f"#{id_attr}"
    data_testid = str(target.get("data_testid") or "").strip()
    if data_testid:
        return f"[data-testid={data_testid}]"
    instance_id = str(target.get("instance_id") or "").strip()
    if instance_id:
        return instance_id
    href = str(target.get("href") or "").strip()
    if href:
        return f"href:{href}"
    name_attr = str(target.get("name_attr") or "").strip()
    if name_attr:
        return f"name:{name_attr}"
    aria_label = str(target.get("aria_label") or "").strip()
    if aria_label:
        return f"aria:{aria_label}"
    text = str(target.get("text") or "").strip()
    if text:
        return f"text:{text}"
    tag = str(target.get("tag") or "").strip()
    route_key = route.strip() or "unknown_route"
    if tag:
        return f"{route_key}::{tag}::idx:{int(interaction_index)}"
    return f"{route_key}::idx:{int(interaction_index)}"


def collect_targets(page: Any) -> list[dict[str, Any]]:
    script = r"""
(() => {
  const CLICKABLE_ROLES = new Set(["button", "menuitem", "tab", "switch", "checkbox", "radio"]);
  const CLICKABLE_INPUT_TYPES = new Set(["button", "submit", "reset", "image", "checkbox", "radio"]);
  const TARGET_SELECTOR = [
    "button",
    "a[href]",
    "input[type='button']",
    "input[type='submit']",
    "[role='button']",
    "[role='menuitem']",
    "[role='tab']",
    "[role='switch']",
    "[role='checkbox']",
    "[role='radio']",
    "[data-testid]"
  ].join(", ");
  const cssEscape = (value) => {
    if (!value) return "";
    if (window.CSS && typeof window.CSS.escape === "function") {
      return window.CSS.escape(value);
    }
    return String(value).replace(/([ !"#$%&'()*+,./:;<=>?@[\\\]^`{|}~])/g, "\\$1");
  };
  const isVisible = (el) => {
    let current = el.parentElement;
    while (current) {
      const tag = (current.tagName || "").toLowerCase();
      if (tag === "details" && !current.hasAttribute("open")) {
        const summary = current.querySelector(":scope > summary");
        if (!(summary instanceof HTMLElement) || (el !== summary && !summary.contains(el))) {
          return false;
        }
      }
      current = current.parentElement;
    }
    const style = window.getComputedStyle(el);
    if (!style) return false;
    if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity || "1") === 0) {
      return false;
    }
    const rect = el.getBoundingClientRect();
    if (!rect || rect.width <= 1 || rect.height <= 1) return false;
    return true;
  };
  const isLikelyClickable = (el) => {
    const tag = (el.tagName || "").toLowerCase();
    const role = (el.getAttribute("role") || "").trim().toLowerCase();
    const type = (el.getAttribute("type") || "").trim().toLowerCase();
    if (tag === "button") return true;
    if (tag === "a" && (el.getAttribute("href") || "").trim()) return true;
    if (tag === "input" && CLICKABLE_INPUT_TYPES.has(type)) return true;
    if (CLICKABLE_ROLES.has(role)) return true;
    return false;
  };
  const buildSelector = (el) => {
    const idAttr = (el.getAttribute("id") || "").trim();
    if (idAttr) return `#${cssEscape(idAttr)}`;
    const parts = [];
    let current = el;
    while (current && current.nodeType === Node.ELEMENT_NODE) {
      const tag = (current.tagName || "").toLowerCase();
      if (!tag || tag === "html") break;
      const parent = current.parentElement;
      if (!parent) {
        parts.unshift(tag);
        break;
      }
      const siblings = Array.from(parent.children).filter((child) => {
        return (child.tagName || "").toLowerCase() === tag;
      });
      const nth = siblings.indexOf(current) + 1;
      parts.unshift(`${tag}:nth-of-type(${Math.max(1, nth)})`);
      if ((parent.tagName || "").toLowerCase() === "body") break;
      current = parent;
    }
    return parts.join(" > ");
  };
  const nodes = Array.from(document.querySelectorAll(TARGET_SELECTOR));
  const rows = [];
  let visibleIndex = 0;
  for (let i = 0; i < nodes.length; i++) {
    const el = nodes[i];
    if (!(el instanceof HTMLElement)) continue;
    if (!isVisible(el)) continue;
    if (!isLikelyClickable(el)) continue;
    const tag = (el.tagName || "").toLowerCase();
    const role = (el.getAttribute("role") || "").trim().toLowerCase();
    const text = (el.innerText || el.textContent || "").replace(/\s+/g, " ").trim();
    const ariaLabel = (el.getAttribute("aria-label") || "").trim();
    const testid = (el.getAttribute("data-testid") || "").trim();
    const idAttr = (el.getAttribute("id") || "").trim();
    const nameAttr = (el.getAttribute("name") || "").trim();
    const href = (el.getAttribute("href") || "").trim();
    const isHashJump = tag === "a" && href.startsWith("#");
    const isRouteNavigationLink = tag === "a" && href.startsWith("/");
    const isSkipLink =
      tag === "a" &&
      (href === "#dashboard-content" ||
        text === "跳到主内容" ||
        ariaLabel === "跳到主内容");
    if (isHashJump || isSkipLink || isRouteNavigationLink) continue;
    const selector = buildSelector(el);
    const tabIndex = Number(el.getAttribute("tabindex"));
    const disabled =
      el.hasAttribute("disabled") ||
      el.getAttribute("aria-disabled") === "true" ||
      ((el instanceof HTMLButtonElement || el instanceof HTMLInputElement) && Boolean(el.disabled));
    rows.push({
      instance_id: `target_${visibleIndex}_${i}`,
      index: visibleIndex,
      dom_index: i,
      tag,
      role,
      text,
      aria_label: ariaLabel,
      data_testid: testid,
      id_attr: idAttr,
      name_attr: nameAttr,
      selector,
      href,
      tab_index: Number.isNaN(tabIndex) ? null : tabIndex,
      disabled,
    });
    visibleIndex += 1;
  }
  return rows;
})()
"""
    return list(page.evaluate(script))


def cap_redundant_targets(targets: list[dict[str, Any]], *, per_signature_limit: int = 3) -> list[dict[str, Any]]:
    limit = max(1, int(per_signature_limit))
    kept: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    for target in targets:
        if not isinstance(target, dict):
            continue
        signature = "||".join(
            [
                str(target.get("tag") or "").strip().lower(),
                str(target.get("role") or "").strip().lower(),
                str(target.get("text") or "").strip(),
                str(target.get("aria_label") or "").strip(),
                str(target.get("data_testid") or "").strip(),
                str(target.get("href") or "").strip(),
                str(target.get("id_attr") or "").strip(),
                str(target.get("name_attr") or "").strip(),
            ]
        )
        count = seen.get(signature, 0)
        if count >= limit:
            continue
        kept.append(target)
        seen[signature] = count + 1
    return kept


def find_target(page: Any, target: dict[str, Any]) -> Any:
    selector = str(target.get("selector") or "").strip()
    if selector:
        try:
            locator = page.locator(selector).first
            if locator.count() > 0:
                return locator
        except Exception:
            pass
    if target.get("data_testid"):
        testid = escape_css_attr(str(target["data_testid"]))
        locator = page.locator(f"[data-testid=\"{testid}\"]").first
        if locator.count() > 0:
            return locator
    if target.get("id_attr"):
        locator = page.locator(f"#{escape_css_attr(str(target['id_attr']))}").first
        if locator.count() > 0:
            return locator
    if target.get("aria_label"):
        aria_label = escape_css_attr(str(target["aria_label"]))
        locator = page.locator(f"[aria-label=\"{aria_label}\"]").first
        if locator.count() > 0:
            return locator
    if target.get("href"):
        href = str(target.get("href") or "").strip()
        if href:
            locator = page.locator(f"a[href=\"{escape_css_attr(href)}\"]").first
            if locator.count() > 0:
                return locator
    role = str(target.get("role") or "").strip().lower()
    tag = str(target.get("tag") or "*").strip().lower()
    if target.get("text"):
        try:
            role_name = role if role in {"button", "menuitem", "tab", "switch", "checkbox", "radio"} else None
            if role_name is None:
                role_name = "button" if tag in {"button", "input"} else "link" if tag == "a" else None
            if role_name:
                locator = page.get_by_role(role_name, name=target["text"], exact=True).first
                if locator.count() > 0:
                    return locator
                locator = page.get_by_role(role_name, name=target["text"]).first
                if locator.count() > 0:
                    return locator
        except Exception:
            pass
    fallback_selector = (
        "button:visible, a[href]:visible, input[type='button']:visible, input[type='submit']:visible, "
        "[role='button']:visible, [role='menuitem']:visible, [role='tab']:visible, [role='switch']:visible, "
        "[role='checkbox']:visible, [role='radio']:visible, [data-testid]:visible"
    )
    idx = int(target.get("index") or 0)
    locator = page.locator(fallback_selector)
    try:
        count = locator.count()
    except Exception:
        return None
    if idx < 0 or idx >= count:
        return None
    return locator.nth(idx)


def relocate_target_after_reload(page: Any, target: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
    current_targets = collect_targets(page)
    if not current_targets:
        return None, target

    def _match_score(candidate: dict[str, Any]) -> int:
        score = 0
        if target.get("selector") and candidate.get("selector") == target.get("selector"):
            score += 18
        if target.get("instance_id") and candidate.get("instance_id") == target.get("instance_id"):
            score += 12
        if target.get("data_testid") and candidate.get("data_testid") == target.get("data_testid"):
            score += 16
        if target.get("id_attr") and candidate.get("id_attr") == target.get("id_attr"):
            score += 14
        if target.get("aria_label") and candidate.get("aria_label") == target.get("aria_label"):
            score += 12
        if target.get("href") and candidate.get("href") == target.get("href"):
            score += 10
        if target.get("text") and candidate.get("text") == target.get("text"):
            score += 8
        if target.get("tag") and candidate.get("tag") == target.get("tag"):
            score += 4
        if target.get("role") and candidate.get("role") == target.get("role"):
            score += 2
        if target.get("index") is not None and candidate.get("index") is not None:
            try:
                diff = abs(int(target.get("index") or 0) - int(candidate.get("index") or 0))
                if diff == 0:
                    score += 6
                elif diff <= 2:
                    score += 2
            except Exception:
                pass
        return score

    best = max(current_targets, key=_match_score)
    if _match_score(best) <= 0:
        return None, target
    locator = find_target(page, best)
    if locator is None:
        return None, target
    return locator, best


def guess_expected_effect(target: dict[str, Any]) -> str:
    text = " ".join(
        [
            str(target.get("text") or ""),
            str(target.get("aria_label") or ""),
            str(target.get("href") or ""),
        ]
    ).lower()
    mapping = [
        (("run", "执行", "/run"), "应触发执行或进入执行阶段，并出现运行中/结果反馈。"),
        (("refresh", "刷新"), "应刷新当前数据视图或状态。"),
        (("approve", "批准", "确认"), "应显示确认流程并落地审批状态变化。"),
        (("reject", "拒绝"), "应显示拒绝动作反馈并更新状态。"),
        (("rollback", "回滚"), "应触发回滚流程并出现结果反馈。"),
        (("replay", "回放"), "应触发回放并出现对比或任务结果提示。"),
        (("send", "发送"), "应发送消息或命令并显示发送结果。"),
        (("toggle", "展开", "收起", "pause", "resume", "实时"), "应切换界面状态并有明显反馈。"),
        (("open", "view", "查看", "/"), "应打开对应页面、详情或面板。"),
    ]
    for keywords, expected in mapping:
        if any(keyword in text for keyword in keywords):
            return expected
    return "应产生明确且可见的交互反馈（状态变化、内容变化或导航变化）。"
