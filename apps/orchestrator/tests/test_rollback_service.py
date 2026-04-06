import json
from pathlib import Path

from cortexpilot_orch.services.rollback_service import RollbackService
from cortexpilot_orch.store import run_store as run_store_module
from cortexpilot_orch.store.run_store import RunStore


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_rollback_service_run_not_found(tmp_path: Path) -> None:
    service = RollbackService(runs_root=tmp_path / "runs")
    result = service.apply("missing")
    assert result["ok"] is False
    assert result["error_code"] == "RUN_NOT_FOUND"


def test_rollback_service_worktree_ref_missing(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    run_id = "run_missing_ref"
    run_dir = runs_root / run_id
    _write_json(run_dir / "manifest.json", {"run_id": run_id, "status": "SUCCESS"})

    store = RunStore(runs_root=runs_root)
    run_store_module._default_store = store

    service = RollbackService(runs_root=runs_root)
    result = service.apply(run_id)
    assert result["ok"] is False
    assert result["reason"] == "worktree_ref missing"


def test_rollback_service_applies_strategy(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    worktree_root = tmp_path / "worktree"
    worktree_root.mkdir(parents=True, exist_ok=True)

    run_id = "run_ok"
    run_dir = runs_root / run_id
    _write_json(run_dir / "manifest.json", {"run_id": run_id, "status": "SUCCESS"})
    _write_json(
        run_dir / "contract.json",
        {"rollback": {"strategy": "worktree_drop", "baseline_ref": "HEAD"}},
    )
    (run_dir / "worktree_ref.txt").write_text(str(worktree_root), encoding="utf-8")

    store = RunStore(runs_root=runs_root)
    run_store_module._default_store = store

    service = RollbackService(runs_root=runs_root)
    result = service.apply(run_id)
    assert result["ok"] is True
    assert result["strategy"] == "worktree_drop"


def test_rollback_service_read_json_default_and_invalid(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    assert RollbackService._read_json(missing, {"ok": False}) == {"ok": False}

    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    assert RollbackService._read_json(broken, {"fallback": 1}) == {"fallback": 1}


def test_rollback_service_apply_failure_updates_manifest(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    worktree_root = tmp_path / "worktree"
    worktree_root.mkdir(parents=True, exist_ok=True)

    run_id = "run_fail"
    run_dir = runs_root / run_id
    # Use a non-dict manifest payload to exercise fail-closed normalization.
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text("[1,2,3]", encoding="utf-8")
    _write_json(run_dir / "contract.json", {"rollback": {"strategy": "worktree_drop"}})
    (run_dir / "worktree_ref.txt").write_text(str(worktree_root), encoding="utf-8")

    monkeypatch.setattr(
        "cortexpilot_orch.services.rollback_service.apply_rollback",
        lambda _worktree_path, _rollback: {"ok": False, "error": "synthetic failure"},
    )

    store = RunStore(runs_root=runs_root)
    run_store_module._default_store = store

    service = RollbackService(runs_root=runs_root)
    result = service.apply(run_id)
    assert result == {"ok": False, "error": "synthetic failure"}

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "FAILURE"
    assert manifest["failure_code"] == "ROLLBACK_FAILED"
    assert manifest["failure_reason"] == "synthetic failure"
