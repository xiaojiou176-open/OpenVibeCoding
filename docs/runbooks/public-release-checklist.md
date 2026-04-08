# Public Release Checklist

Use this checklist before publishing a user-facing GitHub Release.

This file is the repo-side contract for the first public release bundle. It is
not the live GitHub Release page itself, and its presence alone does not prove
that the live notes, social preview, or other repository settings are current.

## 1. Truth Boundary

- Repo-side docs can prove what is tracked in git.
- Repo-side docs cannot prove that a live GitHub Release, social preview
  setting, or other repository setting has already been applied.
- The latest published release can lag current `main`; if it does, README,
  Pages, and `DISTRIBUTION.md` must say so directly instead of implying that
  the newest docs and the newest tag are already the same snapshot.
- Treat storyboard assets as explainers.
- Treat degraded or local-only captures as real assets with limited proof value,
  not as healthy end-to-end proof.

## 2. Official First Public Happy Path

For the first public release bundle, the only official happy-path baseline is
`news_digest`.

- `news_digest` is the only path that release notes, README release language,
  storefront copy, and proof tracking may describe as the first-run baseline.
- `topic_brief` and `page_brief` may remain in schema or advanced paths, but
  they are not part of the first public proof contract until each has its own
  healthy proof and benchmark.

## 3. Required Proof Bundle

Do not publish the first release as if it is fully proved unless this bundle is
explicitly checked:

| Proof item | Repo-side status today | Release requirement |
| --- | --- | --- |
| Release notes draft | exists in `docs/releases/first-public-release-draft.md` | convert to the live GitHub Release entry |
| README/storefront story | exists | must stay aligned with `news_digest` as the only first-run baseline |
| Healthy backend-backed `news_digest` capture set | exists in `docs/releases/assets/news-digest-healthy-proof-2026-03-27.md` plus copied screenshots | link or attach the tracked proof assets and keep `docs/assets/storefront/demo-status.md` aligned |
| Public benchmark artifact | exists as the single-run baseline in `docs/releases/assets/news-digest-benchmark-summary-2026-03-27.md` | if quoting numbers, quote from the tracked summary and keep the single-run scope explicit |
| Social preview upload candidate | exists in repo | still needs manual GitHub settings application |

If a proof item is still missing, say so directly in the release notes instead
of implying it exists.

## 4. User-Facing Notes Contract

Release notes should:

- explain what changed in user terms
- point readers to the `news_digest` happy path first
- separate present proof from planned proof
- list breaking changes or migration steps if they exist
- avoid raw commit dumps

Use `docs/releases/first-public-release-draft.md` as the repo-side draft, then
trim or expand it for the live GitHub Release page.

## 5. Minimum Verification

Run the smallest repo-side checks before a release-facing doc change:

```bash
CORTEXPILOT_HOST_COMPAT=1 bash scripts/test_quick.sh --no-related
bash scripts/check_repo_hygiene.sh
```

Run broader verification as needed for the release scope.

## 6. Storefront Asset Rules

- README hero must still render correctly
- storyboard assets may explain the loop, but they do not count as healthy proof
- release notes should include at least one useful screenshot, diagram, or
  proof surface when relevant
- benchmark claims must include environment, version or release identifier,
  baseline, reproduction command, suite count, and failure rate
- single-run benchmark baselines must stay labeled as single-run baselines
- if a capture was taken in a degraded or local-only state, label it that way

## 7. Manual GitHub Steps

- create or update the GitHub Release entry
- paste user-facing notes based on the repo-side draft
- attach artifacts if this release includes them
- upload the social preview image in GitHub settings if that step is part of
  the release pass
- verify the release page is public and subscribable
- confirm the published release does not claim healthy proof or benchmark data
  that is still marked missing in repo docs
