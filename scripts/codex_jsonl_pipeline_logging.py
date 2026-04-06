from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


def now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def write_failure_markdown(md_path: Path, jsonl_path: Path, reason: str) -> None:
    content = (
        f"# {jsonl_path.stem} - Turn-by-turn conversation refinement\n\n"
        f"> Automatic generation failed: {reason}\n\n"
        "## File info\n"
        f"- Source file: `{jsonl_path.name}`\n"
        f"- Failure time: {now_ts()}\n\n"
        "## Notes\n"
        "- The pipeline attempted to call the model for turn-by-turn refinement, but this run failed.\n"
        "- Check the runtime log and the `.invalid` file before retrying.\n"
    )
    md_path.write_text(content, encoding="utf-8")


def ensure_runtime_log() -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    log_dir = repo_root / ".runtime-cache" / "logs" / "runtime"
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return log_dir / f"codex_jsonl_pipeline_{stamp}.jsonl"


def append_log(log_path: Path, payload: dict[str, Any], log_lock: threading.Lock) -> None:
    with log_lock:
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
