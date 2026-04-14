# Contributing

Thank you for considering a contribution to OpenVibeCoding.

## Good Contributions

- reproducible bug fixes
- documentation improvements
- targeted tests
- narrowly scoped feature work with a clear problem statement

## Please Avoid

- large refactors mixed with behavior changes
- drive-by formatting-only pull requests
- compatibility shims without a removal plan
- policy or license changes without maintainer alignment

## Before You Open A Pull Request

1. Read [README.md](README.md).
2. Read [docs/README.md](docs/README.md).
3. Read the nearest module guide if you touch `apps/orchestrator`, `apps/dashboard`, or `apps/desktop`.
4. Run the relevant verification commands locally.

## Required Standards

- keep changes scoped to one main purpose
- update tests when behavior changes
- update docs when commands, APIs, or public behavior change
- do not commit runtime output, logs, local secrets, or generated noise
- prefer minimal, auditable diffs over broad rewrites

## Pull Request Checklist

- explain what changed and why
- list exact verification commands you ran
- call out unresolved risks
- update documentation when needed

See [`.github/pull_request_template.md`](.github/pull_request_template.md) for the expected format.
