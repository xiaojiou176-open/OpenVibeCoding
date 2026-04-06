from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_taxonomy_module():
    script_path = Path(__file__).resolve().parents[3] / "scripts" / "ui_regression_failure_taxonomy.py"
    spec = importlib.util.spec_from_file_location("ui_regression_failure_taxonomy", script_path)
    assert spec and spec.loader, f"Failed to load taxonomy module from {script_path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gate_manual_env_failures_do_not_collapse_to_product_bucket() -> None:
    module = _load_taxonomy_module()

    gate_code, gate_bucket, _ = module.classify("policy gate denied: write path not in allowed_paths")
    manual_code, manual_bucket, _ = module.classify("manual cancel requested by operator")
    env_code, env_bucket, _ = module.classify("address already in use: port 3100")
    product_code, product_bucket, _ = module.classify("500 internal server error from backend")

    assert gate_code == "RULE_BLOCKED"
    assert gate_bucket == "gate"
    assert manual_code == "MANUAL_CONFIRM_REQUIRED"
    assert manual_bucket == "manual"
    assert env_code == "PORT_CONFLICT"
    assert env_bucket == "env"
    assert product_code == "API_5XX"
    assert product_bucket == "product"


def test_taxonomy_fallback_no_longer_returns_unknown() -> None:
    module = _load_taxonomy_module()

    code, bucket, owner = module.classify("non-deterministic crash signature with no known pattern")
    assert code == "FUNCTIONAL_ANOMALY"
    assert bucket == "product"
    assert owner == "backend"
