#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MATRIX = ROOT / "docs" / "governance" / "ui-button-coverage-matrix.md"
DEFAULT_OUTPUT = ROOT / "configs" / "ui_button_coverage_annotations.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="One-time migrate matrix annotations from markdown to JSON SSOT.")
    parser.add_argument("--matrix", default=str(DEFAULT_MATRIX))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    matrix_path = Path(args.matrix).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    rows: dict[str, dict[str, str]] = {}

    for line in matrix_path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| btn-"):
            continue
        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) < 10:
            continue
        row_id = cols[0]
        rows[row_id] = {
            "status": cols[5],
            "notes": cols[6],
            "evidence_type": cols[7],
            "source_path": cols[8],
            "source_kind": cols[9],
        }

    output_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "description": "Human-maintained annotations for generated UI button coverage matrix rows.",
                "rows": rows,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"[migrate-ui-matrix] migrated_rows={len(rows)} output={output_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
