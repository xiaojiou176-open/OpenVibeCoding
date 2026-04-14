from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SessionBinding:
    pm_session_id: str
    run_id: str
    binding_type: str
    bound_at: str


class SessionIndexService:
    def __init__(self, runtime_root: Path) -> None:
        self._runtime_root = runtime_root

    def _intakes_root(self) -> Path:
        return self._runtime_root / "intakes"

    def list_session_ids(self) -> list[str]:
        root = self._intakes_root()
        if not root.exists():
            return []
        ids = [entry.name for entry in root.glob("*") if entry.is_dir()]
        ids.sort()
        return ids

    def read_session_files(self, pm_session_id: str) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
        intake_dir = self._intakes_root() / pm_session_id
        if not intake_dir.exists() or not intake_dir.is_dir():
            return {}, {}, []

        intake_raw = self._read_json(intake_dir / "intake.json", {})
        response_raw = self._read_json(intake_dir / "response.json", {})
        events = self._read_jsonl(intake_dir / "events.jsonl")

        intake = intake_raw if isinstance(intake_raw, dict) else {}
        response = response_raw if isinstance(response_raw, dict) else {}
        return intake, response, events

    def derive_session_source(self, intake: dict[str, Any], response: dict[str, Any]) -> str:
        for key in ["session_source", "source", "origin"]:
            value = intake.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip().lower()
        for key in ["session_source", "source", "origin"]:
            value = response.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip().lower()
        return "intake"

    def derive_bindings(
        self,
        pm_session_id: str,
        response: dict[str, Any],
        intake_events: list[dict[str, Any]],
    ) -> list[SessionBinding]:
        bindings: list[SessionBinding] = []
        seen: set[str] = set()

        def _add(run_id: Any, binding_type: str, bound_at: Any) -> None:
            if not isinstance(run_id, str):
                return
            cleaned = run_id.strip()
            if not cleaned or cleaned in seen:
                return
            seen.add(cleaned)
            ts = bound_at.strip() if isinstance(bound_at, str) else ""
            bindings.append(
                SessionBinding(
                    pm_session_id=pm_session_id,
                    run_id=cleaned,
                    binding_type=binding_type,
                    bound_at=ts,
                )
            )

        for event in intake_events:
            if not isinstance(event, dict):
                continue
            event_name = str(event.get("event") or "").strip().upper()
            if event_name == "INTAKE_RUN":
                _add(event.get("run_id"), "child", event.get("ts"))
            elif event_name == "INTAKE_CHAIN_RUN":
                _add(event.get("run_id"), "primary", event.get("ts"))

        _add(response.get("chain_run_id"), "primary", response.get("updated_at") or response.get("created_at"))

        raw_chain_ids = response.get("chain_run_ids")
        if isinstance(raw_chain_ids, list):
            for item in raw_chain_ids:
                _add(item, "child", response.get("updated_at") or response.get("created_at"))

        return bindings

    @staticmethod
    def _read_json(path: Path, default: object) -> object:
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return default

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for raw in path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = {"raw": raw}
            if isinstance(parsed, dict):
                rows.append(parsed)
        return rows
