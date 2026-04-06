# Schemas

Machine-readable schemas for contracts, events, and policy validation.

## Key Files

- `orchestrator_event.v1.json` — canonical event schema emitted by orchestrator runtime.
- `execution_plan_report.v1.json` — advisory intake-preview report used before execution starts.
- `approval_pack.v1.json` / `incident_pack.v1.json` / `run_compare_report.v1.json` — derived operator-readable decision packs for approval, failure triage, and replay compare surfaces.
- `proof_pack.v1.json` — derived success-pack for public task slices that completed with reusable proof artifacts.
- `task_pack_manifest.v1.json` — source-owned manifest schema for registry-driven task packs under `contracts/packs/`, including `input_fields` and evidence hints.
- `pm_intake_request.v1.json` — operator intake request contract; `template_payload` is open-shaped here and finalized by pack-specific runtime validation.
- `queue_item.v1.json` / `scheduled_run.v1.json` / `sla_state.v1.json` — runtime queue and schedule/SLA contracts for operator surfaces and queue governance gates.
- `workflow_case.v1.json` — persisted workflow-case snapshot stored under `.runtime-cache/cortexpilot/workflow-cases/`.
- `CHANGELOG.md` — schema evolution notes.

## Rules

- Schema changes must preserve compatibility or include explicit migration notes.
- Keep schema changelog synchronized with runtime code and tests.
