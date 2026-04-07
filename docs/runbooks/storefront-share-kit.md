# Storefront Share Kit

Use this file as the minimum public sharing kit for CortexPilot.

For the first public release window, `news_digest` is the only official
happy-path baseline for proof-oriented copy. Other slices may exist in product
surfaces, but they should not be presented as equally release-proven yet.

## Punchline

Command Tower for Codex and Claude Code workflows with Workflow Cases, proof,
replay, read-only MCP access, and explainable operator guidance.

## 10-Second Story

1. Start a task from PM.
2. Watch it move through Command Tower.
3. Open the Workflow Case and inspect proof, replay, or the operator brief.

## Current Public Framing

- **First proven workflow**: `news_digest`
- **Public proof pack**: healthy proof summary + benchmark summary + Workflow Case recap + demo-status ledger
- **Showcase expansions**: `topic_brief` and `page_brief` until they earn their own healthy proof bundles

## Current Tracked Assets

- `docs/assets/storefront/hero-command-tower.svg`
- `docs/assets/storefront/first-loop-storyboard.svg`
- `docs/assets/storefront/first-loop-storyboard.gif`
- `docs/assets/storefront/dashboard-home-live-1440x900.png`
- `docs/assets/storefront/dashboard-command-tower-live-1440x900.png`
- `docs/assets/storefront/dashboard-runs-live-1440x900.png`
- `docs/assets/storefront/dashboard-live-healthy-loop.gif`
- `docs/assets/storefront/dashboard-live-degraded-loop.gif`
- `docs/assets/storefront/desktop-shell-live-1440x900.png`
- `docs/assets/storefront/social-preview-source.svg`
- `docs/assets/storefront/social-preview-1280x640.png`
- `docs/assets/storefront/demo-status.md`
- `docs/releases/assets/news-digest-healthy-proof-2026-03-27.md`
- `docs/releases/assets/news-digest-healthy-proof-gemini-2026-03-27.png`
- `docs/releases/assets/news-digest-healthy-proof-grok-2026-03-27.png`
- `docs/releases/assets/news-digest-benchmark-summary-2026-03-27.md`
- `docs/releases/assets/news-digest-proof-pack-2026-03-27.json`
- `docs/releases/assets/news-digest-workflow-case-recap-2026-03-27.md`

## Proof Status By Asset Type

| Asset type | Current status | Safe public use |
| --- | --- | --- |
| Hero and storyboard art | tracked | use as explanation and storytelling |
| Local degraded dashboard captures | tracked historical fallback | use only with degraded/local wording |
| Desktop snapshot preview | tracked | use as a UI preview, not as end-to-end proof |
| Healthy backend-backed dashboard capture set | present | safe to reference as repo-tracked proof, not as proof of live GitHub publication |
| Healthy backend-backed live GIF | present | safe to reference as repo-tracked proof of the local first public happy path |
| Public benchmark artifact | present | safe to quote as a single-run baseline only |
| Workflow Case recap asset | present | safe to reuse as the strongest public recap for the official first-run path |
| GitHub Release card | present | safe to reference the live release page and the tracked draft together |

## Current Gaps

- no broader multi-round public benchmark figure yet
- no live GitHub social preview upload yet

## Safe Post Angles

- why governed runs matter after “the agent replied”
- how evidence + replay changes debugging and review
- how read-only MCP access turns CortexPilot into a node other tools can inspect
- how the operator brief explains failures without pretending to execute recovery
- why CortexPilot is a control plane, not a generic agent demo
- anchor first-look copy on the `news_digest` path when referring to a public
  first run
- use the storyboard GIF only as a process explainer, not as proof of live runtime behavior
- describe `dashboard-home-live-1440x900.png`, `dashboard-command-tower-live-1440x900.png`, and `dashboard-runs-live-1440x900.png` as healthy English-first local captures from the same verified path
- describe `dashboard-live-healthy-loop.gif` as the healthy backend-backed local walkthrough for the official first public baseline
- describe `dashboard-live-degraded-loop.gif` as a historical degraded dashboard capture, not the current public proof default
- quote the current benchmark artifact only as a single-run `news_digest`
  baseline until a broader benchmark summary replaces it
- if mentioning the first release, link the live GitHub Release page first and
  treat `docs/releases/first-public-release-draft.md` as the repo-side source
  that fed those published notes
