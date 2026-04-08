# CortexPilot v0.1.0-alpha.1 - first public release baseline

This file is the tracked source for the first public GitHub Release notes.

This release is the first public storefront baseline for CortexPilot.

Treat it as the first published baseline, not as a claim that current `main`
and the latest public release are always the same snapshot.

Historical note: the newer current release note source lives at
`docs/releases/v0.1.0-alpha.3.md`.

## Why this release matters

CortexPilot is not just an agent demo repository. It is a command tower for
Codex and Claude Code workflows with evidence, replay, Workflow Cases, and
operator visibility.

This release makes that story much clearer on the public surface.

## What changed

- rewrote the root README around the PM -> Command Tower -> Runs loop
- added tracked storefront assets for hero art and social preview
- added a Pages-ready landing source with title and description metadata
- split the first-success quickstart from contributor onboarding
- added release and storefront runbooks for future maintenance
- clarified the repo-side proof contract for the first public release bundle
- added a repo-local read-only MCP server entry for control-plane reads
- added an explain-only operator brief on dashboard Run Detail and Run Compare
- added dedicated public Pages entrypoints for ecosystem, builder, use-case, and AI/MCP/API discovery

## What to look at first

1. `README.md`
2. `docs/index.html`
3. `docs/runbooks/public-release-checklist.md`
4. `docs/runbooks/storefront-share-kit.md`

## Official First Public Path

The first public release contract treats `news_digest` as the only official
happy-path baseline for proof-oriented copy and future benchmark publication.

## Present Repo-Side Proof

- release notes source exists in this file
- README and storefront docs exist and are aligned to the current public story
- tracked explainer assets and limited-scope captures exist in
  `docs/assets/storefront/`
- a tracked healthy `news_digest` proof summary now exists in
  `docs/releases/assets/news-digest-healthy-proof-2026-03-27.md`
- a tracked single-run public baseline now exists in
  `docs/releases/assets/news-digest-benchmark-summary-2026-03-27.md`
- repo-side Prompt 4 now also includes read-only MCP and operator-brief docs in
  `docs/architecture/mcp-and-operator-copilot-v1.md`

## Live Publication Checks Still Require Fresh Verification

- confirm the GitHub social preview in repository settings before calling the
  release live-public complete
- verify the current GitHub Release page at
  `https://github.com/xiaojiou176-open/CortexPilot-public/releases/tag/v0.1.0-alpha.1`
  still matches this repo-side draft instead of assuming it does
- verify the live GitHub Pages site at
  `https://xiaojiou176-open.github.io/CortexPilot-public/` is serving the
  current landing copy instead of inferring that from git alone
- verify whether GitHub Discussions, release visibility, and subscriber flows
  are currently enabled in the live repository settings
- keep the “no broader multi-round benchmark artifact is published yet” note as
  a release-time check until a fresh live/public proof bundle says otherwise

## Verification

```bash
CORTEXPILOT_HOST_COMPAT=1 bash scripts/test_quick.sh --no-related
TMPDIR=/path/to/tmpdir bash scripts/check_repo_hygiene.sh
```

## Release Note Guardrails

- do not describe storyboard assets as healthy proof
- do not describe degraded local captures as healthy end-to-end evidence
- do not quote benchmark numbers outside the tracked artifact or without keeping
  the current single-run scope explicit
- do not turn last-known live repository settings into repo-side current truth;
  live/public checks must be re-verified at release time
