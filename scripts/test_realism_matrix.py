#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / ".runtime-cache" / "test_output" / "test_realism_matrix"
RUN_ID = f"realism_matrix_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
OUT_DIR = OUT_ROOT / RUN_ID
OUT_DIR.mkdir(parents=True, exist_ok=True)

PATTERNS = {
    "mock_heavy": re.compile(r"mock_mode\s*=\s*True|vi\.mock\(|jest\.mock\(|\bmock\b", re.IGNORECASE),
    "local_real": re.compile(r"127\.0\.0\.1|localhost|playwright|/api/", re.IGNORECASE),
    "external_real": re.compile(r"https://(?!127\.0\.0\.1|localhost)", re.IGNORECASE),
    "llm_real_candidate": re.compile(r"GEMINI_API_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY|provider|model", re.IGNORECASE),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def classify_text(text: str) -> dict[str, bool]:
    return {k: bool(p.search(text)) for k, p in PATTERNS.items()}


def target_files() -> list[Path]:
    globs = [
        "apps/orchestrator/tests/**/*.py",
        "apps/dashboard/**/*.test.ts",
        "apps/dashboard/**/*.test.tsx",
        "apps/desktop/**/*.test.ts",
        "apps/desktop/**/*.test.tsx",
        "scripts/e2e*.sh",
        "scripts/e2e*.py",
        "apps/desktop/scripts/e2e*.mjs",
    ]
    files: list[Path] = []
    for g in globs:
        files.extend(ROOT.glob(g))
    # stable de-dup
    seen: set[str] = set()
    unique: list[Path] = []
    for f in sorted(files):
        key = str(f.resolve())
        if key in seen:
            continue
        seen.add(key)
        unique.append(f)
    return unique


def main() -> int:
    rows: list[dict[str, object]] = []
    counts = Counter()
    tier_counts: dict[str, Counter[str]] = defaultdict(Counter)

    for f in target_files():
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        flags = classify_text(text)

        if flags["external_real"]:
            tier = "external_real"
        elif flags["local_real"] and not flags["mock_heavy"]:
            tier = "local_real"
        elif flags["local_real"] and flags["mock_heavy"]:
            tier = "hybrid"
        elif flags["mock_heavy"]:
            tier = "mock_heavy"
        else:
            tier = "unclear"

        counts[tier] += 1
        if flags["llm_real_candidate"]:
            tier_counts[tier]["llm_candidate"] += 1

        rows.append(
            {
                "path": str(f.relative_to(ROOT)),
                "tier": tier,
                "flags": flags,
            }
        )

    summary = {
        "generated_at": utc_now(),
        "run_id": RUN_ID,
        "total_files": len(rows),
        "tier_counts": dict(counts),
        "llm_candidate_by_tier": {k: dict(v) for k, v in tier_counts.items()},
    }

    json_path = OUT_DIR / "report.json"
    md_path = OUT_DIR / "report.md"

    json_path.write_text(
        json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# Test Realism Matrix",
        "",
        f"- generated_at: {summary['generated_at']}",
        f"- total_files: {summary['total_files']}",
        f"- tier_counts: {summary['tier_counts']}",
        "",
        "| Path | Tier | LLM Candidate |",
        "|---|---|---|",
    ]
    for row in rows:
        flags = row["flags"]
        assert isinstance(flags, dict)
        lines.append(
            f"| `{row['path']}` | `{row['tier']}` | `{str(bool(flags.get('llm_real_candidate', False))).lower()}` |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({"report_json": str(json_path), "report_md": str(md_path)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
