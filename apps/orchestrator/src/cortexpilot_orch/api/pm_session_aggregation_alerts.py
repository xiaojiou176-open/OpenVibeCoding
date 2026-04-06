from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable


_ParseTsOrNoneFn = Callable[[Any], datetime | None]


def compute_failure_trend_30m(
    contexts: list[dict[str, Any]],
    *,
    failed_statuses: set[str],
    parse_ts_or_none_fn: _ParseTsOrNoneFn,
) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
    count = 0
    for context in contexts:
        for run in context.get("runs", []):
            status = str(run.get("status") or "").strip().upper()
            if status not in failed_statuses:
                continue
            ts = parse_ts_or_none_fn(run.get("finished_at") or run.get("last_event_ts") or run.get("created_at"))
            if ts is not None and ts >= cutoff:
                count += 1
    return count


def command_tower_ratios(total_sessions: int, failed_sessions: int, blocked_sessions: int) -> tuple[float, float]:
    if total_sessions <= 0:
        return 0.0, 0.0
    failed_ratio = round((failed_sessions / total_sessions), 4)
    blocked_ratio = round((blocked_sessions / total_sessions), 4)
    return failed_ratio, blocked_ratio


def build_command_tower_alerts(overview: dict[str, Any]) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []

    total_sessions = int(overview.get("total_sessions") or 0)
    active_sessions = int(overview.get("active_sessions") or 0)
    blocked_sessions = int(overview.get("blocked_sessions") or 0)
    failure_trend = int(overview.get("failure_trend_30m") or 0)
    failed_ratio = float(overview.get("failed_ratio") or 0.0)

    if failed_ratio >= 0.3 and total_sessions > 0:
        alerts.append(
            {
                "code": "COMMAND_TOWER_SLO_BREACH",
                "severity": "critical",
                "message": f"Failed ratio {failed_ratio:.2%} exceeds target 30%",
                "suggested_action": "Reduce live interval and inspect top blockers first.",
            }
        )
    if blocked_sessions > 0:
        alerts.append(
            {
                "code": "COMMAND_TOWER_BLOCKED_SESSIONS",
                "severity": "warning",
                "message": f"{blocked_sessions} blocked sessions need attention.",
                "suggested_action": "Open blocker panel and resolve HUMAN_APPROVAL_REQUIRED runs.",
            }
        )
    if failure_trend > 0:
        alerts.append(
            {
                "code": "COMMAND_TOWER_FAILURE_TREND_SPIKE",
                "severity": "warning",
                "message": f"Failure trend in last 30m: {failure_trend}",
                "suggested_action": "Inspect session timeline for latest failed handoffs.",
            }
        )
    if active_sessions >= 20:
        alerts.append(
            {
                "code": "COMMAND_TOWER_HIGH_CONCURRENCY",
                "severity": "info",
                "message": f"High concurrency detected: {active_sessions} active sessions.",
                "suggested_action": "Enable adaptive polling safeguards for non-critical panels.",
            }
        )

    return alerts
