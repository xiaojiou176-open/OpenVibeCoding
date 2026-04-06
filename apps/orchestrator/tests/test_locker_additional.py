import json
from datetime import datetime, timezone
from pathlib import Path

from cortexpilot_orch.locks import locker


def _write_manifest(runtime_root: Path, run_id: str, status: str) -> None:
    run_dir = runtime_root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text(json.dumps({"run_id": run_id, "status": status}), encoding="utf-8")


def test_locker_parse_and_time_helpers(tmp_path: Path) -> None:
    missing_meta = locker._parse_lock_file(tmp_path / "missing.lock")
    assert missing_meta == {"run_id": "", "ts": "", "path": "", "pid": "", "owner": ""}

    lock_file = tmp_path / "one.lock"
    lock_file.write_text("run_id=run_1\nts=2024-01-01T00:00:00Z\npath=src/a.py\n", encoding="utf-8")
    parsed = locker._parse_lock_file(lock_file)
    assert parsed["run_id"] == "run_1"
    assert parsed["path"] == "src/a.py"
    assert parsed["pid"] == ""
    assert parsed["owner"] == ""

    parsed_ts = locker._parse_ts("2024-01-01T00:00:00Z")
    assert parsed_ts is not None
    assert locker._parse_ts("invalid") is None

    assert locker._lock_age_seconds(None) is None
    naive = datetime(2024, 1, 1, 0, 0, 0)
    assert locker._lock_age_seconds(naive) is not None


def test_lock_staleness_and_cleanup(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_RUN_ID", "run_active")

    allowed_path = "src/main.py"
    locks_root = runtime_root / "locks"
    locks_root.mkdir(parents=True, exist_ok=True)
    lock_path = locker._lock_path(allowed_path, locks_root)

    _write_manifest(runtime_root, "run_done", "SUCCESS")
    lock_path.write_text(
        "\n".join(
            [
                "run_id=run_done",
                "ts=2024-01-01T00:00:00Z",
                f"path={allowed_path}",
            ]
        ),
        encoding="utf-8",
    )

    removed, remaining = locker.cleanup_stale_locks([allowed_path], ttl_sec=900)
    assert len(removed) == 1
    assert remaining == []
    assert not lock_path.exists()

    assert locker.acquire_lock([allowed_path]) is True

    _write_manifest(runtime_root, "run_active", "SUCCESS")
    monkeypatch.setenv("CORTEXPILOT_RUN_ID", "run_new")
    ok, removed_after, remaining_after = locker.acquire_lock_with_cleanup([allowed_path], auto_cleanup=True)
    assert ok is True
    assert removed_after
    assert remaining_after == []

    locker.release_lock([allowed_path])


def test_lock_pid_dead_cleanup_for_running_manifest(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))

    allowed_path = "src/orphan.py"
    locks_root = runtime_root / "locks"
    locks_root.mkdir(parents=True, exist_ok=True)
    lock_path = locker._lock_path(allowed_path, locks_root)

    _write_manifest(runtime_root, "run_orphan", "RUNNING")
    lock_path.write_text(
        "\n".join(
            [
                "run_id=run_orphan",
                "ts=2026-02-09T00:00:00Z",
                f"path={allowed_path}",
                "pid=999999",
            ]
        ),
        encoding="utf-8",
    )

    removed, remaining = locker.cleanup_stale_locks([allowed_path], ttl_sec=0)
    assert len(removed) == 1
    assert removed[0]["reason"] == "pid_dead"
    assert remaining == []


def test_lock_ttl_and_non_cleanup_paths(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_RUN_ID", "run_a")
    monkeypatch.delenv("CORTEXPILOT_LOCK_TTL_SEC", raising=False)
    monkeypatch.delenv("CORTEXPILOT_LOCK_TTL_SEC_DEFAULT", raising=False)

    ttl_disabled, source_disabled = locker.resolve_lock_ttl(auto_cleanup=False)
    assert ttl_disabled == 0
    assert source_disabled == "disabled"

    monkeypatch.setenv("CORTEXPILOT_LOCK_TTL_SEC", "invalid")
    ttl_invalid, source_invalid = locker.resolve_lock_ttl(auto_cleanup=True)
    assert ttl_invalid == 0
    assert source_invalid == "env_invalid"

    monkeypatch.setenv("CORTEXPILOT_LOCK_TTL_SEC", "120")
    ttl_env, source_env = locker.resolve_lock_ttl(auto_cleanup=True)
    assert ttl_env == 120
    assert source_env == "env"

    target = ["src/feature.py"]
    assert locker.acquire_lock(target) is True

    monkeypatch.setenv("CORTEXPILOT_RUN_ID", "run_b")
    ok, removed, remaining = locker.acquire_lock_with_cleanup(target, auto_cleanup=False)
    assert ok is False
    assert removed == []
    assert remaining == []

    locker.release_lock(target)
    locker.release_lock([])
