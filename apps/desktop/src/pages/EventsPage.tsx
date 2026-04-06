import { Fragment, useCallback, useEffect, useState } from "react";
import type { EventRecord } from "../lib/types";
import { fetchAllEvents } from "../lib/api";
import { statusVariant } from "../lib/statusPresentation";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";

export function EventsPage() {
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { const data = await fetchAllEvents(); setEvents(Array.isArray(data) ? data : []); }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const toggleExpanded = useCallback((index: number) => {
    setExpandedIndex((prev) => (prev === index ? null : index));
  }, []);

  return (
    <div className="content">
      <div className="section-header">
        <div><h1 className="page-title">Events</h1><p className="page-subtitle">Global event timeline. Expand a row to inspect the payload.</p></div>
        <Button onClick={load}>Refresh</Button>
      </div>
      {error && <div className="alert alert-danger">{error}</div>}
      {loading ? (
        <div className="skeleton-stack-lg"><div className="skeleton skeleton-row" /><div className="skeleton skeleton-row" /><div className="skeleton skeleton-row" /></div>
      ) : events.length === 0 ? (
        <div className="empty-state-stack"><p className="muted">No events yet</p></div>
      ) : (
        <Card>
          <table className="run-table">
            <thead><tr><th>Time</th><th>Event</th><th>Level</th><th>Task ID</th><th>Run ID</th></tr></thead>
            <tbody>
              {events.map((evt, i) => (
                <Fragment key={`evt-${i}`}>
                  <tr className="clickable-row">
                    <td className="muted">{evt.ts ? new Date(evt.ts).toLocaleString("zh-CN") : "-"}</td>
                    <td className="cell-primary">
                      <Button
                        variant="ghost"
                        aria-expanded={expandedIndex === i}
                        aria-label={`View event details ${evt.event || evt.event_type || "event"}`}
                        onClick={() => toggleExpanded(i)}
                      >
                        {evt.event || evt.event_type || "-"}
                      </Button>
                    </td>
                    <td><Badge variant={statusVariant(evt.level)}>{evt.level || "-"}</Badge></td>
                    <td className="mono">{evt.task_id || "-"}</td>
                    <td className="mono">{(evt.run_id || evt._run_id || "").toString().slice(0, 12)}</td>
                  </tr>
                  {expandedIndex === i && evt.context && (
                    <tr>
                      <td colSpan={5}><pre className="pre-reset">{JSON.stringify(evt.context, null, 2)}</pre></td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
