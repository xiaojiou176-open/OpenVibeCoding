from __future__ import annotations

import time
import urllib.parse
from pathlib import Path
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from scripts.ui_full_e2e_gemini_audit_common import is_runtime_closed_error, safe_name
from scripts.ui_full_e2e_gemini_audit_gemini import (
    ensure_interaction_analysis_payload,
    ensure_page_analysis_payload,
    fallback_interaction_analysis,
    fallback_page_analysis,
)
from scripts.ui_full_e2e_gemini_audit_reports import derive_interaction_result
from scripts.ui_full_e2e_gemini_audit_runtime import (
    ensure_route_runtime,
    goto_with_retry,
    rebuild_route_runtime,
    safe_close_browser,
    safe_close_context,
    safe_close_page,
    safe_screenshot,
)
from scripts.ui_full_e2e_gemini_audit_targets import (
    build_target_ref,
    cap_redundant_targets,
    collect_targets,
    find_target,
    guess_expected_effect,
    relocate_target_after_reload,
    target_label,
)


def _apply_auth_cookies(*, context: Any, base_dashboard: str, api_token: str) -> None:
    token = str(api_token or "").strip()
    if not token:
        return
    context.add_cookies(
        [
            {"name": "cortexpilot_api_token", "value": token, "url": base_dashboard},
            {"name": "api_token", "value": token, "url": base_dashboard},
        ]
    )


def _wait_for_load_state_best_effort(*, page: Any, state: str, timeout_ms: int) -> bool:
    timeout_ms = max(0, int(timeout_ms))
    if timeout_ms <= 0:
        return False
    try:
        page.wait_for_load_state(state, timeout=timeout_ms)
        return True
    except (PlaywrightTimeoutError, PlaywrightError):
        return False


def _wait_for_page_settle(*, page: Any, settle_ms: int) -> None:
    settle_ms = max(0, int(settle_ms))
    if settle_ms <= 0:
        return
    started = time.monotonic()
    _wait_for_load_state_best_effort(page=page, state="domcontentloaded", timeout_ms=settle_ms)
    elapsed_ms = int((time.monotonic() - started) * 1000)
    remaining_ms = max(0, settle_ms - elapsed_ms)
    if remaining_ms <= 0:
        return
    if _wait_for_load_state_best_effort(page=page, state="networkidle", timeout_ms=remaining_ms):
        return
    elapsed_ms = int((time.monotonic() - started) * 1000)
    remaining_ms = max(0, settle_ms - elapsed_ms)
    if remaining_ms <= 0:
        return
    try:
        page.wait_for_function(
            "() => document.readyState === 'complete' || document.readyState === 'interactive'",
            timeout=remaining_ms,
        )
    except (PlaywrightTimeoutError, PlaywrightError):
        return


def _wait_for_post_action_settle(*, page: Any, settle_ms: int) -> None:
    settle_ms = max(0, int(settle_ms))
    if settle_ms <= 0:
        return
    if _wait_for_load_state_best_effort(page=page, state="networkidle", timeout_ms=settle_ms):
        return
    try:
        page.wait_for_function(
            "() => document.readyState === 'complete' || document.readyState === 'interactive'",
            timeout=settle_ms,
        )
    except (PlaywrightTimeoutError, PlaywrightError):
        return


def _wait_for_command_tower_ready(*, page: Any, timeout_ms: int) -> None:
    timeout_ms = max(0, int(timeout_ms))
    if timeout_ms <= 0:
        return
    try:
        page.wait_for_function(
            """
            () => {
              const bodyText = document.body?.innerText || "";
              const hasRefreshFailure = bodyText.includes("刷新异常");
              const hasSessionBoard =
                bodyText.includes("会话面板列表") ||
                bodyText.includes("风险样本") ||
                bodyText.includes("高风险会话");
              return hasSessionBoard && !hasRefreshFailure;
            }
            """,
            timeout=timeout_ms,
        )
    except (PlaywrightTimeoutError, PlaywrightError):
        return


def execute_playwright_audit(
    *,
    resolved_routes: list[str],
    base_dashboard: str,
    page_dir: Path,
    interaction_dir: Path,
    payload: dict[str, Any],
    analyzer: Any,
    update_heartbeat: Any,
    args: Any,
) -> tuple[int, int, int, int]:
    total_routes_planned = len(resolved_routes)
    total_interactions = 0
    click_failures = 0
    gemini_warn_or_fail = 0
    routed_completed = 0
    max_interactions = max(0, int(getattr(args, "max_interactions", 0)))
    max_duplicate_targets = max(1, int(getattr(args, "max_duplicate_targets", 3)))
    interaction_budget_reached = False

    with sync_playwright() as p:
        update_heartbeat("playwright_launch")
        headless_mode = not bool(getattr(args, "headed", False))
        print(
            "🧪 [ui-full-e2e] launching Playwright browser "
            f"(headless={'true' if headless_mode else 'false'})"
        )
        browser: Any | None = None
        context: Any | None = None
        page: Any | None = None
        browser, context, page, _ = ensure_route_runtime(
            playwright_runtime=p,
            browser=browser,
            context=context,
            page=page,
            navigation_timeout_ms=args.navigation_timeout_ms,
            headless=headless_mode,
        )
        _apply_auth_cookies(context=context, base_dashboard=base_dashboard, api_token=args.api_token)

        for route_idx, route in enumerate(resolved_routes, start=1):
            update_heartbeat(
                "route_start",
                route=route,
                route_index=route_idx,
                routes_total=total_routes_planned,
                routes_done=routed_completed,
                interactions_done=total_interactions,
                click_failures=click_failures,
                gemini_warn_or_fail=gemini_warn_or_fail,
            )
            print(f"📄 [ui-full-e2e] route={route}")
            route_key = safe_name(route.strip("/").replace("/", "_") or "root")
            route_item: dict[str, Any] = {
                "route": route,
                "page_screenshot": "",
                "page_analysis": fallback_page_analysis(route=route, reason="route_not_started"),
                "interactions": [],
                "click_inventory": [],
                "errors": [],
            }
            payload["routes"].append(route_item)

            url = f"{base_dashboard}{route}"
            page_shot = page_dir / f"{route_key}.png"
            targets: list[dict[str, Any]] = []
            route_ready = False
            for route_attempt in range(1, 3):
                try:
                    browser, context, page, rebuilt = ensure_route_runtime(
                        playwright_runtime=p,
                        browser=browser,
                        context=context,
                        page=page,
                        navigation_timeout_ms=args.navigation_timeout_ms,
                        headless=headless_mode,
                    )
                    if rebuilt:
                        route_item["errors"].append("route runtime rebuilt before navigation")
                        _apply_auth_cookies(
                            context=context,
                            base_dashboard=base_dashboard,
                            api_token=args.api_token,
                        )
                    goto_with_retry(
                        page,
                        url,
                        wait_until="domcontentloaded",
                        timeout_ms=args.navigation_timeout_ms,
                        max_attempts=3,
                    )
                    _wait_for_page_settle(page=page, settle_ms=args.page_settle_ms)
                    if route == "/command-tower":
                        _wait_for_command_tower_ready(
                            page=page,
                            timeout_ms=min(max(args.page_settle_ms, 0) + 10000, 20000),
                        )
                    safe_screenshot(page, page_shot, full_page=True, timeout_ms=0)
                    route_item["page_screenshot"] = str(page_shot)
                    if analyzer is None:
                        route_item["page_analysis"] = fallback_page_analysis(
                            route=route,
                            reason="gemini_skipped",
                            verdict="warn",
                        )
                    elif page_shot.exists():
                        try:
                            route_item["page_analysis"] = analyzer.analyze_page(route=route, screenshot_path=page_shot)
                        except Exception as exc:
                            error_text = str(exc)
                            route_item["errors"].append(f"gemini page analysis failed: {error_text}")
                            page_reason = (
                                "gemini_page_failed_extreme_tall_screenshot"
                                if "extreme_tall_screenshot" in error_text
                                else "gemini_page_failed"
                            )
                            route_item["page_analysis"] = fallback_page_analysis(
                                route=route,
                                reason=page_reason,
                                error=error_text,
                            )
                    else:
                        route_item["page_analysis"] = fallback_page_analysis(
                            route=route,
                            reason="page_screenshot_missing",
                        )
                    route_item["page_analysis"] = ensure_page_analysis_payload(
                        route_item.get("page_analysis"),
                        route=route,
                        fallback_reason="route_page_analysis_invalid",
                    )
                    targets = collect_targets(page)
                    targets = cap_redundant_targets(targets, per_signature_limit=max_duplicate_targets)
                    if args.max_buttons_per_page > 0:
                        targets = targets[: args.max_buttons_per_page]
                    route_item["target_count"] = len(targets)
                    route_ready = True
                    break
                except Exception as exc:
                    if route_attempt == 1 and is_runtime_closed_error(exc):
                        route_item["errors"].append(
                            f"route runtime closed, rebuilding and retrying once: {exc}"
                        )
                        try:
                            browser, context, page = rebuild_route_runtime(
                                playwright_runtime=p,
                                browser=browser,
                                context=context,
                                page=page,
                                navigation_timeout_ms=args.navigation_timeout_ms,
                                headless=headless_mode,
                            )
                            _apply_auth_cookies(
                                context=context,
                                base_dashboard=base_dashboard,
                                api_token=args.api_token,
                            )
                            continue
                        except Exception as rebuild_exc:
                            route_item["errors"].append(f"route runtime rebuild failed: {rebuild_exc}")
                            route_item["page_analysis"] = fallback_page_analysis(
                                route=route,
                                reason="route_runtime_rebuild_failed",
                                error=str(rebuild_exc),
                            )
                            break
                    route_item["errors"].append(f"route prepare failed: {exc}")
                    route_item["page_analysis"] = fallback_page_analysis(
                        route=route,
                        reason="route_prepare_failed",
                        error=str(exc),
                    )
                    break

            route_item["page_analysis"] = ensure_page_analysis_payload(
                route_item.get("page_analysis"),
                route=route,
                fallback_reason="route_page_analysis_missing",
            )
            page_verdict = str((route_item["page_analysis"] or {}).get("verdict", "")).lower().strip()
            if page_verdict in {"warn", "fail"}:
                gemini_warn_or_fail += 1

            if not route_ready:
                routed_completed += 1
                update_heartbeat(
                    "route_prepare_failed",
                    route=route,
                    route_index=route_idx,
                    routes_total=total_routes_planned,
                    routes_done=routed_completed,
                    interactions_done=total_interactions,
                    click_failures=click_failures,
                    gemini_warn_or_fail=gemini_warn_or_fail,
                )
                continue

            for idx, target in enumerate(targets, start=1):
                if max_interactions > 0 and total_interactions >= max_interactions:
                    interaction_budget_reached = True
                    route_item.setdefault("notes", []).append(
                        f"interaction budget reached: total_interactions={total_interactions}, max={max_interactions}"
                    )
                    update_heartbeat(
                        "interaction_budget_reached",
                        route=route,
                        route_index=route_idx,
                        interaction_index=idx,
                        route_target_count=len(targets),
                        routes_total=total_routes_planned,
                        routes_done=routed_completed,
                        interactions_done=total_interactions,
                        click_failures=click_failures,
                        gemini_warn_or_fail=gemini_warn_or_fail,
                    )
                    break
                total_interactions += 1
                update_heartbeat(
                    "interaction_start",
                    route=route,
                    route_index=route_idx,
                    interaction_index=idx,
                    route_target_count=len(targets),
                    routes_total=total_routes_planned,
                    routes_done=routed_completed,
                    interactions_done=total_interactions,
                    click_failures=click_failures,
                    gemini_warn_or_fail=gemini_warn_or_fail,
                )
                label = (
                    str(target.get("text") or "").strip()
                    or str(target.get("aria_label") or "").strip()
                    or str(target.get("data_testid") or "").strip()
                    or str(target.get("id_attr") or "").strip()
                    or f"target_{idx}"
                )
                target_key = safe_name(f"{route_key}_{idx}_{label}")[:120]
                before_path = interaction_dir / f"{target_key}.before.png"
                after_path = interaction_dir / f"{target_key}.after.png"

                entry: dict[str, Any] = {
                    "index": idx,
                    "target": target,
                    "expected_effect": guess_expected_effect(target),
                    "before_screenshot": str(before_path),
                    "after_screenshot": str(after_path),
                    "click_ok": False,
                    "click_strategy": "",
                    "observed": {},
                    "analysis": fallback_interaction_analysis(
                        route=route,
                        target=target,
                        reason="interaction_not_started",
                    ),
                    "errors": [],
                }
                route_item["interactions"].append(entry)
                interaction_page: Any | None = None
                response_listener_attached = False
                try:
                    for page_attempt in range(1, 3):
                        try:
                            interaction_page = context.new_page()
                            break
                        except Exception as exc:
                            if page_attempt == 1 and is_runtime_closed_error(exc):
                                route_item["errors"].append(
                                    f"interaction runtime closed, rebuilding and retrying once: {exc}"
                                )
                                browser, context, page = rebuild_route_runtime(
                                    playwright_runtime=p,
                                    browser=browser,
                                    context=context,
                                    page=page,
                                    navigation_timeout_ms=args.navigation_timeout_ms,
                                    headless=headless_mode,
                                )
                                continue
                            raise
                    if interaction_page is None:
                        raise RuntimeError("failed to open interaction page")

                    goto_with_retry(
                        interaction_page,
                        url,
                        wait_until="domcontentloaded",
                        timeout_ms=args.navigation_timeout_ms,
                        max_attempts=3,
                    )
                    _wait_for_page_settle(page=interaction_page, settle_ms=args.page_settle_ms)
                    if route == "/command-tower":
                        _wait_for_command_tower_ready(
                            page=interaction_page,
                            timeout_ms=min(max(args.page_settle_ms, 0) + 10000, 20000),
                        )

                    locator = find_target(interaction_page, target)
                    relocated = False
                    if locator is None:
                        relocated_locator, relocated_target = relocate_target_after_reload(interaction_page, target)
                        if relocated_locator is not None:
                            locator = relocated_locator
                            target = relocated_target
                            entry["target"] = relocated_target
                            relocated = True
                        else:
                            entry["errors"].append("target locator not found")
                            entry["analysis"] = fallback_interaction_analysis(
                                route=route,
                                target=target,
                                reason="target_locator_not_found",
                            )
                            continue

                    try:
                        if locator.count() < 1:
                            relocated_locator, relocated_target = relocate_target_after_reload(interaction_page, target)
                            if relocated_locator is not None:
                                locator = relocated_locator
                                target = relocated_target
                                entry["target"] = relocated_target
                                relocated = True
                            else:
                                entry["errors"].append("target count=0 after reload")
                                entry["analysis"] = fallback_interaction_analysis(
                                    route=route,
                                    target=target,
                                    reason="target_count_zero_after_reload",
                                )
                                continue
                    except Exception:
                        pass

                    url_before = interaction_page.url
                    api_requests_before: list[dict[str, Any]] = []

                    def _on_response(resp: Any) -> None:
                        try:
                            if "/api/" in resp.url:
                                api_requests_before.append({"url": resp.url, "status": resp.status})
                        except Exception:
                            pass

                    interaction_page.on("response", _on_response)
                    response_listener_attached = True
                    try:
                        safe_screenshot(interaction_page, before_path, full_page=False, timeout_ms=0)
                    except Exception as exc:
                        entry["errors"].append(f"before screenshot failed: {exc}")
                    disabled_target = bool(target.get("disabled"))
                    if disabled_target:
                        entry["click_ok"] = True
                        entry["click_strategy"] = "skip_disabled"
                        entry["expected_effect"] = "该控件处于禁用态，预期不触发动作且禁用反馈应清晰。"
                        _wait_for_post_action_settle(
                            page=interaction_page,
                            settle_ms=min(200, args.interaction_settle_ms),
                        )
                    else:
                        click_exc: str | None = None
                        try:
                            locator.scroll_into_view_if_needed(timeout=args.action_timeout_ms)
                            locator.click(timeout=args.action_timeout_ms)
                            _wait_for_post_action_settle(
                                page=interaction_page,
                                settle_ms=args.interaction_settle_ms,
                            )
                            entry["click_ok"] = True
                            entry["click_strategy"] = "normal"
                        except (PlaywrightTimeoutError, PlaywrightError, Exception) as exc:  # noqa: PERF203
                            click_exc = str(exc)

                        if not entry["click_ok"]:
                            try:
                                locator.scroll_into_view_if_needed(timeout=args.action_timeout_ms)
                                locator.click(timeout=args.action_timeout_ms, force=True)
                                _wait_for_post_action_settle(
                                    page=interaction_page,
                                    settle_ms=args.interaction_settle_ms,
                                )
                                entry["click_ok"] = True
                                entry["click_strategy"] = "force"
                            except (PlaywrightTimeoutError, PlaywrightError, Exception):
                                pass

                        if not entry["click_ok"]:
                            try:
                                handle = locator.element_handle(timeout=args.action_timeout_ms)
                                if handle is not None:
                                    interaction_page.evaluate("(el) => { el.click(); }", handle)
                                    _wait_for_post_action_settle(
                                        page=interaction_page,
                                        settle_ms=args.interaction_settle_ms,
                                    )
                                    entry["click_ok"] = True
                                    entry["click_strategy"] = "dom_click"
                            except Exception:
                                pass

                        if not entry["click_ok"]:
                            detail = f"click failed: {click_exc}" if click_exc else "click failed: unknown"
                            entry["errors"].append(detail)
                    try:
                        safe_screenshot(interaction_page, after_path, full_page=False, timeout_ms=0)
                    except Exception as exc:
                        entry["errors"].append(f"after screenshot failed: {exc}")

                    url_after = interaction_page.url
                    observed = {
                        "url_before": url_before,
                        "url_after": url_after,
                        "url_changed": url_before != url_after,
                        "target_relocated": relocated,
                        "api_calls_count": len(api_requests_before),
                        "api_calls": api_requests_before[:30],
                    }
                    entry["observed"] = observed

                    if analyzer is None:
                        entry["analysis"] = fallback_interaction_analysis(
                            route=route,
                            target=target,
                            reason="gemini_skipped",
                            verdict="warn",
                        )
                    elif not before_path.exists() or not after_path.exists():
                        entry["errors"].append("gemini interaction analysis skipped: screenshot missing")
                        entry["analysis"] = fallback_interaction_analysis(
                            route=route,
                            target=target,
                            reason="interaction_screenshot_missing",
                        )
                    else:
                        current_route_path = urllib.parse.urlparse(url_before).path or "/"
                        current_route_path = current_route_path.rstrip("/") or "/"
                        target_href = str(target.get("href") or "").strip()
                        target_route_path = (
                            target_href.split("?")[0].rstrip("/") or "/" if target_href.startswith("/") else ""
                        )
                        if target_route_path and target_route_path == current_route_path:
                            entry["analysis"] = {
                                "verdict": "pass",
                                "summary": "点击当前已激活导航项，保持页面与激活态一致属于预期行为。",
                                "issues": [],
                                "recommendations": [],
                            }
                        else:
                            try:
                                entry["analysis"] = analyzer.analyze_interaction(
                                    route=route,
                                    target=target,
                                    expected_effect=entry["expected_effect"],
                                    observed=observed,
                                    before_path=before_path,
                                    after_path=after_path,
                                )
                            except Exception as exc:
                                error_text = str(exc)
                                entry["errors"].append(f"gemini interaction analysis failed: {error_text}")
                                interaction_reason = (
                                    "gemini_interaction_failed_extreme_tall_screenshot"
                                    if "extreme_tall_screenshot" in error_text
                                    else "gemini_interaction_failed"
                                )
                                entry["analysis"] = fallback_interaction_analysis(
                                    route=route,
                                    target=target,
                                    reason=interaction_reason,
                                    error=error_text,
                                )
                except Exception as exc:
                    entry["errors"].append(f"interaction runtime failed: {exc}")
                    entry["analysis"] = fallback_interaction_analysis(
                        route=route,
                        target=target,
                        reason="interaction_runtime_failed",
                        error=str(exc),
                    )
                finally:
                    if response_listener_attached and interaction_page is not None:
                        try:
                            interaction_page.remove_listener("response", _on_response)
                        except Exception:
                            pass
                    safe_close_page(interaction_page)

                entry["analysis"] = ensure_interaction_analysis_payload(
                    entry.get("analysis"),
                    route=route,
                    target=entry.get("target") or target,
                    fallback_reason="interaction_analysis_missing",
                )
                if entry.get("click_ok") is not True:
                    click_failures += 1
                verdict = str((entry["analysis"] or {}).get("verdict", "")).lower().strip()
                if verdict in {"warn", "fail"}:
                    gemini_warn_or_fail += 1
                target_for_inventory = (
                    entry.get("target") if isinstance(entry.get("target"), dict) else target
                )
                selector = str((target_for_inventory or {}).get("selector") or "").strip()
                id_attr = str((target_for_inventory or {}).get("id_attr") or "").strip()
                data_testid = str((target_for_inventory or {}).get("data_testid") or "").strip()
                instance_id = str((target_for_inventory or {}).get("instance_id") or "").strip()
                target_ref = build_target_ref(
                    target_for_inventory if isinstance(target_for_inventory, dict) else {},
                    route=route,
                    interaction_index=int(entry.get("index", idx) or idx),
                )
                interaction_result = derive_interaction_result(
                    click_ok=entry.get("click_ok") is True,
                    analysis_verdict=verdict,
                )
                route_item["click_inventory"].append(
                    {
                        "route": route,
                        "interaction_index": int(entry.get("index", idx) or idx),
                        "target_label": target_label(target_for_inventory or {}),
                        "target_selector": selector,
                        "target_instance_id": instance_id,
                        "target_id_attr": id_attr,
                        "target_data_testid": data_testid,
                        "target_ref": target_ref,
                        "click_ok": entry.get("click_ok") is True,
                        "analysis_verdict": verdict or "unknown",
                        "interaction_result": interaction_result,
                        "errors": [str(err) for err in (entry.get("errors") or [])],
                    }
                )

            routed_completed += 1
            update_heartbeat(
                "route_done",
                route=route,
                route_index=route_idx,
                routes_total=total_routes_planned,
                routes_done=routed_completed,
                interactions_done=total_interactions,
                click_failures=click_failures,
                gemini_warn_or_fail=gemini_warn_or_fail,
            )
            if interaction_budget_reached:
                break

        update_heartbeat(
            "browser_closing",
            force=True,
            routes_total=total_routes_planned,
            routes_done=routed_completed,
            interactions_done=total_interactions,
            click_failures=click_failures,
            gemini_warn_or_fail=gemini_warn_or_fail,
        )
        safe_close_page(page)
        safe_close_context(context)
        safe_close_browser(browser)

    return total_interactions, click_failures, gemini_warn_or_fail, routed_completed
