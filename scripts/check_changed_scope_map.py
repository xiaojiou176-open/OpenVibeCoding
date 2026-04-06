#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import json
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"map_not_found:{path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"map_json_invalid:{path}:{exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("map_root_must_be_object")
    return data


def _validate_map(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    version = data.get("version")
    if version != 1:
        errors.append("version_must_be_1")

    backend_scope_globs = data.get("backend_scope_globs")
    if not isinstance(backend_scope_globs, list) or not all(
        isinstance(item, str) and item for item in backend_scope_globs
    ):
        errors.append("backend_scope_globs_must_be_non_empty_string_list")

    rules = data.get("rules")
    if not isinstance(rules, list) or not rules:
        errors.append("rules_must_be_non_empty_list")
    else:
        seen_rule_ids: set[str] = set()
        for idx, rule in enumerate(rules):
            if not isinstance(rule, dict):
                errors.append(f"rules[{idx}]_must_be_object")
                continue
            rule_id = rule.get("id")
            if not isinstance(rule_id, str) or not rule_id:
                errors.append(f"rules[{idx}].id_must_be_non_empty_string")
            elif rule_id in seen_rule_ids:
                errors.append(f"rules[{idx}].id_duplicate:{rule_id}")
            else:
                seen_rule_ids.add(rule_id)

            path_globs = rule.get("path_globs")
            if not isinstance(path_globs, list) or not path_globs or not all(
                isinstance(item, str) and item for item in path_globs
            ):
                errors.append(f"rules[{idx}].path_globs_invalid")

            tests = rule.get("tests")
            select_changed = rule.get("select_changed_test_file", False)
            if tests is None and not select_changed:
                errors.append(
                    f"rules[{idx}]_must_define_tests_or_select_changed_test_file"
                )
            if tests is not None and (
                not isinstance(tests, list)
                or not all(isinstance(item, str) and item for item in tests)
            ):
                errors.append(f"rules[{idx}].tests_invalid")
            if not isinstance(select_changed, bool):
                errors.append(f"rules[{idx}].select_changed_test_file_must_be_bool")

    fallback = data.get("fallback")
    if not isinstance(fallback, dict):
        errors.append("fallback_must_be_object")
    else:
        fallback_tests = fallback.get("tests", [])
        if not isinstance(fallback_tests, list) or not all(
            isinstance(item, str) and item for item in fallback_tests
        ):
            errors.append("fallback.tests_invalid")
        by_path_globs = fallback.get("by_path_globs", [])
        if not isinstance(by_path_globs, list):
            errors.append("fallback.by_path_globs_must_be_list")
        else:
            for idx, item in enumerate(by_path_globs):
                if not isinstance(item, dict):
                    errors.append(f"fallback.by_path_globs[{idx}]_must_be_object")
                    continue
                path_globs = item.get("path_globs")
                tests = item.get("tests")
                if not isinstance(path_globs, list) or not path_globs or not all(
                    isinstance(pattern, str) and pattern for pattern in path_globs
                ):
                    errors.append(f"fallback.by_path_globs[{idx}].path_globs_invalid")
                if not isinstance(tests, list) or not tests or not all(
                    isinstance(test, str) and test for test in tests
                ):
                    errors.append(f"fallback.by_path_globs[{idx}].tests_invalid")
        heuristic = fallback.get("orchestrator_source_heuristic", True)
        if not isinstance(heuristic, bool):
            errors.append("fallback.orchestrator_source_heuristic_must_be_bool")
    return errors


def _read_changed_files(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _matches_any(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def _existing_test(path: str, repo_root: Path) -> str | None:
    candidate = repo_root / path
    if candidate.is_file():
        return path
    return None


def _find_tests_by_glob(repo_root: Path, pattern: str) -> list[str]:
    return sorted(
        str(p.relative_to(repo_root))
        for p in repo_root.glob(pattern)
        if p.is_file()
    )


def _find_tests_by_import_token(repo_root: Path, token: str) -> list[str]:
    tests_root = repo_root / "apps/orchestrator/tests"
    if not tests_root.exists():
        return []
    matched: list[str] = []
    for path in tests_root.rglob("*.py"):
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if token in content:
            matched.append(str(path.relative_to(repo_root)))
    return sorted(matched)


def _source_heuristic(path: str, repo_root: Path) -> tuple[list[str], list[str]]:
    if not (path.startswith("apps/orchestrator/src/") and path.endswith(".py")):
        return [], []
    heuristic_reasons: list[str] = []
    selected: set[str] = set()
    module_rel = path[len("apps/orchestrator/src/") : -3]
    module_name = Path(module_rel).name
    module_dir = Path(module_rel).parent.name
    module_import = module_rel.replace("/", ".")

    if module_name and module_name != "__init__":
        heuristic_reasons.append("module_name_pattern")
        selected.update(
            _find_tests_by_glob(repo_root, f"apps/orchestrator/tests/test_{module_name}.py")
        )
        selected.update(
            _find_tests_by_glob(repo_root, f"apps/orchestrator/tests/test*{module_name}*.py")
        )

    if module_import:
        import_hits = _find_tests_by_import_token(repo_root, module_import)
        if import_hits:
            heuristic_reasons.append("module_import_token")
            selected.update(import_hits)

    if module_name and module_dir and module_dir not in {".", "cortexpilot_orch"}:
        dir_hits = _find_tests_by_glob(
            repo_root,
            f"apps/orchestrator/tests/test*{module_dir}*{module_name}*.py",
        )
        if dir_hits:
            heuristic_reasons.append("module_dir_pattern")
            selected.update(dir_hits)

    return sorted(selected), heuristic_reasons


def _write_targets(path: Path, targets: list[str]) -> None:
    content = "\n".join(targets)
    if content:
        content += "\n"
    path.write_text(content, encoding="utf-8")


def _write_backend(path: Path, backend_paths: list[str]) -> None:
    content = "\n".join(backend_paths)
    if content:
        content += "\n"
    path.write_text(content, encoding="utf-8")


def _write_report_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_report_text(path: Path, payload: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append(f"status={payload.get('status', 'unknown')}")
    lines.append(f"reason={payload.get('reason', 'unknown')}")
    lines.append(f"changed_files_count={payload.get('changed_files_count', 0)}")
    lines.append(f"backend_files_count={payload.get('backend_files_count', 0)}")
    lines.append(f"selected_tests_count={len(payload.get('selected_tests', []))}")
    lines.append("matched_rules:")
    for rule in payload.get("rule_hits", []):
        lines.append(f"- {rule['rule_id']}: {rule['hit_count']} hit(s)")
    lines.append("fallbacks:")
    for fallback in payload.get("fallbacks", []):
        lines.append(
            f"- {fallback['path']}: reason={fallback['reason']} tests={len(fallback['tests'])}"
        )
    lines.append("selected_tests:")
    for test in payload.get("selected_tests", []):
        lines.append(f"- {test}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _validate_declared_tests_exist(data: dict[str, Any], repo_root: Path) -> list[str]:
    declared: set[str] = set()
    for rule in data.get("rules", []):
        for test in rule.get("tests", []):
            declared.add(test)
    fallback = data.get("fallback", {})
    for test in fallback.get("tests", []):
        declared.add(test)
    for item in fallback.get("by_path_globs", []):
        for test in item.get("tests", []):
            declared.add(test)
    missing = sorted(test for test in declared if not (repo_root / test).is_file())
    return missing


def _resolve_targets(
    map_data: dict[str, Any], changed_files: list[str], repo_root: Path
) -> dict[str, Any]:
    backend_scope_globs = map_data["backend_scope_globs"]
    rules = map_data["rules"]
    fallback = map_data["fallback"]
    backend_paths = [path for path in changed_files if _matches_any(path, backend_scope_globs)]

    selected: set[str] = set()
    rule_hits: dict[str, int] = {}
    fallbacks: list[dict[str, Any]] = []
    path_details: list[dict[str, Any]] = []

    for path in backend_paths:
        matched_rules = [rule for rule in rules if _matches_any(path, rule["path_globs"])]
        mapped_for_path: set[str] = set()
        matched_rule_ids: list[str] = []

        for rule in matched_rules:
            rule_id = rule["id"]
            matched_rule_ids.append(rule_id)
            rule_hits[rule_id] = rule_hits.get(rule_id, 0) + 1

            for test in rule.get("tests", []):
                existing = _existing_test(test, repo_root)
                if existing:
                    mapped_for_path.add(existing)
            if rule.get("select_changed_test_file", False):
                existing = _existing_test(path, repo_root)
                if existing:
                    mapped_for_path.add(existing)

        fallback_reason: str | None = None
        fallback_tests: set[str] = set()
        if not matched_rules:
            fallback_reason = "no_rule_matched"
        elif not mapped_for_path:
            fallback_reason = "rules_matched_but_no_existing_tests"

        if fallback_reason is not None:
            for test in fallback.get("tests", []):
                existing = _existing_test(test, repo_root)
                if existing:
                    fallback_tests.add(existing)

            for item in fallback.get("by_path_globs", []):
                if _matches_any(path, item["path_globs"]):
                    for test in item.get("tests", []):
                        existing = _existing_test(test, repo_root)
                        if existing:
                            fallback_tests.add(existing)

            if fallback.get("orchestrator_source_heuristic", True):
                heuristic_tests, heuristic_reasons = _source_heuristic(path, repo_root)
                fallback_tests.update(heuristic_tests)
                if heuristic_reasons:
                    fallback_reason = f"{fallback_reason}+{','.join(heuristic_reasons)}"

            fallbacks.append(
                {
                    "path": path,
                    "reason": fallback_reason,
                    "tests": sorted(fallback_tests),
                }
            )

        selected.update(mapped_for_path)
        selected.update(fallback_tests)
        path_details.append(
            {
                "path": path,
                "matched_rules": matched_rule_ids,
                "mapped_tests": sorted(mapped_for_path),
                "fallback_reason": fallback_reason,
                "fallback_tests": sorted(fallback_tests),
            }
        )

    return {
        "backend_paths": backend_paths,
        "selected_tests": sorted(selected),
        "rule_hits": [{"rule_id": key, "hit_count": value} for key, value in sorted(rule_hits.items())],
        "fallbacks": fallbacks,
        "path_details": path_details,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate and resolve changed-scope test map with fail-closed semantics."
    )
    parser.add_argument(
        "--map-file",
        default="configs/changed_scope_test_map.json",
        help="Path to changed-scope mapping JSON.",
    )
    parser.add_argument("--repo-root", default=".", help="Repository root.")
    parser.add_argument(
        "--changed-files-file",
        help="Optional changed files input. If omitted, only map validation is performed.",
    )
    parser.add_argument(
        "--targets-out",
        help="Output file for selected tests (required when --changed-files-file is set).",
    )
    parser.add_argument(
        "--backend-out",
        help="Optional output file for backend-related changed files.",
    )
    parser.add_argument(
        "--report-json-out",
        help="Optional selection report JSON path.",
    )
    parser.add_argument(
        "--report-txt-out",
        help="Optional selection report text path.",
    )
    parser.add_argument(
        "--strict-declared-tests",
        action="store_true",
        help="Fail if declared map tests do not exist in repository.",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    map_file = Path(args.map_file)
    if not map_file.is_absolute():
        map_file = (repo_root / map_file).resolve()

    try:
        map_data = _read_json(map_file)
    except ValueError as exc:
        print(f"changed_scope_map_error={exc}")
        return 1

    errors = _validate_map(map_data)
    if errors:
        print("changed_scope_map_validation=failed")
        for err in errors:
            print(f"- {err}")
        return 1

    if args.strict_declared_tests:
        missing = _validate_declared_tests_exist(map_data, repo_root)
        if missing:
            print("changed_scope_map_declared_tests=missing")
            for path in missing:
                print(f"- {path}")
            return 1

    print("changed_scope_map_validation=passed")
    print(f"map_file={map_file}")

    if not args.changed_files_file:
        return 0
    if not args.targets_out:
        print("changed_scope_map_error=targets_out_required_when_changed_files_file_set")
        return 1

    changed_files_path = Path(args.changed_files_file)
    if not changed_files_path.is_absolute():
        changed_files_path = (repo_root / changed_files_path).resolve()
    try:
        changed_files = _read_changed_files(changed_files_path)
    except FileNotFoundError:
        print(f"changed_scope_map_error=changed_files_not_found:{changed_files_path}")
        return 1

    resolved = _resolve_targets(map_data, changed_files, repo_root)
    backend_paths = resolved["backend_paths"]
    selected_tests = resolved["selected_tests"]
    reason = "selection_resolved"
    status = "ok"
    if backend_paths and not selected_tests:
        reason = "backend_changes_without_selected_tests"
        status = "fail_closed"

    targets_out = Path(args.targets_out)
    if not targets_out.is_absolute():
        targets_out = (repo_root / targets_out).resolve()
    targets_out.parent.mkdir(parents=True, exist_ok=True)
    _write_targets(targets_out, selected_tests)

    if args.backend_out:
        backend_out = Path(args.backend_out)
        if not backend_out.is_absolute():
            backend_out = (repo_root / backend_out).resolve()
        backend_out.parent.mkdir(parents=True, exist_ok=True)
        _write_backend(backend_out, backend_paths)

    report_payload = {
        "status": status,
        "reason": reason,
        "map_file": str(map_file.relative_to(repo_root)),
        "changed_files_count": len(changed_files),
        "backend_files_count": len(backend_paths),
        "rule_hits": resolved["rule_hits"],
        "fallbacks": resolved["fallbacks"],
        "path_details": resolved["path_details"],
        "selected_tests": selected_tests,
    }

    if args.report_json_out:
        report_json_out = Path(args.report_json_out)
        if not report_json_out.is_absolute():
            report_json_out = (repo_root / report_json_out).resolve()
        report_json_out.parent.mkdir(parents=True, exist_ok=True)
        _write_report_json(report_json_out, report_payload)

    if args.report_txt_out:
        report_txt_out = Path(args.report_txt_out)
        if not report_txt_out.is_absolute():
            report_txt_out = (repo_root / report_txt_out).resolve()
        report_txt_out.parent.mkdir(parents=True, exist_ok=True)
        _write_report_text(report_txt_out, report_payload)

    if status != "ok":
        print(f"changed_scope_map_selection={status}")
        print(f"reason={reason}")
        return 1
    print("changed_scope_map_selection=ok")
    print(f"selected_tests_count={len(selected_tests)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
