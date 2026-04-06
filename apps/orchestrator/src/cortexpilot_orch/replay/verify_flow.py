from __future__ import annotations

from typing import Any

from cortexpilot_orch.replay.replayer import ReplayRunner


def verify_run(replayer: ReplayRunner, run_id: str, strict: bool = True) -> dict[str, Any]:
    return replayer.verify(run_id, strict=strict)
