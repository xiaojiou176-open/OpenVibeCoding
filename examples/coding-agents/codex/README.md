# Codex example

This folder shows the narrowest truthful OpenVibeCoding setup for Codex:

- one local marketplace example for the repo-owned skill bundle
- one shared read-only MCP example for the real control-plane inspection path

## What is here

- `marketplace.example.json`: copy to `.agents/plugins/marketplace.json` when
  you want Codex to discover the local OpenVibeCoding bundle from this repo clone
- `../mcp/readonly.mcp.json.example`: shared read-only MCP config example
- `../plugin-bundles/openvibecoding-coding-agent-bundle/`: compatible local skill
  bundle with Codex metadata plus the same repo-owned adoption router skill
- `../plugin-bundles/openvibecoding-coding-agent-bundle/skills/openvibecoding-adoption-router/manifest.yaml`:
  registry-shaped metadata for that shared skill

## Suggested setup

1. Copy `marketplace.example.json` to the Codex marketplace path used by your
   repo or home config.
2. Copy `../mcp/readonly.mcp.json.example` to the MCP config path you use for
   Codex and replace `__OPENVIBECODING_REPO_ROOT__`.
3. Keep the read order aligned with OpenVibeCoding truth sources:
   - `README.md`
   - `docs/README.md`
   - `AGENTS.md`
   - the public compatibility / integration / MCP guides

## Expected success

- the repo-local proof-first path still works before and after you copy the
  Codex files
- the local marketplace seed points at your real OpenVibeCoding checkout, not at a
  stale relative path
- you can route back through `docs/use-cases/index.html` and still explain the
  same Workflow Cases / Proof & Replay loop without claiming an official Codex
  listing

## Boundary

- This is a local marketplace example, not a published Codex directory entry.
- The MCP example is read-only.
- Hosted, write-capable MCP, and official listing claims remain out of scope.
