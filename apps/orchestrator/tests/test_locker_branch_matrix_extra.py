import json
import os
from pathlib import Path

from openvibecoding_orch.locks import locker


def _write_manifest(runtime_root: Path, run_id: str, status: str) -> None:
    run_dir = runtime_root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text(json.dumps({"run_id": run_id, "status": status}), encoding="utf-8")


def test_pid_alive_branch_matrix(monkeypatch) -> None:
    assert locker._pid_alive("") is None
    assert locker._pid_alive("abc") is None
    assert locker._pid_alive("0") is None

    def _kill_permission(_pid: int, _sig: int) -> None:
        raise PermissionError

    monkeypatch.setattr(os, "kill", _kill_permission)
    assert locker._pid_alive("1") is True

    def _kill_ok(_pid: int, _sig: int) -> None:
        return None

    monkeypatch.setattr(os, "kill", _kill_ok)
    assert locker._pid_alive("1") is True


def test_lock_is_stale_branches_and_remaining_record(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))

    # RUNNING + pid alive => rely on TTL branch
    _write_manifest(runtime_root, "run-running", "RUNNING")
    meta_running = {
        "run_id": "run-running",
        "ts": "1970-01-01T00:00:00Z",
        "path": "src/a.py",
        "pid": str(os.getpid()),
    }
    stale_ttl, reason_ttl = locker._lock_is_stale(runtime_root, meta_running, ttl_sec=1)
    assert stale_ttl is True
    assert reason_ttl.startswith("ttl_expired=")

    # RUNNING + pid dead => stale via pid_dead
    meta_pid_dead = {
        "run_id": "run-running",
        "ts": "2026-02-10T00:00:00Z",
        "path": "src/a.py",
        "pid": "999999",
    }
    stale_dead, reason_dead = locker._lock_is_stale(runtime_root, meta_pid_dead, ttl_sec=0)
    assert stale_dead is True
    assert reason_dead == "pid_dead"

    # Unknown run status + pid unknown + recent ts => not stale
    meta_recent = {
        "run_id": "",
        "ts": "2999-01-01T00:00:00Z",
        "path": "src/keep.py",
        "pid": "",
    }
    stale_recent, reason_recent = locker._lock_is_stale(runtime_root, meta_recent, ttl_sec=900)
    assert stale_recent is False
    assert reason_recent == ""

    allowed_path = "src/keep.py"
    locks_root = runtime_root / "locks"
    locks_root.mkdir(parents=True, exist_ok=True)
    lock_path = locker._lock_path(allowed_path, locks_root)
    lock_path.write_text(
        "\n".join(
            [
                "run_id=",
                "ts=2999-01-01T00:00:00Z",
                f"path={allowed_path}",
                "pid=",
            ]
        ),
        encoding="utf-8",
    )

    removed, remaining = locker.cleanup_stale_locks([allowed_path], ttl_sec=900)
    assert removed == []
    assert len(remaining) == 1
    assert remaining[0]["path"] == allowed_path
    assert lock_path.exists()


def test_acquire_reclaims_hard_stale_without_auto_cleanup(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUN_ID", "run-new")

    allowed_path = "apps/orchestrator/src"
    locks_root = runtime_root / "locks"
    locks_root.mkdir(parents=True, exist_ok=True)
    lock_path = locker._lock_path(allowed_path, locks_root)

    _write_manifest(runtime_root, "run-stale", "RUNNING")
    lock_path.write_text(
        "\n".join(
            [
                "run_id=run-stale",
                "ts=2026-02-10T00:00:00Z",
                f"path={allowed_path}",
                "pid=999999",
            ]
        ),
        encoding="utf-8",
    )

    ok, removed, remaining = locker.acquire_lock_with_cleanup([allowed_path], auto_cleanup=False)
    assert ok is True
    assert removed == []
    assert remaining == []

    meta = locker._parse_lock_file(lock_path)
    assert meta["run_id"] == "run-new"
    locker.release_lock([allowed_path])


def test_lock_running_without_active_marker_is_stale(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUNNING_LOCK_STALE_SEC", "1")

    _write_manifest(runtime_root, "run-running", "RUNNING")
    meta = {
        "run_id": "run-running",
        "ts": "1970-01-01T00:00:00Z",
        "path": "apps/dashboard",
        "pid": str(os.getpid()),
    }

    stale, reason = locker._lock_is_stale(runtime_root, meta, ttl_sec=0)
    assert stale is True
    assert reason == "running_no_active_marker"


def test_lock_running_with_active_marker_not_stale(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUNNING_LOCK_STALE_SEC", "1")

    _write_manifest(runtime_root, "run-running", "RUNNING")
    active_dir = runtime_root / "active"
    active_dir.mkdir(parents=True, exist_ok=True)
    (active_dir / "run_id.txt").write_text("run-running", encoding="utf-8")

    meta = {
        "run_id": "run-running",
        "ts": "1970-01-01T00:00:00Z",
        "path": "apps/dashboard",
        "pid": str(os.getpid()),
    }

    stale, reason = locker._lock_is_stale(runtime_root, meta, ttl_sec=0)
    assert stale is False
    assert reason == ""


def test_lock_running_with_other_active_marker_is_stale(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUNNING_LOCK_STALE_SEC", "1")

    _write_manifest(runtime_root, "run-running", "RUNNING")
    active_dir = runtime_root / "active"
    active_dir.mkdir(parents=True, exist_ok=True)
    (active_dir / "run_id.txt").write_text("run-other", encoding="utf-8")

    meta = {
        "run_id": "run-running",
        "ts": "1970-01-01T00:00:00Z",
        "path": "apps/dashboard",
        "pid": str(os.getpid()),
    }

    stale, reason = locker._lock_is_stale(runtime_root, meta, ttl_sec=0)
    assert stale is True
    assert reason == "running_not_active_marker"
