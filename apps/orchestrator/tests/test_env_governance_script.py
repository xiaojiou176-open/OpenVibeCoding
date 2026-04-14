from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_env_governance_module():
    script_path = Path(__file__).resolve().parents[3] / "scripts" / "check_env_governance.py"
    spec = importlib.util.spec_from_file_location("check_env_governance", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_collect_source_keys_captures_os_environ_writes(monkeypatch, tmp_path: Path) -> None:
    module = _load_env_governance_module()
    scan_root = tmp_path / "src"
    scan_root.mkdir(parents=True, exist_ok=True)
    source = scan_root / "sample.py"
    source.write_text(
        "\n".join(
            [
                'os.environ["OPENVIBECODING_RUNNER"] = "agents"',
                'os.environ.setdefault("OPENVIBECODING_ALLOW_CODEX_EXEC", "1")',
                'os.environ.pop("OPENVIBECODING_FORCE_UNLOCK", None)',
                'os.getenv("OPENVIBECODING_RUNTIME_ROOT", ".runtime-cache/openvibecoding")',
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "SCAN_ROOTS", ("src",))
    refs = module._collect_source_keys(tmp_path)

    assert "OPENVIBECODING_RUNNER" in refs
    assert "OPENVIBECODING_ALLOW_CODEX_EXEC" in refs
    assert "OPENVIBECODING_FORCE_UNLOCK" in refs
    assert "OPENVIBECODING_RUNTIME_ROOT" in refs
