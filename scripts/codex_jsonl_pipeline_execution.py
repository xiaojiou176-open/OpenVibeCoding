from __future__ import annotations

import argparse
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from codex_jsonl_pipeline_discovery import FileTask
from codex_jsonl_pipeline_logging import append_log, now_ts, write_failure_markdown
from codex_jsonl_pipeline_markdown import (
    build_chunk_prompt,
    build_prompt,
    compose_chunked_markdown,
    load_compact_turns,
    markdown_is_valid,
    persist_invalid_markdown,
    split_turn_chunks,
    validate_markdown_text,
)
from codex_jsonl_provider_codex import run_codex_once
from codex_jsonl_provider_gemini import run_gemini_once


@dataclass
class FileRunOutcome:
    ok: bool
    message: str
    attempts: int
    expected_turns: int
    provider_meta: dict[str, Any]
    invalid_artifact: str = ""


def run_codex_chunked_for_file(
    *,
    jsonl_path: Path,
    md_path: Path,
    root: Path,
    args: argparse.Namespace,
    print_lock: threading.Lock,
) -> FileRunOutcome:
    if args.provider != "codex":
        return FileRunOutcome(
            ok=False,
            message="chunked mode only supports provider=codex",
            attempts=1,
            expected_turns=0,
            provider_meta={"provider": args.provider, "prompt_mode": "chunked"},
        )

    cwd = jsonl_path.parent
    _, turns, expected_turn_ids, bad_line_count = load_compact_turns(jsonl_path, args.max_chars_per_side)
    chunks = split_turn_chunks(turns, args.codex_chunk_size)
    attempts_per_chunk = max(0, args.retry_on_invalid) + 1
    turn_sections: dict[str, str] = {}
    total_attempts_used = 0
    last_invalid_artifact = ""

    repo_root = Path(__file__).resolve().parents[1]
    chunk_temp_dir = repo_root / ".runtime-cache" / "cortexpilot" / "temp" / "codex_jsonl_chunks" / jsonl_path.stem
    chunk_temp_dir.mkdir(parents=True, exist_ok=True)

    for chunk_index, chunk_turns in enumerate(chunks, 1):
        chunk_turn_ids = [str(item.get("turn_id", "")).strip() for item in chunk_turns]
        chunk_prompt = build_chunk_prompt(
            jsonl_path=jsonl_path,
            root=root,
            chunk_turns=chunk_turns,
            chunk_turn_ids=chunk_turn_ids,
            chunk_index=chunk_index,
            chunk_total=len(chunks),
        )
        chunk_md_path = chunk_temp_dir / f"{jsonl_path.stem}.chunk{chunk_index}.md"

        chunk_succeeded = False
        chunk_error = "unknown chunk failure"
        for attempt in range(1, attempts_per_chunk + 1):
            total_attempts_used += 1
            ok, message, provider_meta = run_codex_once(
                prompt=chunk_prompt,
                md_path=chunk_md_path,
                cwd=cwd,
                codex_bin=args.codex_bin,
                model=args.model,
                profile=args.profile,
                timeout_sec=args.timeout_sec,
                dry_run=args.dry_run,
                print_lock=print_lock,
            )
            provider_meta["chunk_index"] = chunk_index
            provider_meta["chunk_total"] = len(chunks)
            provider_meta["bad_line_count"] = bad_line_count

            if not ok:
                chunk_error = message
                continue

            if message == "dry-run":
                return FileRunOutcome(
                    ok=True,
                    message="dry-run",
                    attempts=total_attempts_used,
                    expected_turns=len(expected_turn_ids),
                    provider_meta={
                        "provider": "codex",
                        "prompt_mode": "chunked",
                        "chunk_count": len(chunks),
                        "bad_line_count": bad_line_count,
                    },
                )

            chunk_text = chunk_md_path.read_text(encoding="utf-8")
            valid, reason, chunk_sections = validate_markdown_text(
                chunk_text,
                chunk_turn_ids,
                require_overall_section=False,
            )
            if valid:
                for turn_id in chunk_turn_ids:
                    turn_sections[turn_id] = chunk_sections.get(turn_id, "")
                chunk_succeeded = True
                try:
                    chunk_md_path.unlink(missing_ok=True)
                except Exception:
                    pass
                break

            invalid_artifact = persist_invalid_markdown(chunk_md_path, attempt)
            if invalid_artifact:
                last_invalid_artifact = invalid_artifact
                chunk_error = (
                    f"chunk {chunk_index}/{len(chunks)} invalid markdown: {reason} "
                    f"| invalid_saved={invalid_artifact}"
                )
            else:
                chunk_error = f"chunk {chunk_index}/{len(chunks)} invalid markdown: {reason}"

        if not chunk_succeeded:
            return FileRunOutcome(
                ok=False,
                message=chunk_error,
                attempts=total_attempts_used,
                expected_turns=len(expected_turn_ids),
                provider_meta={
                    "provider": "codex",
                    "prompt_mode": "chunked",
                    "chunk_count": len(chunks),
                    "failed_chunk": chunk_index,
                    "bad_line_count": bad_line_count,
                },
                invalid_artifact=last_invalid_artifact,
            )

    combined_markdown = compose_chunked_markdown(
        jsonl_path=jsonl_path,
        root=root,
        expected_turn_ids=expected_turn_ids,
        turn_sections=turn_sections,
    )
    md_path.write_text(combined_markdown, encoding="utf-8")

    valid, reason = markdown_is_valid(md_path, expected_turn_ids)
    if not valid:
        invalid_artifact = persist_invalid_markdown(md_path, 0)
        message = f"chunked merge invalid markdown: {reason}"
        if invalid_artifact:
            message = f"{message} | invalid_saved={invalid_artifact}"
        return FileRunOutcome(
            ok=False,
            message=message,
            attempts=total_attempts_used,
            expected_turns=len(expected_turn_ids),
            provider_meta={
                "provider": "codex",
                "prompt_mode": "chunked",
                "chunk_count": len(chunks),
                "bad_line_count": bad_line_count,
            },
            invalid_artifact=invalid_artifact,
        )

    return FileRunOutcome(
        ok=True,
        message="ok",
        attempts=total_attempts_used,
        expected_turns=len(expected_turn_ids),
        provider_meta={
            "provider": "codex",
            "prompt_mode": "chunked",
            "chunk_count": len(chunks),
            "bad_line_count": bad_line_count,
        },
    )


def run_model_for_file(
    jsonl_path: Path,
    md_path: Path,
    root: Path,
    args: argparse.Namespace,
    print_lock: threading.Lock,
    gemini_semaphore: threading.Semaphore | None,
) -> FileRunOutcome:
    cwd = jsonl_path.parent
    prompt, expected_turn_ids, bad_line_count, prompt_mode = build_prompt(jsonl_path, root, args)

    if args.provider == "codex" and prompt_mode == "chunked":
        return run_codex_chunked_for_file(
            jsonl_path=jsonl_path,
            md_path=md_path,
            root=root,
            args=args,
            print_lock=print_lock,
        )

    attempts = max(0, args.retry_on_invalid) + 1
    last_error = "unknown failure"
    last_meta: dict[str, Any] = {"bad_line_count": bad_line_count, "prompt_mode": prompt_mode}

    for attempt in range(1, attempts + 1):
        if args.provider == "gemini":
            ok, message, provider_meta = run_gemini_once(
                prompt=prompt,
                md_path=md_path,
                gemini_model=args.gemini_model,
                gemini_api_key_env=args.gemini_api_key_env,
                timeout_sec=args.timeout_sec,
                dry_run=args.dry_run,
                print_lock=print_lock,
                display_name=jsonl_path.name,
                max_output_tokens=args.gemini_max_output_tokens,
                max_retries=args.gemini_max_retries,
                backoff_sec=args.gemini_backoff_sec,
                semaphore=gemini_semaphore,
            )
        else:
            ok, message, provider_meta = run_codex_once(
                prompt=prompt,
                md_path=md_path,
                cwd=cwd,
                codex_bin=args.codex_bin,
                model=args.model,
                profile=args.profile,
                timeout_sec=args.timeout_sec,
                dry_run=args.dry_run,
                print_lock=print_lock,
            )

        provider_meta["attempt"] = attempt
        provider_meta["bad_line_count"] = bad_line_count
        provider_meta["prompt_mode"] = prompt_mode
        last_meta = provider_meta

        if not ok:
            last_error = message
            if attempt == attempts:
                return FileRunOutcome(
                    ok=False,
                    message=last_error,
                    attempts=attempt,
                    expected_turns=len(expected_turn_ids),
                    provider_meta=last_meta,
                )
            continue

        if message == "dry-run":
            return FileRunOutcome(
                ok=True,
                message="dry-run",
                attempts=attempt,
                expected_turns=len(expected_turn_ids),
                provider_meta=last_meta,
            )

        valid, reason = markdown_is_valid(md_path, expected_turn_ids)
        if valid:
            return FileRunOutcome(
                ok=True,
                message="ok",
                attempts=attempt,
                expected_turns=len(expected_turn_ids),
                provider_meta=last_meta,
            )

        invalid_artifact = persist_invalid_markdown(md_path, attempt)
        last_error = f"invalid markdown: {reason}"
        if invalid_artifact:
            last_error = f"{last_error} | invalid_saved={invalid_artifact}"
        if attempt == attempts:
            return FileRunOutcome(
                ok=False,
                message=last_error,
                attempts=attempt,
                expected_turns=len(expected_turn_ids),
                provider_meta=last_meta,
                invalid_artifact=invalid_artifact,
            )

    return FileRunOutcome(
        ok=False,
        message=last_error,
        attempts=attempts,
        expected_turns=len(expected_turn_ids),
        provider_meta=last_meta,
    )


def process_single_file(
    task: FileTask,
    args: argparse.Namespace,
    root: Path,
    print_lock: threading.Lock,
    log_path: Path,
    log_lock: threading.Lock,
    gemini_semaphore: threading.Semaphore | None,
) -> tuple[Path, str]:
    directory = task.directory
    jsonl_file = task.jsonl_path
    md_file = jsonl_file.with_suffix(".md")
    file_started = datetime.now()
    existing_md_text: str | None = None

    if md_file.exists():
        if not args.overwrite:
            append_log(
                log_path,
                {
                    "ts": now_ts(),
                    "event": "file_done",
                    "status": "skipped",
                    "provider": args.provider,
                    "directory": str(directory),
                    "jsonl_path": str(jsonl_file),
                    "md_path": str(md_file),
                    "reason": "markdown_exists",
                },
                log_lock,
            )
            with print_lock:
                print(f"  ↪️  [{task.index}/{task.total_in_directory}] skipped (already exists): {md_file.name}")
            return directory, "skipped"
        existing_md_text = md_file.read_text(encoding="utf-8")

    outcome = run_model_for_file(
        jsonl_path=jsonl_file,
        md_path=md_file,
        root=root,
        args=args,
        print_lock=print_lock,
        gemini_semaphore=gemini_semaphore,
    )

    elapsed_sec = (datetime.now() - file_started).total_seconds()
    log_payload = {
        "ts": now_ts(),
        "event": "file_done",
        "provider": args.provider,
        "model": args.gemini_model if args.provider == "gemini" else (args.model or "default"),
        "directory": str(directory),
        "jsonl_path": str(jsonl_file),
        "md_path": str(md_file),
        "turns": outcome.expected_turns,
        "attempts_used": outcome.attempts,
        "elapsed_sec": round(elapsed_sec, 3),
        "status": "success" if outcome.ok else "failed",
        "message": outcome.message,
        "provider_meta": outcome.provider_meta,
    }
    if outcome.invalid_artifact:
        log_payload["invalid_artifact"] = outcome.invalid_artifact
    append_log(log_path, log_payload, log_lock)

    if outcome.ok:
        if outcome.message == "dry-run":
            with print_lock:
                print(f"  🧪 [{task.index}/{task.total_in_directory}] dry run: {md_file.name}")
            return directory, "skipped"

        with print_lock:
            print(
                f"  ✅ [{task.index}/{task.total_in_directory}] generated: {md_file.name} "
                f"| turns={outcome.expected_turns} | attempts={outcome.attempts}"
            )
        return directory, "generated"

    recovery_note = ""
    if not args.dry_run:
        if existing_md_text is not None:
            md_file.write_text(existing_md_text, encoding="utf-8")
            failure_sidecar = md_file.with_suffix(md_file.suffix + ".failed")
            write_failure_markdown(failure_sidecar, jsonl_file, outcome.message)
            recovery_note = f" | restored original Markdown, failure note: {failure_sidecar.name}"
        else:
            write_failure_markdown(md_file, jsonl_file, outcome.message)
    with print_lock:
        print(
            f"  ❌ [{task.index}/{task.total_in_directory}] generation failed: {jsonl_file.name} "
            f"| {outcome.message}{recovery_note}"
        )
    return directory, "failed"
