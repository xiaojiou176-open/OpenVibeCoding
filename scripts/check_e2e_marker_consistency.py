#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    test_name: str


def _is_pytest_mark_e2e(node: ast.AST) -> bool:
    current = node
    if isinstance(current, ast.Call):
        current = current.func
    if not isinstance(current, ast.Attribute):
        return False
    if current.attr != "e2e":
        return False
    mark = current.value
    return (
        isinstance(mark, ast.Attribute)
        and mark.attr == "mark"
        and isinstance(mark.value, ast.Name)
        and mark.value.id == "pytest"
    )


def _contains_e2e_marker(node: ast.AST | None) -> bool:
    if node is None:
        return False
    if _is_pytest_mark_e2e(node):
        return True
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return any(_contains_e2e_marker(elt) for elt in node.elts)
    return False


def _module_has_e2e_marker(tree: ast.Module) -> bool:
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in stmt.targets):
                return _contains_e2e_marker(stmt.value)
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and stmt.target.id == "pytestmark":
            return _contains_e2e_marker(stmt.value)
    return False


def _decorators_have_e2e(decorators: list[ast.expr]) -> bool:
    return any(_contains_e2e_marker(dec) for dec in decorators)


def _collect_violations(path: Path) -> list[Violation]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    module_marked = _module_has_e2e_marker(tree)
    violations: list[Violation] = []

    for stmt in tree.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and stmt.name.startswith("test_"):
            if not (module_marked or _decorators_have_e2e(stmt.decorator_list)):
                violations.append(Violation(path=path, line=stmt.lineno, test_name=stmt.name))
            continue

        if isinstance(stmt, ast.ClassDef):
            class_marked = module_marked or _decorators_have_e2e(stmt.decorator_list)
            for item in stmt.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name.startswith("test_"):
                    if not (class_marked or _decorators_have_e2e(item.decorator_list)):
                        violations.append(Violation(path=path, line=item.lineno, test_name=item.name))
    return violations


def _iter_test_files(e2e_root: Path) -> list[Path]:
    return sorted(path for path in e2e_root.rglob("test_*.py") if path.is_file())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail if tests under apps/orchestrator/tests/e2e are missing pytest.mark.e2e."
    )
    parser.add_argument(
        "--e2e-root",
        default="apps/orchestrator/tests/e2e",
        help="Root directory containing e2e tests (default: apps/orchestrator/tests/e2e).",
    )
    args = parser.parse_args()

    e2e_root = Path(args.e2e_root).resolve()
    if not e2e_root.exists():
        print(f"❌ [e2e-marker] e2e root does not exist: {e2e_root}")
        return 1

    files = _iter_test_files(e2e_root)
    if not files:
        print(f"❌ [e2e-marker] no test files found under: {e2e_root}")
        return 1

    violations: list[Violation] = []
    for path in files:
        try:
            violations.extend(_collect_violations(path))
        except SyntaxError as exc:
            print(f"❌ [e2e-marker] failed to parse {path}: {exc}")
            return 1
        except OSError as exc:
            print(f"❌ [e2e-marker] failed to read {path}: {exc}")
            return 1

    if violations:
        print("❌ [e2e-marker] missing pytest.mark.e2e on e2e tests:")
        for v in violations:
            print(f"  - {v.path}:{v.line} {v.test_name}")
        return 1

    print(f"✅ [e2e-marker] consistency check passed ({len(files)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
