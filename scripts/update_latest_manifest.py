#!/usr/bin/env python3
"""Generate a single latest manifest for UI regression artifacts."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LatestEntry:
    path: str
    abs_path: str
    exists: bool
    mtime_epoch: float | None
    mtime_iso: str | None
    run_id: str | None
    run_id_normalized: str | None
    source: str
    selection_basis: str
    status: str
    incomplete_reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "abs_path": self.abs_path,
            "exists": self.exists,
            "mtime_epoch": self.mtime_epoch,
            "mtime_iso": self.mtime_iso,
            "run_id": self.run_id,
            "run_id_normalized": self.run_id_normalized,
            "source": self.source,
            "selection_basis": self.selection_basis,
            "status": self.status,
            "incomplete_reasons": self.incomplete_reasons,
        }


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso_from_epoch(epoch: float | None) -> str | None:
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


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


def _extract_run_id_from_payload(payload: Any) -> str | None:
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


def _load_payload(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _resolve_relative_path(raw_path: str, repo_root: Path) -> Path:
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = (repo_root / path).resolve()
    return path


def _jsonl_non_empty_line_count(path: Path) -> int:
    count = 0
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    count += 1
    except Exception:
        return 0
    return count


def _display_path(path: Path, repo_root: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(repo_root.resolve()))
    except ValueError:
        return str(resolved)


def _make_missing_entry(source: str, selection_basis: str) -> LatestEntry:
    return LatestEntry(
        path="",
        abs_path="",
        exists=False,
        mtime_epoch=None,
        mtime_iso=None,
        run_id=None,
        run_id_normalized=None,
        source=source,
        selection_basis=selection_basis,
        status="missing",
        incomplete_reasons=["entry_not_found"],
    )


def _derive_flake_status(path: Path, payload: Any, repo_root: Path) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if not isinstance(payload, dict):
        return ("incomplete", ["invalid_json_or_not_object"])

    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict):
        reasons.append("artifacts_missing_or_invalid")
        return ("incomplete", reasons)

    attempts_path_raw = artifacts.get("attempts_jsonl")
    if not isinstance(attempts_path_raw, str) or not attempts_path_raw.strip():
        reasons.append("attempts_jsonl_missing")
        return ("incomplete", reasons)

    attempts_path = _resolve_relative_path(attempts_path_raw.strip(), repo_root)
    if not attempts_path.is_file():
        reasons.append("attempts_jsonl_not_found")
        return ("incomplete", reasons)

    if _jsonl_non_empty_line_count(attempts_path) <= 0:
        reasons.append("attempts_jsonl_empty")

    if payload.get("completed_all_attempts") is not True:
        reasons.append("completed_all_attempts_false")

    if payload.get("incomplete_commands"):
        reasons.append("incomplete_commands_present")

    status = "complete" if not reasons else "incomplete"
    return (status, reasons)


def _derive_click_inventory_status(path: Path, payload: Any, repo_root: Path) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if not isinstance(payload, dict):
        return ("incomplete", ["invalid_json_or_not_object"])

    source_report_raw = payload.get("source_report")
    if not isinstance(source_report_raw, str) or not source_report_raw.strip():
        reasons.append("source_report_missing")
    else:
        source_report_path = _resolve_relative_path(source_report_raw.strip(), repo_root)
        if not source_report_path.is_file():
            reasons.append("source_report_not_found")

    summary = payload.get("summary")
    if not isinstance(summary, dict):
        reasons.append("summary_missing_or_invalid")

    inventory = payload.get("inventory")
    if not isinstance(inventory, list):
        reasons.append("inventory_missing_or_invalid")

    status = "complete" if not reasons else "incomplete"
    return (status, reasons)


def _candidate_score_for_tier(path: Path, tier: str) -> int:
    parent = path.parent.name.lower()
    token = re.compile(rf"(?:^|[^a-z0-9]){re.escape(tier)}(?:[^a-z0-9]|$)")
    if token.search(parent):
        return 100
    if "p0p1" in parent or "p1p0" in parent:
        return 50
    return 0


def _resolve_latest_flake(flake_root: Path, tier: str, repo_root: Path) -> LatestEntry:
    source = f"scan:{flake_root.as_posix()}"
    selection_basis = "latest_by_tier_and_mtime"
    if not flake_root.exists():
        return _make_missing_entry(source, selection_basis)

    candidates: list[tuple[int, float, Path]] = []
    for path in flake_root.glob("*/flake_report.json"):
        if not path.is_file():
            continue
        stat = path.stat()
        candidates.append((_candidate_score_for_tier(path, tier), stat.st_mtime, path))

    if not candidates:
        return _make_missing_entry(source, selection_basis)

    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    best = candidates[0][2]
    stat = best.stat()
    payload = _load_payload(best)
    run_id = _extract_run_id_from_payload(payload) or best.parent.name
    status, incomplete_reasons = _derive_flake_status(best, payload, repo_root)
    rel_path = _display_path(best, repo_root)
    return LatestEntry(
        path=rel_path,
        abs_path=str(best.resolve()),
        exists=True,
        mtime_epoch=stat.st_mtime,
        mtime_iso=_iso_from_epoch(stat.st_mtime),
        run_id=run_id,
        run_id_normalized=_normalize_run_id(run_id),
        source=source,
        selection_basis=selection_basis,
        status=status,
        incomplete_reasons=incomplete_reasons,
    )


def _resolve_latest_click_inventory(full_audit_root: Path, repo_root: Path) -> LatestEntry:
    source = f"scan:{full_audit_root.as_posix()}"
    selection_basis = "latest_by_mtime"
    if not full_audit_root.exists():
        return _make_missing_entry(source, selection_basis)

    candidates = [path for path in full_audit_root.glob("*/click_inventory_report.json") if path.is_file()]
    if not candidates:
        return _make_missing_entry(source, selection_basis)
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    best = candidates[0]
    stat = best.stat()
    payload = _load_payload(best)
    run_id = _extract_run_id_from_payload(payload) or best.parent.name
    status, incomplete_reasons = _derive_click_inventory_status(best, payload, repo_root)
    rel_path = _display_path(best, repo_root)
    return LatestEntry(
        path=rel_path,
        abs_path=str(best.resolve()),
        exists=True,
        mtime_epoch=stat.st_mtime,
        mtime_iso=_iso_from_epoch(stat.st_mtime),
        run_id=run_id,
        run_id_normalized=_normalize_run_id(run_id),
        source=source,
        selection_basis=selection_basis,
        status=status,
        incomplete_reasons=incomplete_reasons,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        default=".runtime-cache/test_output/latest_manifest.json",
        help="Output manifest path.",
    )
    parser.add_argument(
        "--flake-root",
        default=".runtime-cache/test_output/ui_regression",
        help="Root path that contains flake report run folders.",
    )
    parser.add_argument(
        "--full-audit-root",
        default=".runtime-cache/test_output/ui_full_gemini_audit",
        help="Root path that contains full audit run folders.",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print manifest JSON to stdout after write.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    repo_root = Path.cwd().resolve()
    manifest_path = Path(args.manifest).expanduser()
    if not manifest_path.is_absolute():
        manifest_path = (repo_root / manifest_path).resolve()
    flake_root = Path(args.flake_root).expanduser()
    if not flake_root.is_absolute():
        flake_root = (repo_root / flake_root).resolve()
    full_audit_root = Path(args.full_audit_root).expanduser()
    if not full_audit_root.is_absolute():
        full_audit_root = (repo_root / full_audit_root).resolve()

    p0_entry = _resolve_latest_flake(flake_root, "p0", repo_root)
    p1_entry = _resolve_latest_flake(flake_root, "p1", repo_root)
    click_entry = _resolve_latest_click_inventory(full_audit_root, repo_root)

    payload: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": _iso_now(),
        "generated_by": "scripts/update_latest_manifest.py",
        "ui_regression": {
            "p0_flake_report": p0_entry.to_dict(),
            "p1_flake_report": p1_entry.to_dict(),
        },
        "ui_full_gemini_audit": {
            "click_inventory_report": click_entry.to_dict(),
        },
    }

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    result = {
        "manifest": str(manifest_path),
        "p0": p0_entry.to_dict(),
        "p1": p1_entry.to_dict(),
        "click_inventory": click_entry.to_dict(),
    }
    if args.stdout:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
