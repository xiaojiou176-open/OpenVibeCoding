import Link from "next/link";

import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import RunList from "../../components/RunList";
import { fetchRuns } from "../../lib/api";
import { safeLoad } from "../../lib/serverPageData";

type RunsPageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

function queryValue(value: string | string[] | undefined): string {
  return Array.isArray(value) ? String(value[0] || "").trim() : String(value || "").trim();
}

export default async function RunsPage({ searchParams }: RunsPageProps) {
  const params = searchParams ? await searchParams : {};
  const statusFilter = queryValue(params.status).toUpperCase();
  const { data: runs, warning } = await safeLoad(fetchRuns, [], "Run records");
  const filteredRuns = statusFilter
    ? runs.filter((run) => String(run.status || "").toUpperCase() === statusFilter)
    : runs;
  const visibleRuns = filteredRuns.slice(0, 8);
  const failed = runs.filter((run) => String(run.status || "").toUpperCase().includes("FAIL")).length;
  const success = runs.filter((run) => ["SUCCESS", "DONE", "PASSED"].includes(String(run.status || "").toUpperCase())).length;
  const running = Math.max(runs.length - failed - success, 0);
  const failureRate = runs.length > 0 ? failed / runs.length : 0;
  const highFailureMode = failed > 0 && failureRate >= 0.5;
  const distributionHeadline = highFailureMode ? `Failed ${failed}` : `Succeeded ${success}`;
  const distributionClass = highFailureMode
    ? "metric-value--danger"
    : failed > 0
      ? "metric-value--warning"
      : "metric-value--success";
  const distributionSubline = highFailureMode
    ? `Failure-first · Succeeded ${success} · Running ${running}`
    : `Success-first · Running ${running} · Failed ${failed}`;
  const governanceHeadline = failed > 0 ? `Failed runs to triage: ${failed}` : "No failed runs in triage";
  const governanceCtaHref = failed > 0 ? "/runs?status=FAILED" : "/pm";
  const governanceCtaLabel = failed > 0 ? "Open failed-run triage" : "Create new task";
  const governanceSubline = failed > 0
    ? "Global entry: filter failed runs and handle them from one queue."
    : "Failed runs are at 0. Continue monitoring new runs.";
  return (
    <main className="grid" aria-labelledby="runs-page-title">
      <header className="app-section">
        <div className="section-header">
          <div>
            <h1 id="runs-page-title" className="page-title">Runs</h1>
            <p className="page-subtitle">Audit run batches, owners, and failure clues from one operator queue.</p>
          </div>
          <Badge>{runs.length} runs</Badge>
        </div>
      </header>
      <section className="app-section" aria-label="Run list">
        {warning ? (
          <Card variant="compact" role="status" aria-live="polite">
            <p className="ct-home-empty-text">Run list data is degraded. Showing the current available result set.</p>
            <p className="mono muted">{warning}</p>
          </Card>
        ) : null}
        <div className="stats-grid">
          <Card asChild variant="metric">
            <article>
              <p className="metric-label">Run inventory</p>
              <p className="metric-value metric-value--primary">{runs.length}</p>
              <p className="cell-sub mono muted">Total runs currently visible to the dashboard</p>
            </article>
          </Card>
          <Card asChild variant="metric">
            <article>
              <p className="metric-label">Status distribution</p>
              <p className={`metric-value ${distributionClass}`}>{distributionHeadline}</p>
              <p className="cell-sub mono muted">{distributionSubline}</p>
            </article>
          </Card>
          <Card asChild variant="metric">
            <article>
              <p className="metric-label">Failed-run triage</p>
              <p className={`metric-value ${failed > 0 ? "metric-value--warning" : "metric-value--success"}`}>{governanceHeadline}</p>
              <p className="cell-sub mono muted">{governanceSubline}</p>
              <div className="inline-stack">
                <Button asChild variant={failed > 0 ? "warning" : "secondary"}>
                  <Link href={governanceCtaHref}>{governanceCtaLabel}</Link>
                </Button>
                {failed > 0 ? (
                  <Button asChild variant="ghost">
                    <Link href="/events">View failed events</Link>
                  </Button>
                ) : null}
              </div>
            </article>
          </Card>
        </div>
        <div className="toolbar toolbar--mt" role="group" aria-label="Run status filter">
          <Button asChild variant={statusFilter === "" ? "default" : "ghost"}>
            <Link href="/runs">All</Link>
          </Button>
          <Button asChild variant={statusFilter === "FAILED" ? "warning" : "ghost"}>
            <Link href="/runs?status=FAILED">Failed</Link>
          </Button>
          <Button asChild variant={statusFilter === "RUNNING" ? "secondary" : "ghost"}>
            <Link href="/runs?status=RUNNING">Running</Link>
          </Button>
          <Button asChild variant={statusFilter === "SUCCESS" ? "secondary" : "ghost"}>
            <Link href="/runs?status=SUCCESS">Succeeded</Link>
          </Button>
        </div>
        {runs.length > visibleRuns.length ? (
          <p className="mono muted" role="status">
            The first screen is capped at the latest {visibleRuns.length} runs for quick triage.
          </p>
        ) : null}
        <RunList runs={visibleRuns} />
      </section>
    </main>
  );
}
