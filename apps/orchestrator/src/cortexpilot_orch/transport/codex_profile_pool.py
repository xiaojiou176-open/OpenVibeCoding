from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_logger = logging.getLogger(__name__)
_POOL_LOCK = threading.RLock()
_DEFAULT_LOCK_TTL_SEC = 120.0


def _now_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _runtime_root() -> Path:
    return Path(os.getenv("CORTEXPILOT_RUNTIME_ROOT", ".runtime-cache/cortexpilot")).resolve()


def _pool_path() -> Path:
    return _runtime_root() / "pools" / "codex_profile_pool.json"


def _pool_lock_path() -> Path:
    return _runtime_root() / "pools" / "codex_profile_pool.lock"


def _lock_ttl_sec() -> float:
    raw = os.getenv("CORTEXPILOT_CODEX_PROFILE_POOL_LOCK_TTL_SEC", "").strip()
    if not raw:
        return _DEFAULT_LOCK_TTL_SEC
    try:
        value = float(raw)
    except ValueError:
        return _DEFAULT_LOCK_TTL_SEC
    return value if value > 0 else _DEFAULT_LOCK_TTL_SEC


def _pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _read_lock_payload(lock_path: Path) -> dict[str, Any]:
    if not lock_path.exists():
        return {}
    try:
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        _logger.debug("codex_profile_pool: failed to read lock payload: %s", exc)
        return {}
    return payload if isinstance(payload, dict) else {}


def _is_stale_lock(lock_path: Path, ttl_sec: float) -> bool:
    payload = _read_lock_payload(lock_path)
    if lock_path.exists() and not payload:
        try:
            return (time.time() - lock_path.stat().st_mtime) > ttl_sec
        except OSError:
            return False

    pid_raw = payload.get("pid")
    ts_raw = payload.get("ts")
    pid: int | None = None
    ts: float | None = None
    try:
        if pid_raw is not None:
            pid = int(pid_raw)
    except (TypeError, ValueError):
        pid = None
    try:
        if ts_raw is not None:
            ts = float(ts_raw)
    except (TypeError, ValueError):
        ts = None

    if pid is not None and not _pid_exists(pid):
        return True
    if ts is not None and (time.time() - ts) > ttl_sec:
        return True
    return False


def _acquire_file_lock(timeout_sec: float = 5.0) -> int | None:
    lock_path = _pool_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout_sec
    attempted_stale_recovery = False
    ttl_sec = _lock_ttl_sec()
    while time.monotonic() < deadline:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            payload = {"pid": os.getpid(), "ts": time.time()}
            os.write(fd, json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            return fd
        except FileExistsError:
            if not attempted_stale_recovery and _is_stale_lock(lock_path, ttl_sec):
                attempted_stale_recovery = True
                try:
                    lock_path.unlink(missing_ok=True)
                    continue
                except Exception as exc:  # noqa: BLE001
                    _logger.debug("codex_profile_pool: stale lock cleanup failed: %s", exc)
            time.sleep(0.05)
    return None


def _release_file_lock(fd: int | None) -> None:
    if fd is None:
        return
    try:
        os.close(fd)
    finally:
        try:
            lock_path = _pool_lock_path()
            payload = _read_lock_payload(lock_path)
            owner_pid = payload.get("pid")
            owner_matches = False
            try:
                owner_matches = int(owner_pid) == os.getpid()
            except (TypeError, ValueError):
                owner_matches = False
            if owner_matches or _is_stale_lock(lock_path, _lock_ttl_sec()):
                lock_path.unlink(missing_ok=True)
        except Exception as exc:  # noqa: BLE001
            _logger.debug("codex_profile_pool: lock release cleanup failed: %s", exc)


def _parse_pool_env() -> list[str]:
    raw = os.getenv("CORTEXPILOT_CODEX_PROFILE_POOL", "")
    if not raw:
        return []
    profiles = [item.strip() for item in raw.split(",") if item.strip()]
    seen: set[str] = set()
    ordered: list[str] = []
    for item in profiles:
        lowered = item.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        ordered.append(item)
    return ordered


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        _logger.debug("codex_profile_pool: failed to load state: %s", exc)
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_state(path: Path, state: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(path)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"codex profile pool write failed: {exc}") from exc


def pick_profile() -> str | None:
    profiles = _parse_pool_env()
    if not profiles:
        return None
    lock_fd: int | None = None
    try:
        lock_fd = _acquire_file_lock()
        if lock_fd is None:
            return None
        with _POOL_LOCK:
            path = _pool_path()
            state = _load_state(path)
            index = state.get("index")
            try:
                index = int(index) if index is not None else -1
            except (TypeError, ValueError):
                index = -1
            next_index = (index + 1) % len(profiles)
            profile = profiles[next_index]
            state = {
                "index": next_index,
                "profiles": profiles,
                "updated_at": _now_ts(),
            }
            _write_state(path, state)
            return profile
    finally:
        _release_file_lock(lock_fd)
