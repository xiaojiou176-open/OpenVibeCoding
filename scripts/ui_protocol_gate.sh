#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

MODE="${CORTEXPILOT_UI_PROTOCOL_MODE:-gate}"
if [[ "${1:-}" == "--mode" ]]; then
  MODE="${2:-}"
  shift 2
fi
if [[ "$MODE" != "warn" && "$MODE" != "gate" ]]; then
  echo "❌ [ui-protocol] invalid mode: $MODE (expected warn|gate)"
  exit 2
fi

FAIL_ON_WARN="${CORTEXPILOT_UI_PROTOCOL_FAIL_ON_WARN:-0}"
ALLOWLIST_PATH="${CORTEXPILOT_UI_PROTOCOL_ALLOWLIST:-docs/governance/ui_protocol_allowlist.json}"
REPORT_DIR=".runtime-cache/test_output/ui_protocol"
REPORT_JSON="${REPORT_DIR}/ui_protocol_gate.json"
REPORT_MD="${REPORT_DIR}/ui_protocol_gate.md"
mkdir -p "$REPORT_DIR"

echo "🚀 [ui-protocol] running UI/UX static protocol gate (mode=$MODE)"

python3 - <<'PY' "$ROOT_DIR" "$REPORT_JSON" "$REPORT_MD" "$MODE" "$FAIL_ON_WARN" "$ALLOWLIST_PATH"
from __future__ import annotations

import json
import pathlib
import re
import sys
from datetime import date, datetime
from dataclasses import asdict, dataclass

root = pathlib.Path(sys.argv[1])
report_json = pathlib.Path(sys.argv[2])
report_md = pathlib.Path(sys.argv[3])
mode = sys.argv[4]
fail_on_warn = sys.argv[5] == "1"
allowlist_path = pathlib.Path(sys.argv[6])

allowed_spacing = {"0", "4", "6", "8", "12", "16", "24", "32", "48", "64"}
spacing_prop_re = re.compile(
    r"^\s*(margin|margin-top|margin-right|margin-bottom|margin-left|padding|padding-top|padding-right|padding-bottom|padding-left|gap|row-gap|column-gap)\s*:\s*([^;]+);"
)
px_number_re = re.compile(r"(-?\d+(?:\.\d+)?)px")
hex_color_re = re.compile(r"#[0-9a-fA-F]{3,8}\b")
rgb_color_re = re.compile(r"rgb(a)?\(")
div_onclick_re = re.compile(r"<div[^>]*\bonClick=")
token_decl_re = re.compile(r"^\s*--[\w-]+\s*:")
inline_style_re = re.compile(r"<[A-Za-z][^>]*\sstyle=\{")
button_text_re = re.compile(r"<Button[^>]*>([^<]+)</Button>|<button[^>]*>([^<]+)</button>")
button_block_re = re.compile(r"<(?:Button|button)\b[^>]*>(.*?)</(?:Button|button)>", re.S)
anchor_block_re = re.compile(r"<a\b[^>]*className=\"[^\"]*btn[^\"]*\"[^>]*>(.*?)</a>", re.S)
raw_button_tag_re = re.compile(r"<button\b")
raw_btn_class_re = re.compile(r"className=\{?(?:\"[^\"]*(?:^|\s)btn(?:\s|$)[^\"]*\"|'[^']*(?:^|\s)btn(?:\s|$)[^']*')")
raw_primitive_class_re = re.compile(
    r"className=\{?(?:\"[^\"]*(?:^|\s)(?:card|badge|input)(?:\s|$)[^\"]*\"|'[^']*(?:^|\s)(?:card|badge|input)(?:\s|$)[^']*'|`[^`]*(?:^|\s)(?:card|badge|input)(?:\s|$)[^`]*`)"
)
raw_button_with_btn_helper_re = re.compile(
    r"<button\b[\s\S]{0,600}?className=\{[\s\S]{0,200}?\b(?:buttonClasses|buttonVariants|btnClasses|getButtonClassNames)\s*\(",
    re.S,
)
raw_input_tag_re = re.compile(r"<input\b[\s\S]{0,400}?>", re.S)
raw_textarea_tag_re = re.compile(r"<textarea\b[\s\S]{0,400}?>", re.S)
input_type_attr_re = re.compile(r"type\s*=\s*(?:\"([^\"]+)\"|'([^']+)'|\{([^}]+)\})")
enter_send_handler_re = re.compile(r"onKeyDown=\{\(event\)\s*=>\s*\{[\s\S]{0,500}?event\.key\s*===\s*\"Enter\"[\s\S]{0,500}?!event\.shiftKey")
pm_abort_signal_re = re.compile(r"AbortController|chatAbortRef|\.abort\(")
input_restore_re = re.compile(r"setChatInput\(message\)")
session_scope_re = re.compile(r"chatLogBySession")
desktop_cancel_runtime_re = re.compile(r"pendingReplyRef|clearTimeout\(")
action_verb_re = re.compile(r"(发起|查看|处理|开始|继续|输入|更新|重试|去|打开|创建|填写|回答)")

scan_roots = [root / "apps/dashboard", root / "apps/desktop"]
exclude_parts = {
    "node_modules",
    ".next",
    "dist",
    "build",
    ".runtime-cache",
    "coverage",
    "lcov-report",
    "src-tauri/target",
    "target",
}

blocking_rules = {
    "semantic-html",
    "microcopy",
    "a11y-focus",
    "state-coverage",
    "focus-outline",
    "chat-core",
    "shadcn-primitive",
    "input-primitive",
}
warning_rules = {
    "spacing-scale",
    "color-token",
    "allowlist-stale",
    "inline-style",
    "microcopy-weak",
    "primary-density",
    "chat-advanced",
}

@dataclass
class Violation:
    rule: str
    severity: str
    file: str
    line: int
    detail: str


violations: list[Violation] = []
suppressed_violations: list[Violation] = []


@dataclass
class AllowlistEntry:
    rule: str
    file: str
    line: int | None
    detail_contains: str | None
    reason: str
    issue: str
    expires_on: date
    raw_index: int


def rel(path: pathlib.Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def add(rule: str, path: pathlib.Path, line: int, detail: str) -> None:
    severity = "blocking" if rule in blocking_rules else "warning"
    violations.append(Violation(rule=rule, severity=severity, file=rel(path), line=line, detail=detail))


def add_raw(rule: str, file: str, line: int, detail: str) -> None:
    severity = "blocking" if rule in blocking_rules else "warning"
    violations.append(Violation(rule=rule, severity=severity, file=file, line=line, detail=detail))


textual_input_types = {
    "text",
    "email",
    "search",
    "url",
    "tel",
    "password",
    "number",
}
semantic_input_exclusions = {
    "checkbox",
    "radio",
}


def extract_literal_input_type(raw_tag: str) -> str | None:
    match = input_type_attr_re.search(raw_tag)
    if not match:
        return ""
    inline_type = (match.group(1) or match.group(2) or "").strip().lower()
    if inline_type:
        return inline_type
    dynamic_expr = (match.group(3) or "").strip()
    if not dynamic_expr:
        return ""
    if (
        (dynamic_expr.startswith("\"") and dynamic_expr.endswith("\""))
        or (dynamic_expr.startswith("'") and dynamic_expr.endswith("'"))
    ):
        return dynamic_expr[1:-1].strip().lower()
    return None


def is_raw_text_input_bypass(raw_tag: str) -> bool:
    input_type = extract_literal_input_type(raw_tag)
    if input_type is None:
        return False
    if input_type == "":
        # HTML <input> defaults to type="text".
        return True
    if input_type in semantic_input_exclusions:
        return False
    return input_type in textual_input_types


def parse_allowlist(raw: object) -> tuple[list[AllowlistEntry], list[str]]:
    errors: list[str] = []
    entries: list[AllowlistEntry] = []
    if raw is None:
        return entries, errors
    if not isinstance(raw, dict):
        errors.append("allowlist root must be object with `entries` list")
        return entries, errors
    items = raw.get("entries", [])
    if not isinstance(items, list):
        errors.append("allowlist `entries` must be list")
        return entries, errors
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            errors.append(f"entries[{idx}] must be object")
            continue
        rule = str(item.get("rule", "")).strip()
        file = str(item.get("file", "")).strip().replace("\\", "/")
        reason = str(item.get("reason", "")).strip()
        issue = str(item.get("issue", "")).strip()
        expires = str(item.get("expires_on", "")).strip()
        line_raw = item.get("line")
        detail_contains = item.get("detail_contains")
        if not rule or not file or not reason or not issue or not expires:
            errors.append(f"entries[{idx}] missing required fields (rule,file,reason,issue,expires_on)")
            continue
        if line_raw is not None and (not isinstance(line_raw, int) or line_raw <= 0):
            errors.append(f"entries[{idx}] line must be positive int when provided")
            continue
        if detail_contains is not None and not isinstance(detail_contains, str):
            errors.append(f"entries[{idx}] detail_contains must be string when provided")
            continue
        try:
            expires_on = datetime.strptime(expires, "%Y-%m-%d").date()
        except ValueError:
            errors.append(f"entries[{idx}] expires_on must be YYYY-MM-DD")
            continue
        entries.append(
            AllowlistEntry(
                rule=rule,
                file=file,
                line=line_raw,
                detail_contains=detail_contains.strip() if isinstance(detail_contains, str) else None,
                reason=reason,
                issue=issue,
                expires_on=expires_on,
                raw_index=idx,
            )
        )
    return entries, errors


def matches_allowlist(v: Violation, entry: AllowlistEntry) -> bool:
    if v.rule != entry.rule:
        return False
    if v.file != entry.file:
        return False
    if entry.line is not None and v.line != entry.line:
        return False
    if entry.detail_contains and entry.detail_contains not in v.detail:
        return False
    return True


def should_skip(path: pathlib.Path) -> bool:
    p = rel(path)
    normalized = pathlib.PurePosixPath(p)
    if any(part in p for part in exclude_parts):
        return True
    if "tests" in normalized.parts or "__tests__" in normalized.parts:
        return True
    if normalized.name.endswith((".test.ts", ".test.tsx", ".test.js", ".test.jsx", ".spec.ts", ".spec.tsx", ".spec.js", ".spec.jsx")):
        return True
    return False


def collect_files(patterns: list[str]) -> list[pathlib.Path]:
    out: list[pathlib.Path] = []
    for scan_root in scan_roots:
        if not scan_root.exists():
            continue
        for pattern in patterns:
            for file in scan_root.rglob(pattern):
                if file.is_file() and not should_skip(file):
                    out.append(file)
    return sorted(set(out), key=lambda p: rel(p))


def collect_source_bundle(
    sources: list[pathlib.Path],
    patterns: tuple[str, ...] = ("*.ts", "*.tsx", "*.js", "*.jsx"),
) -> tuple[pathlib.Path | None, list[pathlib.Path], str]:
    files: list[pathlib.Path] = []
    for source in sources:
        if source.is_file():
            if not should_skip(source):
                files.append(source)
            continue
        if not source.is_dir():
            continue
        for pattern in patterns:
            for file in source.rglob(pattern):
                if file.is_file() and not should_skip(file):
                    files.append(file)
    ordered = sorted(set(files), key=lambda p: rel(p))
    text = "\n".join(path.read_text(encoding="utf-8") for path in ordered)
    anchor = ordered[0] if ordered else None
    return anchor, ordered, text


tsx_files = collect_files(["*.tsx", "*.jsx"])
css_files = collect_files(["*.css"])

# 1) TSX/JSX protocol checks: no div onClick, no lorem ipsum.
for file in tsx_files:
    text = file.read_text(encoding="utf-8")
    primary_button_count = 0
    file_rel = rel(file)
    dashboard_governed_surface = (
        (
            file_rel.startswith("apps/dashboard/app/")
            or file_rel.startswith("apps/dashboard/components/")
        )
        and not file_rel.startswith("apps/dashboard/components/ui/")
    )
    desktop_governed_surface = (
        file_rel.startswith("apps/desktop/src/App.tsx")
        or file_rel.startswith("apps/desktop/src/pages/")
        or file_rel.startswith("apps/desktop/src/features/")
        or file_rel.startswith("apps/desktop/src/components/")
    ) and not file_rel.startswith("apps/desktop/src/components/ui/")
    primitive_governed_surface = dashboard_governed_surface or desktop_governed_surface
    governed_surface_label = "Dashboard" if dashboard_governed_surface and not desktop_governed_surface else "Desktop" if desktop_governed_surface and not dashboard_governed_surface else "Dashboard/Desktop"
    if primitive_governed_surface:
        for raw_button_match in raw_button_tag_re.finditer(text):
            line_no = text.count("\n", 0, raw_button_match.start()) + 1
            add(
                "shadcn-primitive",
                file,
                line_no,
                f"{governed_surface_label} governed surfaces must use Button primitive instead of raw `<button>`.",
            )
        for helper_match in raw_button_with_btn_helper_re.finditer(text):
            line_no = text.count("\n", 0, helper_match.start()) + 1
            add(
                "shadcn-primitive",
                file,
                line_no,
                f"{governed_surface_label} governed surfaces must use Button primitive instead of raw `<button>` with button-style helper classes.",
            )
        for raw_input_match in raw_input_tag_re.finditer(text):
            raw_input_tag = raw_input_match.group(0)
            if not is_raw_text_input_bypass(raw_input_tag):
                continue
            line_no = text.count("\n", 0, raw_input_match.start()) + 1
            add(
                "input-primitive",
                file,
                line_no,
                f"{governed_surface_label} governed surfaces must use Input primitive instead of raw text-like `<input>`.",
            )
        for raw_textarea_match in raw_textarea_tag_re.finditer(text):
            line_no = text.count("\n", 0, raw_textarea_match.start()) + 1
            add(
                "input-primitive",
                file,
                line_no,
                f"{governed_surface_label} governed surfaces must use Textarea primitive instead of raw `<textarea>`.",
            )
    for line_no, line in enumerate(text.splitlines(), start=1):
        if div_onclick_re.search(line):
            add("semantic-html", file, line_no, "Use semantic interactive elements instead of <div onClick>.")
        if (
            primitive_governed_surface
            and raw_btn_class_re.search(line)
            and "<Button" not in line
            and "<button" not in line
        ):
            add(
                "shadcn-primitive",
                file,
                line_no,
                f"{governed_surface_label} governed surfaces must use Button primitive instead of raw `className=\"btn...\"`.",
            )
        if (
            primitive_governed_surface
            and raw_primitive_class_re.search(line)
            and "<Card" not in line
            and "<Badge" not in line
            and "<Input" not in line
            and "<Select" not in line
            and "<Textarea" not in line
            and "<card" not in line
            and "<badge" not in line
            and "<input" not in line
            and "<select" not in line
            and "<textarea" not in line
        ):
            add(
                "shadcn-primitive",
                file,
                line_no,
                f"{governed_surface_label} governed surfaces must use Card/Badge/Input primitives instead of raw `className` tokens.",
            )
        if "lorem ipsum" in line.lower():
            add("microcopy", file, line_no, "Placeholder lorem ipsum text is forbidden.")
        if inline_style_re.search(line):
            add("inline-style", file, line_no, "Inline style detected; prefer tokens/classes unless value is runtime-calculated.")
        if 'variant="primary"' in line:
            primary_button_count += line.count('variant="primary"')
        if "className=" in line and "ui-button-primary" in line:
            primary_button_count += 1
        if "点击这里" in line or "了解更多" in line:
            add("microcopy-weak", file, line_no, "Weak link copy detected; use concrete action labels.")
        if ">OK<" in line or ">Submit<" in line or ">确定<" in line:
            add("microcopy-weak", file, line_no, "Weak button copy detected; use verb-led, task-specific labels.")
        for button_match in button_text_re.finditer(line):
            text_node = (button_match.group(1) or button_match.group(2) or "").strip()
            if text_node in {"OK", "Submit", "确定"}:
                add("microcopy-weak", file, line_no, f"Weak button copy `{text_node}` is forbidden.")
    if primary_button_count > 5:
        add(
            "primary-density",
            file,
            1,
            f"Detected {primary_button_count} primary-style buttons in one file; review visual hierarchy and action prioritization.",
        )


# 2) CSS checks: spacing scale + hardcoded color outside token declarations.
for css_file in css_files:
    lines = css_file.read_text(encoding="utf-8").splitlines()
    for line_no, line in enumerate(lines, start=1):
        m = spacing_prop_re.search(line)
        if m:
            value = m.group(2)
            for px_match in px_number_re.finditer(value):
                raw = px_match.group(1)
                if raw.startswith("-"):
                    # Accessibility helpers (e.g. visually-hidden) may rely on negative offsets.
                    continue
                normalized = raw.lstrip("-")
                if normalized not in allowed_spacing:
                    add(
                        "spacing-scale",
                        css_file,
                        line_no,
                        f"Spacing value {raw}px is outside allowed scale {sorted(allowed_spacing)}.",
                    )

        if hex_color_re.search(line) or rgb_color_re.search(line):
            # allow token declarations (design token definitions)
            if token_decl_re.search(line):
                continue
            add("color-token", css_file, line_no, "Hardcoded color found outside token declaration.")
        compact_line = line.lower().replace(" ", "")
        if "outline:none" in compact_line:
            add("focus-outline", css_file, line_no, "Forbidden `outline: none` detected without guaranteed focus replacement.")


# 3) Focus-visible baseline check.
focus_visible_count = 0
for css_file in css_files:
    text = css_file.read_text(encoding="utf-8")
    focus_visible_count += text.count(":focus-visible")
if focus_visible_count == 0 and css_files:
    add("a11y-focus", css_files[0], 1, "No :focus-visible style found in frontend CSS.")


# 4) Key screen state coverage heuristics.
pm_page = root / "apps/dashboard/app/pm/page.tsx"
pm_components_dir = root / "apps/dashboard/app/pm/components"
pm_feature_anchor = pm_components_dir / "PMIntakeFeature.tsx"
pm_anchor, pm_sources, pm_text = collect_source_bundle([pm_page, pm_components_dir])
if pm_feature_anchor in pm_sources:
    pm_anchor = pm_feature_anchor
session_live = root / "apps/dashboard/components/command-tower/CommandTowerSessionLive.tsx"
session_drawer = root / "apps/dashboard/components/command-tower/CommandTowerSessionDrawer.tsx"
session_panels = root / "apps/dashboard/components/command-tower/CommandTowerSessionPanels.tsx"
session_anchor, _session_sources, session_text = collect_source_bundle([session_live, session_drawer, session_panels])
if session_live.exists():
    session_anchor = session_live
desktop_app = root / "apps/desktop/src/App.tsx"
desktop_chat_panel = root / "apps/desktop/src/components/conversation/ChatPanel.tsx"
desktop_state_view = root / "apps/desktop/src/components/ui/StateView.tsx"

if pm_anchor is not None:
    required_pm_signals = [
        ("loading", ("正在加载历史会话", "Loading session history")),
        ("error", 'role="alert"'),
        ("empty", ("暂无历史会话", "No previous sessions yet")),
        ("disabled", "disabled={"),
        ("success", "alert-success"),
    ]
    for state_name, needle in required_pm_signals:
        if isinstance(needle, tuple):
            if not any(item in pm_text for item in needle):
                add("state-coverage", pm_anchor, 1, f"Missing PM state signal: {state_name} ({' | '.join(needle)}).")
            continue
        if needle not in pm_text:
            add("state-coverage", pm_anchor, 1, f"Missing PM state signal: {state_name} ({needle}).")

if session_anchor is not None:
    required_session_signals = [
        ("loading", ("正在刷新会话上下文", "Refreshing session context")),
        ("error", 'role="alert"'),
        ("empty", ("暂无事件时间线", "No event timeline yet")),
        ("disabled", "disabled={"),
        ("success", 'role="status"'),
    ]
    for state_name, needle in required_session_signals:
        if isinstance(needle, tuple):
            if not any(item in session_text for item in needle):
                add("state-coverage", session_anchor, 1, f"Missing session state signal: {state_name} ({' | '.join(needle)}).")
            continue
        if needle not in session_text:
            add("state-coverage", session_anchor, 1, f"Missing session state signal: {state_name} ({needle}).")

desktop_chat_sources = [path for path in (desktop_app, desktop_chat_panel) if path.exists()]
desktop_chat_text = "\n".join(path.read_text(encoding="utf-8") for path in desktop_chat_sources)
desktop_chat_anchor = desktop_chat_sources[0] if desktop_chat_sources else None

if desktop_chat_anchor is not None:
    required_desktop_signals = [
        ("loading", ("正在同步会话数据", "Syncing session data")),
        ("error", 'role="alert"'),
        ("empty", ("当前会话暂无消息", "This session has no messages yet")),
        ("disabled", "composerInput.trim().length === 0"),
        ("success", 'role="status"'),
    ]
    for state_name, needle in required_desktop_signals:
        if isinstance(needle, tuple):
            if not any(item in desktop_chat_text for item in needle):
                add("state-coverage", desktop_chat_anchor, 1, f"Missing desktop app state signal: {state_name} ({' | '.join(needle)}).")
            continue
        if needle not in desktop_chat_text:
            add("state-coverage", desktop_chat_anchor, 1, f"Missing desktop app state signal: {state_name} ({needle}).")

if desktop_state_view.exists():
    text = desktop_state_view.read_text(encoding="utf-8")
    required_state_view_signals = [
        ("loading", "loading:"),
        ("error", "error:"),
        ("empty", "empty:"),
        ("disabled", "disabled:"),
        ("success", "success:"),
    ]
    for state_name, needle in required_state_view_signals:
        if needle not in text:
            add("state-coverage", desktop_state_view, 1, f"Missing StateView state signal: {state_name} ({needle}).")

# 4.1) First-run actionability guard (warning only).
def strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()

first_run_targets = [
    (root / "apps/dashboard/app/page.tsx", 3, []),
    (root / "apps/desktop/src/pages/OverviewPage.tsx", 3, []),
    (root / "apps/dashboard/app/pm/page.tsx", 2, [pm_components_dir]),
]
for target_file, min_actions, extra_sources in first_run_targets:
    if not target_file.exists():
        continue
    _target_anchor, _target_sources, text = collect_source_bundle([target_file, *extra_sources])
    action_count = 0
    for match in button_block_re.finditer(text):
        label = strip_tags(match.group(1))
        if label and action_verb_re.search(label):
            action_count += 1
    for match in anchor_block_re.finditer(text):
        label = strip_tags(match.group(1))
        if label and action_verb_re.search(label):
            action_count += 1
    if action_count < min_actions:
        # Fallback to relaxed text scan to avoid false negatives when JSX spans multi-lines.
        action_count = len(action_verb_re.findall(text))
    if action_count < min_actions:
        add(
            "microcopy-weak",
            target_file,
            1,
            f"First-run actionability weak: detected {action_count} verb-led actions, expected >= {min_actions}.",
        )

# 4.5) AI chat interface protocol checks (core + advanced).
if pm_anchor is not None:
    chat_core_pm = [
        ("chat-log-role", 'role="log"' in pm_text, 'role="log"'),
        ("chat-live-region", 'aria-live="polite"' in pm_text, 'aria-live="polite"'),
        ("chat-enter-send-handler", bool(enter_send_handler_re.search(pm_text)), 'onKeyDown Enter + !Shift handler'),
        ("chat-send-guard", "disabled={chatFlowBusy}" in pm_text, "disabled={chatFlowBusy}"),
        ("chat-cancel-runtime", bool(pm_abort_signal_re.search(pm_text)), "AbortController/chatAbortRef/.abort"),
        ("chat-error-recovery", bool(input_restore_re.search(pm_text)), "setChatInput(message)"),
        ("chat-session-isolation", bool(session_scope_re.search(pm_text)), "chatLogBySession"),
    ]
    for check_name, ok, detail in chat_core_pm:
        if not ok:
            add("chat-core", pm_anchor, 1, f"Missing PM chat core signal: {check_name} ({detail}).")

    chat_adv_pm = [
        ("chat-back-to-bottom", "回到底部" in pm_text or "Back to bottom" in pm_text, "回到底部|Back to bottom"),
        ("chat-cancel-control", "停止生成" in pm_text or "取消当前请求" in pm_text or "Stop generation" in pm_text or "Cancel current request" in pm_text, "停止生成|取消当前请求|Stop generation|Cancel current request"),
    ]
    for check_name, ok, detail in chat_adv_pm:
        if not ok:
            add("chat-advanced", pm_anchor, 1, f"Missing PM chat advanced signal: {check_name} ({detail}).")

if session_anchor is not None:
    chat_core_session = [
        ("chat-stream-runtime", "openEventsStream" in session_text, "openEventsStream"),
        ("chat-enter-hint", "Shift+Enter 换行" in session_text or "Shift+Enter for newlines" in session_text or "Shift+Enter for a newline" in session_text, "Shift+Enter 换行|Shift+Enter for newlines"),
        ("chat-input-guard", "disabled={" in session_text, "disabled={"),
        ("chat-error-surface", 'role="alert"' in session_text, 'role="alert"'),
    ]
    for check_name, ok, detail in chat_core_session:
        if not ok:
            add("chat-core", session_anchor, 1, f"Missing session chat core signal: {check_name} ({detail}).")

if desktop_chat_anchor is not None:
    chat_core_desktop = [
        ("chat-thread-region", "chat-thread" in desktop_chat_text, "chat-thread"),
        ("chat-log-role", 'role="log"' in desktop_chat_text, 'role="log"'),
        ("chat-live-region", 'aria-live="polite"' in desktop_chat_text, 'aria-live="polite"'),
        ("chat-busy-region", "aria-busy=" in desktop_chat_text, "aria-busy"),
        ("chat-composer-label", 'label htmlFor="desktop-chat-input"' in desktop_chat_text, 'label htmlFor="desktop-chat-input"'),
        ("chat-enter-send-handler", bool(enter_send_handler_re.search(desktop_chat_text)), 'onKeyDown Enter + !Shift handler'),
        ("chat-send-disabled", "hasActiveGeneration" in desktop_chat_text, "hasActiveGeneration"),
        ("chat-cancel-runtime", bool(desktop_cancel_runtime_re.search(desktop_chat_text)), "pendingReplyRef + clearTimeout"),
        ("chat-enter-hint", "Shift+Enter 换行" in desktop_chat_text or "Shift+Enter for newlines" in desktop_chat_text or "Shift+Enter for a new line" in desktop_chat_text, "Shift+Enter 换行|Shift+Enter for new line"),
    ]
    for check_name, ok, detail in chat_core_desktop:
        if not ok:
            add("chat-core", desktop_chat_anchor, 1, f"Missing desktop chat core signal: {check_name} ({detail}).")
    chat_adv_desktop = [
        ("chat-back-to-bottom", "回到底部" in desktop_chat_text or "Back to bottom" in desktop_chat_text, "回到底部|Back to bottom"),
        ("chat-cancel-control", "停止生成" in desktop_chat_text or "取消当前请求" in desktop_chat_text or "Stop generation" in desktop_chat_text or "Cancel current request" in desktop_chat_text, "停止生成|取消当前请求|Stop generation|Cancel current request"),
    ]
    for check_name, ok, detail in chat_adv_desktop:
        if not ok:
            add("chat-advanced", desktop_chat_anchor, 1, f"Missing desktop chat advanced signal: {check_name} ({detail}).")

# 5) Allowlist suppression with expiry checks.
allowlist_entries: list[AllowlistEntry] = []
allowlist_errors: list[str] = []
if allowlist_path.exists():
    try:
        raw_allowlist = json.loads(allowlist_path.read_text(encoding="utf-8"))
        allowlist_entries, allowlist_errors = parse_allowlist(raw_allowlist)
    except Exception as exc:
        allowlist_errors.append(f"failed to read allowlist: {exc}")

if allowlist_errors:
    for err in allowlist_errors:
        add_raw("state-coverage", str(allowlist_path).replace("\\", "/"), 1, f"Allowlist invalid: {err}")

if allowlist_entries:
    today = date.today()
    keep: list[Violation] = []
    matched_entry_indices: set[int] = set()
    for v in violations:
        matched = False
        for entry in allowlist_entries:
            if not matches_allowlist(v, entry):
                continue
            matched = True
            matched_entry_indices.add(entry.raw_index)
            if entry.expires_on < today:
                add_raw(
                    "state-coverage",
                    entry.file,
                    entry.line or 1,
                    f"Allowlist entry expired on {entry.expires_on.isoformat()} ({entry.issue}): {entry.reason}",
                )
            else:
                suppressed_violations.append(v)
            break
        if not matched:
            keep.append(v)
    violations = keep
    for entry in allowlist_entries:
        if entry.raw_index not in matched_entry_indices:
            add_raw(
                "allowlist-stale",
                entry.file,
                entry.line or 1,
                f"Allowlist entry is stale (no matching violation): {entry.issue} {entry.reason}",
            )

blocking_count = sum(1 for v in violations if v.severity == "blocking")
warning_count = sum(1 for v in violations if v.severity == "warning")
severity = "blocking" if blocking_count > 0 else "warning" if warning_count > 0 else "ok"

summary = {
    "mode": mode,
    "severity": severity,
    "fail_on_warn": fail_on_warn,
    "violation_count": len(violations),
    "blocking_count": blocking_count,
    "warning_count": warning_count,
    "violations": [asdict(v) for v in violations],
    "suppressed_count": len(suppressed_violations),
    "suppressed_violations": [asdict(v) for v in suppressed_violations],
    "allowlist": {
        "path": str(allowlist_path).replace("\\", "/"),
        "entry_count": len(allowlist_entries),
        "error_count": len(allowlist_errors),
    },
    "checked": {
        "roots": [str(p) for p in scan_roots],
        "tsx_files": [str(p) for p in tsx_files],
        "css_files": [str(p) for p in css_files],
        "focus_visible_count": focus_visible_count,
    },
    "allowed_spacing_scale_px": sorted(int(v) for v in allowed_spacing),
}

report_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

md_lines = [
    "# UI Protocol Gate Report",
    "",
    f"- mode: `{mode}`",
    f"- severity: `{severity}`",
    f"- violation_count: `{summary['violation_count']}`",
    f"- blocking_count: `{blocking_count}`",
    f"- warning_count: `{warning_count}`",
    f"- suppressed_count: `{len(suppressed_violations)}`",
    "",
    "## Violations",
    "",
]
if violations:
    for v in violations:
        md_lines.append(f"- [{v.severity}|{v.rule}] `{v.file}:{v.line}` {v.detail}")
else:
    md_lines.append("- none")
md_lines.extend(["", "## Suppressed", ""])
if suppressed_violations:
    for v in suppressed_violations:
        md_lines.append(f"- [{v.severity}|{v.rule}] `{v.file}:{v.line}` {v.detail}")
else:
    md_lines.append("- none")
report_md.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

print(f"report_json={report_json}")
print(f"report_md={report_md}")
print(f"severity={severity}")
print(f"blocking_count={blocking_count}")
print(f"warning_count={warning_count}")

if mode == "warn":
    sys.exit(0)
if blocking_count > 0:
    sys.exit(1)
if fail_on_warn and warning_count > 0:
    sys.exit(1)
PY

echo "✅ [ui-protocol] pass"
