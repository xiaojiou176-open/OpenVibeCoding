# Business Logic Closure Matrix — 2026-04-14

## Scope Actually Closed In This Wave

| Area | What landed | Evidence |
| --- | --- | --- |
| Dependency tail | absorbed `playwright 1.59.1`, `vitest 4.1.3`, `@vitest/coverage-v8 4.1.3`, `@types/node 25.5.2` into tracked manifests + lockfiles | PR `#117` merge commit `8f4fdfde8eaf74a273859b4e43dbd9bee8f22ba0` |
| Desktop stale tests | aligned stale desktop assertions with the current sidebar section naming, localized runs heading, and design token truth | updated desktop test files on `main` via `#117` |
| Maintenance PR closeout | superseded open maintenance PRs were closed and their remote branches removed | PRs `#102/#103/#105/#106/#112` closed; remote heads reduced to `main` only |
| Security alert tail | dismissed the remaining `rand` low alert with a repo-scoped `not_used` judgment backed by fresh reachability evidence | GitHub Dependabot alert `#14` state = dismissed |

## Scope Explicitly Not Reopened

| Area | Why it stayed frozen |
| --- | --- |
| hosted operator rollout | outside repo-owned write scope for this wave |
| write-capable MCP rollout | still later-gated |
| registry / marketplace publication | still external-only / owner-manual later |
| internal deep namespace hard-cut | not required to close the repo-owned blocker set in this wave |

## Negative Tests / Non-Regression Proof

- dashboard targeted regression bundle -> pass
- desktop targeted stale-failure bundle -> pass after assertions were realigned
- repo hygiene -> pass
- docs check -> pass

## Remaining Non-Repo-Owned Tail

- stale / red upstream receipts remain outside repo-owned closure
- host-level Docker helper / socket bring-up remains `owner-manual later`
