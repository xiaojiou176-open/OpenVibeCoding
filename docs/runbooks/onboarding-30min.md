# 30-Minute Onboarding

This guide is the shortest path to a productive local setup.

If you only want the shortest public evaluation path, follow the root
`README.md` first-success flow instead. This runbook is the contributor-oriented
setup path.

## 1. Bootstrap

```bash
npm run bootstrap
```

## 2. Run the main checks

```bash
npm run ci
npm run test
npm run test:quick
bash scripts/check_repo_hygiene.sh
```

## 3. Read the core docs

1. `README.md`
2. `docs/README.md`
3. `docs/architecture/runtime-topology.md`
4. `docs/specs/00_SPEC.md`

## 4. Pick a module

- `apps/orchestrator/`
- `apps/dashboard/`
- `apps/desktop/`

Read the nearest `README.md`, `AGENTS.md`, or `CLAUDE.md` before editing.
