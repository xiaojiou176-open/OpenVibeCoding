# Frontend API Client

`@cortexpilot/frontend-api-client` is the thin JavaScript/TypeScript client
layer for CortexPilot command-tower consumers.

Current package boundary: this package now carries publish-ready metadata and a
registry-safe manifest, but no public registry release is live yet. The
truthful adoption path today is still repo-local consumption, clone-and-reuse,
vendored internal reuse, or local pack smoke until the first package release
is published.

## What it exposes today

- `createFrontendApiClient`
- `createDashboardApiClient`
- `createDesktopApiClient`
- `createControlPlaneStarter`
- shared auth, HTTP, and SSE cores for the same API surface

This package is useful when you want one import boundary for:

- runs and run reports
- Workflow Cases and queue posture
- run/workflow binding read models that stay explicitly below execution authority
- PM intake and command-tower overview routes
- approvals, reviews, and operator-facing control-plane reads
- the command-tower loop of plan / delegate / track / resume / prove
- role-configuration fetch / preview / apply routes for repo-owned role
  defaults, including the same mutation-role header discipline used by other
  operator mutation surfaces
- contract-backed workflow, queue, PM-session, and command-tower path/query bindings

## Minimal example

```ts
import {
  createControlPlaneStarter,
  createDashboardApiClient,
} from "@cortexpilot/frontend-api-client";

const client = createDashboardApiClient({
  baseUrl: "http://localhost:8000",
  resolveToken: () => window.localStorage.getItem("cortexpilot.token") || undefined,
  resolveMutationRole: () => "TECH_LEAD",
});

const starter = createControlPlaneStarter(client);

const bootstrap = await starter.fetchBootstrap({ role: "WORKER" });
const preview = await starter.previewRoleDefaults("WORKER", {
  runtime_binding: {
    provider: "cliproxyapi",
    model: "gpt-5.4",
  },
});
```

## Workspace integration starter

Use `createControlPlaneStarter(...)` when another dashboard, desktop shell, or
builder tool inside the same repo, a shared workspace, or a vendored internal
copy needs the shortest repo-owned path into the current control-plane story.

It gives repo-local or vendored consumers one place to:

- bootstrap Command Tower overview + agents + contracts + optional role config
- preview role-default changes without inventing a second client wrapper
- apply role-default changes with the same mutation-role header discipline the
  existing operator surfaces already use
- stay inside the truthful boundary where role defaults are configurable but
  `task_contract` remains the execution authority

The starter also exposes guarded queue helpers for trusted repo operators:

- preview queue enqueue changes from one run through the same repo-owned HTTP
  control-plane boundary
- cancel a pending queue item through the same mutation-role header discipline

Those queue helpers stay outside the default public builder promise. They are
repo-owned operator add-ons, not a claim that the public MCP contract is
write-capable.

## Repo-owned starter example

If you want a copy-pasteable starting point instead of reading the helpers one
by one, use the repo-owned example:

```bash
node packages/frontend-api-client/examples/control_plane_starter.local.mjs
```

## Before you run the starter

This example assumes you already have a truthful local control-plane context:

```bash
npm run bootstrap:host
CORTEXPILOT_HOST_COMPAT=1 bash scripts/test_quick.sh --no-related
```

Then either start the dashboard loop or make sure the API base URL you plan to
use is actually running:

```bash
npm run dashboard:dev
```

If you do not yet have a running API base URL, token story, or repo-local proof
receipt, stop here and start from:

- the public compatibility matrix
- the agent starter kits
- the read-only MCP quickstart
- the use-case proof loop

Those pages close the gap before this package asks you for `baseUrl`,
`resolveToken()`, and a running backend.

That example bootstraps:

- Command Tower overview
- `/api/agents`
- `/api/contracts`
- optional role-config preview for one role

The quickest useful preview run looks like this:

```bash
node packages/frontend-api-client/examples/control_plane_starter.local.mjs \
  --base-url http://127.0.0.1:10000 \
  --role WORKER \
  --mutation-role TECH_LEAD \
  --preview-provider cliproxyapi \
  --preview-model gpt-5.4
```

Expected success today:

- the example can fetch bootstrap data from the current API base URL
- it can read overview + agents + contracts without implying hosted SDK or
  public write-capable MCP
- any guarded mutation remains opt-in and repo-operator-only

Apply stays opt-in on purpose:

```bash
node packages/frontend-api-client/examples/control_plane_starter.local.mjs \
  --base-url http://127.0.0.1:10000 \
  --role WORKER \
  --mutation-role TECH_LEAD \
  --preview-provider cliproxyapi \
  --preview-model gpt-5.4 \
  --apply
```

The example stays inside the truthful boundary:

- it demonstrates bootstrap + preview
- apply only happens when you pass `--apply`
- it does not imply hosted SDK behavior
- it does not replace the backend orchestration runtime
- queue preview/cancel remain repo-owned operator HTTP surfaces; they do not
  promote the public MCP contract into write-capable MCP
- `task_contract` remains the execution authority even when role-default apply
  is available through the same client under local operator policy

## Fastest ecosystem-aware adoption order

Use this order when you are integrating the client into a real coding-agent
workflow instead of just reading the package in isolation:

1. Confirm the host ecosystem first:
   - Codex: [repo](https://github.com/openai/codex),
     [docs](https://developers.openai.com/codex),
     [IDE install](https://developers.openai.com/codex/ide)
   - Claude Code: [overview](https://code.claude.com/docs/en/overview),
     [MCP docs](https://code.claude.com/docs/en/mcp)
   - OpenClaw: [repo](https://github.com/openclaw/openclaw),
     [skills docs](https://docs.openclaw.ai/tools/skills),
     [ClawHub](https://github.com/openclaw/clawhub)
2. Use CortexPilot's
   [compatibility matrix](https://xiaojiou176-open.github.io/OpenVibeCoding/compatibility/)
   and
   [integration guide](https://xiaojiou176-open.github.io/OpenVibeCoding/integrations/)
   to pick the first truthful CortexPilot lane.
3. Keep this package together with `@cortexpilot/frontend-api-contract` and
   `@cortexpilot/frontend-shared` inside one clone or vendored workspace copy.
4. Prove the integration with `createControlPlaneStarter(...)` before you
   enable any guarded operator mutation path.

## Vendored or shared-workspace recipe

The package manifest is repo-side publish-ready, but no npm release is live
yet. The current truthful reuse path is still shared-workspace or
vendored-copy adoption, not `npm install` from a public registry.

```bash
git clone https://github.com/xiaojiou176-open/OpenVibeCoding.git
cd OpenVibeCoding
npm run bootstrap:host
node packages/frontend-api-client/examples/control_plane_starter.local.mjs \
  --base-url http://127.0.0.1:10000 \
  --role WORKER \
  --mutation-role TECH_LEAD \
  --preview-provider cliproxyapi \
  --preview-model gpt-5.4
```

## Vendored workspace recipe

If another Codex / Claude Code / OpenClaw workspace wants the shortest truthful
builder reuse path today, keep the copied surface explicit:

```text
vendor/CortexPilot/
  packages/frontend-api-client/
  packages/frontend-api-contract/
  packages/frontend-shared/
```

Then keep the workflow small:

1. point the client at the current API base URL
2. start from `createControlPlaneStarter(...)` or the repo-owned starter example
3. keep role-config apply and queue preview/cancel behind trusted maintainer
   policy instead of treating them as public builder defaults
4. pair package reuse with the public compatibility / integration / MCP / skills
   guides so teams do not accidentally re-label this client as an official
   plugin or a hosted SDK

## Current boundary

- This is a thin client surface, not a full SDK platform.
- It wraps the current HTTP routes that power the dashboard and desktop shells.
- Where `@cortexpilot/frontend-api-contract` already publishes frontend-safe
  route or query truth, this client reuses that contract instead of keeping a
  second handwritten path map.
- It does not replace the backend orchestration runtime or the read-only MCP
  server.
- Queue preview/cancel and the queue-only MCP pilot server are later-gated
  operator mutation groundwork, not public write-capable MCP.
- The control-plane starter is a builder convenience layer, not a second
  execution authority or a hosted SDK runtime.
- This package is publish-ready, but not published for public registry install
  today.
- Prompt 7-style frontend slices should treat `role_binding_read_model` and
  `workflow_case_read_model` as read-only operator surfaces; the task contract
  remains the execution authority.

## Human-readable entrypoints

If you are onboarding a Codex / Claude Code / OpenClaw workflow and want the
repo's truthful public explanation before you read the package internals, start
here:

- [Integration guide](https://xiaojiou176-open.github.io/OpenVibeCoding/integrations/)
- [Compatibility matrix](https://xiaojiou176-open.github.io/OpenVibeCoding/compatibility/)
- [Agent starter kits](https://xiaojiou176-open.github.io/OpenVibeCoding/agent-starters/)
- [Read-only MCP quickstart](https://xiaojiou176-open.github.io/OpenVibeCoding/mcp/)
- [API quickstart](https://xiaojiou176-open.github.io/OpenVibeCoding/api/)
- [Builder quickstart](https://xiaojiou176-open.github.io/OpenVibeCoding/builders/)
- [Contract package guide](../frontend-api-contract/docs/README.md)
- [Skills quickstart](https://xiaojiou176-open.github.io/OpenVibeCoding/skills/)
