# Storefront Assets

Tracked assets in this directory exist for public README, release, landing-page,
and social-preview use.

## Current Files

- `hero-command-tower.svg`: README and landing-page hero asset
- `first-loop-storyboard.svg`: shareable storyboard for the PM -> Command Tower -> Runs story
- `first-loop-storyboard.png`: exportable static storyboard preview
- `first-loop-storyboard.gif`: tracked storyboard animation (not a live product capture)
- `openvibecoding-command-tower-teaser-poster.png`: poster frame for the short promo teaser
- `openvibecoding-command-tower-teaser.mp4`: tracked short promo teaser for README / Pages front door
- `openvibecoding-command-tower-teaser.vtt`: tracked English captions for the teaser
- `dashboard-command-tower-current-1440x900.png`: tracked current-brand Command Tower read-back screenshot (may show explicit degraded/live-state messaging)
- `dashboard-home-live-1440x900.png`: tracked healthy English-first dashboard home screenshot
- `dashboard-command-tower-live-1440x900.png`: tracked healthy English-first Command Tower session screenshot
- `dashboard-runs-live-1440x900.png`: tracked healthy English-first Runs / Proof & Replay screenshot
- `dashboard-live-healthy-loop.gif`: tracked healthy backend-backed dashboard GIF
- `dashboard-live-degraded-loop.gif`: historical degraded dashboard GIF retained as a truth-boundary reference
- `desktop-shell-live-1440x900.png`: tracked real screenshot from the desktop snapshot pipeline
- `social-preview-source.svg`: source artwork for a GitHub social preview export
- `social-preview-1280x640.png`: exported GitHub social preview candidate
- `demo-status.md`: explicit status ledger for real demo/benchmark asset closure
- `proof-pack-index.json`: machine-readable public proof bundle index
- `live-capture-requirements.json`: machine-readable contract for the remaining healthy public capture deliverables

## Rules

- keep filenames descriptive and stable
- keep the public story aligned with `PM -> Command Tower -> Runs / Evidence`
- do not point README or docs at `.runtime-cache/` image artifacts
- keep `social-preview-source.svg` as the editable source and `social-preview-1280x640.png` as the upload candidate
- keep `tooling/remotion-promo/` as the repo-owned editable source for the teaser poster / MP4 / captions set
- keep `scripts/render_storefront_teaser.sh` as the reproducible front door for rebuilding the teaser outputs
- treat `first-loop-storyboard.gif` as a storyboard animation, not as a real live-product recording
- treat `openvibecoding-command-tower-teaser.mp4` as a public-facing promo asset, not as proof of hosted production scale or broader workflow coverage
- treat `dashboard-command-tower-current-1440x900.png` as a current operator-shell read-back, not as a substitute for the healthy proof capture contract
- label degraded local screenshots honestly when backend data is unavailable
- label degraded local GIF captures honestly when backend data is unavailable
- label healthy local dashboard captures as repo-side local proof, not as proof of hosted production scale or live GitHub publication
- treat `proof-pack-index.json` as the public proof bundle SSOT for repo-tracked proof surfaces
- treat `live-capture-requirements.json` as the SSOT for the remaining healthy GIF / English-first capture deliverables
- regenerate tracked exports on macOS with `bash scripts/export_storefront_assets.sh` (supports `inkscape` or `rsvg-convert` as optional SVG fallbacks)
