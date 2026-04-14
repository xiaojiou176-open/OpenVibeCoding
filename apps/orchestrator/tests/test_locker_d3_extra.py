import json
import os
from pathlib import Path

from openvibecoding_orch.locks import locker


def test_locker_helper_edge_branches(tmp_path: Path, monkeypatch) -> None:
    assert locker._normalize_lock_path("././src/main.py/") == "src/main.py"

    monkeypatch.setenv("OPENVIBECODING_RUN_ID", "run-edge")
    monkeypatch.delenv("OPENVIBECODING_LOCK_OWNER_TOKEN", raising=False)
    assert locker._owner_token().startswith("run:run-edge:pid:")

    monkeypatch.setenv("OPENVIBECODING_RUNNING_LOCK_STALE_SEC", "invalid")
    assert locker._resolve_running_stale_sec() == locker._DEFAULT_RUNNING_STALE_SEC

    assert locker._sanitize_allowed_paths("src/a.py") == ["src/a.py"]
    assert locker._sanitize_allowed_paths(12345) == []

    runtime_root = tmp_path / "runtime"
    run_id = "run-json"
    run_dir = runtime_root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = run_dir / "manifest.json"

    manifest.write_text("{", encoding="utf-8")
    assert locker._load_run_status(runtime_root, run_id) is None

    manifest.write_text(json.dumps({"status": 123}), encoding="utf-8")
    assert locker._load_run_status(runtime_root, run_id) is None

    active_dir = runtime_root / "active"
    active_dir.mkdir(parents=True, exist_ok=True)
    run_id_path = active_dir / "run_id.txt"
    run_id_path.write_text("run-edge", encoding="utf-8")

    original_read_text = Path.read_text

    def _fake_read_text(self: Path, *args, **kwargs):
        if self == run_id_path:
            raise OSError("read failed")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _fake_read_text)
    assert locker._load_active_run_id(runtime_root) == ""


def test_locker_unlink_and_stale_pid_branches(tmp_path: Path, monkeypatch) -> None:
    lock_path = tmp_path / "target.lock"
    lock_path.write_text(
        "run_id=run-1\nts=2026-01-01T00:00:00Z\npath=src/a.py\npid=123\nowner=owner-a\n",
        encoding="utf-8",
    )
    expected = locker._parse_lock_file(lock_path)

    mismatch = dict(expected)
    mismatch["owner"] = "owner-b"
    assert locker._unlink_if_meta_unchanged(lock_path, mismatch) is False

    original_unlink = Path.unlink

    def _raise_missing(self: Path, *args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(Path, "unlink", _raise_missing)
    assert locker._unlink_if_meta_unchanged(lock_path, expected) is False

    assert locker._safe_unlink_owned_lock(lock_path, run_id="run-1", owner_token="owner-a", pid="123") is False

    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    stale, reason = locker._lock_is_stale(
        runtime_root,
        {"run_id": "", "pid": "999999", "ts": "", "path": "src/a.py"},
        ttl_sec=0,
    )
    assert stale is True
    assert reason == "pid_dead_no_manifest"

    monkeypatch.setattr(Path, "unlink", original_unlink)


def test_locker_cleanup_ttl_release_and_acquire_retries(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUN_ID", "run-main")

    removed, remaining = locker.cleanup_stale_locks(["src/missing.py"], ttl_sec=0)
    assert removed == []
    assert remaining == []

    locks_root = runtime_root / "locks"
    locks_root.mkdir(parents=True, exist_ok=True)
    stale_path = "src/stale.py"
    stale_lock = locker._lock_path(stale_path, locks_root)
    stale_lock.write_text(
        "run_id=run-stale\nts=2020-01-01T00:00:00Z\npath=src/stale.py\npid=\nowner=\n",
        encoding="utf-8",
    )
    run_dir = runtime_root / "runs" / "run-stale"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text(json.dumps({"status": "SUCCESS"}), encoding="utf-8")

    original_unlink = Path.unlink

    def _unlink_missing_for_stale(self: Path, *args, **kwargs):
        if self == stale_lock:
            raise FileNotFoundError
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", _unlink_missing_for_stale)
    removed_after, remaining_after = locker.cleanup_stale_locks([stale_path], ttl_sec=0)
    assert len(removed_after) == 1
    assert remaining_after == []

    monkeypatch.delenv("OPENVIBECODING_LOCK_TTL_SEC", raising=False)
    monkeypatch.setenv("OPENVIBECODING_LOCK_TTL_SEC_DEFAULT", "invalid")
    assert locker.resolve_lock_ttl(auto_cleanup=True) == (0, "default_env_invalid")

    # acquire_lock_with_cleanup final retry fails -> returns False with cleanup records.
    monkeypatch.setattr(locker, "acquire_lock", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(locker, "cleanup_stale_locks", lambda *_args, **_kwargs: ([{"reason": "x"}], []))
    ok, removed_retry, remaining_retry = locker.acquire_lock_with_cleanup(["src/a.py"], auto_cleanup=True)
    assert ok is False
    assert removed_retry == [{"reason": "x"}]
    assert remaining_retry == []

    # Reclaim branch where stale lock cannot be unlinked safely.
    monkeypatch.setattr(locker, "_write_lock", lambda *_args, **_kwargs: (_ for _ in ()).throw(FileExistsError()))
    monkeypatch.setattr(locker, "_lock_is_stale", lambda *_args, **_kwargs: (True, "stale"))
    monkeypatch.setattr(locker, "_unlink_if_meta_unchanged", lambda *_args, **_kwargs: False)
    assert locker.acquire_lock(["src/reclaim-false.py"], reclaim_stale=True) is False

    # Reclaim branch where second write still collides.
    monkeypatch.setattr(locker, "_unlink_if_meta_unchanged", lambda *_args, **_kwargs: True)
    assert locker.acquire_lock(["src/reclaim-race.py"], reclaim_stale=True) is False

    monkeypatch.setattr(Path, "unlink", original_unlink)


def test_locker_release_missing_and_unlink_file_not_found(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUN_ID", "run-release")
    monkeypatch.setenv("OPENVIBECODING_LOCK_OWNER_TOKEN", "owner-release")

    # Missing lock path branch.
    locker.release_lock(["src/not-found.py"])

    target = ["src/owned.py"]
    assert locker.acquire_lock(target) is True
    lock_path = locker._lock_path("src/owned.py", runtime_root / "locks")

    original_unlink = Path.unlink

    def _unlink_missing(self: Path, *args, **kwargs):
        if self == lock_path:
            raise FileNotFoundError
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", _unlink_missing)
    locker.release_lock(target)
