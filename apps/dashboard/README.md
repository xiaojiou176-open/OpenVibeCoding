# Dashboard Module

## Positioning

This module is the repository's **web command-tower surface**.

Read it as:

- the browser-based command tower for plan, delegate, track, resume, and prove
  loops
- a way to inspect and operate OpenVibeCoding Command Tower orchestration truth from the web
- a repo-owned UI for L0-style oversight and case-driven operator review

Do **not** read it as:

- a polished customer-facing SaaS product
- a standalone web application with its own independent product roadmap
- evidence that every workflow here is already broad-market ready

## Module Responsibility

- Provide run, workflow, session, and review visualization for OpenVibeCoding Command Tower
  orchestration output.
- Surface operator-facing status, artifacts, and control points for the web.
- Surface intake preview, approval summaries, and run diagnostics as
  operator-readable decision objects rather than raw payloads alone.

## Why This Module Exists

If `apps/orchestrator/` is the machine room, `apps/dashboard/` is the glass
command tower operators use to see what the machine room is doing. Its job is
visibility, delegation, and proof-first oversight, not pretending the whole
repository is already a finished consumer product.

## Input / Output

- Input: API responses from the orchestrator backend.
- Output: operational UI views for runs, events, contracts, reports, and
  command surfaces.

## High-value operator surfaces

- PM workspace: registry-driven task-pack selection plus `execution_plan_report`
  preview before execution starts.
- Planner desk: a first-class planner-facing triage route that pulls
  `planning_wave_plan`, `planning_worker_prompt_contracts`,
  `planning_unblock_tasks`, and `completion_governance_report` into one
  planning control desk, now with inline queue / dispatch controls so planners
  can act on the next contract instead of only reading artifacts and clicking
  away to other desks.
- Agents: the first-screen role catalog now also hosts a repo-owned role
  configuration desk for previewing and saving future compiled defaults
  (`system_prompt_ref`, bundle refs, and role-level runtime binding) while
  `task_contract` remains the only execution authority.
- Workflow views: workflow-case summaries derived from run manifests and PM
  session bindings, now with queue/SLA read surfaces and a read-only
  `Workflow read model` card sourced from `workflow_case_read_model`.
- Dashboard `Run Detail` and `Workflow Case detail` now resolve page-level
  title/subtitle/degraded-state copy from the shared locale substrate via the
  UI locale cookie, so the high-value detail routes stay aligned with the
  English-first / `zh-CN` operator contract instead of drifting through
  page-local literals.
- Run Detail: incident packs, approval summaries, replay compare reports, and a
  read-only role-binding summary in the existing `Status & Contract` card, so
  bundle/runtime posture is visible on the main run surface without creating a
  second execution-authority switch.
- Contracts and Run Detail now also surface the derived runtime capability
  posture (`lane`, `compat_api_mode`, `provider_status`, `tool_execution`) so
  operators can read chat-style compatibility vs fail-closed tool execution
  without overstating the current runtime boundary.
- The staged UI-audit/dashboard-build path now depends on
  `apps/dashboard/lib/types.ts` explicitly re-exporting task-pack/runtime
  helper values and on `scripts/install_dashboard_deps.sh` recreating its
  runtime log directory before each install attempt, so smoke failures track
  product regressions instead of staging drift.
- Builder/public discovery: the home builder section now surfaces direct
  `Read-only MCP quickstart` and `API and contract quickstart` entry cards so
  operators can jump from the web control surface into the truthful public
  onboarding ladder before diving into package-level docs.
- Home discovery now compresses the old ecosystem / integrations / AI surfaces /
  builder sprawl into one adoption-path section so the dashboard front door
  behaves more like a router than a wall of repeated summaries.
- That same adoption layer now treats `/compatibility/` as the primary routing
  decision card, swaps the redundant compatibility action button for a lighter
  `/use-cases/` proof-first CTA, and keeps `/integrations/`, `/skills/`,
  `/mcp/`, `/api/`, and `/builders/` as the deeper branches once the job is
  clear.
- The dashboard public-docs resolver still treats `/integrations/`,
  `/skills/`, and `/compatibility/` as first-class public docs routes so
  public-docs base overrides do not strand those CTA links on app-local paths.
- The same public-home polish keeps the explicit `See first proven workflow` side
  door routed through the public-docs resolver, so the proof-first walkthrough
  stays visible without turning the dashboard back into a second full routing
  matrix.
- The contract-facing builder card now points to the repo-owned
  `packages/frontend-api-contract/docs/README.md` guide instead of only the raw
  generated `.d.ts` surface, so builders get a human-readable package entrypoint
  before opening the generated types.
- The home surface and PM workspace now also carry small `zh-CN` screen-reader
  onboarding lists plus the clearer `Back to bottom` chat action wording, so
  the first-step contract stays discoverable in localized assistive flows
  without changing the visible English-first operator copy.
- PM intake/chat regressions should keep the `Back to bottom` wording and the
  localized onboarding note aligned with this README in the same patch, so the
  dashboard doc-drift gate tracks the same visible operator-language contract
  that the PM intake tests now assert.

## Strongest Signals

- operator-first web workflows
- command visibility over product marketing polish
- alignment with the repository's three truth layers

## Key Config

- API base and frontend fetch layer are defined in `apps/dashboard/lib/api.ts`.
- Runtime defaults and startup commands are coordinated from the repo root
  quickstart in `README.md`.
- Dashboard dependency hotfixes should keep the root `package.json` overrides,
  root `pnpm-lock.yaml`, and `apps/dashboard/pnpm-lock.yaml` aligned so
  dashboard-only transitive patches do not drift from the workspace baseline.
- `apps/dashboard/pnpm-lock.yaml` is a maintained dashboard-specific lockfile;
  keep transitive security patch updates in the same change set when dashboard
  dependency metadata changes.
- The optional `depcheck` package is intentionally absent from the default
  dashboard dependency set; the dead-code gate already skips when the probe is
  unavailable, so leaving it out avoids carrying an otherwise unnecessary
  `brace-expansion` advisory path in the maintained lock surface.
- Dashboard dependency lock refreshes are repo-owned: when transitive package
  fixes land here, keep `apps/dashboard/pnpm-lock.yaml` aligned with the root
  `package.json` / `pnpm-lock.yaml` change set.
- Current transitive hardening includes the `yaml` override used through
  `cosmiconfig@7.1.0`; keep the dashboard lockfile and the root override in
  sync so the dashboard does not drift onto an older parser patch level.
- Current lock maintenance also pins patched `picomatch` / `brace-expansion`
  transitive paths through the repo-owned override set so GitHub security
  receipts and the dashboard lockfile stay aligned.
- Current security-only lock maintenance also pins `lodash-es@4.18.1` through
  both the root workspace and `apps/dashboard` override surfaces so the
  tracked `lighthouse@13.0.3` transitive chain does not fall back to the
  vulnerable `lodash-es@4.17.23` path on either maintained lockfile.
- When a dashboard security-only lock refresh lands, keep this module README in
  the same change set so doc-drift gates can trace the maintenance decision to
  the dashboard surface that actually owns the lockfile.

## Common Troubleshooting

- Dependencies missing: `pnpm --dir apps/dashboard install`
- Test failure: `pnpm --dir apps/dashboard test`
- Typecheck: `pnpm --dir apps/dashboard exec tsc -p tsconfig.typecheck.json --noEmit`

## Quality Gate

- Coverage gate (stage-1): >= 85%
- Command Tower regression tests now treat the English-first labels, drawer
  names, and quick-action copy as the canonical operator contract; update the
  dashboard tests in the same patch whenever those public-facing labels move.
- Search page regression tests should wait for the terminal promote-status copy
  instead of the first rendered status node because the UI intentionally passes
  through `Promoting evidence...` before it settles on success or failure.
- The current CI unblock patch also keeps the PM and RunDetail regression suite
  aligned with the English-first operator surface, including Command Tower
  session copy, PM composer controls, and RunDetail tab/status wording.
- Workflow Case detail now also renders the latest linked run's
  `workflow_case_read_model` for operator inspection, but that card remains a
  read-only mirror below `task_contract` execution authority.
- Run Detail now mirrors `role_binding_read_model` inside the existing
  `Status & Contract` card, and that note keeps `task_contract` explicit as the
  only execution authority.
- Agents now also uses a registry-backed read-only role catalog on the first
  screen, so operators can inspect skills/MCP/runtime posture before drilling
  into individual agent seats or scheduler backlog.
- Contracts now acts as a bundle/runtime inspector: each card keeps the task
  contract envelope visible while projecting the derived bundle/runtime summary
  as read-only operator context rather than a control surface; role-default
  edits belong on `Agents`, not on the contract inspector.
