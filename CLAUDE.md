# CLAUDE.md

This file mirrors the root AI entrypoint for tools that prefer `CLAUDE.md`.

## Read First

1. `README.md`
2. `docs/README.md`
3. `docs/specs/00_SPEC.md`
4. `docs/architecture/runtime-topology.md`
5. `AGENTS.md`

## Working Rules

- keep diffs small and auditable
- run real verification commands before claiming success
- keep docs and code synchronized
- keep runtime output out of tracked source
- keep public test/probe fixtures free of maintainer-local absolute paths and
  raw token-shaped literals; prefer generic workspace roots plus synthetic
  string assembly, keep placeholder security URIs pinned to the exact
  `example.com` contract, preserve `.jsonl` temp-report hints in portable scan
  scratch names, fail closed on tracked direct email/phone markers plus
  forbidden runtime files, fail closed on open GitHub secret/code scanning
  alerts in local hooks and pre-push while GitHub-hosted `trusted_pr`,
  `untrusted_pr`, and hosted-first `push_main` Quick Feedback / hosted policy
  lanes stay advisory under integration-token and first-analysis timing
  limits, keep workflow static security (`actionlint` + `zizmor`), canonical
  secret scanning, and Trivy dependency scanning wired into repo-owned
  entrypoints, and sync the root/docs entrypoints when that contract shifts
- host-process safety is fail-closed: worker/test/orchestrator paths must not
  use `killall`, `pkill`, process-group kills, negative/zero PID signals, or
  AppleScript `System Events`; terminate only recorded child handles and stop
  with manual cleanup instructions when stale repo-owned runtime state already
  exists
- repo-owned `scripts/*.py` entrypoints must keep shared helper imports usable
  when they are executed directly or through `bash scripts/run_governance_py.sh`;
  do not assume the repo root is already present on `PYTHONPATH`
- host-compatible pre-commit hooks that execute repo-owned `scripts/*.py`
  entrypoints must use the same wrapper path (or an equivalent `python3 -B`
  contract) so clean hook runs do not leave repo-local `__pycache__` residue
- keep public CI hosted-first: fork PRs stay low-privilege on GitHub-hosted
  lanes, and sensitive verification stays on protected manual dispatch lanes
- GitHub repo-first pushes may hand CI an all-zero base SHA; repo-owned
  doc-drift/doc-sync gates must skip `ci-diff` comparison in that case instead
  of failing before the repository has a real baseline commit
- treat `configs/github_control_plane_policy.json` as the machine SSOT for
  required check names, and point human-facing summaries back to the root
  `README.md` instead of duplicating the list here
- `GitHub Control Plane` workflow should prefer the repo secret
  `GH_ADMIN_TOKEN` when it needs to prove admin-only repository APIs, because
  the default workflow token cannot read Actions permissions, branch
  protection, or vulnerability-alert endpoints on the live control plane
- protected upstream/live-smoke receipts are route-exempt on `trusted_pr`,
  `untrusted_pr`, and hosted-first `push_main`; those routes must not fail
  solely because manual closeout/provider credentials are absent
- hosted `push_main` governance closeout also treats `upstream_report`,
  `upstream_same_run_report`, and `current_run_consistency` as advisory when
  the manifest already marks upstream/live smoke route-exempt
- when dashboard dependency lock refreshes land, keep the app-local dashboard
  lockfile aligned with the root workspace lock updates and document the change
- the current security-only dashboard lock refresh keeps `lodash-es@4.18.1`
  pinned through the repo-owned override layer so `lighthouse@13.0.3` does not
  drift back onto the vulnerable `lodash-es@4.17.23` transitive path, without
  expanding this maintenance slice into a broader Lighthouse upgrade
- when dashboard or desktop lock maintenance changes the shipped dependency
  contract, update the root docs entrypoints in the same patch so doc-sync and
  closeout gates describe the live state
- when one closeout patch touches both dashboard and desktop packaging, mirror
  that decision in the root docs entrypoints instead of relying on module docs
  alone
- when the live public GitHub surface moves or changes repository URLs, sync
  the root docs/security/storefront entrypoints in the same patch so
  repo-side links do not drift behind the published `OpenVibeCoding`
  surface
- when security reporting wording changes, keep `SECURITY.md`, `SUPPORT.md`,
  issue template contact links, and the root README aligned in the same patch
- when security-scan or fixture-hygiene changes touch tracked test literals or
  scan wrappers, keep this file, `AGENTS.md`, and the root/docs entrypoints
  aligned in the same patch; current examples include generic workspace roots
  instead of maintainer-local absolute paths, runtime-built token-like
  fixtures, and BSD-safe temp-file naming in `scripts/security_scan.sh`
- when dashboard/operator wording or intake/runtime contracts change, sync the
  root AI/docs entrypoints in the same patch so doc-sync gates keep following
  the live English-first dashboard surface and the current intake/probe rules
- when runtime-provider compatibility changes the orchestrator client contract,
  sync the root AI/docs entrypoints in the same patch; current examples include
  the Switchyard runtime-first `/v1/runtime/invoke` adapter, the forced
  `chat_completions` mode on chat-only intake/operator paths, and the
  fail-closed rule that keeps MCP tool execution on tool-capable providers;
  Quick Feedback-safe helper extraction, dead-code-clean
  `provider_resolution` compatibility exports, and env-governance allowlist
  updates for read-only runtime-capability summaries follow the same rule
- when role-contract / prompt-ref / handoff-summary semantics change the
  orchestrator contract or preview surfaces, sync the root AI/docs entrypoints
  in the same patch; current examples include resolved `role_contract`,
  intake `role_contract_summary`, summary/risk-only handoff, and the
  governance-backed metadata in `policies/agent_registry.json` plus
  `configs/env_direct_read_allowlist.json`
- when Prompt 4-style binding/read-surface work extends those role-contract
  surfaces, keep the root AI/docs entrypoints aligned in the same patch;
  current examples include contract-derived `role_binding_summary` in
  PM-facing `run_intake(...)` responses plus the same summary persisted into
  run manifests, alongside registry-backed SEARCHER/RESEARCHER
  `mcp_bundle_ref` hardening in `policies/agent_registry.json`
- when CI maintenance changes the Python dependency audit contract or the
  tracked runtime report namespaces, sync the root AI/docs entrypoints in the
  same patch; current examples include `.runtime-cache/test_output/ci/` and
  `configs/pip_audit_ignored_advisories.json`, plus the dashboard
  and desktop install-time ENOSPC recovery knobs plus the Docker daemon
  precheck retry knobs registered in `configs/env.registry.json`, and the
  bounded transient npm registry socket-timeout retries inside
  `scripts/install_dashboard_deps.sh` plus
  `scripts/install_desktop_deps.sh`; current CI credential/evidence examples
  also include the upstream receipt refresh
  fallback to `scripts/verify_upstream_slices.py --mode smoke` and the strict
  live-provider rule that resolves process env first and `~/.codex/config.toml`
  second while keeping dotenv and shell-export fallbacks disabled on mainline;
  staged dashboard UI-audit workspaces must also keep package-local frontend
  sources inside the temporary workspace root instead of relying on out-of-root
  symlinks that Turbopack rejects, and repeated pnpm `ERR_PNPM_ENOENT`
  recovery should escalate to workspace-local store recovery instead of
  repeating the same failing fresh-store copy path
- when retention and space-governance contracts change, sync the root AI/docs
  entrypoints in the same patch; current examples include retention
  `log_lane_summary` + `space_bridge`, serial-only heavy cleanup ordering,
  cleanup inventory consistency checks, and the rule that `~/.cache/cortexpilot`
  is the repo-external strong-related root while shared ecosystem layers stay
  observe-only; current Docker runtime lane changes must keep cleanup scoped to
  CortexPilot-owned images/containers/volumes while workstation-global
  Docker/cache totals stay audit-only; current machine-temp examples also
  include `~/.cache/cortexpilot/tmp/docker-ci/runner-temp-*`,
  `~/.cache/cortexpilot/tmp/clean-room-machine-cache.*`, and
  `~/.cache/cortexpilot/tmp/clean-room-preserve.*`, which stay
  repo-external-related under wave3 instead of defaulting to Darwin `TMPDIR`;
  current closeout slices also include `machine_cache_summary` +
  `machine_cache_auto_prune` in the retention/space-governance bridge, the
  structured Docker runtime receipt at
  `.runtime-cache/cortexpilot/reports/space_governance/docker_runtime.json`,
  repo-owned buildx local cache under
  `~/.cache/cortexpilot/docker-buildx-cache/`, plus the repo-owned singleton
  Chrome root under `~/.cache/cortexpilot/browser/chrome-user-data/` that
  `allow_profile` now attaches to over the fixed CDP endpoint instead of
  reusing the default Chrome root; CI / docker / clean-room lanes still fail
  closed back to `ephemeral`
- when workflow-case / proof-pack / compare / task-pack / queue-scheduling
  contracts change, sync the root AI/docs entrypoints in the same patch; the
  current examples are `.runtime-cache/cortexpilot/workflow-cases/`,
  `proof_pack.json`, dedicated run-compare surfaces, desktop Flight Plan
  preview, and timezone-safe queue scheduling inputs
- when Version B closeout work changes the public front door, shared locale
  substrate, read-only MCP exposure, or operator-copilot surfaces, sync
  `README.md`, `docs/index.html`, `docs/releases/first-public-release-draft.md`,
  `apps/orchestrator/README.md`, and the root AI entrypoints in the same patch
  so doc-drift and doc-sync gates keep following the live Command Tower /
  Workflow Cases / Proof & Replay contract
- when ecosystem-binding, builder-entrypoint, or distribution-facing surfaces
  change, sync the root AI/docs entrypoints in the same patch; current examples
  include `docs/architecture/ecosystem-and-builder-surfaces-v1.md`, the
  package-facing `frontend-api-client` / `frontend-shared` READMEs, and the
  dashboard home/docs landing sections that explain Codex / Claude Code /
  read-only MCP plus the first-run -> proof -> share loop
- when a follow-up builder/adoption slice adds a legal contract-package guide
  or surfaces integrations/skills adoption more directly on the dashboard home,
  keep this file, `AGENTS.md`, and the root/docs entrypoints aligned in the
  same patch; current examples include
  `packages/frontend-api-contract/docs/README.md`, the dashboard-home
  integrations section in `apps/dashboard/components/DashboardHomeStorySections.tsx`,
  and the docs-base resolver now honoring `/integrations/` and `/skills/`
- when a later ecosystem-adoption slice adds copy-paste starter kits or
  ecosystem-native example configs, keep this file, `AGENTS.md`, and the
  root/docs entrypoints aligned in the same patch; current examples include
  `docs/agent-starters/index.html`, `examples/coding-agents/README.md`, the
  shared read-only MCP example under `examples/coding-agents/mcp/`, and the
  local plugin-bundle manifests under
  `examples/coding-agents/plugin-bundles/` that stay starter-only rather than
  official marketplace artifacts
- when a later Phase 2 wave adds dedicated public sub-entrypoints (for example
  `/ecosystem/`, `/builders/`, `/use-cases/`, `/compatibility/`) or moves additional dashboard home
  hero/ecosystem/AI/builder copy into the shared locale substrate, sync the
  root AI/docs entrypoints in the same patch so doc-sync gates can trace the
  new discoverability surfaces without guessing
- when a follow-up Phase 2 wave adds new public discoverability hubs such as
  `/ai-surfaces/` or makes the dashboard-home locale toggle drive
  server-rendered copy through cookie-backed preference sync, update the root
  AI/docs entrypoints and release-facing docs in the same patch so doc-sync
  gates can follow both the public wording and the locale-contract change;
  current examples include `docs/ai-surfaces/index.html`, the extracted
  `apps/dashboard/components/DashboardHomeStorySections.tsx` narrative layer,
  and the AI Work Command Tower wording now shared by the dashboard metadata
  and the public Pages landing copy
- when that wave also moves the dashboard-home story into a dedicated
  shared-copy component, keep this file, `AGENTS.md`, and `CHANGELOG.md`
  aligned in the same patch so quick-feedback gates can trace the locale-aware
  rendering path instead of inferring it from page-local literals
- keep the root wording aligned when the dashboard home mixes cookie-backed
  locale SSR with client-side locale refresh, because that split is easy to
  miss when only the page diff is inspected
- the current concrete examples are `docs/ai-surfaces/index.html`,
  `apps/dashboard/components/DashboardHomeStorySections.tsx`,
  `packages/frontend-shared/uiLocale.ts`, and dashboard metadata that now says
  "AI Work Command Tower for Codex, Claude Code, and MCP"
- when the next Phase 2 wave hardens desktop `Run Detail` / `Overview`
  operator wording through the shared locale and shared status-presentation
  substrate, keep this file, `AGENTS.md`, and the desktop/module docs aligned
  in the same patch; current examples include `apps/desktop/README.md`,
  `packages/frontend-shared/uiCopy.ts`, and locale-aware desktop tests for
  `RunDetailPage` / `OverviewPage`
  `packages/frontend-shared/uiLocale.ts`, and dashboard metadata that now says
  "AI Work Command Tower for Codex, Claude Code, and MCP"
- when a later Phase 2 wave hardens desktop `Run Detail` / `Overview`
  operator-surface locale coverage or moves more desktop strings onto
  `@cortexpilot/frontend-shared`, keep the root AI entrypoints aligned in the
  same patch; current examples include locale-aware desktop status labels,
  shared-copy Run Detail table/action chrome, and zh-CN regression coverage
- when a front-door discoverability wave adds or reprioritizes public
  integration/skills/SEO entrypoints, keep this file, `AGENTS.md`, and the
  root/docs entrypoints aligned in the same patch; current examples include
  `docs/integrations/index.html`, `docs/compatibility/index.html`,
  `docs/skills/index.html`, `docs/robots.txt`, `docs/sitemap.xml`, the
  docs-navigation registry move that now treats
  ecosystem/use-cases/AI/MCP/API/builders/compatibility as primary public
  entrypoints, and the skills quickstart CTA shift toward in-page
  adoption/maintainer anchors instead of a dead public-repo tree link
- when dashboard route-level discoverability or Workflow Case list locale
  coverage changes, keep this file, `AGENTS.md`, and the root/docs entrypoints
  aligned in the same patch; current examples include route metadata on
  `apps/dashboard/app/command-tower/page.tsx`,
  `apps/dashboard/app/workflows/page.tsx`, and
  `apps/dashboard/app/workflows/[id]/page.tsx`, plus the shared-copy workflow
  list substrate and the matching metadata/locale regression coverage in
  `apps/dashboard/tests/command_tower_page_ssr_query_repro.test.ts`,
  `apps/dashboard/tests/workflow_detail_page.test.tsx`, and
  `apps/dashboard/tests/workflows_queue_page.test.tsx`
  list substrate now carried through `packages/frontend-shared/uiCopy.ts` and
  `packages/frontend-shared/uiCopy.js`
- when dashboard home discoverability grows a new integrations/skills adoption
  layer or package-contract CTA path, keep this file, `AGENTS.md`, and the
  root/docs entrypoints aligned in the same patch; current examples include
  `apps/dashboard/components/DashboardHomeStorySections.tsx`, the public-docs
  resolver allowlist in `apps/dashboard/lib/env.ts`, the matching env/home
  regression coverage, and the repo-owned
  `packages/frontend-api-contract/docs/README.md` guide that now sits between
  the public API quickstart and the raw generated `.d.ts` files
- when a later discoverability wave adds a public compatibility/adoption
  matrix, keep this file, `AGENTS.md`, and the root/docs/dashboard entrypoints
  aligned in the same patch; current examples include
  `docs/compatibility/index.html`, `configs/docs_nav_registry.json`,
  `docs/sitemap.xml`, the dashboard public-docs allowlist in
  `apps/dashboard/lib/env.ts`, and the dashboard-home integration layer now
  pointing teams toward a compatibility ladder before they choose protocol,
  skills, builders, or proof-first onboarding
- when a follow-up discoverability wave adds public copy-paste starter kits or
  local bundle examples for Codex / Claude Code / OpenClaw, keep this file,
  `AGENTS.md`, and the root/docs entrypoints aligned in the same patch;
  current examples include `docs/agent-starters/index.html`,
  `docs/examples/agent-starters/`, `examples/coding-agents/`,
  `configs/root_allowlist.json`, and the root/docs wording that now separates
  host-platform plugin reality from CortexPilot's own publication state
- when a later polish wave compresses the public homepage or dashboard-home
  discovery stack into a clearer route page, keep this file, `AGENTS.md`, and
  the root/docs/dashboard entrypoints aligned in the same patch; current
  examples include the homepage mini-nav, reduced hero CTA set,
  compatibility-first routing, and the dashboard-home adoption layer
  consolidating ecosystem / integrations / AI / builders into one smaller
  decision surface
- when a follow-up CTA polish slice changes that dashboard adoption layer
  again, keep this file, `AGENTS.md`, `README.md`, `CHANGELOG.md`,
  `docs/README.md`, and `apps/dashboard/README.md` aligned in the same patch;
  current examples include keeping `/compatibility/` as the main routing card,
  restoring a lighter `/use-cases/` proof-first side door, and updating the
  adoption-nav accessibility label so the dashboard no longer advertises the
  old integration-only action group
- when the next Phase 2 wave deepens public `MCP` / `API` discoverability,
  keep this file, `AGENTS.md`, and the root/docs entrypoints aligned in the
  same patch; current examples include `docs/mcp/index.html`,
  `docs/api/index.html`, the dashboard-home AI CTA, and root navigation that
  points readers toward read-only MCP and API quickstarts without implying
  hosted/write-capable MCP
  shared-copy Run Detail table/action chrome, and zh-CN regression coverage
- when Prompt 6-style skills-bundle and workflow/control-plane read-model work
  lands, keep this file, `AGENTS.md`, `README.md`, and the orchestrator/docs
  entrypoints aligned in the same patch; current examples include
  `policies/skills_bundle_registry.json`, enriched
  `role_binding_summary.skills_bundle_ref` metadata, and
  `workflow_case_read_model` on workflow/control-plane reads that remain
  explicitly read-only
- when a Prompt 7-style frontend slice projects those same read models onto
  dashboard or desktop Workflow Case detail surfaces, keep this file, the root
  AI entrypoints, and the module READMEs aligned in the same patch; current
  examples include the read-only `Workflow read model` cards on
  `apps/dashboard/app/workflows/[id]/page.tsx` and
  `apps/desktop/src/pages/WorkflowDetailPage.tsx`, plus the typed frontend
  `RoleBindingReadModel` / `WorkflowCaseReadModel` surfaces that stay below
  `task_contract`
- when a Prompt 8-style slice converges the OpenAPI/frontend-contract
  generation chain or projects `role_binding_read_model` onto dashboard/desktop
  Run Detail surfaces, keep this file, the root AI/docs entrypoints, and the
  module READMEs aligned in the same patch; current examples include
  `docs/api/openapi.cortexpilot.json`, generated
  `@cortexpilot/frontend-api-contract` read-model types, and the read-only Run
  Detail operator summaries that continue to treat `task_contract` as
  execution authority
- when a Prompt 9-style slice turns role / bundle / runtime truth into
  dashboard/desktop `Agents` + `Contracts` operator catalog surfaces, keep this
  file, the root AI/docs entrypoints, and the module READMEs aligned in the
  same patch; current examples include the registry-backed `/api/agents` role
  catalog, the normalized `/api/contracts` inspector payload, and the same
  read-only authority/advisory wording carried through both web and desktop
  operator shells
- when a Prompt 10-style slice turns those read-only catalog surfaces into a
  repo-owned role-configuration control plane, keep this file, the root
  AI/docs entrypoints, and the module READMEs aligned in the same patch;
  current examples include `policies/role_config_registry.json`, the
  role-config preview/apply routes under `/api/agents/roles/{role}/config*`,
  the generated frontend contract bindings for those routes, and the rule that
  `Agents` becomes the control desk while `Contracts` stays inspector-first and
  `task_contract` remains the only execution authority
- when a Prompt 10 follow-up slice adds derived runtime capability posture to
  intake previews, run manifests, operator-copilot briefs, or the
  dashboard/desktop `Contracts` and `Run Detail` surfaces, keep this file, the
  root AI/docs entrypoints, and the module READMEs aligned in the same patch;
  current examples include `execution_plan_report.runtime_capability_summary`,
  `role_binding_read_model.runtime_binding.capability`, the shared
  dashboard/desktop runtime-capability copy, and the fail-closed wording that
  keeps chat-compatible lanes separate from tool execution parity
- when a Prompt 10 closeout fix changes how contract package entrypoints load
  on CI/governance paths, keep this file, the root AI/docs entrypoints, and
  the relevant module/docs READMEs aligned in the same patch; current examples
  include lazy-loading `cortexpilot_orch.contract` so `ContractValidator`
  imports and schedule-boundary checks stay below runtime-provider dependencies
  such as `httpx` on Quick Feedback lanes
- when a Prompt 10 Wave 3 slice hardens builder/client entrypoints into a
  repo-owned starter path, keep this file, the root AI/docs entrypoints, and
  the package/docs entrypoints aligned in the same patch; current examples
  include `packages/frontend-api-client/examples/control_plane_starter.local.mjs`,
  the package-facing `createControlPlaneStarter(...)` bootstrap flow, and the
  rule that the starter remains a repo-owned integration edge rather than a
  hosted SDK or marketplace claim
- when dashboard dependency verification learns about new runtime-critical
  packages for quick/clean-room lanes, keep this file, `AGENTS.md`, and the
  relevant package/docs entrypoints aligned in the same patch; current examples
  include `scripts/install_dashboard_deps.sh` verifying that `jsdom` itself
  loads successfully so partial dashboard installs fail fast before the quick lane
  claims success
- when the Final-100 / Wave 4 follow-up slice adds hosted pilot readiness or
  queue-first mutation groundwork, keep this file, `AGENTS.md`, and the root
  AI/docs entrypoints aligned in the same patch; current examples include
  `render.yaml`, `docs/runbooks/render-hosted-operator-pilot.md`, the hosted
  `CORTEXPILOT_API_ALLOWED_ORIGINS` env wiring across `.env.example`,
  `apps/orchestrator/.env.example`, `configs/env.registry.json`, and
  `configs/env_direct_read_allowlist.json`, plus the rule that
  `apps/orchestrator/src/cortexpilot_orch/mcp_queue_pilot_server.py` and queue
  preview/cancel routes remain repo-owned operator groundwork instead of live
  hosted proof or public write-capable MCP
- when a Final-100 hosted/operator follow-up only moves governance,
  queue-pilot, or API posture files after the public docs already moved, keep
  this file and `AGENTS.md` updated in the same patch so the ci-diff doc-sync
  gate can see the root AI navigation layer refresh above
  `configs/env_direct_read_allowlist.json`, `render.yaml`, and the guarded
  queue preview/cancel operator surfaces instead of flagging logic-only drift
- when staged dashboard smoke builds change their dependency-install behavior
  or the `apps/dashboard/lib/types.ts` export bridge, keep this file and the
  root/module docs aligned in the same patch so UI-audit / pre-push failures
  stay attributable to staging drift vs real dashboard regressions
- when clean-room recovery changes the package-local install order for
  `frontend-api-client`, keep this file and the root docs aligned in the same
  patch so recovery gates fail on product regressions instead of missing local
  package installs
- when clean-room recovery changes the ordering between workspace cleanup and
  broad runtime deletion, keep this file and the root docs aligned in the same
  patch; current examples include running `scripts/cleanup_workspace_modules.sh`
  before the clean-room `rm -rf` sweep, plus quarantining stubborn dashboard
  module residue when recursive delete alone is not enough, so the recovery
  lane does not abort early on transient bind-mounted trees

## Key Commands

- `npm run bootstrap`
- `npm run ci`
- `npm run ci:strict`
- `npm run test`
- `npm run test:quick`
- `npm run scan:host-process-risks`
- `npm run space:audit`
- `npm run docker:runtime:audit`
- `bash scripts/check_repo_hygiene.sh`
- `npm run scan:workflow-security`
- `npm run scan:trivy`
- `npm run security:scan:closeout`
- `pre-commit run --all-files`

## Generated Governance Context

<!-- GENERATED:ci-topology-summary:start -->
- trust flow: `ci-trust-boundary -> quick-feedback -> hosted policy/core slices -> pr-release-critical-gates -> pr-ci-gate`
- hosted policy/core slices: `policy-and-security, core-tests`
- untrusted PR path: `quick-feedback -> untrusted-pr-basic-gates -> pr-ci-gate`
- protected sensitive lanes: `workflow_dispatch -> owner-approved-sensitive -> ui-truth / resilience-and-e2e / release-evidence`
- canonical machine SSOT: `configs/ci_governance_policy.json`
<!-- GENERATED:ci-topology-summary:end -->

<!-- GENERATED:current-run-evidence-summary:start -->
- authoritative release-truth builders must consume `.runtime-cache/cortexpilot/reports/ci/current_run/source_manifest.json`.
- the live current-run authority verdict belongs to `python3 scripts/check_ci_current_run_sources.py` and `.runtime-cache/cortexpilot/reports/ci/current_run/consistency.json`.
- current-run builders: `artifact_index/current_run_index`, `cost_profile`, `runner_health`, `slo`, `portal`, `provenance`.
- docs and wrappers must not hand-maintain live current-run status; they must point readers back to the checker receipts.
- if the current-run source manifest is missing, authoritative current-run reports must fail closed or run only in explicit advisory mode.
<!-- GENERATED:current-run-evidence-summary:end -->

<!-- GENERATED:coverage-summary:start -->
- repo coverage snapshot unavailable
- run `npm run coverage:repo` to refresh this fragment.
<!-- GENERATED:coverage-summary:end -->
