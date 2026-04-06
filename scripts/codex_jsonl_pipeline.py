#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from codex_jsonl_pipeline_discovery import collect_file_tasks, discover_directories
from codex_jsonl_pipeline_execution import process_single_file
from codex_jsonl_pipeline_logging import append_log, ensure_runtime_log, now_ts

DEFAULT_CONCURRENCY_BASELINE = 6


@dataclass
class TaskResult:
    directory: Path
    total: int = 0
    generated: int = 0
    skipped: int = 0
    failed: int = 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Concurrent pipeline: refine JSONL conversations turn by turn into same-name Markdown.",
    )
    parser.add_argument("--root", required=True, help="Root directory for exported JSONL files")
    parser.add_argument(
        "--include-dir",
        action="append",
        default=[],
        help="Only process the selected subdirectories (repeatable); accepts a directory name or relative path.",
    )
    parser.add_argument(
        "--exclude-dir",
        action="append",
        default=[],
        help="Exclude subdirectories (repeatable); matches by directory name.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_CONCURRENCY_BASELINE,
        help=f"File-level concurrency. Default: {DEFAULT_CONCURRENCY_BASELINE}",
    )
    parser.add_argument("--limit-per-dir", type=int, default=0, help="Per-directory processing limit. Use 0 for all files")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing Markdown files with the same name")
    parser.add_argument("--dry-run", action="store_true", help="Print the plan only; do not call the model")
    parser.add_argument("--codex-bin", default="codex", help="Path to the codex executable")
    parser.add_argument(
        "--provider",
        choices=["codex", "gemini"],
        default="codex",
        help="Model provider: codex (local/gateway) or gemini (cloud API)",
    )
    parser.add_argument("--model", default="", help="Optional; forwarded to codex exec --model")
    parser.add_argument("--profile", default="", help="Optional; forwarded to codex exec --profile")
    parser.add_argument(
        "--codex-prompt-mode",
        choices=["auto", "embedded", "path", "chunked"],
        default="auto",
        help="codex prompt mode: auto (default, chunk long inputs), embedded (inline turns), path (force file-path reads), or chunked (force chunking)",
    )
    parser.add_argument(
        "--codex-path-threshold-turns",
        type=int,
        default=999999,
        help="When codex-prompt-mode=auto, switch to path reads once the turn count reaches this threshold. Default stays high to avoid accidental switching.",
    )
    parser.add_argument(
        "--codex-chunk-threshold-turns",
        type=int,
        default=40,
        help="When codex-prompt-mode=auto, use chunked mode once the turn count reaches this threshold. Default: 40.",
    )
    parser.add_argument(
        "--codex-chunk-size",
        type=int,
        default=30,
        help="Turns per chunk in chunked mode. Recommended: 30-50. Default: 30.",
    )
    parser.add_argument(
        "--gemini-model",
        default="gemini-2.5-flash",
        help="Gemini model name (used only when provider=gemini)",
    )
    parser.add_argument(
        "--gemini-api-key-env",
        default="GEMINI_API_KEY",
        help="Environment variable that holds the Gemini API key",
    )
    parser.add_argument(
        "--gemini-max-output-tokens",
        type=int,
        default=8192,
        help="Gemini maximum output token limit. Default: 8192",
    )
    parser.add_argument(
        "--gemini-max-retries",
        type=int,
        default=2,
        help="Retry count for Gemini request failures (429/5xx/network failures only)",
    )
    parser.add_argument(
        "--gemini-backoff-sec",
        type=float,
        default=1.5,
        help="Base seconds for Gemini exponential backoff. Default: 1.5",
    )
    parser.add_argument(
        "--gemini-max-concurrency",
        type=int,
        default=DEFAULT_CONCURRENCY_BASELINE,
        help=f"Global Gemini request concurrency limit. Default: {DEFAULT_CONCURRENCY_BASELINE}",
    )
    parser.add_argument("--timeout-sec", type=int, default=180, help="Per-file timeout in seconds")
    parser.add_argument(
        "--max-chars-per-side",
        type=int,
        default=1600,
        help="In embedded mode, maximum characters per user/assistant side for each turn",
    )
    parser.add_argument(
        "--retry-on-invalid",
        type=int,
        default=1,
        help="Retry count when the output format is invalid. Default: 1",
    )
    return parser
def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)

    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        print(f"❌ root directory does not exist: {root}", file=sys.stderr)
        return 2

    workers = max(1, args.workers)
    excludes = set(args.exclude_dir)
    directories = discover_directories(root, args.include_dir, excludes)
    if not directories:
        print("⚠️ no eligible directories found.")
        return 0

    file_tasks, per_directory_total = collect_file_tasks(directories, args.limit_per_dir)
    if not file_tasks:
        print("⚠️ no JSONL files found under the selected directories.")
        return 0

    gemini_semaphore: threading.Semaphore | None = None
    if args.provider == "gemini":
        gemini_semaphore = threading.BoundedSemaphore(max(1, args.gemini_max_concurrency))

    print("🚀 JSONL→Markdown concurrent pipeline starting")
    print(f"- root: {root}")
    print(f"- directories: {len(directories)}")
    print(f"- files: {len(file_tasks)}")
    print(f"- workers: {workers} (file-level concurrency)")
    print(f"- provider: {args.provider}")
    if args.provider == "codex":
        print(f"- codex_prompt_mode: {args.codex_prompt_mode}")
        print(f"- codex_path_threshold_turns: {max(1, args.codex_path_threshold_turns)}")
        print(f"- codex_chunk_threshold_turns: {max(1, args.codex_chunk_threshold_turns)}")
        print(f"- codex_chunk_size: {max(1, args.codex_chunk_size)}")
    if args.provider == "gemini":
        print(f"- gemini_model: {args.gemini_model}")
        print(f"- gemini_auth_env_configured: {bool(args.gemini_api_key_env)}")
        print(f"- gemini_max_output_tokens: {args.gemini_max_output_tokens}")
        print(f"- gemini_max_retries: {args.gemini_max_retries}")
        print(f"- gemini_backoff_sec: {args.gemini_backoff_sec}")
        print(f"- gemini_max_concurrency: {max(1, args.gemini_max_concurrency)}")
    print(f"- dry_run: {args.dry_run}")
    print(f"- overwrite: {args.overwrite}")

    log_path = ensure_runtime_log()
    log_lock = threading.Lock()
    append_log(
        log_path,
        {
            "ts": now_ts(),
            "event": "pipeline_start",
            "root": str(root),
            "workers": workers,
            "dry_run": args.dry_run,
            "provider": args.provider,
            "codex_prompt_mode": args.codex_prompt_mode,
            "codex_path_threshold_turns": max(1, args.codex_path_threshold_turns),
            "codex_chunk_threshold_turns": max(1, args.codex_chunk_threshold_turns),
            "codex_chunk_size": max(1, args.codex_chunk_size),
            "directories": [str(directory) for directory in directories],
            "file_count": len(file_tasks),
        },
        log_lock,
    )

    print_lock = threading.Lock()
    directory_results: dict[Path, TaskResult] = {
        directory: TaskResult(directory=directory, total=per_directory_total.get(directory, 0))
        for directory in directories
    }

    with print_lock:
        for directory in directories:
            print(f"\n📂 directory started: {directory} | JSONL={per_directory_total.get(directory, 0)}")

    with ThreadPoolExecutor(max_workers=min(workers, len(file_tasks))) as pool:
        future_map = {
            pool.submit(
                process_single_file,
                task,
                args,
                root,
                print_lock,
                log_path,
                log_lock,
                gemini_semaphore,
            ): task
            for task in file_tasks
        }
        for future in as_completed(future_map):
            task = future_map[future]
            try:
                directory, status = future.result()
                result = directory_results[directory]
                if status == "generated":
                    result.generated += 1
                elif status == "skipped":
                    result.skipped += 1
                else:
                    result.failed += 1
            except Exception as exc:  # noqa: BLE001
                result = directory_results[task.directory]
                result.failed += 1
                append_log(
                    log_path,
                    {
                        "ts": now_ts(),
                        "event": "file_crash",
                        "directory": str(task.directory),
                        "jsonl_path": str(task.jsonl_path),
                        "error": str(exc),
                    },
                    log_lock,
                )
                print(f"❌ file execution exception: {task.jsonl_path} | {exc}", file=sys.stderr)

    results = [directory_results[directory] for directory in directories]
    for result in results:
        append_log(
            log_path,
            {
                "ts": now_ts(),
                "event": "directory_done",
                "directory": str(result.directory),
                "total": result.total,
                "generated": result.generated,
                "skipped": result.skipped,
                "failed": result.failed,
            },
            log_lock,
        )
        with print_lock:
            print(
                f"📁 directory finished: {result.directory.name} | total={result.total} "
                f"generated={result.generated} skipped={result.skipped} failed={result.failed}"
            )

    total_files = sum(item.total for item in results)
    total_generated = sum(item.generated for item in results)
    total_skipped = sum(item.skipped for item in results)
    total_failed = sum(item.failed for item in results)

    append_log(
        log_path,
        {
            "ts": now_ts(),
            "event": "pipeline_done",
            "total_files": total_files,
            "generated": total_generated,
            "skipped": total_skipped,
            "failed": total_failed,
        },
        log_lock,
    )

    print("\n📊 Summary")
    print(f"- total files: {total_files}")
    print(f"- generated: {total_generated}")
    print(f"- skipped: {total_skipped}")
    print(f"- failed: {total_failed}")
    print(f"- log: {log_path}")

    return 1 if total_failed > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
