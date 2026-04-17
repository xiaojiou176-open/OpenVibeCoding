# news_digest Workflow Case Recap - 2026-03-27

This file is the strongest repo-tracked public recap asset for the official
`news_digest` first-run path.

It sits between the raw proof bundle and the public landing pages:

- use the proof summary when you need the full backend-backed receipt
- use the benchmark summary when you need the single-run baseline numbers
- use this recap when you need one share-ready story that explains what the
  Workflow Case proves and why it matters

This is still repo-side proof only. It is not proof that a live hosted product,
live GitHub social preview, or broader release benchmark has already shipped.

## The Case In One Paragraph

A PM asks OpenVibeCoding for a `news_digest` on `Seattle AI` over the last `24h`
from `theverge.com`. The run moves through the normal command-tower path,
records one Workflow Case, produces a successful digest, and leaves behind a
proof bundle that another person can inspect without re-running the whole
operator flow.

## Public Snapshot

- task template: `news_digest`
- topic: `Seattle AI`
- time range: `24h`
- source allowlist: `theverge.com`
- max results: `3`
- run id: `run_20260327_102651_8274cd4519324674a3ddd67506febd83`
- commit: `03b8bf9`
- generated at: `2026-03-27T10:27:20.898375+00:00`
- providers observed in the tracked successful run:
  - `gemini_web`
  - `grok_web`

## Why This Case Matters

This case is the current public baseline because it shows the whole point of
OpenVibeCoding in one small, honest loop:

1. a workflow starts from a bounded PM request
2. Command Tower and the Workflow Case keep the run reviewable
3. proof and replay stay available after the run finishes
4. the result can be shared as a recap asset instead of forcing every reviewer
   back into the full operator UI

That makes `news_digest` the easiest truthful answer to “What does OpenVibeCoding
actually do today?”

## What You Can Inspect Today

- proof summary:
  - `configs/public_proof/releases_assets/news-digest-healthy-proof-2026-03-27.md`
- single-run public baseline:
  - `configs/public_proof/releases_assets/news-digest-benchmark-summary-2026-03-27.md`
- proof screenshots:
  - `docs/releases/assets/news-digest-healthy-proof-gemini-2026-03-27.png`
  - `docs/releases/assets/news-digest-healthy-proof-grok-2026-03-27.png`
- storefront asset ledger:
  - `configs/public_proof/storefront/demo-status.md`

## Safe Public Wording

Use wording like:

- "OpenVibeCoding already has one release-proven public workflow case: `news_digest`."
- "The Workflow Case can be reused as a share-ready recap asset."
- "The public benchmark is currently a single-run `news_digest` baseline."

Avoid wording like:

- "OpenVibeCoding already has a broad public benchmark program."
- "All public cases are equally release-proven."
- "This recap proves a live hosted product or live GitHub publication state."

## Truth Boundary

- This recap is derived from the same successful local run summarized in
  `news-digest-healthy-proof-2026-03-27.md`.
- It is fit for public explanation and recap language, not for broader claims
  about hosted readiness, production scale, or stable multi-run performance.
- `topic_brief` now has a tracked search-backed public proof bundle, but it is
  still not the official first public baseline.
- `page_brief` now has a tracked browser-backed public proof bundle, but it is
  still not the official first public baseline.
- The missing storefront gaps still remain:
  - no broader multi-round public benchmark artifact
  - no confirmed live GitHub social preview upload
