#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MATRIX = ROOT / "docs" / "governance" / "ui-button-coverage-matrix.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fail when matrix has TODO entries for required tiers.")
    parser.add_argument("--matrix", default=str(DEFAULT_MATRIX), help="Matrix markdown path")
    parser.add_argument("--tiers", default="P0", help="Comma-separated tiers, e.g. P0 or P0,P1")
    parser.add_argument("--surfaces", default="dashboard,desktop", help="Comma-separated surfaces")
    parser.add_argument(
        "--min-scoped",
        type=int,
        default=1,
        help="Fail when scoped rows are fewer than this value (default: 1). Use 0 to disable.",
    )
    parser.add_argument(
        "--fail-on-todo",
        type=int,
        choices=(0, 1),
        default=1,
        help="Whether TODO rows should fail the gate (1=yes, 0=no).",
    )
    parser.add_argument(
        "--gate-name",
        default="ui-matrix-todo-gate",
        help="Logical gate name used in output for attribution.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    matrix_path = Path(args.matrix)
    tiers = {x.strip() for x in args.tiers.split(",") if x.strip()}
    surfaces = {x.strip() for x in args.surfaces.split(",") if x.strip()}
    min_scoped = max(args.min_scoped, 0)
    fail_on_todo = bool(args.fail_on_todo)
    gate_name = args.gate_name.strip() or "ui-matrix-todo-gate"

    if not matrix_path.exists():
        raise SystemExit(f"matrix not found: {matrix_path}")

    rows = []
    for line in matrix_path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| btn-"):
            continue
        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) < 7:
            continue
        row = {
            "id": cols[0],
            "surface": cols[1],
            "tier": cols[2],
            "file": cols[3],
            "action": cols[4],
            "status": cols[5],
            "notes": cols[6],
        }
        rows.append(row)

    scoped = [r for r in rows if r["tier"] in tiers and r["surface"] in surfaces]
    todo = [r for r in scoped if r["status"] == "TODO"]

    print(
        f"[{gate_name}] "
        f"scoped={len(scoped)} todo={len(todo)} tiers={','.join(sorted(tiers))} surfaces={','.join(sorted(surfaces))} "
        f"min_scoped={min_scoped} fail_on_todo={int(fail_on_todo)}"
    )

    if min_scoped > 0 and len(scoped) < min_scoped:
        print(
            f"\n[{gate_name}] scoped rows below minimum: scoped={len(scoped)} < min_scoped={min_scoped}. "
            "Please sync matrix tiers and/or update scope filters."
        )
        return 1

    if fail_on_todo and todo:
        print(f"\n[{gate_name}] TODO entries:")
        for r in todo:
            print(f"- {r['id']} | {r['surface']} | {r['tier']} | {r['file']} | {r['action']}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
