from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e


def test_doctor_e2e(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[4]
    env = os.environ.copy()
    pythonpath = str(repo_root / "apps" / "orchestrator" / "src")
    if env.get("PYTHONPATH"):
        pythonpath = f"{pythonpath}{os.pathsep}{env['PYTHONPATH']}"
    env["PYTHONPATH"] = pythonpath
    result = subprocess.run(
        [sys.executable, "-m", "cortexpilot_orch.cli", "doctor"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
