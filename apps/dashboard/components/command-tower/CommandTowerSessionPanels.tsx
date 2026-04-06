import Link from "next/link";

import type { EventRecord, PmSessionConversationGraphPayload, PmSessionDetailPayload } from "../../lib/types";
import ConversationGraph from "./ConversationGraph";
import SessionTimeline from "./SessionTimeline";
import { Card } from "../ui/card";

type Props = {
  detail: PmSessionDetailPayload;
  events: EventRecord[];
  graph: PmSessionConversationGraphPayload;
  activeMainTab: "runs" | "graph" | "timeline";
  sessionRunsRegionId: string;
  sessionRunsTabId: string;
  sessionGraphRegionId: string;
  sessionGraphTabId: string;
  sessionTimelineRegionId: string;
  sessionTimelineTabId: string;
};

export default function CommandTowerSessionPanels(props: Props) {
  if (props.activeMainTab === "runs") {
    return (
      <section
        className="app-section"
        id={props.sessionRunsRegionId}
        role="tabpanel"
        aria-labelledby={props.sessionRunsTabId}
        data-state="active"
        data-testid="ct-session-panel-runs"
        aria-label="Session runs table"
      >
        <div className="section-header">
          <div>
            <h3>Session runs</h3>
            <p>Runs linked to this session and the current execution position.</p>
          </div>
        </div>
        <Card variant="table">
          <table className="run-table">
            <caption className="sr-only">Session runs with status, role step, and latest event time.</caption>
            <thead>
              <tr>
                <th scope="col">Run</th>
                <th scope="col">Status</th>
                <th scope="col">Failure reason</th>
                <th scope="col">Role / Step</th>
                <th scope="col">Blocked</th>
                <th scope="col">Latest event</th>
              </tr>
            </thead>
            <tbody>
              {props.detail.runs.length === 0 ? (
                <tr>
                  <td colSpan={6}>
                    <p className="muted">This session has no runs yet. Send a message in PM and trigger `/run` to start execution.</p>
                  </td>
                </tr>
              ) : (
                props.detail.runs.map((run) => (
                  <tr key={run.run_id}>
                    <td>
                      <Link href={`/runs/${encodeURIComponent(run.run_id)}`} className="run-link">
                        {run.run_id}
                      </Link>
                      <div className="mono muted">{run.task_id || "-"}</div>
                    </td>
                    <td className="mono">{run.status || "-"}</td>
                    <td className="mono">{run.failure_reason || "-"}</td>
                    <td>
                      <div className="mono">{run.current_role || "-"}</div>
                      <div className="mono muted">{run.current_step || "-"}</div>
                    </td>
                    <td className="mono">{run.blocked ? "Yes" : "No"}</td>
                    <td className="mono">{run.last_event_ts || run.finished_at || run.created_at || "-"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </Card>
      </section>
    );
  }

  if (props.activeMainTab === "graph") {
    return (
      <div
        id={props.sessionGraphRegionId}
        role="tabpanel"
        aria-labelledby={props.sessionGraphTabId}
        data-state="active"
        data-testid="ct-session-panel-graph"
        aria-label="Session role handoff graph"
      >
        <ConversationGraph graph={props.graph} />
      </div>
    );
  }

  return (
    <div
      id={props.sessionTimelineRegionId}
      role="tabpanel"
      aria-labelledby={props.sessionTimelineTabId}
      data-state="active"
      data-testid="ct-session-panel-timeline"
      aria-label="Session timeline"
    >
      {props.events.length === 0 ? (
        <Card>
          <p className="muted">No session timeline yet. Once a run starts, role handoffs and key moments will appear automatically.</p>
        </Card>
      ) : (
        <SessionTimeline events={props.events} />
      )}
    </div>
  );
}
