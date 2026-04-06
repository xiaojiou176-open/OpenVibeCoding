#!/usr/bin/env python3
"""Matrix-Compiler merge entry for 49/70/68/52 master table."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

FIELD_ALIASES = {
    "list": ("list",),
    "id": ("id",),
    "issue": ("issue", "\u95ee\u9898"),
    "status": ("status", "\u72b6\u6001"),
    "evidence_path": ("evidence_path", "\u8bc1\u636e\u8def\u5f84"),
    "fix_ref": ("fix_ref", "\u4fee\u590dPR/\u6d4b\u8bd5\u547d\u4ee4"),
}
REQUIRED_FIELDS = tuple(FIELD_ALIASES.keys())
DEFAULT_COUNTS = {"A": 49, "B": 70, "C": 68, "D": 52}
DEFAULT_TEMPLATE = Path(
    "docs/archive/governance/matrix-compiler-49-70-68-52-master-table-template.md"
)
DEFAULT_OUTPUT = Path("docs/governance/matrix-compiler-49-70-68-52-master-table.md")


@dataclass(frozen=True)
class MatrixRow:
    list_name: str
    row_id: str
    issue: str
    status: str
    evidence_path: str
    fix_ref: str

    @classmethod
    def from_payload(cls, payload: dict[str, object], source: Path, index: int) -> "MatrixRow":
        missing = [key for key in REQUIRED_FIELDS if _is_blank(_resolve_field(payload, key))]
        if missing:
            raise ValueError(
                f"{source}:{index} missing required fields: {', '.join(missing)}"
            )
        list_name = str(_resolve_field(payload, "list")).strip()
        if list_name not in DEFAULT_COUNTS:
            raise ValueError(f"{source}:{index} invalid list value: {list_name!r}; expected one of A/B/C/D")
        return cls(
            list_name=list_name,
            row_id=str(_resolve_field(payload, "id")).strip(),
            issue=str(_resolve_field(payload, "issue")).strip(),
            status=str(_resolve_field(payload, "status")).strip(),
            evidence_path=str(_resolve_field(payload, "evidence_path")).strip(),
            fix_ref=str(_resolve_field(payload, "fix_ref")).strip(),
        )

    def markdown_row(self) -> str:
        cols = [
            self.list_name,
            _escape_md(self.row_id),
            _escape_md(self.issue),
            _escape_md(self.status),
            _escape_md(self.evidence_path),
            _escape_md(self.fix_ref),
        ]
        return f"| {' | '.join(cols)} |"


def _is_blank(value: object) -> bool:
    return value is None or str(value).strip() == ""


def _escape_md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "<br>")


def _resolve_field(payload: dict[str, object], canonical: str) -> object:
    for alias in FIELD_ALIASES[canonical]:
        if alias in payload and not _is_blank(payload.get(alias)):
            return payload.get(alias)
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge A/B/C/D matrix JSON rows into the 49/70/68/52 master markdown table."
    )
    parser.add_argument("--a", type=Path, help="A list JSON file (49 rows expected)")
    parser.add_argument("--b", type=Path, help="B list JSON file (70 rows expected)")
    parser.add_argument("--c", type=Path, help="C list JSON file (68 rows expected)")
    parser.add_argument("--d", type=Path, help="D list JSON file (52 rows expected)")
    parser.add_argument(
        "--template",
        type=Path,
        default=DEFAULT_TEMPLATE,
        help=f"Template markdown path (default: {DEFAULT_TEMPLATE})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Master markdown output path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--init-template-only",
        action="store_true",
        help="Only verify template exists and print merge-ready guidance.",
    )
    return parser.parse_args()


def load_rows(path: Path) -> list[MatrixRow]:
    if not path.exists():
        raise FileNotFoundError(f"input file does not exist: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"{path} must be a JSON array")
    rows: list[MatrixRow] = []
    for i, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"{path}:{i} must be a JSON object")
        rows.append(MatrixRow.from_payload(item, path, i))
    return rows


def validate_counts(grouped: dict[str, list[MatrixRow]]) -> None:
    for key, expected in DEFAULT_COUNTS.items():
        actual = len(grouped.get(key, []))
        if actual != expected:
            raise ValueError(f"list {key} row count mismatch: expected={expected}, actual={actual}")


def validate_unique_ids(rows: Iterable[MatrixRow]) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for row in rows:
        if row.row_id in seen:
            duplicates.add(row.row_id)
        seen.add(row.row_id)
    if duplicates:
        dup_text = ", ".join(sorted(duplicates))
        raise ValueError(f"duplicate id detected: {dup_text}")


def render_master(rows: list[MatrixRow]) -> str:
    generated_at = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
    by_status: dict[str, int] = {}
    for row in rows:
        by_status[row.status] = by_status.get(row.status, 0) + 1
    status_lines = "\n".join(
        f"| `status={_escape_md(status)}` | {count} |"
        for status, count in sorted(by_status.items(), key=lambda item: item[0])
    ) or "| `status=none` | 0 |"

    header = [
        "# Matrix-Compiler Master Table (49/70/68/52)",
        "",
        f"> Generated at: {generated_at}",
        f"> Total rows: {len(rows)}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
        "| Total target rows | 239 |",
        f"| Merged rows | {len(rows)} |",
        status_lines,
        "",
        "## Row Matrix",
        "",
        "| list | id | issue | status | evidence_path | fix_ref |",
        "|---|---|---|---|---|---|",
    ]
    body = [row.markdown_row() for row in rows]
    return "\n".join(header + body) + "\n"


def main() -> int:
    args = parse_args()
    if not args.template.exists():
        raise FileNotFoundError(f"template file does not exist: {args.template}")

    if args.init_template_only:
        print("[matrix-compiler] template is ready.")
        print(f"[matrix-compiler] template={args.template}")
        print(
            "[matrix-compiler] example merge command:\n"
            "  python3 scripts/matrix_compiler_merge.py "
            "--a <A.json> --b <B.json> --c <C.json> --d <D.json>"
        )
        return 0

    missing_inputs = [k for k, v in {"--a": args.a, "--b": args.b, "--c": args.c, "--d": args.d}.items() if v is None]
    if missing_inputs:
        raise ValueError(f"missing required input arguments: {', '.join(missing_inputs)}")

    rows_a = load_rows(args.a)
    rows_b = load_rows(args.b)
    rows_c = load_rows(args.c)
    rows_d = load_rows(args.d)

    grouped = {"A": rows_a, "B": rows_b, "C": rows_c, "D": rows_d}
    validate_counts(grouped)

    merged = rows_a + rows_b + rows_c + rows_d
    validate_unique_ids(merged)

    content = render_master(merged)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    print(f"[matrix-compiler] merge done: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
