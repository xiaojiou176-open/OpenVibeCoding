# Scripts

This directory contains repo-owned helper scripts for bootstrap, verification,
CI, hygiene, and release tasks.

## Common Entry Points

- `bootstrap.sh`
- `run_orchestrator_cli.sh`
- `run_orchestrator_pytest.sh`
- `test.sh`
- `test_quick.sh`
- `check_repo_hygiene.sh`
- `check_workflow_static_security.sh`
- `check_trivy_repo_scan.sh`
- `check_secret_scan_closeout.sh`
- `scan_host_process_risks.py`
- `check_schedule_boundary.py`
- `docker_ci.sh`
- `prune_docker_runtime.sh`
- `repo_chrome_singleton.py`
- `build_space_governance_report.py`
- `check_space_cleanup_gate.py`
- `check_space_governance_inventory.py`
- `apply_space_cleanup.py`
- `cleanup_space.sh`

`run_orchestrator_pytest.sh` is the canonical repo-owned wrapper for
orchestrator pytest entrypoints. It resolves the managed Python toolchain,
exports `PYTHONDONTWRITEBYTECODE=1`, and keeps `PYTHONPATH=apps/orchestrator/src`
aligned so module docs do not rely on `uv run pytest` selecting a compatible
interpreter by accident.

`run_orchestrator_cli.sh` is the matching repo-owned wrapper for
`openvibecoding_orch.cli` commands. It keeps the managed Python toolchain and
`PYTHONPATH=apps/orchestrator/src` aligned so module docs do not depend on the
user's ambient Python environment.

## Audit Lane Notes

- Keep default blocking lanes focused on stable, repeatable checks.
- Public CI is hosted-first: fork PRs stay on low-privilege GitHub-hosted
  checks, while `ui-truth`, `resilience-and-e2e`, and `release-evidence` are
  protected `workflow_dispatch` lanes that require
  `owner-approved-sensitive`.
- `ui_audit_gate.sh` stages a temporary dashboard workspace for Lighthouse +
  axe verification; keep the required `packages/frontend-*` sources copied
  inside that temporary root so Next/Turbopack does not reject out-of-root
  symlinks during smoke builds.
- `install_dashboard_deps.sh` and `install_desktop_deps.sh` now escalate
  repeated pnpm `ERR_PNPM_ENOENT` failures from fresh-store retries to a
  workspace-local store recovery path instead of repeating the same failing
  copy strategy indefinitely.
- `scan_host_process_risks.py` is the repo-owned static gate for host-process
  safety. Run `npm run scan:host-process-risks` before live desktop/browser or
  cleanup flows; worker/test/orchestrator paths must fail closed instead of
  broad-killing stale processes.
- Bootstrap/install/docker-ci/clean-room entrypoints now run a rate-limited
  machine-cache auto-prune hook before creating new repo-owned external caches.
  The hook reuses `scripts/cleanup_runtime.sh apply` with root-noise cleanup
  disabled, so OpenVibeCoding still has one cleanup world instead of a separate
  cache-only deletion path.
- Temporary pnpm retry stores now stay under `~/.cache/openvibecoding` with the
  shared `pnpm-store-local-*` naming contract instead of ad-hoc
  `pnpm-store-dashboard-retry.*` / `pnpm-store-desktop-retry.*` variants.
- Hosted CI lanes now try `sudo -E bash scripts/docker_ci.sh ...` only when
  passwordless sudo is available; otherwise they fall back to direct
  `bash scripts/docker_ci.sh ...` execution so `main` push lanes do not fail on
  runners that can invoke Docker without an interactive sudo prompt.
- `prune_docker_runtime.sh` is the dedicated Docker runtime lane helper for
  OpenVibeCoding-owned local CI residue. It can remove stopped containers for the
  canonical core and desktop-native local CI images plus optional repo-prefixed
  volumes, while keeping workstation-global Docker/cache totals strictly
  observation-only.
- `docker_runtime_governance.py` is the structured report engine behind that
  lane. It writes `.runtime-cache/openvibecoding/reports/space_governance/docker_runtime.json`
  so Docker residue no longer exists only as shell stdout.
- `repo_chrome_singleton.py` is the repo-owned browser entrypoint for the
  local singleton Chrome model:
  - `npm run browser:chrome:migrate` copies the named default-Chrome profile
    into `~/.cache/openvibecoding/browser/chrome-user-data/` once
  - `npm run browser:chrome:launch` attaches to or launches the repo-owned
    Chrome singleton on the fixed CDP endpoint
  - `npm run browser:chrome:status` reports whether the repo-owned root is
    bootstrapped, which profile directory is active, whether CDP is live, and
    whether the last-known singleton state has gone stale, plus whether the
    current machine browser load still permits a safe new repo-owned launch
- `docker_ci.sh` now prefers repo-owned local buildx cache directories under
  `~/.cache/openvibecoding/docker-buildx-cache/` when `docker buildx` is
  available, which turns rebuildable Docker image cache into a governed
  repo-owned external cache instead of a purely opaque daemon-side layer.
  GitHub-hosted / in-container CI lanes intentionally keep that optimization
  disabled unless explicitly reopened, because the hosted Docker driver may not
  support local cache export.
- The doc-drift/doc-sync hooks now skip `ci-diff` comparisons when GitHub push
  events provide the all-zero base SHA on a repo-first push, so a freshly
  created public repository does not fail Quick Feedback before it has any real
  comparison baseline.
- `.github/workflows/github-control-plane.yml` now prefers the repo secret
  `GH_ADMIN_TOKEN` when present, because the default workflow token cannot read
  admin-only repository APIs such as Actions permissions, branch protection,
  and vulnerability-alert proofs.
- `docker_ci.sh` and `check_clean_room_recovery.sh` now keep their heavy
  machine-scoped temp roots under `~/.cache/openvibecoding/tmp/` by default
  (for example `tmp/docker-ci/runner-temp-*` and
  `tmp/clean-room-machine-cache.*`) so Darwin `TMPDIR` is no longer the
  default landing zone for those repo-owned heavy temp surfaces.
- `e2e_external_web_probe.py` no longer persists `run_id` in its JSON status
  and report artifacts; its JSON writer helpers no longer accept `run_id` as an
  input, and probe receipts now persist epoch timing fields, stage/category
  allowlists, and summarized artifacts from dedicated safe summary scalars
  only.
- `ci_slice_runner.sh` now exports `PYTHONDONTWRITEBYTECODE=1` before running
  the slice driver so hosted `policy-and-security` / `core-tests` lanes do
  not pollute the workspace with `__pycache__` residues mid-run.
- `ci_main_impl.sh` and `resolve_ci_policy.py` now write CI stage logs, policy
  snapshots, and the orchestrator coverage JSON under
  `.runtime-cache/test_output/ci/` so retention-report hygiene no longer flags
  root-level `test_output` residue during `main` push validation.
- `check_ci_runner_drift.py` still emits the GitHub-hosted runner drift report
  on every lane, but host-only commands such as `docker` and `sudo` stay
  report-only on hosted container routes (`trusted_pr`, `untrusted_pr`, and
  `push_main`) because those tools may be absent inside the repo-owned CI
  container even when the outer GitHub runner is healthy.
- `check_space_governance_inventory.py` now closes the loop between
  `runtime_artifact_policy.json`, `space_governance_policy.json`, and
  `cleanup_workspace_modules.sh`, so repo-local cleanup targets must be
  contract-declared before hygiene accepts them.
- `apply_space_cleanup.py` now records per-target reclaim estimates,
  post-cleanup verification commands, verification results, and rollback notes
  instead of treating deletion as a completed recovery by itself.
- `test_quick.sh` now keeps its quick-check logs under
  `.runtime-cache/test_output/governance/quick_checks/` so retention-report
  discipline no longer has to tolerate root-level `test_output` files.
- `check_schedule_boundary.py` now guards the queue/schedule runtime contract:
  `.runtime-cache/openvibecoding/queue.jsonl` must stay compatible with
  `queue_item.v1.json`, `scheduled_run.v1.json`, and `sla_state.v1.json`
  before repo-side hygiene accepts scheduling changes.
- `check_public_sensitive_surface.py` is the fail-closed gate for tracked
  public surfaces. It blocks maintainer-local absolute paths, raw token-like
  literals, direct email/phone markers, and forbidden tracked runtime files
  before those patterns can land on current public source surfaces.
- `security_scan.sh` now filters a very small allowlist of non-verified,
  synthetic placeholder findings from test/example git history while still
  failing on every other trufflehog hit.
- `security_scan.sh` also uses BSD-safe temp report naming for trufflehog
  scratch files, keeps the `.jsonl` hint ahead of the random suffix, and
  parses placeholder URIs strictly enough to allow only the exact synthetic
  `example.com` placeholder contract instead of broad prefix matches.
- `check_public_sensitive_surface.py` is the fail-closed tracked-surface gate
  for maintainer-local absolute paths, raw token-like literals, direct PII
  markers, and forbidden tracked runtime/sensitive files; it is wired into
  `check_repo_hygiene.sh` and a dedicated pre-commit hook.
- `check_github_security_alerts.py` is the live GitHub alert gate for current
  open `secret-scanning` and `code-scanning` findings; it is wired into
  repo hygiene, the host-compatible pre-commit quality gate, a dedicated
  pre-commit hook, pre-push, and Quick Feedback so cloud-side security
  regressions cannot hide behind a locally clean worktree. GitHub-hosted
  `trusted_pr`, `untrusted_pr`, and hosted-first `push_main` routes keep this
  query advisory-only in Quick Feedback and the hosted policy slice because
  the integration token may not be able to read the alerts APIs there and a
  fresh hosted `push_main` route may not have live analysis yet. The gate now
  queries the GitHub REST API directly from `GH_TOKEN` / `GITHUB_TOKEN` and
  only falls back to `gh auth token` for local token discovery, so
  containerized CI lanes do not depend on a `gh` binary being installed.
- `check_workflow_static_security.sh` is the repo-owned GitHub Actions static
  security gate. It bootstraps pinned `actionlint` + `zizmor` binaries through
  `scripts/lib/release_tool_helpers.sh`, then runs both scanners fail-closed
  through one stable workflow-hardening entrypoint.
- `check_trivy_repo_scan.sh` is the repo-owned Trivy filesystem/dependency
  lane. It scans the tracked repository surface plus lockfiles, skips generated
  runtime/build roots, and blocks on high/critical findings.
- `check_secret_scan_closeout.sh` is the closeout-oriented secret scan wrapper:
  `--mode current` runs the canonical repo history scan with pinned
  `trufflehog` / `gitleaks`, while `--mode both` reruns the same scan from a
  fresh clone so final closeout proof does not depend on the current workspace
  state.
- `.github/dependency-review-config.yml` is the repo-owned policy file for the
  official GitHub Dependency Review action, which now runs on pull requests and
  feeds into the PR CI closure path.
- `security_scan.sh` is paired with token/path-fixture hygiene in orchestrator
  tests: public fixtures must use synthetic fragments or generic workspace
  roots instead of maintainer-local paths or raw token-looking literals.
- `check_pip_audit_gate.py` now enforces Python dependency audit findings
  through a machine-readable ignore contract and only downgrades explicitly
  listed advisories when `pip-audit` exposes no published fix version.
- `install_dashboard_deps.sh` now detects `ERR_PNPM_ENOSPC` and retries with a
  workspace-local pnpm store plus hardlink imports so hosted `main`
  lanes can recover when copy-based installs exhaust the bind-mounted
  workspace volume.
- `install_desktop_deps.sh` now mirrors the same `ERR_PNPM_ENOSPC` recovery
  path, uses per-attempt workspace retry stores, and scopes hardlink imports
  to the recovery attempt so repeated hosted runs do not accumulate a
  long-lived desktop workspace cache.
- `install_dashboard_deps.sh` now records its install transcript under
  `.runtime-cache/logs/runtime/deps_install/install_dashboard_deps.log` even
  when its lock/retry bookkeeping still uses the temp state root.
- Run Gemini-backed UI audits explicitly when needed:
  - `python3 scripts/ui_ux_gemini_quick_gate.py`
  - `bash scripts/ci_slice_runner.sh ui-truth`
  - `bash scripts/ui_e2e_truth_gate.sh --strict-closeout`
- Desktop native Linux/BSD smoke and full Cargo.lock audits are
  explicit/manual lanes after the public desktop boundary moved to macOS-only.

## Rule Of Thumb

Prefer the scripts in this directory over one-off shell command sequences when
you need a repeatable repo workflow.
