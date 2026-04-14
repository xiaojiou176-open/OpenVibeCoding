from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "apps" / "dashboard" / "app"
RUNTIME_OUT = ROOT / ".runtime-cache" / "test_output" / "ui_full_gemini_audit"
RUNTIME_LOGS = ROOT / ".runtime-cache" / "logs" / "runtime"

PAGE_SCREEN_DIR = "pages"
INTERACTION_SCREEN_DIR = "interactions"

PROJECT_CONTEXT = """你正在审计 OpenVibeCoding Web Dashboard。

OpenVibeCoding 是一个“AI 管家/指挥塔”系统，核心目标是：
1. 让用户通过 PM 对话驱动任务编排（Discover/Clarify/Execute/Verify）。
2. 在 Command Tower 里实时监控会话、风险和执行链路。
3. 支持高风险操作（批准、拒绝、回滚、回放）且必须可审计。

本次审计任务不是“做设计灵感”，而是“产品级验收”：
1. 功能是否符合预期交互。
2. UI/UX 是否清晰、低认知负担、主次分明。
3. 状态反馈是否一致（加载/成功/失败/禁用）。
4. 文案是否行动导向，是否存在误导或歧义。

请严格基于给你的截图和交互上下文判断，不要编造不存在的信息。
"""

PAGE_ANALYSIS_PROMPT = """你是 OpenVibeCoding UI 审计官。请分析单页截图并输出 JSON（不要附加多余文本）。

输出 JSON Schema:
{
  "verdict": "pass|warn|fail",
  "confidence": 0.0-1.0,
  "summary": "一句话结论",
  "information_architecture": {
    "stage_clarity": "clear|partial|unclear",
    "primary_action_clarity": "clear|partial|unclear",
    "noise_level": "low|medium|high",
    "notes": "具体说明"
  },
  "visual_ux": {
    "hierarchy": "good|mixed|poor",
    "readability": "good|mixed|poor",
    "feedback_signal": "good|mixed|poor",
    "notes": "具体说明"
  },
  "issues": [
    {"severity":"critical|major|minor","title":"问题标题","detail":"问题细节"}
  ],
  "recommendations": [
    "可执行改进建议1",
    "可执行改进建议2"
  ]
}

要求:
1. 基于页面用途判断“是否达成该页面的任务目标”。
2. 必须指出最关键的 1-3 个问题（如果没有则写空数组）。
3. 建议要可执行，避免空泛描述。
4. 只有当问题会直接阻断核心任务路径（无法操作/状态错误/关键入口不可达/严重可访问性缺失）时，才可标记为 major 或 critical。
5. 对于“视觉偏好、信息密度、术语风格、可进一步优化建议”这类不阻断任务的项，请标记为 minor，并且页面 verdict 仍应为 pass。
"""

INTERACTION_ANALYSIS_PROMPT = """你是 OpenVibeCoding 交互验收官。你会收到一次按钮交互的前后截图与运行观察数据。请输出 JSON（不要附加多余文本）。

输出 JSON Schema:
{
  "verdict": "pass|warn|fail",
  "confidence": 0.0-1.0,
  "expected_match": "yes|partial|no",
  "summary": "一句话结论",
  "functional_assessment": {
    "state_change_visible": true,
    "feedback_present": true,
    "error_signal_quality": "good|mixed|poor",
    "notes": "说明"
  },
  "ux_assessment": {
    "affordance": "good|mixed|poor",
    "consistency": "good|mixed|poor",
    "cognitive_load": "low|medium|high",
    "notes": "说明"
  },
  "issues": [
    {"severity":"critical|major|minor","title":"问题标题","detail":"问题细节"}
  ],
  "recommendations": [
    "可执行改进建议1",
    "可执行改进建议2"
  ]
}

判定优先级:
1. 功能正确 > 反馈明确 > 视觉优化。
2. 如果功能未按预期，直接 fail 或 warn，不要粉饰。
"""

_RUNTIME_CLOSED_ERROR_MARKERS = (
    "has been closed",
    "target closed",
    "browser has been closed",
    "browser has disconnected",
    "context closed",
    "execution context was destroyed",
    "most likely because of a navigation",
)


class RuntimeBudgetExceeded(TimeoutError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", value).strip("_")
    return cleaned or "unknown"


def escape_css_attr(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def parse_json_response(text: str) -> dict[str, Any]:
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```[a-zA-Z]*\n?", "", candidate)
        candidate = candidate.rstrip("`").strip()
    try:
        payload = json.loads(candidate)
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass
    match = re.search(r"\{[\s\S]*\}", candidate)
    if not match:
        raise ValueError("gemini response is not valid json object")
    payload = json.loads(match.group(0))
    if not isinstance(payload, dict):
        raise ValueError("gemini response json is not object")
    return payload


def is_runtime_closed_error(exc: Exception | str) -> bool:
    msg = str(exc).lower()
    return any(token in msg for token in _RUNTIME_CLOSED_ERROR_MARKERS)
