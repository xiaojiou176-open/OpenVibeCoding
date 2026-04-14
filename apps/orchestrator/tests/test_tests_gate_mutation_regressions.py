from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _write_checker(path: Path, trigger_texts: list[str]) -> None:
    checks = "\n".join([f"if {trigger!r} in text:\n    raise SystemExit(1)" for trigger in trigger_texts])
    path.write_text(
        (
            "from pathlib import Path\n"
            "import os\n\n"
            "target = Path(os.environ['OPENVIBECODING_MUTATION_TARGET_FILE'])\n"
            "text = target.read_text(encoding='utf-8')\n"
            f"{checks}\n"
            "raise SystemExit(0)\n"
        ),
        encoding="utf-8",
    )


def test_mutation_gate_writes_report_and_enforces_kill_rate(tmp_path: Path) -> None:
    repo_root = _repo_root()
    script_path = repo_root / "scripts" / "mutation_gate.sh"

    target_file = tmp_path / "target.py"
    target_file.write_text("FLAG = True\nVALUE = 1\nMODE = 'strict'\n", encoding="utf-8")

    config_file = tmp_path / "mutants.json"
    config_file.write_text(
        json.dumps(
            {
                "mutants": [
                    {
                        "name": "flag_flip",
                        "operator": "boolean_flip",
                        "old": "FLAG = True",
                        "new": "FLAG = False",
                    },
                    {
                        "name": "value_increment",
                        "operator": "literal_replace",
                        "old": "VALUE = 1",
                        "new": "VALUE = 2",
                    },
                    {
                        "name": "mode_change",
                        "operator": "literal_replace",
                        "old": "MODE = 'strict'",
                        "new": "MODE = 'loose'",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    checker = tmp_path / "checker.py"
    _write_checker(checker, ["FLAG = False", "VALUE = 2", "MODE = 'loose'"])
    report_path = tmp_path / "mutation_gate_report.json"

    env = dict(os.environ)
    env.update(
        {
                "PYTHON_BIN": sys.executable,
                "OPENVIBECODING_MUTATION_TARGET_FILE": str(target_file),
                "OPENVIBECODING_MUTATION_CONFIG_FILE": str(config_file),
                "OPENVIBECODING_MUTATION_TEST_CMD": f"\"{sys.executable}\" \"{checker}\"",
                "OPENVIBECODING_MUTATION_REPORT_PATH": str(report_path),
                "OPENVIBECODING_MUTATION_MIN_MUTANTS": "3",
                "OPENVIBECODING_MUTATION_MIN_KILL_RATE": "1.0",
            }
    )

    proc = subprocess.run(["bash", str(script_path)], cwd=repo_root, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert report_path.exists()

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["target"] == str(target_file.resolve())
    assert report["killed"] == 3
    assert report["survived"] == 0
    assert report["kill_rate"] == 1.0
    assert "operators" in report
    assert report["status"] == "passed"
    assert target_file.read_text(encoding="utf-8") == "FLAG = True\nVALUE = 1\nMODE = 'strict'\n"


def test_mutation_gate_fail_closed_when_kill_rate_below_threshold(tmp_path: Path) -> None:
    repo_root = _repo_root()
    script_path = repo_root / "scripts" / "mutation_gate.sh"

    target_file = tmp_path / "target.py"
    target_file.write_text("FLAG = True\nVALUE = 1\n", encoding="utf-8")

    config_file = tmp_path / "mutants.json"
    config_file.write_text(
        json.dumps(
            {
                "mutants": [
                    {
                        "name": "flag_flip",
                        "operator": "boolean_flip",
                        "old": "FLAG = True",
                        "new": "FLAG = False",
                    },
                    {
                        "name": "value_increment_survivor",
                        "operator": "literal_replace",
                        "old": "VALUE = 1",
                        "new": "VALUE = 2",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    checker = tmp_path / "checker.py"
    _write_checker(checker, ["FLAG = False"])
    report_path = tmp_path / "mutation_gate_report.json"

    env = dict(os.environ)
    env.update(
        {
                "PYTHON_BIN": sys.executable,
                "OPENVIBECODING_MUTATION_TARGET_FILE": str(target_file),
                "OPENVIBECODING_MUTATION_CONFIG_FILE": str(config_file),
                "OPENVIBECODING_MUTATION_TEST_CMD": f"\"{sys.executable}\" \"{checker}\"",
                "OPENVIBECODING_MUTATION_REPORT_PATH": str(report_path),
                "OPENVIBECODING_MUTATION_MIN_MUTANTS": "2",
                "OPENVIBECODING_MUTATION_MIN_KILL_RATE": "1.0",
            }
    )

    proc = subprocess.run(["bash", str(script_path)], cwd=repo_root, env=env, capture_output=True, text=True)
    assert proc.returncode != 0
    assert report_path.exists()

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["killed"] == 1
    assert report["survived"] == 1
    assert report["kill_rate"] == 0.5
    assert report["status"] == "failed"
    assert report["failure_reasons"]
