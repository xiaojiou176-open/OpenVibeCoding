# Contracts Workspace

This directory holds contract artifacts for OpenVibeCoding governance.

- packs/: source-of-truth task-pack manifests for registry-driven intake surfaces.
- plans/: PM or Tech Lead plans (plan schema).
- tasks/: tracked contract examples or source-level task artifacts only; runtime-generated task results do not live here.
- results/: tracked contract examples or source-level result artifacts only; runtime-generated results do not live here.
- reviews/: tracked contract examples or source-level review artifacts only; runtime-generated reviews do not live here.
- examples/: Example contracts for smoke tests (task_contract, task_result, review_report, test_report, work_report, evidence_report, task_chain, chain_report, reexec_report).
- examples/task_result.failure.denied.json, examples/task_result.failure.sampling_gate.json, examples/task_result.failure.timeout.json: Failure-state examples for audit, teaching, and test scenarios only; they are not direct scheduler inputs and must not be used for runtime dispatch execution.
- examples/task_chain.lifecycle.full.json: Full PM→TL→Workers→Reviewers→Testing→TL→PM lifecycle chain with explicit `handoff` and `strategy.lifecycle` enforcement.
  - Reviewer/Test steps are modeled as read-only contracts (`task_type=REVIEW|TEST`) with scope declared in `allowed_paths`.
  - Reviewer `allowed_paths` includes reviewed worker outputs to accept dependency patch context under strict diff gate.
  - Multi-reviewer chains with overlapping review scope run serially (no shared `parallel_group`) to avoid lock contention by design.
- Runtime-generated task/review/result contracts are written under `.runtime-cache/openvibecoding/contracts/{tasks,reviews,results}`.
- Runtime-generated pack metadata must not write back into `contracts/packs/`; pack manifests stay source-owned and repo-tracked.
- Pack manifests now also carry `input_fields` plus `evidence_contract`
  metadata so dashboard and desktop intake surfaces can render pack-specific
  forms without inventing their own field registry.
- `contracts/` is source-of-truth workspace only; any runtime path that writes back into `contracts/tasks|reviews|results` is governance drift.
- Auto-generated coverage self-heal chains therefore land under `.runtime-cache/openvibecoding/contracts/tasks`, even when their schema/source examples live in this directory.

## Sampling Request Routing (Scheduler Contract Semantics)

The scheduler entrypoint `run_sampling_requests(...)` routes each `request.requests[]` item by `tool` with fail-fast behavior:

- `tool` omitted: defaults to `sampling`.
- `tool=sampling`: runs `tool_runner.run_mcp("sampling", payload)` as gate first, then executes sampling runtime (`tools.mcp.sampling_runner.run_sampling`) only if gate passes.
- `tool in {aider, continue, open_interpreter}`: routed through `tool_runner.run_mcp(tool, payload)` and executed via adapter runtime path.
- Compatibility alias: incoming `open-interpreter` is normalized to `open_interpreter` before routing.
- Any other `tool`: returns `ok=false` with `reason="unsupported tool"` and stops further request processing.

## Adapter Failure Examples and Audit Fields

The three failure examples are contract-level teaching/audit samples, and map to current runtime failure classes:

- `task_result.failure.denied.json`: policy denial class (for example MCP tool denied). Runtime audit includes `MCP_TOOL_DENIED` and carries `meta.task_id`, `meta.reason`, and `meta.denied_reason`.
- `task_result.failure.sampling_gate.json`: sampling gate rejection class. Runtime audit includes `MCP_SAMPLING_GATE_RESULT`; blocked outcomes propagate `reason` in both event/meta and task-level error payload.
- `task_result.failure.timeout.json`: timeout class. Adapter runtime timeout reason is `adapter command timeout`; failures are surfaced as MCP/Tool failure payloads with `error`/`reason`.

These examples describe canonical failure semantics and required evidence shape; they are not exhaustive snapshots of every possible runtime field.

## Compatibility Notes (P0 Adapter Rollout)

- Adapter routing is additive; it does not replace OpenVibeCoding primary orchestration.
- Existing sampling-only requests remain valid (`tool` omitted still routes to sampling).
- Adapter tools remain policy-gated by contract `tool_permissions.mcp_tools`; denied tools fail with deterministic `error/reason`.
