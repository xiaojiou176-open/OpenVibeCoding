#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MAX_FILE_BYTES = 350_000
CODE_SUFFIXES = {
    ".bash",
    ".cjs",
    ".command",
    ".go",
    ".js",
    ".json",
    ".mjs",
    ".mts",
    ".py",
    ".rs",
    ".sh",
    ".swift",
    ".ts",
    ".tsx",
    ".zsh",
}
SKIP_DIRS = {
    ".git",
    ".next",
    ".runtime-cache",
    ".venv",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "out",
    "target",
}


@dataclass(frozen=True)
class Rule:
    name: str
    severity: str
    pattern: re.Pattern[str]
    reason: str


RULES = [
    Rule(
        name="killall",
        severity="HARD_BAN",
        pattern=re.compile(r"\bkillall\b"),
        reason="Broad app-name termination is forbidden.",
    ),
    Rule(
        name="pkill",
        severity="HARD_BAN",
        pattern=re.compile(r"\bpkill\b"),
        reason="Pattern-based process termination is forbidden.",
    ),
    Rule(
        name="killpg",
        severity="HARD_BAN",
        pattern=re.compile(r"\bkillpg\s*\("),
        reason="Process-group termination is forbidden.",
    ),
    Rule(
        name="negative_pid_signal",
        severity="HARD_BAN",
        pattern=re.compile(r"\b(?:process|os)\.kill\(\s*-\s*\d+"),
        reason="Negative PID signals can target process groups or broad process sets.",
    ),
    Rule(
        name="zero_pid_signal",
        severity="HARD_BAN",
        pattern=re.compile(r"\b(?:process|os)\.kill\(\s*0(?:\s*[,\)])"),
        reason="PID 0 signals can target the current process group.",
    ),
    Rule(
        name="loginwindow_reference",
        severity="HARD_BAN",
        pattern=re.compile(r"\bloginwindow\b"),
        reason="Host session control paths are forbidden in repo code.",
    ),
    Rule(
        name="force_quit_api",
        severity="HARD_BAN",
        pattern=re.compile(r"showForceQuitPanel|kAEShowApplicationWindow|aevt,apwn|CGSession"),
        reason="Force Quit and session APIs are forbidden.",
    ),
    Rule(
        name="system_events",
        severity="HARD_BAN",
        pattern=re.compile(r'tell application "System Events"'),
        reason="Desktop-wide System Events automation is forbidden in worker/test/orchestrator paths.",
    ),
    Rule(
        name="apple_script_quit",
        severity="HARD_BAN",
        pattern=re.compile(r'tell application(?: id)? .* to quit'),
        reason="AppleScript app quitting is forbidden in worker/test/orchestrator paths.",
    ),
    Rule(
        name="osascript",
        severity="REVIEW_REQUIRED",
        pattern=re.compile(r"\bosascript\b"),
        reason="AppleScript usage must stay read-only and product-specific.",
    ),
    Rule(
        name="detached_launch",
        severity="REVIEW_REQUIRED",
        pattern=re.compile(r"\bdetached\s*:"),
        reason="Detached launches need explicit repo-owned singleton justification.",
    ),
    Rule(
        name="start_new_session",
        severity="REVIEW_REQUIRED",
        pattern=re.compile(r"\bstart_new_session\s*=\s*True\b"),
        reason="Detached process-session launches need explicit repo-owned lifecycle review.",
    ),
]


def iter_scan_files(root: Path):
    self_path = Path(__file__).resolve()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.resolve() == self_path:
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix not in CODE_SUFFIXES:
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        yield path


def scan_path(path: Path) -> list[dict[str, object]]:
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []

    findings: list[dict[str, object]] = []
    for idx, line in enumerate(lines, start=1):
        for rule in RULES:
            if rule.pattern.search(line):
                findings.append(
                    {
                        "severity": rule.severity,
                        "rule": rule.name,
                        "reason": rule.reason,
                        "path": str(path),
                        "line": idx,
                        "text": line.strip(),
                    }
                )
    return findings


def print_findings(findings: list[dict[str, object]]) -> None:
    if not findings:
        print("No host-process risk findings detected.")
        return

    for severity in ("HARD_BAN", "REVIEW_REQUIRED"):
        scoped = [finding for finding in findings if finding["severity"] == severity]
        if not scoped:
            continue
        print(f"\n[{severity}] {len(scoped)} hit(s)")
        for finding in scoped:
            print(
                f"- {finding['path']}:{finding['line']} "
                f"[{finding['rule']}] {finding['text']}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scan CortexPilot for host-process safety risks."
    )
    parser.add_argument(
        "--root",
        default=str(ROOT),
        help="Repository root to scan. Defaults to the parent of this script.",
    )
    parser.add_argument(
        "--fail-on-review",
        action="store_true",
        help="Return non-zero if REVIEW_REQUIRED findings exist.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    findings: list[dict[str, object]] = []
    scanned_files = 0

    for path in iter_scan_files(root):
        scanned_files += 1
        findings.extend(scan_path(path))

    hard_bans = [finding for finding in findings if finding["severity"] == "HARD_BAN"]
    reviews = [finding for finding in findings if finding["severity"] == "REVIEW_REQUIRED"]

    print("Host Process Risk Scan")
    print(f"- root: {root}")
    print(f"- scanned_files: {scanned_files}")
    print(f"- hard_ban_hits: {len(hard_bans)}")
    print(f"- review_required_hits: {len(reviews)}")
    print_findings(findings)

    if hard_bans:
        return 2
    if args.fail_on_review and reviews:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
