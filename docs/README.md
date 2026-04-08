# Documentation

This repository keeps its public documentation intentionally small.

The product spine stays stable across the docs entrypoints:

- **Command Tower** for live operator visibility
- **Workflow Cases** for the case-level operating record
- **Proof & Replay** for evidence, compare, and replay review

`docs/index.html` is the current tracked GitHub Pages landing source for the
public docs surface. `docs/README.md` remains the repo-side documentation
summary for contributors and maintainers.

`configs/docs_nav_registry.json` is the machine source of truth for the active
docs inventory. This file is the human-readable summary of that registry.

Daily local verification lives in the root [README](../README.md). Treat this
file as the docs inventory map, not as a second CI manual.

For CI/security/documentation truth, prefer the machine-owned surfaces and
repo-owned gates instead of restating the same rules here:

- `configs/docs_nav_registry.json`
- `configs/ci_governance_policy.json`
- `configs/github_control_plane_policy.json`
- `scripts/check_public_sensitive_surface.py`
- `scripts/check_workflow_static_security.sh`
- `scripts/check_trivy_repo_scan.sh`
- `scripts/check_secret_scan_closeout.sh`

## Repository Entry

This link stays outside the docs inventory registry. Treat it as the public
repository entrypoint rather than a registered docs page.

1. [../README.md](../README.md)

## Primary Registered Docs

These are the active registered docs that stay in the primary docs navigation.

1. [index.html](index.html)
2. [ecosystem/index.html](ecosystem/index.html)
3. [compatibility/index.html](compatibility/index.html)
4. [distribution/index.html](distribution/index.html)
5. [agent-starters/index.html](agent-starters/index.html)
6. [use-cases/index.html](use-cases/index.html)
7. [ai-surfaces/index.html](ai-surfaces/index.html)
8. [integrations/index.html](integrations/index.html)
9. [skills/index.html](skills/index.html)
10. [mcp/index.html](mcp/index.html)
11. [api/index.html](api/index.html)
12. [builders/index.html](builders/index.html)
13. [architecture/runtime-topology.md](architecture/runtime-topology.md)
14. [specs/00_SPEC.md](specs/00_SPEC.md)
15. [runbooks/onboarding-30min.md](runbooks/onboarding-30min.md)
16. [runbooks/space-governance.md](runbooks/space-governance.md)
17. [architecture/mcp-and-operator-copilot-v1.md](architecture/mcp-and-operator-copilot-v1.md)

## Supplemental Registered Docs

These files remain active and canonical, but they are not part of the primary
navigation set.

1. [runbooks/public-release-checklist.md](runbooks/public-release-checklist.md)
2. [runbooks/storefront-share-kit.md](runbooks/storefront-share-kit.md)
3. [runbooks/github-storefront-manual-steps.md](runbooks/github-storefront-manual-steps.md)
4. [releases/v0.1.0-alpha.3.md](releases/v0.1.0-alpha.3.md)
5. [releases/first-public-release-draft.md](releases/first-public-release-draft.md)
6. [assets/storefront/demo-status.md](assets/storefront/demo-status.md)
7. [assets/storefront/benchmark-methodology.md](assets/storefront/benchmark-methodology.md)
8. [architecture/ecosystem-and-builder-surfaces-v1.md](architecture/ecosystem-and-builder-surfaces-v1.md)
9. [runbooks/render-hosted-operator-pilot.md](runbooks/render-hosted-operator-pilot.md)
10. [runbooks/write-mcp-queue-pilot.md](runbooks/write-mcp-queue-pilot.md)
11. [robots.txt](robots.txt)
12. [sitemap.xml](sitemap.xml)

## What Each File Is For

- `docs/index.html`: search-facing landing source for the live GitHub Pages/docs surface; keep it acting like a route page, not a wall of repeated subpage summaries
- `../DISTRIBUTION.md`: canonical repo-side distribution contract for what ships now, what stays starter-only, what remains internal-only, and what is explicitly deferred
- `docs/architecture/runtime-topology.md`: system layout and major boundaries
- `docs/specs/00_SPEC.md`: active product and contract baseline
- `docs/runbooks/onboarding-30min.md`: shortest contributor handoff path
- `docs/runbooks/space-governance.md`: disk-space audit, gating, and cleanup workflow
- `docs/architecture/mcp-and-operator-copilot-v1.md`: Prompt 4 baseline for the read-only MCP node and run-scoped operator copilot
- `docs/runbooks/public-release-checklist.md`: user-facing GitHub release preparation checklist
- `docs/runbooks/storefront-share-kit.md`: tracked punchline and sharing kit for storefront work
- `docs/runbooks/github-storefront-manual-steps.md`: exact GitHub UI values and manual storefront steps
- `docs/releases/v0.1.0-alpha.3.md`: repo-side draft source for the current published prerelease notes
- `docs/releases/first-public-release-draft.md`: repo-side draft source for the first public GitHub Release
- `docs/assets/storefront/demo-status.md`: status ledger for tracked public demo and proof assets
- `docs/assets/storefront/proof-pack-index.json`: machine-readable public proof bundle index for proven and showcase storefront slices
- `docs/assets/storefront/live-capture-requirements.json`: machine-readable contract for the remaining healthy GIF and English-first public capture deliverables
- `docs/assets/storefront/benchmark-methodology.md`: public benchmark evidence contract and wording boundary
- `docs/architecture/ecosystem-and-builder-surfaces-v1.md`: ecosystem binding, first-run distribution loop, and current builder/client entry points
- `docs/runbooks/render-hosted-operator-pilot.md`: repo-side Git-backed hosted operator blueprint for future guarded Render pilots; use it to stage env/health/rollback/support/security requirements without implying a live hosted service
- `docs/runbooks/write-mcp-queue-pilot.md`: repo-owned operator runbook for the smallest honest queue-only write-MCP pilot; keep it preview-first, default-off, and below the public read-only MCP contract
- `docs/builders/index.html`: public builder quickstart hub for current client/contract/shared entrypoints, including the repo-owned control-plane starter path and its runnable local example
- `docs/ecosystem/index.html`: public ecosystem positioning page for Codex / Claude Code / MCP plus adjacent comparison layers
- `docs/compatibility/index.html`: public adoption matrix for choosing between Codex / Claude Code / OpenClaw / skills / builders / proof-first onboarding paths
- `docs/distribution/index.html`: public mirror of the root `DISTRIBUTION.md` contract for shipped, starter-only or bundle-compatible, publish-ready but deferred, workspace-only, and deferred public surfaces, including release truth and package boundaries
- `docs/agent-starters/index.html`: public copy-paste starter kits for Codex / Claude Code / OpenClaw teams that want tracked MCP config snippets plus the shortest repo-owned skills/bootstrap entrypoints
- `docs/use-cases/index.html`: public first-run, proof, and share-ready asset guide
- `docs/ai-surfaces/index.html`: public AI operator / read-only MCP / API entrypoint map for truthful discoverability
- `docs/mcp/index.html`: public read-only MCP quickstart page for truthful protocol discovery
- `configs/mcp_public_manifest.json`: machine-readable MCP distribution artifact for the shipped read-only stdio surface
- `docs/api/index.html`: public API / contract quickstart page for OpenAPI, frontend client, and contract-facing types
- `docs/integrations/index.html`: truthful coding-agent integration map for Codex / Claude Code / OpenClaw, including the no-fake-plugin boundary plus a lighter proof-first pointer back to `use-cases/`
- `docs/skills/index.html`: repo-owned skills quickstart for teams adopting CortexPilot playbooks with coding agents, including a minimal vendored skill-pack layout and the same lighter proof-first pointer instead of a second chooser grid
- `apps/dashboard/README.md`: dashboard-owned module note for operator-surface wording, staged UI-audit build behavior, and control-plane/runtime-capability presentation changes
- `apps/desktop/README.md`: desktop-owned module note for operator-surface locale/status hardening when desktop wording contracts change
- `policies/agent_registry.json`: machine SSOT for role-contract defaults such as purpose, prompt ref, MCP bundle ref, downstream-role expectations, and fail-closed posture
- `policies/skills_bundle_registry.json`: repo-owned authority surface for named skills bundles used by qualifying role contracts
- `policies/role_config_registry.json`: repo-owned mutable defaults surface for role configuration preview/apply flows; changes here affect future compiled role defaults, not the execution authority of already-issued task contracts
- `configs/env_direct_read_allowlist.json`: machine allowlist for governed backend direct env reads; update this alongside docs when a role/runtime helper legitimately reads env-backed model metadata
- `docs/api/openapi.cortexpilot.json`: canonical frontend contract extension that now carries Prompt 8 run/workflow route bindings plus Prompt 9 agents/contracts catalog bindings and generated read-model metadata for `RoleBindingReadModel` / `WorkflowCaseReadModel`
- `scripts/generate_frontend_contracts.py`: repo-owned generator that now emits Prompt 8 read-model types plus Prompt 9 agents/contracts catalog routes into `@cortexpilot/frontend-api-contract`
- `schemas/role_config_registry.v1.json`: schema-first contract for the repo-owned role configuration overlay used by Prompt 10 role-default preview/apply surfaces
- `packages/frontend-api-contract/generated/index.d.ts`: generated TypeScript contract surface for frontend-safe run/workflow routes and read-model types; avoid hand-maintaining parallel overlays when this file changes
- `packages/frontend-api-contract/docs/README.md`: human-readable contract package guide that now sits between the public API/builder quickstarts and the raw generated contract files
- `scripts/check_clean_room_recovery.sh`: clean-room bootstrap/verification path that now reinstalls package-local frontend-api-client deps before its node smoke bundle and runs the repo-owned workspace-module cleanup before the broader runtime delete sweep; that cleanup path can quarantine stubborn dashboard module residue before deletion when recursive removal alone is not enough
- `scripts/install_dashboard_deps.sh`: dashboard clean-room install gate that now proves `jsdom` itself can load, so quick-lane success does not depend on a specific transitive dependency layout such as `data-urls`
- `scripts/check_public_sensitive_surface.py`: fail-closed tracked-surface gate for maintainer-local paths, raw token-like literals, direct PII markers, and forbidden tracked runtime files; the gate is wired into repo hygiene and a dedicated pre-commit hook
- `scripts/check_workflow_static_security.sh`: repo-owned GitHub Actions security wrapper; it resolves the pinned `actionlint` + `zizmor` binaries through `scripts/lib/release_tool_helpers.sh` and fails on actionlint errors plus medium/high zizmor findings
- `scripts/check_trivy_repo_scan.sh`: repo-owned Trivy filesystem/dependency scan for the tracked repository surface and lockfiles
- `scripts/check_secret_scan_closeout.sh`: closeout-oriented secret scan wrapper; it can run the canonical history scan on the current tree or repeat it from a fresh clone
- `scripts/lib/release_tool_helpers.sh`: pinned release-tool bootstrap for `actionlint`, `zizmor`, `trivy`, `gitleaks`, and `trufflehog`
- `.github/dependency-review-config.yml`: repo-owned configuration for the official GitHub Dependency Review action on pull requests
- `.pre-commit-config.yaml`: host-compatible hook inventory; repo-owned
  `scripts/*.py` hooks should run through `bash scripts/run_governance_py.sh`
  (or an equivalent `python3 -B` path) so clean hook passes do not leave
  repo-local `__pycache__` residue behind
- `apps/orchestrator/src/cortexpilot_orch/api/main_pm_intake_helpers.py`: PM-facing helper surface that now returns a contract-derived `role_binding_summary`, and the same read model now persists into run manifests for stable post-run inspection without becoming execution authority
- `schemas/execution_plan_report.v1.json` / `schemas/run_manifest.v1.json`: schema-owned runtime capability summaries (`lane`, `compat_api_mode`, `provider_status`, `tool_execution`) that keep preview/manifests honest about chat-compatible vs fail-closed tool posture
- `apps/orchestrator/src/cortexpilot_orch/api/main_runs_handlers.py`: run-detail helper surface that now returns a stable `role_binding_read_model` derived from persisted contract truth for read-only inspection
- `apps/orchestrator/src/cortexpilot_orch/api/main_state_store_helpers.py`: workflow aggregation helper that now projects `workflow_case_read_model` from the latest linked run's persisted binding summary for control-plane/workflow reads
- `apps/orchestrator/src/cortexpilot_orch/api/main_run_views_helpers.py`: registry-backed agent inventory now also publishes a read-only role catalog, while contract artifact listing emits normalized bundle/runtime inspector rows for Prompt 9 operator pages

## Public CI Contract

- active CI layers are `pre-commit`, `pre-push`, `hosted`, `nightly`, and `manual`
- no sixth CI/profile/workflow layer exists in this repository
- internal UI policy helpers may still say `pr`; that means the hosted PR
  subprofile, not a sixth top-level CI layer
- default public CI is hosted-first and GitHub-hosted
- fork PRs stay on low-privilege checks only and must not touch secrets or
  live/external systems
- maintainer-owned PRs still stay on GitHub-hosted policy/core lanes
- protected sensitive lanes (`ui-truth`, `resilience-and-e2e`,
  `release-evidence`) are manual `workflow_dispatch` paths gated by the
  `owner-approved-sensitive` environment
- `configs/ci_governance_policy.json` is the machine SSOT for repo-side CI
  routing; `configs/github_control_plane_policy.json` is the live GitHub
  control-plane contract
- repo-first pushes may hand GitHub Actions the all-zero base SHA; the
  repo-owned doc-drift/doc-sync hooks now skip `ci-diff` comparison for that
  bootstrap-only case so Quick Feedback does not fail before the repository has
  a real baseline commit
- `GitHub Control Plane` should prefer the repo secret `GH_ADMIN_TOKEN` when
  it needs to prove admin-only repository APIs, because the default workflow
  token cannot read Actions permissions, branch protection, or
  vulnerability-alert endpoints on the live control plane
- protected upstream/live-smoke receipts remain outside hosted-first base
  routes: `trusted_pr`, `untrusted_pr`, and `push_main` now treat those checks
  as route-exempt, while authoritative provider/live closeout proof stays in
  protected/manual lanes
- the hosted-first closeout builder follows the same contract: when `push_main`
  is route-exempt for upstream/live smoke, `upstream_report`,
  `upstream_same_run_report`, and `current_run_consistency` stay advisory
  instead of blocking base CI

## Documentation Rules

- keep docs English-first
- keep docs public-facing and minimal
- treat `configs/docs_nav_registry.json` as the machine docs inventory SSOT
- keep `docs/README.md` as a summary, not a second handwritten source of truth
- treat `configs/github_control_plane_policy.json` as the machine SSOT for
  required check names, and reuse the root `README.md` summary instead of
  repeating the literal list here
- state public support boundaries explicitly when a module is intentionally out of scope
- current desktop public support boundary is macOS-only; Linux/BSD desktop
  evidence is manual or historical, unsupported, and not part of the default
  closeout contract
- move runtime evidence, generated output, and internal scratch material out of
  tracked docs
- when dashboard dependency lock refreshes land, treat the dashboard lockfile
  and the root workspace lockfiles as one documented maintenance change set
- the current security-only dashboard/root lock refresh keeps
  `lodash-es@4.18.1` pinned through the repo-owned override layer so the
  tracked `lighthouse@13.0.3` transitive path does not drift back to the
  vulnerable `lodash-es@4.17.23` resolution on either maintained lock surface,
  which keeps the current security repair truthful without widening into a
  general Lighthouse upgrade
- when dashboard or desktop dependency maintenance changes the shipped build
  contract, sync the root docs entrypoints in the same patch; the current
  examples are the optional dashboard `depcheck` removal from the maintained
  lock surface and the desktop Vite 8 / Rolldown function-based chunking note
- when a single closeout patch spans both dashboard and desktop packaging, pair
  these docs updates with the root AI entrypoints (`AGENTS.md` / `CLAUDE.md`)
  so doc-sync gates can follow the decision chain without guessing
- when dashboard/operator labels or intake/probe contracts move, keep the
  module READMEs and root entrypoints aligned in the same patch; the current
  examples are the English-first Command Tower regression surface and the
  intake/probe response fields that now omit absent `task_template` data
- when security-scan or fixture-hygiene work changes tracked test literals or
  wrapper scripts, sync this summary plus the root/module entrypoints in the
  same patch; current examples include generic workspace roots instead of
  maintainer-local paths, runtime-built token-like fixtures, and BSD-safe
  temp-file naming in `scripts/security_scan.sh`
- when CI maintenance changes the runtime report namespace or the Python
  dependency audit contract, sync this summary and the root entrypoints in the
  same patch; the current examples are `.runtime-cache/test_output/ci/` and
  `configs/pip_audit_ignored_advisories.json`, plus the dashboard and desktop
  ENOSPC recovery knobs plus the Docker daemon precheck retry knobs registered
  in `configs/env.registry.json`; current CI contract changes also include the
  upstream receipt refresh fallback to `scripts/verify_upstream_slices.py --mode smoke`
  and the strict hosted-first live-provider rule that allows
  process env first and `~/.codex/config.toml` second while keeping dotenv and
  shell-export fallbacks disabled on mainline
