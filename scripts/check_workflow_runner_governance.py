#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


ALLOWED_RUNS_ON = {
    "runs-on: ubuntu-24.04",
}
FORBIDDEN_RUNNER_REGISTRATION_TOKENS = (
    "config.sh",
    "./config.sh",
    "run.sh",
    "./run.sh",
    "remove.sh",
    "./remove.sh",
)
WORKSPACE_RISK_KEYS = {
    "AGENT_TOOLSDIRECTORY",
    "RUNNER_TOOL_CACHE",
    "PRE_COMMIT_HOME",
    "PIP_CACHE_DIR",
    "PLAYWRIGHT_BROWSERS_PATH",
    "TMPDIR",
    "TEMP",
    "TMP",
}
WORKSPACE_RISK_HINTS = (".cache", "cache", "tool", "temp", "tmp", ".runtime-cache")
PINNED_ACTION_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*@[0-9a-f]{40}$")


def _iter_workflow_files(root: Path) -> list[Path]:
    workflows_dir = root / ".github" / "workflows"
    files = sorted(workflows_dir.glob("*.yml")) + sorted(workflows_dir.glob("*.yaml"))
    return [path for path in files if path.is_file()]


def _is_comment_or_blank(line: str) -> bool:
    stripped = line.strip()
    return not stripped or stripped.startswith("#")


def _line_indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _collect_runs_on_violations(path: Path, lines: list[str]) -> list[str]:
    violations: list[str] = []
    for lineno, raw in enumerate(lines, start=1):
        if _is_comment_or_blank(raw):
            continue
        stripped = raw.strip()
        if not stripped.startswith("runs-on:"):
            continue
        if stripped not in ALLOWED_RUNS_ON:
            allowed = " or ".join(f"`{item}`" for item in sorted(ALLOWED_RUNS_ON))
            violations.append(
                f"{path}:{lineno}: runs-on must be exactly one of {allowed} (found `{stripped}`)"
            )
        lowered = stripped.lower()
        if "pool-core" in lowered or "pool-spot" in lowered:
            violations.append(f"{path}:{lineno}: runs-on must not bind runner names directly")
    return violations


def _collect_action_pinning_violations(path: Path, lines: list[str]) -> list[str]:
    violations: list[str] = []
    for lineno, raw in enumerate(lines, start=1):
        if _is_comment_or_blank(raw):
            continue
        stripped = raw.strip()
        if stripped.startswith("- "):
            stripped = stripped[2:].strip()
        if not stripped.startswith("uses:"):
            continue
        action_ref = stripped.split("uses:", 1)[1].strip().split()[0]
        if action_ref.startswith("./") or action_ref.startswith("docker://"):
            continue
        if not PINNED_ACTION_RE.fullmatch(action_ref):
            violations.append(
                f"{path}:{lineno}: external GitHub Actions must pin a full commit SHA (found `{action_ref}`)"
            )
    return violations


def _collect_registration_violations(path: Path, lines: list[str]) -> list[str]:
    violations: list[str] = []
    for lineno, raw in enumerate(lines, start=1):
        if _is_comment_or_blank(raw):
            continue
        lowered = raw.lower()
        for token in FORBIDDEN_RUNNER_REGISTRATION_TOKENS:
            if token in lowered:
                violations.append(
                    f"{path}:{lineno}: workflow must not invoke runner registration command `{token}`"
                )
    return violations


def _collect_checkout_clean_violations(path: Path, lines: list[str]) -> list[str]:
    violations: list[str] = []
    for index, raw in enumerate(lines):
        if "uses: actions/checkout@" not in raw or _is_comment_or_blank(raw):
            continue
        checkout_lineno = index + 1
        base_indent = _line_indent(raw)
        found_clean_true = False
        for follow_index in range(index + 1, len(lines)):
            follow_raw = lines[follow_index]
            if _is_comment_or_blank(follow_raw):
                continue
            follow_indent = _line_indent(follow_raw)
            stripped = follow_raw.strip()
            if follow_indent < base_indent or (
                follow_indent == base_indent and stripped.startswith("- ")
            ):
                break
            if stripped == "clean: true":
                found_clean_true = True
                break
        if not found_clean_true:
            violations.append(
                f"{path}:{checkout_lineno}: actions/checkout must set `clean: true` explicitly"
            )
    return violations


def _collect_env_assignment_violations(path: Path, lines: list[str]) -> list[str]:
    violations: list[str] = []
    for lineno, raw in enumerate(lines, start=1):
        if _is_comment_or_blank(raw):
            continue
        if ":" not in raw:
            continue
        indent = _line_indent(raw)
        stripped = raw.strip()
        if indent == 0:
            continue
        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key or not value:
            continue
        lowered_value = value.lower()
        key_upper = key.upper()

        if key_upper in WORKSPACE_RISK_KEYS:
            if "github.workspace" in lowered_value:
                violations.append(
                    f"{path}:{lineno}: {key} must not point into github.workspace for cache/tool/temp state"
                )
            if "~/.cache" in lowered_value or ".cache/pre-commit" in lowered_value:
                violations.append(
                    f"{path}:{lineno}: {key} must not use shell-home cache paths inside workflow config"
                )

        if "github.workspace" in lowered_value and any(hint in key_upper.lower() or hint in lowered_value for hint in WORKSPACE_RISK_HINTS):
            violations.append(
                f"{path}:{lineno}: cache/tool/temp path must not live under github.workspace"
            )
    return violations


def check_root(root: Path) -> list[str]:
    violations: list[str] = []
    workflow_files = _iter_workflow_files(root)
    if not workflow_files:
        return [f"{root / '.github' / 'workflows'}: no workflow files found"]
    for path in workflow_files:
        lines = path.read_text(encoding="utf-8").splitlines()
        violations.extend(_collect_runs_on_violations(path, lines))
        violations.extend(_collect_registration_violations(path, lines))
        violations.extend(_collect_action_pinning_violations(path, lines))
        violations.extend(_collect_checkout_clean_violations(path, lines))
        violations.extend(_collect_env_assignment_violations(path, lines))
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description="Enforce hosted-first workflow governance.")
    parser.add_argument("--root", default=".", help="Repo root to scan")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    violations = check_root(root)
    if violations:
        print("❌ [workflow-runner-governance] detected workflow governance violations:")
        for item in violations:
            print(f"- {item}")
        return 1
    print("✅ [workflow-runner-governance] workflows satisfy runner/cache governance")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
