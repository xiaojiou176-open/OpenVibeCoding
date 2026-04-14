import io
import json
import os
import time
from pathlib import Path

import pytest

from openvibecoding_orch.transport import codex_profile_pool as profile_pool
from openvibecoding_orch.transport import mcp_jsonl


class _FakeSelector:
    def __init__(self, stdout: io.StringIO) -> None:
        self._stdout = stdout

    def register(self, _fileobj, _events):  # noqa: ANN001, ANN201
        return None

    def select(self, timeout: float):  # noqa: ANN201
        pos = self._stdout.tell()
        line = self._stdout.readline()
        self._stdout.seek(pos)
        if line:
            return [(object(), object())]
        return []


class _Proc:
    def __init__(self, stdout_text: str = "", returncode: int | None = None) -> None:
        self.stdin = io.StringIO()
        self.stdout = io.StringIO(stdout_text)
        self.returncode = returncode

    def poll(self) -> int | None:
        return self.returncode


def test_profile_pool_parse_and_state_roundtrip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("OPENVIBECODING_CODEX_PROFILE_POOL", "A,a,B")

    assert profile_pool._parse_pool_env() == ["A", "B"]

    state_path = profile_pool._pool_path()
    profile_pool._write_state(state_path, {"index": 1, "profiles": ["A", "B"]})
    loaded = profile_pool._load_state(state_path)
    assert loaded["index"] == 1

    state_path.write_text("{", encoding="utf-8")
    assert profile_pool._load_state(state_path) == {}

    lock_fd = profile_pool._acquire_file_lock(timeout_sec=0.2)
    assert lock_fd is not None
    lock_payload = json.loads(profile_pool._pool_lock_path().read_text(encoding="utf-8"))
    assert lock_payload["pid"] == os.getpid()
    assert isinstance(lock_payload["ts"], float)
    blocked_fd = profile_pool._acquire_file_lock(timeout_sec=0.05)
    assert blocked_fd is None
    profile_pool._release_file_lock(lock_fd)


def test_profile_pool_pick_profile_rotation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("OPENVIBECODING_CODEX_PROFILE_POOL", "alpha,beta")

    first = profile_pool.pick_profile()
    second = profile_pool.pick_profile()
    third = profile_pool.pick_profile()

    assert first == "alpha"
    assert second == "beta"
    assert third == "alpha"

    state_path = profile_pool._pool_path()
    state_path.write_text(json.dumps({"index": "bad-index"}), encoding="utf-8")
    after_bad_index = profile_pool.pick_profile()
    assert after_bad_index == "alpha"

    monkeypatch.delenv("OPENVIBECODING_CODEX_PROFILE_POOL", raising=False)
    assert profile_pool.pick_profile() is None


def test_profile_pool_pick_profile_fail_closed_when_lock_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("OPENVIBECODING_CODEX_PROFILE_POOL", "alpha,beta")

    monkeypatch.setattr(profile_pool, "_acquire_file_lock", lambda timeout_sec=5.0: None)

    assert profile_pool.pick_profile() is None
    assert not profile_pool._pool_path().exists()


def test_profile_pool_lock_self_heal_on_stale_pid(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(tmp_path / "runtime"))
    lock_path = profile_pool._pool_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(json.dumps({"pid": 999999, "ts": time.time()}), encoding="utf-8")
    monkeypatch.setattr(profile_pool, "_pid_exists", lambda _pid: False)

    lock_fd = profile_pool._acquire_file_lock(timeout_sec=0.2)
    assert lock_fd is not None
    healed_payload = json.loads(lock_path.read_text(encoding="utf-8"))
    assert healed_payload["pid"] == os.getpid()
    profile_pool._release_file_lock(lock_fd)


def test_profile_pool_lock_self_heal_on_stale_ttl(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("OPENVIBECODING_CODEX_PROFILE_POOL_LOCK_TTL_SEC", "1")
    lock_path = profile_pool._pool_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(json.dumps({"pid": os.getpid(), "ts": time.time() - 10}), encoding="utf-8")
    monkeypatch.setattr(profile_pool, "_pid_exists", lambda _pid: True)

    lock_fd = profile_pool._acquire_file_lock(timeout_sec=0.2)
    assert lock_fd is not None
    profile_pool._release_file_lock(lock_fd)


def test_profile_pool_lock_does_not_preempt_active_lock(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("OPENVIBECODING_CODEX_PROFILE_POOL_LOCK_TTL_SEC", "120")
    lock_path = profile_pool._pool_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    active_payload = {"pid": os.getpid(), "ts": time.time()}
    lock_path.write_text(json.dumps(active_payload), encoding="utf-8")
    monkeypatch.setattr(profile_pool, "_pid_exists", lambda _pid: True)

    lock_fd = profile_pool._acquire_file_lock(timeout_sec=0.05)
    assert lock_fd is None
    assert json.loads(lock_path.read_text(encoding="utf-8")) == active_payload


def test_profile_pool_lock_self_heal_on_invalid_payload_by_ttl(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("OPENVIBECODING_CODEX_PROFILE_POOL_LOCK_TTL_SEC", "1")
    lock_path = profile_pool._pool_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("{not-json", encoding="utf-8")
    stale_ts = time.time() - 10
    os.utime(lock_path, (stale_ts, stale_ts))

    lock_fd = profile_pool._acquire_file_lock(timeout_sec=0.2)
    assert lock_fd is not None
    healed_payload = json.loads(lock_path.read_text(encoding="utf-8"))
    assert healed_payload["pid"] == os.getpid()
    profile_pool._release_file_lock(lock_fd)


def test_profile_pool_release_keeps_active_non_owner_lock(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("OPENVIBECODING_CODEX_PROFILE_POOL_LOCK_TTL_SEC", "120")
    lock_path = profile_pool._pool_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(json.dumps({"pid": 999999, "ts": time.time()}), encoding="utf-8")
    monkeypatch.setattr(profile_pool, "_pid_exists", lambda _pid: True)

    read_fd, write_fd = os.pipe()
    os.close(read_fd)
    profile_pool._release_file_lock(write_fd)

    assert lock_path.exists()
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    assert payload["pid"] == 999999


def test_send_json_and_jsonl_stream(monkeypatch) -> None:
    proc = _Proc(stdout_text='{"id": 1}\n')
    mcp_jsonl.send_json(proc, {"method": "ping"})
    assert proc.stdin.getvalue().strip() == '{"method": "ping"}'

    proc_no_stdin = _Proc(stdout_text="")
    proc_no_stdin.stdin = None
    mcp_jsonl.send_json(proc_no_stdin, {"method": "ping"})

    stream = mcp_jsonl.JsonlStream(proc, selector=_FakeSelector(proc.stdout))
    payload = stream.read_json(timeout=0.2)
    assert payload == {"id": 1}


def test_jsonl_stream_error_and_timeout_paths() -> None:
    proc_exited = _Proc(stdout_text="", returncode=1)
    stream_exited = mcp_jsonl.JsonlStream(proc_exited, selector=_FakeSelector(proc_exited.stdout))
    with pytest.raises(RuntimeError, match="process exited"):
        stream_exited.read_json(timeout=0.2)

    proc_invalid = _Proc(stdout_text="not-json\n")
    stream_invalid = mcp_jsonl.JsonlStream(proc_invalid, selector=_FakeSelector(proc_invalid.stdout))
    assert stream_invalid.read_json(timeout=0.1) is None

    proc_until = _Proc(stdout_text='{"id": 2, "ok": true}\n')
    stream_until = mcp_jsonl.JsonlStream(proc_until, selector=_FakeSelector(proc_until.stdout))
    got = stream_until.read_until_id(match_id=2, timeout=0.2)
    assert got["id"] == 2

    proc_timeout = _Proc(stdout_text='{"id": 3}\n')
    stream_timeout = mcp_jsonl.JsonlStream(proc_timeout, selector=_FakeSelector(proc_timeout.stdout))
    with pytest.raises(RuntimeError, match="timeout waiting for response"):
        stream_timeout.read_until_id(match_id=99, timeout=0.1)


def test_jsonl_stream_requires_stdout() -> None:
    proc = _Proc()
    proc.stdout = None
    with pytest.raises(RuntimeError, match="stdout missing"):
        mcp_jsonl.JsonlStream(proc)


def test_jsonl_stream_read_line_when_stdout_becomes_none() -> None:
    proc = _Proc(stdout_text='{"id": 1}\n')
    stream = mcp_jsonl.JsonlStream(proc, selector=_FakeSelector(proc.stdout))
    stream.proc.stdout = None
    assert stream.read_line(timeout=0.1) is None
    assert mcp_jsonl.JsonlStream._ids_match(None, 2) is False
    assert mcp_jsonl.JsonlStream._ids_match("2", 2) is True


def test_profile_pool_release_none_and_write_failure(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(tmp_path / "runtime"))

    profile_pool._release_file_lock(None)

    target_path = profile_pool._pool_path()

    class _BrokenPath:
        def __init__(self, wrapped: Path) -> None:
            self._wrapped = wrapped

        @property
        def parent(self):
            return self._wrapped.parent

        def with_suffix(self, suffix: str):
            class _Tmp:
                def write_text(self, text: str, _encoding: str):  # noqa: ANN001
                    raise OSError("write failed")

                def replace(self, target):  # noqa: ANN001
                    return None

            return _Tmp()

    with pytest.raises(RuntimeError, match="codex profile pool write failed"):
        profile_pool._write_state(_BrokenPath(target_path), {"x": 1})

    read_fd, write_fd = os.pipe()
    os.close(read_fd)

    class _BrokenLockPath:
        def unlink(self, _missing_ok: bool = True) -> None:
            raise OSError("unlink failed")

    monkeypatch.setattr(profile_pool, "_pool_lock_path", lambda: _BrokenLockPath())
    profile_pool._release_file_lock(write_fd)


def test_profile_pool_error_and_parse_branches(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("OPENVIBECODING_CODEX_PROFILE_POOL", "p1,p2")

    profile_pool._release_file_lock(None)

    opened = os.open(str(tmp_path / "dummy.lock"), os.O_CREAT | os.O_WRONLY)

    class _BadLockPath:
        def unlink(self, _missing_ok: bool = False) -> None:
            raise OSError("cannot unlink")

    monkeypatch.setattr(profile_pool, "_pool_lock_path", lambda: _BadLockPath())
    profile_pool._release_file_lock(opened)

    monkeypatch.setattr(profile_pool.json, "dumps", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("boom")))
    with pytest.raises(RuntimeError, match="write failed"):
        profile_pool._write_state(profile_pool._pool_path(), {"index": 0})

    monkeypatch.undo()
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("OPENVIBECODING_CODEX_PROFILE_POOL", "p1,p2")
    profile_pool._write_state(profile_pool._pool_path(), {"index": "bad"})
    assert profile_pool.pick_profile() == "p1"
