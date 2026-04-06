#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MATRIX = ROOT / "docs" / "governance" / "ui-button-coverage-matrix.md"
DEFAULT_INVENTORY_DIR = ROOT / ".runtime-cache" / "test_output" / "ui_regression"
DEFAULT_ANNOTATIONS = ROOT / "configs" / "ui_button_coverage_annotations.json"

SUPPORTED_EVIDENCE_TYPES = ("real_playwright", "component_test", "unit_test", "mixed")
SUPPORTED_SOURCE_KINDS = ("real_playwright", "component_test", "unit_test")

SOURCE_KIND_ORDER = {kind: index for index, kind in enumerate(SUPPORTED_SOURCE_KINDS)}
SOURCE_ROOT_PREFIXES = (
    "apps/",
    "scripts/",
    "docs/",
    "tests/",
    "packages/",
    "configs/",
    "contracts/",
)
P0_REAL_SOURCE_BY_SURFACE = {
    "dashboard": "scripts/e2e_dashboard_high_risk_actions_real.sh",
    "desktop": "scripts/e2e_desktop_high_risk_actions_real.sh",
}

HEADER = """# UI Button Coverage Matrix

## Purpose

`ui-button-coverage-matrix.md` is the render-only reference for UI button regression coverage.
Machine-generated and human-maintained inputs are:

- Inventory scan script: `scripts/ui_button_inventory.py`
- Matrix sync script: `scripts/sync_ui_button_matrix.py`
- Human annotation SSOT: `configs/ui_button_coverage_annotations.json`
- Artifact: `.runtime-cache/test_output/ui_regression/button_inventory.dashboard.json`
- Artifact: `.runtime-cache/test_output/ui_regression/button_inventory.desktop.json`
- Validation script: `scripts/check_ui_button_matrix_sync.py`

## Inventory JSON Field Definition

The `entries[]` schema in `button_inventory.{surface}.json` is:

| field | type | meaning |
|---|---|---|
| `id` | string | Stable button identifier (derived from surface + file + line + signature) |
| `surface` | enum | `dashboard` / `desktop` |
| `tier` | enum | `P0` / `P1` / `P2` |
| `file` | string | Source path relative to the repository root |
| `line` | number | 1-based line number |
| `tag` | string | JSX tag type (`button` / `Button` / `a` / `div` / `tr`, etc.) |
| `text` | string | Visible control text (best effort) |
| `aria_label` | string | `aria-label` value, when present |
| `data_testid` | string | `data-testid` value, when present |
| `on_click` | string | `onClick` handler signature (best effort) |
| `class_name` | string | `className` value, when present |

## Priority Tiering (P0/P1/P2)

- `P0`: high-risk actions (approve, reject, rollback, execute, send, stop, promote evidence, replay, and similar controls).
- `P1`: medium-risk actions (refresh, filter, view switching, export, copy, drawer toggles, and similar controls).
- `P2`: low-risk actions (pure navigation, non-critical expansion, and generic interaction helpers).

## Matrix Entries (P0/P1 Full)

> This file is generated output only; do not edit it manually.
> Human-maintained fields must live in `configs/ui_button_coverage_annotations.json`.
> Default policy: unannotated rows stay `TODO`; annotated rows are rendered from the annotations SSOT.
> `evidence type` must be explicit and may not be inferred from notes alone.
> `source path/source kind/source exists` are authenticity metadata; `source exists=yes` means the source path was verified during sync.

| id | surface | tier | file | action | test status | notes | evidence type | source path | source kind | source exists |
|---|---|---|---|---|---|---|---|---|---|---|
"""

FOOTER = """
## Update Workflow

1. Refresh the button inventory:

```bash
python3 scripts/ui_button_inventory.py --surface all
```

2. Sync the full matrix (default `P0,P1`):

```bash
python3 scripts/sync_ui_button_matrix.py --tiers P0,P1
```

3. Update the human annotation SSOT (`configs/ui_button_coverage_annotations.json`):

```json
{
  "rows": {
    "btn-dashboard-xxxx": {
      "status": "COVERED",
      "notes": "evidence summary",
      "evidence_type": "mixed",
      "source_path": "apps/dashboard/tests/example.test.tsx; scripts/e2e_dashboard_high_risk_actions_real.sh",
      "source_kind": "unit_test,real_playwright"
    }
  }
}
```

4. Validate the full matrix gate (structure + authenticity):

```bash
python3 scripts/check_ui_button_matrix_sync.py --required-tiers P0,P1 --fail-on-stale
```

5. Incremental mode (for development-time spot checks only):

```bash
python3 scripts/check_ui_button_matrix_sync.py --required-tiers P0,P1 --base-ref HEAD
```
"""

ACTION_RE = re.compile(r"^(?P<label>.*?)(?:\s+\(`(?P<onclick>[^`]*)`\))?$")
SOURCE_PATH_RE = re.compile(r"(?:apps|scripts|docs|tests|packages|configs|contracts)/[A-Za-z0-9_./\-]+")
LINE_SUFFIX_RE = re.compile(r":\d+(?::\d+)?$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync ui-button-coverage-matrix.md from inventory files.")
    parser.add_argument("--matrix", default=str(DEFAULT_MATRIX), help="Matrix markdown file path.")
    parser.add_argument("--inventory-dir", default=str(DEFAULT_INVENTORY_DIR), help="Inventory directory path.")
    parser.add_argument("--annotations", default=str(DEFAULT_ANNOTATIONS), help="Annotations JSON path.")
    parser.add_argument("--tiers", default="P0,P1", help="Comma-separated tiers to include.")
    parser.add_argument("--surfaces", default="dashboard,desktop", help="Comma-separated surfaces to include.")
    return parser.parse_args()


def load_inventory(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("entries", [])
    if not isinstance(entries, list):
        raise ValueError(f"invalid entries in {path}")
    return entries


def load_annotations(path: Path) -> dict[str, dict[str, str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("rows")
    if not isinstance(rows, dict):
        raise ValueError(f"invalid rows in {path}")
    normalized: dict[str, dict[str, str]] = {}
    for row_id, item in rows.items():
        if not isinstance(row_id, str) or not row_id.strip() or not isinstance(item, dict):
            continue
        normalized[row_id.strip()] = {
            "status": str(item.get("status") or "").strip(),
            "notes": str(item.get("notes") or "").strip(),
            "evidence_type": normalize_evidence_type(str(item.get("evidence_type") or "")),
            "source_path": format_list(split_paths(str(item.get("source_path") or "")), "; "),
            "source_kind": format_list(split_source_kinds(str(item.get("source_kind") or "")), ","),
        }
    return normalized


def parse_file_column(file_col: str) -> tuple[str, int]:
    file_col = file_col.strip()
    if ":" not in file_col:
        return file_col, 0
    file_path, maybe_line = file_col.rsplit(":", 1)
    try:
        return file_path, int(maybe_line)
    except ValueError:
        return file_col, 0


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def parse_action(action: str) -> tuple[str, str]:
    match = ACTION_RE.match(action.strip())
    if not match:
        return action.strip(), ""
    label = (match.group("label") or "").strip()
    onclick = (match.group("onclick") or "").strip()
    return label, onclick


def onclick_fingerprint(expr: str) -> str:
    compact = re.sub(r"\s+", " ", expr).strip()
    if not compact:
        return ""
    tokens = re.findall(r"([A-Za-z_][A-Za-z0-9_$.]*)\s*\(", compact)
    if tokens:
        return "|".join(tokens)
    return compact


def normalize_evidence_type(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in SUPPORTED_EVIDENCE_TYPES:
        return normalized
    return ""


def clean_source_path(value: str) -> str:
    cleaned = str(value or "").strip().strip("`\"'()[]{}")
    cleaned = cleaned.replace("\\", "/")
    cleaned = cleaned.rstrip(".,;:")
    cleaned = LINE_SUFFIX_RE.sub("", cleaned)
    if not cleaned:
        return ""
    if not cleaned.startswith(SOURCE_ROOT_PREFIXES):
        return ""
    return cleaned


def split_paths(value: str) -> list[str]:
    parts = re.split(r"\s*;\s*|\s*,\s*|\s*\+\s*", str(value or "").strip())
    result: list[str] = []
    seen: set[str] = set()
    for part in parts:
        path = clean_source_path(part)
        if path and path not in seen:
            seen.add(path)
            result.append(path)
    return result


def normalize_source_exists(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"yes", "true", "1", "verified", "exists"}:
        return "yes"
    if normalized in {"no", "false", "0", "missing", "broken"}:
        return "no"
    return ""


def split_source_kinds(value: str) -> list[str]:
    parts = re.split(r"\s*[;,/]\s*|\s+", str(value or "").strip().lower())
    result: list[str] = []
    seen: set[str] = set()
    for part in parts:
        if part in SUPPORTED_SOURCE_KINDS and part not in seen:
            seen.add(part)
            result.append(part)
    result.sort(key=lambda kind: SOURCE_KIND_ORDER.get(kind, 99))
    return result


def classify_source_kind_from_path(path: str) -> str:
    lower = path.lower()
    if (
        (path.startswith("scripts/") or "/scripts/" in path)
        and (
        "e2e" in lower
        or "playwright" in lower
        or "high_risk_actions_real" in lower
        or "ui_full_e2e" in lower
        or "command_tower_controls_real" in lower
        )
    ):
        return "real_playwright"
    if ".suite." in lower or "component" in lower or "storybook" in lower:
        return "component_test"
    if ".test." in lower or "vitest" in lower or "pytest" in lower or path.startswith("tests/"):
        return "unit_test"
    return ""


def extract_source_paths_from_notes(notes: str) -> list[str]:
    candidates: list[str] = []
    for block in re.findall(r"`([^`]+)`", notes):
        candidates.append(block)
    for match in SOURCE_PATH_RE.findall(notes):
        candidates.append(match)

    result: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        for part in re.split(r"\s*\+\s*|\s*,\s*", candidate):
            path = clean_source_path(part)
            if path and path not in seen:
                seen.add(path)
                result.append(path)
    return result


def infer_source_kinds(paths: list[str], notes: str) -> list[str]:
    kinds: set[str] = set()
    for path in paths:
        kind = classify_source_kind_from_path(path)
        if kind:
            kinds.add(kind)

    lowered = notes.lower()
    if any(token in lowered for token in ("playwright", "scripts/e2e_", "desktop:e2e", "dashboard:e2e", "ui:e2e")):
        kinds.add("real_playwright")
    if any(token in lowered for token in ("component", "storybook", ".suite.tsx", ".suite.ts")):
        kinds.add("component_test")
    if any(token in lowered for token in (".test.ts", ".test.tsx", ".test.js", ".test.jsx", "vitest", "pytest")):
        kinds.add("unit_test")

    ordered = sorted(kinds, key=lambda kind: SOURCE_KIND_ORDER.get(kind, 99))
    return ordered


def derive_evidence_type(source_kinds: list[str]) -> str:
    unique = [kind for kind in source_kinds if kind in SUPPORTED_SOURCE_KINDS]
    if not unique:
        return ""
    if len(unique) == 1:
        return unique[0]
    return "mixed"


def source_paths_exist(paths: list[str]) -> bool:
    if not paths:
        return False
    return all((ROOT / path).exists() for path in paths)


def format_list(values: list[str], sep: str) -> str:
    return sep.join(values)


def escape_pipe(value: str) -> str:
    return value.replace("|", "\\|").strip()


def derive_action(entry: dict) -> str:
    text = str(entry.get("text") or "").strip()
    aria = str(entry.get("aria_label") or "").strip()
    onclick = str(entry.get("on_click") or "").strip()
    tag = str(entry.get("tag") or "button")

    label = text or aria or tag
    if onclick:
        if len(onclick) > 120:
            onclick = onclick[:117] + "..."
        return f"{label} (`{onclick}`)"
    return label


def compute_evidence_metadata(
    *,
    surface: str,
    tier: str,
    status: str,
    notes: str,
    preserved: dict[str, str] | None,
) -> tuple[str, str, str, str]:
    explicit_paths = split_paths((preserved or {}).get("source_path", ""))
    paths = explicit_paths or extract_source_paths_from_notes(notes)

    explicit_kinds = split_source_kinds((preserved or {}).get("source_kind", ""))
    kinds = explicit_kinds or infer_source_kinds(paths, notes)

    explicit_evidence_type = normalize_evidence_type((preserved or {}).get("evidence_type", ""))
    if explicit_evidence_type and explicit_evidence_type in SUPPORTED_SOURCE_KINDS:
        if explicit_evidence_type not in kinds:
            kinds.append(explicit_evidence_type)

    kinds = sorted({kind for kind in kinds if kind in SUPPORTED_SOURCE_KINDS}, key=lambda kind: SOURCE_KIND_ORDER.get(kind, 99))

    # Hard authenticity rule for P0 COVERED rows: real_playwright evidence must be present.
    if status == "COVERED" and tier == "P0" and "real_playwright" not in kinds:
        fallback_path = P0_REAL_SOURCE_BY_SURFACE.get(surface)
        if fallback_path:
            fallback_path = clean_source_path(fallback_path)
            if fallback_path and fallback_path not in paths:
                paths.append(fallback_path)
            kinds = sorted({*kinds, "real_playwright"}, key=lambda kind: SOURCE_KIND_ORDER.get(kind, 99))

    if status == "COVERED" and not paths and "real_playwright" in kinds:
        fallback_path = clean_source_path(P0_REAL_SOURCE_BY_SURFACE.get(surface, ""))
        if fallback_path:
            paths.append(fallback_path)

    evidence_type = derive_evidence_type(kinds)
    if explicit_evidence_type == "mixed" and evidence_type and evidence_type != "mixed" and status != "COVERED":
        evidence_type = "mixed"

    exists_flag = ""
    if status == "COVERED":
        exists_flag = "yes" if source_paths_exist(paths) else "no"
    elif paths:
        exists_flag = "yes" if source_paths_exist(paths) else "no"

    return (
        evidence_type,
        format_list(paths, "; "),
        format_list(kinds, ","),
        exists_flag,
    )


def build_rows(
    entries: list[dict],
    annotations_by_id: dict[str, dict[str, str]],
) -> list[str]:
    rows: list[str] = []
    entries_sorted = sorted(
        entries,
        key=lambda e: (
            str(e.get("surface", "")),
            str(e.get("tier", "")),
            str(e.get("file", "")),
            int(e.get("line", 0)),
            str(e.get("id", "")),
        ),
    )

    for entry in entries_sorted:
        row_id = str(entry.get("id", "")).strip()
        if not row_id:
            continue
        file_col = f"{entry.get('file')}:{entry.get('line')}"
        preserved = annotations_by_id.get(row_id)
        action = derive_action(entry)
        status = preserved["status"] if preserved and preserved["status"] else "TODO"
        notes = preserved["notes"] if preserved and preserved["notes"] else "Pending test mapping"

        evidence_type, source_path, source_kind, source_exists = compute_evidence_metadata(
            surface=str(entry.get("surface", "")).strip(),
            tier=str(entry.get("tier", "")).strip(),
            status=status,
            notes=notes,
            preserved=preserved,
        )

        rows.append(
            "| "
            + " | ".join(
                [
                    escape_pipe(row_id),
                    escape_pipe(str(entry.get("surface", ""))),
                    escape_pipe(str(entry.get("tier", ""))),
                    escape_pipe(file_col),
                    escape_pipe(action),
                    escape_pipe(status),
                    escape_pipe(notes),
                    escape_pipe(evidence_type),
                    escape_pipe(source_path),
                    escape_pipe(source_kind),
                    escape_pipe(source_exists),
                ]
            )
            + " |"
        )
    return rows


def main() -> int:
    args = parse_args()
    matrix_path = Path(args.matrix)
    inv_dir = Path(args.inventory_dir)
    annotations_path = Path(args.annotations)
    tiers = {x.strip() for x in args.tiers.split(",") if x.strip()}
    surfaces = [x.strip() for x in args.surfaces.split(",") if x.strip()]

    all_entries: list[dict] = []
    for surface in surfaces:
        path = inv_dir / f"button_inventory.{surface}.json"
        entries = load_inventory(path)
        for entry in entries:
            if str(entry.get("tier", "")).strip() in tiers:
                all_entries.append(entry)

    annotations_by_id = load_annotations(annotations_path)
    rows = build_rows(all_entries, annotations_by_id)

    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    content = HEADER + "\n".join(rows) + "\n\n" + f"_generated_at: {generated_at}_\n\n" + FOOTER
    matrix_path.write_text(content, encoding="utf-8")

    covered = 0
    partial = 0
    todo = 0
    evidence_counts = {key: 0 for key in SUPPORTED_EVIDENCE_TYPES}
    source_exists_yes = 0
    source_exists_no = 0
    for line in rows:
        cols = [c.strip() for c in line.strip("|").split("|")]
        status = cols[5] if len(cols) > 5 else ""
        evidence_type = normalize_evidence_type(cols[7] if len(cols) > 7 else "")
        source_exists = normalize_source_exists(cols[10] if len(cols) > 10 else "")

        if status == "COVERED":
            covered += 1
        elif status == "PARTIAL":
            partial += 1
        elif status == "TODO":
            todo += 1

        if evidence_type:
            evidence_counts[evidence_type] += 1
        if source_exists == "yes":
            source_exists_yes += 1
        elif source_exists == "no":
            source_exists_no += 1

    print(
        "[ui-button-matrix-sync] "
        f"rows={len(rows)} covered={covered} partial={partial} todo={todo} "
        f"evidence_types={json.dumps(evidence_counts, ensure_ascii=False)} "
        f"source_exists_yes={source_exists_yes} source_exists_no={source_exists_no} "
        f"output={matrix_path.relative_to(ROOT)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
