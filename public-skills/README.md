This directory holds OpenVibeCoding public skill bundles for external skill
registries.

Each bundle here must ship four things together:

- `SKILL.md`: the agent-facing instructions
- `README.md`: the human-facing install and usage guide
- `references/`: bundle-local install, tool-map, and lane notes
- `manifest.yaml`: registry metadata for hosts such as ClawHub

The bundle is only valid if an agent can answer all four questions without
leaving this directory:

1. How do I install the published OpenVibeCoding MCP package?
2. Which read-only tools does the MCP expose?
3. Which lane should I choose first?
4. Which claims remain out of bounds?
