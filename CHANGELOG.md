# Changelog

All notable changes to this repository will be documented in this file.

## Unreleased

### Changed

- replaced the Node 20-pinned GitHub Dependency Review action with the
  repo-owned `check_dependency_review_gate.py` wrapper over GitHub's official
  dependency-graph compare API, then bumped the pinned `actions/checkout`,
  `actions/upload-artifact`, and `actions/download-artifact` workflow SHAs onto
  their Node 24-based majors so hosted CI stops carrying avoidable deprecation
  warnings on the active PR path
- corrected the default localhost full-stack operator path so `npm run dev`
  now truthfully pairs the dashboard with a localhost-only API lane, while
  `dashboard:dev` stays a dashboard-only shell on the expected port; the same
  slice also pulls the dashboard `Runs / Contracts / Agents` first-screen copy
  back into shared command-tower proof / contract / role-desk language instead
  of leaving those pages on scattered inspector phrasing
- pinned transitive dashboard security fixes through the maintained pnpm
  override surfaces so `axios` now resolves to `1.15.0` and `basic-ftp` to
  `5.3.0` in both the root and dashboard lockfiles, clearing the live
  Dependabot alert chain without widening into unrelated dependency upgrades
- added a registry-shaped `manifest.yaml` for the repo-owned
  `openvibecoding-adoption-router` skill inside the coding-agent bundle, then
  synced the distribution contract, skills quickstart, and Codex / Claude Code /
  OpenClaw starter docs so OpenVibeCoding can truthfully describe one cross-tool
  skill artifact as `publish-ready but deferred` without claiming any live
  marketplace or registry listing
- added a repo-owned workflow/dependency/security closeout lane by bootstrapping
  pinned `actionlint`, `zizmor`, `trivy`, `gitleaks`, and `trufflehog`
  binaries through `scripts/lib/release_tool_helpers.sh`; the same slice adds
  `check_workflow_static_security.sh`, `check_trivy_repo_scan.sh`, and
  `check_secret_scan_closeout.sh`, wires workflow security into local
  pre-commit/pre-push and GitHub Quick Feedback, wires Trivy into the strict
  dependency-audit slice, and adds official pull-request Dependency Review via
  `.github/dependency-review-config.yml` plus `PR CI Gate` aggregation; on
  GitHub-hosted `pull_request` routes the live alerts query now stays
  advisory-only because the integration token may not be allowed to read the
  alerts APIs there
- hardened the live GitHub alert gate for containerized CI by teaching
  `check_github_security_alerts.py` to query the GitHub REST API directly from
  `GH_TOKEN` / `GITHUB_TOKEN` while falling back to `gh auth token` only for
  local token discovery, granting the `Policy and Security` lane
  `security-events: read` plus an explicit `GH_TOKEN` injection, aligning the
  route-report policy test with the grouped `GITHUB_ENV` export block used by
  the current workflow hardening, and teaching hosted `trusted_pr` /
  `untrusted_pr` / `push_main` repo hygiene plus Quick Feedback to keep the
  live alerts query advisory when the GitHub integration token still cannot
  read the alerts APIs or the first hosted analysis has not materialized yet
- scrubbed maintainer-local path fixtures and raw token-looking literals from
  public orchestrator/security tests, generalized the modules-root ignore rule,
  and documented the same public-fixture hygiene contract across the root AI
  entrypoints plus module docs so Quick Feedback/doc-sync gates can trace the
  security cleanup end to end; the follow-up hardening now keeps
  `security_scan.sh` placeholder-URI matching exact to `example.com` and
  preserves `.jsonl` hints in BSD-safe temp report names, while a new
  `check_public_sensitive_surface.py` gate fails closed on tracked local paths,
  raw token-like literals, direct email/phone markers, and forbidden tracked
  runtime files; a later hardening slice also adds
  `check_github_security_alerts.py` so pre-push and Quick Feedback fail closed
  on open GitHub secret-scanning and code-scanning alerts
- aligned governance evidence refresh with the hosted-first public CI contract
  by treating protected upstream/live-smoke receipts as route-exempt on
  `trusted_pr`, `untrusted_pr`, and `push_main`, so base CI no longer fails on
  missing manual closeout/provider credentials
- aligned governance closeout consumption with that same hosted-first rule so
  route-exempt `push_main` lanes treat `upstream_report`,
  `upstream_same_run_report`, and `current_run_consistency` as advisory rather
  than blocking payloads
- hardened repo bootstrap CI by teaching doc-drift/doc-sync to skip `ci-diff`
  comparisons when GitHub push events use the all-zero base SHA on a
  repository-first push, and by teaching `GitHub Control Plane` to prefer the
  repo secret `GH_ADMIN_TOKEN` when it needs admin-only repository API proofs
- scrubbed maintainer-local and token-looking fixture literals from tracked
  security tests, generalized the matching `.gitignore` rule so it no longer
  embeds a user-home fragment, and updated `scripts/security_scan.sh` to use
  BSD-safe temp-file naming while keeping placeholder-only trufflehog
  allowlists explicit and narrow
- added a public `agent-starters` entrypoint plus tracked `examples/coding-agents/`
  starter kits so Codex, Claude Code, and OpenClaw teams can copy real
  read-only MCP configs, repo-owned skills/bootstrap files, and local
  plugin-bundle examples without inventing hosted/store claims; the same slice
  also tightened the root/package/docs wording around ecosystem-native anchors
  and vendored-workspace adoption
- fixed the repo-owned Chrome singleton launch path on non-macOS lanes by
  initializing the macOS-only `launched_via_mac_open` flag before the platform
  branch, so Linux/GitHub-hosted `test_repo_chrome_singleton` paths stop
  crashing with `UnboundLocalError` while the macOS `open -na` retry contract
  remains intact
- hardened the host-compatible pre-commit lane so repo-owned `scripts/*.py`
  hooks now use the governance wrapper instead of direct `python3` entrypoints,
  keeping clean hook runs deterministic and free of repo-local `__pycache__`
  residue after the gate finishes
- hardened the repo-owned Chrome singleton closeout contract so unstable
  launches fail closed instead of pretending the browser is healthy: the
  singleton launcher now retries macOS app boot through `open -na` after an
  unstable bind, clears stale singleton residue before the next attach, and
  surfaces current machine browser roots in `browser:chrome:status` so login
  and browser-pressure debugging stay repo-scoped and auditable; stale-root
  cleanup now keys off the requested CDP port instead of the default port, and
  direct-execution governance helpers now keep their tracked-child imports
  working without a repo-root `PYTHONPATH` assumption
- tightened the Final-100 Wave 4 truth layer by documenting the default-off,
  queue-only write-MCP pilot in
  `.agents/InternalDocs/runbooks/write-mcp-queue-pilot.md`,
  adding a share-ready `news_digest` Workflow Case recap asset, and syncing the
  root/use-case/storefront/env wording so the public contract still says
  read-only MCP while the guarded queue pilot stays an internal operator-only
  later gate
- added an explicit host/process safety gate for live closeout paths:
  `npm run scan:host-process-risks` now checks the repo for forbidden broad
  cleanup patterns, shared host-safety helpers back the desktop/browser cleanup
  scripts, and the governed queue-mutation allowlist wording now explicitly
  covers approval-gated queue pilot surfaces alongside the existing admin
  routes
- replaced the old shared-root `allow_profile` model with a repo-owned Chrome
  singleton workspace under `~/.cache/openvibecoding/browser/chrome-user-data`,
  added explicit `browser:chrome:migrate|launch|status` entrypoints, moved
  Playwright browser/search cleanup onto the live-CDP lifetime instead of
  post-teardown best effort, and marked the browser subtree as protected +
  cap-excluded so retention/governance reports keep it visible without
  auto-pruning it; the default singleton CDP contract now uses port `9341`,
  and the repo-safe machine browser pressure threshold now waits only after
  more than 6 live browser instances instead of 4; same-root legacy singleton
  processes on the old port now relaunch onto `9341` instead of being treated
  as foreign occupants
- hardened cache/browser closeout by unifying repo-authored runtime artifacts
  under `.runtime-cache/`, formalizing build/dependency exceptions, adding a
  default 20 GiB + TTL machine-cache retention contract for
  `~/.cache/openvibecoding`, introducing a rate-limited auto-prune hook before
  heavy cache producers, and keeping `.serena/` as ignore-only local MCP state
  instead of a governed repo cache
- added repo-owned Docker runtime governance receipts plus local buildx cache
  under `~/.cache/openvibecoding/docker-buildx-cache/`, so the Docker runtime
  lane now reports managed image/container/volume/build-cache totals through
  `.runtime-cache/openvibecoding/reports/space_governance/docker_runtime.json`
  instead of relying only on shell stdout
- switched local browser policy to the real Chrome profile display name
  `openvibecoding`, resolving Chrome `Local State -> profile.info_cache` to the
  actual `Profile N` directory, while forcing CI / docker / clean-room lanes
  back to `ephemeral` and failing closed when the real Chrome executable or
  real profile directory cannot be resolved
- compressed the public homepage and dashboard-home discovery layer so the
  front door now behaves more like a route page: fewer competing hero actions,
  compatibility-first routing, and less repeated subpage summary copy
- kept the dashboard follow-up truthful by turning the proof-first CTA into a
  lighter `Use Cases` side door, removing the dead dashboard case-gallery
  baseline copy, and syncing the dashboard/module/root docs so CI doc-sync
  gates can trace the same adoption contract
- added the homepage mini-nav plus tighter dashboard adoption-path routing so
  Codex / Claude Code / OpenClaw visitors can choose the right path without
  rereading the same MCP / builders / integrations story twice
- opened Extreme Polish Wave 3 by adding a public compatibility matrix for
  Codex / Claude Code / OpenClaw / skills / builders / proof-first onboarding,
  wiring that adoption ladder through the GitHub Pages landing page,
  integration/skills/ecosystem/API/MCP/builder docs, the docs navigation
  registry and sitemap, dashboard home discoverability, package-facing human
  entrypoints, and the root AI guidance so teams can choose the right truthful
  path without fake plugin or marketplace claims
- added a minimal `lodash-es@4.18.1` override on both the root workspace and
  `apps/dashboard` package surfaces so the tracked `lighthouse@13.0.3`
  transitive chain can clear the current Dependabot alerts without forcing a
  broader Lighthouse toolchain upgrade
- opened Extreme Polish Wave 1 by adding truthful public `integrations` and
  `skills` entrypoints plus `robots.txt` / `sitemap.xml`, promoting the
  ecosystem/use-cases/AI/MCP/API/builder ladder into primary docs navigation,
  sharpening the GitHub Pages hero toward the first success path, separating
  default builder onboarding from trusted operator-only mutation add-ons, and
  aligning the frontend starter facade with guarded queue preview/cancel helpers
  plus package tests instead of letting the docs overclaim the starter surface;
  the skills quickstart CTA now stays inside truthful public docs instead of
  linking to a dead public-repo tree path
- hardened dashboard discoverability by adding route-level metadata for
  `Command Tower`, `Workflow Cases`, and `Workflow Case detail`, then moving the
  Workflow Cases list surface onto the shared locale substrate with regression
  coverage for metadata and `zh-CN` rendering so the main operator spine no
  longer falls back to a page-local English island
- tightened dashboard quick-lane dependency verification by teaching
  `scripts/install_dashboard_deps.sh` to validate `jsdom` itself, instead of
  pinning the gate to a transitive `data-urls` layout, alongside the existing
  Next/lighthouse toolchain checks so partial
  dashboard installs fail fast and recover before `npm run test:quick`
  reports a green lane
- fixed governance manifest receipt reuse so `refresh_governance_evidence_manifest.py`
  now accepts the shell-authored clean-room `status = "ok"` token in the same
  path as `pass` / `passed`, preventing pre-push refresh from rerunning the
  full clean-room bundle when a fresh healthy local receipt already exists
- opened Extreme Polish Wave 2 by rendering the dashboard-home
  `Integrations and skills adoption` section, lifting integrations/skills
  adoption into the dashboard home discovery ladder, adding the repo-owned
  `packages/frontend-api-contract/docs/README.md` guide to replace raw
  `@openvibecoding/frontend-api-contract` type-file links, and extending the
  dashboard public-docs resolver so `/integrations/` and `/skills/` follow the
  configured public-docs base instead of falling back to app-local paths
- continued the Omega closeout hardening line by moving the dashboard
  `Run detail` / `Workflow Case detail` page-level copy onto the shared
  locale substrate, keeping the command-tower/operator story aligned across
  English-first and `zh-CN` operator views while syncing the dashboard and
  desktop module READMEs to the same detail-route contract
- tightened the later-gated queue-only MCP pilot into a truly default-off
  operator path: `enqueue_from_run` now requires explicit operator metadata and
  also stays disabled unless `OPENVIBECODING_MCP_QUEUE_PILOT_ENABLE_APPLY=1` is
  enabled in a trusted operator environment, with env governance, examples,
  and docs updated in the same change set
- closed the stale dependabot maintenance shell by explicitly closing PRs
  `#65-#84` with rationale, leaving the active closeout branch/PR as the only
  remaining GitHub work item while keeping browser/profile and Docker hygiene
  rules institutionalized in the root AI guidance
- aligned the command-tower reliability guard with the new locale-driven page
  source and kept the current closeout head carrying an explicit changelog
  entry so PR doc-sync gates can trace the final dashboard/desktop/operator
  follow-up fixes on the same branch head they validate
- closed Prompt 3 by formalizing `Role Contract v1` across schema, policy,
  compiler, validator, intake preview, and handoff summary surfaces while
  syncing the root/orchestrator/docs entrypoints and env-read governance with
  the same resolved role-binding contract
- extended Prompt 4 with registry-backed SEARCHER / RESEARCHER MCP bundle
  hardening plus an advisory `role_binding_summary` on PM-facing
  `run_intake(...)` responses so bundle/runtime state is easier to read without
  presenting that helper surface as execution authority
- deepened Prompt 5 by adding a stable `role_binding_read_model` on run detail
  and read-only MCP surfaces plus resolved MCP tool-set visibility, while
  keeping the execution authority anchored to the task contract itself
- opened Prompt 6 by formalizing `skills_bundle_ref` around a repo-owned
  `policies/skills_bundle_registry.json` authority artifact, enriching
  `role_binding_summary.skills_bundle_ref` with bundle metadata, and adding a
  `workflow_case_read_model` on workflow/control-plane reads while keeping
  `execution_authority = task_contract`
- opened Prompt 7 by projecting the Prompt 5/6 workflow binding read model onto
  dashboard and desktop Workflow Case detail surfaces, typing the frontend
  `RoleBindingReadModel` / `WorkflowCaseReadModel` shapes, and keeping those
  operator cards explicitly below `task_contract` execution authority
- opened Prompt 8 by converging `docs/api/openapi.openvibecoding.json`,
  `generate_frontend_contracts.py`, `@openvibecoding/frontend-api-contract`,
  frontend client/types, and dashboard/desktop Run Detail so
  `role_binding_read_model` is now contract-backed from the generated frontend
  surface through the primary run operator views
- opened Prompt 9 by turning role / bundle / runtime truth into a global
  read-only operator catalog: `/api/agents` now publishes a registry-backed
  role catalog, `/api/contracts` now emits normalized inspector rows, the
  generated frontend contract now covers agents/contracts catalog routes, and
  dashboard/desktop `Agents` + `Contracts` pages project the same advisory
  bundle/runtime posture without becoming execution-authority controls
- opened Prompt 10 Wave 1 by adding a repo-owned role configuration control
  plane: `policies/role_config_registry.json` plus role-config schemas now own
  mutable role defaults, `/api/agents/roles/{role}/config` exposes
  read/preview/apply surfaces, generated frontend contracts/client paths now
  cover those routes, dashboard/desktop `Agents` pages now host the minimal
  preview/apply desk, and `Contracts` remains inspector-first while
  `task_contract` stays the only execution authority
- opened Prompt 10 Wave 2 by projecting a derived runtime capability summary
  (`lane`, `compat_api_mode`, `provider_status`, `tool_execution`) onto intake
  previews, run manifests, operator-copilot briefs, and the dashboard/desktop
  `Contracts` + `Run Detail` operator surfaces while keeping `task_contract`
  as the only execution authority and preserving fail-closed tool/runtime
  posture
- opened Prompt 10 Wave 3 by hardening the repo-owned frontend starter path:
  `@openvibecoding/frontend-api-client` now documents and exports
  `createControlPlaneStarter(...)`, the package ships a runnable local example
  at `packages/frontend-api-client/examples/control_plane_starter.local.mjs`,
  and the builder/API/docs entrypoints now describe that preview-first starter
  loop without overclaiming a hosted SDK or marketplace surface
- hardened the Prompt 10 follow-up smoke gates by ensuring dashboard dependency
  installs always recreate their runtime log directory and by making
  `apps/dashboard/lib/types.ts` explicitly re-export task-pack/runtime helpers
  for staged UI-audit builds instead of relying on a fragile wildcard-only
  surface
- restored clean-room frontend-api-client recovery by making
  `scripts/check_clean_room_recovery.sh` reinstall package-local
  `frontend-api-client` dependencies before it runs the node smoke bundle
- hardened Prompt 10 closeout CI by lazy-loading
  `openvibecoding_orch.contract` package entrypoints, so Quick Feedback /
  schedule-boundary governance checks no longer pull runtime-provider
  dependencies like `httpx` just to import `ContractValidator`
- hardened the Prompt 10 control-plane CI path by extracting lightweight
  provider-capability helpers for role-config runtime summaries, registering
  the governed env reads in `configs/env_direct_read_allowlist.json`, and
  adding a regression that proves the role-config read surface still imports
  when `httpx` is unavailable on quick-path governance runners; the staged
  dashboard UI-audit workspace now also copies the required
  `packages/frontend-*` sources into its temporary root so Next/Turbopack does
  not reject out-of-root symlinks during smoke builds, and repeated pnpm
  `ERR_PNPM_ENOENT` recovery now escalates from fresh-store retries to a
  workspace-local store path for dashboard/desktop dependency bootstrap lanes,
  including clean-room recovery and prompt-stack pre-push host-compat lanes
- aligned the governance closeout builder with `trusted_pr` route exemptions so
  pre-push closeout no longer fails on missing `upstream_inventory_report` /
  `upstream_same_run_cohesion` artifacts when the evidence manifest has already
  marked those upstream checks as route-exempt on PR-bound lanes
- hardened `scripts/check_log_event_contract.py` so backend log-contract
  samples can bootstrap a repo-owned Python toolchain when the active
  interpreter cannot import orchestrator logging dependencies, keeping
  containerized pre-push governance lanes from failing on `/usr/bin/python3`
  drift alone, and rewrote the bootstrap shell command as one explicit list
  element so GitHub code-quality review no longer flags implicit string
  concatenation on that fallback path
- hardened `scripts/check_clean_room_recovery.sh` by running the repo-owned
  workspace-module cleanup before its broad runtime `rm -rf` sweep, so
  stubborn `apps/dashboard/node_modules` bind-mount residue no longer aborts
  clean-room recovery before the resilient cleanup path runs; the cleanup
  helper itself now quarantines stubborn module trees when recursive removal
  alone is not enough
- taught `refresh_governance_evidence_manifest.py` to reuse a fresh
  `clean_room_recovery.json` receipt instead of rerunning the full clean-room
  bundle on every PR-bound pre-push refresh, keeping the local governance
  manifest strict while making repeated CI-fix pushes finish inside the worker
  execution window
- hardened the Final-100 Wave 4/public-truth layer by tightening proof-state
  wording across the use-case/ecosystem/builder docs, adding a repo-side Render
  hosted-pilot blueprint plus runbook, wiring `/api/health` and configurable
  public API origins for future hosted pilots, and landing queue preview/cancel
  groundwork plus a confirm-gated queue-only MCP pilot server without promoting
  the public contract into write-capable MCP
- cleaned the remaining Wave 1 review-thread blockers by dropping the unused
  fallback assignment in `role_config_registry.py`, keeping
  `provider_resolution` as a dead-code-clean compatibility export surface for
  lightweight helper callers, and aligning the Wave 1 role-binding MCP test
  expectation with the registry-backed `['codex', 'search']` tool set
- added a Switchyard runtime-first adapter for chat-only orchestrator paths,
  forcing `chat_completions` on intake/operator flows while keeping MCP tool
  execution fail-closed until a tool-capable provider path exists, and synced
  the root/orchestrator/docs entrypoints to the same contract
- opened the fifth Phase 2 wave by adding dedicated public `MCP` and `API`
  quickstart entrypoints, wiring the dashboard AI section to the new discovery
  hub, and strengthening keyword-facing discoverability around read-only MCP,
  OpenAPI, contract-facing types, and Codex / Claude Code workflow surfaces
- deepened the third Phase 2 wave by making the dashboard-home locale toggle
  drive the server-rendered home story via cookie-backed preference sync,
  extracting the narrative sections into `DashboardHomeStorySections`, and
  adding a public `AI + MCP + API` Pages entrypoint plus stronger
  ecosystem/builder/use-case SEO metadata and dashboard metadata wording around
  the AI Work Command Tower / Codex / Claude Code / MCP front door while
  syncing the root AI entrypoint files with the same discoverability contract;
  the same wave now also records the locale-aware rendering path explicitly in
  the root AI guidance so quick-feedback gates can trace the shared-copy split
- opened the fourth Phase 2 wave by hardening desktop `Run Detail` /
  `Overview` operator surfaces onto the shared locale/status substrate,
  replacing the remaining high-frequency page-local strings with shared copy,
  and adding zh-CN regression coverage for desktop operator pages
- deepened the second Phase 2 wave by moving the newest dashboard home
  ecosystem/AI/builder hero surfaces into shared home copy, adding dedicated
  public Pages sub-entrypoints for ecosystem/builders/use-cases, and wiring the
  root/docs/dashboard entrypoints toward those discoverability surfaces instead
  of only pointing at blob-level references
- opened the first Phase 2 ecosystem/distribution wave by adding an
  ecosystem-and-builder surface map, package-facing client/shared READMEs, and
  dashboard/docs landing sections that explain Codex / Claude Code / read-only
  MCP plus the first-run -> proof -> share loop without overclaiming a full
  SDK platform or reopening hosted/write-capable MCP
- closed the Version B command-tower packaging lane by aligning the public
  front door around Codex, Claude Code, MCP-readable runs, Workflow Cases, and
  Proof & Replay while syncing the repo description, release wording, Pages
  source, AI entrypoints, and orchestrator topic docs with the same contract
- landed the shared locale/copy substrate across the dashboard shell, desktop
  shell, desktop overview/run detail/command-tower surfaces, and the
  associated status/CTA helpers so English-first public copy and `zh-CN`
  operator rendering now flow through one reusable path instead of scattered
  literals
- added the read-only MCP and bounded operator-copilot surfaces across the
  orchestrator, dashboard, desktop, and docs entrypoints, plus a dashboard vs
  desktop operator-surface parity artifact to guide follow-up closeout slices
- shipped workflow-case snapshots, proof packs, dedicated run-compare surfaces,
  desktop Flight Plan preview, and timezone-safe queue scheduling inputs across
  orchestrator/dashboard/desktop while syncing schema registry, runtime policy,
  and repo-side verification coverage
- closed the public hosted-first loop by moving sensitive verification lanes onto protected `workflow_dispatch` environments, aligning CI route validators/helpers with GitHub-hosted current truth, and syncing the root/module docs plus generated governance fragments with the live public collaboration contract
- let self-hosted CI Docker lanes fall back to direct `bash scripts/docker_ci.sh ...`
  execution when passwordless sudo is unavailable, so `main` push jobs no
  longer fail immediately on runners that can use Docker without an interactive
  sudo prompt
- aligned the live public GitHub repository, Pages, release, and security-reporting links around `OpenVibeCoding` so repo-side docs no longer point at stale repo URLs
- synchronized root AI entrypoints, README, support/security docs, and GitHub issue/PR templates with the current public security-reporting boundary and fallback-channel follow-up
- fixed docs inventory drift by registering `docs/index.html` plus release/proof docs in the docs navigation registry and upgrading the navigation checker to catch summary-vs-registry drift
- aligned the trusted PR CI governance contract with the real workflow aggregation path and extended the checker/tests to catch route-semantic drift
- moved the RUM writer onto config-driven log roots and `log_event.v2`-shaped metadata, then verified the path with targeted orchestrator tests
- expanded repository-level provenance tracking from a single icon bundle to storefront and release-proof asset bundles, and taught the runtime artifact / clean-room checks about the package-local frontend client module cache
- hardened the PM chat E2E runner to follow the current English-first PM intake surface instead of older Chinese-only control labels
- clarified the first public release contract so repo docs now separate tracked proof, missing proof, and live GitHub manual steps
- locked the first public proof-oriented happy path to `news_digest` in release-facing docs until other slices have their own healthy proof
- documented the minimum public benchmark artifact contract and the truth boundary for repo-tracked storefront assets
- rewrote the public README around the PM -> Command Tower -> Runs story instead of repo-internal layout first
- added tracked storefront assets for README hero and social preview source art
- added a minimal Pages-ready landing source under `docs/index.html` with title and description metadata
- split visitor quickstart from contributor onboarding so the first success path is easier to copy and verify
- reduced the public documentation surface to a smaller English-first set
- removed archive, governance, and rehearsal-heavy docs from the public tree
- switched repository collaboration files to an open-source posture
- excluded agent state, runtime caches, logs, and other forbidden surfaces from the public repo seed
- added disk-space governance tooling with audit reports, cleanup preflight gates, and documented repo/external cache boundaries
- moved Gemini-backed UI audits out of default pre-push and PR-blocking lanes into explicit ui-truth / closeout paths
- removed Linux/BSD desktop from the public support contract and from default closeout-required governance receipts
- aligned the GitHub control-plane required check policy with the live PR gate names (`quick-feedback`, `pr-release-critical-gates`, `pr-ci-gate`)
- replaced the legacy `JARVIS` PM-session fixture with a neutral project key so governance closeout artifacts stay identity-clean
- aligned GitHub branch-protection required checks with the lightweight PR route so the live control-plane policy and `pr-ci-gate` stay in sync
- aligned GitHub branch protection required-check names with the active PR route gates (`Quick Feedback`, `PR Release-Critical Gates`, `PR CI Gate`)
- aligned dashboard contract tests with the current English-first Command Tower and RunDetail surfaces instead of older Chinese UI wording
- taught `scripts/ci_slice_runner.sh` to force `PYTHONDONTWRITEBYTECODE=1` so self-hosted policy/core slices stop generating `__pycache__` residue during `main` push validation
- moved CI stage logs, policy snapshots, and the orchestrator coverage JSON under `.runtime-cache/test_output/ci/` so the retention-report gate no longer flags root-level test-output residue on `main` push runs
- aligned remaining dashboard regression tests with the live English-first PM and Command Tower copy instead of legacy Chinese labels
- filtered secret-scan history noise down to a narrow set of known synthetic placeholder findings and removed the live embedded-credential sample from the external web probe tests
- added a machine-readable Python audit ignore contract for unfixed upstream advisories and taught the dependency gate to downgrade only those entries when `pip-audit` reports no fix version
- promoted `pygments` to `2.20.0` inside the orchestrator lock input, regenerated `apps/orchestrator/uv.lock`, and emptied the stale `pip_audit_ignored_advisories.json` entry now that a patched release exists
- taught `install_dashboard_deps.sh` to recover from `ERR_PNPM_ENOSPC` by retrying with a workspace-local pnpm store and hardlink imports on self-hosted `main` validation lanes
- taught `install_desktop_deps.sh` to recover from `ERR_PNPM_ENOSPC` with the same workspace-local retry strategy, while scoping hardlink imports to the recovery attempt and using per-attempt workspace retry stores
- taught `scripts/docker_ci.sh` to retry Docker daemon prechecks with bounded backoff so transient self-hosted socket refusal no longer fail-closes CI at the first probe
- pinned transitive `picomatch` and `brace-expansion` security fixes across the root, dashboard, and desktop lockfile surfaces so GitHub Dependabot findings close on the same documented change set
- removed the optional dashboard `depcheck` package because the dead-code gate already skips when the probe is absent and the package kept an unpatchable `brace-expansion` advisory alive in the default workspace lock surface
- aligned dashboard Command Tower regression tests with the current
  English-first operator surface and synced the root/module docs required by
  doc-sync gates
- aligned intake/probe helper tests and runtime helpers with the current
  response/writer contracts, including optional `task_template` emission and
  dedicated dashboard dependency install logs
- tightened the space-governance / retention contract so cleanup inventory,
  wave receipts, retention lane summaries, and test-output namespace discipline
  now agree on the same repo-local and repo-external cache boundaries
- added a dedicated Docker runtime lane for OpenVibeCoding-owned local CI residue,
  registered its environment knobs, and kept workstation-global Docker/cache
  totals audit-only instead of apply targets

## 2026-03-24

### Changed

- prepared the repository for a rebuilt public main history
- converted the repository license to MIT
- simplified README, contributor, security, support, and AI navigation files
