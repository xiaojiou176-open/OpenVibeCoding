# Agents Prompt Library

This directory is the physical isolation layer for role-specific System Prompts,
aligned with `00_SPEC` and `20_ARCHITECTURE`.
Each role maintains its own prompt so context bleed and permission drift stay
auditable.

## Directory Layout
- `pm/SYSTEM.md`
- `tech_lead/SYSTEM.md`
- `reviewer/SYSTEM.md`
- `workers/SYSTEM.md`
- `search/SYSTEM.md`

## Usage Rules
- Every System Prompt must declare: Mission, Scope, Forbidden Actions, Required Output Format, Tool Permissions, Evidence, and Fail-Closed behavior.
- Prompts constrain role behavior only; they do not replace Task Contract hard constraints.
- If roles need deeper specialization such as frontend, backend, AI, or security, extend under `workers/` with a new branch.

## Relation To `agents/codex/roles`
`agents/codex/roles/` may still serve as Codex CLI role templates.
This directory exists as the engineering-owned prompt library so the
Orchestrator and UI can load and audit role prompts directly.
