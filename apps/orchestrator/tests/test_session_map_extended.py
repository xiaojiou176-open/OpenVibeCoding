import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from openvibecoding_orch.store import session_map as session_map_module
from openvibecoding_orch.store.session_map import SessionAliasStore


def test_session_map_corrupt_json_creates_backup(tmp_path: Path) -> None:
    path = tmp_path / "alias.json"
    path.write_text("{", encoding="utf-8")

    store = SessionAliasStore(path=path)
    record = store.resolve("missing")
    assert record is None

    backups = list(tmp_path.glob("alias.json.corrupt.*"))
    assert backups


def test_session_map_set_alias_validation(tmp_path: Path) -> None:
    store = SessionAliasStore(path=tmp_path / "alias.json")
    with pytest.raises(ValueError, match="alias required"):
        store.set_alias("", "session")
    with pytest.raises(ValueError, match="session_id required"):
        store.set_alias("alias", "")


def test_session_map_list_handles_bad_records(tmp_path: Path) -> None:
    path = tmp_path / "alias.json"
    payload = {"version": 1, "aliases": {"bad": "oops"}}
    path.write_text(json.dumps(payload), encoding="utf-8")
    store = SessionAliasStore(path=path)
    assert store.list_aliases() == []


def test_session_map_empty_alias_and_delete(tmp_path: Path) -> None:
    store = SessionAliasStore(path=tmp_path / "alias.json")
    assert store.resolve("") is None
    assert store.delete("") is False


def test_session_map_aliases_not_dict(tmp_path: Path) -> None:
    path = tmp_path / "alias.json"
    payload = {"version": 1, "aliases": []}
    path.write_text(json.dumps(payload), encoding="utf-8")
    store = SessionAliasStore(path=path)
    assert store.list_aliases() == []


def test_session_map_load_non_dict_payload(tmp_path: Path) -> None:
    path = tmp_path / "alias.json"
    path.write_text("[]", encoding="utf-8")
    store = SessionAliasStore(path=path)
    assert store.list_aliases() == []


def test_session_map_default_paths(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_CODEX_SESSIONS_ROOT", str(tmp_path / "sessions"))
    from openvibecoding_orch.store import session_map as mod
    root = mod._default_sessions_root()
    assert root == tmp_path / "sessions"

    monkeypatch.setenv("OPENVIBECODING_SESSION_ALIAS_PATH", str(tmp_path / "alias.json"))
    alias_path = mod._default_alias_path()
    assert alias_path == tmp_path / "alias.json"


def test_session_map_list_aliases_non_dict(monkeypatch, tmp_path: Path) -> None:
    store = SessionAliasStore(path=tmp_path / "alias.json")
    monkeypatch.setattr(store, "_load", lambda: {"aliases": []})
    assert store.list_aliases() == []


def test_session_map_module_functions(tmp_path: Path, monkeypatch) -> None:
    alias_path = tmp_path / "alias.json"
    monkeypatch.setenv("OPENVIBECODING_SESSION_ALIAS_PATH", str(alias_path))

    from openvibecoding_orch.store import session_map as mod

    record = mod.set_alias("agent-x", "session-x", thread_id="thread-x", note="note")
    assert record.alias == "agent-x"
    assert mod.resolve("agent-x") is not None
    assert mod.list_aliases()
    assert mod.delete("agent-x") is True


def test_session_map_concurrent_set_alias_preserves_all_entries(tmp_path: Path) -> None:
    store = SessionAliasStore(path=tmp_path / "alias.json")
    aliases = [f"agent-{idx}" for idx in range(20)]

    def _write(alias: str) -> None:
        store.set_alias(alias, f"session-{alias}", thread_id=f"thread-{alias}")

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(_write, aliases))

    records = store.list_aliases()
    record_aliases = {record.alias for record in records}
    assert record_aliases == set(aliases)


def test_session_map_concurrent_set_alias_preserves_entries_without_fcntl(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SessionAliasStore(path=tmp_path / "alias.json")
    aliases = [f"agent-{idx}" for idx in range(50)]
    monkeypatch.setattr(session_map_module, "fcntl", None)

    original_load = store._load

    def _slow_load():
        payload = original_load()
        # Amplify concurrent overlap in the no-fcntl path to catch lost-update regressions.
        time.sleep(0.001)
        return payload

    monkeypatch.setattr(store, "_load", _slow_load)

    def _write(alias: str) -> None:
        store.set_alias(alias, f"session-{alias}", thread_id=f"thread-{alias}")

    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(_write, aliases))

    records = store.list_aliases()
    record_aliases = {record.alias for record in records}
    assert record_aliases == set(aliases)
