#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "configs" / "docs_render_manifest.json"


def git_commit_ts(path: Path) -> int | None:
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%ct", "--", str(path.relative_to(ROOT))],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None
    raw = result.stdout.strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def is_git_fresh(output: Path, source: Path) -> bool:
    output_ts = git_commit_ts(output)
    source_ts = git_commit_ts(source)
    if output_ts is None or source_ts is None:
        return False
    return output_ts >= source_ts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate docs render outputs against manifest freshness rules.")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest_path = Path(args.manifest).expanduser().resolve()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise SystemExit("❌ [docs-render] invalid manifest: entries(list) required")

    registered_outputs: set[Path] = set()
    errors: list[str] = []
    for item in entries:
        output_rel = str(item.get("output_path") or "").strip()
        if not output_rel:
            errors.append("manifest entry missing output_path")
            continue
        output = ROOT / output_rel
        registered_outputs.add(output.resolve())
        if not output.exists():
            errors.append(f"manifest output missing: {output_rel}")
            continue
        output_mtime = output.stat().st_mtime
        for source_rel in item.get("source_inputs") or []:
            source = ROOT / str(source_rel)
            if not source.exists():
                errors.append(f"manifest source missing: {source_rel}")
                continue
            if source.stat().st_mtime > output_mtime and not is_git_fresh(output, source):
                errors.append(f"render output stale: {output_rel} older than {source_rel}")

    generated_dir = ROOT / "docs" / "generated"
    if generated_dir.exists():
        for path in generated_dir.rglob("*"):
            if path.is_file() and path.resolve() not in registered_outputs:
                errors.append(f"generated output not registered in manifest: {path.relative_to(ROOT)}")

    if errors:
        print("❌ [docs-render] freshness/boundary violations:")
        for item in errors:
            print(f"- {item}")
        return 1

    print("✅ [docs-render] render outputs are present and fresh")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
