from __future__ import annotations

from pathlib import Path

import pytest

from openvibecoding_orch.store.run_store import RunStore


@pytest.mark.parametrize("bad_run_id", ["", "../escape", "run/../escape", "/abs/path", "..", "run..id"])
def test_run_dir_rejects_unsafe_run_ids(tmp_path: Path, bad_run_id: str) -> None:
    store = RunStore(runs_root=tmp_path / "runs")
    with pytest.raises(ValueError):
        store.run_dir(bad_run_id)


def test_run_dir_accepts_safe_run_id(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path / "runs")
    run_dir = store.run_dir("run_20260225_abcdef")
    assert run_dir == tmp_path / "runs" / "run_20260225_abcdef"


def test_active_contract_is_isolated_per_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(tmp_path / "runtime"))
    store = RunStore(runs_root=tmp_path / "runs")
    run_a = "run_a"
    run_b = "run_b"
    contract_a = {"task_id": "task-a", "tag": "A"}
    contract_b = {"task_id": "task-b", "tag": "B"}

    path_a = store.write_active_contract(run_a, contract_a)
    path_b = store.write_active_contract(run_b, contract_b)

    assert path_a != path_b
    assert path_a.exists()
    assert path_b.exists()
    assert store.read_active_contract(run_a) == contract_a
    assert store.read_active_contract(run_b) == contract_b

    store.clear_active_contract(run_a)
    assert store.read_active_contract(run_a) is None
    assert store.read_active_contract(run_b) == contract_b
