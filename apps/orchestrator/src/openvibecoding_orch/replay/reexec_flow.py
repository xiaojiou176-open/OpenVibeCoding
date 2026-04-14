from __future__ import annotations

from typing import Any

from openvibecoding_orch.replay.replayer import ReplayRunner


def reexecute_run(replayer: ReplayRunner, run_id: str, strict: bool = True) -> dict[str, Any]:
    return replayer.reexecute(run_id, strict=strict)
