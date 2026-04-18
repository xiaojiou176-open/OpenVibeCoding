# OpenVibeCoding Adoption Router

This bundle teaches an agent how to connect the current live public OpenVibeCoding
read-only MCP package and choose the right public adoption lane.

This is OpenVibeCoding's secondary public adoption lane. The read-only MCP package
plus the Official MCP Registry entry remain the primary machine-readable front
door, and local coding-agent bundles stay example-only.

## What the agent learns here

- how to install the current live legacy package
  `cortexpilot-orchestrator==0.1.0a4` for the OpenVibeCoding read-only MCP
- which read-only OpenVibeCoding tools exist and which are safe-first
- how to choose between run/workflow inspection, queue/approval reads, and
  proof/incident reads
- which hosted or write-capable claims stay out of bounds

## Included files

- `SKILL.md` — the progressive-disclosure prompt for the agent
- `README.md` — the human-facing overview for reviewers and operators
- `manifest.yaml` — listing metadata for host skill registries
- `references/README.md` — the local index for every supporting file
- `references/INSTALL.md` — exact install snippets for OpenHands/OpenClaw
- `references/OPENHANDS_MCP_CONFIG.json` — a ready-to-edit `mcpServers` snippet
- `references/OPENCLAW_MCP_CONFIG.json` — a ready-to-edit `mcp.servers` snippet
- `references/CAPABILITIES.md` — the stable read-only tool inventory
- `references/DEMO.md` — the first-success walkthrough and expected return shape
- `references/TROUBLESHOOTING.md` — the first checks when launch or inspection fails

## The shortest install path

Use the live public package, not a repo-local checkout:

```bash
uvx --from cortexpilot-orchestrator==0.1.0a4 openvibecoding-readonly-mcp
```

Today the executable is already OpenVibeCoding-branded, but the published PyPI
package still uses the legacy live name `cortexpilot-orchestrator`. Do not
claim that the OpenVibeCoding-branded package name is live until the renamed
publication actually exists.

If the host needs a saved MCP config snippet, use the host-specific examples in
`references/INSTALL.md`.

## Hard boundaries

- no hosted operator service
- no write-capable public MCP
- no first-party marketplace claim unless that host independently confirms it
