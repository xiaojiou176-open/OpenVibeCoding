#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / ".runtime-cache" / "test_output" / "ui_regression"

SURFACE_PATHS = {
    "dashboard": ROOT / "apps" / "dashboard",
    "desktop": ROOT / "apps" / "desktop",
}

START_TAG_RE = re.compile(r"<(?P<tag>button|Button|a|div|span|tr)\b", re.MULTILINE)
ONCLICK_RE = re.compile(r"\bonClick\s*=\s*\{(?P<value>[^}]*)\}")
ARIALABEL_RE = re.compile(r"\baria-label\s*=\s*(?P<q>\"[^\"]*\"|'[^']*')")
ROLE_BUTTON_RE = re.compile(r"\brole\s*=\s*(?P<q>\"button\"|'button')")
CLASSNAME_RE = re.compile(r"\bclassName\s*=\s*(?P<q>\"[^\"]*\"|'[^']*')")
DATA_TESTID_RE = re.compile(r"\bdata-testid\s*=\s*(?P<q>\"[^\"]*\"|'[^']*')")

IGNORE_PARTS = {
    "node_modules",
    ".next",
    "dist",
    "coverage",
    "build",
    "src-tauri/target",
}

UI_FILE_PATTERNS = ("*.tsx", "*.jsx", "*.ts", "*.js")

P0_KEYWORDS = {
    "run",
    "执行",
    "批准",
    "approve",
    "拒绝",
    "reject",
    "回滚",
    "rollback",
    "replay",
    "发送",
    "send",
    "god mode",
    "promote",
    "证据",
    "diff",
    "停止",
    "stop",
}

P1_KEYWORDS = {
    "刷新",
    "refresh",
    "重置",
    "reset",
    "过滤",
    "filter",
    "切换",
    "toggle",
    "展开",
    "收起",
    "查看",
    "tab",
    "live",
    "导出",
    "export",
    "复制",
    "copy",
    "返回",
}


@dataclass
class ButtonEntry:
    id: str
    surface: str
    tier: str
    file: str
    line: int
    tag: str
    text: str
    aria_label: str
    data_testid: str
    on_click: str
    class_name: str


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and ((value[0] == '"' and value[-1] == '"') or (value[0] == "'" and value[-1] == "'")):
        return value[1:-1]
    return value


def _normalize_text(value: str) -> str:
    collapsed = re.sub(r"\s+", " ", value)
    return collapsed.strip()


def _rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def _line_for_offset(content: str, offset: int) -> int:
    return content.count("\n", 0, offset) + 1


def _iter_files(surface: str) -> Iterable[Path]:
    base = SURFACE_PATHS[surface]
    files: list[Path] = []
    for pattern in UI_FILE_PATTERNS:
        files.extend(base.rglob(pattern))
    dedup = sorted(set(files))
    for file in dedup:
        rel = _rel(file)
        if any(part in rel for part in IGNORE_PARTS):
            continue
        if ".test." in file.name or ".spec." in file.name:
            continue
        yield file


def _extract_inner_text(content: str, end_index: int, tag: str) -> str:
    segment = content[end_index : end_index + 600]
    close_marker = f"</{tag}>"
    close_index = segment.find(close_marker)
    if close_index >= 0:
        raw = segment[:close_index]
    else:
        raw = segment[:220]
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = re.sub(r"\{[^{}]{0,160}\}", " ", raw)
    return _normalize_text(raw)


def _extract_opening_tag(content: str, start_index: int) -> tuple[str, int] | None:
    in_single_quote = False
    in_double_quote = False
    brace_depth = 0
    i = start_index
    while i < len(content):
        ch = content[i]
        if ch == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
        elif ch == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
        elif not in_single_quote and not in_double_quote:
            if ch == "{":
                brace_depth += 1
            elif ch == "}":
                brace_depth = max(0, brace_depth - 1)
            elif ch == ">" and brace_depth == 0:
                return content[start_index : i + 1], i + 1
        i += 1
    return None


def _compute_tier(file_rel: str, text: str, aria_label: str, on_click: str) -> str:
    signal = f"{file_rel} {text} {aria_label} {on_click}".lower()
    if any(keyword in signal for keyword in P0_KEYWORDS):
        return "P0"
    if any(keyword in signal for keyword in P1_KEYWORDS):
        return "P1"
    return "P2"


def _stable_id(surface: str, file_rel: str, line: int, tag: str, text: str, aria_label: str, on_click: str) -> str:
    basis = f"{surface}|{file_rel}|{line}|{tag}|{text}|{aria_label}|{on_click}".encode("utf-8")
    short = hashlib.sha1(basis).hexdigest()[:12]
    return f"btn-{surface}-{short}"


def scan_surface(surface: str) -> list[ButtonEntry]:
    entries: list[ButtonEntry] = []
    for file in _iter_files(surface):
        content = file.read_text(encoding="utf-8")
        file_rel = _rel(file)

        for match in START_TAG_RE.finditer(content):
            tag = match.group("tag")
            tag_open = _extract_opening_tag(content, match.start())
            if not tag_open:
                continue
            opening_tag, tag_end = tag_open
            attrs = opening_tag[len(tag) + 1 : -1]
            on_click_match = ONCLICK_RE.search(attrs)
            has_on_click = on_click_match is not None
            role_button = ROLE_BUTTON_RE.search(attrs) is not None

            if tag in {"button", "Button"}:
                clickable = True
            else:
                clickable = has_on_click and (role_button or tag in {"a", "tr", "div", "span"})

            if not clickable:
                continue

            aria_label_match = ARIALABEL_RE.search(attrs)
            class_name_match = CLASSNAME_RE.search(attrs)
            data_testid_match = DATA_TESTID_RE.search(attrs)

            line = _line_for_offset(content, match.start())
            text = _extract_inner_text(content, tag_end, tag)
            aria_label = _strip_quotes(aria_label_match.group("q")) if aria_label_match else ""
            data_testid = _strip_quotes(data_testid_match.group("q")) if data_testid_match else ""
            class_name = _strip_quotes(class_name_match.group("q")) if class_name_match else ""
            on_click = _normalize_text(on_click_match.group("value")) if on_click_match else ""
            tier = _compute_tier(file_rel, text, aria_label, on_click)

            entry_id = _stable_id(surface, file_rel, line, tag, text, aria_label, on_click)
            entries.append(
                ButtonEntry(
                    id=entry_id,
                    surface=surface,
                    tier=tier,
                    file=file_rel,
                    line=line,
                    tag=tag,
                    text=text,
                    aria_label=aria_label,
                    data_testid=data_testid,
                    on_click=on_click,
                    class_name=class_name,
                )
            )

    entries.sort(key=lambda item: (item.file, item.line, item.id))
    return entries


def write_output(surface: str, entries: list[ButtonEntry]) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "surface": surface,
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "count": len(entries),
        "entries": [asdict(entry) for entry in entries],
    }
    output = OUTPUT_DIR / f"button_inventory.{surface}.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inventory clickable UI elements for dashboard/desktop.")
    parser.add_argument(
        "--surface",
        choices=["dashboard", "desktop", "all"],
        default="all",
        help="Surface to scan. Default: all",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    targets = ["dashboard", "desktop"] if args.surface == "all" else [args.surface]

    for surface in targets:
        entries = scan_surface(surface)
        output = write_output(surface, entries)
        counts = {"P0": 0, "P1": 0, "P2": 0}
        for entry in entries:
            counts[entry.tier] += 1
        print(
            f"[ui-button-inventory] surface={surface} total={len(entries)} "
            f"P0={counts['P0']} P1={counts['P1']} P2={counts['P2']} output={output.relative_to(ROOT)}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
