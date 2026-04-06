from __future__ import annotations

from pathlib import Path
from typing import Any

from cortexpilot_orch.scheduler import core_helpers


def artifact_ref(name: str, rel_path: str, content: str, media_type: str = "text/plain") -> dict[str, Any]:
    return core_helpers.artifact_ref(name, rel_path, content, media_type)


def artifact_ref_from_path(name: str, run_dir: Path, rel_path: str, media_type: str = "text/plain") -> dict[str, Any]:
    return core_helpers.artifact_ref_from_path(name, run_dir, rel_path, media_type)


def artifact_ref_from_hash(
    name: str,
    rel_path: str,
    sha256: str,
    size_bytes: int,
    media_type: str | None = None,
) -> dict[str, Any]:
    return core_helpers.artifact_ref_from_hash(name, rel_path, sha256, size_bytes, media_type)


def guess_media_type(path: str) -> str | None:
    return core_helpers.guess_media_type(path)


def artifact_refs_from_hashes(run_dir: Path, hashes: dict[str, str]) -> list[dict[str, Any]]:
    return core_helpers.artifact_refs_from_hashes(run_dir, hashes)
