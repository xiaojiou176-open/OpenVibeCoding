# OpenVibeCoding coding-agent bundle

This bundle keeps one repo-owned starter pack compatible with:

- Codex local marketplace installs
- Claude Code local `--plugin-dir` development
- OpenClaw compatible bundle installs from a local path or link

It is a local example lane, not OpenVibeCoding's canonical public root. The
read-only MCP surface stays primary, and the adoption-router public skill
packet stays secondary.

## What is inside

- `.codex-plugin/plugin.json`: Codex bundle metadata
- `.claude-plugin/plugin.json`: Claude Code plugin metadata
- `.mcp.json`: plugin-scoped read-only MCP wiring
- `skills/openvibecoding-adoption-router/SKILL.md`: route the job to the right
  OpenVibeCoding lane without overclaiming
- `skills/openvibecoding-adoption-router/manifest.yaml`: registry-shaped skill
  metadata with semver, host compatibility, and non-claim boundaries
- `commands/openvibecoding-proof.md`: Claude-style proof-first command
- `agents/openvibecoding-reviewer.md`: Claude-style focused reviewer prompt
- `bin/run-openvibecoding-readonly-mcp.sh`: repo-aware wrapper for the real
  read-only MCP server

## Skill packaging truth

The adoption-router skill now ships with both:

- `SKILL.md` for repo-owned playbook behavior
- `manifest.yaml` for registry-shaped metadata and semver

That means the bundle can honestly say it already contains one **cross-tool
skill artifact** for Codex / Claude Code / OpenClaw style installs. It still
does **not** mean a live public listing already exists in any of those
ecosystems.

## How the MCP wrapper behaves

The wrapper works in two truthful modes:

1. If the bundle still lives inside a real OpenVibeCoding clone, it auto-discovers
   the repo root.
2. If the bundle is installed somewhere else, set `OPENVIBECODING_REPO_ROOT` to
   the real clone path before you load the plugin.

The wrapper always runs the real stdio server through the repo-owned top-level wrapper:

```bash
bash /absolute/path/to/OpenVibeCoding/scripts/run_openvibecoding_readonly_mcp.sh
```

Under the hood that wrapper still launches `python3 -m openvibecoding_orch.cli mcp-readonly-server`
with the repo-local Python path exported first. It never upgrades the public
contract into hosted or write-capable MCP.
