# Frontend Shared

Shared frontend-only presentation helpers and types for the dashboard and
desktop command-tower surfaces.

Current package boundary: this package remains a repo-owned presentation
substrate and is not treated as a standalone distribution unit today. The
truthful adoption path is still repo-local consumption, clone-and-reuse, or
vendored internal reuse rather than a separate public package story.

## What lives here

- `uiCopy`: shared brand, shell, operator, approval, and page-level copy
- `uiLocale`: preferred UI locale detection, persistence, and toggle helpers
- `statusPresentation`: locale-aware status, stage, CTA, and datetime helpers
- `types`: frontend-facing shared report/type surfaces that sit above the raw
  API contract

## What does not live here

- backend-facing HTTP contract definitions
- generated API path/query bindings
- runtime orchestration logic
- MCP server contracts

## Current boundary

- This package is part of the frontend presentation substrate, not a standalone
  public SDK.
- Public API contract types stay in `@openvibecoding/frontend-api-contract`.
- Client entry points stay in `@openvibecoding/frontend-api-client`.
- This package is not treated as a standalone public package surface today.

## Human-readable entrypoints

If you want the public explanation for how this shared substrate fits into
Codex / Claude Code / OpenClaw workflows, use:

- [Compatibility matrix](https://xiaojiou176-open.github.io/OpenVibeCoding/compatibility/)
- [Integration guide](https://xiaojiou176-open.github.io/OpenVibeCoding/integrations/)
- [Agent starter kits](https://xiaojiou176-open.github.io/OpenVibeCoding/agent-starters/)
- [Read-only MCP quickstart](https://xiaojiou176-open.github.io/OpenVibeCoding/mcp/)
- [API quickstart](https://xiaojiou176-open.github.io/OpenVibeCoding/api/)
- [Contract package guide](../frontend-api-contract/docs/README.md)
- [Skills quickstart](https://xiaojiou176-open.github.io/OpenVibeCoding/skills/)

## Ecosystem reality anchors

When a team asks "what already exists on the host side?", point them to the
native surfaces first:

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

This package then stays in its narrower role:

- shared UI copy, locale, and status presentation for OpenVibeCoding command-tower surfaces
- repo-owned presentation reuse across dashboard, desktop, and future web
- not a native plugin for Codex, Claude Code, or OpenClaw
