# Read-only MCP + Operator Copilot v1

Date: 2026-03-31 (America/Los_Angeles)

This document captures the Prompt 4 baseline for the first **read-only MCP
server** and the first **AI operator copilot** surface in CortexPilot.

## Why this slice exists

CortexPilot already had the control-plane truth and the operator UI. Prompt 4
turns that into two new product surfaces:

- an **agent-facing read-only MCP node**
- a **human-facing explain-only operator brief**

Both surfaces reuse the same existing truth. Neither one is allowed to create a
second truth source or hide write behavior behind soft wording.

## Read-only MCP server v1

### Current entry

For stdio-capable clients, the shortest repo-owned entry is:

```bash
bash /absolute/path/to/CortexPilot/scripts/run_readonly_mcp.sh
```

The underlying runtime command remains:

```bash
PYTHONPATH=apps/orchestrator/src python3 -m cortexpilot_orch.cli mcp-readonly-server
```

The repo-local entry lives at
`apps/orchestrator/src/cortexpilot_orch/mcp_readonly_server.py` and the CLI
hook lives at `apps/orchestrator/src/cortexpilot_orch/cli.py`.

### What v1 exposes

The first server is **stdio JSON-RPC** and **read-only**.

Current tool set:

- `list_runs`
- `get_run`
- `get_run_events`
- `get_run_reports`
- `list_workflows`
- `get_workflow`
- `list_queue`
- `get_pending_approvals`
- `get_diff_gate_state`
- `get_compare_summary`
- `get_proof_summary`
- `get_incident_summary`

### Read-only contract

- The server must not mutate runs, workflows, queue items, approvals, or
  provider state.
- Workflow and queue tools use `ControlPlaneReadService` so Prompt 4 can read
  workflow cases and queue state without refreshing workflow snapshots or
  touching `queue.jsonl` on cold start.
- Write-capable MCP remains out of scope for Prompt 4.

### Structured output contract

- tools return structured JSON in `structuredContent`
- `content[].text` is a short compatibility summary only
- errors that belong to the business domain return `isError: true`
- protocol-level method failures remain JSON-RPC errors

## AI operator copilot v1

### Current landing zones

Prompt 4 intentionally keeps Copilot v1 **run-scoped**.

Primary surface:

- `apps/dashboard/app/runs/[id]/page.tsx`

Second surface:

- `apps/dashboard/app/runs/[id]/compare/page.tsx`

Shared UI entry:

- `apps/dashboard/components/control-plane/OperatorCopilotPanel.tsx`

Prompt 7 extends the same bounded brief shell to these additional surfaces:

- dashboard `Workflow Case detail`
- dashboard `Flight Plan` preview in PM intake
- desktop `Run Detail`
- desktop `Run Compare`
- desktop `Workflow Detail`
- desktop `Flight Plan` preview in the chat shell

Backend brief generation:

- `apps/orchestrator/src/cortexpilot_orch/services/operator_copilot.py`
- `schemas/operator_copilot_brief.v1.json`

### What v1 answers

The first brief is bounded on purpose. It answers:

- Why did this run fail or get blocked?
- What changed compared with the baseline?
- What is the next operator action?
- Where is the workflow or queue risk right now?

### What v1 reads

Copilot v1 is grounded in existing read models only:

- `get_run`
- `get_reports`
- `get_workflow`
- `list_queue`
- `list_pending_approvals`
- `list_diff_gate`

That means the brief can explain:

- compare deltas
- proof readiness
- incident context
- queue / SLA posture
- approval and diff-gate blockers

### What v1 does not do

- no open chat
- no rollback / reject / replay / approve / promote actions
- no speculative RCA when truth is missing
- no replacement of Flight Plan or PM planning

### Failure behavior

If the provider or agents SDK is unavailable, Copilot returns
`status = "UNAVAILABLE"` and points the operator back to the existing compare /
proof / incident / workflow surfaces.

## Prompt 5 handoff

Prompt 5 should continue from here instead of reopening discovery:

- strengthen the public task-pack first-run loop
- add case export / share
- extend copilot from run-scoped to workflow-scoped and Flight Plan pre-run
  scopes
- extend reliability language to GodMode / DiffGate / session-level surfaces
- reassess write-capable MCP only after the read-only contract stays stable

Still deferred:

- write-capable MCP tools
- hosted operator surface
- large front-door / SEO / growth expansion

## Prompt 7 extensions

Prompt 7 does **not** reopen write-MCP or hosted scope. It only extends product
completeness around the same bounded explanation path.

### Workflow-scoped copilot

- route: `POST /api/workflows/{workflow_id}/copilot-brief`
- still explain-only
- still grounded in repo-side truth only
- reads workflow detail, queue posture, latest linked run, latest compare/proof/incident, and gate posture
- must surface missing truth instead of inventing a complete story

### Flight Plan pre-run copilot

- route: `POST /api/intake/preview/copilot-brief`
- advisory only; it does not claim any post-run truth
- grounded in `execution_plan_report.v1.json`
- explains risk gates, capability triggers, approval posture, and the best pre-run confirmation step

### Desktop parity

- desktop now reuses the same bounded brief contract on Run Detail, Run Compare, Workflow Detail, and the pre-run Flight Plan preview
- desktop parity remains compact, but it does **not** create a second truth pipeline

## Prompt 8 final boundary verdict

Prompt 8 does **not** reopen product-completeness work. It freezes the two
remaining high-risk directions as follows.

### Write-capable MCP verdict: Later

Why not now:

- the repo ships only a read-only MCP surface today
- internal write APIs and approval routes exist, but there is still no
  agent-facing write contract with explicit mutation semantics
- MCP-specific actor identity, audit expectations, approval handshake, and
  blast-radius boundaries are not yet formalized as a public/operator contract
- the current docs/public wording would overstate reality if they implied
  agent-safe write access today

Smallest safe next move if reopened later:

- one owner-only, manual-only, default-off queue mutation pilot
- one mutation type only
- explicit audit/actor evidence
- deny by default outside the pilot path
- repo-side groundwork may include queue preview/cancel plus a confirm-gated
  queue-only MCP pilot server, but those do not change the public read-only MCP
  verdict until live operator policy and mutation proof are promoted explicitly

### Hosted operator surface verdict: No-Go

Why not now:

- README / SUPPORT / PRIVACY still define CortexPilot as source code plus
  operator/demo surfaces, not a hosted service
- `cortexpilot.ai` is still a holding page, not a production front door
- the live public repo, release body, and Pages wording still lag behind the
  repo-side product story
- no tenant boundary, service onboarding, or hosted support promise is part of
  the current public contract

Smallest safe next move if ever reopened:

- a docs-level readiness proof or waitlist-style expression of interest only
- not a hosted login shell, not a production trial surface
