# Space Governance

Use the repo-owned space governance workflow when you need a repeatable
disk-space audit or a guarded cleanup plan.

This workflow now sits beside runtime retention rather than replacing it:

- `retention.py` owns canonical runtime lanes such as `.runtime-cache/logs`,
  `.runtime-cache/cache`, runs/worktrees/contracts/intakes/codex-homes, plus
  repo-owned machine-cache child retention under `~/.cache/openvibecoding`, and
  emits `retention_report.json`.
- `space_governance.py` owns high-yield cleanup candidates, low-risk workspace
  residue, and repo-external strong-related cache surfaces, and emits
  `space_governance/report.{json,md}` plus gated cleanup receipts.

## Commands

```bash
npm run space:audit
npm run space:gate:wave1
npm run space:gate:wave2
npm run space:gate:wave3
bash scripts/cleanup_space.sh wave1 dry-run
npm run docker:runtime:audit
```

## What The Workflow Produces

- `.runtime-cache/openvibecoding/reports/space_governance/report.json`
- `.runtime-cache/openvibecoding/reports/space_governance/report.md`
- `.runtime-cache/test_output/space_governance/cleanup_gate_<wave>.json`

## Policy Boundaries

- Repo-internal high-yield surfaces include dashboard/desktop `node_modules`,
  orchestrator `.venv`, and desktop `dist`.
- Repo-external strong-related surfaces are limited to the OpenVibeCoding machine
  cache namespace under `~/.cache/openvibecoding`.
- Repo-authored runtime/test/temp/evidence artifacts stay under
  `.runtime-cache/`; app-local dependency/build roots such as
  `node_modules`, `.next`, `.venv`, and `*.tsbuildinfo` remain explicit
  build/dependency exceptions rather than part of the unified runtime cache.
- Runtime retention now applies a **default 20 GiB cap** to that machine-cache
  namespace, but only through repo-owned child paths that are explicitly marked
  in `configs/space_governance_policy.json`. The cap never turns the rollup root
  itself into an apply target.
- `~/.cache/openvibecoding/browser/**` is a special-case repo-owned persistent
  browser workspace. It stays visible in audit/report output, but it is both
  `protected` and `cap-excluded`, so TTL/cap auto-prune never treats it as a
  reclaim target.
- Heavy machine-scoped temp producers also belong to that same governed
  namespace: local `docker_ci` host runner temp now defaults to
  `~/.cache/openvibecoding/tmp/docker-ci/runner-temp-*`, while clean-room
  recovery uses `~/.cache/openvibecoding/tmp/clean-room-machine-cache.*` and
  `~/.cache/openvibecoding/tmp/clean-room-preserve.*`.
- Shared ecosystem layers such as Docker Desktop, global Cargo/Rustup, global
  uv, and global Playwright remain observation-only unless a separate audit
  proves safe attribution.
- Cross-repo symlink targets, such as Python toolchains that resolve into
  another repo namespace, are never treated as single-repo cleanup targets.

## Docker Runtime Lane

Use the dedicated Docker runtime lane when disk pressure is dominated by the
local CI image family or builder cache:

```bash
npm run docker:runtime:audit
npm run docker:runtime:prune:rebuildable
npm run docker:runtime:prune:aggressive
npm run docker:runtime:prune:aggressive:full
```

Current semantics:

- `docker:runtime:audit` reports `openvibecoding-ci-core:local`,
  `openvibecoding-ci-desktop-native:local`, stopped containers derived from those
  images, repo-related named volumes, and a workstation-global Docker summary
  for observation only
- `docker:runtime:prune:rebuildable` removes stopped OpenVibeCoding-owned
  containers only
- `docker:runtime:prune:aggressive` extends rebuildable cleanup and may also
  remove the canonical local CI image or repo-related named volumes when
  explicitly unlocked with `--include-image` / `--include-volumes`
- `docker:runtime:prune:aggressive:full` is the package-level convenience alias
  that unlocks both image and repo-related volume removal

The Docker runtime lane is the canonical operator path for Docker-heavy local
CI residue. Keep `space:cleanup:wave*` focused on repo-local residue and the
governed `~/.cache/openvibecoding` namespace. Workstation-global Docker/cache
totals remain observation-only and are not apply targets for this lane.

The lane now also writes a structured receipt to
`.runtime-cache/openvibecoding/reports/space_governance/docker_runtime.json`.
That receipt includes managed image/container/volume/build-cache totals,
planned reclaim bytes, actual reclaimed bytes, and any `skipped_active`
surfaces that stayed live.
Repo-owned `docker-buildx-cache/` is intended for local developer/recovery
lanes. GitHub-hosted and in-container CI stay fail-closed on the simpler daemon
path when cache export is unavailable, rather than forcing buildx local cache
into an unsupported environment.

## Cleanup Rules

- Always run the audit and the wave gate before any cleanup apply step.
- `wave1` is for low-risk repo-local residue such as `__pycache__`,
  `.pytest_cache`, `.next`, `dist`, `*.tsbuildinfo`, and aged runtime temp or
  evidence children.
- `wave2` is for repo-local dependency surfaces and gray-zone build outputs.
  Heavy repo-local targets stay serial-only: clean one, rebuild/verify it, then
  move to the next.
- `wave3` is for `~/.cache/openvibecoding` and requires explicit shared-cache
  confirmation. The preferred apply targets are child paths such as
  `pnpm-store/dashboard`, `pnpm-store/desktop`, `pnpm-store/v10`,
  `playwright`, and the governed machine-temp roots under `tmp/`, not the
  rollup root.
- The repo-owned machine-temp roots are part of `wave3`, not generic system
  temp cleanup. Current examples are:
  - `tmp/docker-ci/runner-temp-*`
  - `tmp/clean-room-machine-cache.*`
  - `tmp/clean-room-preserve.*`
- Automatic retention TTLs inside `~/.cache/openvibecoding` are currently:
  - `tmp/**` repo-owned child roots: **24h**
  - `playwright/`: **7d**
  - `pnpm-store/dashboard` and `pnpm-store/desktop`: **7d**
  - `pnpm-store/v10`: **14d**
  - `pnpm-store-local-*`: **24h**
  - `docker-buildx-cache/*`: **72h**
- The governed machine-cache root has a default cap of **20 GiB**. Retention
  first clears TTL-expired repo-owned child paths, then adds the oldest/largest
  eligible child paths under cap pressure until the projected total returns
  below the threshold or only protected surfaces remain.
- The repo-owned singleton browser subtree under
  `~/.cache/openvibecoding/browser/` is outside that cap-pressure math. It is a
  persistent workspace for the single headed Chrome instance and must not be
  treated as reclaimable machine cache.
- These paths stay `repo_external_related`, must resolve inside
  `~/.cache/openvibecoding/tmp/**`, and must fail closed if they escape into
  unrelated temp roots or shared/system-owned browser temp trees.
- `toolchains/python/current`, shared observation layers, and any
  `observe-only` entry remain reportable but never become automatic retention
  targets.
- The repo-owned browser singleton uses these explicit operator commands:
  - `npm run browser:chrome:migrate`
  - `npm run browser:chrome:launch`
  - `npm run browser:chrome:status`
- Heavy producer entrypoints now run a rate-limited auto-prune hook before
  creating new external caches:
  - `scripts/bootstrap.sh`
  - `scripts/install_dashboard_deps.sh`
  - `scripts/install_desktop_deps.sh`
  - `scripts/install_frontend_api_client_deps.sh`
  - `scripts/docker_ci.sh`
  - `scripts/check_clean_room_recovery.sh`
- Auto-prune uses the existing `cleanup runtime --apply` path with root-noise
  cleanup disabled, so OpenVibeCoding still has one cleanup world instead of a
  separate machine-cache-only deletion path.
- Docker runtime is now a separate operator lane rather than part of the
  generic wave cleanup:
  - `npm run docker:runtime:audit`
  - `npm run docker:runtime:prune:rebuildable`
  - `npm run docker:runtime:prune:aggressive`
  - `npm run docker:runtime:prune:aggressive:full`
- Lane semantics:
  - `audit` inventories `openvibecoding-ci-core:local`,
    `openvibecoding-ci-desktop-native:local`, exited repo containers, repo-related
    named volumes, and a workstation-global Docker summary that is explicitly
    observation-only.
  - `rebuildable` removes exited repo containers and keeps shared Docker/cache
    layers untouched.
  - `aggressive` can additionally remove `openvibecoding-ci-core:local` and
    `openvibecoding-ci-desktop-native:local` when they are not backing running
    containers.
  - `aggressive:full` extends `aggressive` by also removing repo-related named
    volumes that match the configured prefix.
- A blocked gate means stop.
- A manual-confirmation gate means the path is hot or shared and needs an
  explicit override before apply.
- Apply only from a freshly generated gate artifact; stale gate JSON or
  cross-repo symlink targets must fail closed rather than partially cleaning.
- `observe-only` means the object can appear in reports but must not enter apply
  scope. This covers shared observation layers and high-risk gray zones such as
  `~/.cache/openvibecoding/toolchains/python/current` until live owner validation
  exists.
- Cleanup receipts now carry expected reclaim bytes, execution order,
  post-cleanup verification commands, and per-target verification outcomes so a
  cleanup step cannot be mistaken for a completed recovery.
- `retention_report.json` now also records machine-cache entry-level TTL, age,
  size, candidate status, process-blocked status, cap delta, and the last apply
  result so external cache pressure is auditable instead of manual-only.
- `space_governance/report.json` embeds that same retention snapshot, including
  `machine_cache_summary` and the latest `machine_cache_auto_prune` receipt, so
  operators do not have to manually cross-open two separate reports just to
  inspect machine-cache pressure.
- `space_governance/report.json` also embeds the latest Docker runtime receipt,
  so the same governance surface can answer “what is the repo-owned Docker
  residue right now?” without relying on shell output alone.
