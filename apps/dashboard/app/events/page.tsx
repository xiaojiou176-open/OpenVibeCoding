import Link from "next/link";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import { Input, Select } from "../../components/ui/input";
import { fetchAllEvents } from "../../lib/api";
import { safeLoad } from "../../lib/serverPageData";

type EventsPageProps = {
  searchParams?: Promise<{ q?: string; risk?: string; category?: string }>;
};

type EventRisk = "HIGH" | "NORMAL";
type EventCategory = "FAILURE" | "SECURITY" | "APPROVAL" | "ORCHESTRATION";

type ClassifiedEvent = {
  record: Record<string, unknown>;
  idx: number;
  eventName: string;
  runId: string;
  ts: string;
  risk: EventRisk;
  riskLabel: string;
  category: EventCategory;
  categoryLabel: string;
};

const HIGH_RISK_TOKENS = [
  "FAIL",
  "ERROR",
  "TIMEOUT",
  "REJECT",
  "DENY",
  "ROLLBACK",
  "ABORT",
  "BLOCK",
  "PANIC",
  "SECURITY",
  "BREACH",
  "LOCK",
];

const SECURITY_TOKENS = ["SECURITY", "AUTH", "TOKEN", "PERMISSION", "DENY", "FORBIDDEN", "CREDENTIAL"];
const APPROVAL_TOKENS = ["APPROVAL", "APPROVE", "REVIEW", "AUDIT", "GOD_MODE", "DIFF_GATE", "LOCK"];
const FAILURE_TOKENS = ["FAIL", "ERROR", "TIMEOUT", "ROLLBACK", "REJECT", "ABORT", "CANCEL", "RETRY"];

function readQueryValue(value: string | undefined): string {
  return String(value || "").trim();
}

function normalizeTokenSource(eventName: string, event: Record<string, unknown>): string {
  const extras = [event.level, event.severity, event.status, event.stage, event.source]
    .map((value) => String(value || "").trim().toUpperCase())
    .filter(Boolean);
  return [eventName.toUpperCase(), ...extras].join(" ");
}

function classifyEvent(eventName: string, event: Record<string, unknown>): Omit<ClassifiedEvent, "record" | "idx" | "runId" | "ts" | "eventName"> {
  const tokenSource = normalizeTokenSource(eventName, event);
  const risk: EventRisk = HIGH_RISK_TOKENS.some((token) => tokenSource.includes(token)) ? "HIGH" : "NORMAL";
  let category: EventCategory = "ORCHESTRATION";
  if (SECURITY_TOKENS.some((token) => tokenSource.includes(token))) {
    category = "SECURITY";
  } else if (FAILURE_TOKENS.some((token) => tokenSource.includes(token))) {
    category = "FAILURE";
  } else if (APPROVAL_TOKENS.some((token) => tokenSource.includes(token))) {
    category = "APPROVAL";
  }
  const categoryLabel =
    category === "SECURITY"
      ? "Security & access"
      : category === "FAILURE"
        ? "Failures & rollback"
        : category === "APPROVAL"
          ? "Approvals & review"
          : "Runtime orchestration";
  return {
    risk,
    riskLabel: risk === "HIGH" ? "High risk" : "Normal",
    category,
    categoryLabel,
  };
}

function includesQuery(item: ClassifiedEvent, query: string): boolean {
  if (!query) {
    return true;
  }
  const normalized = query.toLowerCase();
  const hints = [
    item.eventName,
    item.runId,
    item.ts,
    item.riskLabel,
    item.categoryLabel,
    item.record.stage,
    item.record.status,
    item.record.message,
    item.record.source,
  ];
  return hints.some((value) => String(value || "").toLowerCase().includes(normalized));
}

export default async function EventsPage({ searchParams }: EventsPageProps = {}) {
  const { data: events, warning } = await safeLoad(fetchAllEvents, [] as Record<string, unknown>[], "Event stream");
  const resolvedSearchParams = (await searchParams) || {};
  const query = readQueryValue(resolvedSearchParams.q);
  const riskFilterRaw = readQueryValue(resolvedSearchParams.risk).toUpperCase();
  const riskFilter = riskFilterRaw === "HIGH" || riskFilterRaw === "NORMAL" ? riskFilterRaw : "ALL";
  const categoryFilterRaw = readQueryValue(resolvedSearchParams.category).toUpperCase();
  const categoryFilter = ["FAILURE", "SECURITY", "APPROVAL", "ORCHESTRATION"].includes(categoryFilterRaw)
    ? categoryFilterRaw
    : "ALL";
  const normalizedEvents: ClassifiedEvent[] = events.map((event: Record<string, unknown>, idx: number) => {
    const eventName = String(event.event || event.event_type || "event");
    const runId = String(event._run_id || event.run_id || "-").trim();
    const ts = String(event.ts || event.timestamp || event.created_at || "-");
    return {
      record: event,
      idx,
      eventName,
      runId,
      ts,
      ...classifyEvent(eventName, event),
    };
  });
  const filteredEvents = normalizedEvents.filter((item) => {
    if (riskFilter !== "ALL" && item.risk !== riskFilter) {
      return false;
    }
    if (categoryFilter !== "ALL" && item.category !== categoryFilter) {
      return false;
    }
    return includesQuery(item, query);
  });
  const totalHighRisk = normalizedEvents.filter((item) => item.risk === "HIGH").length;
  const filteredHighRisk = filteredEvents.filter((item) => item.risk === "HIGH").length;
  const hasFilter = Boolean(query || riskFilter !== "ALL" || categoryFilter !== "ALL");

  return (
    <main className="grid" aria-labelledby="events-page-title">
      <header className="app-section">
        <div className="section-header">
          <div>
            <h1 id="events-page-title" className="page-title">Event stream</h1>
            <p className="page-subtitle">Triage high-risk events first, then review run context and the raw payload.</p>
          </div>
          <Badge>{filteredEvents.length} / {events.length} events</Badge>
        </div>
      </header>
      <section className="stats-grid" aria-label="Event-risk summary">
        <article className="metric-card">
          <p className="metric-label">High-risk events (total)</p>
          <p className={`metric-value ${totalHighRisk > 0 ? "metric-value--danger" : "metric-value--primary"}`}>{totalHighRisk}</p>
          <Badge variant={totalHighRisk > 0 ? "failed" : "success"}>
            {totalHighRisk > 0 ? "Needs triage first" : "No high-risk events"}
          </Badge>
        </article>
        <article className="metric-card">
          <p className="metric-label">Current filter hits</p>
          <p className={`metric-value ${filteredHighRisk > 0 ? "metric-value--warning" : "metric-value--primary"}`}>{filteredEvents.length}</p>
          <p className="cell-sub mono muted">High risk within filter: {filteredHighRisk}</p>
        </article>
        <article className="metric-card">
          <p className="metric-label">Filter mode</p>
          <p className="metric-value">{hasFilter ? "Enabled" : "All events"}</p>
          <p className="cell-sub mono muted">Supports keyword + risk + semantic category</p>
        </article>
      </section>
      <section className="app-section" aria-label="Event list">
        <Card>
          <form className="toolbar" method="get" data-testid="events-filter-form">
            <label className="diff-gate-filter-field">
              <span className="muted">Keyword</span>
              <Input type="search" name="q" defaultValue={query} placeholder="Filter by event / run_id / stage / time" />
            </label>
            <label className="diff-gate-filter-field">
              <span className="muted">Risk</span>
              <Select name="risk" defaultValue={riskFilter}>
                <option value="ALL">All</option>
                <option value="HIGH">High risk</option>
                <option value="NORMAL">Normal</option>
              </Select>
            </label>
            <label className="diff-gate-filter-field">
              <span className="muted">Category</span>
              <Select name="category" defaultValue={categoryFilter}>
                <option value="ALL">All</option>
                <option value="FAILURE">Failures & rollback</option>
                <option value="SECURITY">Security & access</option>
                <option value="APPROVAL">Approvals & review</option>
                <option value="ORCHESTRATION">Runtime orchestration</option>
              </Select>
            </label>
            <Button type="submit" variant="secondary">Apply filter</Button>
            <Button asChild variant="ghost">
              <Link href="/events">Clear filter</Link>
            </Button>
          </form>
          <p className="mono muted">High-risk classification covers FAIL / ERROR / TIMEOUT / ROLLBACK / SECURITY / LOCK tokens.</p>
        </Card>
        {warning ? (
          <Card variant="compact" role="status" aria-live="polite">
            <p className="ct-home-empty-text">The event stream is currently in degraded snapshot mode. Re-check run detail before approval or rollback.</p>
            <p className="mono muted">{warning}</p>
          </Card>
        ) : null}
        {filteredEvents.length === 0 ? (
          <Card>
            <div className="empty-state-stack">
              <span className="muted">No events yet</span>
              <span className="mono muted">{hasFilter ? "No events match the current filter. Widen the filter and try again." : "Runtime events will appear here."}</span>
            </div>
          </Card>
        ) : (
          <Card variant="table">
            <table className="run-table">
              <caption className="sr-only">Event list</caption>
              <thead>
                <tr>
                  <th scope="col">Event</th>
                  <th scope="col">Risk</th>
                  <th scope="col">Category</th>
                  <th scope="col">Run ID</th>
                  <th scope="col">Timestamp</th>
                  <th scope="col">Payload</th>
                </tr>
              </thead>
              <tbody>
                {filteredEvents.map((item) => {
                  const runId = item.runId;
                  const hasRunId = runId.length > 0 && runId !== "-";
                  const encodedRunId = hasRunId ? encodeURIComponent(runId) : "";
                  return (
                    <tr key={`${item.eventName}-${item.idx}`}>
                      <td>
                        <Badge variant={item.risk === "HIGH" ? "failed" : "running"}>{item.eventName}</Badge>
                      </td>
                      <td>
                        <Badge variant={item.risk === "HIGH" ? "failed" : "success"}>{item.riskLabel}</Badge>
                      </td>
                      <td>
                        <Badge variant={item.category === "ORCHESTRATION" ? "default" : "warning"}>
                          {item.categoryLabel}
                        </Badge>
                      </td>
                      <td>
                        {hasRunId ? (
                          <Link
                            href={`/runs/${encodedRunId}`}
                            className="run-link"
                            title={runId}
                            data-run-id={runId}
                            data-testid={`events-run-link-${item.idx}`}
                          >
                            {runId.length > 12 ? `${runId.slice(0, 12)}...` : runId}
                          </Link>
                        ) : (
                          <span className="muted">-</span>
                        )}
                      </td>
                      <td><span className="mono muted">{item.ts}</span></td>
                      <td>
                        <details className="collapsible">
                          <summary>View payload</summary>
                          <div className="collapsible-body">
                            <pre className="mono">{JSON.stringify(item.record, null, 2)}</pre>
                          </div>
                        </details>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </Card>
        )}
      </section>
    </main>
  );
}
