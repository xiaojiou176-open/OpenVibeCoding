from __future__ import annotations

import json
from pathlib import Path


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_worker_mcp_tools_alignment_across_policy_registries() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    policy_registry = _load_json(repo_root / "policies" / "agent_registry.json")
    allowlist = _load_json(repo_root / "policies" / "mcp_allowlist.json")
    tools_registry = _load_json(repo_root / "tooling" / "registry.json")

    expected_worker_tools = {"01-filesystem", "codex", "sampling", "aider", "continue", "open_interpreter"}

    workers = [a for a in policy_registry.get("agents", []) if a.get("role") == "WORKER"]
    assert workers, "WORKER entries must exist in policy registry"
    for worker in workers:
        tools = set((worker.get("capabilities") or {}).get("mcp_tools", []))
        assert tools == expected_worker_tools, (
            f"worker {worker.get('agent_id')} drifted mcp_tools: {sorted(tools)}"
        )

    allow_set = set(allowlist.get("allow", []))
    deny_set = set(allowlist.get("deny", []))
    integrated_set = set(tools_registry.get("integrated", []))

    assert expected_worker_tools.issubset(allow_set), "worker tools must be allowlisted"
    assert expected_worker_tools.issubset(integrated_set), "worker tools must be integrated"
    assert not expected_worker_tools.intersection(deny_set), "worker tools cannot be denied"

    # Canonical key is open_interpreter; hyphen alias is runtime compatibility only.
    assert "open-interpreter" not in allow_set
    assert "open-interpreter" not in integrated_set
