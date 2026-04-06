import Link from "next/link";
import type { BadgeVariant } from "../../components/ui/badge";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader } from "../../components/ui/card";
import { Input, Select } from "../../components/ui/input";
import { fetchTests } from "../../lib/api";
import { safeLoad } from "../../lib/serverPageData";

function statusLabelEn(status: string | undefined): string {
  const normalized = String(status || "").trim().toLowerCase();
  if (!normalized) {
    return "Unknown";
  }
  if (["success", "done", "passed", "completed", "approved"].includes(normalized)) return "Passed";
  if (["failed", "failure", "error"].includes(normalized)) return "Failed";
  if (["running", "active", "in_progress", "pending"].includes(normalized)) return "Running";
  if (["queued"].includes(normalized)) return "Queued";
  if (["blocked", "warning", "paused"].includes(normalized)) return "Blocked";
  return normalized.replace(/_/g, " ");
}

const DEFAULT_TEST_LIMIT = 10;

function statusBadgeVariant(status: string | undefined): BadgeVariant {
  const s = String(status || "").toLowerCase();
  if (["success", "done", "passed", "completed"].includes(s)) return "success";
  if (["failed", "failure", "error"].includes(s)) return "failed";
  if (["running", "active", "in_progress"].includes(s)) return "running";
  return "default";
}

function isFailedStatus(status: string | undefined): boolean {
  return ["failed", "failure", "error"].includes(String(status || "").toLowerCase());
}

function isRunningStatus(status: string | undefined): boolean {
  return ["running", "active", "in_progress", "pending"].includes(String(status || "").toLowerCase());
}

function compactSummary(summary: unknown): string {
  if (!summary || typeof summary !== "object" || Array.isArray(summary)) {
    return typeof summary === "string" && summary.trim() ? summary : "-";
  }
  const record = summary as Record<string, unknown>;
  const passed = Number(record.passed || record.pass || 0);
  const failed = Number(record.failed || record.fail || 0);
  const skipped = Number(record.skipped || 0);
  if (Number.isFinite(passed) || Number.isFinite(failed) || Number.isFinite(skipped)) {
    return `Passed ${passed || 0} / Failed ${failed || 0} / Skipped ${skipped || 0}`;
  }
  const message = [record.message, record.summary, record.result]
    .map((item) => (typeof item === "string" ? item.trim() : ""))
    .find(Boolean);
  return message || "A structured summary is available. Expand the full report for details.";
}

function compactFailure(failure: unknown): string {
  if (!failure || typeof failure !== "object" || Array.isArray(failure)) {
    return typeof failure === "string" && failure.trim() ? failure : "Unknown failure";
  }
  const record = failure as Record<string, unknown>;
  const code = typeof record.code === "string" ? record.code : "";
  const reason = [record.reason, record.message, record.detail]
    .map((item) => (typeof item === "string" ? item.trim() : ""))
    .find(Boolean);
  return [code, reason].filter(Boolean).join(" / ") || "Expand the full report for failure details.";
}

export default async function TestsPage({
  searchParams,
}: {
  searchParams?: Promise<{ q?: string; status?: string; limit?: string }>;
}) {
  const { data: tests, warning } = await safeLoad(fetchTests, [] as Record<string, unknown>[], "Test reports");
  const resolvedSearchParams = (await searchParams) || {};
  const query = String(resolvedSearchParams.q || "").trim().toLowerCase();
  const statusFilter = String(resolvedSearchParams.status || "ALL").trim().toUpperCase();
  const limitRaw = Number.parseInt(String(resolvedSearchParams.limit || DEFAULT_TEST_LIMIT), 10);
  const limit = Number.isFinite(limitRaw) && limitRaw > 0 ? limitRaw : DEFAULT_TEST_LIMIT;
  const filteredTests = tests.filter((item: Record<string, unknown>) => {
    const report = (item.report || {}) as Record<string, unknown>;
    const statusValue = String(report.status || "").trim().toUpperCase();
    if (statusFilter !== "ALL" && statusValue !== statusFilter) {
      return false;
    }
    if (!query) {
      return true;
    }
    return [item.run_id, report.status, report.finished_at, report.started_at]
      .map((value) => String(value || "").toLowerCase())
      .some((value) => value.includes(query));
  });
  const visibleTests = filteredTests.slice(0, limit);
  const statusOptions = Array.from(
    new Set(["ALL", ...tests.map((item: Record<string, unknown>) => String(((item.report || {}) as Record<string, unknown>).status || "").trim().toUpperCase()).filter(Boolean)]),
  );
  const failedTests = filteredTests.filter((item: Record<string, unknown>) =>
    isFailedStatus(String(((item.report || {}) as Record<string, unknown>).status || ""))
  ).length;
  const runningTests = filteredTests.filter((item: Record<string, unknown>) =>
    isRunningStatus(String(((item.report || {}) as Record<string, unknown>).status || ""))
  ).length;
  const passedTests = Math.max(0, filteredTests.length - failedTests - runningTests);
  const attentionTests = failedTests + runningTests;

  return (
    <main className="grid" aria-labelledby="tests-page-title">
      <header className="app-section">
        <div className="section-header">
          <div>
            <h1 id="tests-page-title" className="page-title">Tests</h1>
            <p className="page-subtitle">Triage failed and running test reports first, then inspect commands, summaries, and the full report.</p>
          </div>
          <Badge>{filteredTests.length} / {tests.length} reports</Badge>
        </div>
      </header>
      <section className="stats-grid" aria-label="Test-risk summary">
        <article className="metric-card">
          <p className="metric-label">Needs attention</p>
          <p className={`metric-value ${attentionTests > 0 ? "metric-value--warning" : "metric-value--primary"}`}>{attentionTests}</p>
          <Badge variant={attentionTests > 0 ? "warning" : "success"}>
            {attentionTests > 0 ? "Failed / running first" : "Stable right now"}
          </Badge>
        </article>
        <article className="metric-card">
          <p className="metric-label">Failed</p>
          <p className={`metric-value ${failedTests > 0 ? "metric-value--danger" : "metric-value--primary"}`}>{failedTests}</p>
          <p className="cell-sub mono muted">Counted from status=FAILED/ERROR</p>
        </article>
        <article className="metric-card">
          <p className="metric-label">Passed</p>
          <p className="metric-value">{passedTests}</p>
          <p className="cell-sub mono muted">Running {runningTests} / Total {filteredTests.length}</p>
        </article>
      </section>
      <section className="app-section" aria-label="Test-report list">
        <Card>
          <form className="toolbar" method="get">
            <label className="diff-gate-filter-field">
              <span className="muted">Search</span>
              <Input type="search" name="q" defaultValue={query} placeholder="Filter by run_id / status / time" />
            </label>
            <label className="diff-gate-filter-field">
              <span className="muted">Status</span>
              <Select name="status" defaultValue={statusFilter}>
                {statusOptions.map((option) => (
                  <option key={option} value={option}>
                    {option === "ALL" ? "All statuses" : option}
                  </option>
                ))}
              </Select>
            </label>
            <input type="hidden" name="limit" value={String(limit)} />
            <Button type="submit" variant="secondary">Apply filter</Button>
            <Button asChild variant="ghost">
              <Link href="/tests">Clear filter</Link>
            </Button>
          </form>
          <p className="mono muted">Showing {visibleTests.length} / {filteredTests.length} reports. Default first-page limit: {DEFAULT_TEST_LIMIT}.</p>
        </Card>
        {warning ? (
          <Card variant="compact" role="status" aria-live="polite">
            <p className="ct-home-empty-text">Test data is currently in degraded snapshot mode. Re-check run detail before approving any release action.</p>
            <p className="mono muted">{warning}</p>
          </Card>
        ) : null}
        {filteredTests.length === 0 ? (
          <Card>
            <div className="empty-state-stack">
              <span className="muted">No test reports yet</span>
              <span className="mono muted">{query || statusFilter !== "ALL" ? "No reports match the current filter. Adjust it and try again." : "Reports appear here after a test flow runs."}</span>
            </div>
          </Card>
        ) : (
          <div className="grid">
            {visibleTests.map((item: Record<string, unknown>) => {
              const report = (item.report || {}) as Record<string, unknown>;
              return (
                <Card key={String(item.run_id)} variant="detail">
                  <CardHeader>
                    <Link href={`/runs/${encodeURIComponent(String(item.run_id || ""))}`} className="run-link card-header-title">
                      {String(item.run_id)}
                    </Link>
                    <Badge variant={statusBadgeVariant(report.status as string)}>
                      {statusLabelEn(report.status as string)}
                    </Badge>
                  </CardHeader>
                  <CardContent>
                    <div className="data-list">
                      <div className="data-list-row">
                        <span className="data-list-label">Started at</span>
                        <span className="data-list-value mono">{String(report.started_at || "-")}</span>
                      </div>
                      <div className="data-list-row">
                        <span className="data-list-label">Finished at</span>
                        <span className="data-list-value mono">{String(report.finished_at || "-")}</span>
                      </div>
                      {report.summary ? (
                        <div className="data-list-row">
                          <span className="data-list-label">Summary</span>
                          <span className="data-list-value">{compactSummary(report.summary)}</span>
                        </div>
                      ) : null}
                      {report.failure ? (
                        <div className="data-list-row">
                          <span className="data-list-label">Failure</span>
                          <span className="data-list-value cell-danger">{compactFailure(report.failure)}</span>
                        </div>
                      ) : null}
                      {Array.isArray(report.commands) && report.commands.length > 0 ? (
                        <div className="data-list-row">
                          <span className="data-list-label">Commands</span>
                          <span className="data-list-value">
                            <span className="chip-list">
                              {(report.commands as string[]).map((cmd, i) => (
                                <span key={i} className="chip">{String(cmd)}</span>
                              ))}
                            </span>
                          </span>
                        </div>
                      ) : null}
                    </div>
                  </CardContent>
                  <details className="collapsible">
                    <summary>Full report JSON</summary>
                    <div className="collapsible-body">
                      <pre className="mono">{JSON.stringify(report, null, 2)}</pre>
                    </div>
                  </details>
                </Card>
              );
            })}
          </div>
        )}
        {filteredTests.length > limit ? (
          <Card>
            <p className="mono muted">{filteredTests.length - limit} more reports are hidden.</p>
            <div className="toolbar mt-2">
              <Button asChild variant="secondary">
                <Link href={`/tests?${new URLSearchParams({ q: query, status: statusFilter, limit: String(filteredTests.length) }).toString()}`}>
                  Show all
                </Link>
              </Button>
            </div>
          </Card>
        ) : null}
      </section>
    </main>
  );
}
