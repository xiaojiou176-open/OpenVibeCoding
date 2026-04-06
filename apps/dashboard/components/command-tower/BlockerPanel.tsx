import Link from "next/link";
import { Badge } from "../ui/badge";
import { Card } from "../ui/card";

import type { PmSessionSummary } from "../../lib/types";

type BlockerPanelProps = {
  blockers: PmSessionSummary[];
};

export default function BlockerPanel({ blockers }: BlockerPanelProps) {
  return (
    <section className="app-section blocker-panel">
      <div className="section-header blocker-panel__header">
        <div>
          <h3>Blocked session queue</h3>
          <p>Sorted by blocked run count so the most disruptive sessions are handled first.</p>
        </div>
      </div>
      <div className="grid command-tower-panel-group command-tower-panel-group--single blocker-panel__body">
        {blockers.length === 0 ? (
          <Card variant="compact" className="blocker-panel__empty" role="status" aria-live="polite">
            <p className="muted">No blocked sessions right now</p>
          </Card>
        ) : (
          blockers.map((session) => (
            <Card key={session.pm_session_id} asChild className="run-detail-live-panel blocker-panel__item">
              <article>
                <div className="run-detail-live-head blocker-panel__item-header">
                  <div className="min-w-0">
                    <Link
                      className="run-link"
                      href={`/command-tower/sessions/${encodeURIComponent(session.pm_session_id)}`}
                    >
                      {session.pm_session_id}
                    </Link>
                    <p className="mono muted run-detail-inline-gap blocker-panel__item-objective">{session.objective || "-"}</p>
                  </div>
                  <Badge variant="failed">Blocked {session.blocked_runs}</Badge>
                </div>
                <div className="run-detail-chip-row blocker-panel__item-body">
                  <Badge variant="running">Running {session.running_runs}</Badge>
                  <Badge variant="failed">Failed {session.failed_runs}</Badge>
                  <Badge>Owner {session.owner_pm || "-"}</Badge>
                </div>
              </article>
            </Card>
          ))
        )}
      </div>
    </section>
  );
}
