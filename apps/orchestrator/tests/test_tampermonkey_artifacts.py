import json
from pathlib import Path

from cortexpilot_orch.store.run_store import RunStore
from tooling.tampermonkey.runner import run_tampermonkey


def test_tampermonkey_artifacts_unique(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runs_root))
    store = RunStore(runs_root)
    run_id = store.create_run("task_tm")

    run_tampermonkey(run_id, "script_demo", "first")
    run_tampermonkey(run_id, "script_demo", "second")

    events_path = runs_root / run_id / "events.jsonl"
    lines = events_path.read_text(encoding="utf-8").splitlines()
    outputs = [json.loads(line) for line in lines if "\"TAMPERMONKEY_OUTPUT\"" in line]
    assert len(outputs) == 2
    raw_refs = [item["context"]["raw_ref"] for item in outputs]
    assert raw_refs[0] != raw_refs[1]
    for ref in raw_refs:
        assert Path(ref).exists()
