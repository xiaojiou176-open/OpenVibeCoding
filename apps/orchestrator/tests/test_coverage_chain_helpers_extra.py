import json
from pathlib import Path

import pytest

from openvibecoding_orch.planning import coverage_chain


def test_run_coverage_scan_invokes_subprocess(monkeypatch, tmp_path: Path) -> None:
    calls: dict[str, object] = {}

    def _fake_run(cmd, cwd, check, env):  # noqa: ANN001
        calls["cmd"] = cmd
        calls["cwd"] = cwd
        calls["check"] = check
        calls["pythonpath"] = env.get("PYTHONPATH")

    monkeypatch.setattr(coverage_chain.subprocess, "run", _fake_run)

    output_path = tmp_path / "nested" / "coverage.json"
    coverage_chain.run_coverage_scan(tmp_path, output_path)

    assert output_path.parent.exists()
    cmd = calls.get("cmd")
    assert isinstance(cmd, list)
    assert any(str(item).startswith("--cov-report=json:") for item in cmd)
    assert calls.get("cwd") == tmp_path
    assert calls.get("check") is True
    assert calls.get("pythonpath") == "apps/orchestrator/src"


def test_load_coverage_targets_handles_invalid_payload_shapes(tmp_path: Path) -> None:
    payload_invalid = {"files": []}
    coverage_path = tmp_path / "coverage-invalid.json"
    coverage_path.write_text(json.dumps(payload_invalid), encoding="utf-8")
    assert coverage_chain.load_coverage_targets(coverage_path, threshold=90.0, max_workers=3) == []

    payload = {
        "files": {
            "apps/orchestrator/src/openvibecoding_orch/__init__.py": {
                "summary": {
                    "percent_covered": 1.0,
                }
            },
            "apps/orchestrator/src/openvibecoding_orch/service/foo.py": {
                "summary": {
                    "percent_covered": 72.0,
                }
            },
            "apps/orchestrator/src/openvibecoding_orch/service/bar.py": {
                "summary": "not-dict",
            },
            "other/path.py": {
                "summary": {
                    "percent_covered": 0.0,
                }
            },
        }
    }
    coverage_path.write_text(json.dumps(payload), encoding="utf-8")

    targets = coverage_chain.load_coverage_targets(
        coverage_path,
        threshold=90.0,
        max_workers=3,
        include_prefix="apps/orchestrator/src/openvibecoding_orch/",
        coverage_metric="branches",
    )

    assert [item.module_name for item in targets] == ["openvibecoding_orch.service.foo"]


def test_coverage_chain_default_python_and_timeout_fallback(monkeypatch) -> None:
    monkeypatch.delenv("OPENVIBECODING_PYTHON", raising=False)
    monkeypatch.setenv("OPENVIBECODING_COVERAGE_WORKER_TIMEOUT_SEC", "bad-timeout")

    python_bin = coverage_chain._preferred_worker_python()
    timeout_sec = coverage_chain._worker_timeout_sec()

    assert python_bin.endswith("/.runtime-cache/cache/toolchains/python/current/bin/python")
    assert timeout_sec == 300


def test_build_chain_requires_targets() -> None:
    with pytest.raises(ValueError, match="no coverage targets selected"):
        coverage_chain.build_coverage_self_heal_chain([], chain_id="empty")
