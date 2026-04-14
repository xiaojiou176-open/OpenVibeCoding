#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "orchestrator" / "src"))

from openvibecoding_orch.runtime.space_governance import (
    load_space_governance_policy,
    path_size_bytes,
    revalidate_cleanup_targets,
)


DEFAULT_POLICY = ROOT / "configs" / "space_governance_policy.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply OpenVibeCoding space cleanup after gate revalidation.")
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    parser.add_argument("--gate-json", required=True)
    parser.add_argument("--result-json", required=True)
    parser.add_argument("--repo-root", default=str(ROOT), help=argparse.SUPPRESS)
    return parser.parse_args()


def remove_path(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
        return
    shutil.rmtree(path)


def size_for_cleanup_path(path: Path) -> int:
    if not path.exists() and not path.is_symlink():
        return 0
    resolved_path = path.resolve(strict=False)
    size_target = resolved_path if path.is_symlink() and resolved_path.exists() else path
    return path_size_bytes(size_target)


def read_tail(path: Path, *, max_bytes: int = 1000) -> str:
    if not path.exists():
        return ""
    with path.open("rb") as handle:
        try:
            handle.seek(-max_bytes, 2)
        except OSError:
            handle.seek(0)
        return handle.read().decode("utf-8", errors="replace")


def run_verification_commands(*, repo_root: Path, commands: list[dict]) -> tuple[list[dict], str]:
    results: list[dict] = []
    for command in commands:
        argv = [str(item) for item in command.get("argv", []) if str(item).strip()]
        command_line = shlex.join(argv) if argv else ""
        if not argv:
            results.append(
                {
                    "command_id": str(command.get("command_id", "")),
                    "command": command_line,
                    "exit_code": 1,
                    "available": False,
                    "detail": "missing argv",
                }
            )
            return results, "cleanup completed but no runnable post-cleanup verification command was available; rerun the declared rebuild commands manually"
        with tempfile.NamedTemporaryFile(mode="w+b", delete=False) as stdout_handle, tempfile.NamedTemporaryFile(
            mode="w+b", delete=False
        ) as stderr_handle:
            stdout_path = Path(stdout_handle.name)
            stderr_path = Path(stderr_handle.name)
        try:
            with stdout_path.open("w", encoding="utf-8") as stdout_file, stderr_path.open("w", encoding="utf-8") as stderr_file:
                proc = subprocess.run(
                    argv,
                    cwd=repo_root,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    text=True,
                    check=False,
                )
            stdout_tail = read_tail(stdout_path)
            stderr_tail = read_tail(stderr_path)
        finally:
            stdout_path.unlink(missing_ok=True)
            stderr_path.unlink(missing_ok=True)
        results.append(
            {
                "command_id": str(command.get("command_id", "")),
                "command": command_line,
                "exit_code": int(proc.returncode),
                "available": bool(command.get("available", False)),
                "detail": str(command.get("detail", "")),
                "stdout_tail": stdout_tail,
                "stderr_tail": stderr_tail,
            }
        )
        if proc.returncode != 0:
            return (
                results,
                "cleanup completed but post-cleanup verification failed; rerun the listed rebuild commands to restore this surface before continuing",
            )
    return results, ""


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).expanduser().resolve()
    policy = load_space_governance_policy(Path(args.policy).expanduser().resolve())
    gate_path = Path(args.gate_json).expanduser().resolve()
    result_path = Path(args.result_json).expanduser().resolve()
    gate = json.loads(gate_path.read_text(encoding="utf-8"))

    revalidation = revalidate_cleanup_targets(repo_root=repo_root, policy=policy, gate=gate)
    if revalidation["gate_errors"] or revalidation["rejected_targets"]:
        payload = {
            "wave": revalidation["wave"],
            "status": "rejected",
            "gate_errors": revalidation["gate_errors"],
            "validated_targets": revalidation["validated_targets"],
            "rejected_targets": revalidation["rejected_targets"],
            "source_gate": str(gate_path),
        }
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("❌ [space-cleanup-apply] target revalidation failed")
        for item in revalidation["gate_errors"]:
            print(f"- gate: {item}")
        for item in revalidation["rejected_targets"]:
            print(f"- {item['path']}: {item['revalidation_reason']}")
        return 1

    removed_targets = []
    before_total = 0
    after_total = 0
    verification_failures: list[dict[str, object]] = []
    for item in revalidation["validated_targets"]:
        path = Path(item["path"])
        before = size_for_cleanup_path(path)
        before_total += before
        remove_path(path)
        after = size_for_cleanup_path(path)
        after_total += after
        verification_commands = list(item.get("post_cleanup_verification_commands", []))
        verification_results, failure_rollback_note = run_verification_commands(
            repo_root=repo_root,
            commands=verification_commands,
        )
        verification_failed = bool(failure_rollback_note)
        removed_targets.append(
            {
                "entry_id": item["entry_id"],
                "path": item["path"],
                "realpath": item["canonical_path"],
                "size_before": before,
                "size_after": after,
                "released_bytes": max(before - after, 0),
                "removed_paths_count": 1 if not path.exists() else 0,
                "classification": item["classification"],
                "rebuild_entrypoints": item["rebuild_entrypoints"],
                "post_cleanup_verification_commands": verification_commands,
                "verification_results": verification_results,
                "verification_failed": verification_failed,
                "failure_rollback_note": failure_rollback_note,
                "deleted": not path.exists(),
                "skip_reason": "",
            }
        )
        if verification_failed:
            verification_failures.append(
                {
                    "entry_id": item["entry_id"],
                    "path": item["path"],
                    "failure_rollback_note": failure_rollback_note,
                }
            )

    payload = {
        "wave": revalidation["wave"],
        "status": "verification_failed" if verification_failures else "applied",
        "gate_errors": [],
        "validated_targets": revalidation["validated_targets"],
        "rejected_targets": [],
        "removed_targets": removed_targets,
        "released_total_bytes": max(before_total - after_total, 0),
        "before_total_bytes": before_total,
        "after_total_bytes": after_total,
        "verification_failures": verification_failures,
        "source_gate": str(gate_path),
    }
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if verification_failures:
        print(
            f"❌ [space-cleanup-apply] cleanup verified with failures wave={payload['wave']} "
            f"released_bytes={payload['released_total_bytes']} targets={len(removed_targets)}"
        )
        for item in verification_failures:
            print(f"- {item['path']}: {item['failure_rollback_note']}")
        return 1

    print(
        f"🧹 [space-cleanup-apply] applied wave={payload['wave']} "
        f"released_bytes={payload['released_total_bytes']} targets={len(removed_targets)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
