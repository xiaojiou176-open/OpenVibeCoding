from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

from openvibecoding_orch.config import load_config

_DEFAULT_LOCK_TTL_SEC = 900
_DEFAULT_RUNNING_STALE_SEC = 1800


def _now_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_lock_path(path: str) -> str:
    normalized = Path(path).as_posix().strip().rstrip("/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if normalized == ".":
        return ""
    return normalized


def _lock_path(path: str, locks_root: Path) -> Path:
    normalized = _normalize_lock_path(path)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return locks_root / f"{digest}.lock"


def _parse_lock_file(lock_path: Path) -> dict[str, str]:
    meta = {"run_id": "", "ts": "", "path": "", "pid": "", "owner": ""}
    try:
        for line in lock_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("run_id="):
                meta["run_id"] = line.split("=", 1)[1].strip()
            elif line.startswith("ts="):
                meta["ts"] = line.split("=", 1)[1].strip()
            elif line.startswith("path="):
                meta["path"] = line.split("=", 1)[1].strip()
            elif line.startswith("pid="):
                meta["pid"] = line.split("=", 1)[1].strip()
            elif line.startswith("owner="):
                meta["owner"] = line.split("=", 1)[1].strip()
    except FileNotFoundError:
        return meta
    return meta


def _parse_ts(value: str) -> datetime | None:
    if not value:
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _load_run_status(runtime_root: Path, run_id: str) -> str | None:
    if not run_id:
        return None
    manifest = runtime_root / "runs" / run_id / "manifest.json"
    if not manifest.exists():
        return None
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    status = payload.get("status")
    if isinstance(status, str) and status.strip():
        return status.strip().upper()
    return None


def _load_active_run_id(runtime_root: Path) -> str:
    run_id_path = runtime_root / "active" / "run_id.txt"
    if not run_id_path.exists():
        return ""
    try:
        return run_id_path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _resolve_running_stale_sec() -> int:
    raw = os.getenv("OPENVIBECODING_RUNNING_LOCK_STALE_SEC", "").strip()
    if raw:
        try:
            return max(int(raw), 0)
        except ValueError:
            return _DEFAULT_RUNNING_STALE_SEC
    return _DEFAULT_RUNNING_STALE_SEC


def _truthy(raw: str) -> bool:
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _force_unlock_enabled() -> bool:
    return _truthy(os.getenv("OPENVIBECODING_FORCE_UNLOCK", ""))


def _owner_token() -> str:
    explicit = os.getenv("OPENVIBECODING_LOCK_OWNER_TOKEN", "").strip()
    if explicit:
        return explicit
    run_id = os.getenv("OPENVIBECODING_RUN_ID", "").strip()
    if run_id:
        return f"run:{run_id}:pid:{os.getpid()}"
    return f"pid:{os.getpid()}"


def _sanitize_allowed_paths(allowed_paths: object) -> list[str]:
    if isinstance(allowed_paths, str):
        candidates: list[object] = [allowed_paths]
    elif isinstance(allowed_paths, Iterable):
        candidates = list(allowed_paths)
    else:
        candidates = []
    normalized_paths: list[str] = []
    seen: set[str] = set()
    for raw in candidates:
        if not isinstance(raw, str):
            continue
        path = raw.strip()
        normalized_path = _normalize_lock_path(path)
        if (
            not normalized_path
            or normalized_path in seen
            or normalized_path.startswith("/")
            or normalized_path.startswith("../")
            or "/../" in normalized_path
            or "\n" in normalized_path
            or "\r" in normalized_path
            or "\x00" in normalized_path
        ):
            continue
        normalized_paths.append(normalized_path)
        seen.add(normalized_path)
    return normalized_paths


def _meta_signature(meta: dict[str, str]) -> tuple[str, str, str, str, str]:
    return (
        meta.get("run_id", ""),
        meta.get("ts", ""),
        meta.get("path", ""),
        meta.get("pid", ""),
        meta.get("owner", ""),
    )


def _unlink_if_meta_unchanged(lock_path: Path, expected_meta: dict[str, str]) -> bool:
    current = _parse_lock_file(lock_path)
    if _meta_signature(current) != _meta_signature(expected_meta):
        return False
    try:
        lock_path.unlink()
    except FileNotFoundError:
        return False
    return True


def _safe_unlink_owned_lock(lock_path: Path, run_id: str, owner_token: str, pid: str) -> bool:
    meta = _parse_lock_file(lock_path)
    owner = meta.get("owner", "")
    owner_match = bool(owner and owner == owner_token)
    legacy_owner_match = bool(run_id) and meta.get("run_id", "") == run_id and (not meta.get("pid", "") or meta.get("pid", "") == pid)
    if not owner_match and not legacy_owner_match:
        return False
    try:
        lock_path.unlink()
    except FileNotFoundError:
        return False
    return True


def _lock_age_seconds(ts: datetime | None) -> float | None:
    if ts is None:
        return None
    now = datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return max((now - ts).total_seconds(), 0.0)


def _pid_alive(pid_raw: str) -> bool | None:
    if not pid_raw:
        return None
    try:
        pid = int(pid_raw)
    except ValueError:
        return None
    if pid <= 0:
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _lock_is_stale(
    runtime_root: Path,
    meta: dict[str, str],
    ttl_sec: int,
) -> tuple[bool, str]:
    run_id = meta.get("run_id", "")
    run_status = _load_run_status(runtime_root, run_id)
    pid_alive = _pid_alive(meta.get("pid", ""))

    ts = _parse_ts(meta.get("ts", ""))
    age = _lock_age_seconds(ts)

    if run_status == "RUNNING":
        if pid_alive is False:
            return True, "pid_dead"
        if ttl_sec == 0 and pid_alive is True and run_id and age is not None:
            running_stale_sec = _resolve_running_stale_sec()
            if running_stale_sec > 0 and age >= running_stale_sec:
                active_run_id = _load_active_run_id(runtime_root)
                if not active_run_id:
                    return True, "running_no_active_marker"
                if active_run_id != run_id:
                    return True, "running_not_active_marker"
    elif run_status:
        return True, f"run_status={run_status}"
    elif pid_alive is False:
        return True, "pid_dead_no_manifest"

    if ttl_sec > 0 and age is not None and age >= ttl_sec:
        return True, f"ttl_expired={int(age)}"
    return False, ""


def cleanup_stale_locks(allowed_paths: Iterable[str], ttl_sec: int) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    cfg = load_config()
    locks_root = cfg.runtime_root / "locks"
    removed: list[dict[str, str]] = []
    remaining: list[dict[str, str]] = []
    for path in _sanitize_allowed_paths(allowed_paths):
        lock_path = _lock_path(path, locks_root)
        if not lock_path.exists():
            continue
        meta = _parse_lock_file(lock_path)
        stale, reason = _lock_is_stale(cfg.runtime_root, meta, ttl_sec)
        record = {
            "lock_path": str(lock_path),
            "path": meta.get("path", path),
            "run_id": meta.get("run_id", ""),
            "ts": meta.get("ts", ""),
            "reason": reason,
        }
        if stale:
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass
            removed.append(record)
        else:
            remaining.append(record)
    return removed, remaining


def _resolve_lock_ttl(auto_cleanup: bool) -> tuple[int, str]:
    ttl_raw = os.getenv("OPENVIBECODING_LOCK_TTL_SEC", "").strip()
    if ttl_raw != "":
        try:
            return max(int(ttl_raw), 0), "env"
        except ValueError:
            return 0, "env_invalid"
    if not auto_cleanup:
        return 0, "disabled"
    default_raw = os.getenv("OPENVIBECODING_LOCK_TTL_SEC_DEFAULT", "").strip()
    if default_raw != "":
        try:
            return max(int(default_raw), 0), "default_env"
        except ValueError:
            return 0, "default_env_invalid"
    return _DEFAULT_LOCK_TTL_SEC, "built_in_default"


def resolve_lock_ttl(auto_cleanup: bool) -> tuple[int, str]:
    return _resolve_lock_ttl(auto_cleanup)


def acquire_lock_with_cleanup(allowed_paths: Iterable[str], auto_cleanup: bool) -> tuple[bool, list[dict[str, str]], list[dict[str, str]]]:
    paths = _sanitize_allowed_paths(allowed_paths)
    if acquire_lock(paths, reclaim_stale=not auto_cleanup):
        return True, [], []
    if not auto_cleanup:
        return False, [], []
    ttl_sec, _ = _resolve_lock_ttl(auto_cleanup)
    removed, remaining = cleanup_stale_locks(paths, ttl_sec)
    if acquire_lock(paths, reclaim_stale=False):
        return True, removed, remaining
    return False, removed, remaining


def _write_lock(lock_path: Path, run_id: str, path: str) -> None:
    fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(f"run_id={run_id}\n")
        handle.write(f"ts={_now_ts()}\n")
        handle.write(f"path={path}\n")
        handle.write(f"pid={os.getpid()}\n")
        handle.write(f"owner={_owner_token()}\n")


def acquire_lock(allowed_paths: Iterable[str], reclaim_stale: bool = True) -> bool:
    cfg = load_config()
    locks_root = cfg.runtime_root / "locks"
    locks_root.mkdir(parents=True, exist_ok=True)
    run_id = os.getenv("OPENVIBECODING_RUN_ID", "unknown")
    paths = _sanitize_allowed_paths(allowed_paths)
    if not paths:
        return False

    acquired: list[Path] = []
    for path in paths:
        lock_path = _lock_path(path, locks_root)
        try:
            _write_lock(lock_path, run_id, path)
            acquired.append(lock_path)
        except FileExistsError:
            if reclaim_stale:
                meta = _parse_lock_file(lock_path)
                stale, _ = _lock_is_stale(cfg.runtime_root, meta, ttl_sec=0)
                if stale:
                    if _unlink_if_meta_unchanged(lock_path, meta):
                        try:
                            _write_lock(lock_path, run_id, path)
                            acquired.append(lock_path)
                            continue
                        except FileExistsError:
                            pass
            for held in acquired:
                _safe_unlink_owned_lock(
                    held,
                    run_id=run_id,
                    owner_token=_owner_token(),
                    pid=str(os.getpid()),
                )
            return False
    return True


def release_lock(allowed_paths: Iterable[str]) -> None:
    cfg = load_config()
    locks_root = cfg.runtime_root / "locks"
    paths = _sanitize_allowed_paths(allowed_paths)
    if not paths:
        return
    run_id = os.getenv("OPENVIBECODING_RUN_ID", "").strip()
    current_pid = str(os.getpid())
    current_owner = _owner_token()
    force_unlock = _force_unlock_enabled()
    for path in paths:
        lock_path = _lock_path(path, locks_root)
        if not lock_path.exists():
            continue
        meta = _parse_lock_file(lock_path)
        owner = meta.get("owner", "")
        owner_match = bool(owner and owner == current_owner)
        legacy_owner_match = (
            bool(run_id)
            and meta.get("run_id", "") == run_id
            and (not meta.get("pid", "") or meta.get("pid", "") == current_pid)
        )
        if force_unlock or owner_match or legacy_owner_match:
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass
