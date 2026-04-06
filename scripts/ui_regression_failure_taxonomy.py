#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


RULES: list[tuple[str, re.Pattern[str], str, str]] = [
    (
        "RULE_BLOCKED",
        re.compile(
            r"diff gate|gate denied|policy gate|rule gate|allowed_paths|rejected by rule|rule blocked|gate blocked",
            re.I,
        ),
        "gate",
        "backend",
    ),
    (
        "MANUAL_CONFIRM_REQUIRED",
        re.compile(
            r"manual (cancel|verify|approval|confirm|review|intervention)|human approval required|pending manual|awaiting manual|manual confirmation",
            re.I,
        ),
        "manual",
        "ops",
    ),
    (
        "STALE_DEV_LOCK",
        re.compile(r"stale lock|\.next/dev/lock|lock with active dashboard dev process", re.I),
        "env",
        "platform",
    ),
    ("PORT_CONFLICT", re.compile(r"address already in use|eaddrinuse|port .* in use", re.I), "env", "platform"),
    (
        "SERVICE_BOOT_TIMEOUT",
        re.compile(r"timeout waiting for http|failed to connect|connection refused|ECONNREFUSED", re.I),
        "env",
        "platform",
    ),
    ("NETWORK_UNSTABLE", re.compile(r"timeout|timed out|net::|ECONN|ENOTFOUND|ECONNRESET", re.I), "env", "platform"),
    ("TEST_ACT_WARNING", re.compile(r"not wrapped in act", re.I), "test", "frontend"),
    (
        "SELECTOR_TIMEOUT",
        re.compile(r"locator\.(click|fill)|waiting for getByLabel|waiting for getByRole|Timeout \d+ms exceeded", re.I),
        "test",
        "frontend",
    ),
    ("SELECTOR_DRIFT", re.compile(r"getByRole|locator|strict mode violation|Unable to find", re.I), "test", "frontend"),
    ("ASSERTION_MISMATCH", re.compile(r"expect\(|AssertionError|toBe|toEqual|assert", re.I), "test", "frontend"),
    (
        "COMMAND_TOWER_CHECK_FAILED",
        re.compile(r"command tower controls .* failed: one or more checks failed", re.I),
        "product",
        "frontend",
    ),
    ("API_5XX", re.compile(r"\b50[0-9]\b|internal server error", re.I), "product", "backend"),
    ("API_4XX", re.compile(r"\b40[0-9]\b|bad request|forbidden|unauthorized|not found", re.I), "contract", "backend"),
    ("TAURI_SHELL", re.compile(r"tauri|windowCount|foundProcess|shell real", re.I), "product", "desktop"),
]


BUCKET_TO_AUDIT_CATEGORY: dict[str, str] = {
    "env": "Environment noise",
    "test": "Test fragility",
    "gate": "Rule blocked",
    "manual": "Manual confirmation required",
    "product": "Functional anomaly",
    "contract": "Functional anomaly",
    "unknown": "Functional anomaly",
}


def classify(text: str) -> tuple[str, str, str]:
    for code, pattern, bucket, owner in RULES:
        if pattern.search(text):
            return code, bucket, owner
    return "FUNCTIONAL_ANOMALY", "product", "backend"


def build_classification_text(row: dict) -> str:
    parts: list[str] = []
    for key in ("failure_signature", "first_cause"):
        value = str(row.get(key) or "").strip()
        if value:
            parts.append(value)

    log_path_raw = str(row.get("log_path") or "").strip()
    if log_path_raw:
        log_path = Path(log_path_raw)
        if log_path.exists():
            try:
                parts.append(log_path.read_text(encoding="utf-8", errors="ignore")[:4000])
            except OSError:
                pass
    return "\n".join(parts)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate failure taxonomy from UI flake report.")
    parser.add_argument("--flake-report", required=True, help="Path to flake_report.json")
    parser.add_argument(
        "--out-json",
        default="",
        help="Output JSON path, default: <report_dir>/failure_taxonomy.json",
    )
    parser.add_argument(
        "--out-md",
        default="",
        help="Output markdown path, default: <report_dir>/failure_taxonomy.md",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report_path = Path(args.flake_report)
    if not report_path.exists():
        raise SystemExit(f"missing flake report: {report_path}")

    report = json.loads(report_path.read_text(encoding="utf-8"))
    attempts_path = Path(report["artifacts"]["attempts_jsonl"])
    if not attempts_path.exists():
        raise SystemExit(f"missing attempts jsonl: {attempts_path}")

    failed_records: list[dict] = []
    for line in attempts_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if int(row.get("exit_code", 0)) != 0:
            failed_records.append(row)

    classified: list[dict] = []
    bucket_counter: Counter[str] = Counter()
    code_counter: Counter[str] = Counter()
    owner_counter: Counter[str] = Counter()
    audit_category_counter: Counter[str] = Counter()
    code_owner_counter: dict[str, Counter[str]] = defaultdict(Counter)
    samples: dict[str, str] = {}
    first_cause_samples: dict[str, str] = {}
    by_command: dict[str, Counter[str]] = defaultdict(Counter)

    for row in failed_records:
        classification_text = build_classification_text(row)
        signature = str(row.get("failure_signature") or row.get("first_cause") or "")
        code, bucket, owner = classify(classification_text or signature)
        audit_category = BUCKET_TO_AUDIT_CATEGORY.get(bucket, "Test fragility")
        bucket_counter[bucket] += 1
        code_counter[code] += 1
        owner_counter[owner] += 1
        code_owner_counter[code][owner] += 1
        audit_category_counter[audit_category] += 1
        sample_text = str(row.get("first_cause") or signature)[:300]
        samples.setdefault(code, sample_text)
        first_cause_samples.setdefault(code, sample_text)
        by_command[str(row.get("command", "unknown"))][code] += 1
        classified.append(
            {
                "command_index": row.get("command_index"),
                "command": row.get("command"),
                "iteration": row.get("iteration"),
                "failure_signature": row.get("failure_signature"),
                "first_cause": row.get("first_cause"),
                "taxonomy_code": code,
                "taxonomy_bucket": bucket,
                "audit_category": audit_category,
                "owner": owner,
                "log_path": row.get("log_path"),
            }
        )

    out_json = Path(args.out_json) if args.out_json else report_path.with_name("failure_taxonomy.json")
    out_md = Path(args.out_md) if args.out_md else report_path.with_name("failure_taxonomy.md")
    out_json.parent.mkdir(parents=True, exist_ok=True)

    code_owner_mapping = {
        code: owner_counts.most_common(1)[0][0]
        for code, owner_counts in code_owner_counter.items()
        if owner_counts
    }

    output = {
        "run_id": report.get("run_id"),
        "source_report": str(report_path),
        "failed_attempts": len(failed_records),
        "taxonomy_bucket_counts": dict(bucket_counter),
        "taxonomy_code_counts": dict(code_counter),
        "owner_counts": dict(owner_counter),
        "code_owner_mapping": code_owner_mapping,
        "audit_category_counts": dict(audit_category_counter),
        "code_samples": samples,
        "first_cause_samples": first_cause_samples,
        "per_command": {cmd: dict(counter) for cmd, counter in by_command.items()},
        "records": classified,
    }
    out_json.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        f"# UI Failure Taxonomy ({report.get('run_id', 'unknown')})",
        "",
        f"- source: `{report_path}`",
        f"- failed_attempts: {len(failed_records)}",
        "",
        "## Audit Categories",
        "",
        "| Category | Count |",
        "|---|---:|",
    ]
    for category, count in audit_category_counter.most_common():
        lines.append(f"| {category} | {count} |")
    if not audit_category_counter:
        lines.append("| none | 0 |")

    lines.extend(
        [
            "",
        "## Bucket Counts",
        "",
        "| Bucket | Count |",
        "|---|---:|",
        ]
    )
    for bucket, count in bucket_counter.most_common():
        lines.append(f"| {bucket} | {count} |")
    if not bucket_counter:
        lines.append("| none | 0 |")

    lines.extend(
        [
            "",
            "## Code Counts",
            "",
            "| Code | Count | Owner | First Cause Sample |",
            "|---|---:|---|---|",
        ]
    )
    for code, count in code_counter.most_common():
        owner = code_owner_mapping.get(code, "triage")
        sample = (first_cause_samples.get(code) or samples.get(code) or "").replace("|", "\\|")
        lines.append(f"| {code} | {count} | {owner} | {sample[:120]} |")
    if not code_counter:
        lines.append("| none | 0 | - | - |")

    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"failure_taxonomy": str(out_json), "failed_attempts": len(failed_records)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
