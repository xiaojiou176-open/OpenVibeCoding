from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any


def _write_report_fixture(tmp_path: Path, *, summary_overrides: dict[str, Any] | None = None) -> Path:
    run_dir = tmp_path / "ui_full_run"
    run_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "total_routes": 1,
        "total_interactions": 1,
        "interaction_click_failures": 0,
        "gemini_warn_or_fail": 2,
        "click_inventory_entries": 1,
        "click_inventory_blocking_failures": 0,
        "click_inventory_missing_target_refs": 0,
        "click_inventory_overall_passed": True,
    }
    if summary_overrides:
        summary.update(summary_overrides)
    click_inventory_report = run_dir / "click_inventory_report.json"
    click_inventory_report.write_text(
        json.dumps(
            {
                "summary": {
                    "total_entries": int(summary["click_inventory_entries"]),
                    "blocking_failures": int(summary["click_inventory_blocking_failures"]),
                    "missing_target_ref_count": int(summary["click_inventory_missing_target_refs"]),
                    "overall_passed": bool(summary["click_inventory_overall_passed"]),
                    "click_failures": int(summary["interaction_click_failures"]),
                    "analysis_warn_or_fail_count": int(summary["gemini_warn_or_fail"]),
                }
            }
        ),
        encoding="utf-8",
    )
    report = {
        "routes": [
            {
                "route": "/pm",
                "errors": [],
                "page_analysis": {"verdict": "fail"},
                "interactions": [
                    {
                        "index": 1,
                        "target": {"href": "/pm", "text": "PM"},
                        "click_ok": True,
                        "analysis": {"verdict": "warn"},
                        "errors": [],
                    }
                ],
            }
        ],
        "summary": summary,
        "artifacts": {
            "click_inventory_report": str(click_inventory_report),
        },
    }
    report_path = run_dir / "report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    return report_path


def _stdout_summary(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    text = result.stdout.strip()
    for idx, char in enumerate(text):
        if char != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(text[idx:])
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            continue
    raise AssertionError(f"missing JSON summary in stdout: {text}")


def test_ui_full_e2e_strict_gate_click_only_mode_passes_when_click_consistency_ok(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    script_path = repo_root / "scripts" / "ui_full_e2e_gemini_strict_gate.py"
    report_path = _write_report_fixture(tmp_path)

    env = dict(os.environ)
    env.update(
        {
            "OPENVIBECODING_UI_STRICT_BREAK_GLASS": "1",
            "OPENVIBECODING_UI_STRICT_BREAK_GLASS_REASON": "test-click-only",
            "OPENVIBECODING_UI_STRICT_BREAK_GLASS_TICKET": "TEST-STRICT-001",
        }
    )
    result = subprocess.run(
        ["python3", str(script_path), "--report", str(report_path), "--click-only"],
        cwd=repo_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    summary = _stdout_summary(result)
    assert summary["click_only_mode"] is True
    assert summary["hard_gate_ok"] is True
    assert summary["anti_fake_ok"] is True
    assert summary["gemini_clean_ok"] is False
    assert summary["page_fail"] == 1
    assert summary["inter_warn"] == 1


def test_ui_full_e2e_strict_gate_full_mode_blocks_warn_fail(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    script_path = repo_root / "scripts" / "ui_full_e2e_gemini_strict_gate.py"
    report_path = _write_report_fixture(tmp_path)

    result = subprocess.run(
        ["python3", str(script_path), "--report", str(report_path)],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, result.stderr
    assert "page verdict has warn/fail" in result.stderr
    summary = _stdout_summary(result)
    assert summary["click_only_mode"] is False
    assert summary["gemini_clean_ok"] is False
    assert summary["hard_gate_ok"] is True


def test_ui_full_e2e_strict_gate_click_only_mode_blocks_summary_mismatch(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    script_path = repo_root / "scripts" / "ui_full_e2e_gemini_strict_gate.py"
    report_path = _write_report_fixture(tmp_path, summary_overrides={"total_interactions": 7})

    env = dict(os.environ)
    env.update(
        {
            "OPENVIBECODING_UI_STRICT_BREAK_GLASS": "1",
            "OPENVIBECODING_UI_STRICT_BREAK_GLASS_REASON": "test-click-only-mismatch",
            "OPENVIBECODING_UI_STRICT_BREAK_GLASS_TICKET": "TEST-STRICT-002",
        }
    )
    result = subprocess.run(
        ["python3", str(script_path), "--report", str(report_path), "--click-only"],
        cwd=repo_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, result.stderr
    assert "summary.total_interactions mismatch" in result.stderr


def test_ui_full_e2e_strict_gate_blocks_when_summary_mismatches_click_inventory_report(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    script_path = repo_root / "scripts" / "ui_full_e2e_gemini_strict_gate.py"
    report_path = _write_report_fixture(tmp_path)
    click_inventory_report_path = report_path.parent / "click_inventory_report.json"
    click_inventory_payload = json.loads(click_inventory_report_path.read_text(encoding="utf-8"))
    click_inventory_payload["summary"]["click_failures"] = 1
    click_inventory_report_path.write_text(
        json.dumps(click_inventory_payload),
        encoding="utf-8",
    )

    env = dict(os.environ)
    env.update(
        {
            "OPENVIBECODING_UI_STRICT_BREAK_GLASS": "1",
            "OPENVIBECODING_UI_STRICT_BREAK_GLASS_REASON": "test-click-summary-mismatch",
            "OPENVIBECODING_UI_STRICT_BREAK_GLASS_TICKET": "TEST-STRICT-003",
        }
    )
    result = subprocess.run(
        ["python3", str(script_path), "--report", str(report_path), "--click-only"],
        cwd=repo_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, result.stderr
    assert "summary.interaction_click_failures mismatch" in result.stderr
