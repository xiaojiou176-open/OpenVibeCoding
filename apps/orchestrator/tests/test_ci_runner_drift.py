from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = REPO_ROOT / "scripts" / "check_ci_runner_drift.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_ci_runner_drift", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_baseline(path: Path) -> Path:
    payload = {
        "schema_version": 1,
        "commands": [
            {"name": "docker", "version_args": ["--version"], "required": True, "match_regex": "^Docker version"},
            {"name": "sudo", "version_args": ["--version"], "required": True, "match_regex": "^Sudo version"},
            {"name": "curl", "version_args": ["--version"], "required": True, "match_regex": "^curl 8\\."},
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def test_push_main_treats_missing_host_tools_as_report_only(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    baseline = _write_baseline(tmp_path / "baseline.json")
    out_dir = tmp_path / "out"

    def fake_run(name: str, _args: list[str]) -> tuple[bool, str]:
        outputs = {
            "docker": (False, ""),
            "sudo": (False, ""),
            "curl": (True, "curl 8.5.0"),
        }
        return outputs[name]

    monkeypatch.setattr(module, "_run_command", fake_run)
    monkeypatch.setenv("OPENVIBECODING_CI_ROUTE_ID", "push_main")
    monkeypatch.setattr(
        module,
        "DEFAULT_OUT_DIR",
        out_dir,
        raising=False,
    )
    monkeypatch.setattr(
        module.argparse.ArgumentParser,
        "parse_args",
        lambda self: module.argparse.Namespace(
            baseline=str(baseline),
            out_dir=str(out_dir),
            mode="strict",
        ),
    )

    assert module.main() == 0
    payload = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
    assert payload["status"] == "pass"
    assert payload["route_id"] == "push_main"
    assert payload["failures"] == []
    assert [row["name"] for row in payload["checks"] if row["report_only"]] == ["docker", "sudo"]


def test_local_strict_mode_still_fails_on_missing_host_tools(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    baseline = _write_baseline(tmp_path / "baseline.json")
    out_dir = tmp_path / "out"

    def fake_run(name: str, _args: list[str]) -> tuple[bool, str]:
        outputs = {
            "docker": (False, ""),
            "sudo": (False, ""),
            "curl": (True, "curl 8.5.0"),
        }
        return outputs[name]

    monkeypatch.setattr(module, "_run_command", fake_run)
    monkeypatch.delenv("OPENVIBECODING_CI_ROUTE_ID", raising=False)
    monkeypatch.setattr(
        module,
        "DEFAULT_OUT_DIR",
        out_dir,
        raising=False,
    )
    monkeypatch.setattr(
        module.argparse.ArgumentParser,
        "parse_args",
        lambda self: module.argparse.Namespace(
            baseline=str(baseline),
            out_dir=str(out_dir),
            mode="strict",
        ),
    )

    assert module.main() == 1
    payload = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
    assert payload["status"] == "fail"
    assert payload["route_id"] is None
    assert payload["failures"] == ["docker: command missing", "sudo: command missing"]
