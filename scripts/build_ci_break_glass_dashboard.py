#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT_LOG = ROOT / ".runtime-cache" / "test_output" / "ci_break_glass_audit.jsonl"
OUT_DIR = ROOT / ".runtime-cache" / "openvibecoding" / "reports" / "ci" / "break_glass"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    if AUDIT_LOG.is_file():
        for raw in AUDIT_LOG.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    scope_counter = Counter(str(item.get("scope") or "unknown") for item in rows)
    reason_counter = Counter(str(item.get("reason") or "unknown") for item in rows)
    payload = {
        "report_type": "openvibecoding_ci_break_glass_dashboard",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "audit_log": str(AUDIT_LOG),
        "total_events": len(rows),
        "top_scopes": scope_counter.most_common(10),
        "top_reasons": reason_counter.most_common(10),
        "recent_events": rows[-20:],
    }
    report_json = OUT_DIR / "dashboard.json"
    report_md = OUT_DIR / "dashboard.md"
    report_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "## CI Break-Glass Dashboard",
        "",
        f"- total_events: `{payload['total_events']}`",
        f"- audit_log: `{AUDIT_LOG}`",
        "",
        "### Top Scopes",
    ]
    if payload["top_scopes"]:
        lines.extend([f"- `{name}`: {count}" for name, count in payload["top_scopes"]])
    else:
        lines.append("- none")
    lines.extend(["", "### Top Reasons"])
    if payload["top_reasons"]:
        lines.extend([f"- `{name}`: {count}" for name, count in payload["top_reasons"]])
    else:
        lines.append("- none")
    lines.append("")
    report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(str(report_json))
    print(str(report_md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
