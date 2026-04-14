#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write a structured CI slice summary.")
    parser.add_argument("--slice", required=True)
    parser.add_argument("--status", required=True, choices=("running", "success", "failure"))
    parser.add_argument("--json-path", required=True)
    parser.add_argument("--markdown-path", required=True)
    parser.add_argument("--started-at", required=True)
    parser.add_argument("--started-epoch", required=True, type=int)
    parser.add_argument("--artifact-root", action="append", default=[])
    parser.add_argument("--source-run-id", default="")
    parser.add_argument("--source-run-attempt", default="")
    parser.add_argument("--source-sha", default="")
    parser.add_argument("--source-ref", default="")
    parser.add_argument("--source-event", default="")
    parser.add_argument("--source-route", default="")
    parser.add_argument("--source-trust-class", default="")
    parser.add_argument("--source-runner-class", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    finished_at = datetime.now(timezone.utc).isoformat()
    duration_sec = max(0, int(time.time()) - int(args.started_epoch))
    payload = {
        "report_type": "openvibecoding_ci_slice_summary",
        "slice": args.slice,
        "status": args.status,
        "started_at": args.started_at,
        "finished_at": finished_at,
        "duration_sec": duration_sec,
        "artifact_roots": args.artifact_root,
        "source_run_id": args.source_run_id,
        "source_run_attempt": args.source_run_attempt,
        "source_sha": args.source_sha,
        "source_ref": args.source_ref,
        "source_event": args.source_event,
        "source_route": args.source_route,
        "source_trust_class": args.source_trust_class,
        "source_runner_class": args.source_runner_class,
    }
    json_path = Path(args.json_path).expanduser().resolve()
    md_path = Path(args.markdown_path).expanduser().resolve()
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        f"## CI Slice Summary - {args.slice}",
        "",
        f"- status: **{args.status}**",
        f"- started_at: `{args.started_at}`",
        f"- finished_at: `{finished_at}`",
        f"- duration_sec: `{duration_sec}`",
        f"- source_run_id: `{args.source_run_id}`",
        f"- source_run_attempt: `{args.source_run_attempt}`",
        f"- source_event: `{args.source_event}`",
        f"- source_route: `{args.source_route}`",
        f"- source_runner_class: `{args.source_runner_class}`",
        "",
        "### Artifact Roots",
    ]
    if args.artifact_root:
        lines.extend([f"- `{item}`" for item in args.artifact_root])
    else:
        lines.append("- none")
    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

