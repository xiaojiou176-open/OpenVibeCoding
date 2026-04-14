from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable

from fastapi import HTTPException


_logger = logging.getLogger(__name__)
_ErrorDetailFn = Callable[[str], dict[str, str]]


def safe_artifact_target(run_id: str, name: str, *, runs_root: Path, error_detail_fn: _ErrorDetailFn) -> Path:
    if not isinstance(name, str) or not name.strip():
        raise HTTPException(status_code=400, detail=error_detail_fn("ARTIFACT_NAME_REQUIRED"))
    requested = Path(name)
    if requested.is_absolute():
        raise HTTPException(status_code=400, detail=error_detail_fn("ARTIFACT_PATH_INVALID"))
    artifacts_dir = (runs_root / run_id / "artifacts").resolve()
    target = (artifacts_dir / requested).resolve()
    try:
        target.relative_to(artifacts_dir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=error_detail_fn("ARTIFACT_PATH_ESCAPE")) from exc
    return target


def read_artifact_file(run_id: str, name: str, *, runs_root: Path, error_detail_fn: _ErrorDetailFn) -> object | None:
    try:
        target = safe_artifact_target(run_id, name, runs_root=runs_root, error_detail_fn=error_detail_fn)
    except HTTPException:
        return None
    if not target.exists():
        return None
    try:
        if target.suffix == ".json":
            return json.loads(target.read_text(encoding="utf-8"))
        if target.suffix == ".jsonl":
            lines: list[dict] = []
            for raw in target.read_text(encoding="utf-8").splitlines():
                if not raw.strip():
                    continue
                try:
                    lines.append(json.loads(raw))
                except json.JSONDecodeError:
                    lines.append({"raw": raw})
            return lines
        return target.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        _logger.debug("artifact_helpers: read_artifact_file failed for %s/%s: %s", run_id, name, exc)
        return None


def read_report_file(run_id: str, name: str, *, runs_root: Path) -> object | None:
    report_path = runs_root / run_id / "reports" / name
    if not report_path.exists():
        return None
    try:
        return json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return report_path.read_text(encoding="utf-8")
