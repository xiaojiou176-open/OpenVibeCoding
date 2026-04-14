# Write-MCP Queue Pilot

This runbook defines the **smallest honest** write-capable MCP pilot that
OpenVibeCoding can describe today without pretending the public MCP contract has
already become broadly writable.

It is an internal operator runbook, not a public product promise.

## Why this file exists

Three different things are easy to blur together:

1. public read-only MCP
2. repo-owned operator HTTP mutation helpers
3. a later-gated queue-only MCP pilot

This file keeps those lanes separate so future workers do not turn one narrow
mutation path into a fake “general write-capable MCP” claim.

## Current boundary

- Public MCP contract = **read-only only**
- Public API / builder story = thin client + contract + shared presentation
  substrate
- Later-gated write pilot = **queue-first only**
- No broader mutation claim is legal from this file

## Smallest honest cut

The only write-shaped MCP cut that is truthful today is:

- derive one queue item from one existing run
- preview that derived queue item first
- require an explicit confirmation payload before enqueue
- keep the actual apply path default-off in trusted operator environments only
- treat queue cancel as the rollback path for pending pilot items

That means the pilot is not:

- arbitrary run mutation
- arbitrary workflow mutation
- approval mutation
- provider mutation
- contract rewrite
- external-account mutation

## Current repo-owned surfaces

### MCP pilot entry

- CLI entrypoint:
  - `python -m openvibecoding_orch.cli mcp-queue-pilot-server`
- code:
  - `apps/orchestrator/src/openvibecoding_orch/mcp_queue_pilot_server.py`

### HTTP control-plane helpers

- preview enqueue:
  - `POST /api/queue/from-run/{run_id}/preview`
- apply enqueue:
  - `POST /api/queue/from-run/{run_id}`
- cancel pending queue item:
  - `POST /api/queue/{queue_id}/cancel`

### Store / audit path

- queue ledger path:
  - `.runtime-cache/openvibecoding/queue.jsonl`

## How the pilot stays fail-closed

The current repo-owned implementation already enforces these boundaries:

1. preview is read-only
   - `preview_enqueue_from_run` derives a queue item without mutating queue
     state
2. apply is default-off
   - `enqueue_from_run` is blocked until
     `OPENVIBECODING_MCP_QUEUE_PILOT_ENABLE_APPLY=1`
3. apply requires explicit confirmation
   - `confirm=true` is mandatory
4. apply requires a trusted operator role
   - default allowed roles are:
     - `OWNER`
     - `ARCHITECT`
     - `OPS`
     - `TECH_LEAD`
5. apply requires operator metadata
   - `requested_by`
   - `approval_reason`
   - `actor_role`
6. the pilot self-labels its boundary
   - `approval_mode = manual-owner-default-off`
   - `pilot_source = mcp_queue_pilot_server`

## Approval / audit / rollback / rejection semantics

### Preview

- preview is the first-class required step
- the preview response must show:
  - `validation = fail-closed`
  - `preview_item`
  - `required_apply_inputs`
  - `allowed_roles`
  - `mutation_gate`
  - `next_step`

### Approval

- approval is currently encoded as:
  - trusted operator role
  - explicit `confirm=true`
  - explicit `approval_reason`
  - trusted environment gate

This is a narrow operator gate, not a general human-approval framework for all
future write actions.

### Audit

- queue append / cancel actions are recorded in `queue.jsonl`
- enqueue items carry:
  - `source_run_id`
  - `workflow_id`
  - `priority`
  - scheduling metadata
- MCP apply payload also stamps:
  - `pilot_source`
  - `approval_mode`
  - `requested_by`
  - `actor_role`
  - `approval_reason`

### Rollback

- for pending pilot items, rollback = cancel the queue item through:
  - `POST /api/queue/{queue_id}/cancel`
- once a queue item is claimed and work has started, this pilot no longer counts
  as a safe queue-only rollback surface

### Rejection

- rejection before apply = do not call `enqueue_from_run`
- rejection after preview but before execution = cancel the pending queue item
- broader run rejection remains outside this pilot and lives on the regular
  run-control surfaces

## Forbidden mutations

This pilot must not be described or widened into any of the following without a
new explicit owner decision and fresh evidence:

- arbitrary filesystem writes through MCP
- role-config apply through MCP
- run rollback / run reject through MCP
- approval queue mutation through MCP
- provider or credential mutation
- workflow-case truth rewrite
- broad task-contract mutation
- GitHub / Render / npm / marketplace / store actions

## Builder / docs boundary

Repo-owned builder surfaces may expose guarded operator helpers, but they do
not change the public product truth:

- `@openvibecoding/frontend-api-client` may surface queue preview/cancel helpers
- generated contract paths may include queue preview/cancel routes
- public docs must still say:
  - read-only MCP is the shipped contract
  - queue-only pilot groundwork is internal / later-gated
  - no write-capable MCP claim is live

## Verification

Run these commands after changing the queue pilot contract or its surrounding
docs:

```bash
bash scripts/run_orchestrator_pytest.sh \
  apps/orchestrator/tests/test_mcp_queue_pilot_server.py \
  apps/orchestrator/tests/test_api_main_runtime_views.py \
  apps/orchestrator/tests/test_queue.py -q

npm run docs:check
bash scripts/hooks/doc_drift_gate.sh
bash scripts/hooks/doc_sync_gate.sh
bash scripts/check_repo_hygiene.sh
```

## Human boundaries that still remain

Even when the repo-side pilot is complete, these actions still require a real
human boundary before any broader write claim can be made:

- enabling the trusted operator environment in a live deployment
- deciding whether hosted operator service is actually being reopened
- deciding whether any broader MCP mutation family is in scope
- deciding whether any store / publisher / external platform write path should
  exist at all

## Truth sentence for future workers

Use this sentence unless fresh evidence changes it:

> OpenVibeCoding still ships a read-only public MCP surface. The only truthful
> write-shaped repo-side pilot today is a default-off, confirm-gated,
> trusted-operator queue enqueue path derived from an existing run, with queue
> cancel as the rollback path for pending pilot items.
