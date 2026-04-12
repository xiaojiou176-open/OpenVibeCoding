# Schema Changelog

## 2026-04-12
- Added `control_plane_runtime_policy.v1.json` to formalize L0 command-tower runtime rules.
- Added `wave_plan.v1.json` and `worker_prompt_contract.v1.json` for planner preview artifacts.
- Added `unblock_task.v1.json` to formalize L0-managed independent temporary unblock assignments.
- Added `context_pack.v1.json` and `harness_request.v1.json` to reserve first-class schema homes for explicit handoff and harness-evolution contracts.
- Extended `execution_plan_report.v1.json` with `wave_plan`, `worker_prompt_contracts`, and `unblock_tasks`.

## 2026-02-04
- Added `schema_registry.json` with SHA256 and size metadata for all v1 schemas.
- Snapshot for current v1 schema set.
- Added `plan_bundle.v1.json`, `search_requests.v1.json`, `browser_tasks.v1.json`.
- Extended `plan.schema.json` with `plan_type`.
- Extended `pm_intake_response.v1.json` with `plan_bundle`.
