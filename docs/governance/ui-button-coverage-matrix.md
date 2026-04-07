# UI Button Coverage Matrix

## Purpose

`ui-button-coverage-matrix.md` is the render-only reference for UI button regression coverage.
Machine-generated and human-maintained inputs are:

- Inventory scan script: `scripts/ui_button_inventory.py`
- Matrix sync script: `scripts/sync_ui_button_matrix.py`
- Human annotation SSOT: `configs/ui_button_coverage_annotations.json`
- Artifact: `.runtime-cache/test_output/ui_regression/button_inventory.dashboard.json`
- Artifact: `.runtime-cache/test_output/ui_regression/button_inventory.desktop.json`
- Validation script: `scripts/check_ui_button_matrix_sync.py`

## Inventory JSON Field Definition

The `entries[]` schema in `button_inventory.{surface}.json` is:

| field | type | meaning |
|---|---|---|
| `id` | string | Stable button identifier (derived from surface + file + line + signature) |
| `surface` | enum | `dashboard` / `desktop` |
| `tier` | enum | `P0` / `P1` / `P2` |
| `file` | string | Source path relative to the repository root |
| `line` | number | 1-based line number |
| `tag` | string | JSX tag type (`button` / `Button` / `a` / `div` / `tr`, etc.) |
| `text` | string | Visible control text (best effort) |
| `aria_label` | string | `aria-label` value, when present |
| `data_testid` | string | `data-testid` value, when present |
| `on_click` | string | `onClick` handler signature (best effort) |
| `class_name` | string | `className` value, when present |

## Priority Tiering (P0/P1/P2)

- `P0`: high-risk actions (approve, reject, rollback, execute, send, stop, promote evidence, replay, and similar controls).
- `P1`: medium-risk actions (refresh, filter, view switching, export, copy, drawer toggles, and similar controls).
- `P2`: low-risk actions (pure navigation, non-critical expansion, and generic interaction helpers).

## Matrix Entries (P0/P1 Full)

> This file is generated output only; do not edit it manually.
> Human-maintained fields must live in `configs/ui_button_coverage_annotations.json`.
> Default policy: unannotated rows stay `TODO`; annotated rows are rendered from the annotations SSOT.
> `evidence type` must be explicit and may not be inferred from notes alone.
> `source path/source kind/source exists` are authenticity metadata; `source exists=yes` means the source path was verified during sync.

| id | surface | tier | file | action | test status | notes | evidence type | source path | source kind | source exists |
|---|---|---|---|---|---|---|---|---|---|---|
| btn-dashboard-e72b92a68a68 | dashboard | P0 | apps/dashboard/app/agents/page.tsx:519 | View failed runs in bulk | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-84e1e3a0303b | dashboard | P0 | apps/dashboard/app/locks/page.tsx:212 | Go to runs | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-aa0e4d405a16 | dashboard | P0 | apps/dashboard/app/page.tsx:399 | View all runs | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-0751a2cc97e1 | dashboard | P0 | apps/dashboard/app/pm/components/PMIntakeCenterPanel.tsx:171 | Button (`() => { if (isFirstSendReady) { onSend(); return;`) | COVERED | `apps/dashboard/tests/pm_intake_components_branches.test.tsx`（discover 阶段输入已就绪时直接触发首条需求发送） | mixed | apps/dashboard/tests/pm_intake_components_branches.test.tsx; scripts/e2e_pm_chat_command_tower_success.sh | real_playwright,unit_test | yes |
| btn-dashboard-57b043808d6e | dashboard | P0 | apps/dashboard/app/pm/components/PMIntakeCenterPanel.tsx:345 | Stop generation (`() => onStopGeneration()`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-bc8fb46f58f6 | dashboard | P0 | apps/dashboard/app/pm/components/PMIntakeCenterPanel.tsx:357 | Send (`() => onSend()`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-1a24ee250060 | dashboard | P0 | apps/dashboard/app/pm/components/PMIntakeLeftSidebar.tsx:130 | Draft session (start typing) Focuses the composer only. Sending the first request creates the formal session. (`handleDraftSessionClick`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-ce4e74573c55 | dashboard | P0 | apps/dashboard/app/pm/components/PMIntakeRightSidebar.tsx:496 | Start execution (`() => onRun()`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-705b57a4622f | dashboard | P0 | apps/dashboard/app/runs/page.tsx:85 | Button | COVERED | `apps/dashboard/tests/home_page.test.tsx`（治理 CTA 在失败态 `打开全局失败治理` 与无失败态 `发起新任务` 两条分支断言） | mixed | apps/dashboard/tests/home_page.test.tsx; scripts/e2e_dashboard_high_risk_actions_real.sh | real_playwright,unit_test | yes |
| btn-dashboard-bd7a9922f149 | dashboard | P0 | apps/dashboard/app/runs/page.tsx:89 | View failed events | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-09f789e8c654 | dashboard | P0 | apps/dashboard/app/runs/page.tsx:98 | All | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-f710b4a90de0 | dashboard | P0 | apps/dashboard/app/runs/page.tsx:101 | Failed | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-1030c5ddb0ce | dashboard | P0 | apps/dashboard/app/runs/page.tsx:104 | Running | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-cbefd14d7a48 | dashboard | P0 | apps/dashboard/app/runs/page.tsx:107 | Succeeded | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-c30a4bb53012 | dashboard | P0 | apps/dashboard/app/search/page.tsx:107 | Button (`handlePromote`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-22c59dc8ed30 | dashboard | P0 | apps/dashboard/app/workflows/WorkflowQueueMutationControls.tsx:168 | Button (`() => void handleQueueLatestRun()`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-82b252849785 | dashboard | P0 | apps/dashboard/app/workflows/WorkflowQueueMutationControls.tsx:176 | Button (`() => void handleRunNextQueue()`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-754a29e2c517 | dashboard | P0 | apps/dashboard/app/workflows/[id]/share/page.tsx:241 | Open latest run | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-336745456bd6 | dashboard | P0 | apps/dashboard/components/DiffGatePanel.tsx:346 | Approve | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-ae9db2db2e62 | dashboard | P0 | apps/dashboard/components/DiffGatePanel.tsx:349 | Reject change | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-4d435bdb23d1 | dashboard | P0 | apps/dashboard/components/DiffGatePanel.tsx:352 | Rollback run | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-e6ae160a418d | dashboard | P0 | apps/dashboard/components/DiffGatePanel.tsx:380 | Retry load (`() => void load({ forceNetwork: true`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-acfc94c64f3f | dashboard | P0 | apps/dashboard/components/DiffGatePanel.tsx:388 | Open runs list for investigation | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-6f2f6a51f5d6 | dashboard | P0 | apps/dashboard/components/DiffGatePanel.tsx:453 | Button (`() => void load({ soft: true, forceNetwork: true`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-ce0afe75ba10 | dashboard | P0 | apps/dashboard/components/DiffGatePanel.tsx:463 | Expand all ( ) (`() => { setVisibleCount(filteredItems.length); setListStatus(`Expanded all ${filteredItems.length`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-05d3bc1fafb2 | dashboard | P0 | apps/dashboard/components/DiffGatePanel.tsx:475 | Collapse to first 10 (`() => { setVisibleCount(DEFAULT_ROW_LIMIT); setListStatus(`Collapsed back to the first ${DEFAULT_ROW_LIMIT`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-684a1f37ae84 | dashboard | P0 | apps/dashboard/components/DiffGatePanel.tsx:487 | Open runs list | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-c346b771c8fd | dashboard | P0 | apps/dashboard/components/DiffGatePanel.tsx:546 | Button (`() => void toggleDiff(runId)`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-e7ce185be7e3 | dashboard | P0 | apps/dashboard/components/DiffGatePanel.tsx:556 | Rollback (`() => void handleRollback(runId)`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-11931a067db0 | dashboard | P0 | apps/dashboard/components/DiffGatePanel.tsx:567 | Reject change (`() => void handleReject(runId)`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-37327536b9d0 | dashboard | P0 | apps/dashboard/components/DiffGatePanel.tsx:620 | Collapse to first 10 (`() => setVisibleCount(DEFAULT_ROW_LIMIT)`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-85adbbd51378 | dashboard | P0 | apps/dashboard/components/DiffViewer.tsx:193 | Refresh this page (`handleRetry`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-f76ce6b00fbc | dashboard | P0 | apps/dashboard/components/DiffViewer.tsx:209 | Retry refresh (`handleRetry`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-cb30d228a1a2 | dashboard | P0 | apps/dashboard/components/GodModePanel.tsx:397 | Button (`(event) => requestApproveItem(String(item.run_id), event.currentTarget)`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-d6ba69913290 | dashboard | P0 | apps/dashboard/components/GodModePanel.tsx:426 | Button (`handleApprove`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-d99fa05ee83b | dashboard | P0 | apps/dashboard/components/GodModePanel.tsx:451 | Button (`confirmApproveItem`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-0bb0d449acbb | dashboard | P0 | apps/dashboard/components/RunList.tsx:38 | Create your first task in PM | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-9a51ea49f3ad | dashboard | P0 | apps/dashboard/components/RunList.tsx:114 | Open triage | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-218b91619ce6 | dashboard | P0 | apps/dashboard/components/command-tower/CommandTowerHomeLayout.tsx:230 | Button (`() => props.onRunQuickAction?.("live")`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-43799d0e18bf | dashboard | P0 | apps/dashboard/components/command-tower/CommandTowerSessionDrawer.tsx:183 | Jump to latest run | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-afcd85dc666d | dashboard | P0 | apps/dashboard/components/command-tower/CommandTowerSessionDrawer.tsx:221 | Button (`() => void props.handleSendMessage()`) | COVERED | `apps/dashboard/tests/command_tower_async_session.suite.tsx`（drawer 发送消息交互） | mixed | apps/dashboard/tests/command_tower_async_session.suite.tsx; scripts/e2e_dashboard_high_risk_actions_real.sh | real_playwright,component_test | yes |
| btn-dashboard-dacf3324330b | dashboard | P0 | apps/dashboard/components/command-tower/CommandTowerSessionLive.tsx:391 | Open run detail (`() => void handleOpenRunDetail()`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-1743b905fea7 | dashboard | P0 | apps/dashboard/components/command-tower/CommandTowerSessionLive.tsx:424 | Open run detail | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-ed5804bc06e8 | dashboard | P0 | apps/dashboard/components/command-tower/CommandTowerSessionLive.tsx:436 | Go to the PM session and trigger /run | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-76d73477e1fb | dashboard | P0 | apps/dashboard/components/command-tower/CommandTowerSessionLive.tsx:443 | Retry (`() => void handleOpenRunDetail()`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-76d75b2a6b17 | dashboard | P0 | apps/dashboard/components/command-tower/CommandTowerSessionLive.tsx:461 | Runs (`() => handleSessionMainTabClick("runs")`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-6222f438b650 | dashboard | P0 | apps/dashboard/components/run-detail/RunDetailDetailPanel.tsx:194 | Diff (`() => onTabChange("diff")`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-5c6aa626e891 | dashboard | P0 | apps/dashboard/components/run-detail/RunDetailDetailPanel.tsx:207 | Logs (`() => onTabChange("logs")`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-781c337007cf | dashboard | P0 | apps/dashboard/components/run-detail/RunDetailDetailPanel.tsx:220 | Reports (`() => onTabChange("reports")`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-2050e9c3e23a | dashboard | P0 | apps/dashboard/components/run-detail/RunDetailDetailPanel.tsx:234 | Chain (`() => onTabChange("chain")`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-259f58f9be93 | dashboard | P0 | apps/dashboard/components/run-detail/RunDetailDetailPanel.tsx:341 | Run replay comparison (`onReplay`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-3200d9f3343f | dashboard | P0 | apps/dashboard/components/run-detail/RunDetailStatusContractCard.tsx:117 | Button (`onToggleLive`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-15901e65ac1c | dashboard | P0 | apps/dashboard/components/run-detail/RunDetailStatusContractCard.tsx:136 | Open diagnostic report (`onOpenReports`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-47878e9d3cdb | dashboard | P0 | apps/dashboard/components/run-detail/RunDetailStatusContractCard.tsx:139 | Open execution logs (`onOpenLogs`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-fcd5ca7b5b8d | dashboard | P0 | apps/dashboard/components/run-detail/RunDetailStatusContractCard.tsx:172 | Open manual approvals | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-6daf943ceca1 | dashboard | P1 | apps/dashboard/app/agents/page.tsx:496 | Apply filter | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-e1744eb1fc69 | dashboard | P1 | apps/dashboard/app/agents/page.tsx:500 | Clear filter | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-4ebab1ed4dd0 | dashboard | P1 | apps/dashboard/app/command-tower/error.tsx:25 | Retry load (`reset`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-022f20539980 | dashboard | P1 | apps/dashboard/app/contracts/page.tsx:61 | Apply filter | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-82f43a564b45 | dashboard | P1 | apps/dashboard/app/error.tsx:25 | Retry load (`reset`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-c87834c3d7eb | dashboard | P1 | apps/dashboard/app/events/page.tsx:195 | Apply filter | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-d47c92fe1a7d | dashboard | P1 | apps/dashboard/app/events/page.tsx:196 | Clear filter | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-32eb05398ee0 | dashboard | P1 | apps/dashboard/app/locks/page.tsx:307 | Show all (`() => setVisibleCount(filteredLocks.length)`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-605787899083 | dashboard | P1 | apps/dashboard/app/pm/error.tsx:25 | Retry loading (`reset`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-465019e3806d | dashboard | P1 | apps/dashboard/app/reviews/page.tsx:147 | Clear filters | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-a6debf056dda | dashboard | P1 | apps/dashboard/app/reviews/page.tsx:238 | Apply filters | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-72a02803713e | dashboard | P1 | apps/dashboard/app/tests/page.tsx:155 | Apply filter | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-05fc70388167 | dashboard | P1 | apps/dashboard/app/tests/page.tsx:156 | Clear filter | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-5911f493d52b | dashboard | P1 | apps/dashboard/components/DashboardShellChrome.tsx:61 | Button (`() => { setLocale((previous) => { const next = toggleUiLocale(previous); persistPreferredUiLocale(next); router.refre...`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-43e59965bb9f | dashboard | P1 | apps/dashboard/components/EventTimeline.tsx:107 | Button (`() => setFilter(preset.value)`) | COVERED | `apps/dashboard/tests/event_timeline.test.tsx` (filter preset buttons) | unit_test | apps/dashboard/tests/event_timeline.test.tsx | unit_test | yes |
| btn-dashboard-694553a4e310 | dashboard | P1 | apps/dashboard/components/EventTimeline.tsx:147 | Clear filters (`() => setFilter("")`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-ef5fa7839de8 | dashboard | P1 | apps/dashboard/components/EventTimeline.tsx:163 | <span className="mono m (`() => { setSelectedSourceIdx(sourceIdx); onEventInspect?.(ev); if (onEventInspect) { setInspectNotice(`Refreshed the ...`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-2869f57bb49e | dashboard | P1 | apps/dashboard/components/EventTimeline.tsx:218 | Refresh linked execution logs (`() => { onEventInspect(selectedEvent); setInspectNotice(`Refreshed the linked execution logs for ${selectedEventName`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-80aaab90932d | dashboard | P1 | apps/dashboard/components/GodModePanel.tsx:307 | Button (`() => void loadPending({ trigger: "refresh"`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-9e960e9ecc89 | dashboard | P1 | apps/dashboard/components/command-tower/CommandTowerHomeDrawer.tsx:245 | Button (`onApplyFilters`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-f454fbd51a7f | dashboard | P1 | apps/dashboard/components/command-tower/CommandTowerHomeDrawer.tsx:254 | Button (`onResetFilters`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-75c7a062adb9 | dashboard | P1 | apps/dashboard/components/command-tower/CommandTowerHomeLayout.tsx:135 | Button (`props.toggleHighRiskFocus`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-11f6cc17c02a | dashboard | P1 | apps/dashboard/components/command-tower/CommandTowerHomeLayout.tsx:235 | Button (`props.toggleHighRiskFocus`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-854e7bd60f27 | dashboard | P1 | apps/dashboard/components/command-tower/CommandTowerHomeLayout.tsx:266 | Button (`props.resetFilters`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-8fa7ec44694f | dashboard | P1 | apps/dashboard/components/command-tower/CommandTowerSessionDrawer.tsx:88 | Button (`props.handleToggleLive`) | COVERED | `apps/dashboard/tests/command_tower_async_session.suite.tsx`（session live toggle） | component_test | apps/dashboard/tests/command_tower_async_session.suite.tsx | component_test | yes |
| btn-dashboard-7ee1d15e3d34 | dashboard | P1 | apps/dashboard/components/command-tower/CommandTowerSessionDrawer.tsx:99 | Manual refresh (`() => void props.handleManualRefresh()`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-c577de4c64a6 | dashboard | P1 | apps/dashboard/components/command-tower/CommandTowerSessionLive.tsx:369 | Refresh latest progress (`() => void handleManualRefresh()`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-9f247d1c3721 | dashboard | P1 | apps/dashboard/components/command-tower/CommandTowerSessionLive.tsx:380 | Button (`handleToggleLive`) | COVERED | `scripts/e2e_command_tower_controls_real.sh` (Session 暂停/恢复实时) | real_playwright | scripts/e2e_command_tower_controls_real.sh | real_playwright | yes |
| btn-dashboard-1b2e8b0293b2 | dashboard | P1 | apps/dashboard/components/command-tower/CommandTowerSessionLive.tsx:478 | Role flow (`() => handleSessionMainTabClick("graph")`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-a0af236fb9a3 | dashboard | P1 | apps/dashboard/components/command-tower/CommandTowerSessionLive.tsx:495 | Timeline (`() => handleSessionMainTabClick("timeline")`) | TODO | Pending test mapping |  |  |  |  |
| btn-dashboard-a48e73885017 | dashboard | P1 | apps/dashboard/components/workflows/WorkflowCaseShareActions.tsx:59 | Copy share link (`() => void copyShareLink()`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-9a21b868022d | desktop | P0 | apps/desktop/src/components/chain/NodeDetailDrawer.tsx:48 | Open diff review (`onOpenDiff`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-6828223c0bac | desktop | P0 | apps/desktop/src/components/conversation/ChatPanel.tsx:485 | Send message (`onComposerEnterSend`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-adaf450b30d3 | desktop | P0 | apps/desktop/src/components/conversation/ChatPanel.tsx:498 | Stop generation (`stopGeneration`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-4079d0fc610c | desktop | P0 | apps/desktop/src/components/review/DiffReviewModal.tsx:98 | × (`onClose`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-91fabc0723b0 | desktop | P0 | apps/desktop/src/components/review/DiffReviewModal.tsx:114 | Accept and merge (`onAccept`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-fde31493ffd3 | desktop | P0 | apps/desktop/src/components/review/DiffReviewModal.tsx:115 | Request changes (`onRework`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-ffb5408aabe4 | desktop | P0 | apps/desktop/src/lib/desktopUi.tsx:299 | View full diff (`() => reportActions?.onViewDiff?.(embed.id)`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-a88f7e08ed01 | desktop | P0 | apps/desktop/src/pages/CTSessionDetailPage.tsx:482 | Button (`handleSend`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-9fe2e2dc3a41 | desktop | P0 | apps/desktop/src/pages/ChangeGatesPage.tsx:86 | Button (`() => loadDiff(runId)`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-94724af6495f | desktop | P0 | apps/desktop/src/pages/ChangeGatesPage.tsx:89 | Rollback (`() => handleAction(runId, "rollback")`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-a9647c780426 | desktop | P0 | apps/desktop/src/pages/ChangeGatesPage.tsx:90 | Reject change (`() => handleAction(runId, "reject")`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-9cb742e43036 | desktop | P0 | apps/desktop/src/pages/CommandTowerPage.tsx:494 | {opt.value === "all" && } {opt.value === "high_risk" && } {opt.value === "blocked" && } {opt.value === "running" && } (`() => setFocusMode(opt.value)`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-ec99e080c351 | desktop | P0 | apps/desktop/src/pages/GodModePage.tsx:233 | Button (`() => openConfirmDialog(runId)`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-4125529b5827 | desktop | P0 | apps/desktop/src/pages/GodModePage.tsx:262 | Button (`handleManualApprove`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-05478759b240 | desktop | P0 | apps/desktop/src/pages/GodModePage.tsx:290 | Button (`() => handleApprove(confirmRunId)`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-64e767087f61 | desktop | P0 | apps/desktop/src/pages/OverviewPage.tsx:235 | Button (`() => onNavigate("runs")`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-58c1e0cb3ad9 | desktop | P0 | apps/desktop/src/pages/OverviewPage.tsx:249 | Button (`() => onNavigateToRun(run.run_id)`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-c5be35312e10 | desktop | P0 | apps/desktop/src/pages/OverviewPage.tsx:296 | Button (`() => onNavigateToRun(entry.runId)`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-ca6302ae539f | desktop | P0 | apps/desktop/src/pages/RunComparePage.tsx:91 | Back (`onBack`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-5e68b4638a6e | desktop | P0 | apps/desktop/src/pages/RunComparePage.tsx:96 | Back to run detail (`onBack`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-1fc003fec67a | desktop | P0 | apps/desktop/src/pages/RunDetailPage.tsx:341 | Button (`() => void load()`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-d34f9eaedcf2 | desktop | P0 | apps/desktop/src/pages/RunDetailPage.tsx:342 | Button (`onBack`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-0c6fd4daeff9 | desktop | P0 | apps/desktop/src/pages/RunDetailPage.tsx:352 | Button (`() => void load()`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-fd735710beff | desktop | P0 | apps/desktop/src/pages/RunDetailPage.tsx:353 | Button (`onBack`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-e0d11350db7c | desktop | P0 | apps/desktop/src/pages/RunDetailPage.tsx:412 | Button (`onBack`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-dea3d13bc103 | desktop | P0 | apps/desktop/src/pages/RunDetailPage.tsx:418 | Button (`() => setLiveEnabled(p => !p)`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-6ec4f272a6ad | desktop | P0 | apps/desktop/src/pages/RunDetailPage.tsx:499 | Button (`() => void load()`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-a8a82130a8aa | desktop | P0 | apps/desktop/src/pages/RunDetailPage.tsx:544 | Button (`() => void load()`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-23d1b14efb1d | desktop | P0 | apps/desktop/src/pages/RunDetailPage.tsx:548 | Button (`() => handleAction("promote")`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-ffb241c06bce | desktop | P0 | apps/desktop/src/pages/RunDetailPage.tsx:556 | Button (`() => handleAction("rollback")`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-06e08ce41b8e | desktop | P0 | apps/desktop/src/pages/RunDetailPage.tsx:557 | Button (`() => handleAction("reject")`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-228017131f69 | desktop | P0 | apps/desktop/src/pages/RunDetailPage.tsx:558 | Button (`load`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-b4d37b3bf071 | desktop | P0 | apps/desktop/src/pages/RunDetailPage.tsx:564 | Button (`() => setActiveTab(tab.key)`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-6d8e670816f8 | desktop | P0 | apps/desktop/src/pages/RunDetailPage.tsx:577 | Button (`() => void load()`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-89d9ed8a0cc8 | desktop | P0 | apps/desktop/src/pages/RunDetailPage.tsx:591 | Button (`() => toggleExpandedEvent(i)`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-2a92aff78f62 | desktop | P0 | apps/desktop/src/pages/RunDetailPage.tsx:627 | Button (`() => void load()`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-72575d8e3c01 | desktop | P0 | apps/desktop/src/pages/RunDetailPage.tsx:628 | Button (`() => setActiveTab("events")`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-963e98b8a362 | desktop | P0 | apps/desktop/src/pages/RunDetailPage.tsx:650 | Button (`() => void load()`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-fd89eefbedf9 | desktop | P0 | apps/desktop/src/pages/RunDetailPage.tsx:672 | Button (`() => void load()`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-023753c3b783 | desktop | P0 | apps/desktop/src/pages/RunDetailPage.tsx:715 | Button (`() => void load()`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-47fc8349d0a2 | desktop | P0 | apps/desktop/src/pages/RunDetailPage.tsx:730 | Button (`() => void load()`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-12f12609c0bd | desktop | P0 | apps/desktop/src/pages/RunDetailPage.tsx:751 | Button (`() => handleAction("replay")`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-ad97eef4846c | desktop | P0 | apps/desktop/src/pages/RunDetailPage.tsx:795 | Button (`onOpenCompare`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-6688e04822a0 | desktop | P0 | apps/desktop/src/pages/RunsPage.tsx:54 | Refresh (`load`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-ec445f782463 | desktop | P0 | apps/desktop/src/pages/RunsPage.tsx:92 | Button (`() => onNavigateToRun(run.run_id)`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-f1c8ace8cf76 | desktop | P0 | apps/desktop/src/pages/SearchPage.tsx:105 | Promote to EvidenceBundle (`handlePromote`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-b1036f47a77c | desktop | P0 | apps/desktop/src/pages/WorkflowDetailPage.tsx:153 | Button (`() => void handleQueueLatestRun()`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-5bb2f78ee0f5 | desktop | P0 | apps/desktop/src/pages/WorkflowDetailPage.tsx:154 | Button (`() => void handleRunNextQueue()`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-c2d8eae2216f | desktop | P0 | apps/desktop/src/pages/WorkflowDetailPage.tsx:228 | Button (`() => onNavigateToRun(r.run_id)`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-bcf160d1dfe3 | desktop | P0 | apps/desktop/src/pages/WorkflowsPage.tsx:67 | Button (`() => void handleRunNextQueue()`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-03cd05daf6a6 | desktop | P1 | apps/desktop/src/App.tsx:787 | Button (`() => { setUiLocale((previous) => { const next = toggleUiLocale(previous); persistPreferredUiLocale(next); return next;`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-98c57c960d8a | desktop | P1 | apps/desktop/src/components/chain/NodeDetailDrawer.tsx:45 | Button (`onToggleRaw`) | COVERED | `apps/desktop/src/pages/desktop_p1_controls.test.tsx` + `apps/desktop/src/App.test.tsx` | unit_test | apps/desktop/src/pages/desktop_p1_controls.test.tsx; apps/desktop/src/App.test.tsx | unit_test | yes |
| btn-desktop-70d50c26f366 | desktop | P1 | apps/desktop/src/components/conversation/ChatPanel.tsx:287 | Refresh now (`() => refreshNow()`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-cce4528a6f6d | desktop | P1 | apps/desktop/src/pages/CTSessionDetailPage.tsx:350 | Button (`() => setLiveEnabled((p) => !p)`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-ab7b2f366eab | desktop | P1 | apps/desktop/src/pages/CTSessionDetailPage.tsx:351 | Refresh now (`() => void refreshAll()`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-8f8b537fedcd | desktop | P1 | apps/desktop/src/pages/ChangeGatesPage.tsx:45 | Refresh (`load`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-17285ab7497c | desktop | P1 | apps/desktop/src/pages/CommandTowerPage.tsx:405 | Button (`refreshNow`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-a6685d58cfef | desktop | P1 | apps/desktop/src/pages/CommandTowerPage.tsx:408 | Button (`() => setLiveEnabled((p) => !p)`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-a564bdc75dff | desktop | P1 | apps/desktop/src/pages/CommandTowerPage.tsx:485 | Button (`applyFilters`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-0e513ea1f298 | desktop | P1 | apps/desktop/src/pages/CommandTowerPage.tsx:486 | Button (`resetFilters`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-ed5032000f2f | desktop | P1 | apps/desktop/src/pages/CommandTowerPage.tsx:523 | Button (`refreshNow`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-dcd1a1a6468d | desktop | P1 | apps/desktop/src/pages/CommandTowerPage.tsx:526 | Button (`() => setLiveEnabled(false)`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-3378d622ef9a | desktop | P1 | apps/desktop/src/pages/CommandTowerPage.tsx:534 | Button (`resetFilters`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-1027a5d86943 | desktop | P1 | apps/desktop/src/pages/CommandTowerPage.tsx:557 | Button (`refreshNow`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-6c1bbf9edfaf | desktop | P1 | apps/desktop/src/pages/CommandTowerPage.tsx:560 | Button (`() => { setFocusMode("all"); resetFilters();`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-1ce62f0c4ff4 | desktop | P1 | apps/desktop/src/pages/CommandTowerPage.tsx:654 | Alt+Shift+R (`refreshNow`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-0d902621b5f8 | desktop | P1 | apps/desktop/src/pages/CommandTowerPage.tsx:655 | Alt+Shift+L (`() => setLiveEnabled((p) => !p)`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-123b9b1bc126 | desktop | P1 | apps/desktop/src/pages/CommandTowerPage.tsx:656 | Alt+Shift+E (`exportFailedSessions`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-66d5d9677153 | desktop | P1 | apps/desktop/src/pages/CommandTowerPage.tsx:657 | Alt+Shift+C (`() => void copyCurrentViewLink()`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-e9f4c947fc9b | desktop | P1 | apps/desktop/src/pages/CommandTowerPage.tsx:708 | Button (`refreshNow`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-3c36a3a681c7 | desktop | P1 | apps/desktop/src/pages/ContractsPage.tsx:25 | Refresh (`load`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-d2e26ec72426 | desktop | P1 | apps/desktop/src/pages/EventsPage.tsx:32 | Refresh (`load`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-dfe65f3bfdfe | desktop | P1 | apps/desktop/src/pages/EventsPage.tsx:49 | Button (`() => toggleExpanded(i)`) | COVERED | `apps/desktop/src/pages/EventsPage.test.tsx`（row toggle 展开/收起详情） | unit_test | apps/desktop/src/pages/EventsPage.test.tsx | unit_test | yes |
| btn-desktop-b5a1cb9a57f9 | desktop | P1 | apps/desktop/src/pages/LocksPage.tsx:20 | Refresh (`load`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-aaaae3b65369 | desktop | P1 | apps/desktop/src/pages/TestsPage.tsx:22 | Refresh (`load`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-d6a1b0bbd5ba | desktop | P1 | apps/desktop/src/pages/WorkflowsPage.tsx:66 | Refresh (`load`) | TODO | Pending test mapping |  |  |  |  |
| btn-desktop-2d20e437f143 | desktop | P1 | apps/desktop/src/pages/WorktreesPage.tsx:21 | Refresh (`load`) | TODO | Pending test mapping |  |  |  |  |

_generated_at: 2026-04-07T07:50:22Z_


## Update Workflow

1. Refresh the button inventory:

```bash
python3 scripts/ui_button_inventory.py --surface all
```

2. Sync the full matrix (default `P0,P1`):

```bash
python3 scripts/sync_ui_button_matrix.py --tiers P0,P1
```

3. Update the human annotation SSOT (`configs/ui_button_coverage_annotations.json`):

```json
{
  "rows": {
    "btn-dashboard-xxxx": {
      "status": "COVERED",
      "notes": "evidence summary",
      "evidence_type": "mixed",
      "source_path": "apps/dashboard/tests/example.test.tsx; scripts/e2e_dashboard_high_risk_actions_real.sh",
      "source_kind": "unit_test,real_playwright"
    }
  }
}
```

4. Validate the full matrix gate (structure + authenticity):

```bash
python3 scripts/check_ui_button_matrix_sync.py --required-tiers P0,P1 --fail-on-stale
```

5. Incremental mode (for development-time spot checks only):

```bash
python3 scripts/check_ui_button_matrix_sync.py --required-tiers P0,P1 --base-ref HEAD
```
