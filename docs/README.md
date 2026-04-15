# Documentation

This repository keeps its public documentation intentionally small.

The public route pages now speak as **OpenVibeCoding**, the command tower for
AI engineering across the repo's public surfaces.

The product spine stays stable across the docs entrypoints:

- **Command Tower** for live operator visibility
- **Workflow Cases** for the case-level operating record
- **Proof & Replay** for evidence, compare, and replay review

`docs/index.html` is the current tracked GitHub Pages landing source for the
OpenVibeCoding front door. `docs/README.md` remains the repo-side
documentation summary for contributors and maintainers who still need the
runtime and repository inventory.

`configs/docs_nav_registry.json` is the machine source of truth for the **active
public docs inventory only**. Treat files outside that active inventory as
maintainer-only reference or archive material, even if they still live under
`docs/` for repo history and contributor access.

Daily local verification lives in the root [README](../README.md). Treat this
file as the docs inventory map, not as a second CI manual.

## Public Lane Order

- `pure_mcp` is the primary public machine-readable lane.
- `public-skills/openvibecoding-adoption-router/` is the secondary public adoption lane.
- `examples/coding-agents/` and `examples/coding-agents/plugin-bundles/` are
  starter/example lanes only; do not treat them as the canonical public root.

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

## Internal Design Sources

These files are repo-owned internal design truth, not public docs navigation
pages.

- `design-system/MASTER.md`: canonical visual/design constitution for the
  command-tower product language across web and desktop
- `design-system/pages/*.md`: page-level overrides for the key control-plane
  surfaces
- `.stitch/DESIGN.md`: Stitch-facing design summary for the same product
  language
- `.stitch/designs/*.prompt.md`: enhanced prompt pack for repo-owned Stitch
  fallback until authenticated HTML/screenshot exports exist

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

## Supplemental Registered Docs

These are the only active public supplemental surfaces.

1. [robots.txt](robots.txt)
2. [sitemap.xml](sitemap.xml)

## Maintainer References Outside The Active Public Inventory

Some repo-owned materials still live under `docs/` for contributor setup,
historical release archaeology, implementation truth, or archival proof, but
they are **not** part of the active public docs inventory and must not be
treated as front-door navigation. This includes:

- architecture notes and topology references
- engineering/specification baselines
- maintainer runbooks and future pilot blueprints
- historical release-draft sources and release-side proof ledgers
- storefront methodology/status ledgers that remain useful as archive material

Heavy reference docs, release archaeology, proof ledgers, governance maps, and
preview runbooks still live in the repository for maintainers. Treat them as
implementation/archive reference when needed, not as part of the minimal
public story.

## What Each Active Public File Is For

- `docs/index.html`: search-facing landing source for the live GitHub Pages surface; keep it acting like a route page, not a wall of repeated subpage summaries
- `docs/ecosystem/index.html`: public ecosystem positioning page for Codex / Claude Code / MCP plus adjacent comparison layers
- `docs/compatibility/index.html`: public adoption matrix for choosing between Codex / Claude Code / OpenClaw / skills / builders / proof-first onboarding paths
- `docs/distribution/index.html`: public mirror of the root `DISTRIBUTION.md` contract for shipped, starter-only, deferred, and workspace-only surfaces
- `docs/agent-starters/index.html`: public copy-paste starter kits for Codex / Claude Code / OpenClaw teams that want the shortest repo-owned bootstrap path
- `docs/use-cases/index.html`: public first-run, proof, and share-ready asset guide
- `docs/ai-surfaces/index.html`: public AI / read-only MCP / API entrypoint map for truthful discoverability
- `docs/mcp/index.html`: public read-only MCP quickstart page for truthful protocol discovery
- `docs/api/index.html`: public API / contract quickstart page for OpenAPI, thin client helpers, and contract-facing types
- `docs/builders/index.html`: public builder quickstart hub for current client/contract/shared entrypoints
- `docs/integrations/index.html`: truthful coding-agent integration map for Codex / Claude Code / OpenClaw without fake plugin claims
- `docs/skills/index.html`: repo-owned skills quickstart for teams adopting OpenVibeCoding playbooks with coding agents
- `docs/robots.txt` / `docs/sitemap.xml`: crawler-facing discovery surfaces
- `configs/mcp_public_manifest.json`: machine-readable MCP distribution artifact for the shipped read-only stdio surface
- `docs/api/openapi.openvibecoding.json`: canonical frontend contract extension that now carries Prompt 8 run/workflow route bindings plus Prompt 9 agents/contracts catalog bindings and generated read-model metadata for `RoleBindingReadModel` / `WorkflowCaseReadModel`

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
  ENOSPC recovery knobs, the minimum-headroom fail-fast thresholds, and the
  Docker daemon precheck retry knobs registered in `configs/env.registry.json`,
  together with the bounded transient npm registry socket-timeout retries inside
  `scripts/install_dashboard_deps.sh` / `scripts/install_desktop_deps.sh`;
  current CI contract changes also include the
  upstream receipt refresh fallback to `scripts/verify_upstream_slices.py --mode smoke`
  and the strict hosted-first live-provider rule that allows
  process env first and `~/.codex/config.toml` second while keeping dotenv and
  shell-export fallbacks disabled on mainline
