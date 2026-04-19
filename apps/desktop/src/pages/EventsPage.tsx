import { Fragment, useCallback, useEffect, useState } from "react";
import type { UiLocale } from "@openvibecoding/frontend-shared/uiCopy";
import { detectPreferredUiLocale } from "@openvibecoding/frontend-shared/uiLocale";
import type { EventRecord } from "../lib/types";
import { fetchAllEvents } from "../lib/api";
import { formatDesktopDateTime, statusVariant } from "../lib/statusPresentation";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";

export function EventsPage({ locale = detectPreferredUiLocale() as UiLocale }: { locale?: UiLocale } = {}) {
  const copy =
    locale === "zh-CN"
      ? {
          title: "事件流",
          subtitle: "全局事件时间线。展开一行查看 payload。",
          refresh: "刷新",
          empty: "当前还没有事件",
          headers: { time: "时间", event: "事件", level: "级别", taskId: "任务 ID", runId: "运行 ID" },
          ariaDetails: (name: string) => `查看事件详情 ${name}`,
        }
      : {
          title: "Events",
          subtitle: "Global event timeline. Expand a row to inspect the payload.",
          refresh: "Refresh",
          empty: "No events yet",
          headers: { time: "Time", event: "Event", level: "Level", taskId: "Task ID", runId: "Run ID" },
          ariaDetails: (name: string) => `View event details ${name}`,
        };
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
        <div><h1 className="page-title">{copy.title}</h1><p className="page-subtitle">{copy.subtitle}</p></div>
        <Button onClick={load}>{copy.refresh}</Button>
      </div>
      {error && <div className="alert alert-danger">{error}</div>}
      {loading ? (
        <div className="skeleton-stack-lg"><div className="skeleton skeleton-row" /><div className="skeleton skeleton-row" /><div className="skeleton skeleton-row" /></div>
      ) : events.length === 0 ? (
        <div className="empty-state-stack"><p className="muted">{copy.empty}</p></div>
      ) : (
        <Card>
          <table className="run-table">
            <thead><tr><th>{copy.headers.time}</th><th>{copy.headers.event}</th><th>{copy.headers.level}</th><th>{copy.headers.taskId}</th><th>{copy.headers.runId}</th></tr></thead>
            <tbody>
              {events.map((evt, i) => (
                <Fragment key={`evt-${i}`}>
                  <tr className="clickable-row">
                    <td className="muted">{evt.ts ? formatDesktopDateTime(evt.ts, locale) : "-"}</td>
                    <td className="cell-primary">
                      <Button
                        variant="ghost"
                        aria-expanded={expandedIndex === i}
                        aria-label={copy.ariaDetails(String(evt.event || evt.event_type || "event"))}
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
