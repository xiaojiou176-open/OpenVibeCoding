# Orchestrator Implementation Architecture

> Orchestrator is not an Agent. Treat it as the tower, referee, and judge.

---

## 1) Core Principles

1. Contract-first
2. No Direct Agent Chat
3. Side Effects Centralized
4. Two-Layer Defense
5. Evidence Append-only

---

## 2) Module Boundaries (Python)

- store/
- contracts/
- worktrees/
- adapters/
- gates/
- runner/

---

## 3) Key Interfaces

- `create_run(user_input) -> run_id`
- `enqueue(contract)`
- `claim_task(task_id) -> worktree`
- `run_worker(task_id) -> task_result`
- `run_diff_gate(task_id) -> verdict`
- `run_reviewer(task_id) -> review_report`
- `run_acceptance_tests(task_id) -> test_report`
- `apply_rollback(task_id)`
- `advance_state(task_id, from->to)`

---

## 4) Execution Routes

- Route B（P0）：`codex exec --json`
- Route A（P1）：Agents SDK + `codex mcp-server`

---

## 5) Minimal Event Fields

- `ts / level / event_type / run_id / task_id / attempt / payload`
- Optional: `event` / `context`

## 6) Atomic Writes

- `*.tmp` → `rename`
