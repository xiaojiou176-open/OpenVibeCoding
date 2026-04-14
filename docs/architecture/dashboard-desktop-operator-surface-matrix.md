# Dashboard vs Desktop Operator Surface Matrix

Date: 2026-03-31 (America/Los_Angeles)

This matrix is intentionally **high-value only**. It is not a button-by-button parity audit.
The goal is to help the next prompts choose the best web follow-up slices without reopening discovery.

## Summary

| Capability | Dashboard (web) | Desktop | Verdict | Prompt Priority | Evidence |
|:--|:--|:--|:--|:--|:--|
| PM intake + run creation | Present | Present | Aligned | Keep steady | `apps/dashboard/app/pm/*`, `apps/desktop/src/components/conversation/ChatPanel.tsx` |
| Flight Plan preview | Present as sign-off checklist | Present as compact checklist preview | Web is still stronger, but checklist parity is now visible on both surfaces | Prompt 3 | dashboard PM sidebar + desktop ChatPanel preview |
| Command Tower monitoring | Present | Present | Aligned, different emphasis | Keep steady | `apps/dashboard/app/command-tower/page.tsx`, `apps/desktop/src/pages/CommandTowerPage.tsx` |
| Workflow Case list/detail visibility | Present, with next-action framing and queue actions on the web detail path | Present, stronger execution flow remains | High-value parity improved; desktop still has stronger shell continuity | Prompt 3 polish | `apps/dashboard/app/page.tsx`, `apps/dashboard/app/workflows/*.tsx`, `apps/desktop/src/pages/WorkflowsPage.tsx`, `apps/desktop/src/pages/WorkflowDetailPage.tsx` |
| Queue read visibility | Present | Present | Aligned | Keep steady | dashboard + desktop workflow pages read queue state |
| Queue mutation (`run next`, `enqueue`) | API + UI now present on workflow list/detail | UI present with buttons/inputs | Core operator gap closed; web now supports the main queue path | Prompt 3 polish | `apps/dashboard/lib/api.ts`, `apps/dashboard/app/workflows/*.tsx`, `apps/desktop/src/lib/api.ts`, desktop workflow controls |
| Run compare surface | Present as decision-first compare page with summary, deltas, and next step | Present with decision summary + action context | Decision baseline landed on both surfaces | Prompt 4 polish | dashboard run compare page + desktop run compare page |
| Proof / Incident action surface | Run Detail now exposes compare / proof / incident cards before deep-dive tabs | Run Detail replay area now exposes compare decision + action context | Baseline decision surface landed; dashboard still richer | Prompt 4 | `apps/dashboard/app/runs/[id]/page.tsx`, `apps/desktop/src/pages/RunDetailPage.tsx` |
| AI operator copilot brief | Present on dashboard Run Detail, Run Compare, Workflow Case detail, and Flight Plan preview as bounded explain-only panels | Present on desktop Run Detail, Run Compare, Workflow Detail, and Flight Plan preview as compact parity | Prompt 7 closes the highest-value parity gap without creating a second truth pipeline | Prompt 7 | dashboard + desktop copilot panels and surfaces |
| Read-only MCP access | Repo-local `mcp-readonly-server` now exposes run/workflow/queue/approval/diff-gate/compare/proof/incident reads | No dedicated desktop shell entry; desktop consumes the same backend truth through UI APIs | Prompt 4 now has an agent-facing read node without changing desktop surface parity goals | Prompt 5 | `apps/orchestrator/src/openvibecoding_orch/mcp_readonly_server.py`, `services/control_plane_read_service.py` |
| Degraded/error/operator messaging | Run Detail, Workflow Detail, and Command Tower now share more explicit control-plane guidance | Desktop still relies more on local page wording | Cross-surface baseline started; desktop still needs copy consolidation | Prompt 4 | workflow pages, run detail, command tower |
| Public task-pack front door | Prompt 1 now shows all three tracked public cases on the web front door | Desktop remains operator-shell-first | Web is the primary landing surface and now carries the baseline | Prompt 2 polish later | `contracts/packs/*.json`, `apps/dashboard/app/page.tsx` |

## Fresh Findings

### Already aligned enough

- Both surfaces speak the same core product nouns around `Command Tower`, runs, events, contracts, reviews, and tests.
- Both surfaces already consume queue APIs and workflow APIs.
- Both surfaces already expose replay/compare-style run analysis.

### Desktop is still stronger today

- Desktop still keeps queue actions closer to a shell-like operator flow, while web has only just gained the core mutations.
- Desktop workflow detail still feels more execution-first in one view.
- Desktop keeps a more compact PM/chat/operator loop for first-run guidance.

### Web / cross-surface gaps after Prompt 3

- Dashboard has the strongest decision surface right now; desktop still needs deeper compare/proof/incident readability.
- Reliability language is more consistent than before, but it is not yet copied through every high-value operator page.
- Flight Plan, Compare, Proof, and Incident now feel related, but Prompt 4 still needs to bind them into a tighter operator loop.

### Prompt-4 outcome

- Dashboard Run Detail is now the primary AI operator copilot launcher.
- Dashboard Run Compare now reuses the same bounded brief, so delta review and next-step explanation live on the same run-scoped truth chain.
- The repo now ships a read-only MCP server entry, so Prompt 4 no longer depends only on UI surfaces to expose OpenVibeCoding state outward.

### Prompt-7 outcome

- Dashboard now extends the same bounded brief shell to Workflow Case detail and the Flight Plan pre-run preview.
- Desktop now exposes compact copilot parity on Run Detail, Run Compare, Workflow Detail, and the Flight Plan preview.
- The parity move is still bounded and explain-only; it does not introduce write actions or a second truth source.

## Prompt-7 Recommendations

1. Keep workflow-scoped and Flight Plan-scoped copilot explain-only until Prompt 8 explicitly reopens riskier action semantics.
2. Treat the new public case gallery baseline as a packaging layer, not as a fake showcase data system.
3. Keep reliability rollout focused on high-value trust surfaces instead of turning Prompt 7 into a full copy rewrite.
4. Leave write-capable MCP and hosted operator evaluation to Prompt 8 only.

## Negative Search Evidence

- Prompt 1 baseline lacked dashboard workflow detail controls for `enqueueRunQueue` / `runNextQueue`; Prompt 2 closed that gap on the web surface.
- The old dashboard-only note that queue mutations lived in desktop/CLI is no longer the current repo truth after Prompt 2.
- No full desktop-dashboard 1:1 parity contract was found; the repo continues to present them as aligned operator surfaces with different strengths.
