from pathlib import Path
from typing import cast

import json
from datetime import datetime, timezone

from openvibecoding_orch.locks.locker import _lock_path, acquire_lock, acquire_lock_with_cleanup, release_lock


def test_locker_acquire_collision(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(tmp_path))
    locks_root = tmp_path / "locks"
    locks_root.mkdir(parents=True, exist_ok=True)

    lock_path = _lock_path("file.txt", locks_root)
    lock_path.write_text("held", encoding="utf-8")

    assert acquire_lock(["file.txt"]) is False


def test_locker_cleanup_on_partial_failure(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(tmp_path))
    locks_root = tmp_path / "locks"
    locks_root.mkdir(parents=True, exist_ok=True)

    existing = _lock_path("b.txt", locks_root)
    existing.write_text("held", encoding="utf-8")

    assert acquire_lock(["a.txt", "b.txt"]) is False
    first_lock = _lock_path("a.txt", locks_root)
    assert not first_lock.exists()


def test_locker_release(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(tmp_path))
    monkeypatch.setenv("OPENVIBECODING_RUN_ID", "run_release")
    locks_root = tmp_path / "locks"
    locks_root.mkdir(parents=True, exist_ok=True)

    lock_path = _lock_path("file.txt", locks_root)
    assert acquire_lock(["file.txt"]) is True
    release_lock(["file.txt"])
    assert not lock_path.exists()


def test_locker_release_all_when_empty(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(tmp_path))
    locks_root = tmp_path / "locks"
    locks_root.mkdir(parents=True, exist_ok=True)

    lock_a = _lock_path("a.txt", locks_root)
    lock_b = _lock_path("b.txt", locks_root)
    lock_a.write_text("held", encoding="utf-8")
    lock_b.write_text("held", encoding="utf-8")

    release_lock([])
    assert lock_a.exists()
    assert lock_b.exists()


def test_locker_release_requires_owner_or_force_unlock(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(tmp_path))
    monkeypatch.setenv("OPENVIBECODING_RUN_ID", "run_owner_a")
    monkeypatch.setenv("OPENVIBECODING_LOCK_OWNER_TOKEN", "owner_a")
    target = ["src/owned.py"]

    assert acquire_lock(target) is True

    monkeypatch.setenv("OPENVIBECODING_RUN_ID", "run_owner_b")
    monkeypatch.setenv("OPENVIBECODING_LOCK_OWNER_TOKEN", "owner_b")
    release_lock(target)
    assert acquire_lock(target) is False

    monkeypatch.setenv("OPENVIBECODING_FORCE_UNLOCK", "1")
    release_lock(target)
    monkeypatch.delenv("OPENVIBECODING_FORCE_UNLOCK", raising=False)
    assert acquire_lock(target) is True
    release_lock(target)


def test_locker_sanitize_allowed_paths_non_string_entries(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(tmp_path))
    monkeypatch.setenv("OPENVIBECODING_RUN_ID", "run_sanitize")

    assert acquire_lock(cast(list[str], ["src/ok.py", None, " ", "src/ok.py"])) is True
    release_lock(cast(list[str], ["src/ok.py", 123, ""]))


def test_locker_rejects_traversal_and_absolute_allowed_paths(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(tmp_path))
    monkeypatch.setenv("OPENVIBECODING_RUN_ID", "run_path_safety")

    assert acquire_lock(["../escape.py"]) is False
    assert acquire_lock(["/tmp/escape.py"]) is False
    assert acquire_lock(["src/ok.py", "../escape.py"]) is True
    release_lock(["src/ok.py"])


def test_locker_partial_failure_cleanup_does_not_remove_replaced_foreign_lock(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(tmp_path))
    monkeypatch.setenv("OPENVIBECODING_RUN_ID", "run-owner-a")
    monkeypatch.setenv("OPENVIBECODING_LOCK_OWNER_TOKEN", "owner_a")
    locks_root = tmp_path / "locks"
    locks_root.mkdir(parents=True, exist_ok=True)

    existing = _lock_path("b.txt", locks_root)
    existing.write_text("held", encoding="utf-8")

    import openvibecoding_orch.locks.locker as locker_module

    original_write = locker_module._write_lock

    def _fake_write(lock_path: Path, run_id: str, path: str) -> None:
        if path == "b.txt":
            first_lock = _lock_path("a.txt", locks_root)
            first_lock.write_text(
                "run_id=run-owner-b\n"
                "ts=2026-02-25T00:00:00+00:00\n"
                "path=a.txt\n"
                "pid=999999\n"
                "owner=owner_b\n",
                encoding="utf-8",
            )
            raise FileExistsError
        original_write(lock_path, run_id, path)

    monkeypatch.setattr(locker_module, "_write_lock", _fake_write)

    assert acquire_lock(["a.txt", "b.txt"]) is False
    first_lock = _lock_path("a.txt", locks_root)
    assert first_lock.exists()
    assert "owner=owner_b" in first_lock.read_text(encoding="utf-8")


def test_locker_auto_cleanup_stale_run(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(tmp_path))
    locks_root = tmp_path / "locks"
    locks_root.mkdir(parents=True, exist_ok=True)
    runs_root = tmp_path / "runs"
    run_id = "run-stale"
    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text(
        json.dumps({"run_id": run_id, "status": "SUCCESS"}),
        encoding="utf-8",
    )

    lock_path = _lock_path("file.txt", locks_root)
    lock_path.write_text(
        f"run_id={run_id}\n"
        f"ts={datetime.now(timezone.utc).isoformat()}\n"
        "path=file.txt\n",
        encoding="utf-8",
    )

    ok, cleaned, remaining = acquire_lock_with_cleanup(["file.txt"], auto_cleanup=True)
    assert ok is True
    assert cleaned and cleaned[0]["run_id"] == run_id
    assert remaining == []
