#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from ci_current_run_support import current_truth_authority, load_source_manifest, now_utc, source_metadata


ROOT = Path(__file__).resolve().parents[1]
DOCKER_METADATA_TIMEOUT_SEC = int(os.environ.get("OPENVIBECODING_CI_DOCKER_METADATA_TIMEOUT_SEC", "30"))


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _docker_inspect(image: str) -> tuple[dict, dict[str, object]]:
    meta: dict[str, object] = {
        "status": "ok",
        "timeout_sec": DOCKER_METADATA_TIMEOUT_SEC,
        "error": "",
    }
    try:
        payload = subprocess.check_output(
            ["docker", "image", "inspect", image],
            cwd=ROOT,
            text=True,
            timeout=DOCKER_METADATA_TIMEOUT_SEC,
            stderr=subprocess.STDOUT,
        )
        rows = json.loads(payload)
        return (rows[0] if rows else {}), meta
    except subprocess.TimeoutExpired as exc:
        meta["status"] = "timeout"
        meta["error"] = ((exc.output or "") if isinstance(exc.output, str) else "")[-400:]
        return {}, meta
    except subprocess.CalledProcessError as exc:
        meta["status"] = "error"
        meta["error"] = ((exc.output or "") if isinstance(exc.output, str) else "")[-400:]
        return {}, meta
    except Exception as exc:  # noqa: BLE001
        meta["status"] = "error"
        meta["error"] = str(exc)
        return {}, meta


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build release provenance for the current CI run.")
    parser.add_argument("--source-manifest", default="")
    parser.add_argument("--image", default=os.environ.get("OPENVIBECODING_CI_PROVENANCE_IMAGE", "openvibecoding-ci-core:local"))
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--out-dir", default=".runtime-cache/openvibecoding/release/provenance")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_manifest = load_source_manifest(args.source_manifest or None)
    meta = source_metadata(source_manifest)
    authority = current_truth_authority(source_manifest)
    workflow = {
        "github_run_id": meta["source_run_id"],
        "github_run_attempt": meta["source_run_attempt"],
        "github_sha": meta["source_sha"],
        "github_ref": meta["source_ref"],
        "github_event_name": meta["source_event"],
    }
    if args.strict:
        missing = [key for key, value in workflow.items() if not str(value or "").strip()]
        if missing:
            print("❌ [ci-release-provenance] strict mode requires non-empty workflow metadata")
            for item in missing:
                print(f"- {item}")
            return 1
    inspect, docker_probe = _docker_inspect(args.image)
    payload = {
        "report_type": "openvibecoding_ci_release_provenance",
        "generated_at": now_utc(),
        "authoritative": bool(authority["authoritative_current_truth"]),
        **authority,
        "git": {
            "commit": _git("rev-parse", "HEAD"),
            "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        },
        "workflow": workflow,
        "route_id": meta["source_route"],
        "trust_class": meta["source_trust_class"],
        "runner_class": meta["source_runner_class"],
        "image": {
            "name": args.image,
            "id": inspect.get("Id", ""),
            "repo_tags": inspect.get("RepoTags") or [],
            "input_hash": ((inspect.get("Config") or {}).get("Labels") or {}).get("org.openvibecoding.ci.input-hash", ""),
        },
        "docker_probe": docker_probe,
        **meta,
    }
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    report_json = out_dir / "provenance.json"
    report_md = out_dir / "provenance.md"
    report_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_md.write_text(
        "\n".join(
            [
                "## CI Release Provenance",
                "",
                f"- authoritative: `{bool(authority['authoritative_current_truth'])}`",
                f"- authority_level: `{authority['authority_level']}`",
                f"- source_head_match: `{authority['source_head_match']}`",
                f"- source_run_id: `{meta['source_run_id']}`",
                f"- source_route: `{meta['source_route']}`",
                f"- commit: `{payload['git']['commit']}`",
                f"- branch: `{payload['git']['branch']}`",
                f"- github_event_name: `{workflow['github_event_name']}`",
                f"- image: `{payload['image']['name']}`",
                f"- image_id: `{payload['image']['id']}`",
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
