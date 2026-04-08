# CortexPilot Adoption Router

This bundle teaches an agent how to connect the published CortexPilot read-only
MCP package and choose the right public adoption lane.

## What the agent learns here

- how to install the published `cortexpilot-orchestrator==0.1.0a4` MCP package
- which read-only CortexPilot tools exist and which are safe-first
- how to choose between run/workflow inspection, queue/approval reads, and
  proof/incident reads
- which hosted or write-capable claims stay out of bounds

## Included files

- `SKILL.md` — the progressive-disclosure prompt for the agent
- `references/mcp-install.md` — exact install snippets for OpenHands/OpenClaw
- `references/tool-map.md` — the stable read-only tool inventory
- `references/example-tasks.md` — example asks and expected return shape
- `manifest.yaml` — registry metadata used by hosts such as ClawHub

## The shortest install path

Use the published package, not a repo-local checkout:

```bash
uvx --from cortexpilot-orchestrator==0.1.0a4 cortexpilot-readonly-mcp
```

If the host needs a saved MCP config snippet, use the host-specific examples in
`references/mcp-install.md`.

## Hard boundaries

- no hosted operator service
- no write-capable public MCP
- no first-party marketplace claim unless that host independently confirms it
