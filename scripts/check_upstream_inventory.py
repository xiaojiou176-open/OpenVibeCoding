#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = ROOT / "configs" / "upstream_inventory.json"
DEFAULT_MATRIX = ROOT / "configs" / "upstream_compat_matrix.json"
DEFAULT_CI_POLICY = ROOT / "configs" / "ci_governance_policy.json"
DEFAULT_PROVIDER_FILE = ROOT / "apps" / "orchestrator" / "src" / "openvibecoding_orch" / "runners" / "provider_resolution.py"
DEFAULT_CI_DOCKERFILE = ROOT / "infra" / "ci" / "Dockerfile.core"
DEFAULT_OUTPUT = ROOT / ".runtime-cache" / "test_output" / "governance" / "upstream_inventory_report.json"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate upstream inventory and compatibility matrix.")
    parser.add_argument("--inventory", default=str(DEFAULT_INVENTORY))
    parser.add_argument("--matrix", default=str(DEFAULT_MATRIX))
    parser.add_argument("--ci-policy", default=str(DEFAULT_CI_POLICY))
    parser.add_argument("--mode", choices=("report", "gate"), default="gate")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--skip-verification-records", action="store_true")
    args = parser.parse_args()

    inventory = _load_json(Path(args.inventory))
    matrix = _load_json(Path(args.matrix))
    ci_policy = _load_json(Path(args.ci_policy))
    provider_text = DEFAULT_PROVIDER_FILE.read_text(encoding="utf-8")

    errors: list[str] = []
    upstreams = inventory.get("upstreams", [])
    ids = [entry.get("id", "") for entry in upstreams]
    if len(ids) != len(set(ids)):
        errors.append("duplicate upstream inventory ids detected")
    inventory_ids = set(ids)

    required_inventory_fields = {
        "id",
        "kind",
        "owner",
        "criticality",
        "source_type",
        "pin",
        "contract_surface",
        "ingest_path",
        "validation_gate",
        "rollback_path",
        "license_class",
        "security_review_source",
    }
    for entry in upstreams:
        missing = sorted(required_inventory_fields - set(entry))
        if missing:
            errors.append(f"{entry.get('id', '<missing-id>')} missing fields: {', '.join(missing)}")

    now = datetime.now(timezone.utc)
    verification_records: list[dict[str, object]] = []

    for row in matrix.get("matrix", []):
        required_matrix_fields = {
            "integration_slice",
            "owner",
            "upstream_ids",
            "required_gates",
            "validation_gate",
            "smoke_entrypoint",
            "rollback_path",
            "failure_attribution_hint",
            "verification_record_path",
            "same_run_required",
        }
        missing_matrix_fields = sorted(required_matrix_fields - set(row))
        if missing_matrix_fields:
            errors.append(
                f"compatibility matrix row `{row.get('integration_slice', '<unknown>')}` missing fields: {', '.join(missing_matrix_fields)}"
            )
        for upstream_id in row.get("upstream_ids", []):
            if upstream_id not in inventory_ids:
                errors.append(f"compatibility matrix references unknown upstream id: {upstream_id}")
        verification_record = str(row.get("verification_record_path") or "").strip()
        if verification_record and not verification_record.startswith(".runtime-cache/"):
            errors.append(
                f"compatibility matrix row `{row.get('integration_slice', '<unknown>')}` verification_record_path must stay under .runtime-cache/: {verification_record}"
            )
        if verification_record and not args.skip_verification_records:
            record_path = ROOT / verification_record
            record_summary: dict[str, object] = {
                "integration_slice": row.get("integration_slice"),
                "record_path": verification_record,
                "exists": record_path.exists(),
            }
            if not record_path.exists():
                errors.append(f"compatibility matrix row `{row.get('integration_slice', '<unknown>')}` missing verification record: {verification_record}")
                verification_records.append(record_summary)
                continue
            try:
                record_payload = _load_json(record_path)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"verification record unreadable for `{row.get('integration_slice', '<unknown>')}`: {exc}")
                verification_records.append(record_summary)
                continue
            required_record_fields = {
                "integration_slice",
                "verification_mode",
                "status",
                "last_verified_at",
                "last_verified_run_id",
                "verification_batch_id",
                "last_verified_artifact",
                "command",
                "exit_code",
                "rollback_path",
                "failure_attribution_hint",
            }
            missing_record_fields = sorted(required_record_fields - set(record_payload))
            if missing_record_fields:
                errors.append(
                    f"verification record `{verification_record}` missing fields: {', '.join(missing_record_fields)}"
                )
            if record_payload.get("integration_slice") != row.get("integration_slice"):
                errors.append(
                    f"verification record `{verification_record}` slice mismatch: {record_payload.get('integration_slice')!r}"
                )
            if record_payload.get("status") != "passed":
                errors.append(f"verification record `{verification_record}` status is not passed")
            if record_payload.get("verification_mode") != "smoke":
                errors.append(f"verification record `{verification_record}` must come from smoke mode")
            same_run_required = bool(row.get("same_run_required", False))
            verification_batch_id = str(record_payload.get("verification_batch_id") or "").strip()
            if same_run_required and not verification_batch_id:
                errors.append(f"verification record `{verification_record}` missing verification_batch_id")
            record_summary["verification_batch_id"] = verification_batch_id
            timestamp_raw = str(record_payload.get("last_verified_at") or "").strip()
            try:
                verified_at = datetime.fromisoformat(timestamp_raw)
                if verified_at.tzinfo is None:
                    verified_at = verified_at.replace(tzinfo=timezone.utc)
                age_sec = max(0.0, (now - verified_at).total_seconds())
                record_summary["age_sec"] = age_sec
                if age_sec > 24 * 3600:
                    errors.append(f"verification record `{verification_record}` is stale (>24h)")
            except Exception:  # noqa: BLE001
                errors.append(f"verification record `{verification_record}` has invalid last_verified_at")
            artifact_rel = str(record_payload.get("last_verified_artifact") or "").strip()
            if not artifact_rel.startswith(".runtime-cache/"):
                errors.append(f"verification record `{verification_record}` artifact must stay under .runtime-cache/")
            elif not (ROOT / artifact_rel).exists():
                errors.append(f"verification record `{verification_record}` artifact missing: {artifact_rel}")
            verification_records.append(record_summary)

    for provider in ("gemini", "openai", "anthropic"):
        if f'"{provider}": "{provider}"' in provider_text and f"provider:{provider}" not in inventory_ids:
            errors.append(f"provider alias `{provider}` missing from upstream inventory")

    supply_chain = ci_policy.get("supply_chain", {})
    for repo in supply_chain.get("allowed_action_repos", []):
        if f"action-repo:{repo}" not in inventory_ids:
            errors.append(f"allowed action repo missing from upstream inventory: {repo}")
    for host in supply_chain.get("allowed_download_hosts", []):
        if f"download-host:{host}" not in inventory_ids:
            errors.append(f"allowed download host missing from upstream inventory: {host}")

    dockerfile_lines = DEFAULT_CI_DOCKERFILE.read_text(encoding="utf-8").splitlines()
    dockerfile_from = next((line.split("FROM", 1)[1].strip() for line in dockerfile_lines if line.startswith("FROM ")), "")
    ci_image = next((entry for entry in upstreams if entry.get("id") == "ci-image:openvibecoding-ci-core"), None)
    if isinstance(ci_image, dict):
        recorded_pin = str(ci_image.get("pin") or "").strip()
        if dockerfile_from and recorded_pin != dockerfile_from:
            errors.append(
                "ci-image:openvibecoding-ci-core pin drift vs infra/ci/Dockerfile.core "
                f"(inventory={recorded_pin!r}, dockerfile={dockerfile_from!r})"
            )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "upstream_count": len(upstreams),
        "matrix_count": len(matrix.get("matrix", [])),
        "ci_image_pin": {
            "inventory": str(ci_image.get("pin") or "").strip() if isinstance(ci_image, dict) else "",
            "dockerfile_from": dockerfile_from,
        },
        "verification_records": verification_records,
        "errors": errors,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.mode == "report":
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if not errors else 1

    if errors:
        print("❌ [upstream-inventory] violations:")
        for item in errors:
            print(f"- {item}")
        return 1

    print(f"✅ [upstream-inventory] inventory and compatibility matrix satisfied: {output_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
