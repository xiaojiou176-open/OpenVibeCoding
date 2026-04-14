from __future__ import annotations

import json
import selectors
import time
from typing import Any


# -------------------------------------------------------------------
# MCP JSONL (stdio) transport helpers
# -------------------------------------------------------------------


def send_json(proc, payload: dict[str, Any], ensure_ascii: bool = False) -> None:
    if proc.stdin is None:
        return
    proc.stdin.write(json.dumps(payload, ensure_ascii=ensure_ascii) + "\n")
    proc.stdin.flush()


class JsonlStream:
    def __init__(self, proc, selector: selectors.BaseSelector | None = None) -> None:
        if proc.stdout is None:
            raise RuntimeError("stdout missing")
        self.proc = proc
        self.selector = selector or selectors.DefaultSelector()
        self.selector.register(proc.stdout, selectors.EVENT_READ)

    @staticmethod
    def _ids_match(observed_id: Any, expected_id: Any) -> bool:
        if observed_id == expected_id:
            return True
        if observed_id is None or expected_id is None:
            return False
        return str(observed_id) == str(expected_id)

    def read_line(self, timeout: float) -> str | None:
        events = self.selector.select(timeout=timeout)
        if not events:
            return None
        if self.proc.stdout is None:
            return None
        return self.proc.stdout.readline()

    def read_json(self, timeout: float) -> dict[str, Any] | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"process exited with code={self.proc.returncode}")
            line = self.read_line(0.2)
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload
        return None

    def read_until_id(self, match_id: Any, timeout: float) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            payload = self.read_json(timeout=0.5)
            if not payload:
                continue
            if self._ids_match(payload.get("id"), match_id):
                return payload
        raise RuntimeError(f"timeout waiting for response id={match_id}")
