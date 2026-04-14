#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / ".runtime-cache" / "test_output" / "governance" / "governance_evidence_manifest.json"
DEFAULT_UPSTREAM_MATRIX = ROOT / "configs" / "upstream_compat_matrix.json"
UPSTREAM_RECORD_FRESH_SEC = int(os.environ.get("OPENVIBECODING_UPSTREAM_RECORD_FRESH_SEC", "1800"))
CHECK_OUTPUT_MAX_CHARS = int(os.environ.get("OPENVIBECODING_GOVERNANCE_CHECK_OUTPUT_MAX_CHARS", "12000"))
FORBIDDEN_REPORT_TOKENS = ("jarvis-command-tower", "jarvis")
FORBIDDEN_REPORT_REPLACEMENT = "[legacy-redacted]"
UPSTREAM_EXEMPT_ROUTE_IDS = {"trusted_pr", "untrusted_pr", "push_main"}
UPSTREAM_ROUTE_EXEMPT_CHECKS = {
    "verification_smoke",
    "inventory_matrix_gate",
    "same_run_cohesion",
}

CHECKS = {
    "architecture": [
        {"id": "root_allowlist", "weight": 6, "command": ["python3", "scripts/check_root_allowlist.py", "--mode", "authoritative"]},
        {"id": "module_boundaries", "weight": 7, "command": ["python3", "scripts/check_module_boundaries.py"]},
        {"id": "runtime_contract_split", "weight": 6, "command": ["python3", "scripts/check_runtime_artifact_policy.py"]},
        {"id": "docs_ssot", "weight": 4, "command": ["python3", "scripts/check_docs_manual_fact_boundary.py"]},
        {"id": "no_legacy_active_paths", "weight": 7, "command": ["python3", "scripts/check_legacy_active_paths.py"]},
    ],
    "cache": [
        {"id": "artifact_policy", "weight": 4, "command": ["python3", "scripts/check_runtime_artifact_policy.py"]},
        {"id": "root_noise_clear", "weight": 2, "command": ["python3", "scripts/check_root_semantic_cleanliness.py"]},
        {"id": "toolchain_root_hardcut", "weight": 4, "command": ["python3", "scripts/check_toolchain_hardcut.py"]},
        {
            "id": "clean_room_recovery",
            "weight": 5,
            "command": ["bash", "scripts/check_clean_room_recovery.sh", "--skip-governance-scorecard"],
            "artifacts": [".runtime-cache/test_output/governance/clean_room_recovery.json"],
        },
        {
            "id": "retention_report",
            "weight": 3,
            "command": ["bash", "-lc", "bash scripts/cleanup_runtime.sh dry-run && python3 scripts/check_retention_report.py"],
            "artifacts": [".runtime-cache/openvibecoding/reports/retention_report.json"],
        },
        {"id": "cleanup_demoted", "weight": 2, "command": ["bash", "-lc", "OPENVIBECODING_HYGIENE_SKIP_UPSTREAM=1 bash scripts/check_repo_hygiene.sh"]},
    ],
    "logging": [
        {
            "id": "log_contract_samples",
            "weight": 8,
            "command": ["python3", "scripts/check_log_event_contract.py"],
            "artifacts": [".runtime-cache/test_output/governance/log_event_contract_report.json"],
        },
        {
            "id": "log_correlation_contract",
            "weight": 2,
            "command": ["python3", "scripts/check_log_correlation_contract.py"],
        },
        {
            "id": "log_lane_layout",
            "weight": 2,
            "command": ["python3", "scripts/check_log_lane_layout.py"],
        },
        {
            "id": "backend_logger_tests",
            "weight": 4,
            "command": [
                "bash",
                "-lc",
                "source scripts/lib/env.sh && PYTHONPATH=apps/orchestrator/src ${OPENVIBECODING_PYTHON:-python3} -m pytest apps/orchestrator/tests/test_observability_logger.py -q",
            ],
        },
        {
            "id": "frontend_observability_tests",
            "weight": 4,
            "command": [
                "bash",
                "-lc",
                "bash scripts/install_frontend_api_client_deps.sh >/dev/null && node --test packages/frontend-api-client/tests/observability.test.mjs && bash scripts/cleanup_workspace_modules.sh >/dev/null",
            ],
        },
    ],
    "root_cleanliness": [
        {"id": "allowlist_gate", "weight": 4, "command": ["python3", "scripts/check_root_allowlist.py", "--mode", "authoritative"]},
        {"id": "no_forbidden_outputs", "weight": 3, "command": ["python3", "scripts/check_root_semantic_cleanliness.py"]},
        {"id": "hygiene_gate", "weight": 3, "command": ["bash", "-lc", "OPENVIBECODING_HYGIENE_SKIP_UPSTREAM=1 bash scripts/check_repo_hygiene.sh"]},
    ],
    "upstream": [
        {
            "id": "verification_smoke",
            "weight": 8,
            "command": ["python3", "scripts/verify_upstream_slices.py", "--mode", "smoke"],
        },
        {
            "id": "inventory_matrix_gate",
            "weight": 7,
            "command": ["python3", "scripts/check_upstream_inventory.py", "--mode", "gate"],
            "artifacts": [".runtime-cache/test_output/governance/upstream_inventory_report.json"],
        },
        {
            "id": "same_run_cohesion",
            "weight": 1,
            "command": ["python3", "scripts/check_upstream_same_run_cohesion.py"],
            "artifacts": [".runtime-cache/test_output/governance/upstream_same_run_cohesion.json"],
        },
        {"id": "supply_chain", "weight": 2, "command": ["python3", "scripts/check_ci_supply_chain_policy.py"]},
        {
            "id": "public_contracts",
            "weight": 1,
            "command": [
                "python3",
                "-c",
                (
                    "from pathlib import Path; text=Path('apps/orchestrator/src/openvibecoding_orch/runners/provider_resolution.py')"
                    ".read_text(encoding='utf-8'); banned=['/internal/','private implementation']; "
                    "raise SystemExit(1 if any(item in text for item in banned) else 0)"
                ),
            ],
        },
        {
            "id": "verification_paths",
            "weight": 1,
            "command": [
                "python3",
                "-c",
                (
                    "import json; from pathlib import Path; rows=json.loads(Path('configs/upstream_compat_matrix.json').read_text())['matrix']; "
                    "paths=[row.get('verification_record_path','') for row in rows]; "
                    "raise SystemExit(0 if rows and all(isinstance(path, str) and path.startswith('.runtime-cache/') for path in paths) and len(paths)==len(set(paths)) else 1)"
                ),
            ],
        },
    ],
}


def _run(cmd: list[str]) -> tuple[bool, str]:
    env = os.environ.copy()
    env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    existing_pytest_addopts = env.get("PYTEST_ADDOPTS", "").strip()
    cache_disable = "-p no:cacheprovider"
    if cache_disable not in existing_pytest_addopts:
        env["PYTEST_ADDOPTS"] = f"{existing_pytest_addopts} {cache_disable}".strip()
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, env=env)
    output = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part).strip()
    return result.returncode == 0, output


def _sanitize_text(value: str) -> str:
    sanitized = value
    for token in FORBIDDEN_REPORT_TOKENS:
        sanitized = re.sub(token, FORBIDDEN_REPORT_REPLACEMENT, sanitized, flags=re.IGNORECASE)
    return sanitized


def _sanitize_payload(value: object) -> object:
    if isinstance(value, str):
        return _sanitize_text(value)
    if isinstance(value, list):
        return [_sanitize_payload(item) for item in value]
    if isinstance(value, dict):
        return {key: _sanitize_payload(item) for key, item in value.items()}
    return value


def _truncate_output(value: str) -> str:
    if len(value) <= CHECK_OUTPUT_MAX_CHARS:
        return value
    omitted = len(value) - CHECK_OUTPUT_MAX_CHARS
    return value[:CHECK_OUTPUT_MAX_CHARS].rstrip() + f"\n...[truncated {omitted} chars]"


def _artifact_status(artifacts: list[str]) -> tuple[bool, list[dict[str, object]]]:
    rows: list[dict[str, object]] = []
    ok = True
    for raw_path in artifacts:
        path = ROOT / raw_path
        exists = path.exists()
        rows.append(
            {
                "path": raw_path,
                "exists": exists,
                "mtime": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat() if exists else None,
            }
        )
        if not exists:
            ok = False
    return ok, rows


def _resolve_check_artifacts(check: dict[str, object]) -> list[str]:
    explicit = [str(item) for item in list(check.get("artifacts", [])) if str(item).strip()]
    if explicit:
        return explicit
    if str(check.get("id")) != "verification_smoke":
        return explicit
    matrix_path = ROOT / DEFAULT_UPSTREAM_MATRIX.relative_to(ROOT)
    if not matrix_path.exists():
        return []
    try:
        payload = json.loads(matrix_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    rows = payload.get("matrix", [])
    if not isinstance(rows, list):
        return []
    artifacts: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        record_path = str(row.get("verification_record_path") or "").strip()
        if record_path and record_path not in artifacts:
            artifacts.append(record_path)
    return artifacts


def _reuse_upstream_verification_records(check: dict[str, object]) -> dict[str, object] | None:
    if str(check.get("id")) != "verification_smoke":
        return None
    artifacts = _resolve_check_artifacts(check)
    if not artifacts:
        return None
    _, artifact_rows = _artifact_status(artifacts)

    now_ts = time.time()
    batches: set[str] = set()
    for raw_path in artifacts:
        path = ROOT / raw_path
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        stat = path.stat()
        if now_ts - stat.st_mtime > UPSTREAM_RECORD_FRESH_SEC:
            return None
        if str(payload.get("verification_mode") or "").strip().lower() != "smoke":
            return None
        batch_id = str(payload.get("verification_batch_id") or "").strip()
        if not batch_id:
            return None
        batches.add(batch_id)
        status = str(payload.get("status") or "").strip().lower()
        if status != "passed":
            return None
        artifact_rel = str(payload.get("last_verified_artifact") or "").strip()
        if not artifact_rel:
            return None
        artifact_path = ROOT / artifact_rel
        if not artifact_path.exists():
            return None
    if len(batches) != 1:
        return None

    batch_summary = ", ".join(sorted(batch for batch in batches if batch))
    output = (
        "reused fresh upstream verification records"
        + (f" (batches: {batch_summary})" if batch_summary else "")
    )
    return {
        "id": str(check["id"]),
        "weight": int(check["weight"]),
        "ok": True,
        "command": ["reuse:fresh-upstream-records"],
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "duration_sec": 0.0,
        "artifacts": artifact_rows,
        "output": output,
    }


def _reuse_clean_room_recovery_record(check: dict[str, object]) -> dict[str, object] | None:
    if str(check.get("id")) != "clean_room_recovery":
        return None
    artifacts = _resolve_check_artifacts(check)
    if len(artifacts) != 1:
        return None

    raw_path = artifacts[0]
    path = ROOT / raw_path
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    if str(payload.get("status") or "").strip().lower() not in {"ok", "pass", "passed"}:
        return None

    stat = path.stat()
    now_ts = time.time()
    if now_ts - stat.st_mtime > UPSTREAM_RECORD_FRESH_SEC:
        return None

    artifact_ok, artifact_rows = _artifact_status(artifacts)
    if not artifact_ok:
        return None

    return {
        "id": str(check["id"]),
        "weight": int(check["weight"]),
        "ok": True,
        "command": ["reuse:fresh-clean-room-record"],
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "duration_sec": 0.0,
        "artifacts": artifact_rows,
        "output": "reused fresh clean-room recovery report",
    }


def _current_ci_route_id() -> str:
    return str(os.environ.get("OPENVIBECODING_CI_ROUTE_ID") or "").strip()


def _route_exempt_upstream_check(check: dict[str, object]) -> dict[str, object] | None:
    route_id = _current_ci_route_id()
    if route_id not in UPSTREAM_EXEMPT_ROUTE_IDS:
        return None
    check_id = str(check.get("id") or "")
    if check_id not in UPSTREAM_ROUTE_EXEMPT_CHECKS:
        return None
    if route_id in {"trusted_pr", "untrusted_pr"}:
        route_scope = "workflow_dispatch closeout lanes, not pull_request routes"
    else:
        route_scope = "protected/manual closeout lanes, not the hosted-first push_main base lane"
    return {
        "id": check_id,
        "weight": int(check["weight"]),
        "ok": True,
        "command": [f"route-exempt:{route_id}"],
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "duration_sec": 0.0,
        "artifacts": [],
        "output": (
            f"skipped `{check_id}` on `{route_id}` because protected upstream/live smoke "
            f"verification belongs to {route_scope}"
        ),
    }


def _run_check(check: dict[str, object]) -> dict[str, object]:
    exempt = _route_exempt_upstream_check(check)
    if exempt is not None:
        return exempt
    reused = _reuse_upstream_verification_records(check)
    if reused is not None:
        return reused
    reused = _reuse_clean_room_recovery_record(check)
    if reused is not None:
        return reused
    check_id = str(check["id"])
    weight = int(check["weight"])
    cmd = list(check["command"])
    artifacts = _resolve_check_artifacts(check)

    started = time.monotonic()
    executed_at = datetime.now(timezone.utc).isoformat()
    ok, output = _run(cmd)
    artifact_ok, artifact_rows = _artifact_status(artifacts)
    duration_sec = round(time.monotonic() - started, 3)

    if artifacts and not artifact_ok:
        ok = False
        artifact_failures = [row["path"] for row in artifact_rows if not row["exists"]]
        suffix = ", ".join(str(item) for item in artifact_failures)
        output = "\n".join(part for part in [output, f"missing artifacts: {suffix}"] if part)

    return {
        "id": check_id,
        "weight": weight,
        "ok": ok,
        "command": cmd,
        "executed_at": executed_at,
        "duration_sec": duration_sec,
        "artifacts": artifact_rows,
        "output": _truncate_output(_sanitize_text(output)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute governance checks and write an explicit evidence manifest.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    failed_dimensions: list[str] = []
    dimensions: dict[str, object] = {}
    for dimension, checks in CHECKS.items():
        rows = [_run_check(check) for check in checks]
        if not all(bool(row.get("ok")) for row in rows):
            failed_dimensions.append(dimension)
        dimensions[dimension] = {"checks": rows}

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dimensions": dimensions,
        "failed_dimensions": failed_dimensions,
        "execution_authority": "explicit evidence refresh",
    }
    manifest = _sanitize_payload(manifest)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    if failed_dimensions:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
