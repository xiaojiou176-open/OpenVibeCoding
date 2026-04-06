import Link from "next/link";
import type { BadgeVariant } from "../../components/ui/badge";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader } from "../../components/ui/card";
import { Input } from "../../components/ui/input";
import { fetchReviews } from "../../lib/api";
import { safeLoad } from "../../lib/serverPageData";

const DEFAULT_REVIEW_LIMIT = 10;

function verdictLabel(verdict: string | undefined): string {
  const value = String(verdict || "").trim().toLowerCase();
  if (["pass", "passed", "success", "approved"].includes(value)) return "Passed";
  if (["fail", "failed", "rejected", "deny", "blocked"].includes(value)) return "Failed";
  if (["running", "active", "in_progress"].includes(value)) return "Running";
  if (value === "pending") return "Pending";
  return value ? value.replace(/_/g, " ") : "Unknown";
}

function isFailedVerdict(verdict: string | undefined): boolean {
  const v = String(verdict || "").toLowerCase();
  return ["fail", "failed", "rejected", "deny", "blocked"].includes(v);
}

function verdictBadgeVariant(verdict: string | undefined): BadgeVariant {
  const v = String(verdict || "").toLowerCase();
  if (["pass", "passed", "success", "approved"].includes(v)) return "success";
  if (isFailedVerdict(v)) return "failed";
  if (["running", "active", "in_progress", "pending"].includes(v)) return "running";
  return "default";
}

function summaryText(value: unknown): string {
  if (typeof value === "string" && value.trim()) {
    return value;
  }
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    const primary = [record.message, record.summary_en, record.summary_zh, record.result]
      .map((item) => (typeof item === "string" ? item.trim() : ""))
      .find(Boolean);
    return primary || "A structured summary is available. Expand the full report for details.";
  }
  return "-";
}

function scopeCheckSummary(value: unknown): string {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return "Scope check data unavailable";
  }
  const scope = value as Record<string, unknown>;
  const pass = scope.ok === true || scope.passed === true || scope.pass === true;
  const failCount = [scope.failures, scope.violations, scope.issues]
    .find((item) => Array.isArray(item));
  const count = Array.isArray(failCount) ? failCount.length : 0;
  if (pass) {
    return "Passed";
  }
  if (count > 0) {
    return `Failed (${count} issue${count === 1 ? "" : "s"})`;
  }
  return "Failed";
}

function hasScopeRisk(value: unknown): boolean {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return false;
  }
  const scope = value as Record<string, unknown>;
  if (scope.ok === false || scope.passed === false || scope.pass === false) {
    return true;
  }
  const violations = [scope.failures, scope.violations, scope.issues].find((item) => Array.isArray(item));
  return Array.isArray(violations) && violations.length > 0;
}

export default async function ReviewsPage({
  searchParams,
}: {
  searchParams?: Promise<{ q?: string; limit?: string }>;
}) {
  const { data: reviews, warning } = await safeLoad(fetchReviews, [] as Record<string, unknown>[], "Review records");
  const resolvedSearchParams = (await searchParams) || {};
  const query = String(resolvedSearchParams.q || "").trim().toLowerCase();
  const limitRaw = Number.parseInt(String(resolvedSearchParams.limit || DEFAULT_REVIEW_LIMIT), 10);
  const limit = Number.isFinite(limitRaw) && limitRaw > 0 ? limitRaw : DEFAULT_REVIEW_LIMIT;
  const filteredReviews = reviews.filter((item: Record<string, unknown>) => {
    if (!query) return true;
    const report = (item.report || {}) as Record<string, unknown>;
    return [item.run_id, report.verdict, report.summary]
      .map((value) => String(value || "").toLowerCase())
      .some((value) => value.includes(query));
  });
  const visibleReviews = filteredReviews.slice(0, limit);
  const failedReviews = filteredReviews.filter((item: Record<string, unknown>) =>
    isFailedVerdict(String(((item.report || {}) as Record<string, unknown>).verdict || ""))
  ).length;
  const scopeRiskReviews = filteredReviews.filter((item: Record<string, unknown>) =>
    hasScopeRisk(((item.report || {}) as Record<string, unknown>).scope_check)
  ).length;
  const actionRequiredReviews = failedReviews + scopeRiskReviews;
  return (
    <main className="grid" aria-labelledby="reviews-page-title">
      <header className="app-section">
        <div className="section-header">
          <div>
            <h1 id="reviews-page-title" className="page-title">Review queue</h1>
            <p className="page-subtitle">Triage failed verdicts and scope violations before drilling into evidence and the raw report.</p>
          </div>
          <Badge>{filteredReviews.length} / {reviews.length} reviews</Badge>
        </div>
      </header>
      <section className="stats-grid" aria-label="Review risk summary">
        <article className="metric-card">
          <p className="metric-label">Needs triage</p>
          <p className={`metric-value ${actionRequiredReviews > 0 ? "metric-value--warning" : "metric-value--primary"}`}>{actionRequiredReviews}</p>
          <Badge variant={actionRequiredReviews > 0 ? "warning" : "success"}>
            {actionRequiredReviews > 0 ? "Triage before release" : "No blocking items"}
          </Badge>
        </article>
        <article className="metric-card">
          <p className="metric-label">Failed verdicts</p>
          <p className={`metric-value ${failedReviews > 0 ? "metric-value--danger" : "metric-value--primary"}`}>{failedReviews}</p>
          <p className="cell-sub mono muted">Derived from verdict values such as failed or rejected</p>
        </article>
        <article className="metric-card">
          <p className="metric-label">Scope violations</p>
          <p className={`metric-value ${scopeRiskReviews > 0 ? "metric-value--warning" : "metric-value--primary"}`}>{scopeRiskReviews}</p>
          <p className="cell-sub mono muted">Includes failed scope_check results or explicit violations</p>
        </article>
      </section>
      <section className="app-section" aria-label="Review list">
        <Card>
          <form className="toolbar" method="get">
            <label className="diff-gate-filter-field">
              <span className="muted">Search</span>
              <Input
                type="search"
                name="q"
                defaultValue={query}
                placeholder="Filter by run_id / verdict / summary keyword"
              />
            </label>
            <input type="hidden" name="limit" value={String(limit)} />
            <ButtonAsSubmit />
            <Button asChild variant="ghost">
              <Link href="/reviews">Clear filters</Link>
            </Button>
          </form>
          <p className="mono muted">Showing {visibleReviews.length} / {filteredReviews.length} reviews. The default first screen is capped at {DEFAULT_REVIEW_LIMIT} rows.</p>
        </Card>
        {warning ? (
          <Card variant="compact" role="status" aria-live="polite">
            <p className="ct-home-empty-text">Review data is currently served from a degraded snapshot. Open run detail before taking governance action.</p>
            <p className="mono muted">{warning}</p>
          </Card>
        ) : null}
        {filteredReviews.length === 0 ? (
          <Card>
            <div className="empty-state-stack">
              <span className="muted">No reviews yet</span>
              <span className="mono muted">{query ? "No reviews matched this filter. Adjust the keyword and try again." : "Review artifacts will appear here after the review stage finishes."}</span>
            </div>
          </Card>
        ) : (
          <div className="grid">
            {visibleReviews.map((item: Record<string, unknown>) => {
              const report = (item.report || {}) as Record<string, unknown>;
              return (
                <Card key={String(item.run_id)} className="detail-card">
                  <CardHeader>
                    <Link href={`/runs/${encodeURIComponent(String(item.run_id || ""))}`} className="run-link card-header-title">
                      {String(item.run_id)}
                    </Link>
                    <Badge variant={verdictBadgeVariant(report.verdict as string)}>
                      {verdictLabel(report.verdict as string)}
                    </Badge>
                  </CardHeader>
                  <CardContent>
                    <div className="data-list">
                      <div className="data-list-row">
                        <span className="data-list-label">Reviewed at</span>
                        <span className="data-list-value mono">{String(report.reviewed_at || "-")}</span>
                      </div>
                      <div className="data-list-row">
                        <span className="data-list-label">Summary</span>
                        <span className="data-list-value">{summaryText(report.summary)}</span>
                      </div>
                      {report.scope_check ? (
                        <div className="data-list-row">
                          <span className="data-list-label">Scope check</span>
                          <span className="data-list-value">{scopeCheckSummary(report.scope_check)}</span>
                        </div>
                      ) : null}
                      {Array.isArray(report.evidence) && report.evidence.length > 0 ? (
                        <div className="data-list-row">
                          <span className="data-list-label">Evidence</span>
                          <span className="data-list-value">
                            <span className="chip-list">
                              {(report.evidence as string[]).map((e, i) => (
                                <span key={i} className="chip">{typeof e === "string" ? e : JSON.stringify(e)}</span>
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
        {filteredReviews.length > limit ? (
          <Card>
            <p className="mono muted">{filteredReviews.length - limit} more reviews are not expanded yet.</p>
            <div className="toolbar mt-2">
              <Link className="button button-secondary" href={`/reviews?${new URLSearchParams({ q: query, limit: String(filteredReviews.length) }).toString()}`}>
                Show all
              </Link>
            </div>
          </Card>
        ) : null}
      </section>
    </main>
  );
}

function ButtonAsSubmit() {
  return (
    <Button type="submit" variant="secondary">
      Apply filters
    </Button>
  );
}
