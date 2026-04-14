from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openvibecoding_orch.config import load_config


def _now_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


# -------------------------------------------------------------------
# Intake Store
# -------------------------------------------------------------------


class IntakeStore:
    def __init__(self, root: Path | None = None) -> None:
        cfg = load_config()
        self._root = root or (cfg.runtime_root / "intakes")
        self._root.mkdir(parents=True, exist_ok=True)

    def _resolve_intake_path(self, intake_id: str, *, create: bool, allow_generate: bool = False) -> Path:
        raw = str(intake_id).strip()
        if not raw:
            if allow_generate:
                raw = uuid.uuid4().hex
            else:
                raise ValueError("invalid intake_id")
        root = self._root.resolve()
        candidate = (root / raw).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError("invalid intake_id") from exc
        if create:
            candidate.mkdir(parents=True, exist_ok=True)
        return candidate

    def _intake_dir(self, intake_id: str) -> Path:
        return self._resolve_intake_path(intake_id, create=True, allow_generate=True)

    def intake_exists(self, intake_id: str) -> bool:
        try:
            return self._resolve_intake_path(intake_id, create=False).exists()
        except ValueError:
            return False

    def create(self, payload: dict[str, Any]) -> str:
        intake_id = uuid.uuid4().hex
        path = self._resolve_intake_path(intake_id, create=True)
        stored = dict(payload)
        stored.setdefault("intake_id", intake_id)
        stored.setdefault("created_at", _now_ts())
        (path / "intake.json").write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")
        self.append_event(intake_id, {"event": "INTAKE_CREATED", "ts": _now_ts()})
        return intake_id

    def append_event(self, intake_id: str, event: dict[str, Any]) -> None:
        path = self._resolve_intake_path(intake_id, create=True) / "events.jsonl"
        entry = dict(event)
        if "ts" not in entry:
            entry["ts"] = _now_ts()
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def write_response(self, intake_id: str, payload: dict[str, Any]) -> Path:
        path = self._resolve_intake_path(intake_id, create=True) / "response.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self.append_event(intake_id, {"event": "INTAKE_RESPONSE_WRITTEN", "ts": _now_ts()})
        return path

    def read_intake(self, intake_id: str) -> dict[str, Any]:
        try:
            intake_dir = self._resolve_intake_path(intake_id, create=False)
        except ValueError:
            return {}
        path = intake_dir / "intake.json"
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def read_response(self, intake_id: str) -> dict[str, Any]:
        try:
            intake_dir = self._resolve_intake_path(intake_id, create=False)
        except ValueError:
            return {}
        path = intake_dir / "response.json"
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def list_intakes(self) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for intake_dir in sorted(self._root.glob("*")):
            if not intake_dir.is_dir():
                continue
            intake_id = intake_dir.name
            intake = {}
            intake_path = intake_dir / "intake.json"
            if intake_path.exists():
                try:
                    intake = json.loads(intake_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    intake = {}
            entries.append(
                {
                    "intake_id": intake_id,
                    "objective": intake.get("objective", ""),
                    "created_at": intake.get("created_at", ""),
                }
            )
        return entries
