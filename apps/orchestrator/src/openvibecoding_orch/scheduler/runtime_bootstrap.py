from __future__ import annotations

from pathlib import Path

from openvibecoding_orch.config import load_config


def ensure_runtime_dirs() -> dict[str, Path]:
    cfg = load_config()
    targets = {
        "runtime_root": cfg.runtime_root,
        "runs_root": cfg.runs_root,
        "worktree_root": cfg.worktree_root,
        "logs_root": cfg.logs_root,
        "cache_root": cfg.cache_root,
    }
    for path in targets.values():
        path.mkdir(parents=True, exist_ok=True)
    return targets
