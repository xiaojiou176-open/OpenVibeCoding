# Public Benchmark Methodology

This document exists so OpenVibeCoding can talk about benchmark evidence without
inventing numbers.

## Current State

- Benchmark execution tooling exists:
  - `scripts/bench_e2e_speed.py`
  - `scripts/bench_e2e_speed.sh`
  - `scripts/check_bench_e2e_speed_gate.py`
- A first tracked public single-run baseline now exists at
  `docs/releases/assets/news-digest-benchmark-summary-2026-03-27.md`.
- Broader multi-round public benchmark figures do **not** exist yet.
- A tracked route/blocker receipt for the latest real attempt lives at
  `docs/releases/assets/news-digest-benchmark-route-2026-03-27.md`.
- Any public performance or reliability claim must quote a tracked summary
  copied out of `.runtime-cache/`, and must keep the current single-run scope
  explicit until a broader benchmark artifact exists.

## First Public Release Contract

For the first public release bundle:

- the benchmark must cover the official `news_digest` happy path first
- a repo-tracked public summary must exist before README, release notes, or
  social copy can quote any number
- the public artifact should live in a tracked release-facing path such as
  `docs/releases/assets/` or `docs/assets/storefront/`
- the artifact must be generated from a real run, not a dry run or planning
  preview

## How To Generate A Real Public Baseline

Use a managed Python toolchain and run one of these:

```bash
bash scripts/bench_e2e_speed.sh --rounds 3 --ui-full-gemini-strict --dashboard-high-risk
```

or, for a planning-only preview of the suite selection:

```bash
bash scripts/bench_e2e_speed.sh --rounds 3 --ui-full-gemini-strict --dashboard-high-risk --dry-run
```

## What A Public Benchmark Must Include

- environment
- version / commit or release identifier
- baseline
- reproduction command
- suite count and failure rate
- artifact path committed to the repository

## Minimum Artifact Shape

A tracked public benchmark artifact should include:

- a short Markdown summary for humans
- the exact command that produced the run
- a pointer to the raw machine output location that was copied out of
  `.runtime-cache/`
- enough metadata to show which happy path was exercised

## Gate Contract

Once a real benchmark summary exists, the repo-owned fail-closed gate is:

```bash
npm run bench:e2e:speed:gate
```

Default thresholds are driven by:

- `OPENVIBECODING_BENCH_MAX_FAIL_RATE`
- `OPENVIBECODING_BENCH_UI_FULL_GEMINI_STRICT_MAX_P95_SEC`
- `OPENVIBECODING_BENCH_DASHBOARD_HIGH_RISK_E2E_MAX_P95_SEC`

The gate is intentionally strict about artifact presence: if no benchmark
summary exists yet, it fails instead of inventing a baseline.

## Anti-Fraud Rule

Do not copy raw numbers into README, release notes, or social posts unless they
come from a real run and the tracked public artifact is updated in the same
change set.

Do not describe the current baseline as a broad release average. It is the
first tracked `news_digest` baseline, not the final benchmark story.
