from __future__ import annotations

import re

from fastapi import HTTPException


_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def validate_run_id(run_id: str, *, error_code: str = "RUN_ID_INVALID") -> str:
    if not isinstance(run_id, str):
        raise HTTPException(status_code=400, detail={"code": error_code})
    normalized = run_id.strip()
    if not normalized:
        raise HTTPException(status_code=400, detail={"code": "RUN_ID_REQUIRED"})
    if not _RUN_ID_RE.fullmatch(normalized) or ".." in normalized:
        raise HTTPException(status_code=400, detail={"code": error_code})
    return normalized
