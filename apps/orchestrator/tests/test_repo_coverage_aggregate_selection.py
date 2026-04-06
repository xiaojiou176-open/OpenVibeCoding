from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path


def _load_repo_coverage_aggregate_module():
    script_path = Path(__file__).resolve().parents[3] / "scripts" / "repo_coverage_aggregate.py"
    spec = importlib.util.spec_from_file_location("repo_coverage_aggregate", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_vitest_summary(path: Path, *, lines_total: int, lines_covered: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "total": {
            "lines": {"total": lines_total, "covered": lines_covered, "skipped": 0, "pct": 0},
            "statements": {"total": lines_total, "covered": lines_covered, "skipped": 0, "pct": 0},
            "branches": {"total": lines_total, "covered": lines_covered, "skipped": 0, "pct": 0},
            "functions": {"total": 1, "covered": 1, "skipped": 0, "pct": 100},
        }
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_resolve_source_report_prefers_explicit_path(monkeypatch, tmp_path: Path) -> None:
    module = _load_repo_coverage_aggregate_module()
    explicit = tmp_path / "explicit" / "desktop-summary.json"
    default_candidate = tmp_path / "apps" / "desktop" / "coverage" / "run-1" / "coverage-summary.json"

    _write_vitest_summary(explicit, lines_total=10, lines_covered=10)
    _write_vitest_summary(default_candidate, lines_total=100, lines_covered=90)

    monkeypatch.setitem(module.SOURCE_SELECTION_LAYERS, "desktop", [("path", str(default_candidate))])

    source_report, totals = module._resolve_source_report("desktop", explicit)
    assert source_report == explicit
    assert totals.lines_total == 10
    assert totals.lines_covered == 10


def test_resolve_source_report_rejects_stale_run_artifact(monkeypatch, tmp_path: Path) -> None:
    module = _load_repo_coverage_aggregate_module()
    monkeypatch.setattr(module, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(module, "MAX_RUN_ARTIFACT_AGE_SECONDS", 60)

    stale_run = tmp_path / "apps" / "desktop" / "coverage" / "run-101" / "coverage-summary.json"
    canonical = tmp_path / ".runtime-cache" / "test_output" / "repo_coverage" / "desktop" / "coverage-summary.json"
    _write_vitest_summary(stale_run, lines_total=100, lines_covered=1)
    _write_vitest_summary(canonical, lines_total=100, lines_covered=100)

    stale_timestamp = 1_600_000_000
    fresh_timestamp = stale_timestamp + 10_000
    os.utime(stale_run, (stale_timestamp, stale_timestamp))
    os.utime(canonical, (fresh_timestamp, fresh_timestamp))

    monkeypatch.setitem(
        module.SOURCE_SELECTION_LAYERS,
        "desktop",
        [
            ("path", str(stale_run)),
            ("path", str(canonical)),
        ],
    )

    source_report, totals = module._resolve_source_report("desktop", None)
    assert source_report == canonical
    assert totals.lines_covered == 100


def test_resolve_source_report_skips_invalid_latest_report(monkeypatch, tmp_path: Path) -> None:
    module = _load_repo_coverage_aggregate_module()
    monkeypatch.setattr(module, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(module, "MAX_RUN_ARTIFACT_AGE_SECONDS", 99999999)

    latest_invalid = tmp_path / "apps" / "desktop" / "coverage" / "run-2" / "coverage-summary.json"
    older_valid = tmp_path / "apps" / "desktop" / "coverage" / "run-1" / "coverage-summary.json"
    latest_invalid.parent.mkdir(parents=True, exist_ok=True)
    latest_invalid.write_text("{not-json", encoding="utf-8")
    _write_vitest_summary(older_valid, lines_total=50, lines_covered=45)

    now_ts = int(Path(__file__).stat().st_mtime)
    os.utime(older_valid, (now_ts - 10, now_ts - 10))
    os.utime(latest_invalid, (now_ts, now_ts))

    monkeypatch.setitem(
        module.SOURCE_SELECTION_LAYERS,
        "desktop",
        [("glob", str(tmp_path / "apps" / "desktop" / "coverage" / "run-*" / "coverage-summary.json"))],
    )

    source_report, totals = module._resolve_source_report("desktop", None)
    assert source_report == older_valid
    assert totals.lines_total == 50
    assert totals.lines_covered == 45


def test_resolve_source_report_rejects_half_finished_run_with_tmp_marker(monkeypatch, tmp_path: Path) -> None:
    module = _load_repo_coverage_aggregate_module()
    monkeypatch.setattr(module, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(module, "MAX_RUN_ARTIFACT_AGE_SECONDS", 99999999)

    half_finished = tmp_path / "apps" / "desktop" / "coverage" / "run-202" / "coverage-summary.json"
    fallback = tmp_path / "apps" / "desktop" / "coverage" / "coverage-summary.json"
    _write_vitest_summary(half_finished, lines_total=100, lines_covered=5)
    (half_finished.parent / ".tmp").mkdir(parents=True, exist_ok=True)
    _write_vitest_summary(fallback, lines_total=100, lines_covered=95)

    monkeypatch.setitem(
        module.SOURCE_SELECTION_LAYERS,
        "desktop",
        [("multi", [("path", str(half_finished)), ("path", str(fallback))])],
    )

    source_report, totals = module._resolve_source_report("desktop", None)
    assert source_report == fallback
    assert totals.lines_covered == 95
