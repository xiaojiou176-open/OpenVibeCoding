# Install The Published OpenVibeCoding MCP

Use the published PyPI package, not a repo-local checkout.

## Published package

- package: `openvibecoding-orchestrator==0.1.0a4`
- executable: `openvibecoding-readonly-mcp`
- transport: `stdio`

## OpenHands example

Add the server to `~/.openhands/config.toml`:

```toml
[mcp]
stdio_servers = [
  { name = "openvibecoding-readonly", command = "uvx", args = ["--from", "openvibecoding-orchestrator==0.1.0a4", "openvibecoding-readonly-mcp"] }
]
```

## OpenClaw example

Add the server to your saved MCP server config:

```json
{
  "mcp": {
    "servers": {
      "openvibecoding-readonly": {
        "command": "uvx",
        "args": ["--from", "openvibecoding-orchestrator==0.1.0a4", "openvibecoding-readonly-mcp"]
      }
    }
  }
}
```

## Smoke check

Use a minimal MCP handshake and `tools/list` request after the host attaches the
server.
