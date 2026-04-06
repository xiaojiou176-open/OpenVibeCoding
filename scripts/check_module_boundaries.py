#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "configs" / "module_boundary_rules.json"


def _iter_files(glob_pattern: str) -> list[Path]:
    return sorted(path for path in ROOT.glob(glob_pattern) if path.is_file())


_JS_TS_SPEC_RE = re.compile(
    r"""(?:import|export)\s+(?:type\s+)?(?:[^'"]*?\sfrom\s+)?['"]([^'"]+)['"]|require\(\s*['"]([^'"]+)['"]\s*\)""",
    re.MULTILINE,
)


def _extract_js_ts_specs(text: str) -> list[str]:
    specs: list[str] = []
    for match in _JS_TS_SPEC_RE.finditer(text):
        spec = match.group(1) or match.group(2)
        if spec:
            specs.append(spec)
    return specs


def _resolve_relative_spec(source_path: Path, spec: str) -> Path | None:
    if not spec.startswith("."):
        return None
    candidate = (source_path.parent / spec).resolve()
    try:
        return candidate.relative_to(ROOT.resolve())
    except ValueError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate repository module boundary rules.")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    args = parser.parse_args()
    policy = json.loads(Path(args.policy).read_text(encoding="utf-8"))
    errors: list[str] = []

    for rule in policy.get("rules", []):
        include_globs = rule.get("include_globs", [])
        deny_patterns = rule.get("deny_patterns", [])
        forbidden_relative_resolved_prefixes = tuple(rule.get("forbidden_relative_resolved_prefixes", []))
        matched_files: set[Path] = set()
        for glob_pattern in include_globs:
            matched_files.update(_iter_files(glob_pattern))
        for path in sorted(matched_files):
            text = path.read_text(encoding="utf-8", errors="ignore")
            for deny in deny_patterns:
                if re.search(deny, text, re.MULTILINE):
                    errors.append(f"{rule['id']}: {path.relative_to(ROOT)} contains forbidden dependency pattern `{deny}`")
            if forbidden_relative_resolved_prefixes and path.suffix in {".js", ".mjs", ".ts", ".tsx"}:
                for spec in _extract_js_ts_specs(text):
                    resolved = _resolve_relative_spec(path, spec)
                    if resolved is None:
                        continue
                    resolved_str = str(resolved).replace("\\", "/")
                    for prefix in forbidden_relative_resolved_prefixes:
                        if resolved_str.startswith(prefix):
                            errors.append(
                                f"{rule['id']}: {path.relative_to(ROOT)} relative import `{spec}` resolves to forbidden surface `{resolved_str}`"
                            )
                            break

    if errors:
        print("❌ [module-boundaries] violations:")
        for item in errors:
            print(f"- {item}")
        return 1

    print("✅ [module-boundaries] policy satisfied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
