#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"
CONTRACTS = ROOT / "contracts"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate(schema_path: Path, instance_path: Path) -> list[str]:
    schema = _load_json(schema_path)
    instance = _load_json(instance_path)
    validator = Draft202012Validator(schema)
    errors = []
    for error in sorted(validator.iter_errors(instance), key=str):
        errors.append(error.message)
    return errors


def main() -> int:
    pairs = [
        (SCHEMAS / "task_contract.v1.json", CONTRACTS / "examples" / "task_contract.backend.json"),
        (SCHEMAS / "task_contract.v1.json", CONTRACTS / "examples" / "task_contract.ui.json"),
        (SCHEMAS / "task_result.v1.json", CONTRACTS / "examples" / "task_result.json"),
        (SCHEMAS / "review_report.v1.json", CONTRACTS / "examples" / "review_report.json"),
        (SCHEMAS / "test_report.v1.json", CONTRACTS / "examples" / "test_report.json"),
        (SCHEMAS / "work_report.v1.json", CONTRACTS / "examples" / "work_report.json"),
        (SCHEMAS / "evidence_report.v1.json", CONTRACTS / "examples" / "evidence_report.json"),
        (SCHEMAS / "task_chain.v1.json", CONTRACTS / "examples" / "task_chain.json"),
        (SCHEMAS / "task_chain.v1.json", CONTRACTS / "examples" / "task_chain.lifecycle.full.json"),
        (SCHEMAS / "chain_report.v1.json", CONTRACTS / "examples" / "chain_report.json"),
        (SCHEMAS / "reexec_report.v1.json", CONTRACTS / "examples" / "reexec_report.json"),
        (SCHEMAS / "plan.schema.json", CONTRACTS / "plans" / "plan_example.json"),
    ]

    failed = False
    for schema_path, instance_path in pairs:
        if not schema_path.exists():
            print(f"[missing schema] {schema_path}", file=sys.stderr)
            failed = True
            continue
        if not instance_path.exists():
            print(f"[missing instance] {instance_path}", file=sys.stderr)
            failed = True
            continue
        errors = _validate(schema_path, instance_path)
        if errors:
            failed = True
            print(f"[invalid] {instance_path} vs {schema_path}", file=sys.stderr)
            for message in errors:
                print(f"  - {message}", file=sys.stderr)
        else:
            print(f"[ok] {instance_path}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
