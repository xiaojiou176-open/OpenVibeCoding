#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shlex
from pathlib import Path


def _compile(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


ENV_FLAKY_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("TIMEOUT", _compile(r"timeout|timed out|time out|deadline exceeded")),
    ("NETWORK_IO", _compile(r"econnreset|enotfound|eai_again|connection reset|temporary failure in name resolution")),
    ("NETWORK_REFUSED", _compile(r"econnrefused|connection refused")),
    ("LOCK_CONTENTION", _compile(r"stale lock|\.next/dev/lock|lock with active .* process")),
]

PRODUCT_REGRESSION_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("ASSERTION_FAILURE", _compile(r"assertionerror|expect\(|\bfailed\b.*::|=+ failures =+")),
    ("UNIT_TEST_FAILURE", _compile(r"\btest failure\b|\bpytest\b.*\bfailed\b")),
    ("UI_CHECK_FAILURE", _compile(r"one or more checks failed|check failed")),
    ("COVERAGE_REGRESSION", _compile(r"required test coverage .* not reached|coverage gate")),
]


def _first_match_line(lines: list[str], pattern: re.Pattern[str]) -> str:
    for line in reversed(lines):
        if pattern.search(line):
            return line.strip()
    return ""


def classify(log_path: Path, exit_code: int) -> dict[str, object]:
    if exit_code == 0:
        return {
            "failure_category": "none",
            "retry_recommended": False,
            "matched_rule": "PASS",
            "failure_signature": "",
        }

    lines: list[str] = []
    if log_path.exists():
        try:
            lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            lines = []
    tail = lines[-400:]
    text = "\n".join(tail)

    if exit_code == 124:
        return {
            "failure_category": "env_flaky",
            "retry_recommended": True,
            "matched_rule": "COMMAND_TIMEOUT_124",
            "failure_signature": "command exited with timeout status 124",
        }

    for name, pattern in ENV_FLAKY_RULES:
        if pattern.search(text):
            return {
                "failure_category": "env_flaky",
                "retry_recommended": True,
                "matched_rule": name,
                "failure_signature": _first_match_line(tail, pattern)[:280],
            }

    for name, pattern in PRODUCT_REGRESSION_RULES:
        if pattern.search(text):
            return {
                "failure_category": "product_regression",
                "retry_recommended": False,
                "matched_rule": name,
                "failure_signature": _first_match_line(tail, pattern)[:280],
            }

    return {
        "failure_category": "unknown_failure",
        "retry_recommended": False,
        "matched_rule": "UNCLASSIFIED",
        "failure_signature": (tail[-1].strip() if tail else "")[:280],
    }


def _shell_quote(value: object) -> str:
    return shlex.quote(str(value))


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify continuous governance step failure.")
    parser.add_argument("--log-file", required=True, help="Step log file path.")
    parser.add_argument("--exit-code", required=True, type=int, help="Step exit code.")
    parser.add_argument("--format", choices=("shell", "json"), default="shell")
    args = parser.parse_args()

    result = classify(Path(args.log_file), int(args.exit_code))
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False))
        return 0

    print(f"FAILURE_CATEGORY={_shell_quote(result['failure_category'])}")
    print(f"RETRY_RECOMMENDED={_shell_quote('1' if result['retry_recommended'] else '0')}")
    print(f"MATCHED_RULE={_shell_quote(result['matched_rule'])}")
    print(f"FAILURE_SIGNATURE={_shell_quote(result['failure_signature'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
