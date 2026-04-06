from __future__ import annotations

from typing import Any

from cortexpilot_orch.gates.diff_gate import _normalize as _normalize_path


def _step_task_id(kind: str, payload: dict[str, Any]) -> str:
    if kind in {"plan", "handoff"}:
        plan_id = str(payload.get("plan_id") or payload.get("name") or "").strip()
        task_id = str(payload.get("task_id") or plan_id).strip()
        return task_id or plan_id
    return str(payload.get("task_id", "")).strip()


def _exclusive_paths_for_step(step: dict[str, Any], payload: dict[str, Any]) -> list[str]:
    raw = step.get("exclusive_paths") or []
    if isinstance(raw, list) and any(str(item).strip() for item in raw):
        return [str(item).strip() for item in raw if str(item).strip()]
    kind = str(step.get("kind", "")).strip().lower()
    if kind == "handoff":
        name = str(step.get("name") or _step_task_id("handoff", payload) or "step").strip()
        return [f"__handoff__/{name}"]
    allowed = payload.get("allowed_paths") if isinstance(payload, dict) else []
    if isinstance(allowed, str):
        allowed = [allowed]
    if isinstance(allowed, (list, tuple, set)):
        return [str(item).strip() for item in allowed if isinstance(item, str) and str(item).strip()]
    return []


def _prefix_before_glob(path: str) -> str:
    for idx, ch in enumerate(path):
        if ch in {"*", "?", "["}:
            return path[:idx]
    return path


def _paths_overlap(left: str, right: str) -> bool:
    a = _normalize_path(left)
    b = _normalize_path(right)
    if not a or not b:
        return True
    a_prefix = _prefix_before_glob(a)
    b_prefix = _prefix_before_glob(b)
    if not a_prefix or not b_prefix:
        return True
    if a_prefix == b_prefix:
        return True
    if a_prefix.startswith(b_prefix.rstrip("/") + "/"):
        return True
    if b_prefix.startswith(a_prefix.rstrip("/") + "/"):
        return True
    return False


def _check_exclusive_paths(steps: list[dict[str, Any]], step_payloads: list[dict[str, Any]]) -> list[str]:
    conflicts: list[str] = []
    resolved: list[tuple[str, list[str]]] = []
    for step, payload in zip(steps, step_payloads):
        name = str(step.get("name", "")).strip() or "step"
        paths = _exclusive_paths_for_step(step, payload)
        if not paths:
            conflicts.append(f"{name}: exclusive_paths empty")
        resolved.append((name, paths))
    for idx, (left_name, left_paths) in enumerate(resolved):
        for right_name, right_paths in resolved[idx + 1 :]:
            for left in left_paths:
                for right in right_paths:
                    if _paths_overlap(left, right):
                        conflicts.append(f"{left_name} <-> {right_name}: {left} vs {right}")
                        break
                if conflicts:
                    continue
    return conflicts


def _normalize_depends(depends: Any) -> list[str]:
    if isinstance(depends, str):
        depends = [depends]
    if not isinstance(depends, list):
        return []
    return [str(item).strip() for item in depends if str(item).strip()]
