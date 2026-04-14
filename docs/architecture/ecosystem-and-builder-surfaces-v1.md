# Ecosystem And Builder Surfaces v1

This document explains how OpenVibeCoding fits into today's coding-agent
ecosystem, how the public first-run loop turns into a shareable asset, and
where builders should connect without overclaiming a full SDK/platform story.

## Primary ecosystem bindings

These names are safe to use in the current front door because they match the
repo's real product boundary.

- **Codex**: OpenVibeCoding is a command tower for Codex workflows that need
  governed runs, case records, approvals, and replayable proof.
- **Claude Code**: the same operator/control-plane story applies to Claude Code
  workflows.
- **MCP**: the current product truth is a **read-only MCP surface**. External
  tools can inspect runs, workflows, queue posture, approvals, and proof
  without mutating state.

## Adjacent ecosystem and comparison layer

These names belong in ecosystem/comparison language, not in the main hero.

- **OpenHands**: adjacent ecosystem mention for broader agent stacks and SDK/CLI
  surfaces.
- **OpenCode**: comparison-only and transition-sensitive; do not treat it as a
  primary anchor.
- **OpenClaw**: different category; keep it out of the current front door.

## First run to proof to share

The strongest public distribution loop today is:

1. Start one of the three public packs:
   - `news_digest`
   - `topic_brief`
   - `page_brief`
2. Confirm the outcome in:
   - **Command Tower**
   - **Workflow Cases**
   - **Proof & Replay**
3. Reuse the Workflow Case as a **share-ready asset** instead of trapping the
   result inside a one-off operator page.

That makes OpenVibeCoding easier to explain, review, and circulate without
pretending it is already a hosted product.

## AI surfaces already in the main flow

The current repo already exposes three concrete AI assist surfaces:

- **Flight Plan copilot**: a bounded pre-run advisory brief before execution
- **Workflow copilot**: a workflow-scoped brief grounded in queue posture,
  latest run context, and next operator action
- **Run / compare operator brief**: a run-scoped brief grounded in compare,
  proof, incident, approval, and queue truth

These are real product surfaces, not generic floating chat panels.

## Builder entry points

Use these three layers together:

| Surface | What it is for | Where to start |
| --- | --- | --- |
| `@openvibecoding/frontend-api-client` | thin JS/TS client helpers for dashboard/desktop/web consumers plus the repo-owned `createControlPlaneStarter(...)` bootstrap path | `packages/frontend-api-client/README.md` |
| `@openvibecoding/frontend-api-contract` | generated contract-facing types and route/query names | `packages/frontend-api-contract/index.d.ts` |
| `@openvibecoding/frontend-shared` | shared UI copy, locale, status, and frontend-only presentation helpers | `packages/frontend-shared/README.md` |

## Builder quickstart

1. Import `createFrontendApiClient` or a dashboard/desktop-specific variant
2. Point it at the current API base URL
3. Use `createControlPlaneStarter(...)` when you want the shortest truthful
   bootstrap for overview + agents + contracts + role-config reads
4. Read runs, Workflow Cases, approvals, and command-tower overviews from the
   same client boundary
5. Use `@openvibecoding/frontend-api-contract` for generated contract-facing
   imports
6. Use `@openvibecoding/frontend-shared` for copy, locale, and presentation
   helpers instead of rebuilding those layers per app
7. Use the repo-owned example
   `packages/frontend-api-client/examples/control_plane_starter.local.mjs`
   when you want the shortest runnable bootstrap for overview + agents +
   contracts + role-config preview without inventing a second starter wrapper

## Minimal builder example

```ts
import { createFrontendApiClient } from "@openvibecoding/frontend-api-client";

const client = createFrontendApiClient({
  baseUrl: "http://localhost:8000",
});

const runs = await client.fetchRuns();
const workflows = await client.fetchWorkflows();
const overview = await client.fetchCommandTowerOverview();
```

## Repo-owned starter path

For a truthful external-consumer starting point, run the example that ships
with the thin client package instead of reconstructing the flow from docs
alone:

```bash
node packages/frontend-api-client/examples/control_plane_starter.local.mjs \
  --base-url http://127.0.0.1:10000 \
  --role WORKER \
  --mutation-role TECH_LEAD \
  --preview-provider cliproxyapi \
  --preview-model gpt-5.4
```

Keep the starter preview-first by default. Apply should stay behind
`--apply` so the example does not masquerade as a hosted
SDK or an automatic execution-authority switch.

## Guardrails

- do not describe OpenVibeCoding as a hosted operator product
- do not describe the current MCP surface as write-capable
- do not describe the current package surface as a full SDK platform
- do keep the public story anchored on:
  - Command Tower
  - Workflow Cases
  - Proof & Replay
  - read-only MCP
  - share-ready Workflow Case assets
