# Orchestrator DB Migrations

This directory is the governance anchor for orchestrator database migration artifacts.

## Rules

1. Any schema-impacting code change must include a migration artifact in this directory (or its `versions/` subdirectory).
2. Migration artifacts must be deterministic, reviewable, and reversible.
3. Migration-only documentation changes are allowed and should still pass governance checks with evidence.

## Governance Check

Use:

```bash
bash scripts/check_db_migration_governance.sh
```

Output:

- `.runtime-cache/openvibecoding/release/db_migration_governance.json`

The script reports:

- `PASS` when schema changes and migration evidence are both present.
- `FAIL` when schema changes are present but migration evidence is missing.
- `N/A_WITH_EVIDENCE` when no schema-signaling change exists.
