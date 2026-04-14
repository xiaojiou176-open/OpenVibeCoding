# Project: OpenVibeCoding (Codex-governed)

## Red lines
- File isolation is absolute: no two workers touch the same file.
- Only Searcher searches; Reviewer never edits.

## Working agreement
- All tasks must have a Task Contract with allowed_paths and acceptance_tests.
- Any diff outside allowed_paths -> revert + fail.
- All workers must deliver message + diff + test evidence.

## Default E2E definition (Day-1)
- 1 user story: to be defined by PM.
- 1 CLI command: scripts/e2e.sh
- 1 deterministic result: exit code 0 with expected output.
