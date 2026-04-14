#!/usr/bin/env python3
"""
Detect tests related to changed files for incremental testing.

This script analyzes git diff to find changed Python files and maps them
to their corresponding test files. It supports:
1. Direct test file changes (test_*.py, *_test.py)
2. Source file changes mapped to test files
3. Import dependency analysis for affected tests

Usage:
    python3 scripts/detect_changed_tests.py --base-ref origin/main --test-dir apps/orchestrator/tests
    python3 scripts/detect_changed_tests.py --changed-files "file1.py,file2.py" --test-dir apps/orchestrator/tests
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Set, List, Dict, Optional


@dataclass
class IncrementalTestResult:
    """Result of incremental test detection."""
    changed_files: List[str] = field(default_factory=list)
    changed_test_files: List[str] = field(default_factory=list)
    affected_test_files: List[str] = field(default_factory=list)
    all_test_files_to_run: List[str] = field(default_factory=list)
    should_run_all: bool = False
    reason: str = ""
    
    def to_dict(self) -> dict:
        return {
            "changed_files": self.changed_files,
            "changed_test_files": self.changed_test_files,
            "affected_test_files": self.affected_test_files,
            "all_test_files_to_run": self.all_test_files_to_run,
            "should_run_all": self.should_run_all,
            "reason": self.reason,
        }


def get_changed_files_from_git(base_ref: str, head_ref: str = "HEAD") -> List[str]:
    """Get list of changed files from git diff."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=ACMR", f"{base_ref}...{head_ref}"],
            capture_output=True,
            text=True,
            check=True,
        )
        files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
        return files
    except subprocess.CalledProcessError:
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", "--diff-filter=ACMR", base_ref, head_ref],
                capture_output=True,
                text=True,
                check=True,
            )
            files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
            return files
        except subprocess.CalledProcessError as e:
            print(f"⚠️ [detect-changed-tests] git diff failed: {e}", file=sys.stderr)
            return []


def get_staged_files() -> List[str]:
    """Get list of staged files."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "--cached", "--diff-filter=ACMR"],
            capture_output=True,
            text=True,
            check=True,
        )
        files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
        return files
    except subprocess.CalledProcessError:
        return []


def get_unstaged_files() -> List[str]:
    """Get list of unstaged modified files."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=ACMR"],
            capture_output=True,
            text=True,
            check=True,
        )
        files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
        return files
    except subprocess.CalledProcessError:
        return []


def is_test_file(filepath: str) -> bool:
    """Check if a file is a test file."""
    name = Path(filepath).name
    return (
        name.startswith("test_") and name.endswith(".py")
    ) or (
        name.endswith("_test.py")
    ) or (
        "/tests/" in filepath and name.endswith(".py")
    )


def is_python_file(filepath: str) -> bool:
    """Check if a file is a Python file."""
    return filepath.endswith(".py")


def source_to_test_path(source_path: str, test_dir: str) -> List[str]:
    """
    Map a source file to potential test file paths.
    
    Examples:
        apps/orchestrator/src/openvibecoding_orch/scheduler.py 
        -> apps/orchestrator/tests/test_scheduler.py
        
        apps/orchestrator/src/openvibecoding_orch/api/routes_runs.py
        -> apps/orchestrator/tests/test_routes_runs.py
        -> apps/orchestrator/tests/api/test_routes_runs.py
    """
    candidates = []
    source_name = Path(source_path).stem
    
    test_name = f"test_{source_name}.py"
    candidates.append(str(Path(test_dir) / test_name))
    
    if "/src/" in source_path:
        relative_path = source_path.split("/src/", 1)[1]
        relative_dir = str(Path(relative_path).parent)
        if relative_dir and relative_dir != ".":
            candidates.append(str(Path(test_dir) / relative_dir / test_name))
    
    if "/" in source_path:
        parts = source_path.split("/")
        for i in range(len(parts) - 1, 0, -1):
            subdir = "/".join(parts[i:-1])
            if subdir:
                candidates.append(str(Path(test_dir) / subdir / test_name))
    
    return candidates


def extract_imports_from_file(filepath: str) -> Set[str]:
    """Extract imported module names from a Python file."""
    imports = set()
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module.split(".")[0])
    except (SyntaxError, FileNotFoundError, UnicodeDecodeError):
        pass
    return imports


def find_tests_importing_module(test_dir: str, module_name: str) -> List[str]:
    """Find test files that import a specific module."""
    affected_tests = []
    test_path = Path(test_dir)
    if not test_path.exists():
        return affected_tests
    
    for test_file in test_path.rglob("test_*.py"):
        imports = extract_imports_from_file(str(test_file))
        if module_name in imports:
            affected_tests.append(str(test_file))
    
    for test_file in test_path.rglob("*_test.py"):
        imports = extract_imports_from_file(str(test_file))
        if module_name in imports:
            affected_tests.append(str(test_file))
    
    return affected_tests


def should_trigger_full_test(changed_files: List[str]) -> tuple[bool, str]:
    """
    Determine if changes should trigger a full test run.
    
    Returns (should_run_all, reason)
    """
    critical_patterns = [
        r"^pyproject\.toml$",
        r"^setup\.py$",
        r"^setup\.cfg$",
        r"^requirements.*\.txt$",
        r"^uv\.lock$",
        r"^\.pre-commit-config\.yaml$",
        r"^conftest\.py$",
        r".*/conftest\.py$",
        r"^pytest\.ini$",
        r"^tox\.ini$",
        r"^scripts/test\.sh$",
        r"^scripts/ci\.sh$",
        r"^configs/.*\.json$",
    ]
    
    for filepath in changed_files:
        for pattern in critical_patterns:
            if re.match(pattern, filepath):
                return True, f"Critical file changed: {filepath}"
    
    return False, ""


def detect_incremental_tests(
    changed_files: List[str],
    test_dir: str,
    src_dir: Optional[str] = None,
) -> IncrementalTestResult:
    """
    Detect which tests should run based on changed files.
    """
    result = IncrementalTestResult()
    result.changed_files = changed_files
    
    if not changed_files:
        result.reason = "No changed files detected"
        return result
    
    should_all, reason = should_trigger_full_test(changed_files)
    if should_all:
        result.should_run_all = True
        result.reason = reason
        return result
    
    python_files = [f for f in changed_files if is_python_file(f)]
    if not python_files:
        result.reason = "No Python files changed"
        return result
    
    test_files_changed = set()
    source_files_changed = set()
    
    for filepath in python_files:
        if is_test_file(filepath):
            if Path(filepath).exists():
                test_files_changed.add(filepath)
        else:
            source_files_changed.add(filepath)
    
    result.changed_test_files = sorted(test_files_changed)
    
    affected_tests = set()
    
    for source_file in source_files_changed:
        candidates = source_to_test_path(source_file, test_dir)
        for candidate in candidates:
            if Path(candidate).exists():
                affected_tests.add(candidate)
        
        module_name = Path(source_file).stem
        if src_dir:
            relative = source_file.replace(src_dir, "").lstrip("/")
            module_parts = relative.replace("/", ".").replace(".py", "")
            for part in module_parts.split("."):
                if part:
                    affected_tests.update(find_tests_importing_module(test_dir, part))
        else:
            affected_tests.update(find_tests_importing_module(test_dir, module_name))
    
    result.affected_test_files = sorted(affected_tests - test_files_changed)
    
    all_tests = test_files_changed | affected_tests
    result.all_test_files_to_run = sorted(all_tests)
    
    if not result.all_test_files_to_run:
        result.reason = "No related tests found for changed files"
    else:
        result.reason = f"Found {len(result.all_test_files_to_run)} test files to run"
    
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Detect tests related to changed files for incremental testing"
    )
    parser.add_argument(
        "--base-ref",
        default="origin/main",
        help="Base git ref for comparison (default: origin/main)",
    )
    parser.add_argument(
        "--head-ref",
        default="HEAD",
        help="Head git ref for comparison (default: HEAD)",
    )
    parser.add_argument(
        "--test-dir",
        default="apps/orchestrator/tests",
        help="Directory containing tests (default: apps/orchestrator/tests)",
    )
    parser.add_argument(
        "--src-dir",
        default="apps/orchestrator/src",
        help="Directory containing source code (default: apps/orchestrator/src)",
    )
    parser.add_argument(
        "--changed-files",
        help="Comma-separated list of changed files (overrides git diff)",
    )
    parser.add_argument(
        "--mode",
        choices=["git-diff", "staged", "unstaged", "all-local"],
        default="git-diff",
        help="Mode for detecting changed files",
    )
    parser.add_argument(
        "--output",
        choices=["json", "files", "pytest-args"],
        default="pytest-args",
        help="Output format",
    )
    parser.add_argument(
        "--fallback-all",
        action="store_true",
        help="If no incremental tests found, output flag to run all tests",
    )
    
    args = parser.parse_args()
    
    if args.changed_files:
        changed_files = [f.strip() for f in args.changed_files.split(",") if f.strip()]
    elif args.mode == "git-diff":
        changed_files = get_changed_files_from_git(args.base_ref, args.head_ref)
    elif args.mode == "staged":
        changed_files = get_staged_files()
    elif args.mode == "unstaged":
        changed_files = get_unstaged_files()
    elif args.mode == "all-local":
        changed_files = list(set(get_staged_files() + get_unstaged_files()))
    else:
        changed_files = []
    
    result = detect_incremental_tests(
        changed_files=changed_files,
        test_dir=args.test_dir,
        src_dir=args.src_dir,
    )
    
    if args.output == "json":
        print(json.dumps(result.to_dict(), indent=2))
    elif args.output == "files":
        if result.should_run_all:
            print("__ALL__")
        elif result.all_test_files_to_run:
            for f in result.all_test_files_to_run:
                print(f)
        elif args.fallback_all:
            print("__ALL__")
        else:
            print("__NONE__")
    elif args.output == "pytest-args":
        if result.should_run_all:
            print(args.test_dir)
        elif result.all_test_files_to_run:
            print(" ".join(result.all_test_files_to_run))
        elif args.fallback_all:
            print(args.test_dir)
        else:
            print("__SKIP__")
    
    if result.should_run_all:
        sys.exit(0)
    elif result.all_test_files_to_run:
        sys.exit(0)
    elif args.fallback_all:
        sys.exit(0)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
