# Claude Code example

This folder shows a truthful OpenVibeCoding starter for Claude Code style
workflows without inventing a published marketplace package.

## What is here

- `.claude/commands/openvibecoding-proof.md`: a slash-command style playbook
- `.claude/agents/openvibecoding-reviewer.md`: a focused reviewer/subagent prompt
- `project.mcp.json`: a project-local MCP example for the real read-only server
- `../mcp/readonly.mcp.json.example`: the shared read-only MCP config example
- `../plugin-bundles/openvibecoding-coding-agent-bundle/`: a local plugin-dir
  bundle with the same skill plus plugin-scoped MCP wiring
- `../plugin-bundles/openvibecoding-coding-agent-bundle/skills/openvibecoding-adoption-router/manifest.yaml`:
  registry-shaped metadata for the shared skill artifact

## Suggested setup

1. Copy `.claude/commands/` and `.claude/agents/` into your project.
2. Copy `project.mcp.json` into your project root as `.mcp.json`, or use
   `../mcp/readonly.mcp.json.example` as the shared host-level template and
   replace `__OPENVIBECODING_REPO_ROOT__`.
3. Keep the read order aligned with OpenVibeCoding truth sources:
   - `README.md`
   - `docs/README.md`
   - `AGENTS.md`
   - the public compatibility / integration / MCP guides

## Expected success

- the project-local `.mcp.json` still points at the same repo-root read-only MCP server
- the copied `.claude/commands/openvibecoding-proof.md` playbook routes you back to
  the same proof-first surfaces instead of inventing a new hosted/plugin story
- the result is still described as local/project adoption, not as a published
  Claude Code marketplace listing

## Boundary

- This is a project-local example plus a local plugin-dir seed, not a published
  marketplace listing.
- The MCP example is read-only.
- Hosted, write-capable MCP, and official plugin claims remain out of scope.
