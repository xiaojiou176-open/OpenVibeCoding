# 00_SPEC - CortexPilot Engineering Specification (Single Source of Truth)

> **Active entrypoint note**: this is the current active spec entrypoint and the main product/specification reference for public contributors.

> **Status**: Normative / hard enforcement gates must follow this document  
> **Last Updated**: 2026-04-12
> **Scope**: this repository (monorepo), including CortexPilot Orchestrator and the multi-agent collaboration runtime  
> **Non-goal**: this document does not carry vision, story, or dialectical history; for those materials, see `10_VISION.md` / `90_HISTORY.md`

---

## 0. Document Governance

### 0.1 Authority And Conflict Handling

- This file is the repository's **single authoritative specification** (SSOT). Any implementation, tool, or agent behavior must satisfy the constraints defined here.
- Other documents (vision, architecture whitepapers, dialectical notes, and similar materials) are explanation and background only; they **must not override** this specification.
- **Field-level authority**:
  - `schemas/*.json` are the authoritative source for field shape and required-field constraints (schema-first).
  - This file is the authoritative source for semantics, gate rules, on-disk layout, and state-machine behavior.
  - If this file conflicts with `schemas/`, **schema wins for field constraints, this file wins for semantics and gates**. The conflict must be removed in the next change set.

### 0.2 Three Non-Negotiables

- **Auditability**: the full evidence chain must be attributable, reviewable, and replayable.
- **Reproducibility**: the system must support both rehydration and re-execution comparison.
- **Strong Constraints**: enforcement must come from engineering gates, not from prompt persuasion.

### 0.3 Fail-Closed Principle

- Any gate failure **must fail closed**. The system must not continue past a failed gate.
- Any out-of-scope or out-of-policy behavior must record a `policy_violation` or `gate_failed` event and emit an explainable structured report.

### 0.4 Execution-Plane / Orchestration-Plane Boundary

- **Execution plane (side effects allowed)**: any role or step that modifies files, runs commands, or produces patches must go through Codex MCP (or an equivalent execution plane) and remain constrained by `sandbox`, `diff gate`, and `worktree` isolation.
- **Orchestration plane (no side effects)**: roles that only generate structured plans, reviews, or test reports may use Agents SDK structured outputs, but they **must not** modify files or execute commands.
- **Boundary rule**: if a step requires side effects, it must use the execution plane. If it does not require side effects, prefer the orchestration plane.

---

## 1. Glossary And Naming

> Terms are the shared language of contracts and evidence chains. Inconsistent naming directly damages auditability and replayability.

- **Contract**: a structured task contract; the **only** valid instruction carrier. Natural-language handoff is forbidden.
- **Result / Report**: structured outputs produced by execution, review, or testing, primarily in JSON.
- **Run**: a complete execution instance and its evidence chain; the directory root is `.runtime-cache/cortexpilot/runs/<run_id>`.
- **Run Bundle**: the `.runtime-cache/cortexpilot/runs/<run_id>` directory and everything inside it.
- **Run Store**: the root directory `.runtime-cache/cortexpilot/runs/`.
- **Gate**: a hard gate such as diff / tool / reviewer / tests / network / MCP / integrated / sampling.
- **Worktree**:
  - **P1 default (parallel L2 / multi-worker)**: `.runtime-cache/cortexpilot/worktrees/<run_id>/<task_id>`, one worktree per task with physical isolation.
  - **P0 compatibility**: `.runtime-cache/cortexpilot/worktrees/<run_id>` is allowed only for a single task running serially.
  - **Concurrency hard rule**: if L2 parallelism or multiple workers must write concurrently, P1 is mandatory. Concurrent writes inside a single P0 worktree are forbidden.
- **Event Stream**: `events.jsonl` (append-only).
- **Minimum `events.jsonl` fields**: `ts` / `level` / `event_type` / `run_id` / `task_id` / `attempt` / `payload`.
- **Task Contract**: `schemas/task_contract.v1.json` (field-level single authority).
- **allowed_paths**: the whitelist of writable paths. Only exact paths or directory prefixes are allowed. Wildcards such as `*` or `**` are forbidden.
- **sandbox**: at the contract layer only `read-only | workspace-write` are allowed (mapped to Codex `--sandbox` at runtime).
- **approval_policy / approval-policy**:
  - `approval_policy`: the default permission semantic in Agent Registry (for example `untrusted`, `on-request`, `never`)
  - `approval-policy`: the Codex payload field name (mapped from `tool_permissions.shell`; see 6.1.2)
- **thread_id / codex_thread_id**: the Codex MCP session anchor for continuation and handoff (`codex_thread_id` in the contract, `thread_id` in the manifest)

---

## 2. Repository Layout And Runtime Root

### 2.1 Required Directories

- `schemas/`: all JSON Schemas (field-level authority)
- `apps/orchestrator/`: the single trusted control plane
- `contracts/`: contract examples and notes (examples, plans, and similar materials)
- `docs/`: human-readable documents only; they must not conflict with the specification
- `.runtime-cache/cortexpilot/`: runtime artifact root (must be gitignored; may be overridden with `CORTEXPILOT_RUNTIME_ROOT`)
- `CORTEXPILOT_CODEX_BASE_HOME`: the Codex MCP home root (must include full `mcp_servers.*` and the Equilibrium provider). Role-specific homes must not carry `mcp_servers.*`

### 2.2 Required Development And Test Entrypoints

- `requirements-dev.txt`
- `./scripts/bootstrap.sh`
- `./scripts/test.sh`

---

## 3. P0 Must-Ship Checklist

> This is the smallest dependency-ordered closure path. If these items are complete, Day-1 E2E can run.

### 2.0 P0 Execution Checklist

* **Terminology**
  * The canonical terminology lives in the "Glossary And Naming" section of this file.
* **Execution order (dependency-sorted)**
  1. Freeze the schemas: `task_contract.v1.json` / `run_manifest.v1.json` / `task_result.v1.json` / `work_report.v1.json` / `review_report.v1.json` / `test_report.v1.json` / `evidence_report.v1.json` / `evidence_bundle.v1.json` / `reexec_report.v1.json` / `agent_registry.v1.json` / `orchestrator_event.v1.json`
  2. Run Store: create `.runtime-cache/cortexpilot/runs/<run_id>` and initialize `contract.json` / `manifest.json` / `events.jsonl`
  3. Worktree: create `.runtime-cache/cortexpilot/worktrees/<run_id>/<task_id>` (P1 default), run `git worktree prune` first, and `git worktree remove --force` at the end
  4. Locks: `.runtime-cache/cortexpilot/locks/<sha256>.lock`, with all-or-nothing acquisition and release
  5. Gates: schema / diff / tool / reviewer / tests + network / MCP / integrated / sampling (scope violations fail immediately)
  6. Runner: Codex / Agents Runner must inject `sandbox` / `approval-policy` / `cwd` / `codex_thread_id`
     * Production execution must be MCP-only; `codex exec --json` is reserved for diagnostics and regression sampling
  6.1 Output schema binding: any step that requires structured output must bind an output schema (see 6.2.1) and enforce it at the execution layer; missing schema binding must fail closed
  6.2 Role prompt discipline: when structured output is required, the role prompt must not request natural-language delivery; all content must remain inside JSON fields
  7. Evidence: write `patch.diff` / `diff_name_only.txt` / `reports/*.json`, then generate `manifest.json` + `evidence_hashes`
  8. Replay: support both Rehydration (no LLM call) and Re-execution (rerun)
  9. CLI and acceptance: `init` / `doctor` / `run` / `serve` + Day-1 E2E
* **Archival rule**
  * Runtime artifacts may land only inside `.runtime-cache/cortexpilot/runs/<run_id>`. Scattered output paths are forbidden.

---

## 4. Schemas (v1) And Version Strategy

### 4.1 Required Schemas (v1)

- `schemas/task_contract.v1.json`
- `schemas/task_result.v1.json`
- `schemas/work_report.v1.json`
- `schemas/review_report.v1.json`
- `schemas/test_report.v1.json`
- `schemas/orchestrator_event.v1.json`
- `schemas/reexec_report.v1.json`
- `schemas/run_manifest.v1.json`
- `schemas/evidence_bundle.v1.json`
- `schemas/evidence_report.v1.json`
- `schemas/agent_registry.v1.json`

### 4.2 Schema Drift And Compatibility

- **Schema drift detection**: any schema change must be detectable and traceable through commit, version, and change history.
- Parsers may use a tolerant strategy for unknown fields and preserve the raw event payload.
- Missing required fields must still fail closed.

---

## 5. Run Bundle Specification

### 5.1 Run Bundle Root Directory

- The actual on-disk root is `.runtime-cache/cortexpilot/runs/<run_id>`.
- `events.jsonl` must remain **append-only**, and writes must use both `flush` and `fsync`.

### 5.2 Minimum Required Directory Structure

> The list below is the minimum allowed set. Extensions are allowed; removals are not.

### 2.2 Directory Structure Specification

* General rule
  * Every task execution artifact must be written into this structure.
  * It must support:
    * Replay by Rehydration
    * Audit
* On-disk rule
  * The real on-disk location must be `.runtime-cache/cortexpilot/runs/<run_id>`.
* Directory structure (aligned to the current implementation)
  ```text
  .runtime-cache/cortexpilot/runs/
  ├── <run_id>/                        # unique directory for each run
  │   ├── contract.json                # initial Task Contract
  │   ├── manifest.json                # Run Manifest
  │   ├── events.jsonl                 # Orchestrator event stream (evidence-hash baseline)
  │   ├── patch.diff                   # root-level patch
  │   ├── diff_name_only.txt           # root-level diff file list
  │   ├── meta.json                    # runtime metadata
  │   ├── worktree_ref.txt             # linked worktree path
  │   ├── reports/                     # structured reports (task_result.json / review_report.json / test_report.json / evidence_bundle.json / evidence_report.json)
  │   ├── artifacts/                   # artifacts
  │   ├── tasks/                       # sub-task contracts
  │   ├── results/                     # mirrored task results (results/<task_id>/result.json + patch)
  │   ├── reviews/                     # reviewer outputs (task-level)
  │   ├── ci/                          # CI / test runner outputs
  │   ├── patches/                     # task-scoped diffs
  │   ├── codex/                       # Codex execution-layer data
  │   │   └── <task_id>/
  │   │       ├── events.jsonl         # raw Codex event stream (supporting evidence)
  │   │       ├── transcript.md        # human-readable session record
  │   │       └── thread_id.txt        # Codex thread ID
  │   ├── git/                         # Git-related evidence
  │   │   ├── baseline_commit.txt      # pre-run baseline commit
  │   │   ├── patch.diff               # Git-level patch
  │   │   └── diff_name_only.txt       # Git-level diff list
  │   ├── tests/                       # acceptance test evidence
  │   │   ├── command.txt              # executed test command
  │   │   ├── stdout.log
  │   │   └── stderr.log
  │   ├── trace/                       # tracing evidence
  │   │   └── trace_id.txt             # linked OpenTelemetry / Langfuse trace ID
  │   └── meta.json                    # environment metadata (model version, params, env hash)
  ```

### 5.3 Default Files Under `reports/`

- `reports/task_result.json`
- `reports/review_report.json`
- `reports/test_report.json`
- `reports/evidence_bundle.json`
- `reports/evidence_report.json`

---

## 6. Contract System

### 6.1 Task Contract (Input-Side Contract)

- **Only valid instruction carrier**: the task contract is the only legal basis for agent collaboration.
- The Orchestrator must validate the schema during handoff and reject invalid contracts immediately.
- **Hard constraints (excerpt)**:
  - `allowed_paths` must not be empty and must not use `*` or `**`
  - `assigned_agent` must exist so the execution owner is explicit
  - `tool_permissions` and `acceptance_tests` are hard input constraints
  - `tool_permissions.filesystem` may only be `read-only | workspace-write`
  - `tool_permissions.shell` must map to Codex `approval-policy` using the table in 6.1.2
  - `danger-full-access` may exist only as a platform capability enum; the contract must **always reject** it unless God Mode grants a temporary, fully evidenced override

#### 6.1.1 Task Contract v1 (Field-Level Authority)

- Schema path: `schemas/task_contract.v1.json`
- For readability, Appendix A keeps a human-readable schema copy. The implementation still follows `schemas/`.

#### 6.1.2 Shell Permission Mapping (Hard Rule)

> The goal is to make `tool_permissions.shell` and Codex `approval-policy` deterministic and testable.

| tool_permissions.shell | Codex approval-policy | Execution semantics (fail-closed) |
| --- | --- | --- |
| `deny` | **unset / shell tool forbidden** | any shell request is rejected immediately and recorded as `policy_violation` |
| `never` | `never` | automatically reject all commands that require approval |
| `on-request` | `on-request` | enter approval flow; reject if approval is missing |
| `untrusted` | `untrusted` | every command enters approval flow |

- **Default**: if the field is omitted, treat it as `deny` (least privilege).
- **Execution boundary**: the Orchestrator must apply allowlist/denylist checks before dispatching or executing commands.

#### 6.1.3 Output Schema Binding

> This turns "structured output required" from a prompt wish into an engineering hard constraint.

- **Mandatory binding**: when a task requires structured output, `inputs.artifacts` must include one output schema artifact (JSON Schema).
  - Naming rule: `name` must be `output_schema` or `output_schema.<role>` (for example `output_schema.pm`, `output_schema.worker`)
  - `uri` must point to a repository path such as `schemas/*.json`, and `sha256` is required
- **Execution-layer enforcement**:
  - Codex CLI / MCP must use `--output-schema`
  - Agents SDK must use Structured Outputs (`output_type` or equivalent)
- **Fail-closed rule**: missing output-schema binding must reject execution immediately and emit `policy_violation` or `gate_failed`

#### 6.1.4 Role Contract v1 (Resolved Role View)

- The compiled task contract may carry a resolved `role_contract` object.
- `role_contract` does **not** replace top-level contract fields; it is the
  compiled, read-friendly view of:
  - assigned role identity
  - role purpose
  - prompt ref / skills ref / MCP bundle ref
  - runtime binding (`runner` / `provider` / `model`, when known)
  - tool permissions
  - handoff posture
  - fail-closed conditions
- The Orchestrator must keep `role_contract` consistent with the top-level
  `assigned_agent`, `tool_permissions`, `mcp_tool_set`, `runtime_options`, and
  `handoff_chain` fields. Drift between the resolved role view and the
  authoritative top-level contract must fail closed.
- Intake preview should expose a `role_contract_summary` when available so the
  preview surface and the final execution contract describe the same resolved
  role.
- When available, the Orchestrator may also emit a contract-derived
  `role_binding_summary` read model in PM intake responses and run manifests so
  bundle/runtime state stays inspectable after execution without becoming a
  second execution authority source.
- Read-only run surfaces may project that same contract-derived binding view as
  `role_binding_read_model`, but those projections remain read models layered
  on top of the task contract rather than replacement execution authority.
- Workflow/control-plane reads may project a `workflow_case_read_model` derived
  from the latest linked run's persisted `role_binding_summary`, but that
  projection must remain explicitly read-only and must keep
  `execution_authority = task_contract`.
- Dashboard and desktop Workflow Case detail views may render that same
  `workflow_case_read_model` for operator inspection, but they must present it
  as a read-only case summary instead of an execution-authority switch.

### 6.2 Output-Side Contracts (Results / Reports)

> The Orchestrator may advance the state machine using structured outputs only. Natural-language parsing is forbidden.

- TaskResult required fields: `run_id`, `task_id`, `producer`, `status`, `started_at`, `finished_at`, `summary`, `artifacts`, `git`, `gates`, `next_steps`
- WorkReport uses lowercase status enums (`success/fail/aborted`) for quick aggregation and does not replace TaskResult
- ReviewReport required fields: `run_id`, `reviewer`, `reviewed_at`, `verdict`, `summary`, `scope_check`, `evidence`; `produced_diff` must always be `false`
- TestReport required fields: `run_id`, `task_id`, `runner`, `started_at`, `finished_at`, `status`, `commands`, `artifacts`
- Status enums remain uppercase across the main report layer (`SUCCESS/FAILED/BLOCKED/SKIPPED`, `PASS/FAIL/ERROR/SKIPPED`)

#### 6.2.1 Role Output Lock (JSON-Only)

- **Hard rule**: when a task requires structured output, the role prompt must not include a natural-language delivery checklist. All delivery content must stay inside JSON fields.
- **Output gate**: any non-JSON output, or any JSON output that fails the schema, must fail closed and must not reach the next state.
- **Structured fallback**: if explanatory text is required, it must be written into `summary` or another explicit JSON field. Text outside the JSON payload is forbidden.

#### 6.2.2 Handoff Summary Rule (Contract-Authoritative)

- Handoff output may contain structured summary fields such as `summary` and
  `risks`, but it must not replace or rewrite the task contract instruction.
- The task contract remains the only legal instruction carrier across role
  transitions.
- If a handoff artifact is emitted, it is advisory evidence only; execution
  continues from the contract-authoritative instruction, not from a free-text
  rewritten instruction.

### 6.3 L0 Control-Plane Runtime Policy

- The repo now carries a machine-readable command-tower runtime policy at
  `policies/control_plane_runtime_policy.json`, validated by
  `schemas/control_plane_runtime_policy.v1.json`.
- This policy is the canonical repo-owned summary for:
  - L0/L1/L2 hierarchy semantics
  - long-running session defaults and degradation handling
  - event-driven wake with polling fallback
  - wave completion rules
  - completion governance (`dod_checker`, `reply_auditor`,
    `continuation_policy`)
  - harness-evolution and external-write boundaries
- `control_plane_runtime_policy.json` is a policy/read-model surface. It does
  not replace `task_contract` as execution authority.

### 6.4 Planner Artifact Hierarchy

- The planner surface now distinguishes two explicit artifact tiers:
  - `wave_plan` (`schemas/wave_plan.v1.json`) for wave-level orchestration
  - `worker_prompt_contract` (`schemas/worker_prompt_contract.v1.json`) for
    worker-scoped execution envelopes
- These planner artifacts are advisory planning surfaces that must stay aligned
  with the compiled `task_contract`; they do not supersede the execution
  contract itself.

### 6.5 Context Pack And Harness Request Contracts

- Explicit handoff and runtime-evolution surfaces now have schema-first homes:
  - `schemas/context_pack.v1.json`
  - `schemas/harness_request.v1.json`
- `context_pack` is a **fallback** protocol for pressure, contamination,
  role-switch, or phase-switch situations. It is not the default execution
  loop.
- `harness_request` represents a proposed capability change; applying that
  change still depends on policy and approval boundaries.

### 6.6 Unblock Task Contract

- `schemas/unblock_task.v1.json` defines the first-class object shape for an
  L0-managed independent temporary unblock assignment.
- `unblock_task` is derived from worker continuation policy when
  `on_blocked = spawn_independent_temporary_unblock_task`.
- Intake preview may surface `unblock_tasks`, and run-local planning artifacts
  may persist `planning_unblock_tasks.json` as an advisory planning artifact.
- `unblock_task` does not replace `task_contract` as execution authority; it is
  a read-only control-plane object for unblock coordination.

---

## 7. State Machine

### 2.3 State Machine Definition

* General rule
  * Strict one-way state machine
  * No cross-level jumps
  * Every input and output is constrained by the contract
  * Gate condition: only a diff-gate pass plus test pass may advance the state
* S0: PM Agent (requirement definition)
  * Input
    * one-sentence user request (PRD summary)
  * Output
    * TaskContract (initial version, including spec, acceptance_tests, forbidden_actions)
  * Execution mode
    * orchestration plane (no side effects), Agents SDK structured output allowed
  * Audit point
    * must be pure JSON output
    * PM Agent must not search the network on its own
    * must include executable acceptance criteria
  * Rejection
    * reject immediately if `allowed_paths` is empty or uses wildcard `**`
* S1: Tech Lead Agent (Orchestrator / Plan)
  * Input
    * PM contract + current repo baseline (commit hash)
  * Output
    * N split sub-contracts (one per worker)
  * Execution mode
    * orchestration plane (no side effects), Agents SDK structured output allowed
  * Audit point
    * lock isolation
      * `allowed_paths` between sub-contracts must not overlap unless file locking is explicitly declared
    * least privilege
      * each sub-task must calculate the minimum required `tool_permissions`
  * Rejection
    * if a sub-contract requests `danger-full-access` or another dangerous permission, the Orchestrator must block it automatically
* S2: Worker Agent (execution)
  * Input
    * sub-contract + isolated Git worktree + optional Codex `thread_id`
  * Output
    * Git commit / patch
    * `reports/task_result.json` referencing diff, command output, and evidence links
  * Execution mode
    * execution plane (side effects allowed), and it **must** use Codex MCP (or an equivalent execution plane)
  * Audit point
    * Diff Gate
      * `git diff` must remain fully contained inside `allowed_paths`
    * Event Log
      * must produce a complete `events.jsonl`
      * must record all tool invocations
  * Rejection
    * any out-of-scope file modification triggers automatic rollback and marks the task failed
* S3: Reviewer Agent (audit)
  * Input
    * patch diff (or base-branch comparison) + worker evidence
  * Output
    * structured review report (blocking and non-blocking findings)
  * Execution mode
    * orchestration plane or read-only execution plane; either way it must remain read-only and produce structured JSON
  * Audit point
    * physical isolation
      * must run under `--sandbox read-only` or use `/review`
    * zero side effects
      * worktree status after review must match the initial status exactly
  * Rejection
    * if the Reviewer produces any diff, the task becomes a system-level fault
* S4: CI / Test Runner (validation)
  * Input
    * candidate branch before merge
  * Output
    * test logs + pass/fail verdict
  * Execution mode
    * execution plane or orchestration plane, but **all command execution must be delegated by the Orchestrator** and written as evidence
  * Audit point
    * it must execute exactly the `acceptance_tests` commands declared in the contract
  * Rejection
    * failing tests must generate a new contract and enter the fix loop
* S5: Fix Loop (correction)
  * Trigger
    * blocking review or failed tests
  * Behavior
    * generate a new contract (`Parent ID = original task`)
    * reference failed evidence inside `inputs.artifacts`
  * Limit
    * retries are constrained by `max_retries`
* S6: Done (release)
  * Input
    * commit that passes all checks
  * Behavior
    * merge to the main branch
    * archive the run bundle

---

## 8. Gates And Enforcement

### 2.4 Strong-Constraint Implementation

* Overall goal
  * the system must not merely suggest compliance; it must **physically enforce** compliance
  * strong constraints come from engineering gates + contracts/protocols + physical isolation, not prompt wording
* Four pillars
  * code contracts (JSON Schema)
  * version-control gate (Git Diff Gate)
  * environment isolation (Git Worktree / sandbox)
  * immutable evidence chain (append-only JSONL logs)
* Four closed-loop dimensions
  * instruction carrier: Task Contract
  * physical constraint: sandbox + Diff Gate
  * pipeline state machine: PM -> TL -> Worker -> Reviewer -> CI/Test -> Fix loop -> Done
  * audit and replay: event sourcing + replay / comparison
* Mechanism 0: Output Schema Gate (mandatory for P0)
  * Purpose
    * ensure every structured output strictly matches its JSON Schema
  * Enforcement point
    * the Orchestrator validates immediately after the Runner returns
  * Action
    * invalid JSON or schema mismatch -> immediate fail-closed
    * record `OUTPUT_SCHEMA_ENFORCED` or `gate_failed`
* Mechanism 1: Diff Gate (hard gate - primary defense line)
  * Enforcement point
    * the Orchestrator after worker completion and before review, or a Git hook
  * Execution logic
    ```
    # 1. collect all changed files
    CHANGED_FILES=$(git diff --name-only <baseline_ref>..HEAD)

    # 2. compare against the allowed_paths whitelist in the Task Contract
    # (pseudo-code logic)
    for FILE in $CHANGED_FILES; do
      if not match_any(FILE, allowed_paths); then
        EXIT_CODE=1
        VIOLATION_FILE=$FILE
        break
      fi
    done
    ```
  * Boundary handling (mandatory for P0)
    * rename/copy: both source and destination must match `allowed_paths`
    * submodule (gitlink `160000`) is rejected by default
    * symlink changes are rejected by default, with `realpath` boundary checks against escape
    * binary patches are rejected by default unless explicitly allowed by contract
    * `allowed_paths` in P0 supports exact paths and directory prefixes only; `**` is forbidden
  * Action
    * on violation:
      * immediately execute `git reset --hard <baseline_ref>` or remove the worktree
    * record:
      * write a `policy_violation` event to the log
      * do not enter the review stage
* Mechanism 2: Reviewer Isolation
  * Purpose
    * ensure the reviewer has no ability to modify code
  * Implementation A (Codex CLI native)
    * use `/review`
    * by definition it reads diff only and reports findings without touching the worktree
  * Implementation B (sandbox enforcement)
    * MCP calls to `codex()` must inject:
      ```
      {
        "sandbox": "read-only",
        "approval-policy": "never"
      }
      ```
  * Verification
    * compare file hashes after review
    * alert if anything changed
* Mechanism 3: Tool And Command Gate
  * Goal
    * do not fully trust the agent to execute sensitive operations such as tests or network calls directly
  * Enforcement
    * Shell
      * the agent may only generate a proposed command
      * the Orchestrator validates it against the command allowlist (for example `pytest`, `npm test`) and then executes it on the agent's behalf
    * Network
      * Codex config must use `network: deny` or `network: on-request`
      * all external requests must go through approval or a controlled orchestrator environment
    * Safe execution details (P0)
      * `shell=True` is forbidden; argv only
      * if `acceptance_tests.cmd` is a string, it must be `shlex.split()`-parsed and shell metacharacters must be rejected
      * maintain `policies/command_allowlist.json` using argv prefix matching
      * every command must have a timeout; stdout and stderr must be written to artifacts
      * suggested allowlist prefixes: `pytest`, `python -m pytest`, `npm test`
* Mechanism 4: Pre-Commit / Pre-Push Hooks
  * Purpose
    * prevent local human operations or orchestrator defects from creating out-of-scope commits
  * Implementation
    * install repository Git hooks
    * read the active task contract
    * rerun the Diff Gate logic
    * if the contract is missing or validation fails, reject commit/push
* Mechanism 5: Policy Gate (least-privilege adjudication)
  * Default role permission matrix (P0, from `policies/agent_registry.json`)
    * PM: filesystem=`read-only`, shell=`never`, network=`deny`
    * Tech Lead: filesystem=`read-only`, shell=`never`, network=`deny`
    * Worker: filesystem=`workspace-write`, shell=`never`, network=`deny`
    * Reviewer: filesystem=`read-only`, shell=`never`, network=`deny`
    * Test Runner / Orchestrator: filesystem=`workspace-write`, shell=`never`, network=`deny` (command execution still goes through the command gate + `acceptance_tests` allowlist)
    * Searcher / Researcher: filesystem=`workspace-write`, shell=`never`, network=`allow` (controlled retrieval tasks only)
  * Default `forbidden_actions` denylist
    * `rm -rf`, `sudo`, `ssh`, `curl`, `wget`, and editing `.env`
    * runtime directories such as `.runtime-cache/cortexpilot/` are protected
  * `allowed_paths` breadth review
    * forbid `**`, empty arrays, `.`, and `/`
    * overly broad directories require God Mode approval
  * `mcp_tools` must remain allowlisted; unknown tools are rejected immediately

* Threat model highlights (mandatory for P0)
  * prompt injection / tool-output injection
  * symlink escape / path traversal
  * Git tricks (rename / submodule / binary)
  * secrets leakage (logs / diff / trace)
  * DoS / unbounded retries
  * corresponding defense lines: EvidenceBundle + Diff / Command / Policy Gate

---

## 9-17 Split-Volume Index

To keep the main document size under control, the following sections are split into companion volumes:


This main document keeps the authoritative index and the upstream normative rules; the split volumes carry execution details and appendix source text.
