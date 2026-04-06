from __future__ import annotations

from pathlib import Path
from typing import Iterable


def normalize_path(path: str) -> str:
    return Path(path.strip()).as_posix().lstrip("./")


def is_allowed_path(path: str, allowed_paths: Iterable[str]) -> bool:
    target = normalize_path(path)
    for raw in allowed_paths:
        allowed = normalize_path(str(raw))
        if not allowed:
            continue
        if target == allowed:
            return True
        if target.startswith(allowed.rstrip("/") + "/"):
            return True
    return False
