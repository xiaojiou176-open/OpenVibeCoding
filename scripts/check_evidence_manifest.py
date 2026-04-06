#!/usr/bin/env python3
"""Fail-closed checker for evidence manifest schema + semantic constraints."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = ROOT / "schemas" / "evidence_manifest.schema.json"
VALID_SECTION_STATUS = {"pass", "fail", "missing"}
VALID_UI_STATUS = {"pass", "fail"}
VALID_OVERALL_STATUS = {"pass", "fail"}
VALID_TIMESTAMP_SOURCE = {"generated_at", "created_at", "updated_at", "finished_at", "file_mtime"}
STRICT_SECTION_IDS = {
    "ui_truth",
    "ui_flake_p0",
    "ui_flake_p1",
    "ui_full_strict",
    "mutation",
    "security",
    "incident",
}
ARTIFACT_PATH_KEYS = {"report_json", "attempts_jsonl", "report_markdown", "click_inventory_report"}


def _is_non_empty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _parse_iso(value: Any) -> bool:
    if not _is_non_empty_str(value):
        return False
    text = str(value).strip().replace("Z", "+00:00")
    try:
        dt.datetime.fromisoformat(text)
    except ValueError:
        return False
    return True


def _parse_iso_dt(value: Any) -> dt.datetime | None:
    if not _is_non_empty_str(value):
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _require_exact_keys(
    obj: Any,
    *,
    label: str,
    required: set[str],
    optional: set[str] | None = None,
    errors: list[str],
) -> None:
    if not isinstance(obj, dict):
        errors.append(f"{label} must be object")
        return
    optional_keys = optional or set()
    allowed = required | optional_keys
    extra = sorted(set(obj.keys()) - allowed)
    missing = sorted(required - set(obj.keys()))
    if missing:
        errors.append(f"{label} missing keys: {', '.join(missing)}")
    if extra:
        errors.append(f"{label} has unknown keys: {', '.join(extra)}")


def _validate_schema_file(schema_path: Path) -> list[str]:
    errors: list[str] = []
    if not schema_path.is_file():
        return [f"schema file missing: {schema_path}"]
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"schema json invalid: {exc}"]
    if not isinstance(schema, dict):
        return ["schema must be JSON object"]
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        errors.append("schema.$schema invalid")
    if schema.get("type") != "object":
        errors.append("schema.type must be object")
    if schema.get("additionalProperties") is not False:
        errors.append("schema.additionalProperties must be false")
    properties = schema.get("properties")
    required = schema.get("required")
    if not isinstance(properties, dict):
        errors.append("schema.properties invalid")
    if not isinstance(required, list):
        errors.append("schema.required invalid")
    else:
        expected = {
            "manifest_type",
            "schema_version",
            "generated_at",
            "overall_status",
            "schema_path",
            "strict_mode",
            "strict_required_sections",
            "sources",
            "evidence",
        }
        if set(required) != expected:
            errors.append("schema.required root keys mismatch expected contract")
    return errors


def _normalize_and_check_path(raw: str, *, label: str, errors: list[str], check_files: bool) -> Path | None:
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = (Path.cwd() / candidate).resolve()
    else:
        candidate = candidate.resolve()
    if check_files and not candidate.exists():
        errors.append(f"{label} path not found: {candidate}")
        return None
    return candidate


def _validate_section(
    section: Any,
    *,
    label: str,
    required_artifact_keys: tuple[str, ...],
    allow_missing: bool,
    errors: list[str],
    check_files: bool,
) -> None:
    _require_exact_keys(
        section,
        label=label,
        required={"run_id", "status", "timestamp_utc", "timestamp_source", "artifacts", "metrics"},
        errors=errors,
    )
    if not isinstance(section, dict):
        return

    if not _is_non_empty_str(section.get("run_id")):
        errors.append(f"{label}.run_id invalid")

    status = section.get("status")
    allowed_status = VALID_SECTION_STATUS if allow_missing else VALID_UI_STATUS
    if status not in allowed_status:
        errors.append(f"{label}.status invalid: {status!r}")

    if not _parse_iso(section.get("timestamp_utc")):
        errors.append(f"{label}.timestamp_utc invalid")

    source = section.get("timestamp_source")
    if source not in VALID_TIMESTAMP_SOURCE:
        errors.append(f"{label}.timestamp_source invalid: {source!r}")

    artifacts = section.get("artifacts")
    _require_exact_keys(
        artifacts,
        label=f"{label}.artifacts",
        required=set(required_artifact_keys),
        errors=errors,
    )
    if not isinstance(artifacts, dict):
        return

    for key in required_artifact_keys:
        value = artifacts.get(key)
        if not isinstance(value, str):
            errors.append(f"{label}.artifacts.{key} must be string")
            continue
        if status == "missing":
            if value.strip():
                errors.append(f"{label}.artifacts.{key} must be empty when status=missing")
            continue
        if not value.strip():
            errors.append(f"{label}.artifacts.{key} missing/invalid")
            continue
        if check_files and key in ARTIFACT_PATH_KEYS:
            _normalize_and_check_path(value, label=f"{label}.artifacts.{key}", errors=errors, check_files=True)

    metrics = section.get("metrics")
    if not isinstance(metrics, dict):
        errors.append(f"{label}.metrics invalid")


def _validate_strict_config(payload: dict[str, Any], *, errors: list[str]) -> None:
    strict_mode = payload.get("strict_mode")
    strict_sections = payload.get("strict_required_sections")
    if not isinstance(strict_mode, bool):
        errors.append("root.strict_mode invalid")
    if not isinstance(strict_sections, list) or not strict_sections:
        errors.append("root.strict_required_sections invalid")
        return
    seen: set[str] = set()
    for section in strict_sections:
        if not isinstance(section, str) or section not in STRICT_SECTION_IDS:
            errors.append(f"root.strict_required_sections invalid item: {section!r}")
            continue
        if section in seen:
            errors.append(f"root.strict_required_sections duplicated item: {section}")
        seen.add(section)

    if strict_mode and not errors:
        evidence = payload["evidence"]
        status_map = {
            "ui_truth": evidence["ui_truth"]["status"],
            "ui_flake_p0": evidence["ui_flake"]["p0"]["status"],
            "ui_flake_p1": evidence["ui_flake"]["p1"]["status"],
            "ui_full_strict": evidence["ui_full_strict"]["status"],
            "mutation": evidence["mutation"]["status"],
            "security": evidence["security"]["status"],
            "incident": evidence["incident"]["status"],
        }
        missing = [item for item in strict_sections if status_map.get(item) == "missing"]
        if missing:
            errors.append(f"strict_mode violation: missing sections {', '.join(missing)}")


def validate_manifest(
    payload: Any,
    *,
    check_files: bool = True,
    schema_path: Path = DEFAULT_SCHEMA,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["manifest must be object"]

    errors.extend(_validate_schema_file(schema_path))

    _require_exact_keys(
        payload,
        label="root",
        required={
            "manifest_type",
            "schema_version",
            "generated_at",
            "overall_status",
            "schema_path",
            "strict_mode",
            "strict_required_sections",
            "sources",
            "evidence",
        },
        optional={"release_context"},
        errors=errors,
    )

    if payload.get("manifest_type") != "cortexpilot_evidence_manifest":
        errors.append(f"root.manifest_type invalid: {payload.get('manifest_type')!r}")

    if payload.get("schema_version") != 2:
        errors.append(f"root.schema_version invalid: {payload.get('schema_version')!r}")

    if not _parse_iso(payload.get("generated_at")):
        errors.append("root.generated_at invalid")

    overall_status = payload.get("overall_status")
    if overall_status not in VALID_OVERALL_STATUS:
        errors.append(f"root.overall_status invalid: {overall_status!r}")

    schema_path_value = payload.get("schema_path")
    if not _is_non_empty_str(schema_path_value):
        errors.append("root.schema_path missing/invalid")
    elif check_files:
        _normalize_and_check_path(str(schema_path_value), label="root.schema_path", errors=errors, check_files=True)

    sources = payload.get("sources")
    _require_exact_keys(
        sources,
        label="root.sources",
        required={
            "truth_report",
            "flake_p0_report",
            "flake_p1_report",
            "full_strict_report",
            "mutation_report",
            "security_report",
            "incident_report",
        },
        errors=errors,
    )
    if isinstance(sources, dict):
        for key in ("truth_report", "flake_p0_report", "flake_p1_report", "full_strict_report"):
            value = sources.get(key)
            if not _is_non_empty_str(value):
                errors.append(f"root.sources.{key} missing/invalid")
                continue
            if check_files:
                _normalize_and_check_path(str(value), label=f"root.sources.{key}", errors=errors, check_files=True)
        for key in ("mutation_report", "security_report", "incident_report"):
            value = sources.get(key)
            if not isinstance(value, str):
                errors.append(f"root.sources.{key} must be string")
                continue
            if value.strip() and check_files:
                _normalize_and_check_path(str(value), label=f"root.sources.{key}", errors=errors, check_files=True)

    evidence = payload.get("evidence")
    _require_exact_keys(
        evidence,
        label="root.evidence",
        required={"ui_truth", "ui_flake", "ui_full_strict", "mutation", "security", "incident"},
        errors=errors,
    )
    if not isinstance(evidence, dict):
        return errors

    _validate_section(
        evidence.get("ui_truth"),
        label="evidence.ui_truth",
        required_artifact_keys=("report_json",),
        allow_missing=False,
        errors=errors,
        check_files=check_files,
    )
    ui_flake = evidence.get("ui_flake")
    _require_exact_keys(ui_flake, label="evidence.ui_flake", required={"p0", "p1"}, errors=errors)
    if isinstance(ui_flake, dict):
        _validate_section(
            ui_flake.get("p0"),
            label="evidence.ui_flake.p0",
            required_artifact_keys=("report_json", "attempts_jsonl", "attempts_sha256", "report_markdown"),
            allow_missing=False,
            errors=errors,
            check_files=check_files,
        )
        _validate_section(
            ui_flake.get("p1"),
            label="evidence.ui_flake.p1",
            required_artifact_keys=("report_json", "attempts_jsonl", "attempts_sha256", "report_markdown"),
            allow_missing=False,
            errors=errors,
            check_files=check_files,
        )

    _validate_section(
        evidence.get("ui_full_strict"),
        label="evidence.ui_full_strict",
        required_artifact_keys=("report_json", "click_inventory_report"),
        allow_missing=False,
        errors=errors,
        check_files=check_files,
    )
    _validate_section(
        evidence.get("mutation"),
        label="evidence.mutation",
        required_artifact_keys=("report_json",),
        allow_missing=True,
        errors=errors,
        check_files=check_files,
    )
    _validate_section(
        evidence.get("security"),
        label="evidence.security",
        required_artifact_keys=("report_json",),
        allow_missing=True,
        errors=errors,
        check_files=check_files,
    )
    _validate_section(
        evidence.get("incident"),
        label="evidence.incident",
        required_artifact_keys=("report_json",),
        allow_missing=True,
        errors=errors,
        check_files=check_files,
    )

    if not errors:
        statuses = [
            evidence["ui_truth"]["status"],
            evidence["ui_flake"]["p0"]["status"],
            evidence["ui_flake"]["p1"]["status"],
            evidence["ui_full_strict"]["status"],
        ]
        for key in ("mutation", "security", "incident"):
            status = evidence[key]["status"]
            if status != "missing":
                statuses.append(status)
        expected_overall = "pass" if all(item == "pass" for item in statuses) else "fail"
        if overall_status != expected_overall:
            errors.append(
                f"root.overall_status inconsistent: actual={overall_status!r}, expected={expected_overall!r}"
            )

    if not errors:
        _validate_strict_config(payload, errors=errors)
    release_context = payload.get("release_context")
    if isinstance(release_context, dict):
        _require_exact_keys(
            release_context,
            label="root.release_context",
            required={
                "source_manifest",
                "source_run_id",
                "source_route",
                "source_event",
                "freshness_window_sec",
                "provenance_report",
                "current_run_index",
                "analytics_exclusions",
            },
            errors=errors,
        )
        if check_files and _is_non_empty_str(release_context.get("source_manifest")):
            _normalize_and_check_path(
                str(release_context["source_manifest"]),
                label="root.release_context.source_manifest",
                errors=errors,
                check_files=True,
            )
        for key in ("source_run_id", "source_route", "source_event"):
            if not _is_non_empty_str(release_context.get(key)):
                errors.append(f"root.release_context.{key} missing/invalid")
        if not isinstance(release_context.get("freshness_window_sec"), int) or int(release_context.get("freshness_window_sec")) < 0:
            errors.append("root.release_context.freshness_window_sec invalid")
        for key in ("provenance_report", "current_run_index"):
            if not _is_non_empty_str(release_context.get(key)):
                errors.append(f"root.release_context.{key} missing/invalid")
            elif check_files:
                _normalize_and_check_path(
                    str(release_context[key]),
                    label=f"root.release_context.{key}",
                    errors=errors,
                    check_files=True,
                )
        analytics_exclusions = release_context.get("analytics_exclusions")
        if not isinstance(analytics_exclusions, list):
            errors.append("root.release_context.analytics_exclusions invalid")

        if not errors:
            provenance_path = _normalize_and_check_path(
                str(release_context["provenance_report"]),
                label="root.release_context.provenance_report",
                errors=errors,
                check_files=check_files,
            )
            current_run_index_path = _normalize_and_check_path(
                str(release_context["current_run_index"]),
                label="root.release_context.current_run_index",
                errors=errors,
                check_files=check_files,
            )
            release_generated_at = _parse_iso_dt(payload.get("generated_at"))
            freshness_window = int(release_context.get("freshness_window_sec") or 0)
            if release_generated_at is not None and freshness_window > 0:
                for section_id, section in (
                    ("ui_truth", evidence["ui_truth"]),
                    ("ui_flake_p0", evidence["ui_flake"]["p0"]),
                    ("ui_flake_p1", evidence["ui_flake"]["p1"]),
                    ("ui_full_strict", evidence["ui_full_strict"]),
                ):
                    section_ts = _parse_iso_dt(section.get("timestamp_utc"))
                    if section_ts is None:
                        errors.append(f"strict section timestamp missing: {section_id}")
                        continue
                    delta = abs((release_generated_at - section_ts).total_seconds())
                    if delta > freshness_window:
                        errors.append(
                            f"strict section timestamp outside freshness window: {section_id} delta_sec={int(delta)} window_sec={freshness_window}"
                        )
            if provenance_path and provenance_path.is_file():
                provenance_payload = json.loads(provenance_path.read_text(encoding="utf-8"))
                workflow = provenance_payload.get("workflow")
                if not isinstance(workflow, dict):
                    errors.append("provenance.workflow invalid")
                else:
                    for key in ("github_run_id", "github_run_attempt", "github_ref", "github_event_name"):
                        if not _is_non_empty_str(workflow.get(key)):
                            errors.append(f"provenance.workflow.{key} missing/invalid")
            if current_run_index_path and current_run_index_path.is_file():
                current_run_index = json.loads(current_run_index_path.read_text(encoding="utf-8"))
                current_files = {
                    str(item.get("path") or "")
                    for group in current_run_index.get("groups", [])
                    if isinstance(group, dict)
                    for item in group.get("files", [])
                    if isinstance(item, dict)
                }
                for excluded in analytics_exclusions:
                    if _is_non_empty_str(excluded) and str(excluded) in current_files:
                        errors.append(f"analytics-only artifact present in current_run_index: {excluded}")
    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate CortexPilot evidence manifest schema.")
    parser.add_argument("--manifest", required=True, help="Path to evidence manifest JSON.")
    parser.add_argument(
        "--schema",
        default=str(DEFAULT_SCHEMA),
        help="Path to evidence manifest schema JSON.",
    )
    parser.add_argument(
        "--no-check-files",
        action="store_true",
        help="Disable artifact/source file existence checks.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest_path = Path(args.manifest).expanduser().resolve()
    schema_path = Path(args.schema).expanduser().resolve()
    if not manifest_path.is_file():
        print(f"❌ [evidence-manifest] missing file: {manifest_path}")
        return 1
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"❌ [evidence-manifest] invalid json: {exc}")
        return 1

    errors = validate_manifest(payload, check_files=not args.no_check_files, schema_path=schema_path)
    if errors:
        print("❌ [evidence-manifest] schema check failed")
        for item in errors:
            print(f"- {item}")
        return 1

    print(f"✅ [evidence-manifest] schema check passed: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
