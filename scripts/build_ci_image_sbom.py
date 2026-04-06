#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from ci_current_run_support import current_truth_authority, load_source_manifest, now_utc, source_metadata


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / ".runtime-cache" / "cortexpilot" / "reports" / "ci" / "sbom"
DOCKER_METADATA_TIMEOUT_SEC = int(os.environ.get("CORTEXPILOT_CI_DOCKER_METADATA_TIMEOUT_SEC", "30"))


def _run(args: list[str]) -> tuple[str, dict[str, object]]:
    meta: dict[str, object] = {
        "status": "ok",
        "timeout_sec": DOCKER_METADATA_TIMEOUT_SEC,
        "error": "",
    }
    try:
        proc = subprocess.run(
            args,
            check=True,
            capture_output=True,
            text=True,
            timeout=DOCKER_METADATA_TIMEOUT_SEC,
        )
        return proc.stdout, meta
    except subprocess.TimeoutExpired as exc:
        meta["status"] = "timeout"
        meta["error"] = ((exc.stdout or "") + "\n" + (exc.stderr or "")).strip()[-400:]
        return "", meta
    except subprocess.CalledProcessError as exc:
        meta["status"] = "error"
        meta["error"] = ((exc.stdout or "") + "\n" + (exc.stderr or "")).strip()[-400:]
        return "", meta
    except Exception as exc:  # noqa: BLE001
        meta["status"] = "error"
        meta["error"] = str(exc)
        return "", meta


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a lightweight SBOM/inventory for cortexpilot-ci-core image.")
    parser.add_argument("--image", default="cortexpilot-ci-core:local", help="Docker image name")
    parser.add_argument("--source-manifest", default="")
    parser.add_argument("--out-dir", default=str(OUT_DIR), help="Output directory")
    args = parser.parse_args()

    source_manifest = load_source_manifest(args.source_manifest or None)
    authority = current_truth_authority(source_manifest)
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    inspect_raw, inspect_meta = _run(["docker", "image", "inspect", args.image])
    inspect = json.loads(inspect_raw) if inspect_raw else []
    image_info = inspect[0] if inspect else {}
    inventory_json, inventory_meta = _run(
        [
            "docker",
            "run",
            "--rm",
            args.image,
            "bash",
            "-lc",
            "dpkg-query -W -f='\\${Package}\\t\\${Version}\\n' | sort && echo '---PYTHON---' && python3 -m pip list --format json && echo '---RUNTIME---' && node --version && pnpm --version && cargo --version && cargo-audit --version",
        ]
    )
    payload = {
        "report_type": "cortexpilot_ci_image_sbom",
        "generated_at": now_utc(),
        "authoritative": bool(authority["authoritative_current_truth"]),
        **authority,
        "image": args.image,
        "image_id": image_info.get("Id"),
        "repo_tags": image_info.get("RepoTags") or [],
        "labels": (image_info.get("Config") or {}).get("Labels") or {},
        "inventory_raw": inventory_json,
        "docker_image_probe": inspect_meta,
        "docker_inventory_probe": inventory_meta,
        **source_metadata(source_manifest),
    }
    report_json = out_dir / "image_sbom.json"
    report_md = out_dir / "image_sbom.md"
    report_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_md.write_text(
        "\n".join(
            [
                "## CI Image SBOM",
                "",
                f"- authoritative: `{bool(authority['authoritative_current_truth'])}`",
                f"- authority_level: `{authority['authority_level']}`",
                f"- source_head_match: `{authority['source_head_match']}`",
                f"- source_run_id: `{payload['source_run_id']}`",
                f"- source_route: `{payload['source_route']}`",
                f"- image: `{args.image}`",
                f"- image_id: `{payload['image_id']}`",
                f"- repo_tags: `{', '.join(payload['repo_tags'])}`",
                "",
                "Raw inventory stored in `image_sbom.json`.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(str(report_json))
    print(str(report_md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
