# Install The Current Live Public OpenVibeCoding MCP

Use the current live public PyPI package, not a repo-local checkout.

## Published package

- package: `openvibecoding-orchestrator==0.1.0a4`
- executable: `openvibecoding-readonly-mcp`
- transport: `stdio`

Current truth:

- the executable uses the OpenVibeCoding name
- the primary live published PyPI package now also uses the OpenVibeCoding name
- the legacy package `cortexpilot-orchestrator` remains only as a compatibility alias

## OpenHands example

Use `OPENHANDS_MCP_CONFIG.json` as the starting point for your host config.

## OpenClaw example

Use `OPENCLAW_MCP_CONFIG.json` as the starting point for your host config.

## Smoke check

Use a minimal MCP handshake and `tools/list` request after the host attaches the
server.
