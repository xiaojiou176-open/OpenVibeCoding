#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from scripts.host_process_safety import terminate_tracked_child
except ModuleNotFoundError:
    from host_process_safety import terminate_tracked_child


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MATRIX = ROOT / "configs" / "upstream_compat_matrix.json"
DEFAULT_OUTPUT_DIR = ROOT / ".runtime-cache" / "test_output" / "governance" / "upstream"
DEFAULT_HEARTBEAT_SEC = int(os.environ.get("OPENVIBECODING_UPSTREAM_VERIFICATION_HEARTBEAT_SEC", "15"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_id(prefix: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"upstream_{prefix}_{timestamp}"


def _safe_slug(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in value).strip("-") or "slice"


def _classify_failure_origin(command: str, exit_code: int, output: str) -> str:
    command_lower = command.lower()
    output_lower = output.lower()
    if exit_code == 0:
        return "none"
    if exit_code == 124:
        if "docker_ci.sh lane" in command_lower or "verify_ci_core_image_smoke" in command_lower:
            return "host_or_platform_timeout"
        return "timeout"
    if "docker" in command_lower and ("input/output error" in output_lower or "containerdmeta" in output_lower):
        return "host_storage_or_docker_fault"
    if ("docker" in command_lower or "verify_ci_core_image_smoke" in command_lower) and (
        "cannot connect to the docker daemon" in output_lower
        or "is the docker daemon running?" in output_lower
        or "error during connect" in output_lower
        or "docker desktop is unable to start" in output_lower
        or "docker daemon unavailable for" in output_lower
        or "docker socket " in output_lower
    ):
        return "host_or_platform_docker_unavailable"
    if "connection refused" in output_lower:
        return "runtime_connectivity"
    if "next: not found" in output_lower:
        return "toolchain_or_dependency"
    return "repo_or_upstream_failure"


def _tail_excerpt(output: str, *, max_lines: int = 8) -> list[str]:
    lines = [line for line in output.splitlines() if line.strip()]
    if not lines:
        return []
    return lines[-max_lines:]


def _last_stage_marker(output: str) -> str:
    for line in reversed(output.splitlines()):
        stripped = line.strip()
        if " stage=" not in stripped:
            continue
        return stripped
    return ""


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_in_progress_record(
    *,
    record_path: Path,
    slice_name: str,
    mode: str,
    run_id: str,
    verification_batch_id: str,
    artifact_path: str,
    command: str,
    timeout_sec: int,
    owner: object,
    rollback_path: object,
    failure_attribution_hint: object,
    upstream_ids: object,
) -> None:
    _write_json(
        record_path,
        {
            "integration_slice": slice_name,
            "verification_mode": mode,
            "status": "in_progress",
            "started_at": _utc_now(),
            "last_verified_at": "",
            "last_verified_run_id": run_id,
            "verification_batch_id": verification_batch_id,
            "last_verified_artifact": artifact_path,
            "command": command,
            "timeout_sec": timeout_sec,
            "exit_code": None,
            "owner": owner,
            "rollback_path": rollback_path,
            "failure_attribution_hint": failure_attribution_hint,
            "failure_origin_scope": "in_progress",
            "last_stage_marker": "",
            "failure_tail_excerpt": [],
            "upstream_ids": upstream_ids,
        },
    )


def _recover_interrupted_record(
    *,
    record_path: Path,
    log_path: Path,
    slice_name: str,
    mode: str,
    command: str,
    timeout_sec: int,
    owner: object,
    rollback_path: object,
    failure_attribution_hint: object,
    upstream_ids: object,
) -> None:
    if not record_path.exists():
        return
    try:
        payload = json.loads(record_path.read_text(encoding="utf-8"))
    except Exception:
        return
    if not isinstance(payload, dict):
        return
    if str(payload.get("status") or "").strip().lower() != "in_progress":
        return

    tmp_logs = sorted(
        log_path.parent.glob(f"{log_path.stem}.*.tmp.log"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    source_log_path = tmp_logs[0] if tmp_logs else (log_path if log_path.exists() else None)
    if source_log_path is None:
        return

    output = source_log_path.read_text(encoding="utf-8")
    log_path.write_text(output + ("\n" if output and not output.endswith("\n") else ""), encoding="utf-8")
    for tmp_log_path in tmp_logs:
        tmp_log_path.unlink(missing_ok=True)

    recovered_record = {
        "integration_slice": slice_name,
        "verification_mode": str(payload.get("verification_mode") or mode),
        "status": "failed",
        "started_at": str(payload.get("started_at") or _utc_now()),
        "last_verified_at": _utc_now(),
        "last_verified_run_id": str(payload.get("last_verified_run_id") or _run_id(_safe_slug(slice_name))),
        "verification_batch_id": str(payload.get("verification_batch_id") or ""),
        "last_verified_artifact": str(log_path.relative_to(ROOT)),
        "command": str(payload.get("command") or command),
        "timeout_sec": int(payload.get("timeout_sec") or timeout_sec),
        "exit_code": int(payload.get("exit_code") or 130),
        "owner": payload.get("owner", owner),
        "rollback_path": payload.get("rollback_path", rollback_path),
        "failure_attribution_hint": payload.get("failure_attribution_hint", failure_attribution_hint),
        "failure_origin_scope": "interrupted_before_finalization",
        "last_stage_marker": _last_stage_marker(output),
        "failure_tail_excerpt": _tail_excerpt(output),
        "upstream_ids": payload.get("upstream_ids", upstream_ids),
    }
    _write_json(record_path, recovered_record)


def _clear_previous_artifacts(log_path: Path) -> None:
    log_path.unlink(missing_ok=True)
    for stale_tmp_log in log_path.parent.glob(f"{log_path.stem}.*.tmp.log"):
        stale_tmp_log.unlink(missing_ok=True)


def _run_shell(command: str, *, extra_env: dict[str, str], timeout_sec: int, log_path: Path) -> tuple[int, str]:
    env = os.environ.copy()
    env.update(extra_env)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    heartbeat_sec = max(5, DEFAULT_HEARTBEAT_SEC)
    started = time.monotonic()
    deadline = started + timeout_sec
    last_heartbeat = started
    with tempfile.NamedTemporaryFile(
        mode="w+",
        encoding="utf-8",
        prefix=f"{log_path.stem}.",
        suffix=".tmp.log",
        dir=str(log_path.parent),
        delete=False,
    ) as tmp_log_handle:
        tmp_log_path = Path(tmp_log_handle.name)
        tmp_log_handle.write(f"ℹ️ [verify-upstream-slices] started command={command}\n")
        tmp_log_handle.flush()
        print(f"ℹ️ [verify-upstream-slices] started: {command}", flush=True)
        process = subprocess.Popen(
            ["bash", "-lc", command],
            cwd=ROOT,
            stdout=tmp_log_handle,
            stderr=tmp_log_handle,
            text=True,
            env=env,
        )
        try:
            while True:
                exit_code = process.poll()
                if exit_code is not None:
                    break
                now = time.monotonic()
                if now >= deadline:
                    raise subprocess.TimeoutExpired(command, timeout_sec)
                if now - last_heartbeat >= heartbeat_sec:
                    elapsed = int(now - started)
                    heartbeat = f"ℹ️ [verify-upstream-slices] heartbeat elapsed={elapsed}s command={command}"
                    tmp_log_handle.write(heartbeat + "\n")
                    tmp_log_handle.flush()
                    print(heartbeat, flush=True)
                    last_heartbeat = now
                time.sleep(1)
        except subprocess.TimeoutExpired:
            termination_signal = terminate_tracked_child(
                process,
                term_timeout_sec=5,
                kill_timeout_sec=3,
            )
            timeout_msg = (
                f"command timed out after {timeout_sec}s "
                f"(termination={termination_signal})"
            )
            tmp_log_handle.write(timeout_msg + "\n")
            tmp_log_handle.flush()
            print(f"⚠️ [verify-upstream-slices] {timeout_msg}", flush=True)
            tmp_log_handle.flush()
            tmp_log_handle.seek(0)
            output = tmp_log_handle.read()
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(output + ("\n" if output and not output.endswith("\n") else ""), encoding="utf-8")
            tmp_log_path.unlink(missing_ok=True)
            return 124, output.strip()

        tmp_log_handle.flush()
        tmp_log_handle.seek(0)
        output = tmp_log_handle.read()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(output + ("\n" if output and not output.endswith("\n") else ""), encoding="utf-8")
        tmp_log_path.unlink(missing_ok=True)
        return int(exit_code), output.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute upstream slice verification and write generated records.")
    parser.add_argument("--matrix", default=str(DEFAULT_MATRIX))
    parser.add_argument("--slice", action="append", default=[])
    parser.add_argument("--mode", choices=("validation", "smoke"), default="smoke")
    parser.add_argument("--verification-batch-id", default="")
    parser.add_argument(
        "--timeout-sec",
        type=int,
        default=None,
    )
    args = parser.parse_args()

    matrix = json.loads(Path(args.matrix).read_text(encoding="utf-8"))
    rows = matrix.get("matrix", [])
    selected = set(args.slice)
    failures: list[str] = []
    command_cache: dict[str, tuple[int, str, str]] = {}
    verification_batch_id = str(args.verification_batch_id or "").strip() or _run_id("batch")

    for row in rows:
        slice_name = str(row.get("integration_slice") or "").strip()
        if selected and slice_name not in selected:
            continue
        command = str(row.get("smoke_entrypoint") if args.mode == "smoke" else row.get("validation_gate") or "").strip()
        if not command:
            failures.append(f"{slice_name}: missing command for mode={args.mode}")
            continue
        if args.timeout_sec is not None:
            timeout_sec = int(args.timeout_sec)
        else:
            timeout_sec = int(
                row.get("smoke_timeout_sec")
                if args.mode == "smoke"
                else row.get("validation_timeout_sec") or os.environ.get("OPENVIBECODING_UPSTREAM_VERIFICATION_TIMEOUT_SEC", "180")
            )

        record_path = ROOT / str(row.get("verification_record_path") or "")
        record_path.parent.mkdir(parents=True, exist_ok=True)
        slug = _safe_slug(slice_name)
        run_id = _run_id(slug)
        log_path = record_path.with_suffix(".log")
        artifact_path = str(log_path.relative_to(ROOT))
        extra_env = {
            "OPENVIBECODING_UPSTREAM_VERIFICATION_RUN_ID": run_id,
            "OPENVIBECODING_UPSTREAM_VERIFICATION_BATCH_ID": verification_batch_id,
            "OPENVIBECODING_LOG_RUN_ID": run_id,
            "OPENVIBECODING_LOG_ARTIFACT_KIND": "upstream_verification",
        }
        _recover_interrupted_record(
            record_path=record_path,
            log_path=log_path,
            slice_name=slice_name,
            mode=args.mode,
            command=command,
            timeout_sec=timeout_sec,
            owner=row.get("owner"),
            rollback_path=row.get("rollback_path"),
            failure_attribution_hint=row.get("failure_attribution_hint"),
            upstream_ids=row.get("upstream_ids", []),
        )
        _clear_previous_artifacts(log_path)
        _write_in_progress_record(
            record_path=record_path,
            slice_name=slice_name,
            mode=args.mode,
            run_id=run_id,
            verification_batch_id=verification_batch_id,
            artifact_path=artifact_path,
            command=command,
            timeout_sec=timeout_sec,
            owner=row.get("owner"),
            rollback_path=row.get("rollback_path"),
            failure_attribution_hint=row.get("failure_attribution_hint"),
            upstream_ids=row.get("upstream_ids", []),
        )
        if command in command_cache:
            exit_code, output, cached_artifact = command_cache[command]
            artifact_path = cached_artifact
        else:
            exit_code, output = _run_shell(command, extra_env=extra_env, timeout_sec=timeout_sec, log_path=log_path)
            command_cache[command] = (exit_code, output, artifact_path)
        if artifact_path != str(log_path.relative_to(ROOT)):
            log_path.write_text(output + ("\n" if output else ""), encoding="utf-8")

        status = "passed" if exit_code == 0 else "failed"
        record = {
            "integration_slice": slice_name,
            "verification_mode": args.mode,
            "status": status,
            "last_verified_at": _utc_now(),
            "last_verified_run_id": run_id,
            "verification_batch_id": verification_batch_id,
            "last_verified_artifact": artifact_path,
            "command": command,
            "timeout_sec": timeout_sec,
            "exit_code": exit_code,
            "owner": row.get("owner"),
            "rollback_path": row.get("rollback_path"),
            "failure_attribution_hint": row.get("failure_attribution_hint"),
            "failure_origin_scope": _classify_failure_origin(command, exit_code, output),
            "last_stage_marker": _last_stage_marker(output),
            "failure_tail_excerpt": _tail_excerpt(output),
            "upstream_ids": row.get("upstream_ids", []),
        }
        record_path.parent.mkdir(parents=True, exist_ok=True)
        record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

        if exit_code != 0:
            failures.append(f"{slice_name}: command failed ({exit_code})")

    if failures:
        print("❌ [verify-upstream-slices] failures:")
        for item in failures:
            print(f"- {item}")
        return 1

    print("✅ [verify-upstream-slices] verification records written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
