# Desktop AGENTS

Read root `AGENTS.md` first.

## Scope

- desktop UI and navigation
- Tauri integration
- desktop-specific build and test workflows

## Commands

- `npm --prefix apps/desktop install`
- `npm --prefix apps/desktop run test`
- `npm --prefix apps/desktop run tauri:dev`
- `npm run scan:host-process-risks`

## Safety

- desktop real E2E scripts must fail closed on stale repo-owned runtime state
- do not use AppleScript `System Events`, `killall`, `pkill`, detached cleanup,
  or process-group termination in desktop worker/test/orchestrator paths
- only terminate the recorded child handle started by the current script
