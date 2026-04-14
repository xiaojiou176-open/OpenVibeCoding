# Schemas

Machine-readable schemas for contracts, events, and policy validation.

## Key Files

- `orchestrator_event.v1.json` — canonical event schema emitted by orchestrator runtime.
- `execution_plan_report.v1.json` — advisory intake-preview report used before execution starts.
- `control_plane_runtime_policy.v1.json` — machine-readable command-tower runtime constitution for L0/L1/L2, wake policy, completion governance, and harness boundaries.
- `completion_governance_report.v1.json` — runtime-evaluated completion verdict for DoD, reply audit, continuation, Context Pack fallback readiness, and harness-request lifecycle posture.
- `wave_plan.v1.json` — wave-level orchestration preview artifact derived from intake planning.
- `worker_prompt_contract.v1.json` — worker-scoped planner artifact for scope, reading list, continuation, and verification rules.
- `unblock_task.v1.json` — L0-managed independent temporary unblock assignment derived from worker continuation policy.
- `context_pack.v1.json` — explicit fallback handoff contract for context-pressure and role-switch situations.
- `harness_request.v1.json` — capability-evolution request contract for session-local/project-local/global harness changes.
- `artifacts/context_pack.json` and `artifacts/harness_request.json` are now the
  runtime-generated minimal lifecycle surfaces emitted by completion governance
  when those schema homes are actually exercised during run finalize.
- `approval_pack.v1.json` / `incident_pack.v1.json` / `run_compare_report.v1.json` — derived operator-readable decision packs for approval, failure triage, and replay compare surfaces.
- `proof_pack.v1.json` — derived success-pack for public task slices that completed with reusable proof artifacts.
- `task_pack_manifest.v1.json` — source-owned manifest schema for registry-driven task packs under `contracts/packs/`, including `input_fields` and evidence hints.
- `pm_intake_request.v1.json` — operator intake request contract; `template_payload` is open-shaped here and finalized by pack-specific runtime validation.
- `queue_item.v1.json` / `scheduled_run.v1.json` / `sla_state.v1.json` — runtime queue and schedule/SLA contracts for operator surfaces and queue governance gates.
- `workflow_case.v1.json` — persisted workflow-case snapshot stored under `.runtime-cache/openvibecoding/workflow-cases/`.
- `CHANGELOG.md` — schema evolution notes.

## Rules

- Schema changes must preserve compatibility or include explicit migration notes.
- Keep schema changelog synchronized with runtime code and tests.
