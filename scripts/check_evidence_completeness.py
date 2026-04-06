#!/usr/bin/env python3
"""Validate latest manifest evidence completeness and detect half-finished runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DEFAULT_KEYS = [
    "ui_regression.p0_flake_report",
    "ui_regression.p1_flake_report",
    "ui_full_gemini_audit.click_inventory_report",
]


def _normalize_run_id(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    for suffix in ("_p0", "_p1", "_p2_critical", "_full_strict"):
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
            break
    return normalized or None


def _lookup(payload: dict[str, Any], dotted_key: str) -> dict[str, Any] | None:
    cursor: Any = payload
    for part in dotted_key.split("."):
        if not isinstance(cursor, dict) or part not in cursor:
            return None
        cursor = cursor.get(part)
    return cursor if isinstance(cursor, dict) else None


def _resolve_path(raw_path: str, repo_root: Path) -> Path:
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = (repo_root / path).resolve()
    return path


def _count_non_empty_jsonl(path: Path) -> int:
    count = 0
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    count += 1
    except Exception:
        return 0
    return count


def _extract_run_id(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    for key in ("run_id", "report_run_id"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    meta = payload.get("meta")
    if isinstance(meta, dict):
        value = meta.get("run_id")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _validate_flake_report(path: Path, repo_root: Path) -> dict[str, Any]:
    reasons: list[str] = []
    payload: Any = {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        reasons.append("report_invalid_json")
        return {"complete": False, "reasons": reasons, "run_id": path.parent.name}

    if not isinstance(payload, dict):
        reasons.append("report_not_object")
        return {"complete": False, "reasons": reasons, "run_id": path.parent.name}

    run_id = _extract_run_id(payload) or path.parent.name
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict):
        reasons.append("artifacts_missing_or_invalid")
        return {"complete": False, "reasons": reasons, "run_id": run_id}

    attempts_raw = artifacts.get("attempts_jsonl")
    if not isinstance(attempts_raw, str) or not attempts_raw.strip():
        reasons.append("attempts_jsonl_missing")
        return {"complete": False, "reasons": reasons, "run_id": run_id}

    attempts_path = _resolve_path(attempts_raw.strip(), repo_root)
    if not attempts_path.is_file():
        reasons.append("attempts_jsonl_not_found")
        return {"complete": False, "reasons": reasons, "run_id": run_id}

    if _count_non_empty_jsonl(attempts_path) <= 0:
        reasons.append("attempts_jsonl_empty")
    if payload.get("completed_all_attempts") is not True:
        reasons.append("completed_all_attempts_false")
    if payload.get("incomplete_commands"):
        reasons.append("incomplete_commands_present")

    return {"complete": len(reasons) == 0, "reasons": reasons, "run_id": run_id}


def _validate_click_inventory(path: Path, repo_root: Path) -> dict[str, Any]:
    reasons: list[str] = []
    payload: Any = {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        reasons.append("report_invalid_json")
        return {"complete": False, "reasons": reasons, "run_id": path.parent.name}

    if not isinstance(payload, dict):
        reasons.append("report_not_object")
        return {"complete": False, "reasons": reasons, "run_id": path.parent.name}

    run_id = _extract_run_id(payload) or path.parent.name
    source_report_raw = payload.get("source_report")
    if not isinstance(source_report_raw, str) or not source_report_raw.strip():
        reasons.append("source_report_missing")
    else:
        source_report_path = _resolve_path(source_report_raw.strip(), repo_root)
        if not source_report_path.is_file():
            reasons.append("source_report_not_found")
    if not isinstance(payload.get("summary"), dict):
        reasons.append("summary_missing_or_invalid")
    if not isinstance(payload.get("inventory"), list):
        reasons.append("inventory_missing_or_invalid")
    return {"complete": len(reasons) == 0, "reasons": reasons, "run_id": run_id}


def _validate_entry(
    key: str,
    entry: dict[str, Any] | None,
    repo_root: Path,
    entry_type: str,
) -> dict[str, Any]:
    result: dict[str, Any] = {"key": key, "complete": False, "reasons": [], "path": "", "run_id": None}
    if not entry:
        result["reasons"].append("entry_not_found")
        return result
    if not isinstance(entry, dict):
        result["reasons"].append("entry_not_object")
        return result

    status = str(entry.get("status") or "").strip().lower()
    run_id = entry.get("run_id")
    result["run_id"] = run_id if isinstance(run_id, str) else None

    raw_path = str(entry.get("path") or "").strip()
    if not raw_path:
        result["reasons"].append("entry_path_missing")
        return result
    report_path = _resolve_path(raw_path, repo_root)
    result["path"] = str(report_path)
    if not report_path.is_file():
        result["reasons"].append("entry_path_not_found")
        return result

    if status and status != "complete":
        result["reasons"].append(f"manifest_status_{status}")
    if isinstance(entry.get("incomplete_reasons"), list) and entry.get("incomplete_reasons"):
        result["reasons"].append("manifest_incomplete_reasons_present")

    if entry_type == "flake":
        validation = _validate_flake_report(report_path, repo_root)
    else:
        validation = _validate_click_inventory(report_path, repo_root)
    result["run_id"] = validation.get("run_id") or result["run_id"]
    result["run_id_normalized"] = _normalize_run_id(result["run_id"])
    result["reasons"].extend(validation.get("reasons", []))
    result["complete"] = len(result["reasons"]) == 0 and bool(validation.get("complete"))
    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        default=".runtime-cache/test_output/latest_manifest.json",
        help="Path to latest manifest JSON.",
    )
    parser.add_argument(
        "--keys",
        nargs="+",
        default=DEFAULT_KEYS,
        help="Manifest keys to validate.",
    )
    parser.add_argument(
        "--fail-closed",
        action="store_true",
        help="Exit non-zero when any requested key is incomplete.",
    )
    parser.add_argument(
        "--output",
        choices=("json", "text"),
        default="json",
        help="Output mode.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    repo_root = Path.cwd().resolve()
    manifest_path = Path(args.manifest).expanduser()
    if not manifest_path.is_absolute():
        manifest_path = (repo_root / manifest_path).resolve()

    summary: dict[str, Any] = {
        "manifest": str(manifest_path),
        "keys": args.keys,
        "all_complete": False,
        "results": [],
    }

    if not manifest_path.is_file():
        summary["error"] = "manifest_not_found"
        if args.output == "json":
            print(json.dumps(summary, ensure_ascii=False))
        else:
            print(f"manifest_not_found:{manifest_path}")
        return 1 if args.fail_closed else 0

    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        summary["error"] = f"manifest_invalid_json:{exc}"
        if args.output == "json":
            print(json.dumps(summary, ensure_ascii=False))
        else:
            print(summary["error"])
        return 1 if args.fail_closed else 0

    if not isinstance(payload, dict):
        summary["error"] = "manifest_not_object"
        if args.output == "json":
            print(json.dumps(summary, ensure_ascii=False))
        else:
            print(summary["error"])
        return 1 if args.fail_closed else 0

    key_type = {
        "ui_regression.p0_flake_report": "flake",
        "ui_regression.p1_flake_report": "flake",
        "ui_full_gemini_audit.click_inventory_report": "click_inventory",
    }

    results: list[dict[str, Any]] = []
    for key in args.keys:
        entry = _lookup(payload, key)
        results.append(_validate_entry(key, entry, repo_root, key_type.get(key, "flake")))
    summary["results"] = results
    summary["all_complete"] = all(bool(item.get("complete")) for item in results)

    if args.output == "json":
        print(json.dumps(summary, ensure_ascii=False))
    else:
        for item in results:
            state = "complete" if item.get("complete") else "incomplete"
            reasons = ",".join(item.get("reasons", [])) or "-"
            print(f"{item.get('key')}:{state}:{reasons}")

    if args.fail_closed and not summary["all_complete"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
