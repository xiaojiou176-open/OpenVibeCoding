# Orchestrator Module

`apps/orchestrator/` is the backend core of CortexPilot.

## What It Owns

- task intake and contract compilation
- intake preview and execution-plan prediction
- execution, review, replay, and evidence flows
- read-only MCP exposure for control-plane truth
- explain-only operator copilot brief generation
- API and CLI entrypoints
- gate enforcement and runtime state

## Key Paths

- `src/cortexpilot_orch/config.py`
- `src/cortexpilot_orch/planning/`
- `src/cortexpilot_orch/gates/`
- `src/cortexpilot_orch/store/`
- `src/cortexpilot_orch/policy/browser_policy_resolver.py`

## Search And Browser Policy Notes

- search-task execution resolves browser policy before a web provider runs
- local host development defaults to `allow_profile` with the repo-owned
  Chrome singleton root `~/.cache/cortexpilot/browser/chrome-user-data`
- run `npm run browser:chrome:migrate` once to seed that root from the default
  Chrome display name `cortexpilot`; the repo rewrites it into `Profile 1`
- `allow_profile` then behaves as attach-or-launch against the singleton CDP
  endpoint `127.0.0.1:9341`, so manual and automated runs share the same
  headed Chrome instance instead of re-launching the default Chrome root
- if launch only creates a short-lived repo-owned Chrome process that never
  stays attached to the expected CDP endpoint, the launcher now fails closed
  instead of reporting a successful singleton launch
- launch success now requires a longer stability window instead of a single
  healthy sample, so the repo-owned singleton must stay attached across
  consecutive checks before `browser:chrome:launch` reports success
- if the repo-owned root is already offline, stale singleton locks and the old
  singleton state file are now cleared so status returns to a clean `offline`
  result instead of preserving a misleading stale launch record
- on macOS the launcher now prefers the repo-owned `open -na "Google Chrome"`
  path for headed singleton boot, then still reuses that same route on retry if
  CDP does not bind cleanly; that keeps the singleton on the same `Profile 1`
  root and avoids reporting success from a short-lived CLI-owned Chrome process
- on non-macOS hosts the same singleton path stays on the direct executable
  launch route, initializes its launch-route state before branching, and does
  not borrow the macOS-only `open -na` bootstrap branch
- login state persistence now relies on that single repo-owned user-data root
  plus attach-first reuse; the runtime closes only automation-created pages, so
  reopening the singleton should not require reseeding or second-launch copies
- if that same repo-owned root is still running on the old legacy port, the
  next launch treats it as a managed transition and relaunches it onto `9341`
  instead of flagging it as a foreign occupant
- CI, repo CI containers, and clean-room lanes force browser policy back to
  `ephemeral`; those paths must not depend on login state or on a copied host
  profile
- `allow_profile` still degrades to `ephemeral` if the configured profile root
  is outside the allowlist
- `allow_profile` prefers a real Chrome executable from `CHROME_PATH` or the
  standard macOS install path and fails closed instead of silently falling back
  to Playwright-bundled Chromium
- if the repo-owned root is missing, the singleton CDP port is owned by a
  different browser root, or the root is occupied by a Chrome process without
  CDP, the local host path fails closed instead of guessing or second-launching
- the `browser_ddg` search provider now also fails closed on singleton attach,
  Playwright, or browser-parse failures; it returns an explicit browser error
  instead of fabricating mock search success when the real browser path is down
- the current `gemini_web` prompt path supports both classic text inputs and
  `contenteditable` textbox surfaces, so provider DOM changes do not silently
  break the `news_digest` proof route again

## Commands

```bash
bash scripts/run_orchestrator_pytest.sh apps/orchestrator/tests -q
bash scripts/run_orchestrator_cli.sh --help
```

## Runtime Provider Compatibility Notes

- `CORTEXPILOT_PROVIDER_BASE_URL` may point either at a normal OpenAI-compatible
  `/v1` endpoint or at the Switchyard runtime-first surface
  `/v1/runtime/invoke`.
- When the base URL points at `Switchyard /v1/runtime/invoke`, the orchestrator
  now forces the Agents SDK onto `chat_completions` instead of the default
  `responses` path, because Switchyard is being consumed as a runtime-first
  invoke surface rather than as a fake OpenAI-compatible gateway.
- The current thin slice supports:
  - standard BYOK routing when CortexPilot keeps a normal runtime provider such
    as `gemini`, `openai`, or `anthropic`
  - explicit web-provider routing when the model is written as
    `provider/model`, for example `chatgpt/gpt-4o` or `claude/claude-3-5-sonnet`
- the current runtime-first slice is limited to chat-style compatibility
  surfaces such as intake planning and operator-copilot briefs; it is not a
  generic replacement for every Agents runner path
- The current Switchyard adapter is intentionally chat-only. It does **not**
  expose tool-calling parity yet, so agent flows that require tool invocation
  must keep using a provider path that already supports those semantics.
- `agents_runner` therefore fails closed when `agents_base_url` points at
  `Switchyard /v1/runtime/invoke`, because that path still implies MCP tool
  execution semantics the adapter does not provide yet.

## Role Contract v1 Notes

- compiled task contracts now emit a resolved `role_contract` object so the
  assigned role, role purpose, prompt ref, MCP bundle ref, runtime binding,
  tool permissions, handoff posture, and fail-closed conditions are visible in
  one place instead of being inferred from scattered helpers alone
- intake preview now exposes `role_contract_summary` next to
  `contract_preview`, so operators can inspect the resolved role binding
  without reconstructing it from raw schema fields
- `run_intake(...)` now returns a contract-derived `role_binding_summary` read
  model, and the same summary is persisted into run manifests so PM-facing
  helpers plus post-run surfaces can inspect the same bundle/runtime state;
  registry-backed `mcp_bundle_ref` rows now surface their resolved tool set
  directly instead of falling back to an empty placeholder array
  without treating that summary as execution authority
- `get_run(...)` now also returns a stable `role_binding_read_model`, so run
  detail and read-only MCP consumers can inspect persisted bundle/runtime state
  without treating that read model as execution authority
  from `contract.json` without upgrading that read surface into execution
  authority
- the Prompt 8 frontend contract convergence now publishes the same run/workflow
  read-model truth through `docs/api/openapi.cortexpilot.json` and generated
  `@cortexpilot/frontend-api-contract` artifacts, so frontend consumers no
  longer have to infer Prompt 5/6/7 payload shapes from helper code alone
- role prompt refs now resolve from `policies/agents/codex/roles/` as the
  repository-owned prompt asset root when a worktree-local `codex/roles/`
  override is absent
- qualifying delivery roles now resolve `skills_bundle_ref` through the
  repo-owned `policies/skills_bundle_registry.json` surface; PM, SEARCHER, and
  RESEARCHER intentionally remain `null` to avoid widening non-delivery roles
  into a fake skills system
- handoff summaries remain structured evidence only; they no longer rewrite the
  execution instruction carried by the task contract

## Read-Only MCP + Copilot Notes

- the shortest repo-local MCP entry for external stdio clients is `bash scripts/run_readonly_mcp.sh`
- the underlying raw MCP runtime entry remains `python -m cortexpilot_orch.cli mcp-readonly-server`
- the later-gated queue write pilot entry is `python -m cortexpilot_orch.cli mcp-queue-pilot-server`
- copy-paste host-tool starters now live in `docs/agent-starters/index.html`,
  `docs/examples/agent-starters/`, and `examples/coding-agents/`, so Codex,
  Claude Code, and OpenClaw teams can wire the same read-only stdio server
  without inventing hosted or published-plugin claims
- the MCP surface is intentionally **read-only only** and must not mutate runs,
  workflows, approvals, queue state, or provider state
- the queue pilot server stays outside the public product contract; it only
  supports `preview_enqueue_from_run` plus a single confirm-gated
  `enqueue_from_run` mutation, and that mutation stays default-off until
  `CORTEXPILOT_MCP_QUEUE_PILOT_ENABLE_APPLY=1` is set in a trusted operator
  environment; queue cancel remains an HTTP control-plane recovery path
- the authoritative operator runbook for that later-gated mutation slice lives
  at `docs/runbooks/write-mcp-queue-pilot.md`; treat that file as the truth
  source for preview / approval / audit / rollback wording rather than
  improvising broader write-capable MCP claims
- shared control-plane reads flow through
  `src/cortexpilot_orch/services/control_plane_read_service.py`
- workflow/control-plane reads now also carry `workflow_case_read_model`, which
  points back to the latest linked run's persisted `role_binding_summary`
  without turning workflow cards into execution authority
- dashboard and desktop Run Detail now project `role_binding_read_model` on
  their primary operator surfaces using the same read-only boundary, rather
  than keeping that binding summary hidden behind workflow-only surfaces
- `/api/agents` now also publishes a registry-backed role catalog that reuses
  the same `build_role_binding_summary(...)` authority/source grammar, so
  agents surfaces can inspect role defaults without inventing a second truth
  surface; the lightweight provider-capability import path that feeds those
  read models now stays free of unused helper imports and other dead-code noise
- `/api/agents/roles/{role}/config` plus `preview` / `apply` sibling routes now
  expose the repo-owned role configuration desk for future compiled defaults;
  these routes validate refs and runtime bindings fail-closed, preview the
  derived readback, and persist changes into
  `policies/role_config_registry.json` without promoting that surface into
  execution authority
- intake preview, run manifests, and operator-copilot briefs now also surface
  a derived runtime capability summary (`lane`, `compat_api_mode`,
  `provider_status`, `tool_execution`) so runtime/provider posture is readable
  from repo-owned control-plane reads without implying full tool parity
- the `cortexpilot_orch.contract` package now lazy-loads `compiler` and
  `validator`, so governance-only entrypoints such as
  `scripts/check_schedule_boundary.py` can import `ContractValidator` without
  accidentally loading runtime-provider dependencies like `httpx`; this keeps
  Quick Feedback contract checks lightweight without changing execution
  authority or runtime capability semantics
- the role-config runtime capability preview now resolves through
  `src/cortexpilot_orch/runners/provider_capability.py`, which keeps the
  advisory control-plane lane honest without forcing GitHub-hosted quick
  hygiene checks to import the full provider transport runtime
- `/api/contracts` now normalizes contract artifact rows into a read-only
  bundle/runtime inspector payload instead of leaving dashboard/desktop pages
  to guess from heterogeneous raw JSON blobs
- the bounded operator brief is generated by
  `src/cortexpilot_orch/services/operator_copilot.py`
- the current operator-copilot contract is explain-only, not a write or
  recovery action surface

## Probe Artifact Note

- `scripts/e2e_external_web_probe.py` does not persist `run_id` values in JSON
  status/report outputs. The writer helpers also no longer take `run_id`
  inputs; receipts now persist stage/category allowlists, epoch timing fields,
  and artifact summaries through dedicated safe summary scalars instead of
  reading from the mixed internal report state.
- Probe sanitizer coverage keeps secret-like fixture strings in direct helper
  tests, while JSON writer contract tests use non-sensitive placeholders so PR
  security scans do not mistake unit-test fixtures for persisted clear-text
  payloads.
- Security-focused fixture tests now build token-like samples from safe
  fragments at runtime instead of checking in public raw literals that look
  like real provider/API credentials.
- Public-path contract tests now use generic workspace-style sample roots such
  as `/workspace/CortexPilot Repo/...` instead of developer-local absolute
  paths, so repo fixtures keep path-with-spaces coverage without publishing a
  maintainer machine path.
- PM intake responses only emit `task_template` / `template_payload` when those
  fields are actually present, keeping the response payload aligned with the
  schema contract used by API and intake coverage tests.
- PM intake preview now emits an `execution_plan_report` advisory object through
  `/api/pm/intake/preview`, so operators can inspect the compiled contract
  shape, predicted reports/artifacts, and likely approval boundary before
  starting execution.
- PM task packs are now registry-driven from `contracts/packs/*.json`; the
  orchestrator normalizes `template_payload`, derives objective/search queries,
  and returns pack metadata through `/api/pm/task-packs`.
- Queue operations now expose `/api/queue`, `/api/queue/from-run/{run_id}`, and
  `/api/queue/run-next`, so the control plane can queue an existing run
  contract with `priority`, `scheduled_at`, and `deadline_at`, then derive
  queue/SLA state before execution starts.
- Queue preview/cancel groundwork now also exists under
  `/api/queue/from-run/{run_id}/preview` and `/api/queue/{queue_id}/cancel`, so
  later-gated queue pilots can prove preview + rejection semantics without
  jumping straight to execution.
- Pending approval views now synthesize an `approval_pack` summary from run
  events plus manifest metadata instead of exposing only the raw
  `HUMAN_APPROVAL_REQUIRED` payload.
- Successful public task slices now synthesize a `proof_pack` summary from the
  primary result report and evidence refs, so proof-oriented runs expose an
  operator-readable success pack without relying on release docs alone.
- Replay flows now persist both `replay_report.json` and
  `run_compare_report.json`, so Run Detail surfaces can show compare summaries
  without re-deriving them client-side.
- Workflow reads now persist a governed `workflow_case` snapshot under
  `.runtime-cache/cortexpilot/workflow-cases/`, so case metadata is not rebuilt
  from PM session bindings on every page load alone.

## Mainline CI Notes

- The orchestrator Python lock surface now carries explicit security pins for
  `cryptography`, `pyasn1`, `pyjwt`, and `requests`, and the default dependency
  gate now also pins `pygments==2.20.0`, which lets
  `configs/pip_audit_ignored_advisories.json` stay empty again instead of
  carrying a stale upstream-unfixed downgrade.
- CI policy snapshots, policy/core stage logs, and the orchestrator coverage
  JSON now live under `.runtime-cache/test_output/ci/`, which keeps retention
  reports free of root-level `test_output` residue during `main` push
  validation.
- Strict upstream governance refresh now reuses cached upstream receipts only
  when the full same-batch smoke bundle is present, fresh, and passed; missing,
  stale, failed, or mixed-batch receipts fall back to
  `scripts/verify_upstream_slices.py --mode smoke` so `main` validation
  regenerates real receipts instead of failing on missing files alone.
- PR-route governance closeout now treats `trusted_pr` route exemptions for
  `inventory_matrix_gate` and `same_run_cohesion` as optional evidence in the
  pre-push closeout builder, so lightweight PR-bound pushes do not fail merely
  because workflow-dispatch-only upstream receipts were intentionally skipped.
- Hosted-first `push_main` closeout keeps `current_run_consistency` fail-closed
  by default and only downgrades that receipt to advisory when the governance
  manifest marks `verification_smoke` route-exempt for the current lane, so
  the base `ci` builder does not silently widen the advisory contract beyond
  the documented route-exempt surface.
- The runner-drift report still records GitHub-hosted toolchain state on every
  lane, but hosted container routes (`trusted_pr`, `untrusted_pr`, and
  `push_main`) keep host-only commands such as `docker` and `sudo` report-only
  so the orchestrator policy lane does not mistake container-local absence for
  a host-runner regression.
- Governance evidence refresh now also reuses a fresh
  `clean_room_recovery.json` receipt when that report already passed inside the
  freshness window, which keeps repeated PR-bound CI-fix pushes from rerunning
  the full clean-room bundle just to restate the same healthy local receipt;
  shell-written clean-room receipts now count `status = "ok"` the same way as
  `pass` / `passed`, so pre-push governance refresh does not ignore a healthy
  local receipt just because the shell script used a different success token.
- Mainline live-provider probes keep the stricter credential contract: process
  env first, `~/.codex/config.toml` second, while repo-local dotenv files and
  shell-export fallback stay disabled on `CI` / strict mainline contexts.
- The route-report governance coverage in
  `apps/orchestrator/tests/test_ci_governance_policy_extended.py` now tracks
  the grouped `GITHUB_ENV` export block used by the hardened workflow instead
  of assuming one variable per append line, and the `Policy and Security` lane
  now expects a repo-owned `GH_TOKEN` pass-through plus direct GitHub REST API
  alert queries so hosted container slices do not depend on a container-local
  `gh` binary.
- The route-report governance coverage in
  `apps/orchestrator/tests/test_ci_governance_policy_extended.py` now tracks
  the grouped `GITHUB_ENV` export block used by the hardened workflow instead
  of assuming one variable per append line, and the `Policy and Security` lane
  now expects a repo-owned `GH_TOKEN` pass-through plus direct GitHub REST API
  alert queries so hosted container slices do not depend on a container-local
  `gh` binary.
