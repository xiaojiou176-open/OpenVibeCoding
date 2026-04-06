from __future__ import annotations

import hashlib
import hmac
import os
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None


_INPROCESS_LOCKS: dict[str, threading.Lock] = {}
_INPROCESS_LOCKS_GUARD = threading.Lock()


def now_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_component(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} missing")
    candidate = Path(value)
    if candidate.is_absolute():
        raise ValueError(f"{label} must be relative")
    if len(candidate.parts) != 1:
        raise ValueError(f"{label} must be a single path segment")
    if candidate.parts[0] in {".", ".."}:
        raise ValueError(f"{label} invalid")
    return value


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def hmac_sha256(key: str, payload: bytes) -> str:
    return hmac.new(key.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def load_hmac_key() -> str | None:
    raw = os.getenv("CORTEXPILOT_CONTRACT_HMAC_KEY", "").strip()
    return raw or None


def write_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    with tmp_path.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, path)
    dir_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


@contextmanager
def exclusive_file_lock(lock_path: Path) -> Iterator[None]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_key = str(lock_path.resolve())
    with _INPROCESS_LOCKS_GUARD:
        thread_lock = _INPROCESS_LOCKS.setdefault(lock_key, threading.Lock())
    thread_lock.acquire()
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        if fcntl is not None:
            fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        if fcntl is not None:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
        thread_lock.release()


def safe_artifact_path(artifacts_dir: Path, filename: str) -> Path:
    if not isinstance(filename, str) or not filename.strip():
        raise ValueError("artifact filename missing")
    rel_path = Path(filename)
    if rel_path.is_absolute():
        raise ValueError("artifact path must be relative")
    base_dir = artifacts_dir.resolve()
    candidate = (base_dir / rel_path).resolve()
    try:
        candidate.relative_to(base_dir)
    except ValueError as exc:
        raise ValueError("artifact path escapes artifacts dir") from exc
    return candidate
