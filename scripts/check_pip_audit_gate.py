#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run pip-audit and allow only declared unfixed advisories to downgrade to advisory mode."
    )
    parser.add_argument(
        "--ignore-config",
        default="configs/pip_audit_ignored_advisories.json",
        help="Path to the machine-readable ignore contract.",
    )
    return parser.parse_args()


def load_ignore_config(path: Path) -> tuple[set[str], dict[tuple[str, str], dict[str, str]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    ids = payload.get("ids")
    findings = payload.get("unfixed_surface_findings")
    if not isinstance(ids, list):
        raise SystemExit(f"invalid pip audit ignore config ids: {path}")
    if not isinstance(findings, list):
        raise SystemExit(f"invalid pip audit ignore config unfixed_surface_findings: {path}")

    allowed_ids: set[str] = set()
    allowed_findings: dict[tuple[str, str], dict[str, str]] = {}

    for raw_id in ids:
        if not isinstance(raw_id, str) or not raw_id.strip():
            raise SystemExit(f"invalid advisory id in {path}: {raw_id!r}")
        allowed_ids.add(raw_id.strip())

    for raw in findings:
        if not isinstance(raw, dict):
            raise SystemExit(f"invalid finding entry in {path}: {raw!r}")
        advisory_id = raw.get("id")
        package = raw.get("package")
        rationale = raw.get("rationale")
        treatment = raw.get("treatment")
        if not all(isinstance(item, str) and item.strip() for item in (advisory_id, package, rationale, treatment)):
            raise SystemExit(f"invalid unfixed finding entry in {path}: {raw!r}")
        allowed_findings[(package.strip(), advisory_id.strip())] = {
            "rationale": rationale.strip(),
            "treatment": treatment.strip(),
        }

    return allowed_ids, allowed_findings


def run_pip_audit() -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, "-m", "pip_audit", "-f", "json"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode not in {0, 1}:
        combined = "\n".join(part for part in (proc.stderr.strip(), proc.stdout.strip()) if part.strip())
        raise SystemExit(f"pip-audit execution failed ({proc.returncode}):\n{combined}")

    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"pip-audit returned invalid json: {exc}\nstderr:\n{proc.stderr}") from exc

    if not isinstance(payload, dict):
        raise SystemExit("pip-audit payload root must be an object")
    return payload


def main() -> int:
    args = parse_args()
    ignore_config = Path(args.ignore_config)
    allowed_ids, allowed_findings = load_ignore_config(ignore_config)
    payload = run_pip_audit()

    dependencies = payload.get("dependencies", [])
    if not isinstance(dependencies, list):
        raise SystemExit("pip-audit payload.dependencies must be a list")

    blocking: list[dict[str, str]] = []
    ignored: list[dict[str, str]] = []

    for dep in dependencies:
        if not isinstance(dep, dict):
            raise SystemExit(f"invalid pip-audit dependency entry: {dep!r}")
        package = dep.get("name")
        vulns = dep.get("vulns", [])
        if not isinstance(package, str) or not isinstance(vulns, list):
            raise SystemExit(f"invalid pip-audit dependency shape: {dep!r}")
        for vuln in vulns:
            if not isinstance(vuln, dict):
                raise SystemExit(f"invalid pip-audit vulnerability entry: {vuln!r}")
            advisory_id = vuln.get("id")
            fix_versions = vuln.get("fix_versions", [])
            if not isinstance(advisory_id, str) or not isinstance(fix_versions, list):
                raise SystemExit(f"invalid pip-audit vulnerability shape: {vuln!r}")
            key = (package, advisory_id)
            if advisory_id in allowed_ids and key in allowed_findings and not fix_versions:
                ignored.append(
                    {
                        "package": package,
                        "id": advisory_id,
                        "rationale": allowed_findings[key]["rationale"],
                    }
                )
                continue
            blocking.append(
                {
                    "package": package,
                    "id": advisory_id,
                    "fix_versions": ", ".join(fix_versions) if fix_versions else "(none published)",
                }
            )

    if blocking:
        print("❌ [pip-audit-gate] blocking vulnerabilities remain:")
        for item in blocking:
            print(
                f"- {item['package']} {item['id']} fix_versions={item['fix_versions']}"
            )
        return 1

    if ignored:
        print("⚠️ [pip-audit-gate] only configured unfixed advisories remain:")
        for item in ignored:
            print(f"- {item['package']} {item['id']} advisory-only: {item['rationale']}")

    print("✅ [pip-audit-gate] dependency audit passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
