# OpenClaw example

OpenClaw already has native plugin and skills surfaces. This folder shows the
truthful CortexPilot position inside that ecosystem.

## Start here

1. Use the compatible bundle at:

   ```text
   examples/coding-agents/plugin-bundles/cortexpilot-coding-agent-bundle/
   ```

2. Pair it with one of the tracked OpenClaw MCP/config examples:

   ```text
   examples/coding-agents/openclaw/cortexpilot-server.json
   examples/coding-agents/openclaw/config.openclaw.example.toml
   ```

3. Keep CortexPilot on the proof / replay / read-only integration side unless a
   native published OpenClaw path is explicitly shipped and tested.

## Expected success

- the OpenClaw config resolves to your local CortexPilot checkout and the same
  read-only MCP server
- the proof target is still the public proof-first loop in
  `docs/use-cases/index.html`, not a claim that you are already live on ClawHub
- the final wording stays `bundle-compatible` or `starter-ready`, not
  `published OpenClaw plugin`

## Boundary

- This is a compatible local bundle example plus tracked local MCP/config
  objects, not a published ClawHub item.
- It helps OpenClaw workflows reuse CortexPilot skills and read-only MCP.
- It does not upgrade CortexPilot into a hosted operator or write-capable MCP
  product.
