from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "refresh_governance_evidence_manifest.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("refresh_governance_evidence_manifest", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load refresh_governance_evidence_manifest module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_reuse_upstream_records_requires_all_fresh_passed_receipts(tmp_path: Path) -> None:
    module = _load_module()
    module.ROOT = tmp_path
    module.UPSTREAM_RECORD_FRESH_SEC = 3600

    provider_path = tmp_path / ".runtime-cache/test_output/governance/upstream/provider-runtime-path.json"
    ci_image_path = tmp_path / ".runtime-cache/test_output/governance/upstream/ci-core-image.json"
    provider_log_path = tmp_path / ".runtime-cache/test_output/governance/upstream/provider-runtime-path.log"
    ci_image_log_path = tmp_path / ".runtime-cache/test_output/governance/upstream/ci-core-image.log"
    provider_log_path.parent.mkdir(parents=True, exist_ok=True)
    provider_log_path.write_text("provider ok\n", encoding="utf-8")
    ci_image_log_path.write_text("ci image ok\n", encoding="utf-8")

    _write_json(
        provider_path,
        {
            "integration_slice": "provider-runtime-path",
            "verification_mode": "smoke",
            "status": "passed",
            "last_verified_at": "2026-03-26T12:00:00+00:00",
            "last_verified_run_id": "run-provider",
            "verification_batch_id": "batch-1",
            "last_verified_artifact": ".runtime-cache/test_output/governance/upstream/provider-runtime-path.log",
            "command": "provider",
            "exit_code": 0,
            "rollback_path": "n/a",
            "failure_attribution_hint": "n/a",
        },
    )
    _write_json(
        ci_image_path,
        {
            "integration_slice": "ci-core-image",
            "verification_mode": "smoke",
            "status": "passed",
            "last_verified_at": "2026-03-26T12:01:00+00:00",
            "last_verified_run_id": "run-ci-image",
            "verification_batch_id": "batch-1",
            "last_verified_artifact": ".runtime-cache/test_output/governance/upstream/ci-core-image.log",
            "command": "ci-image",
            "exit_code": 0,
            "rollback_path": "n/a",
            "failure_attribution_hint": "n/a",
        },
    )

    check = {
        "id": "verification_smoke",
        "weight": 8,
        "artifacts": [
            ".runtime-cache/test_output/governance/upstream/provider-runtime-path.json",
            ".runtime-cache/test_output/governance/upstream/ci-core-image.json",
        ],
    }

    result = module._reuse_upstream_verification_records(check)

    assert result is not None
    assert result["ok"] is True
    assert result["command"] == ["reuse:fresh-upstream-records"]
    assert all(row["exists"] for row in result["artifacts"])
    assert "batches: batch-1" in result["output"]
    assert "missing slices" not in result["output"]
    assert "failing slices" not in result["output"]


def test_reuse_upstream_records_returns_none_when_receipts_are_missing_or_failed(tmp_path: Path) -> None:
    module = _load_module()
    module.ROOT = tmp_path
    module.UPSTREAM_RECORD_FRESH_SEC = 3600

    provider_path = tmp_path / ".runtime-cache/test_output/governance/upstream/provider-runtime-path.json"
    provider_log_path = tmp_path / ".runtime-cache/test_output/governance/upstream/provider-runtime-path.log"
    provider_log_path.parent.mkdir(parents=True, exist_ok=True)
    provider_log_path.write_text("provider ok\n", encoding="utf-8")
    _write_json(
        provider_path,
        {
            "integration_slice": "provider-runtime-path",
            "verification_mode": "smoke",
            "status": "failed",
            "last_verified_at": "2026-03-26T12:00:00+00:00",
            "last_verified_run_id": "run-provider",
            "verification_batch_id": "batch-1",
            "last_verified_artifact": ".runtime-cache/test_output/governance/upstream/provider-runtime-path.log",
            "command": "provider",
            "exit_code": 1,
            "rollback_path": "n/a",
            "failure_attribution_hint": "n/a",
        },
    )

    check = {
        "id": "verification_smoke",
        "weight": 8,
        "artifacts": [
            ".runtime-cache/test_output/governance/upstream/provider-runtime-path.json",
            ".runtime-cache/test_output/governance/upstream/ci-core-image.json",
        ],
    }

    assert module._reuse_upstream_verification_records(check) is None


def test_reuse_upstream_records_returns_none_when_receipts_are_stale_or_artifact_missing(tmp_path: Path) -> None:
    module = _load_module()
    module.ROOT = tmp_path
    module.UPSTREAM_RECORD_FRESH_SEC = 60

    provider_path = tmp_path / ".runtime-cache/test_output/governance/upstream/provider-runtime-path.json"
    _write_json(
        provider_path,
        {
            "integration_slice": "provider-runtime-path",
            "verification_mode": "smoke",
            "status": "passed",
            "last_verified_at": "2026-03-26T12:00:00+00:00",
            "last_verified_run_id": "run-provider",
            "verification_batch_id": "batch-1",
            "last_verified_artifact": ".runtime-cache/test_output/governance/upstream/provider-runtime-path.log",
            "command": "provider",
            "exit_code": 0,
            "rollback_path": "n/a",
            "failure_attribution_hint": "n/a",
        },
    )
    old_ts = provider_path.stat().st_mtime - 7200
    os.utime(provider_path, (old_ts, old_ts))

    check = {
        "id": "verification_smoke",
        "weight": 8,
        "artifacts": [
            ".runtime-cache/test_output/governance/upstream/provider-runtime-path.json",
        ],
    }

    assert module._reuse_upstream_verification_records(check) is None


def test_reuse_upstream_records_returns_none_when_batches_do_not_match(tmp_path: Path) -> None:
    module = _load_module()
    module.ROOT = tmp_path
    module.UPSTREAM_RECORD_FRESH_SEC = 3600

    base_dir = tmp_path / ".runtime-cache/test_output/governance/upstream"
    base_dir.mkdir(parents=True, exist_ok=True)
    for name, batch_id in (
        ("provider-runtime-path", "batch-1"),
        ("ci-core-image", "batch-2"),
    ):
        (base_dir / f"{name}.log").write_text(f"{name} ok\n", encoding="utf-8")
        _write_json(
            base_dir / f"{name}.json",
            {
                "integration_slice": name,
                "verification_mode": "smoke",
                "status": "passed",
                "last_verified_at": "2026-03-26T12:00:00+00:00",
                "last_verified_run_id": f"run-{name}",
                "verification_batch_id": batch_id,
                "last_verified_artifact": f".runtime-cache/test_output/governance/upstream/{name}.log",
                "command": name,
                "exit_code": 0,
                "rollback_path": "n/a",
                "failure_attribution_hint": "n/a",
            },
        )

    check = {
        "id": "verification_smoke",
        "weight": 8,
        "artifacts": [
            ".runtime-cache/test_output/governance/upstream/provider-runtime-path.json",
            ".runtime-cache/test_output/governance/upstream/ci-core-image.json",
        ],
    }

    assert module._reuse_upstream_verification_records(check) is None


def test_reuse_clean_room_recovery_record_when_fresh_and_passed(tmp_path: Path) -> None:
    module = _load_module()
    module.ROOT = tmp_path
    module.UPSTREAM_RECORD_FRESH_SEC = 3600

    report_path = tmp_path / ".runtime-cache/test_output/governance/clean_room_recovery.json"
    _write_json(
        report_path,
        {
            "status": "pass",
            "generated_at": "2026-04-03T12:00:00+00:00",
        },
    )

    check = {
        "id": "clean_room_recovery",
        "weight": 5,
        "artifacts": [".runtime-cache/test_output/governance/clean_room_recovery.json"],
    }

    result = module._reuse_clean_room_recovery_record(check)

    assert result is not None
    assert result["ok"] is True
    assert result["command"] == ["reuse:fresh-clean-room-record"]
    assert result["artifacts"][0]["exists"] is True


def test_reuse_clean_room_recovery_record_accepts_ok_status_from_shell_receipt(tmp_path: Path) -> None:
    module = _load_module()
    module.ROOT = tmp_path
    module.UPSTREAM_RECORD_FRESH_SEC = 3600

    report_path = tmp_path / ".runtime-cache/test_output/governance/clean_room_recovery.json"
    _write_json(
        report_path,
        {
            "status": "ok",
            "generated_at": "2026-04-04T12:00:00+00:00",
            "exit_code": 0,
        },
    )

    check = {
        "id": "clean_room_recovery",
        "weight": 5,
        "artifacts": [".runtime-cache/test_output/governance/clean_room_recovery.json"],
    }

    result = module._reuse_clean_room_recovery_record(check)

    assert result is not None
    assert result["ok"] is True
    assert result["command"] == ["reuse:fresh-clean-room-record"]


def test_reuse_clean_room_recovery_record_returns_none_when_stale_or_failed(tmp_path: Path) -> None:
    module = _load_module()
    module.ROOT = tmp_path
    module.UPSTREAM_RECORD_FRESH_SEC = 60

    report_path = tmp_path / ".runtime-cache/test_output/governance/clean_room_recovery.json"
    _write_json(
        report_path,
        {
            "status": "fail",
            "generated_at": "2026-04-03T12:00:00+00:00",
        },
    )
    old_ts = report_path.stat().st_mtime - 7200
    os.utime(report_path, (old_ts, old_ts))

    check = {
        "id": "clean_room_recovery",
        "weight": 5,
        "artifacts": [".runtime-cache/test_output/governance/clean_room_recovery.json"],
    }

    assert module._reuse_clean_room_recovery_record(check) is None


def test_run_check_falls_back_to_real_smoke_command_when_reuse_is_not_allowed(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    module.ROOT = tmp_path
    monkeypatch.delenv("OPENVIBECODING_CI_ROUTE_ID", raising=False)

    def _fake_run(cmd: list[str]) -> tuple[bool, str]:
        assert cmd == ["python3", "scripts/verify_upstream_slices.py", "--mode", "smoke"]
        record_path = tmp_path / ".runtime-cache/test_output/governance/upstream/provider-runtime-path.json"
        artifact_path = tmp_path / ".runtime-cache/test_output/governance/upstream/provider-runtime-path.log"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text("provider ok\n", encoding="utf-8")
        _write_json(
            record_path,
            {
                "integration_slice": "provider-runtime-path",
                "verification_mode": "smoke",
                "status": "passed",
                "last_verified_at": "2026-03-26T12:00:00+00:00",
                "last_verified_run_id": "run-provider",
                "verification_batch_id": "batch-1",
                "last_verified_artifact": ".runtime-cache/test_output/governance/upstream/provider-runtime-path.log",
                "command": "provider",
                "exit_code": 0,
                "rollback_path": "n/a",
                "failure_attribution_hint": "n/a",
            },
        )
        return True, "verification records written"

    module._run = _fake_run

    check = {
        "id": "verification_smoke",
        "weight": 8,
        "command": ["python3", "scripts/verify_upstream_slices.py", "--mode", "smoke"],
        "artifacts": [
            ".runtime-cache/test_output/governance/upstream/provider-runtime-path.json",
        ],
    }

    result = module._run_check(check)

    assert result["ok"] is True
    assert result["command"] == ["python3", "scripts/verify_upstream_slices.py", "--mode", "smoke"]
    assert "verification records written" in result["output"]


def test_truncate_output_caps_large_check_logs() -> None:
    module = _load_module()
    module.CHECK_OUTPUT_MAX_CHARS = 16

    truncated = module._truncate_output("0123456789abcdefghijklmnop")

    assert truncated.startswith("0123456789abcdef")
    assert "[truncated " in truncated


def test_frontend_observability_check_cleans_workspace_modules() -> None:
    module = _load_module()

    check = next(
        item
        for item in module.CHECKS["logging"]
        if item["id"] == "frontend_observability_tests"
    )

    command = " ".join(check["command"])
    assert "install_frontend_api_client_deps.sh" in command
    assert "cleanup_workspace_modules.sh" in command
