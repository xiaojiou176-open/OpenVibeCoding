from __future__ import annotations

from pathlib import Path

from openvibecoding_orch.contract.validator import validate_contract


def run_schema_gate(contract_path: Path) -> dict:
    contract = validate_contract(contract_path)
    return {"ok": True, "contract": contract}
