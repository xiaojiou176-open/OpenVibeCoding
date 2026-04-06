from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FileTask:
    directory: Path
    jsonl_path: Path
    index: int
    total_in_directory: int


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def discover_directories(root: Path, include: list[str], exclude: set[str]) -> list[Path]:
    if include:
        resolved: list[Path] = []
        for item in include:
            candidate = (root / item).resolve()
            if candidate.is_dir() and _is_within(candidate, root):
                if candidate.name not in exclude:
                    resolved.append(candidate)
                continue
            matches = [
                entry
                for entry in root.iterdir()
                if entry.is_dir() and entry.name == item and entry.name not in exclude
            ]
            resolved.extend(matches)
        return sorted({path for path in resolved})

    child_dirs = sorted([entry for entry in root.iterdir() if entry.is_dir() and entry.name not in exclude])
    if any(root.glob("*.jsonl")):
        return [root]
    return child_dirs


def find_jsonl_files(directory: Path, limit: int) -> list[Path]:
    files = sorted(directory.rglob("*.jsonl"))
    return files[:limit] if limit > 0 else files


def collect_file_tasks(directories: list[Path], limit_per_dir: int) -> tuple[list[FileTask], dict[Path, int]]:
    tasks: list[FileTask] = []
    totals: dict[Path, int] = {}
    for directory in directories:
        files = find_jsonl_files(directory, limit_per_dir)
        totals[directory] = len(files)
        for index, jsonl_path in enumerate(files, 1):
            tasks.append(
                FileTask(
                    directory=directory,
                    jsonl_path=jsonl_path,
                    index=index,
                    total_in_directory=len(files),
                )
            )
    return tasks, totals
