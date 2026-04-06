#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MATRIX = ROOT / "configs" / "upstream_compat_matrix.json"
DEFAULT_OUTPUT = ROOT / ".runtime-cache" / "test_output" / "governance" / "upstream_same_run_cohesion.json"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate same-run cohesion across upstream verification records.")
    parser.add_argument("--matrix", default=str(DEFAULT_MATRIX))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    matrix = _load_json(Path(args.matrix))
    batches: dict[str, list[str]] = {}
    errors: list[str] = []

    for row in matrix.get("matrix", []):
        if not row.get("same_run_required", False):
            continue
        record_path = ROOT / str(row.get("verification_record_path") or "")
        if not record_path.exists():
            errors.append(f"missing verification record: {record_path.relative_to(ROOT)}")
            continue
        record = _load_json(record_path)
        batch_id = str(record.get("verification_batch_id") or "").strip()
        if not batch_id:
            errors.append(f"{record_path.relative_to(ROOT)} missing verification_batch_id")
            continue
        batches.setdefault(batch_id, []).append(str(row.get("integration_slice") or "<unknown>"))

    if not batches:
        errors.append("no same-run-required upstream records found")
    elif len(batches) != 1:
        for batch_id, slices in sorted(batches.items()):
            errors.append(f"verification batch `{batch_id}` only covers slices: {', '.join(sorted(slices))}")

    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "report_type": "cortexpilot_upstream_same_run_cohesion",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if not errors else "fail",
        "matrix": str(Path(args.matrix).expanduser().resolve()),
        "batches": {key: sorted(value) for key, value in sorted(batches.items())},
        "errors": errors,
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if errors:
        print("❌ [upstream-same-run-cohesion] violations:")
        for item in errors:
            print(f"- {item}")
        print(f"- report: {output_path}")
        return 1

    print("✅ [upstream-same-run-cohesion] same-run upstream evidence satisfied")
    print(f"report: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
