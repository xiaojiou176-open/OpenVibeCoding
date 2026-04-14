# Render Hosted Operator Pilot

This runbook is the repo-side blueprint for a future guarded hosted operator
pilot on Render.

It is **not** proof that OpenVibeCoding already runs as a hosted operator service.
Treat it as a deployment contract draft that burns down the repo-side work until
the remaining steps are only Render-account, secret, DNS, and live verification
actions.

## Smallest honest cut

Use this cut only for a narrow operator pilot:

- one Render web service for the orchestrator API
- one Render web service for the dashboard
- no hosted login/account product story
- no write-capable MCP claim
- no broad-market SaaS claim
- public narrative remains anchored on `news_digest` as the release-proven
  first-run baseline

## What already exists

- public front door on GitHub Pages
- API auth via `OPENVIBECODING_API_TOKEN`
- repo-owned role-config preview/apply HTTP surfaces
- `/health` and `/api/health` for simple platform probes
- repo-owned run/worktree rollback semantics
- support/security/privacy docs that explicitly say the repo is not yet a
  hosted service

## What is still missing before live hosted claims

- a live operator URL
- a production secret contract, rotation plan, and owner workflow
- a hosted privacy/data-handling contract
- a hosted support/on-call expectation
- a deploy rollback playbook
- live smoke receipts for the dashboard and API together

## Proposed Render blueprint

The paired [render.yaml](../../render.yaml) file is a Git-backed blueprint for
the narrow pilot above.

Service intent:

1. `openvibecoding-api`
   - Python web service
   - starts `python -m openvibecoding_orch.cli serve --host 0.0.0.0 --port $PORT`
   - keeps auth on by default
   - requires a persistent disk because runtime state, queue state, run bundles,
     and logs are file-backed today

2. `openvibecoding-dashboard`
   - Node/Next.js web service
   - builds the repo-owned dashboard shell
   - requires the public API base URL plus a server-side operator token for
     dashboard-originated proxy requests

## Required environment contract

### API service

- `OPENVIBECODING_API_AUTH_REQUIRED=true`
- `OPENVIBECODING_API_TOKEN`
- `OPENVIBECODING_API_ALLOWED_ORIGINS`
- `OPENVIBECODING_PROVIDER`
- provider credential for the chosen provider:
  - `GEMINI_API_KEY`, or
  - `OPENAI_API_KEY`, or
  - `ANTHROPIC_API_KEY`
- `OPENVIBECODING_RUNTIME_ROOT=/var/data/openvibecoding`
- `OPENVIBECODING_RUNS_ROOT=/var/data/openvibecoding/runs`
- `OPENVIBECODING_WORKTREE_ROOT=/var/data/openvibecoding/worktrees`
- `OPENVIBECODING_LOGS_ROOT=/var/data/logs`

### Dashboard service

- `NEXT_PUBLIC_OPENVIBECODING_API_BASE`
- `OPENVIBECODING_API_TOKEN`

## Manual Render steps that still require a human

1. Sign in to Render and connect the Git provider.
2. Open the blueprint from the repository that contains `render.yaml`.
3. Create the persistent disk for the API service.
4. Fill the secret env vars in the Render dashboard.
5. Deploy once to obtain the public API URL.
6. Copy that API URL into `NEXT_PUBLIC_OPENVIBECODING_API_BASE`.
7. Set `OPENVIBECODING_API_ALLOWED_ORIGINS` to the dashboard URL.
8. Keep `OPENVIBECODING_API_TOKEN` server-only; do not mirror it through any
   `NEXT_PUBLIC_*` variable.
9. Re-deploy the dashboard so browser calls use the final API origin.
10. If a custom domain is desired, configure DNS and validate it in Render.

## Live verification checklist

1. API health:
   - `GET /health`
   - `GET /api/health`
2. Dashboard health:
   - dashboard root loads
   - the PM or Command Tower entry surface loads
3. Auth:
   - requests without the token fail closed
   - requests with the configured token succeed
4. First-run pilot:
   - run the `news_digest` path only
   - confirm the Workflow Case and Proof & Replay surfaces render
5. Boundary honesty:
   - public copy still says `not hosted operator product` until the full hosted
     contract changes

## Stop-signs

Do not call this hosted-ready if any of these are still missing:

- persistent disk configuration
- dashboard/API origin wiring
- auth verification
- support/security/privacy wording update
- live smoke receipts
