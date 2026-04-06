import Link from "next/link";
import CommandTowerSessionLive from "../../../../components/command-tower/CommandTowerSessionLive";
import { Badge } from "../../../../components/ui/badge";
import { Button } from "../../../../components/ui/button";
import {
  fetchPmSession,
  fetchPmSessionConversationGraph,
  fetchPmSessionEvents,
  fetchPmSessionMetrics,
} from "../../../../lib/api";
import type {
  EventRecord,
  PmSessionConversationGraphPayload,
  PmSessionDetailPayload,
  PmSessionMetricsPayload,
} from "../../../../lib/types";
import { safeLoad } from "../../../../lib/serverPageData";

function toEventTimestampMs(event: EventRecord): number {
  const raw = event.ts;
  if (typeof raw === "number" && Number.isFinite(raw)) return raw;
  if (typeof raw === "string") {
    const numeric = Number(raw);
    if (Number.isFinite(numeric)) return numeric;
    const parsed = Date.parse(raw);
    return Number.isNaN(parsed) ? 0 : parsed;
  }
  return 0;
}

type CommandTowerSessionPageParams = {
  id: string;
};

export default async function CommandTowerSessionPage({
  params,
}: {
  params: Promise<CommandTowerSessionPageParams>;
}) {
  const { id } = await params;
  const fallbackDetail: PmSessionDetailPayload = {
    session: {
      pm_session_id: id,
      status: "active",
      run_count: 0,
      running_runs: 0,
      failed_runs: 0,
      success_runs: 0,
      blocked_runs: 0,
      latest_run_id: undefined,
      current_role: "PM",
      current_step: "Unknown",
      updated_at: undefined,
    },
    run_ids: [],
    runs: [],
    blockers: [],
  };
  const fallbackEvents: EventRecord[] = [];
  const fallbackGraph: PmSessionConversationGraphPayload = {
    pm_session_id: id,
    window: "24h" as const,
    nodes: [],
    edges: [],
    stats: {
      node_count: 0,
      edge_count: 0,
    },
  };
  const fallbackMetrics: PmSessionMetricsPayload = {
    pm_session_id: id,
    run_count: 0,
    running_runs: 0,
    failed_runs: 0,
    success_runs: 0,
    blocked_runs: 0,
    failure_rate: 0,
    blocked_ratio: 0,
    avg_duration_seconds: 0,
    avg_recovery_seconds: 0,
    cycle_time_seconds: 0,
    mttr_seconds: 0,
  };

  const settled = await Promise.allSettled([
    safeLoad(() => fetchPmSession(id), fallbackDetail, "Session details"),
    safeLoad(() => fetchPmSessionEvents(id, { limit: 800, tail: true }), fallbackEvents, "Session event stream"),
    safeLoad(
      () => fetchPmSessionConversationGraph(id, { window: "24h", groupByRole: true }),
      fallbackGraph,
      "Session role handoff graph",
    ),
    safeLoad(() => fetchPmSessionMetrics(id), fallbackMetrics, "Session metrics"),
  ]);

  const detailResult =
    settled[0].status === "fulfilled" ? settled[0].value : { data: fallbackDetail, warning: "Session details are unavailable right now. Please try again later." };
  const eventsResult =
    settled[1].status === "fulfilled" ? settled[1].value : { data: fallbackEvents, warning: "Session event stream is unavailable right now. Please try again later." };
  const graphResult =
    settled[2].status === "fulfilled" ? settled[2].value : { data: fallbackGraph, warning: "Session role handoff graph is unavailable right now. Please try again later." };
  const metricsResult =
    settled[3].status === "fulfilled" ? settled[3].value : { data: fallbackMetrics, warning: "Session metrics are unavailable right now. Please try again later." };

  const detail = detailResult.data;
  const events = eventsResult.data;
  const graph = graphResult.data;
  const metrics = metricsResult.data;
  const warning = [detailResult.warning, eventsResult.warning, graphResult.warning, metricsResult.warning]
    .filter(Boolean)
    .join(" ");
  const sortedEvents = [...events].sort((a, b) => toEventTimestampMs(b) - toEventTimestampMs(a));

  return (
    <main className="grid" aria-labelledby="command-tower-session-page-title">
      <header className="app-section">
        <div className="section-header">
          <div>
            <h1 id="command-tower-session-page-title">Command Tower Session View</h1>
            <p id="command-tower-session-page-intro">Single-session shell for live trace, role handoffs, and issue convergence.</p>
            <p id="command-tower-session-page-shortcuts" className="mono muted">
              Keyboard shortcuts: Alt+L toggles live mode, Alt+R refreshes manually, Alt+M focuses the PM message input.
            </p>
            <div className="toolbar mt-2" role="navigation" aria-label="Session page quick navigation">
              <Button asChild>
                <Link href="/command-tower" aria-label="Return to Command Tower home">Back to session overview</Link>
              </Button>
            </div>
            {warning ? <p className="alert alert-warning mt-2" role="status">{warning}</p> : null}
            <p className="mono muted">The main session workspace supports Runs / Handoffs / Timeline tabs.</p>
          </div>
          <Badge className="mono">{id}</Badge>
        </div>
      </header>
      <section
        aria-label="Command Tower session workspace"
        aria-describedby="command-tower-session-page-intro command-tower-session-page-shortcuts"
      >
        <CommandTowerSessionLive
          pmSessionId={id}
          initialDetail={detail}
          initialEvents={sortedEvents}
          initialGraph={graph}
          initialMetrics={metrics}
        />
      </section>
    </main>
  );
}
