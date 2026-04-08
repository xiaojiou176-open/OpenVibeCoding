# Frontend API Contract

`@cortexpilot/frontend-api-contract` is the repo-owned contract package for
frontend-safe CortexPilot route names, query shapes, and generated types.

Current package boundary: this package now carries publish-ready metadata and a
registry-safe manifest, but no public registry release is live yet. The
truthful adoption path today is still repo-local consumption, clone-and-reuse,
or vendored internal reuse until the first package release is published.

## What lives here

- `index.d.ts`: stable root entrypoint that re-exports the generated contract
  surface for the main API layer
- `ui-flow.d.ts`: stable root entrypoint that re-exports generated UI-flow
  types for frontend consumers
- `generated/index.d.ts`: current generated contract-facing exports for the
  main API surface
- `generated/ui-flow.d.ts`: current generated UI-flow-facing exports
- stable import boundaries for frontend packages that should not import backend
  modules directly

## What this package is for

Use this package when you want:

- route and query names that stay aligned with the generated frontend contract
- typed control-plane read surfaces without importing backend modules
- a stable contract layer below `@cortexpilot/frontend-api-client`

## What this package is not

- not a hosted SDK
- not a public marketplace artifact
- not a published Codex / Claude Code / OpenClaw listing
- not a replacement for the read-only MCP server

## Shortest truthful onboarding order

1. Start with the public [compatibility matrix](https://xiaojiou176-open.github.io/CortexPilot-public/compatibility/) when your team still needs the shortest “which adoption ladder fits us?” answer.
2. Continue to the public [agent starter kits](https://xiaojiou176-open.github.io/CortexPilot-public/agent-starters/) when your next move is wiring a real Codex / Claude Code / OpenClaw config instead of only reading the route map.
3. Continue to the public [API quickstart](https://xiaojiou176-open.github.io/CortexPilot-public/api/) when you want the human-readable HTTP boundary.
4. Continue to the public [builder quickstart](https://xiaojiou176-open.github.io/CortexPilot-public/builders/) when you want the package map.
5. Import `@cortexpilot/frontend-api-contract` when you are working inside the same repo or a vendored workspace copy and need generated route/query/type truth without backend imports.

## Ecosystem reality anchors

If you are integrating this package into a broader coding-agent workflow,
confirm the host tool's native surface first:

- Codex:
  [repo](https://github.com/openai/codex),
  [docs](https://developers.openai.com/codex),
  [IDE install](https://developers.openai.com/codex/ide)
- Claude Code:
  [overview](https://code.claude.com/docs/en/overview),
  [MCP docs](https://code.claude.com/docs/en/mcp)
- OpenClaw:
  [repo](https://github.com/openclaw/openclaw),
  [skills docs](https://docs.openclaw.ai/tools/skills),
  [ClawHub](https://github.com/openclaw/clawhub)

Then keep the CortexPilot package story honest:

- this contract package is for frontend-safe route/query/type truth
- it sits below the thin client and beside the shared presentation substrate
- it does not turn CortexPilot into an official plugin, marketplace artifact,
  or hosted SDK

## Key entrypoints

- `../README.md`: package root README
- `../index.d.ts`: current generated contract exports
- `../ui-flow.d.ts`: generated UI-flow exports
- `../../frontend-api-client/README.md`: thin client layer that sits above this contract package
- `../../frontend-shared/README.md`: shared presentation substrate that sits beside this package

## Vendored workspace reminder

If you are reusing this contract package outside the repo today, keep the
boundary honest:

- copy it as part of a vendored workspace or clone until the first package
  release exists; do not imply a live registry install today
- pair it with `@cortexpilot/frontend-api-client` when you want a runnable
  bootstrap path instead of raw route/type truth only
- keep the public explanation anchored on compatibility / integrations /
  read-only MCP / skills, not on a fake marketplace or official plugin story
