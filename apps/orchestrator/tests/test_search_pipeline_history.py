import json
from pathlib import Path

from tooling.search_pipeline import write_search_results, write_verification, write_purified_summary


def test_search_pipeline_appends_history(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runs_root))
    run_id = "run_search_history"

    write_search_results(run_id, [{"href": "https://example.com/one"}])
    write_search_results(run_id, [{"href": "https://example.com/two"}])

    latest_path = runs_root / run_id / "artifacts" / "search_results.json"
    payload = json.loads(latest_path.read_text(encoding="utf-8"))
    assert payload["latest"]["results"][0]["href"].endswith("/two")

    history_path = runs_root / run_id / "artifacts" / "search_results.jsonl"
    lines = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 2
    assert lines[0]["entry_id"] != lines[1]["entry_id"]


def test_verification_appends_history(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runs_root))
    run_id = "run_verify_history"

    write_verification(run_id, {"ok": True})
    write_verification(run_id, {"ok": False, "reason": "mismatch"})

    latest_path = runs_root / run_id / "artifacts" / "verification.json"
    payload = json.loads(latest_path.read_text(encoding="utf-8"))
    assert payload["latest"]["verification"]["ok"] is False

    history_path = runs_root / run_id / "artifacts" / "verification.jsonl"
    lines = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 2


def test_purified_summary_appends_history(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runs_root))
    run_id = "run_purify_history"

    write_purified_summary(run_id, [{"provider": "duckduckgo", "results": [{"href": "https://example.com"}]}], {"ok": True})
    write_purified_summary(run_id, [{"provider": "duckduckgo", "results": [{"href": "https://example.com/2"}]}], {"ok": False})

    latest_path = runs_root / run_id / "artifacts" / "purified_summary.json"
    payload = json.loads(latest_path.read_text(encoding="utf-8"))
    assert payload["latest"]["summary"]["total_runs"] == 1
    assert payload["latest"]["summary"]["verification"]["ok"] is False

    history_path = runs_root / run_id / "artifacts" / "purified_summary.jsonl"
    lines = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 2
