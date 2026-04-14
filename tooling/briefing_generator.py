from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


@dataclass
class RunSummary:
    run_id: str
    event_counts: dict[str, int] = field(default_factory=dict)
    error_events: list[dict[str, Any]] = field(default_factory=list)
    warning_events: list[dict[str, Any]] = field(default_factory=list)
    last_status: str | None = None

    def add_event(self, event: dict[str, Any]) -> None:
        name = str(event.get("event", "UNKNOWN"))
        self.event_counts[name] = self.event_counts.get(name, 0) + 1
        level = str(event.get("level", "")).upper()
        if level == "ERROR":
            self.error_events.append(event)
        elif level == "WARN":
            self.warning_events.append(event)

        if name == "STATE_TRANSITION":
            status = event.get("context", {}).get("status")
            if isinstance(status, str):
                self.last_status = status


def _runs_root() -> Path:
    return Path(os.getenv("OPENVIBECODING_RUNS_ROOT", ".runtime-cache/openvibecoding/runs"))


def _parse_ts(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def _load_events(path: Path) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events


def _date_window_local(target_date: datetime) -> tuple[datetime, datetime]:
    local = target_date.astimezone()
    start = datetime(local.year, local.month, local.day, tzinfo=local.tzinfo)
    end = start + timedelta(days=1)
    return start, end


def _format_ts(value: datetime) -> str:
    return value.astimezone().isoformat(timespec="seconds")


def _summarize_events(
    runs_root: Path, start: datetime, end: datetime
) -> tuple[list[RunSummary], dict[str, int], int, int]:
    summaries: dict[str, RunSummary] = {}
    event_totals: dict[str, int] = {}
    error_count = 0
    warn_count = 0

    for events_path in runs_root.glob("*/events.jsonl"):
        for event in _load_events(events_path):
            ts_raw = str(event.get("ts", ""))
            ts = _parse_ts(ts_raw)
            if ts is None:
                continue
            local_ts = ts.astimezone()
            if not (start <= local_ts < end):
                continue

            run_id = str(event.get("run_id", ""))
            if not run_id:
                continue
            summary = summaries.setdefault(run_id, RunSummary(run_id))
            summary.add_event(event)

            name = str(event.get("event", "UNKNOWN"))
            event_totals[name] = event_totals.get(name, 0) + 1

            level = str(event.get("level", "")).upper()
            if level == "ERROR":
                error_count += 1
            elif level == "WARN":
                warn_count += 1

    return list(summaries.values()), event_totals, error_count, warn_count


def _top_items(counts: dict[str, int], limit: int = 6) -> list[tuple[str, int]]:
    return sorted(counts.items(), key=lambda item: item[1], reverse=True)[:limit]


def _select_errors(summaries: list[RunSummary], limit: int = 8) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for summary in summaries:
        for event in summary.error_events:
            errors.append(event)
    return errors[:limit]


def generate_briefing(
    runs_root: Path | None = None,
    target_date: datetime | None = None,
    output_path: Path | None = None,
) -> Path:
    if runs_root is None:
        runs_root = _runs_root()
    if target_date is None:
        target_date = datetime.now(timezone.utc) - timedelta(days=1)

    start, end = _date_window_local(target_date)
    summaries, totals, error_count, warn_count = _summarize_events(runs_root, start, end)

    total_runs = len(summaries)
    success = sum(1 for s in summaries if s.last_status == "SUCCESS")
    failure = sum(1 for s in summaries if s.last_status == "FAILURE")
    unknown = total_runs - success - failure

    top_events = _top_items(totals)
    top_errors = _select_errors(summaries)

    lines: list[str] = []
    lines.append(f"# Morning Briefing - {start.date().isoformat()}")
    lines.append("")
    lines.append(f"Window: {_format_ts(start)} ~ {_format_ts(end)}")
    lines.append(f"Runs root: {runs_root}")
    lines.append("")
    lines.append("## Overview")
    lines.append(f"- Runs: {total_runs} (SUCCESS {success} / FAILURE {failure} / UNKNOWN {unknown})")
    lines.append(f"- Events: {sum(totals.values())} (ERROR {error_count} / WARN {warn_count})")
    lines.append("")

    lines.append("## Top Event Types")
    if top_events:
        for name, count in top_events:
            lines.append(f"- {name}: {count}")
    else:
        lines.append("- No events in window")
    lines.append("")

    lines.append("## Failures Snapshot")
    failure_runs = [s for s in summaries if s.last_status == "FAILURE"]
    if failure_runs:
        for summary in failure_runs[:10]:
            reason = summary.error_events[-1].get("event") if summary.error_events else "UNKNOWN"
            lines.append(f"- {summary.run_id}: {reason}")
    else:
        lines.append("- None")
    lines.append("")

    lines.append("## Notable Errors")
    if top_errors:
        for event in top_errors:
            rid = event.get("run_id", "")
            name = event.get("event", "")
            ctx = event.get("context", {})
            ctx_str = json.dumps(ctx, ensure_ascii=False)
            lines.append(f"- {rid} | {name} | {ctx_str}")
    else:
        lines.append("- None")
    lines.append("")

    lines.append("## Runs Touched")
    if summaries:
        for summary in summaries[:15]:
            lines.append(f"- {summary.run_id}")
    else:
        lines.append("- None")
    lines.append("")

    if output_path is None:
        output_path = Path(".runtime-cache/openvibecoding/briefings")
        output_path.mkdir(parents=True, exist_ok=True)
        output_path = output_path / f"briefing_{start.date().isoformat()}.md"
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a OpenVibeCoding morning briefing.")
    parser.add_argument("--runs-root", default=".runtime-cache/openvibecoding/runs")
    parser.add_argument(
        "--date",
        default="",
        help="Target date in YYYY-MM-DD (local time). Default: yesterday.",
    )
    parser.add_argument("--output", default="")
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    runs_root = Path(args.runs_root)
    if args.date:
        try:
            target_date = datetime.fromisoformat(args.date)
        except ValueError:
            raise SystemExit("Invalid --date. Expected YYYY-MM-DD.")
    else:
        target_date = datetime.now(timezone.utc) - timedelta(days=1)

    output_path = Path(args.output) if args.output else None
    result = generate_briefing(runs_root=runs_root, target_date=target_date, output_path=output_path)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
