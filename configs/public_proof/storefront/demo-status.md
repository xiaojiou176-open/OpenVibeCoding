# Demo Asset Status

This file tracks the public demo surfaces that are already present versus the
ones that still need a real capture pass.

## Present Today: Explainers And Supporting Assets

- `hero-command-tower.svg`: public hero image
- `command-tower-showcase-card.svg`: README and storefront showcase card
- `first-loop-storyboard.svg`: shareable storyboard of the PM -> Command Tower -> Runs loop
- `first-loop-storyboard.png`: static storyboard export
- `first-loop-storyboard.gif`: storyboard animation export
- `dashboard-home-live-1440x900.png`: healthy English-first dashboard home screenshot captured from a clean local runtime root
- `dashboard-command-tower-live-1440x900.png`: healthy English-first Command Tower session screenshot captured from the same verified path
- `dashboard-runs-live-1440x900.png`: healthy English-first Runs / Proof & Replay screenshot captured from the same verified path
- `dashboard-live-healthy-loop.gif`: healthy backend-backed multi-page dashboard GIF captured from the same verified path
- `desktop-shell-live-1440x900.png`: real desktop preview screenshot captured from the app snapshot pipeline
- `social-preview-source.svg`: editable social card source
- `social-preview-1280x640.png`: upload-ready social card candidate
- `configs/public_proof/releases_assets/news-digest-healthy-proof-2026-03-27.md`: repo-tracked healthy `news_digest` proof summary
- `docs/releases/assets/news-digest-healthy-proof-gemini-2026-03-27.png`: successful Gemini proof screenshot
- `docs/releases/assets/news-digest-healthy-proof-grok-2026-03-27.png`: successful Grok proof screenshot
- `configs/public_proof/releases_assets/news-digest-benchmark-summary-2026-03-27.md`: first tracked public `news_digest` baseline summary
- `configs/public_proof/releases_assets/news-digest-proof-pack-2026-03-27.json`: machine-readable proof-pack directory for the March 2026 public trust bundle checkpoint
- `configs/public_proof/releases_assets/news-digest-workflow-case-recap-2026-03-27.md`: share-ready Workflow Case recap for the March 2026 first public baseline checkpoint
- `configs/public_proof/releases_assets/page-brief-healthy-proof-2026-04-15.md`: tracked browser-backed `page_brief` proof summary
- `configs/public_proof/releases_assets/page-brief-benchmark-summary-2026-04-15.md`: tracked browser-backed `page_brief` bundle baseline summary
- `configs/public_proof/releases_assets/page-brief-proof-pack-2026-04-15.json`: machine-readable proof-pack directory for the April 2026 browser-backed public proof checkpoint
- `configs/public_proof/releases_assets/page-brief-workflow-case-recap-2026-04-15.md`: share-ready Workflow Case recap for the tracked `page_brief` proof bundle
- `configs/public_proof/releases_assets/topic-brief-healthy-proof-2026-04-15.md`: tracked search-backed `topic_brief` proof summary
- `configs/public_proof/releases_assets/topic-brief-benchmark-summary-2026-04-15.md`: tracked search-backed `topic_brief` bundle baseline summary
- `configs/public_proof/releases_assets/topic-brief-proof-pack-2026-04-15.json`: machine-readable proof-pack directory for the April 2026 search-backed public proof checkpoint
- `configs/public_proof/releases_assets/topic-brief-workflow-case-recap-2026-04-15.md`: share-ready Workflow Case recap for the tracked `topic_brief` proof bundle

## Current Proof Ledger

| Proof class | Current status | Notes |
| --- | --- | --- |
| Storyboard explainer assets | present | useful for explaining the loop, not proving runtime health |
| Healthy backend-backed dashboard capture set | present | tracked English-first home, Command Tower session, and Runs captures from a clean local runtime root |
| Healthy backend-backed live GIF | present | tracked multi-page walkthrough of the official first public happy path |
| Desktop preview capture | present | shows the shell surface only |
| Healthy backend-backed `news_digest` public proof set | present | tracked proof summary: `configs/public_proof/releases_assets/news-digest-healthy-proof-2026-03-27.md` |
| Public benchmark artifact from a real tracked run | present | first tracked single-run baseline: `configs/public_proof/releases_assets/news-digest-benchmark-summary-2026-03-27.md` |
| Share-ready Workflow Case recap asset | present | tracked recap asset: `configs/public_proof/releases_assets/news-digest-workflow-case-recap-2026-03-27.md` |
| Tracked search-backed `topic_brief` public proof bundle | present | tracked proof pack: `configs/public_proof/releases_assets/topic-brief-proof-pack-2026-04-15.json` |
| Tracked browser-backed `page_brief` public proof bundle | present | tracked proof pack: `configs/public_proof/releases_assets/page-brief-proof-pack-2026-04-15.json` |
| Published GitHub Release page/card | present | live release `v0.1.0-alpha.3` is the latest published prerelease baseline, but the repo has moved ahead and the tag now represents a lagging published snapshot |

## Still Missing

- a broader multi-round public benchmark artifact beyond the current single-run
  baseline summary
- a live GitHub social preview upload

## Why This File Exists

It prevents “we already have assets” from drifting into fake maturity. A source
file, a storyboard, a storyboard animation, and a production-ready live capture
are different things.

The public storytelling shorthand is now:

- **first proven workflow** = `news_digest`
- **public proof pack** = healthy proof summary + benchmark summary + Workflow Case recap + demo-status ledger
- **tracked search-backed public proof bundle** = `topic_brief`
- **tracked browser-backed public proof bundle** = `page_brief`
- **showcase paths** = none on the current public task-template surface

## Truth Boundary

- `dashboard-home-live-1440x900.png`, `dashboard-command-tower-live-1440x900.png`, `dashboard-runs-live-1440x900.png`, and `dashboard-live-healthy-loop.gif` are real healthy captures from the dashboard server backed by the clean local runtime root `.runtime-cache/storefront-final-capture-english`.
- these tracked captures are safe repo-side proof of a healthy local first public path, not proof of hosted production scale, stable multi-run release averages, or live GitHub publication state.
- `dashboard-live-degraded-loop.gif` remains a historical degraded capture and should stay labeled as degraded if it is referenced at all.
- `desktop-shell-live-1440x900.png` is a real screenshot from the desktop snapshot pipeline.
- `social-preview-1280x640.png` is a repo-tracked upload candidate for the GitHub social preview setting, not proof that the live GitHub setting has already been applied.
- the first public release draft remains archived in the maintainer-only internal docs bundle that fed the published release notes.
- the live GitHub Release page currently represents the latest published public
  baseline, not the current `main` snapshot; keep explicit lag wording in repo
  docs until the next tag is cut.
- `configs/public_proof/releases_assets/news-digest-healthy-proof-2026-03-27.md` and the two
  copied screenshots are repo-tracked evidence from a successful local run,
  not proof that the live GitHub Release page has already been published.
- `configs/public_proof/releases_assets/news-digest-benchmark-summary-2026-03-27.md` is a real
  single-run baseline summary, not a broad multi-round benchmark campaign.
- `configs/public_proof/releases_assets/page-brief-proof-pack-2026-04-15.json` and its
  primary assets are repo-tracked proof packaging for the browser-backed
  `page_brief` path, not proof that `page_brief` replaced `news_digest` as the
  official first public baseline.
- `configs/public_proof/releases_assets/topic-brief-proof-pack-2026-04-15.json` and its
  primary assets are repo-tracked proof packaging for the search-backed
  `topic_brief` path, not proof that `topic_brief` replaced `news_digest` as
  the official first public baseline.
- the earlier benchmark-route and healthy-proof-route blocker receipts now live
  in the maintainer-only internal docs bundle, not on the default public docs
  surface.
- `https://xiaojiou176-open.github.io/OpenVibeCoding/` is now the live GitHub
  Pages site backed by `main` / `/docs`.
- None of these captures should be described as proof of live hosted readiness, live GitHub publication state, or broad production-scale stability.
