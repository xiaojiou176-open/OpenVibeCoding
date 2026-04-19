import { useCallback, useEffect, useState } from "react";
import type { UiLocale } from "@openvibecoding/frontend-shared/uiCopy";
import { detectPreferredUiLocale } from "@openvibecoding/frontend-shared/uiLocale";
import { fetchQueue, fetchWorkflows, runNextQueue } from "../lib/api";
import type { QueueItemRecord, WorkflowRecord } from "../lib/types";
import { statusLabelDesktop, statusVariant } from "../lib/statusPresentation";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";

type WorkflowsPageProps = {
  onNavigateToWorkflow: (workflowId: string) => void;
  locale?: UiLocale;
};

export function WorkflowsPage({ onNavigateToWorkflow, locale = detectPreferredUiLocale() as UiLocale }: WorkflowsPageProps) {
  const copy =
    locale === "zh-CN"
      ? {
          title: "工作流案例",
          subtitle: "查看把队列姿态、关联运行和当前操作结论绑在一起的案例记录。",
          refresh: "刷新",
          runningNext: "运行下一条排队任务",
          runningBusy: "运行中...",
          empty: "当前还没有工作流案例",
          started: (runId: string) => `已启动排队工作，运行为 ${runId}。`,
          queueEmpty: "队列为空",
          headers: { id: "工作流 ID", status: "状态", namespace: "命名空间", runs: "运行", queue: "队列" },
          verdictPrefix: "结论",
          slaPrefix: "时限",
        }
      : {
          title: "Workflow Cases",
          subtitle: "Review the case record that ties queue posture, linked runs, and the current operating verdict together.",
          refresh: "Refresh",
          runningNext: "Run next queued task",
          runningBusy: "Running next...",
          empty: "No workflow cases yet",
          started: (runId: string) => `Started queued work as run ${runId}.`,
          queueEmpty: "queue empty",
          headers: { id: "Workflow ID", status: "Status", namespace: "Namespace", runs: "Runs", queue: "Queue" },
          verdictPrefix: "verdict",
          slaPrefix: "sla",
        };
  const [workflows, setWorkflows] = useState<WorkflowRecord[]>([]);
  const [queueItems, setQueueItems] = useState<QueueItemRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [queueActionBusy, setQueueActionBusy] = useState(false);
  const [queueNotice, setQueueNotice] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [workflowData, queueData] = await Promise.all([fetchWorkflows(), fetchQueue()]);
      setWorkflows(Array.isArray(workflowData) ? workflowData : []);
      setQueueItems(Array.isArray(queueData) ? queueData : []);
    }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const queueByWorkflow = queueItems.reduce<Record<string, QueueItemRecord[]>>((accumulator, item) => {
    const workflowId = String(item.workflow_id || "").trim();
    if (!workflowId) {
      return accumulator;
    }
    accumulator[workflowId] = [...(accumulator[workflowId] || []), item];
    return accumulator;
  }, {});

  async function handleRunNextQueue() {
    setQueueActionBusy(true);
    setQueueNotice("");
    try {
      const result = await runNextQueue({});
      if (result?.ok) {
        setQueueNotice(copy.started(String(result.run_id || "-")));
      } else {
        setQueueNotice(String(result?.reason || copy.queueEmpty));
      }
      await load();
    } catch (err) {
      setQueueNotice(err instanceof Error ? err.message : String(err));
    } finally {
      setQueueActionBusy(false);
    }
  }

  return (
    <div className="content">
      <div className="section-header">
        <div><h1 className="page-title">{copy.title}</h1><p className="page-subtitle">{copy.subtitle}</p></div>
        <div className="row-gap-2">
          <Button onClick={load}>{copy.refresh}</Button>
          <Button variant="secondary" onClick={() => void handleRunNextQueue()} disabled={queueActionBusy}>
            {queueActionBusy ? copy.runningBusy : copy.runningNext}
          </Button>
        </div>
      </div>
      {error && <div className="alert alert-danger">{error}</div>}
      {queueNotice ? <div className="alert alert-warning">{queueNotice}</div> : null}
      {loading ? (
        <div className="skeleton-stack-lg"><div className="skeleton skeleton-row" /><div className="skeleton skeleton-row" /></div>
      ) : workflows.length === 0 ? (
        <div className="empty-state-stack"><p className="muted">{copy.empty}</p></div>
      ) : (
        <Card>
          <table className="run-table">
            <thead><tr><th>{copy.headers.id}</th><th>{copy.headers.status}</th><th>{copy.headers.namespace}</th><th>{copy.headers.runs}</th><th>{copy.headers.queue}</th></tr></thead>
            <tbody>
              {workflows.map((wf) => (
                <tr key={wf.workflow_id}>
                  <td>
                    <Button variant="unstyled" className="run-link run-link-reset" onClick={() => onNavigateToWorkflow(wf.workflow_id)}>{wf.workflow_id}</Button>
                    {wf.objective ? <div className="mono muted">{wf.objective}</div> : null}
                  </td>
                  <td><Badge variant={statusVariant(wf.status)}>{statusLabelDesktop(wf.status, locale)}</Badge></td>
                  <td className="mono">{wf.namespace || "-"}</td>
                  <td>
                    {wf.runs?.length ?? 0}
                    {wf.verdict ? <div className="mono muted">{copy.verdictPrefix}: {wf.verdict}</div> : null}
                  </td>
                  <td className="mono">
                    {(queueByWorkflow[wf.workflow_id] || []).length}
                    {(queueByWorkflow[wf.workflow_id] || []).length > 0 ? (
                      <div className="muted">{copy.slaPrefix}: {String(queueByWorkflow[wf.workflow_id][0]?.sla_state || "-")}</div>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
