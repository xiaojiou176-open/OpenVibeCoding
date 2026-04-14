#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_MANIFEST = (
    ROOT / ".runtime-cache" / "openvibecoding" / "reports" / "ci" / "current_run" / "source_manifest.json"
)


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_path(raw: str | Path, *, base_dir: Path = ROOT) -> Path:
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = (base_dir / candidate).resolve()
    else:
        candidate = candidate.resolve()
    return candidate


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def load_json(path: Path, *, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"{label} missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} invalid json: {path} ({exc})") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object: {path}")
    return payload


def parse_iso(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    normalized = raw.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def timestamp_to_iso(raw: Any) -> str | None:
    parsed = parse_iso(raw)
    return parsed.isoformat() if parsed else None


def file_mtime_iso(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()


def source_metadata(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "authority_hint": str(manifest.get("authority_hint") or ""),
        "source_run_id": str(manifest.get("source_run_id") or ""),
        "source_run_attempt": str(manifest.get("source_run_attempt") or ""),
        "source_sha": str(manifest.get("source_sha") or ""),
        "source_ref": str(manifest.get("source_ref") or ""),
        "source_event": str(manifest.get("source_event") or ""),
        "source_route": str(manifest.get("source_route") or ""),
        "source_trust_class": str(manifest.get("source_trust_class") or ""),
        "source_runner_class": str(manifest.get("source_runner_class") or ""),
    }


def current_head_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def current_truth_authority(manifest: dict[str, Any]) -> dict[str, Any]:
    meta = source_metadata(manifest)
    head_sha = current_head_sha()
    source_sha = meta["source_sha"].strip()
    source_route = meta["source_route"].strip()
    authority_hint = meta["authority_hint"].strip().lower()

    reasons: list[str] = []
    # `local-advisory` is the explicit fallback route for self-consistent-but-non-authoritative
    # snapshots. Local release-grade runs that materialize a real `local_full_ci`
    # source manifest should be allowed to become authoritative when their source
    # sha matches the current HEAD.
    advisory_local_only = source_route == "local-advisory" or authority_hint == "advisory"
    if advisory_local_only:
        reasons.append("local_advisory_route")
    if not head_sha:
        reasons.append("current_head_unavailable")
    if not source_sha:
        reasons.append("source_sha_missing")

    source_head_match = bool(source_sha and head_sha and source_sha == head_sha)
    if source_sha and head_sha and not source_head_match:
        reasons.append("source_sha_mismatch")

    authoritative_current_truth = source_head_match and not advisory_local_only
    authority_level = "authoritative" if authoritative_current_truth else "advisory"
    return {
        "current_head_sha": head_sha,
        "source_head_match": source_head_match,
        "authoritative_current_truth": authoritative_current_truth,
        "advisory_local_only": advisory_local_only,
        "authority_level": authority_level,
        "authority_reasons": reasons,
    }


def load_source_manifest(path: str | Path | None = None) -> dict[str, Any]:
    target = resolve_path(path or DEFAULT_SOURCE_MANIFEST)
    payload = load_json(target, label="ci current-run source manifest")
    if payload.get("report_type") != "openvibecoding_ci_current_run_source_manifest":
        raise ValueError(f"ci current-run source manifest has unexpected report_type: {target}")
    return payload


def manifest_required_slices(manifest: dict[str, Any]) -> list[str]:
    raw = manifest.get("required_slice_summaries")
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def manifest_slice_summary_paths(manifest: dict[str, Any]) -> dict[str, Path]:
    raw = manifest.get("slice_summaries")
    if not isinstance(raw, dict):
        return {}
    resolved: dict[str, Path] = {}
    for name, value in raw.items():
        if not isinstance(value, str) or not value.strip():
            continue
        resolved[str(name)] = resolve_path(value)
    return resolved


def manifest_report_paths(manifest: dict[str, Any]) -> dict[str, Path]:
    raw = manifest.get("reports")
    if not isinstance(raw, dict):
        return {}
    resolved: dict[str, Path] = {}
    for name, value in raw.items():
        if not isinstance(value, str) or not value.strip():
            continue
        resolved[str(name)] = resolve_path(value)
    return resolved


def manifest_retry_telemetry_paths(manifest: dict[str, Any]) -> list[Path]:
    raw = manifest.get("retry_telemetry")
    if not isinstance(raw, list):
        return []
    rows: list[Path] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            rows.append(resolve_path(item))
    return rows


def manifest_route_report_path(manifest: dict[str, Any]) -> Path | None:
    value = manifest.get("route_report")
    if not isinstance(value, str) or not value.strip():
        return None
    return resolve_path(value)


def manifest_expected_files(manifest: dict[str, Any]) -> list[tuple[str, Path]]:
    rows: list[tuple[str, Path]] = []
    route_path = manifest_route_report_path(manifest)
    if route_path is not None:
        rows.append(("route_report", route_path))
    for name, path in sorted(manifest_slice_summary_paths(manifest).items()):
        rows.append((f"slice_summary:{name}", path))
    for name, path in sorted(manifest_report_paths(manifest).items()):
        rows.append((f"report:{name}", path))
    for idx, path in enumerate(manifest_retry_telemetry_paths(manifest), start=1):
        rows.append((f"retry_telemetry:{idx}", path))
    return rows


def analytics_exclusion_paths(manifest: dict[str, Any]) -> list[Path]:
    raw = manifest.get("analytics_exclusions")
    if not isinstance(raw, list):
        return []
    rows: list[Path] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        if isinstance(path, str) and path.strip():
            rows.append(resolve_path(path))
    return rows


def report_generated_at(payload: dict[str, Any], *, path: Path) -> str:
    for key in ("generated_at", "created_at", "updated_at", "finished_at"):
        parsed = timestamp_to_iso(payload.get(key))
        if parsed:
            return parsed
    return file_mtime_iso(path)
