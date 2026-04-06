#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "repo_positioning.json"


def main() -> int:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    errors: list[str] = []
    for surface in config.get("surfaces", []):
        path = ROOT / surface["path"]
        text = path.read_text(encoding="utf-8")
        for needle in surface.get("must_include", []):
            if needle not in text:
                errors.append(f"{surface['path']} missing required positioning marker: {needle}")

    if errors:
        print("❌ [repo-positioning] repository positioning drift detected:")
        for item in errors:
            print(f"- {item}")
        return 1

    print("✅ [repo-positioning] repository positioning markers satisfied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
