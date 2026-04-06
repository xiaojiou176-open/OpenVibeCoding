from __future__ import annotations

import random
import string
from pathlib import Path

import jsonschema
from fastapi.testclient import TestClient
from hypothesis import given
from hypothesis import strategies as st

from cortexpilot_orch.api import main as api_main
from cortexpilot_orch.gates import tests_gate


def test_normalize_command_fuzz_never_raises() -> None:
    alphabet = string.ascii_letters + string.digits + " '\"\\\t\n"
    for _ in range(500):
        text = "".join(random.choice(alphabet) for _ in range(random.randint(0, 120)))
        result = tests_gate._normalize_command(text)  # noqa: SLF001 - pilot test for parser robustness
        assert isinstance(result, str)


def test_command_tower_alerts_contract_shape(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runs_root))

    client = TestClient(api_main.app)
    response = client.get("/api/command-tower/alerts")
    assert response.status_code == 200
    payload = response.json()

    schema = {
        "type": "object",
        "required": ["generated_at", "status", "slo_targets", "alerts"],
        "properties": {
            "generated_at": {"type": "string"},
            "status": {"enum": ["healthy", "degraded", "critical"]},
            "slo_targets": {"type": "object"},
            "alerts": {"type": "array"},
        },
        "additionalProperties": True,
    }
    jsonschema.validate(instance=payload, schema=schema)


def test_normalize_command_property_idempotent() -> None:
    @given(st.text())
    def _inner(value: str) -> None:
        once = tests_gate._normalize_command(value)  # noqa: SLF001 - pilot property test
        twice = tests_gate._normalize_command(once)  # noqa: SLF001 - pilot property test
        assert once == twice

    _inner()


def test_normalize_command_removes_control_whitespace_after_escape() -> None:
    once = tests_gate._normalize_command("\\\r0")  # noqa: SLF001 - regression for escaped control whitespace
    twice = tests_gate._normalize_command(once)  # noqa: SLF001 - regression for escaped control whitespace
    assert once == "0"
    assert twice == "0"


def test_normalize_command_keeps_empty_quotes_idempotent_after_formfeed() -> None:
    once = tests_gate._normalize_command('0\f""0')  # noqa: SLF001 - regression for formfeed-adjacent empty quotes
    twice = tests_gate._normalize_command(once)  # noqa: SLF001 - regression for formfeed-adjacent empty quotes
    assert once == '0 "" 0'
    assert twice == '0 "" 0'
