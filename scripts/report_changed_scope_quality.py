#!/usr/bin/env python3
"""Compute changed-scope quality metrics and generate scheduled tuning suggestions.

Inputs:
- JSONL feedback records (one JSON object per line)
- Optional base rule config JSON

Outputs (under --output-dir/<week>/):
- changed_scope_quality.summary.json
- changed_scope_quality.summary.md
- rule_tuning_suggestions.json
- candidate_rule_tuning.json
- candidate_rule_tuning.patch.diff
"""

from __future__ import annotations

import argparse
import copy
import difflib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LABEL_ALIASES = {
    "tp": "tp",
    "true_positive": "tp",
    "hit": "tp",
    "accepted": "tp",
    "fp": "fp",
    "false_positive": "fp",
    "noise": "fp",
    "rejected": "fp",
    "tn": "tn",
    "true_negative": "tn",
    "fn": "fn",
    "false_negative": "fn",
    "miss": "fn",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_timestamp(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def week_key_for(dt: datetime) -> str:
    year, week, _ = dt.isocalendar()
    return f"{year}-W{week:02d}"


@dataclass
class FeedbackRecord:
    week: str
    rule_id: str
    label: str
    timestamp: str
    pr_number: int | None


def normalize_label(raw: str) -> str:
    return LABEL_ALIASES.get(raw.strip().lower(), "")


def load_feedback(path: Path) -> tuple[list[FeedbackRecord], dict[str, int], list[str]]:
    counters = {
        "lines_total": 0,
        "lines_parsed": 0,
        "lines_invalid": 0,
    }
    errors: list[str] = []
    records: list[FeedbackRecord] = []

    with path.open("r", encoding="utf-8") as f:
        for line_no, raw in enumerate(f, start=1):
            counters["lines_total"] += 1
            text = raw.strip()
            if not text:
                continue
            try:
                obj = json.loads(text)
            except json.JSONDecodeError as exc:
                counters["lines_invalid"] += 1
                errors.append(f"line {line_no}: invalid json ({exc})")
                continue
            if not isinstance(obj, dict):
                counters["lines_invalid"] += 1
                errors.append(f"line {line_no}: record must be json object")
                continue

            timestamp = str(obj.get("timestamp") or "").strip()
            rule_id = str(obj.get("rule_id") or "").strip()
            feedback = obj.get("feedback")
            label_raw = ""
            if isinstance(feedback, dict):
                label_raw = str(feedback.get("label") or "").strip()

            if not timestamp or not rule_id or not label_raw:
                counters["lines_invalid"] += 1
                errors.append(
                    f"line {line_no}: missing required fields timestamp/rule_id/feedback.label"
                )
                continue

            label = normalize_label(label_raw)
            if not label:
                counters["lines_invalid"] += 1
                errors.append(
                    f"line {line_no}: unsupported feedback.label={label_raw!r} "
                    "(allowed aliases map to tp/fp/tn/fn)"
                )
                continue

            try:
                dt = parse_timestamp(timestamp)
            except ValueError:
                counters["lines_invalid"] += 1
                errors.append(
                    f"line {line_no}: invalid timestamp={timestamp!r}, expected ISO-8601"
                )
                continue

            pr_number: int | None = None
            pr = obj.get("pr")
            if isinstance(pr, dict):
                raw_number = pr.get("number")
                if isinstance(raw_number, int):
                    pr_number = raw_number

            records.append(
                FeedbackRecord(
                    week=week_key_for(dt),
                    rule_id=rule_id,
                    label=label,
                    timestamp=dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    pr_number=pr_number,
                )
            )
            counters["lines_parsed"] += 1

    return records, counters, errors


def empty_counter() -> dict[str, int]:
    return {"tp": 0, "fp": 0, "tn": 0, "fn": 0}


def build_counts(records: list[FeedbackRecord]) -> tuple[dict[str, int], dict[str, dict[str, int]]]:
    overall = empty_counter()
    by_rule: dict[str, dict[str, int]] = defaultdict(empty_counter)
    for rec in records:
        overall[rec.label] += 1
        by_rule[rec.rule_id][rec.label] += 1
    return overall, by_rule


def metric_div(num: int, den: int) -> float | None:
    if den <= 0:
        return None
    return num / den


def compute_metrics(counts: dict[str, int]) -> dict[str, Any]:
    tp = counts.get("tp", 0)
    fp = counts.get("fp", 0)
    tn = counts.get("tn", 0)
    fn = counts.get("fn", 0)
    support = tp + fp + tn + fn
    hit_rate = metric_div(tp, tp + fp)
    false_positive_rate = metric_div(fp, fp + tn)
    recall = metric_div(tp, tp + fn)
    false_negative_rate = metric_div(fn, tp + fn)
    return {
        "support": support,
        "counts": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
        "hit_rate": hit_rate,
        "false_positive_rate": false_positive_rate,
        "recall": recall,
        "false_negative_rate": false_negative_rate,
    }


def fmt_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.2f}%"


def load_base_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "version": "1.0",
            "updated_at": "1970-01-01T00:00:00Z",
            "default": {"enabled": True, "min_confidence": 0.60},
            "rules": {},
        }
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"base config must be object: {path}")
    raw.setdefault("version", "1.0")
    raw.setdefault("updated_at", "1970-01-01T00:00:00Z")
    default_cfg = raw.setdefault("default", {})
    if not isinstance(default_cfg, dict):
        raise ValueError("base config field default must be object")
    default_cfg.setdefault("enabled", True)
    default_cfg.setdefault("min_confidence", 0.60)
    rules = raw.setdefault("rules", {})
    if not isinstance(rules, dict):
        raise ValueError("base config field rules must be object")
    return raw


def get_rule_conf(base: dict[str, Any], rule_id: str) -> tuple[bool, float]:
    default_cfg = base.get("default") or {}
    rules = base.get("rules") or {}
    enabled = bool(default_cfg.get("enabled", True))
    confidence = float(default_cfg.get("min_confidence", 0.60))
    if rule_id in rules and isinstance(rules[rule_id], dict):
        rule_cfg = rules[rule_id]
        if "enabled" in rule_cfg:
            enabled = bool(rule_cfg["enabled"])
        if "min_confidence" in rule_cfg:
            confidence = float(rule_cfg["min_confidence"])
    confidence = min(0.99, max(0.01, confidence))
    return enabled, confidence


def build_recommendations(
    per_rule_metrics: dict[str, dict[str, Any]],
    base_config: dict[str, Any],
    *,
    min_samples: int,
    target_hit_rate: float,
    max_fpr: float,
    loosen_hit_rate: float,
    max_fn_rate: float,
    confidence_step: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    candidate = copy.deepcopy(base_config)
    candidate.setdefault("rules", {})
    candidate["updated_at"] = utc_now_iso()

    for rule_id, metrics in sorted(per_rule_metrics.items()):
        support = int(metrics.get("support", 0))
        hit_rate = metrics.get("hit_rate")
        fpr = metrics.get("false_positive_rate")
        fn_rate = metrics.get("false_negative_rate")
        enabled, confidence = get_rule_conf(base_config, rule_id)

        suggestion: dict[str, Any] = {
            "rule_id": rule_id,
            "support": support,
            "baseline": {"enabled": enabled, "min_confidence": round(confidence, 4)},
            "action": "keep",
            "reason": "metrics within control bounds",
            "proposed": {"enabled": enabled, "min_confidence": round(confidence, 4)},
        }

        if support < min_samples:
            suggestion["action"] = "hold_insufficient_data"
            suggestion["reason"] = f"support={support} < min_samples={min_samples}"
            suggestions.append(suggestion)
            continue

        should_tighten = (
            (hit_rate is not None and hit_rate < target_hit_rate)
            or (fpr is not None and fpr > max_fpr)
        )
        should_loosen = (
            hit_rate is not None
            and hit_rate >= loosen_hit_rate
            and (fpr is None or fpr <= max_fpr / 2)
            and fn_rate is not None
            and fn_rate > max_fn_rate
        )

        new_enabled = enabled
        new_confidence = confidence
        if should_tighten:
            new_confidence = min(0.99, round(confidence + confidence_step, 4))
            suggestion["action"] = "tighten"
            suggestion["reason"] = (
                f"hit_rate={fmt_pct(hit_rate)} target>={target_hit_rate:.0%}, "
                f"false_positive_rate={fmt_pct(fpr)} target<={max_fpr:.0%}"
            )
            if hit_rate is not None and hit_rate < 0.20 and support >= (min_samples * 2):
                new_enabled = False
                suggestion["action"] = "disable_candidate"
                suggestion["reason"] += "; sustained low hit-rate, disable candidate"
        elif should_loosen:
            new_confidence = max(0.01, round(confidence - confidence_step, 4))
            suggestion["action"] = "loosen"
            suggestion["reason"] = (
                f"hit_rate={fmt_pct(hit_rate)} strong, false_negative_rate={fmt_pct(fn_rate)} high"
            )

        suggestion["proposed"] = {
            "enabled": bool(new_enabled),
            "min_confidence": round(new_confidence, 4),
        }
        suggestions.append(suggestion)

        if new_enabled != enabled or abs(new_confidence - confidence) > 1e-9:
            candidate["rules"][rule_id] = {
                "enabled": bool(new_enabled),
                "min_confidence": round(new_confidence, 4),
            }

    return suggestions, candidate


def render_markdown(
    *,
    selected_week: str,
    input_path: Path,
    counters: dict[str, int],
    overall_metrics: dict[str, Any],
    per_rule_metrics: dict[str, dict[str, Any]],
    suggestions: list[dict[str, Any]],
) -> str:
    lines: list[str] = []
    lines.append("# Changed-Scope Quality Report")
    lines.append("")
    lines.append(f"- week: `{selected_week}`")
    lines.append(f"- input: `{input_path}`")
    lines.append(f"- generated_at: `{utc_now_iso()}`")
    lines.append(
        "- parsed: "
        f"{counters['lines_parsed']} / {counters['lines_total']} "
        f"(invalid={counters['lines_invalid']})"
    )
    lines.append("")

    lines.append("## Overall")
    lines.append("")
    lines.append("| metric | value |")
    lines.append("| --- | --- |")
    lines.append(f"| support | {overall_metrics['support']} |")
    lines.append(f"| hit_rate (TP/(TP+FP)) | {fmt_pct(overall_metrics['hit_rate'])} |")
    lines.append(
        "| false_positive_rate (FP/(FP+TN)) | "
        f"{fmt_pct(overall_metrics['false_positive_rate'])} |"
    )
    lines.append(f"| recall (TP/(TP+FN)) | {fmt_pct(overall_metrics['recall'])} |")
    lines.append(
        "| false_negative_rate (FN/(TP+FN)) | "
        f"{fmt_pct(overall_metrics['false_negative_rate'])} |"
    )
    counts = overall_metrics["counts"]
    lines.append(
        f"| confusion_counts | TP={counts['tp']}, FP={counts['fp']}, TN={counts['tn']}, FN={counts['fn']} |"
    )
    lines.append("")

    lines.append("## Per Rule")
    lines.append("")
    lines.append("| rule_id | support | hit_rate | fpr | recall | fn_rate |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for rule_id, metrics in sorted(per_rule_metrics.items()):
        lines.append(
            f"| `{rule_id}` | {metrics['support']} | {fmt_pct(metrics['hit_rate'])} | "
            f"{fmt_pct(metrics['false_positive_rate'])} | {fmt_pct(metrics['recall'])} | "
            f"{fmt_pct(metrics['false_negative_rate'])} |"
        )
    lines.append("")

    lines.append("## Rule Tuning Suggestions")
    lines.append("")
    if not suggestions:
        lines.append("- no suggestion generated")
    else:
        for item in suggestions:
            proposed = item.get("proposed") or {}
            lines.append(
                "- "
                f"`{item['rule_id']}` -> `{item['action']}` "
                f"(enabled={proposed.get('enabled')}, "
                f"min_confidence={proposed.get('min_confidence')})"
                f" | reason: {item['reason']}"
            )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compute changed-scope hit-rate / false-positive-rate from PR feedback JSONL "
            "and generate scheduled rule tuning suggestions."
        )
    )
    parser.add_argument(
        "--input-jsonl",
        required=True,
        help="Path to standardized feedback JSONL.",
    )
    parser.add_argument(
        "--output-dir",
        default=".runtime-cache/test_output/changed_scope_quality",
        help="Output directory root.",
    )
    parser.add_argument(
        "--base-config",
        default="configs/changed_scope/rule_tuning.json",
        help="Base rule config JSON used to produce candidate patch.",
    )
    parser.add_argument(
        "--week",
        default="",
        help="Target ISO week (YYYY-Www). Defaults to latest week in input.",
    )
    parser.add_argument("--min-samples", type=int, default=8)
    parser.add_argument("--target-hit-rate", type=float, default=0.70)
    parser.add_argument("--max-fpr", type=float, default=0.25)
    parser.add_argument("--loosen-hit-rate", type=float, default=0.90)
    parser.add_argument("--max-fn-rate", type=float, default=0.35)
    parser.add_argument("--confidence-step", type=float, default=0.05)
    parser.add_argument(
        "--fail-on-invalid",
        action="store_true",
        help="Exit non-zero when invalid lines are found.",
    )
    args = parser.parse_args()

    input_path = Path(args.input_jsonl)
    if not input_path.exists():
        raise SystemExit(f"[CHANGED_SCOPE_QUALITY][FAIL] input missing: {input_path}")

    records, counters, errors = load_feedback(input_path)
    if args.fail_on_invalid and counters["lines_invalid"] > 0:
        for err in errors[:20]:
            print(f"[CHANGED_SCOPE_QUALITY][ERROR] {err}")
        raise SystemExit("[CHANGED_SCOPE_QUALITY][FAIL] invalid lines detected")

    if not records:
        output_dir = Path(args.output_dir) / "no-data"
        output_dir.mkdir(parents=True, exist_ok=True)
        summary = {
            "generated_at": utc_now_iso(),
            "status": "no_data",
            "input_jsonl": str(input_path),
            "counters": counters,
            "errors": errors[:50],
        }
        (output_dir / "changed_scope_quality.summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (output_dir / "changed_scope_quality.summary.md").write_text(
            "# Changed-Scope Quality Report\n\n- status: no_data\n",
            encoding="utf-8",
        )
        print("[CHANGED_SCOPE_QUALITY][WARN] no valid records, report generated")
        return 0

    weeks = sorted({r.week for r in records})
    selected_week = args.week.strip() or weeks[-1]
    selected_records = [r for r in records if r.week == selected_week]
    if not selected_records:
        raise SystemExit(
            "[CHANGED_SCOPE_QUALITY][FAIL] "
            f"requested week={selected_week} not found in input weeks={weeks}"
        )

    overall_counts, per_rule_counts = build_counts(selected_records)
    overall_metrics = compute_metrics(overall_counts)
    per_rule_metrics = {
        rule_id: compute_metrics(counts) for rule_id, counts in per_rule_counts.items()
    }

    base_config_path = Path(args.base_config)
    base_config = load_base_config(base_config_path)
    suggestions, candidate_config = build_recommendations(
        per_rule_metrics,
        base_config,
        min_samples=args.min_samples,
        target_hit_rate=args.target_hit_rate,
        max_fpr=args.max_fpr,
        loosen_hit_rate=args.loosen_hit_rate,
        max_fn_rate=args.max_fn_rate,
        confidence_step=args.confidence_step,
    )

    output_dir = Path(args.output_dir) / selected_week
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_json_path = output_dir / "changed_scope_quality.summary.json"
    summary_md_path = output_dir / "changed_scope_quality.summary.md"
    suggestion_json_path = output_dir / "rule_tuning_suggestions.json"
    candidate_json_path = output_dir / "candidate_rule_tuning.json"
    candidate_patch_path = output_dir / "candidate_rule_tuning.patch.diff"

    summary_payload = {
        "generated_at": utc_now_iso(),
        "input_jsonl": str(input_path),
        "selected_week": selected_week,
        "available_weeks": weeks,
        "counters": counters,
        "invalid_line_errors": errors[:200],
        "overall": overall_metrics,
        "per_rule": per_rule_metrics,
        "suggestions": suggestions,
        "candidate_outputs": {
            "base_config": str(base_config_path),
            "candidate_config": str(candidate_json_path),
            "candidate_patch": str(candidate_patch_path),
        },
    }

    summary_json_path.write_text(
        json.dumps(summary_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    summary_md_path.write_text(
        render_markdown(
            selected_week=selected_week,
            input_path=input_path,
            counters=counters,
            overall_metrics=overall_metrics,
            per_rule_metrics=per_rule_metrics,
            suggestions=suggestions,
        )
        + "\n",
        encoding="utf-8",
    )
    suggestion_json_path.write_text(
        json.dumps({"generated_at": utc_now_iso(), "suggestions": suggestions}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    candidate_json_path.write_text(
        json.dumps(candidate_config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    base_config_text = json.dumps(base_config, ensure_ascii=False, indent=2) + "\n"
    candidate_text = json.dumps(candidate_config, ensure_ascii=False, indent=2) + "\n"
    diff_lines = list(
        difflib.unified_diff(
            base_config_text.splitlines(keepends=True),
            candidate_text.splitlines(keepends=True),
            fromfile=str(base_config_path),
            tofile=str(candidate_json_path),
        )
    )
    if not diff_lines:
        diff_lines = ["# No config delta generated for this week.\n"]
    candidate_patch_path.write_text("".join(diff_lines), encoding="utf-8")

    print(
        "[CHANGED_SCOPE_QUALITY][PASS] "
        f"week={selected_week} summary={summary_json_path} "
        f"suggestions={suggestion_json_path} patch={candidate_patch_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
