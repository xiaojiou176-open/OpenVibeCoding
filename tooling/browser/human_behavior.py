from __future__ import annotations

import random
import time
from typing import Any


def apply_human_behavior(page: Any, *, enabled: bool, level: str = "low") -> dict[str, Any]:
    if not enabled:
        return {"enabled": False, "applied": False, "level": level}

    profile = level.lower().strip() or "low"
    if profile not in {"low", "medium", "high"}:
        profile = "low"

    steps = {
        "low": {"moves": 1, "scrolls": 1, "delay": (120, 280)},
        "medium": {"moves": 2, "scrolls": 2, "delay": (180, 420)},
        "high": {"moves": 3, "scrolls": 3, "delay": (240, 620)},
    }[profile]
    rng = random.Random(time.time())

    warnings: list[str] = []

    for _ in range(steps["moves"]):
        try:
            x = rng.randint(80, 900)
            y = rng.randint(80, 700)
            page.mouse.move(x, y)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"mouse_move_failed: {exc}")
            break

    for _ in range(steps["scrolls"]):
        try:
            page.evaluate("window.scrollBy(0, Math.max(120, window.innerHeight * 0.35));")
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"scroll_failed: {exc}")
            break

    try:
        delay_ms = rng.randint(*steps["delay"])
        page.wait_for_timeout(delay_ms)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"delay_failed: {exc}")

    return {
        "enabled": True,
        "applied": True,
        "level": profile,
        "warnings": warnings,
    }
