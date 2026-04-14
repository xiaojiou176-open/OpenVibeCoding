from __future__ import annotations

import os

from openvibecoding_orch.temporal.workflows import _isolated_temporal_env


def test_isolated_temporal_env_restores_values(monkeypatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_TEMPORAL_ACTIVITY", "0")
    monkeypatch.delenv("OPENVIBECODING_TEMPORAL_WORKFLOW_ID", raising=False)

    with _isolated_temporal_env():
        os.environ["OPENVIBECODING_TEMPORAL_ACTIVITY"] = "1"
        os.environ["OPENVIBECODING_TEMPORAL_WORKFLOW"] = "0"
        os.environ["OPENVIBECODING_TEMPORAL_WORKFLOW_ID"] = "wf-123"

    assert os.environ["OPENVIBECODING_TEMPORAL_ACTIVITY"] == "0"
    assert "OPENVIBECODING_TEMPORAL_WORKFLOW_ID" not in os.environ

