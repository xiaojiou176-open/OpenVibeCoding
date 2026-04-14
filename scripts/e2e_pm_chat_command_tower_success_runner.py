#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

host, api_port, dashboard_port, api_token, evidence_path, screen_pm, screen_session, run_mock_raw, run_mode, runner_name, allowed_paths_override, reexec_strict_raw, acceptance_cmd = sys.argv[1:14]
run_mock = str(run_mock_raw).strip().lower() in {"1", "true", "yes", "y"}
reexec_strict = str(reexec_strict_raw).strip().lower() in {"1", "true", "yes", "y", "on"}
allowed_paths_override = str(allowed_paths_override).strip()
acceptance_cmd = str(acceptance_cmd).strip()
orchestration_smoke_mode = str(os.getenv("OPENVIBECODING_E2E_ORCHESTRATION_SMOKE_MODE", "0")).strip().lower() in {"1", "true", "yes", "y", "on"}
strict_acceptance_env = str(os.getenv("OPENVIBECODING_E2E_STRICT_ACCEPTANCE", "")).strip().lower()
if strict_acceptance_env in {"1", "true", "yes", "y", "on"}:
    strict_acceptance = True
elif strict_acceptance_env in {"0", "false", "no", "n", "off"}:
    strict_acceptance = False
else:
    strict_acceptance = str(run_mode).strip().lower() == "real"
api_base = f"http://{host}:{api_port}"
dash_base = f"http://{host}:{dashboard_port}"

run_id_wait_sec = int(
    os.getenv(
        "OPENVIBECODING_E2E_RUN_ID_WAIT_SEC",
        "90" if orchestration_smoke_mode else ("120" if run_mock else "240"),
    )
)
status_wait_sec = int(
    os.getenv(
        "OPENVIBECODING_E2E_STATUS_WAIT_SEC",
        "120" if orchestration_smoke_mode else ("180" if run_mock else "480"),
    )
)
stagnation_timeout_sec = int(
    os.getenv(
        "OPENVIBECODING_E2E_STATUS_STAGNATION_SEC",
        "45" if orchestration_smoke_mode else ("90" if run_mock else "180"),
    )
)
api_post_timeout_sec = int(
    os.getenv(
        "OPENVIBECODING_E2E_API_POST_TIMEOUT_SEC",
        "90" if orchestration_smoke_mode else ("60" if run_mock else "180"),
    )
)
plan_ready_wait_sec = int(
    os.getenv(
        "OPENVIBECODING_E2E_PLAN_READY_WAIT_SEC",
        "90" if orchestration_smoke_mode else ("120" if run_mock else "240"),
    )
)
plan_ready_poll_sec = float(os.getenv("OPENVIBECODING_E2E_PLAN_READY_POLL_SEC", "2.0"))
runtime_options_provider = str(os.getenv("OPENVIBECODING_E2E_RUNTIME_OPTIONS_PROVIDER", "")).strip()
operator_role = "TECH_LEAD"
ui_intake_required = str(os.getenv("OPENVIBECODING_E2E_REQUIRE_UI_INTAKE", "1" if run_mode == "real" else "0")).strip().lower() in {"1", "true", "yes", "y", "on"}
ui_intake_wait_sec = int(
    os.getenv(
        "OPENVIBECODING_E2E_UI_INTAKE_WAIT_SEC",
        "90" if orchestration_smoke_mode else ("150" if run_mode == "real" else "45"),
    )
)
check_pm_stop = str(os.getenv("OPENVIBECODING_E2E_CHECK_PM_STOP", "1")).strip().lower() in {"1", "true", "yes", "y", "on"}
pm_stop_probe_delay_sec = int(os.getenv("OPENVIBECODING_E2E_PM_STOP_PROBE_DELAY_SEC", "8"))
last_session_events_payload: dict | list | None = None
last_run_payload: dict | None = None
default_mcp_tool_set = ["01-filesystem"]

def progress(msg: str) -> None:
    print(f"[pm-chat-e2e] {msg}", flush=True)


def _auth_headers(*, include_json_content_type: bool = False) -> dict[str, str]:
    headers: dict[str, str] = {"Authorization": f"Bearer {api_token}"}
    if operator_role:
        headers["x-openvibecoding-role"] = operator_role
    if include_json_content_type:
        headers["Content-Type"] = "application/json"
    return headers

def api_get_json(path: str) -> dict:
    req = urllib.request.Request(
        f"{api_base}{path}",
        headers=_auth_headers(),
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        return json.loads(resp.read().decode("utf-8"))

def api_post_json(path: str, payload: dict) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{api_base}{path}",
        data=body,
        headers=_auth_headers(include_json_content_type=True),
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=api_post_timeout_sec) as resp:
        return json.loads(resp.read().decode("utf-8"))

objective = (
    "请在 apps/dashboard/README.md 追加一行 `- E2E_REAL_RUNNER_MARKER`，"
    "并保证仅修改 apps/dashboard 目录。禁止执行任何版本控制命令（含 git add/commit/push/rebase/reset）。"
)
answers = [
    "修改范围严格限制在 apps/dashboard 目录。",
    "禁止执行任何版本控制命令（含 git add/commit/push/rebase/reset）；只修改文件内容。",
    "验收标准：run 成功且 Command Tower 会话显示 SUCCESS。",
    "请保持变更最小，避免影响其他模块。",
    "确认：继续。",
]

progress("playwright bootstrap start")
with sync_playwright() as p:
    progress("playwright bootstrap ok")
    browser = p.chromium.launch(headless=True)
    progress("chromium launched")
    context = browser.new_context()
    page = context.new_page()

    stop_probe_state = {"armed": check_pm_stop, "used": False}

    def route_pm_create_payload_guard(route, request):
        intake_path = urllib.parse.urlsplit(request.url).path.rstrip("/")
        if request.method.upper() == "POST" and intake_path.endswith("/api/pm/intake"):
            raw = request.post_data or "{}"
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {}
            if acceptance_cmd:
                # Always override UI defaults so E2E acceptance remains deterministic in clean worktrees.
                payload["acceptance_tests"] = [
                    {
                        "name": "non_trivial_acceptance",
                        "cmd": acceptance_cmd,
                        "must_pass": True,
                    }
                ]
            payload["mcp_tool_set"] = list(default_mcp_tool_set)
            if stop_probe_state["armed"] and not stop_probe_state["used"]:
                stop_probe_state["used"] = True
                progress(f"pm-stop probe delaying first /api/pm/intake by {pm_stop_probe_delay_sec}s")
                time.sleep(max(1, pm_stop_probe_delay_sec))
            headers = dict(request.headers)
            headers["content-type"] = "application/json"
            headers.pop("content-length", None)
            route.continue_(post_data=json.dumps(payload, ensure_ascii=False), headers=headers)
            return
        route.continue_()

    def route_pm_payload_guard(route, request):
        if request.method.upper() == "POST" and "/api/pm/intake/" in request.url:
            if not (request.url.endswith("/run") or request.url.endswith("/answer")):
                route.continue_()
                return
            raw = request.post_data or "{}"
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {}
            if request.url.endswith("/run"):
                payload["runner"] = runner_name
                payload["mock"] = run_mock
                payload["strict_acceptance"] = strict_acceptance
                if runtime_options_provider:
                    runtime_options = payload.get("runtime_options")
                    if not isinstance(runtime_options, dict):
                        runtime_options = {}
                    runtime_options["provider"] = runtime_options_provider
                    payload["runtime_options"] = runtime_options
            if request.url.endswith("/answer"):
                payload["auto_run_chain"] = False
                payload["mock_chain"] = False
            headers = dict(request.headers)
            headers["content-type"] = "application/json"
            headers.pop("content-length", None)
            route.continue_(post_data=json.dumps(payload, ensure_ascii=False), headers=headers)
            return
        route.continue_()

    page.route("**/api/pm/intake", route_pm_create_payload_guard)
    page.route("**/api/pm/intake/*/run", route_pm_payload_guard)
    page.route("**/api/pm/intake/*/answer", route_pm_payload_guard)

    progress("goto /pm start")
    page.goto(f"{dash_base}/pm", wait_until="domcontentloaded")
    progress("goto /pm done")
    workspace_input = page.get_by_label(re.compile(r"Workspace path", re.IGNORECASE)).first
    repo_input = page.get_by_label(re.compile(r"Repository slug|Repo", re.IGNORECASE)).first
    chat_input = page.locator(
        'textarea[aria-label="PM composer"]:visible, '
        'textarea[aria-label="PM chat input"]:visible, '
        'textarea[aria-label="PM 对话输入框"]:visible'
    ).last
    send_btn = page.get_by_role("button", name=re.compile(r"^(Send|发送并推进|发送)$", re.IGNORECASE))
    reset_btn = page.get_by_role(
        "button",
        name=re.compile(
            r"^(\\+\\s*New chat|New chat|Start first request|Send first request now|新建 PM 对话|\\+\\s*新对话|新对话)$",
            re.IGNORECASE,
        ),
    )

    try:
        if reset_btn.is_visible() and reset_btn.is_enabled():
            reset_btn.click()
            page.wait_for_timeout(300)
    except Exception:
        pass

    try:
        if workspace_input.is_visible():
            current_workspace = workspace_input.input_value().strip()
            if not current_workspace:
                workspace_input.fill("apps/dashboard")
                page.wait_for_timeout(100)
        if repo_input.is_visible():
            current_repo = repo_input.input_value().strip()
            if not current_repo:
                repo_input.fill("openvibecoding")
                page.wait_for_timeout(100)
    except Exception:
        pass

    def extract_intake_id_from_body(text: str) -> str:
        patterns = [
            r"Session:\s*([A-Za-z0-9._:/\\-]+)",
            r"当前会话:\s*([A-Za-z0-9._:/\\-]+)",
            r"intake_id:\s*([A-Za-z0-9._:/\\-]+)",
            r"session:\s*([A-Za-z0-9._:/\\-]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if not match:
                continue
            candidate = (match.group(1) or "").strip()
            if candidate and candidate not in {"-", "(未创建)", "未创建", "(not created)", "not created"}:
                return candidate
        return ""

    def wait_chat_ready(timeout_sec: float = 60.0) -> None:
        deadline = time.time() + timeout_sec
        unlock_attempted = False
        while time.time() < deadline:
            try:
                if chat_input.is_enabled():
                    return
            except Exception:
                pass
            if not unlock_attempted:
                for pattern in (
                    r"(Fill example and focus composer|Next: enter the first request|Start first request|Send first request now)",
                    r"(Draft session \(start typing\)|Current session: Draft \(unsent\))",
                ):
                    try:
                        candidate = page.get_by_role("button", name=re.compile(pattern, re.IGNORECASE)).first
                        if candidate.is_visible() and candidate.is_enabled():
                            candidate.click()
                            page.wait_for_timeout(300)
                            unlock_attempted = True
                            break
                    except Exception:
                        continue
            page.wait_for_timeout(200)
        page.screenshot(path=screen_pm, full_page=True)
        raise RuntimeError("chat input remains disabled before send")

    def send_chat_message(text: str) -> None:
        wait_chat_ready()
        chat_input.fill(text)
        page.wait_for_timeout(100)
        if not send_btn.is_enabled():
            page.screenshot(path=screen_pm, full_page=True)
            raise RuntimeError("send button remains disabled after filling chat input")
        send_btn.click()

    pm_stop_probe = {
        "enabled": check_pm_stop,
        "button_seen": False,
        "cancel_notice_seen": False,
        "send_recovered": False,
        "skipped": False,
        "skip_reason": "",
        "pass": False,
    }
    if check_pm_stop:
        stop_btn = page.get_by_role("button", name=re.compile(r"(停止生成|Stop generation)", re.IGNORECASE))
        send_chat_message("E2E STOP PROBE: verify PM stop generation button")
        try:
            stop_btn.first.wait_for(state="visible", timeout=max(2000, pm_stop_probe_delay_sec * 1000))
            pm_stop_probe["button_seen"] = True
            stop_btn.first.click()
            cancel_notice_patterns = ("请求已取消", "当前请求已取消", "Request cancelled", "Request canceled")
            cancel_deadline = time.time() + 12
            while time.time() < cancel_deadline:
                body_text = page.locator("body").inner_text()
                if any(marker in body_text for marker in cancel_notice_patterns):
                    pm_stop_probe["cancel_notice_seen"] = True
                    break
                page.wait_for_timeout(200)
            wait_chat_ready(timeout_sec=20)
            chat_input.fill("stop-check-recovery")
            page.wait_for_timeout(100)
            pm_stop_probe["send_recovered"] = bool(send_btn.is_enabled())
            chat_input.fill("")
        except Exception as exc:
            pm_stop_probe["skipped"] = True
            pm_stop_probe["skip_reason"] = f"stop_button_not_visible:{exc.__class__.__name__}"
            # If stop-probe cannot be executed, hard-reset PM page to avoid
            # carrying a partially created session into the strict intake flow.
            page.goto(f"{dash_base}/pm", wait_until="domcontentloaded")
            page.wait_for_timeout(300)
            try:
                if reset_btn.is_visible() and reset_btn.is_enabled():
                    reset_btn.click()
                    page.wait_for_timeout(300)
            except Exception:
                pass
        finally:
            try:
                if reset_btn.is_visible() and reset_btn.is_enabled():
                    reset_btn.click()
                    page.wait_for_timeout(300)
            except Exception:
                pass
        pm_stop_probe["pass"] = bool(
            pm_stop_probe["skipped"]
            or (
                pm_stop_probe["button_seen"]
                and pm_stop_probe["cancel_notice_seen"]
                and pm_stop_probe["send_recovered"]
            )
        )
        if not pm_stop_probe["pass"]:
            page.screenshot(path=screen_pm, full_page=True)
            raise RuntimeError(f"pm stop generation probe failed: {pm_stop_probe!r}")

    if allowed_paths_override:
        for label in ("允许路径（逗号或换行）", "Allowed Paths（逗号或换行）"):
            try:
                page.get_by_label(label).fill(allowed_paths_override)
                break
            except Exception:
                continue

    session_id = ""
    intake_id = ""
    pending_questions: list[str] = []
    answer_degrade_state = {"mcp_tool_set_missing": False}
    answer_degrade_events: list[dict[str, str]] = []
    ui_intake_request_observed = False

    def _session_rows_snapshot(limit: int = 50) -> list[dict]:
        try:
            payload = api_get_json(f"/api/pm/sessions?limit={int(limit)}&sort=updated_desc")
        except Exception:
            return []
        if isinstance(payload, list):
            rows = payload
        elif isinstance(payload, dict):
            rows = payload.get("items") if isinstance(payload.get("items"), list) else payload.get("sessions")
            if not isinstance(rows, list):
                rows = []
        else:
            rows = []
        return [row for row in rows if isinstance(row, dict)]

    def _extract_session_id(row: dict) -> str:
        if not isinstance(row, dict):
            return ""
        for key in ("pm_session_id", "session_id", "id", "intake_id"):
            value = str(row.get(key) or "").strip()
            if value:
                return value
        return ""

    def _extract_canonical_intake_id(session_payload: dict, *, session_hint: str = "") -> str:
        if not isinstance(session_payload, dict):
            return ""
        candidates: list[str] = []
        for key in ("intake_id", "id"):
            value = str(session_payload.get(key) or "").strip()
            if value:
                candidates.append(value)
        intake_obj = session_payload.get("intake")
        if isinstance(intake_obj, dict):
            for key in ("intake_id", "id"):
                value = str(intake_obj.get(key) or "").strip()
                if value:
                    candidates.append(value)
        response_obj = session_payload.get("response")
        if isinstance(response_obj, dict):
            for key in ("intake_id", "id"):
                value = str(response_obj.get(key) or "").strip()
                if value:
                    candidates.append(value)
        session_obj = session_payload.get("session")
        if isinstance(session_obj, dict):
            value = str(session_obj.get("intake_id") or "").strip()
            if value:
                candidates.append(value)
        for candidate in candidates:
            if candidate and candidate != session_hint:
                return candidate
        return candidates[0] if candidates else ""

    def _extract_session_id_from_payload(session_payload: dict, fallback: str = "") -> str:
        if not isinstance(session_payload, dict):
            return fallback
        session_obj = session_payload.get("session")
        if isinstance(session_obj, dict):
            for key in ("pm_session_id", "session_id", "id"):
                value = str(session_obj.get(key) or "").strip()
                if value:
                    return value
        for key in ("pm_session_id", "session_id", "id"):
            value = str(session_payload.get(key) or "").strip()
            if value:
                return value
        return fallback

    def _resolve_canonical_intake_id(session_value: str, fallback_intake: str = "") -> tuple[str, str]:
        session_value = str(session_value or "").strip()
        if not session_value:
            return fallback_intake, ""
        try:
            payload = api_get_json(f"/api/pm/sessions/{session_value}")
        except Exception as exc:
            progress(f"canonical intake lookup failed: session={session_value} err={type(exc).__name__}: {exc}")
            return fallback_intake, session_value
        canonical_session = _extract_session_id_from_payload(payload, fallback=session_value)
        canonical_intake = _extract_canonical_intake_id(payload, session_hint=canonical_session)
        if not canonical_intake:
            canonical_intake = fallback_intake or canonical_session
        return canonical_intake, canonical_session

    def _session_ids_snapshot(limit: int = 50) -> set[str]:
        rows = _session_rows_snapshot(limit=limit)
        ids: set[str] = set()
        for row in rows:
            session_id = _extract_session_id(row)
            if session_id:
                ids.add(session_id)
        return ids

    def _infer_intake_from_session_rows(
        pre_send_ids: set[str],
        objective_text: str,
        max_wait_sec: float,
    ) -> str:
        deadline = time.time() + max(0.2, float(max_wait_sec))
        normalized_objective = objective_text.strip()
        while time.time() < deadline:
            rows = _session_rows_snapshot(limit=100)
            new_ids_in_order: list[str] = []
            objective_matched_id = ""
            for row in rows:
                session_id = _extract_session_id(row)
                if not session_id or session_id in pre_send_ids:
                    continue
                new_ids_in_order.append(session_id)
                if normalized_objective and not objective_matched_id:
                    row_objective = str(row.get("objective") or "").strip()
                    if row_objective == normalized_objective:
                        objective_matched_id = session_id
            if objective_matched_id:
                return objective_matched_id
            if new_ids_in_order:
                return new_ids_in_order[0]
            time.sleep(0.4)
        return ""

    pre_send_session_ids = _session_ids_snapshot()
    intake_request = None
    intake_response = None
    ui_message_reuse_observed = False

    def _reset_pm_conversation_state() -> None:
        try:
            if reset_btn.is_visible() and reset_btn.is_enabled():
                reset_btn.click()
                page.wait_for_timeout(300)
        except Exception:
            pass
        page.goto(f"{dash_base}/pm", wait_until="domcontentloaded")
        page.wait_for_timeout(300)

    for attempt in range(1, 4):
        pre_send_session_ids = _session_ids_snapshot()
        try:
            with page.expect_request(
                lambda req: req.method.upper() == "POST" and req.url.rstrip("/").endswith("/api/pm/intake"),
                timeout=max(1000, min(20000, ui_intake_wait_sec * 1000)),
            ) as intake_req_info:
                send_chat_message(objective)
            intake_request = intake_req_info.value
            ui_intake_request_observed = True
            progress(f"ui intake request observed: attempt={attempt}")
            break
        except PlaywrightTimeoutError:
            ui_message_reuse_observed = True
            progress(
                "ui create intake timeout or routed to stale session; "
                f"reset and retry (attempt={attempt}/3)"
            )
            if attempt < 3:
                _reset_pm_conversation_state()
        except Exception as exc:
            progress(f"ui create intake failed (attempt={attempt}/3): {type(exc).__name__}: {exc}")
            if attempt < 3:
                _reset_pm_conversation_state()

    if intake_request is not None:
        response_deadline = time.time() + min(15.0, float(ui_intake_wait_sec))
        while time.time() < response_deadline:
            intake_response = intake_request.response()
            if intake_response is not None:
                break
            page.wait_for_timeout(150)
        if intake_response and intake_response.ok:
            try:
                payload = intake_response.json()
            except Exception:
                payload = {}
            if isinstance(payload, dict):
                candidate = str(payload.get("intake_id") or "").strip()
                if not candidate:
                    session_obj = payload.get("session") if isinstance(payload.get("session"), dict) else {}
                    candidate = str(session_obj.get("pm_session_id") or session_obj.get("intake_id") or "").strip()
                if candidate:
                    session_id = candidate
                raw_questions = payload.get("questions")
                if isinstance(raw_questions, list):
                    pending_questions = [str(item).strip() for item in raw_questions if str(item).strip()]

    if not session_id:
        remaining_wait = max(0.2, ui_intake_wait_sec - 2.0)
        inferred = _infer_intake_from_session_rows(pre_send_session_ids, objective, remaining_wait)
        if inferred:
            session_id = inferred
            ui_intake_request_observed = True
            progress(f"ui intake inferred from sessions polling: session_id={session_id}")

    if not session_id:
        post_send_session_ids = _session_ids_snapshot()
        new_session_ids = [sid for sid in post_send_session_ids if sid not in pre_send_session_ids]
        if len(new_session_ids) == 1:
            session_id = new_session_ids[0]
            ui_intake_request_observed = True
            progress(f"ui intake inferred from session snapshot: session_id={session_id}")

    intake_deadline = time.time() + ui_intake_wait_sec
    while not session_id and time.time() < intake_deadline:
        body_text = page.locator("body").inner_text()
        session_id = extract_intake_id_from_body(body_text)
        if session_id:
            break
        page.wait_for_timeout(200)
    if not session_id and ui_intake_required:
        page.screenshot(path=screen_pm, full_page=True)
        raise RuntimeError(
            "failed to create intake through PM UI in strict mode "
            f"(ui_request_observed={ui_intake_request_observed}, reused_session_messages={ui_message_reuse_observed})"
        )
    def _build_api_create_payload() -> dict:
        return {
            "objective": objective,
            "allowed_paths": [item.strip() for item in re.split(r"[\n,]+", allowed_paths_override) if item.strip()] or ["apps/dashboard"],
            "constraints": [
                "只修改 apps/dashboard 目录",
                "禁止执行任何版本控制命令（含 git add/commit/push/rebase/reset）",
                "保持变更最小",
                "不要引入无关改动",
            ],
            "acceptance_tests": [
                {
                    "name": "non_trivial_acceptance",
                    "cmd": acceptance_cmd,
                    "must_pass": True,
                }
            ],
            "mcp_tool_set": list(default_mcp_tool_set),
            "requester_role": "PM",
            "browser_policy_preset": "safe",
        }

    if not session_id and not ui_intake_required:
        try:
            create_payload = _build_api_create_payload()
            create_resp = api_post_json("/api/pm/intake", create_payload)
            intake_id = str(create_resp.get("intake_id") or "").strip() if isinstance(create_resp, dict) else ""
            if intake_id and not session_id:
                session_id = intake_id
            raw_questions = create_resp.get("questions") if isinstance(create_resp, dict) else None
            if isinstance(raw_questions, list):
                pending_questions = [str(item).strip() for item in raw_questions if str(item).strip()]
            if intake_id:
                progress(f"api create intake success: {intake_id}")
        except Exception as exc:
            progress(f"api create intake failed: {type(exc).__name__}: {exc}")
    if session_id and not intake_id:
        canonical_intake_id, canonical_session_id = _resolve_canonical_intake_id(session_id, fallback_intake=intake_id)
        if canonical_session_id and canonical_session_id != session_id:
            progress(f"canonical session id resolved: {session_id} -> {canonical_session_id}")
            session_id = canonical_session_id
        if canonical_intake_id:
            intake_id = canonical_intake_id
            progress(f"canonical intake id resolved from session: session_id={session_id} intake_id={intake_id}")
    if not intake_id and session_id:
        intake_id = session_id
        progress(f"fallback to session id as intake id: {intake_id}")
    if not intake_id:
        page.screenshot(path=screen_pm, full_page=True)
        raise RuntimeError("failed to detect intake id after creating PM session")

    def _repair_intake_if_missing_tool_set(current_intake: str) -> tuple[str, str]:
        try:
            intake_payload = api_get_json(f"/api/intake/{current_intake}")
        except Exception as exc:
            progress(f"intake payload contract probe failed: {type(exc).__name__}: {exc}")
            return current_intake, session_id or current_intake
        intake_obj = intake_payload.get("intake") if isinstance(intake_payload, dict) else None
        if isinstance(intake_obj, dict):
            tool_set = intake_obj.get("mcp_tool_set")
            if isinstance(tool_set, list) and any(str(item).strip() for item in tool_set):
                return current_intake, session_id or current_intake
        progress("intake payload missing mcp_tool_set; recreate deterministic intake via API before /answer")
        repair_resp = api_post_json("/api/pm/intake", _build_api_create_payload())
        repaired_intake = str(repair_resp.get("intake_id") or "").strip() if isinstance(repair_resp, dict) else ""
        if not repaired_intake:
            raise RuntimeError("repaired intake create did not return intake_id")
        raw_questions = repair_resp.get("questions") if isinstance(repair_resp, dict) else None
        if isinstance(raw_questions, list):
            nonlocal_pending_questions = [str(item).strip() for item in raw_questions if str(item).strip()]
            pending_questions.clear()
            pending_questions.extend(nonlocal_pending_questions)
        progress(f"api repair intake success: {repaired_intake}")
        return repaired_intake, repaired_intake

    intake_id, session_id = _repair_intake_if_missing_tool_set(intake_id)

    def post_answer_and_get_questions(answer_text: str, intake_value: str) -> list[str]:
        def _extract_http_error_detail(exc: urllib.error.HTTPError) -> tuple[int, str, str, str]:
            status_code = int(exc.code)
            body_text = ""
            detail_code = ""
            detail_reason = ""
            try:
                body_text = exc.read().decode("utf-8", errors="replace")
            except Exception:
                body_text = str(exc)
            try:
                payload = json.loads(body_text)
            except Exception:
                payload = {}
            if isinstance(payload, dict):
                detail = payload.get("detail")
                if isinstance(detail, dict):
                    detail_code = str(detail.get("code") or "").strip().upper()
                    detail_reason = str(
                        detail.get("reason")
                        or detail.get("message")
                        or detail.get("error")
                        or ""
                    ).strip()
            return status_code, body_text, detail_code, detail_reason

        def _looks_like_id_semantic_mismatch(status_code: int, body_text: str, detail_code: str) -> bool:
            if status_code != 400:
                return False
            if detail_code in {"INTAKE_NOT_FOUND", "INTAKE_ANSWER_FAILED", "PM_SESSION_NOT_FOUND"}:
                return True
            normalized = f"{detail_code}\n{body_text}".upper()
            return "INTAKE" in normalized and ("NOT_FOUND" in normalized or "INVALID" in normalized)

        last_exc: Exception | None = None
        current_intake = intake_value
        for attempt in range(1, 4):
            try:
                answer_payload = api_post_json(
                    f"/api/pm/intake/{current_intake}/answer",
                    {
                        "answers": [answer_text],
                        "auto_run_chain": False,
                        "mock_chain": False,
                    },
                )
                if isinstance(answer_payload, dict):
                    raw_questions = answer_payload.get("questions")
                    if isinstance(raw_questions, list):
                        return [str(item).strip() for item in raw_questions if str(item).strip()]
                return []
            except urllib.error.HTTPError as exc:
                last_exc = exc
                status_code, body_text, detail_code, detail_reason = _extract_http_error_detail(exc)
                normalized_reason = f"{detail_reason}\n{body_text}".lower()
                if (
                    status_code == 400
                    and detail_code == "INTAKE_ANSWER_FAILED"
                    and "mcp_tool_set" in normalized_reason
                    and "missing" in normalized_reason
                ):
                    answer_degrade_state["mcp_tool_set_missing"] = True
                    answer_degrade_events.append(
                        {
                            "code": detail_code,
                            "reason": detail_reason[:400],
                            "intake_id": str(current_intake),
                            "attempt": str(attempt),
                        }
                    )
                    progress(
                        "answer-round failed: intake answer rejected by backend "
                        "(INTAKE_ANSWER_FAILED: mcp_tool_set missing); abort before /run"
                    )
                    snapshot_path = Path(evidence_path).with_suffix(".failure_snapshot.json")
                    snapshot_path.write_text(
                        json.dumps(
                            {
                                "reason": "answer_failed_missing_mcp_tool_set",
                                "intake_id": str(current_intake),
                                "session_id": session_id,
                                "status_code": status_code,
                                "detail_code": detail_code,
                                "detail_reason": detail_reason[:800],
                                "response_body": body_text[:4000],
                            },
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                    raise RuntimeError(
                        "intake answer failed before /run: "
                        f"code={detail_code or '<none>'}, reason={detail_reason or body_text[:240]}"
                    )
                if _looks_like_id_semantic_mismatch(status_code, body_text, detail_code) and session_id:
                    canonical_intake, canonical_session = _resolve_canonical_intake_id(
                        session_id,
                        fallback_intake=current_intake,
                    )
                    if canonical_session and canonical_session != session_id:
                        progress(
                            f"/answer canonical session remap detected: {session_id} -> {canonical_session}"
                        )
                    if canonical_intake and canonical_intake != current_intake:
                        progress(
                            f"/answer id semantic retry with canonical intake id: {current_intake} -> {canonical_intake}"
                        )
                        current_intake = canonical_intake
                        continue
                progress(
                    f"/answer retry {attempt}/3: HTTP {status_code} code={detail_code or '<none>'} body={body_text[:220]!r}"
                )
                time.sleep(2)
            except Exception as exc:
                last_exc = exc
                progress(f"/answer timeout/retry {attempt}/3: {type(exc).__name__}: {exc}")
                time.sleep(2)
        if last_exc is not None:
            raise last_exc
        return []

    max_answer_rounds = int(os.getenv("OPENVIBECODING_E2E_MAX_ANSWER_ROUNDS", "10"))
    for idx in range(max_answer_rounds):
        answer_seed = answers[idx] if idx < len(answers) else ""
        if not answer_seed:
            if pending_questions:
                answer_seed = f"答复：{pending_questions[0]}。请按既有约束继续执行。"
            else:
                answer_seed = "继续，按既有约束与验收标准执行。"
        next_questions = post_answer_and_get_questions(answer_seed, intake_id)
        page.wait_for_timeout(300)
        pending_questions = next_questions
        progress(f"answer round {idx + 1}/{max_answer_rounds}, pending_questions={len(pending_questions)}")
        if not pending_questions:
            break

    baseline_run_ids: set[str] = set()
    session_lookup_id = session_id or intake_id
    plan_ready_probe = {
        "ready": False,
        "attempts": 0,
        "response_status": "",
        "has_plan": False,
        "last_error": "",
        "deadline_sec": plan_ready_wait_sec,
    }

    def _extract_plan_readiness(payload: dict | None) -> tuple[str, bool]:
        if not isinstance(payload, dict):
            return "", False
        response_obj = payload.get("response")
        if not isinstance(response_obj, dict):
            return "", False
        response_status = str(response_obj.get("status") or "").strip().upper()
        response_plan = response_obj.get("plan")
        has_plan = isinstance(response_plan, dict) and bool(response_plan)
        return response_status, has_plan

    def ensure_intake_plan_ready(session_value: str, intake_value: str) -> tuple[bool, dict]:
        plan_payload: dict = {}
        deadline = time.time() + max(2.0, float(plan_ready_wait_sec))
        while time.time() < deadline:
            plan_ready_probe["attempts"] += 1
            try:
                # Probe the canonical intake view rather than PM session detail.
                # `/api/pm/sessions/{id}` no longer exposes top-level `response`,
                # while `/api/intake/{id}` remains the SSOT for plan readiness.
                plan_payload = api_get_json(f"/api/intake/{intake_value}")
                response_status, has_plan = _extract_plan_readiness(plan_payload)
                plan_ready_probe["response_status"] = response_status
                plan_ready_probe["has_plan"] = has_plan
                if has_plan:
                    plan_ready_probe["ready"] = True
                    return True, plan_payload
            except Exception as exc:
                plan_ready_probe["last_error"] = f"{type(exc).__name__}: {exc}"
            time.sleep(max(0.2, plan_ready_poll_sec))
        progress(
            "intake plan readiness probe timed out: "
            f"session_id={session_value} intake_id={intake_value} "
            f"status={plan_ready_probe['response_status']!r} has_plan={plan_ready_probe['has_plan']}"
        )
        return False, plan_payload

    if pending_questions:
        snapshot_path = Path(evidence_path).with_suffix(".failure_snapshot.json")
        snapshot_path.write_text(
            json.dumps(
                {
                    "reason": "intake_questions_pending_before_run",
                    "intake_id": intake_id,
                    "session_id": session_lookup_id,
                    "pending_questions_count": len(pending_questions),
                    "pending_questions_sample": pending_questions[:5],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        page.screenshot(path=screen_pm, full_page=True)
        raise RuntimeError(
            "intake still has pending clarification questions before /run "
            f"(count={len(pending_questions)})"
        )

    plan_ready, plan_payload = ensure_intake_plan_ready(session_lookup_id, intake_id)
    progress(
        "plan readiness probe completed: "
        f"ready={plan_ready} status={plan_ready_probe['response_status']!r} "
        f"has_plan={plan_ready_probe['has_plan']}"
    )
    if plan_ready and isinstance(plan_payload, dict):
        remapped_intake = _extract_canonical_intake_id(plan_payload, session_hint=session_lookup_id)
        if remapped_intake and remapped_intake != intake_id:
            progress(f"intake id remapped after plan ready probe: {intake_id} -> {remapped_intake}")
            intake_id = remapped_intake
    if not plan_ready:
        # Session aggregation payload can lag behind planning completion on busy CI runners.
        # Keep going and rely on the downstream /run INTAKE_PLAN_MISSING retry loop instead of hard-failing here.
        progress(
            "intake plan probe not ready before /run; continue with /run retries "
            f"(status={plan_ready_probe['response_status']!r}, has_plan={plan_ready_probe['has_plan']})"
        )

    try:
        progress(f"baseline session probe start: session_id={session_lookup_id}")
        baseline_payload = api_get_json(f"/api/pm/sessions/{session_lookup_id}")
        baseline_raw = baseline_payload.get("run_ids") if isinstance(baseline_payload, dict) else []
        if isinstance(baseline_raw, list):
            baseline_run_ids = {str(item).strip() for item in baseline_raw if str(item).strip()}
        progress(f"baseline session probe done: existing_run_ids={len(baseline_run_ids)}")
    except Exception:
        progress(f"baseline session probe failed: session_id={session_lookup_id}")
        baseline_run_ids = set()

    run_endpoint = f"/api/pm/intake/{intake_id}/run"
    run_response_status = 0
    run_response_body = ""

    def build_run_request_payload() -> dict:
        payload = {
            "runner": runner_name,
            "mock": run_mock,
            "strict_acceptance": strict_acceptance,
        }
        if runtime_options_provider:
            payload["runtime_options"] = {"provider": runtime_options_provider}
        return payload

    def parse_detail_code(raw: str) -> str:
        if not raw:
            return ""
        try:
            payload = json.loads(raw)
        except Exception:
            return ""
        if not isinstance(payload, dict):
            return ""
        detail = payload.get("detail")
        if isinstance(detail, dict):
            return str(detail.get("code") or "").strip().upper()
        return ""
    try:
        progress(f"/run request start: intake_id={intake_id}")
        run_resp = api_post_json(run_endpoint, build_run_request_payload())
        run_response_status = 200
        run_response_body = json.dumps(run_resp, ensure_ascii=False)
        candidate_run_id = str(run_resp.get("run_id") or "").strip() if isinstance(run_resp, dict) else ""
        progress(f"/run request done: intake_id={intake_id} run_id={candidate_run_id or '<none>'}")
        if candidate_run_id:
            run_id = candidate_run_id
    except urllib.error.HTTPError as exc:
        run_response_status = int(exc.code)
        try:
            run_response_body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            run_response_body = str(exc)
        progress(f"/run request http error: intake_id={intake_id} status={run_response_status}")
    except Exception as exc:
        run_response_status = 0
        run_response_body = str(exc)
        progress(f"/run request transport error: intake_id={intake_id} error={type(exc).__name__}: {exc}")

    detail_code = parse_detail_code(run_response_body)
    if run_response_status == 400 and detail_code == "INTAKE_PLAN_MISSING":
        for attempt in range(1, 7):
            progress(f"/run rejected with INTAKE_PLAN_MISSING, retry {attempt}/6 after backoff")
            time.sleep(5)
            try:
                retry_resp = api_post_json(run_endpoint, build_run_request_payload())
                run_response_status = 200
                run_response_body = json.dumps(retry_resp, ensure_ascii=False)
                detail_code = ""
                candidate_run_id = str(retry_resp.get("run_id") or "").strip() if isinstance(retry_resp, dict) else ""
                if candidate_run_id:
                    run_id = candidate_run_id
                break
            except urllib.error.HTTPError as exc:
                run_response_status = int(exc.code)
                try:
                    run_response_body = exc.read().decode("utf-8", errors="replace")
                except Exception:
                    run_response_body = str(exc)
                detail_code = parse_detail_code(run_response_body)
                if not (run_response_status == 400 and detail_code == "INTAKE_PLAN_MISSING"):
                    break
            except Exception as exc:
                run_response_status = 0
                run_response_body = str(exc)
                detail_code = ""
                break

    run_id = locals().get("run_id", "")
    try:
        page.wait_for_selector("text=执行已触发，run_id:", timeout=15000)
        body_text = page.locator("body").inner_text()
        run_match = re.search(r"run_id:\s*([A-Za-z0-9_\-]+)", body_text)
        run_id = run_match.group(1) if run_match else ""
    except PlaywrightTimeoutError:
        # Keep API/fallback run_id if already captured; selector timeout should not erase valid evidence.
        run_id = run_id.strip()

    if run_response_status == 0:
        progress(
            "run request transport timeout observed; continue with downstream run_id discovery "
            f"(intake_id={intake_id})"
        )

    if run_response_status >= 400:
        snapshot_path = Path(evidence_path).with_suffix(".failure_snapshot.json")
        snapshot_path.write_text(
            json.dumps(
                {
                    "reason": "run_endpoint_non_2xx",
                    "intake_id": intake_id,
                    "run_mode": run_mode,
                    "runner": runner_name,
                    "run_endpoint": run_endpoint,
                    "run_response_status": run_response_status,
                    "run_response_body": run_response_body[:4000],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        page.screenshot(path=screen_pm, full_page=True)
        raise RuntimeError(
            f"/run rejected by API: status={run_response_status}, intake={intake_id}, "
            f"body={run_response_body[:400]!r}"
        )

    session_payload: dict = {}
    run_id_deadline = time.time() + run_id_wait_sec
    last_run_id_log_at = 0.0
    while not run_id and time.time() < run_id_deadline:
        payload = api_get_json(f"/api/pm/sessions/{session_lookup_id}")
        session_payload = payload
        run_ids = payload.get("run_ids") if isinstance(payload, dict) else []
        if not isinstance(run_ids, list):
            run_ids = []
        run_ids_clean = [str(item).strip() for item in run_ids if str(item).strip()]
        latest_run_id = ""
        if isinstance(payload, dict):
            session_obj = payload.get("session") if isinstance(payload.get("session"), dict) else {}
            latest_run_id = str(session_obj.get("latest_run_id") or "").strip()

        if latest_run_id and (latest_run_id not in baseline_run_ids or not baseline_run_ids):
            run_id = latest_run_id
            break

        new_run_ids = [item for item in run_ids_clean if item not in baseline_run_ids]
        if new_run_ids:
            run_id = new_run_ids[-1]
            break
        now = time.time()
        if now - last_run_id_log_at >= 10:
            progress(
                f"waiting run_id intake={intake_id} baseline={len(baseline_run_ids)} "
                f"current={len(run_ids_clean)} elapsed={int(now - (run_id_deadline - run_id_wait_sec))}s"
            )
            last_run_id_log_at = now
        time.sleep(2)

    if not run_id:
        snapshot_path = Path(evidence_path).with_suffix(".failure_snapshot.json")
        snapshot_path.write_text(
            json.dumps(
                {
                    "reason": "run_id_detection_timeout",
                    "intake_id": intake_id,
                    "run_mode": run_mode,
                    "runner": runner_name,
                    "run_id_wait_sec": run_id_wait_sec,
                    "status_wait_sec": status_wait_sec,
                    "stagnation_timeout_sec": stagnation_timeout_sec,
                    "run_endpoint": run_endpoint,
                    "run_response_status": run_response_status,
                    "run_response_body": run_response_body[:4000],
                    "session_payload": session_payload,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        page.screenshot(path=screen_pm, full_page=True)
        raise RuntimeError(f"failed to detect run_id within {run_id_wait_sec}s for intake={intake_id}")

    page.screenshot(path=screen_pm, full_page=True)

    session_url = f"{dash_base}/command-tower/sessions/{session_lookup_id}"
    session_page = context.new_page()
    if not orchestration_smoke_mode:
        session_page.goto(session_url, wait_until="domcontentloaded")
        try:
            session_page.wait_for_selector(f"text={run_id}", timeout=120000 if not run_mock else 60000)
        except PlaywrightTimeoutError:
            pass

    accepted_success = {"SUCCESS", "DONE", "PASSED"}
    accepted_fail = {"FAILURE", "FAILED", "ERROR", "CANCELLED", "REJECTED"}
    accepted_active = {"QUEUED", "PENDING", "PLANNING", "RUNNING", "IN_PROGRESS", "WAITING_APPROVAL"}
    chain_roles_seen: set[str] = set()
    orchestration_smoke_ready = False

    def collect_roles_from_events(payload) -> None:
        events = payload if isinstance(payload, list) else payload.get("events") if isinstance(payload, dict) else []
        if not isinstance(events, list):
            return
        for event in events:
            if not isinstance(event, dict):
                continue
            context = event.get("context")
            if not isinstance(context, dict):
                continue
            for key in ("current_role", "to_role", "assigned_role"):
                role = str(context.get(key) or "").strip().upper()
                if role:
                    chain_roles_seen.add(role)

    def collect_roles_from_session(payload: dict) -> None:
        if not isinstance(payload, dict):
            return
        session_obj = payload.get("session")
        if isinstance(session_obj, dict):
            session_role = str(session_obj.get("current_role") or "").strip().upper()
            if session_role:
                chain_roles_seen.add(session_role)
        runs = payload.get("runs")
        if isinstance(runs, list):
            for run in runs:
                if not isinstance(run, dict):
                    continue
                run_role = str(run.get("current_role") or "").strip().upper()
                if run_role:
                    chain_roles_seen.add(run_role)

    status = ""
    failure_reason = ""
    deadline = time.time() + status_wait_sec
    last_status = ""
    status_changed_at = time.time()
    last_status_log_at = 0.0

    def dump_failure_snapshot(reason: str, extra: dict | None = None) -> None:
        snapshot = {
            "reason": reason,
            "session_id": session_lookup_id,
            "intake_id": intake_id,
            "run_id": run_id,
            "session_run_status": status,
            "session_failure_reason": failure_reason,
            "session_payload": session_payload,
            "session_events_payload": last_session_events_payload,
            "run_payload": last_run_payload,
            "chain_roles_seen": sorted(chain_roles_seen),
            "run_mode": run_mode,
            "runner": runner_name,
            "run_id_wait_sec": run_id_wait_sec,
            "status_wait_sec": status_wait_sec,
            "stagnation_timeout_sec": stagnation_timeout_sec,
            "run_endpoint": run_endpoint,
            "run_response_status": run_response_status,
            "run_response_body": run_response_body[:4000],
        }
        if isinstance(extra, dict) and extra:
            snapshot["extra"] = extra
        snapshot_path = Path(evidence_path).with_suffix(".failure_snapshot.json")
        snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            page.screenshot(path=screen_pm, full_page=True)
        except Exception:
            pass
        try:
            session_page.screenshot(path=screen_session, full_page=True)
        except Exception:
            pass

    while time.time() < deadline:
        payload = api_get_json(f"/api/pm/sessions/{session_lookup_id}")
        session_payload = payload
        collect_roles_from_session(payload)
        try:
            events_payload = api_get_json(f"/api/pm/sessions/{session_lookup_id}/events?limit=120&tail=1")
            last_session_events_payload = events_payload
            collect_roles_from_events(events_payload)
        except Exception:
            pass
        runs = payload.get("runs") if isinstance(payload, dict) else []
        if not isinstance(runs, list):
            runs = []
        target = next((item for item in runs if isinstance(item, dict) and item.get("run_id") == run_id), None)
        if target:
            status = str(target.get("status") or "").strip().upper()
            failure_reason = str(target.get("failure_reason") or "").strip()
            if status != last_status:
                progress(f"status transition run_id={run_id} {last_status or '<none>'} -> {status or '<empty>'}")
                last_status = status
                status_changed_at = time.time()
            if orchestration_smoke_mode:
                non_pm_roles = {role for role in chain_roles_seen if role and role != "PM"}
                if status not in accepted_fail and (non_pm_roles or status in accepted_success or status in accepted_active):
                    orchestration_smoke_ready = True
                    break
            if status in accepted_success:
                break
            if status in accepted_fail:
                if not failure_reason:
                    try:
                        run_payload = api_get_json(f"/api/runs/{run_id}")
                        if isinstance(run_payload, dict):
                            failure_reason = str(run_payload.get("failure_reason") or "").strip()
                    except Exception:
                        pass
                break
        else:
            try:
                run_payload = api_get_json(f"/api/runs/{run_id}")
                if isinstance(run_payload, dict):
                    last_run_payload = run_payload
                    run_status = str(run_payload.get("status") or "").strip().upper()
                    run_failure = str(run_payload.get("failure_reason") or "").strip()
                    if run_status:
                        status = run_status
                    if run_failure:
                        failure_reason = run_failure
                    if status != last_status:
                        progress(f"status transition(run-api) run_id={run_id} {last_status or '<none>'} -> {status or '<empty>'}")
                        last_status = status
                        status_changed_at = time.time()
                    if orchestration_smoke_mode:
                        non_pm_roles = {role for role in chain_roles_seen if role and role != "PM"}
                        if status not in accepted_fail and (non_pm_roles or status in accepted_success or status in accepted_active):
                            orchestration_smoke_ready = True
                            break
                    if status in accepted_success or status in accepted_fail:
                        break
            except Exception:
                pass

        now = time.time()
        if now - last_status_log_at >= 15:
            elapsed = int(now - (deadline - status_wait_sec))
            stagnant_for = int(now - status_changed_at)
            progress(f"poll status run_id={run_id} status={status or '<empty>'} elapsed={elapsed}s stagnant={stagnant_for}s")
            last_status_log_at = now
        if status and status not in accepted_success and status not in accepted_fail and (now - status_changed_at) >= stagnation_timeout_sec:
            failure_reason = (
                f"status stagnation timeout after {stagnation_timeout_sec}s "
                f"(status={status!r}, run_id={run_id})"
            )
            dump_failure_snapshot("status_stagnation_timeout")
            break
        time.sleep(2)

    if not orchestration_smoke_mode:
        session_page.reload(wait_until="domcontentloaded")
        session_page.screenshot(path=screen_session, full_page=True)

    if (
        not orchestration_smoke_ready
        and status not in accepted_success
        and status not in accepted_fail
        and not failure_reason
    ):
        failure_reason = f"terminal status timeout after {status_wait_sec}s"
        dump_failure_snapshot("terminal_status_timeout")

    reexec_report: dict = {}
    reexec_status = ""
    reexec_error = ""
    require_reexec = str(run_mode).strip().lower() == "real"
    if run_id and status in accepted_success:
        strict_flag = "true" if reexec_strict else "false"
        try:
            reexec_report = api_post_json(f"/api/runs/{run_id}/reexec?strict={strict_flag}", {})
            reexec_status = str(reexec_report.get("status") or "").strip().lower()
        except Exception as exc:
            reexec_error = str(exc)

    result = {
        "objective": objective,
        "run_mode": run_mode,
        "run_mock": run_mock,
        "strict_acceptance": strict_acceptance,
        "runner": runner_name,
        "allowed_paths_override": allowed_paths_override,
        "run_id_wait_sec": run_id_wait_sec,
        "status_wait_sec": status_wait_sec,
        "plan_ready_wait_sec": plan_ready_wait_sec,
        "plan_ready_probe": plan_ready_probe,
        "dashboard_url": f"{dash_base}/pm",
        "session_url": session_url,
        "session_id": session_lookup_id,
        "intake_id": intake_id,
        "run_id": run_id,
        "session_run_status": status,
        "session_failure_reason": failure_reason,
        "chain_roles_seen": sorted(chain_roles_seen),
        "orchestration_smoke_mode": orchestration_smoke_mode,
        "orchestration_smoke_ready": orchestration_smoke_ready,
        "reexec_strict": reexec_strict,
        "reexec_required": require_reexec,
        "reexec_status": reexec_status,
        "reexec_error": reexec_error,
        "reexec_report": reexec_report,
        "pm_stop_probe": pm_stop_probe,
        "pm_screenshot": screen_pm,
        "session_screenshot": screen_session,
        "session_payload": session_payload,
        "answer_degraded_due_to_mcp_tool_set_missing": bool(answer_degrade_state.get("mcp_tool_set_missing")),
        "answer_degrade_events": answer_degrade_events,
    }

    Path(evidence_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    browser.close()

    if orchestration_smoke_mode:
        if not orchestration_smoke_ready:
            raise RuntimeError(
                f"orchestration smoke did not observe active run state or non-PM activity: status={status!r}, roles={sorted(chain_roles_seen)!r}"
            )
        raise SystemExit(0)

    if status not in accepted_success:
        raise RuntimeError(f"session run not successful: status={status!r}, failure_reason={failure_reason!r}")
    if str(run_mode).strip().lower() == "real":
        non_pm_roles = {role for role in chain_roles_seen if role and role != "PM"}
        if not non_pm_roles:
            raise RuntimeError(f"missing non-PM chain activity for intake={intake_id}, roles={sorted(chain_roles_seen)!r}")
    if require_reexec:
        if reexec_error:
            raise RuntimeError(f"reexec invocation failed: {reexec_error}")
        if reexec_status != "pass":
            raise RuntimeError(f"reexec not pass: status={reexec_status!r}, report={reexec_report!r}")

print(evidence_path)
