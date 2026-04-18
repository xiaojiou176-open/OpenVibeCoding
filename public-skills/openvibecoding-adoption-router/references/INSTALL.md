# Install The Current Live Public OpenVibeCoding MCP

Use the current live public PyPI package, not a repo-local checkout.

## Published package

- package: `cortexpilot-orchestrator==0.1.0a4`
- executable: `openvibecoding-readonly-mcp`
- transport: `stdio`

Current truth:

- the executable already uses the OpenVibeCoding name
- the live published PyPI package still uses the legacy live name
  `cortexpilot-orchestrator`
- do not claim that `openvibecoding-orchestrator` is live until the renamed
  package is actually published

## OpenHands example

Use `OPENHANDS_MCP_CONFIG.json` as the starting point for your host config.

## OpenClaw example

Use `OPENCLAW_MCP_CONFIG.json` as the starting point for your host config.

## Smoke check

Use a minimal MCP handshake and `tools/list` request after the host attaches the
server.
