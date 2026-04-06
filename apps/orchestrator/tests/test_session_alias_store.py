import os
from pathlib import Path

from cortexpilot_orch.store.session_map import SessionAliasStore


def test_session_alias_store_roundtrip(tmp_path: Path):
    path = tmp_path / "alias_map.json"
    os.environ["CORTEXPILOT_SESSION_ALIAS_PATH"] = str(path)
    try:
        store = SessionAliasStore()

        record = store.set_alias("plan-1", "sess-1", thread_id="thread-1", note="demo")
        assert record.alias == "plan-1"
        assert record.session_id == "sess-1"

        resolved = store.resolve("plan-1")
        assert resolved is not None
        assert resolved.thread_id == "thread-1"

        listed = store.list_aliases()
        assert [item.alias for item in listed] == ["plan-1"]

        assert store.delete("plan-1") is True
        assert store.resolve("plan-1") is None
    finally:
        os.environ.pop("CORTEXPILOT_SESSION_ALIAS_PATH", None)
