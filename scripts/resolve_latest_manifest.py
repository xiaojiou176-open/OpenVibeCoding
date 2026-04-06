#!/usr/bin/env python3
"""Resolve latest artifact path from latest_manifest.json with optional run_id checks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _normalize_run_id(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    for suffix in ("_p0", "_p1", "_p2_critical", "_full_strict"):
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
            break
    return normalized or None


def _lookup_key(payload: dict[str, Any], dotted_key: str) -> dict[str, Any] | None:
    cursor: Any = payload
    for part in dotted_key.split("."):
        if not isinstance(cursor, dict) or part not in cursor:
            return None
        cursor = cursor.get(part)
    return cursor if isinstance(cursor, dict) else None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        default=".runtime-cache/test_output/latest_manifest.json",
        help="Manifest file path.",
    )
    parser.add_argument(
        "--key",
        required=True,
        choices=[
            "ui_regression.p0_flake_report",
            "ui_regression.p1_flake_report",
            "ui_full_gemini_audit.click_inventory_report",
        ],
        help="Manifest key to resolve.",
    )
    parser.add_argument(
        "--expect-run-id",
        default="",
        help="Optional run_id that must match the manifest entry (normalized match).",
    )
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Return empty output and exit 0 when key/path is missing.",
    )
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Allow entries with status!=complete.",
    )
    parser.add_argument(
        "--output",
        choices=["path", "json"],
        default="path",
        help="Output mode.",
    )
    return parser.parse_args()


def _emit_missing(args: argparse.Namespace, reason: str) -> int:
    if args.allow_missing:
        if args.output == "json":
            print(json.dumps({"path": "", "reason": reason}))
        else:
            print("")
        return 0
    print(f"[resolve_latest_manifest] {reason}", file=sys.stderr)
    return 1


def main() -> int:
    args = _parse_args()
    repo_root = Path.cwd().resolve()
    manifest_path = Path(args.manifest).expanduser()
    if not manifest_path.is_absolute():
        manifest_path = (repo_root / manifest_path).resolve()
    if not manifest_path.is_file():
        return _emit_missing(args, f"manifest_not_found:{manifest_path}")

    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        if args.allow_missing:
            if args.output == "json":
                print(json.dumps({"path": "", "reason": f"manifest_invalid_json:{exc}"}))
            else:
                print("")
            return 0
        print(f"[resolve_latest_manifest] manifest_invalid_json:{exc}", file=sys.stderr)
        return 1

    if not isinstance(payload, dict):
        return _emit_missing(args, "manifest_not_object")

    entry = _lookup_key(payload, args.key)
    if not entry:
        return _emit_missing(args, f"entry_not_found:{args.key}")

    raw_path = str(entry.get("path") or "").strip()
    if not raw_path:
        return _emit_missing(args, f"entry_path_empty:{args.key}")

    status = str(entry.get("status") or "").strip().lower()
    if status and status != "complete" and not args.allow_incomplete:
        return _emit_missing(args, f"entry_incomplete_status:{args.key}:{status}")

    entry_path = Path(raw_path)
    if not entry_path.is_absolute():
        entry_path = (repo_root / entry_path).resolve()

    if not entry_path.exists():
        return _emit_missing(args, f"entry_path_not_found:{entry_path}")

    expected_run_id = args.expect_run_id.strip()
    if expected_run_id:
        expected_norm = _normalize_run_id(expected_run_id)
        actual_run_id = str(entry.get("run_id") or "").strip()
        actual_norm = _normalize_run_id(actual_run_id)
        if not expected_norm or not actual_norm or expected_norm != actual_norm:
            if args.allow_missing:
                if args.output == "json":
                    print(
                        json.dumps(
                            {
                                "path": "",
                                "reason": "run_id_mismatch",
                                "expected_run_id": expected_run_id,
                                "actual_run_id": actual_run_id,
                            }
                        )
                    )
                else:
                    print("")
                return 0
            print(
                f"[resolve_latest_manifest] run_id_mismatch expected={expected_run_id} actual={actual_run_id}",
                file=sys.stderr,
            )
            return 1

    if args.output == "json":
        result = {
            "manifest": str(manifest_path),
            "key": args.key,
            "path": str(entry_path),
            "run_id": entry.get("run_id"),
            "run_id_normalized": entry.get("run_id_normalized"),
            "status": entry.get("status"),
            "incomplete_reasons": entry.get("incomplete_reasons"),
            "selection_basis": entry.get("selection_basis"),
            "source": entry.get("source"),
        }
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(str(entry_path))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
