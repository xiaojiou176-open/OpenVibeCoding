from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from itertools import count
from typing import Any

from openvibecoding_orch.transport.mcp_jsonl import send_json


# -------------------------------------------------------------------
# Multiplex proxy
# -------------------------------------------------------------------


_REQUEST_COUNTER = count(1)


@dataclass
class ProxyHandle:
    proc: subprocess.Popen[str]
    pending: dict[str, queue.Queue] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)
    reader: threading.Thread | None = None
    codex_home_dir: str | None = None


class ProxyClient:
    def __init__(self, handle: ProxyHandle, client_id: str) -> None:
        self.handle = handle
        self.client_id = client_id
        self.counter = 0

    def _next_id(self) -> int:
        self.counter += 1
        return next(_REQUEST_COUNTER)

    def call(self, method: str, params: dict[str, Any], timeout: float = 5.0) -> dict[str, Any]:
        req_id = self._next_id()
        req_key = str(req_id)
        q: queue.Queue = queue.Queue()
        with self.handle.lock:
            self.handle.pending[req_key] = q
        send_json(
            self.handle.proc,
            {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params},
        )
        try:
            return q.get(timeout=timeout)
        except queue.Empty as exc:
            raise RuntimeError(f"timeout waiting for {req_id}") from exc
        finally:
            with self.handle.lock:
                self.handle.pending.pop(req_key, None)


# -------------------------------------------------------------------
# I/O
# -------------------------------------------------------------------


def _reader_loop(handle: ProxyHandle) -> None:
    proc = handle.proc
    if proc.stdout is None:
        return
    while True:
        line = proc.stdout.readline()
        if not line:
            if proc.poll() is not None:
                return
            time.sleep(0.05)
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        req_id = payload.get("id")
        if req_id is None:
            continue
        with handle.lock:
            q = handle.pending.get(str(req_id))
        if q is not None:
            q.put(payload)


def _build_isolated_codex_env() -> tuple[dict[str, str], str]:
    codex_home = tempfile.mkdtemp(prefix="openvibecoding_mcp_proxy_home_")
    env = os.environ.copy()
    env["CODEX_HOME"] = codex_home
    env["OPENVIBECODING_CODEX_BASE_HOME"] = codex_home
    return env, codex_home


def start_proxy() -> ProxyHandle:
    env, codex_home_dir = _build_isolated_codex_env()
    proc = subprocess.Popen(
        ["codex", "mcp-server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=env,
    )
    if proc.poll() is not None:
        stderr = proc.stderr.read() if proc.stderr else ""
        raise RuntimeError(f"mcp-server failed to start: {stderr.strip()}")
    handle = ProxyHandle(proc=proc, codex_home_dir=codex_home_dir)
    reader = threading.Thread(target=_reader_loop, args=(handle,), daemon=True)
    handle.reader = reader
    reader.start()
    return handle


def stop_proxy(handle: ProxyHandle) -> None:
    if handle.proc.poll() is None:
        handle.proc.terminate()
        try:
            handle.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            handle.proc.kill()
    if handle.codex_home_dir:
        shutil.rmtree(handle.codex_home_dir, ignore_errors=True)
