from __future__ import annotations

import json
import os
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path
from typing import Any

try:
    import fcntl  # type: ignore
except Exception:  # pragma: no cover - non-posix fallback
    fcntl = None

_PROCESS_LOCK_REGISTRY_GUARD = threading.Lock()
_PROCESS_LOCK_REGISTRY: dict[str, threading.RLock] = {}


def _process_lock_key(path: Path) -> str:
    try:
        return str(path.resolve(strict=False))
    except Exception:
        return str(path)


def _process_lock_for(path: Path) -> threading.RLock:
    key = _process_lock_key(path)
    with _PROCESS_LOCK_REGISTRY_GUARD:
        lock = _PROCESS_LOCK_REGISTRY.get(key)
        if lock is None:
            lock = threading.RLock()
            _PROCESS_LOCK_REGISTRY[key] = lock
        return lock


def _now_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_sessions_root() -> Path:
    env_root = os.getenv("CORTEXPILOT_CODEX_SESSIONS_ROOT", "")
    if env_root:
        return Path(env_root)
    return Path.home() / ".codex" / "sessions"


def _default_alias_path() -> Path:
    env_path = os.getenv("CORTEXPILOT_SESSION_ALIAS_PATH", "")
    if env_path:
        return Path(env_path)
    return _default_sessions_root() / "alias_map.json"


@dataclass(frozen=True)
class SessionAliasRecord:
    alias: str
    session_id: str
    thread_id: str
    note: str
    updated_at: str


class SessionAliasStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _default_alias_path()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_path = self._path.with_suffix(f"{self._path.suffix}.lock")
        self._process_lock = _process_lock_for(self._lock_path)

    @contextmanager
    def _file_lock(self):
        with self._process_lock:
            if fcntl is None:
                yield None
                return
            with self._lock_path.open("a+", encoding="utf-8") as lock_file:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                try:
                    yield lock_file
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {"version": 1, "aliases": {}}
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            backup = self._path.with_suffix(f"{self._path.suffix}.corrupt.{int(datetime.now().timestamp())}")
            self._path.replace(backup)
            print(
                f"[session_map] alias map corrupted, moved to backup: {backup}",
                file=sys.stderr,
            )
            return {"version": 1, "aliases": {}}
        if not isinstance(payload, dict):
            return {"version": 1, "aliases": {}}
        if "aliases" not in payload or not isinstance(payload.get("aliases"), dict):
            payload["aliases"] = {}
        if "version" not in payload:
            payload["version"] = 1
        return payload

    def _write(self, payload: dict[str, Any]) -> None:
        payload.setdefault("version", 1)
        payload.setdefault("aliases", {})
        tmp_path = self._path.with_suffix(
            f"{self._path.suffix}.tmp.{os.getpid()}.{time.time_ns()}"
        )
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(self._path)

    def set_alias(
        self,
        alias: str,
        session_id: str,
        thread_id: str | None = None,
        note: str | None = None,
    ) -> SessionAliasRecord:
        alias = alias.strip()
        session_id = session_id.strip()
        if not alias:
            raise ValueError("alias required")
        if not session_id:
            raise ValueError("session_id required")

        with self._file_lock():
            payload = self._load()
            record = {
                "session_id": session_id,
                "thread_id": (thread_id or "").strip(),
                "note": (note or "").strip(),
                "updated_at": _now_ts(),
            }
            payload["aliases"][alias] = record
            self._write(payload)
        return SessionAliasRecord(alias=alias, **record)

    def resolve(self, alias: str) -> SessionAliasRecord | None:
        alias = alias.strip()
        if not alias:
            return None
        payload = self._load()
        record = payload.get("aliases", {}).get(alias)
        if not isinstance(record, dict):
            return None
        return SessionAliasRecord(
            alias=alias,
            session_id=str(record.get("session_id", "")),
            thread_id=str(record.get("thread_id", "")),
            note=str(record.get("note", "")),
            updated_at=str(record.get("updated_at", "")),
        )

    def delete(self, alias: str) -> bool:
        alias = alias.strip()
        if not alias:
            return False
        with self._file_lock():
            payload = self._load()
            aliases = payload.get("aliases", {})
            if alias not in aliases:
                return False
            aliases.pop(alias)
            payload["aliases"] = aliases
            self._write(payload)
            return True

    def list_aliases(self) -> list[SessionAliasRecord]:
        payload = self._load()
        aliases = payload.get("aliases", {})
        if not isinstance(aliases, dict):
            return []
        records = []
        for alias, record in aliases.items():
            if not isinstance(record, dict):
                continue
            records.append(
                SessionAliasRecord(
                    alias=str(alias),
                    session_id=str(record.get("session_id", "")),
                    thread_id=str(record.get("thread_id", "")),
                    note=str(record.get("note", "")),
                    updated_at=str(record.get("updated_at", "")),
                )
            )
        return sorted(records, key=lambda item: item.alias)


_default_store = SessionAliasStore()


def set_alias(
    alias: str,
    session_id: str,
    thread_id: str | None = None,
    note: str | None = None,
) -> SessionAliasRecord:
    return _default_store.set_alias(alias, session_id, thread_id=thread_id, note=note)


def resolve(alias: str) -> SessionAliasRecord | None:
    return _default_store.resolve(alias)


def delete(alias: str) -> bool:
    return _default_store.delete(alias)


def list_aliases() -> list[SessionAliasRecord]:
    return _default_store.list_aliases()
