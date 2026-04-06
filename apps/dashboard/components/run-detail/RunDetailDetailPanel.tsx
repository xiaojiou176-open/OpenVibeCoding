"use client";

import { useEffect, useRef, type KeyboardEvent, type RefObject } from "react";
import ChainView from "../ChainView";
import DiffViewer from "../DiffViewer";
import { Button } from "../ui/button";
import { Select } from "../ui/input";
import { Card } from "../ui/card";
import type { EventRecord, ReportRecord, RunSummary, ToolCallRecord } from "../../lib/types";
import { toArray, toDisplayText, toObject, toStringOr } from "./runDetailHelpers";

export type RunDetailTab = "diff" | "logs" | "reports" | "chain";

type ReplayEvidence = {
  mismatched?: Array<{ key?: string; baseline?: string; current?: string }>;
  missing?: string[];
  extra?: string[];
};

type SummaryBucket = {
  group: string;
  mismatched: number;
  missing: number;
  extra: number;
};

type RunDetailDetailPanelProps = {
  tab: RunDetailTab;
  onTabChange: (next: RunDetailTab) => void;
  focusRequestKey: number;
  diff: string;
  allowedPaths: string[];
  availableRunsLoading: boolean;
  toolCallsLoading: boolean;
  chainSpecLoading: boolean;
  toolCallsError: string;
  toolCalls: ToolCallRecord[];
  toolEvents: EventRecord[];
  testReport: unknown;
  reviewReport: unknown;
  taskResult: unknown;
  workReport: unknown;
  evidenceReport: unknown;
  incidentPack: unknown;
  proofPack: unknown;
  runCompareReport: unknown;
  availableRunsError: string;
  baselineRunId: string;
  onBaselineRunIdChange: (value: string) => void;
  availableRuns: RunSummary[];
  onReplay: () => void;
  replayStatus: "idle" | "running" | "error" | "done";
  replayError: string;
  replayReport: Record<string, unknown> | undefined;
  evidence: ReplayEvidence | undefined;
  mismatched: Array<{ key?: string; baseline?: string; current?: string }>;
  missing: string[];
  extra: string[];
  summary: SummaryBucket[];
  chainSpecError: string;
  chainReport: ReportRecord["data"];
  chainSpec: Record<string, unknown> | null;
  eventsState: EventRecord[];
};

function describeReportData(data: Record<string, unknown>): string {
  const keys = Object.keys(data);
  if (keys.length === 0) {
    return "No structured fields yet.";
  }
  const previewKeys = keys.slice(0, 3).join(" / ");
  return `Fields ${keys.length}: ${previewKeys}${keys.length > 3 ? "..." : ""}`;
}

function ReportSnapshotSection({ title, data }: { title: string; data: Record<string, unknown> }) {
  const hasData = Object.keys(data).length > 0;
  return (
    <div className="run-detail-section">
      <strong>{title}</strong>
      <p className="mono muted">{describeReportData(data)}</p>
      {hasData ? (
        <details>
          <summary className="mono">Expand JSON</summary>
          <pre className="mono">{JSON.stringify(data, null, 2)}</pre>
        </details>
      ) : null}
    </div>
  );
}

export default function RunDetailDetailPanel({
  tab,
  onTabChange,
  focusRequestKey,
  diff,
  allowedPaths,
  availableRunsLoading,
  toolCallsLoading,
  chainSpecLoading,
  toolCallsError,
  toolCalls,
  toolEvents,
  testReport,
  reviewReport,
  taskResult,
  workReport,
  evidenceReport,
  incidentPack,
  proofPack,
  runCompareReport,
  availableRunsError,
  baselineRunId,
  onBaselineRunIdChange,
  availableRuns,
  onReplay,
  replayStatus,
  replayError,
  replayReport,
  evidence,
  mismatched,
  missing,
  extra,
  summary,
  chainSpecError,
  chainReport,
  chainSpec,
  eventsState,
}: RunDetailDetailPanelProps) {
  const tabOrder: RunDetailTab[] = ["diff", "logs", "reports", "chain"];
  const diffTabRef = useRef<HTMLButtonElement>(null);
  const logsTabRef = useRef<HTMLButtonElement>(null);
  const reportsTabRef = useRef<HTMLButtonElement>(null);
  const chainTabRef = useRef<HTMLButtonElement>(null);
  const tabRefs: Record<RunDetailTab, RefObject<HTMLButtonElement | null>> = {
    diff: diffTabRef,
    logs: logsTabRef,
    reports: reportsTabRef,
    chain: chainTabRef,
  };
  const activateTab = (next: RunDetailTab, moveFocus = false) => {
    onTabChange(next);
    if (moveFocus) {
      tabRefs[next].current?.focus();
    }
  };
  const moveTab = (current: RunDetailTab, direction: "next" | "prev") => {
    const currentIdx = tabOrder.indexOf(current);
    const nextIdx =
      direction === "next"
        ? (currentIdx + 1) % tabOrder.length
        : (currentIdx - 1 + tabOrder.length) % tabOrder.length;
    activateTab(tabOrder[nextIdx], true);
  };
  const handleTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>, current: RunDetailTab) => {
    if (event.key === "ArrowRight" || event.key === "ArrowDown") {
      event.preventDefault();
      moveTab(current, "next");
      return;
    }
    if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      event.preventDefault();
      moveTab(current, "prev");
      return;
    }
    if (event.key === "Home") {
      event.preventDefault();
      activateTab("diff", true);
      return;
    }
    if (event.key === "End") {
      event.preventDefault();
      activateTab("chain", true);
    }
  };

  useEffect(() => {
    if (focusRequestKey <= 0) {
      return;
    }
    const target = tabRefs[tab].current;
    if (!target) {
      return;
    }
    target.focus();
    if (typeof target.scrollIntoView === "function") {
      target.scrollIntoView({ block: "nearest", inline: "nearest" });
    }
  }, [focusRequestKey, tab]);

  return (
    <Card>
      <h3 data-testid="detail-panel-title">Detail panel</h3>
      <div className="run-detail-tab-row" role="tablist" aria-label="Detail panel tabs">
        <Button
          ref={diffTabRef}
          variant="secondary"
          id="run-detail-tab-diff"
          role="tab"
          aria-selected={tab === "diff"}
          aria-controls="run-detail-panel-diff"
          tabIndex={tab === "diff" ? 0 : -1}
          onClick={() => onTabChange("diff")}
          onKeyDown={(event) => handleTabKeyDown(event, "diff")}
        >
          Diff
        </Button>
        <Button
          ref={logsTabRef}
          variant="secondary"
          id="run-detail-tab-logs"
          role="tab"
          aria-selected={tab === "logs"}
          aria-controls="run-detail-panel-logs"
          tabIndex={tab === "logs" ? 0 : -1}
          onClick={() => onTabChange("logs")}
          onKeyDown={(event) => handleTabKeyDown(event, "logs")}
        >
          Logs
        </Button>
        <Button
          ref={reportsTabRef}
          variant="secondary"
          id="run-detail-tab-reports"
          role="tab"
          aria-selected={tab === "reports"}
          aria-controls="run-detail-panel-reports"
          tabIndex={tab === "reports" ? 0 : -1}
          data-testid="tab-reports"
          onClick={() => onTabChange("reports")}
          onKeyDown={(event) => handleTabKeyDown(event, "reports")}
        >
          Reports
        </Button>
        <Button
          ref={chainTabRef}
          variant="secondary"
          id="run-detail-tab-chain"
          role="tab"
          aria-selected={tab === "chain"}
          aria-controls="run-detail-panel-chain"
          tabIndex={tab === "chain" ? 0 : -1}
          onClick={() => onTabChange("chain")}
          onKeyDown={(event) => handleTabKeyDown(event, "chain")}
        >
          Chain
        </Button>
      </div>
      <p className="mono muted" role="status" aria-live="polite" data-testid="run-detail-active-tab-state">
        Current detail tab: {tab === "diff" ? "Diff" : tab === "logs" ? "Logs" : tab === "reports" ? "Reports" : "Chain"}
      </p>
      {tab === "diff" && (
        <div id="run-detail-panel-diff" role="tabpanel" aria-labelledby="run-detail-tab-diff">
          <DiffViewer diff={diff} allowedPaths={toArray(allowedPaths)} />
        </div>
      )}
      {tab === "logs" && (
        <div id="run-detail-panel-logs" role="tabpanel" aria-labelledby="run-detail-tab-logs">
          <strong>Tool calls (artifacts/tool_calls.jsonl)</strong>
          {toolCallsLoading ? (
            <div className="mono" role="status" aria-live="polite">
              Loading tool calls...
            </div>
          ) : toolCallsError ? (
            <div className="mono run-detail-live-error" role="alert" aria-live="assertive">
              {toolCallsError}
            </div>
          ) : null}
          {!toolCallsLoading && toolCalls.length === 0 ? (
            <div className="mono">No tool calls yet</div>
          ) : (
            <div className="grid run-detail-grid-gap">
              {toolCalls.map((call, idx) => (
                <Card key={`${String(call.tool || "unknown")}-${idx}`} className="run-detail-tool-card">
                  <div className="mono">Tool: {call.tool}</div>
                  <div className="mono">Status: {call.status}</div>
                  <div className="mono">Task ID: {toDisplayText(call.task_id)}</div>
                  <div className="mono">Duration (ms): {call.duration_ms ?? "-"}</div>
                  {call.error ? <div className="mono">Error: {call.error}</div> : null}
                  <details>
                    <summary className="mono">Expand call JSON</summary>
                    <pre className="mono">{JSON.stringify(call, null, 2)}</pre>
                  </details>
                </Card>
              ))}
            </div>
          )}
          <div className="run-detail-section">
            <strong>Tool events</strong>
            {toolEvents.length === 0 ? (
              <div className="mono">No tool events yet</div>
            ) : (
              toolEvents.map((ev, idx) => (
                <details key={`${toStringOr(ev.event, "")}-${idx}`}>
                  <summary className="mono">
                    {toDisplayText(ev.event)} @ {toDisplayText(ev.ts)}
                  </summary>
                  <pre className="mono">{JSON.stringify(toObject(ev.context), null, 2)}</pre>
                </details>
              ))
            )}
          </div>
        </div>
      )}
      {tab === "reports" && (
        <div id="run-detail-panel-reports" role="tabpanel" aria-labelledby="run-detail-tab-reports">
          <ReportSnapshotSection title="Test report" data={toObject(testReport)} />
          <ReportSnapshotSection title="Review report" data={toObject(reviewReport)} />
          <ReportSnapshotSection title="Task result" data={toObject(taskResult)} />
          <ReportSnapshotSection title="Work report" data={toObject(workReport)} />
          <ReportSnapshotSection title="Evidence report" data={toObject(evidenceReport)} />
          <ReportSnapshotSection title="Incident pack" data={toObject(incidentPack)} />
          <ReportSnapshotSection title="Proof pack" data={toObject(proofPack)} />
          <ReportSnapshotSection title="Run compare report" data={toObject(runCompareReport)} />
          <div className="run-detail-section">
            <strong data-testid="replay-controls-title">Replay controls</strong>
            {availableRunsLoading ? (
              <div className="mono" role="status" aria-live="polite">
                Loading baseline run IDs...
              </div>
            ) : null}
            {availableRunsError ? (
              <div className="mono run-detail-live-error" role="alert" aria-live="assertive">
                {availableRunsError}
              </div>
            ) : null}
            <div className="run-detail-replay-controls">
              <Select
                aria-label="Replay baseline run_id"
                value={baselineRunId}
                onChange={(event) => onBaselineRunIdChange(event.target.value)}
                className="run-detail-baseline-select"
                disabled={availableRunsLoading}
              >
                <option value="">{availableRunsLoading ? "Loading baseline run IDs..." : "Baseline run ID (current by default)"}</option>
                {availableRuns.map((item) => (
                  <option key={item.run_id} value={item.run_id}>
                    {item.run_id}
                  </option>
                ))}
              </Select>
              <Button variant="secondary" data-testid="replay-compare-button" onClick={onReplay} disabled={replayStatus === "running"}>
                Run replay comparison
              </Button>
            </div>
            {replayStatus === "running" && (
              <div className="mono" role="status" aria-live="polite">
                Replay comparison in progress...
              </div>
            )}
            {replayStatus === "error" && (
              <div className="mono run-detail-live-error" role="alert" aria-live="assertive">
                {replayError}
              </div>
            )}
          </div>
          <div className="run-detail-section">
            <strong>Replay report</strong>
            <p className="mono muted">{describeReportData(toObject(replayReport))}</p>
            {Object.keys(toObject(runCompareReport)).length > 0 ? (
              <div className="mono muted">
                Compare summary: {JSON.stringify(toObject(runCompareReport).compare_summary || {}, null, 2)}
              </div>
            ) : null}
            {Object.keys(toObject(replayReport)).length > 0 ? (
              <details>
                <summary className="mono">Expand JSON</summary>
                <pre className="mono">{JSON.stringify(toObject(replayReport), null, 2)}</pre>
              </details>
            ) : null}
          </div>
          <div className="run-detail-section">
            <strong>Evidence hash differences</strong>
            {!evidence ? (
              <div className="mono">No replay evidence hashes yet</div>
            ) : mismatched.length === 0 && missing.length === 0 && extra.length === 0 ? (
              <div className="mono">No differences</div>
            ) : (
              <div className="grid run-detail-grid-gap">
                <Card className="run-detail-summary-card">
                  <strong>Difference summary</strong>
                  <div className="grid run-detail-grid-gap">
                    {summary.map((item) => (
                      <div key={item.group} className="mono run-detail-summary-row">
                        <div className="run-detail-summary-key">{item.group}</div>
                        <div>Mismatched: {item.mismatched}</div>
                        <div>Missing: {item.missing}</div>
                        <div>Extra: {item.extra}</div>
                      </div>
                    ))}
                  </div>
                </Card>
                {mismatched.map((item, idx) => (
                  <div key={`${toStringOr(item.key, "")}-${idx}`} className="mono run-detail-evidence-card run-detail-evidence-card--mismatch">
                    <div>Key: {toStringOr(item.key, "")}</div>
                    <div>Baseline: {toStringOr(item.baseline, "")}</div>
                    <div>Current: {toStringOr(item.current, "")}</div>
                  </div>
                ))}
                {missing.map((item, idx) => (
                  <div key={`missing-${item}-${idx}`} className="mono run-detail-evidence-card run-detail-evidence-card--missing">
                    <div>Missing: {item}</div>
                  </div>
                ))}
                {extra.map((item, idx) => (
                  <div key={`extra-${item}-${idx}`} className="mono run-detail-evidence-card run-detail-evidence-card--extra">
                    <div>Extra: {item}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
      {tab === "chain" && (
        <div id="run-detail-panel-chain" role="tabpanel" aria-labelledby="run-detail-tab-chain">
          {chainSpecLoading ? (
            <div className="mono" role="status" aria-live="polite">
              Loading chain spec...
            </div>
          ) : null}
          {chainSpecError ? (
            <div className="mono run-detail-live-error" role="alert" aria-live="assertive">
              {chainSpecError}
            </div>
          ) : null}
          <ChainView chainReport={chainReport as Record<string, unknown>} chainSpec={chainSpec} events={eventsState} />
        </div>
      )}
    </Card>
  );
}
