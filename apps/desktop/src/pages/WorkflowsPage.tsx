import { useCallback, useEffect, useState } from "react";
import { fetchQueue, fetchWorkflows, runNextQueue } from "../lib/api";
import type { QueueItemRecord, WorkflowRecord } from "../lib/types";
import { statusLabelZh, statusVariant } from "../lib/statusPresentation";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";

type WorkflowsPageProps = {
  onNavigateToWorkflow: (workflowId: string) => void;
};

export function WorkflowsPage({ onNavigateToWorkflow }: WorkflowsPageProps) {
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
        setQueueNotice(`Started queued work as run ${String(result.run_id || "-")}.`);
      } else {
        setQueueNotice(String(result?.reason || "queue empty"));
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
        <div><h1 className="page-title">Workflow Cases</h1><p className="page-subtitle">Review the case record that ties queue posture, linked runs, and the current operating verdict together.</p></div>
        <div className="row-gap-2">
          <Button onClick={load}>Refresh</Button>
          <Button variant="secondary" onClick={() => void handleRunNextQueue()} disabled={queueActionBusy}>
            {queueActionBusy ? "Running next..." : "Run next queued task"}
          </Button>
        </div>
      </div>
      {error && <div className="alert alert-danger">{error}</div>}
      {queueNotice ? <div className="alert alert-warning">{queueNotice}</div> : null}
      {loading ? (
        <div className="skeleton-stack-lg"><div className="skeleton skeleton-row" /><div className="skeleton skeleton-row" /></div>
      ) : workflows.length === 0 ? (
        <div className="empty-state-stack"><p className="muted">No workflow cases yet</p></div>
      ) : (
        <Card>
          <table className="run-table">
            <thead><tr><th>Workflow ID</th><th>Status</th><th>Namespace</th><th>Runs</th><th>Queue</th></tr></thead>
            <tbody>
              {workflows.map((wf) => (
                <tr key={wf.workflow_id}>
                  <td>
                    <Button variant="unstyled" className="run-link run-link-reset" onClick={() => onNavigateToWorkflow(wf.workflow_id)}>{wf.workflow_id}</Button>
                    {wf.objective ? <div className="mono muted">{wf.objective}</div> : null}
                  </td>
                  <td><Badge variant={statusVariant(wf.status)}>{statusLabelZh(wf.status)}</Badge></td>
                  <td className="mono">{wf.namespace || "-"}</td>
                  <td>
                    {wf.runs?.length ?? 0}
                    {wf.verdict ? <div className="mono muted">verdict: {wf.verdict}</div> : null}
                  </td>
                  <td className="mono">
                    {(queueByWorkflow[wf.workflow_id] || []).length}
                    {(queueByWorkflow[wf.workflow_id] || []).length > 0 ? (
                      <div className="muted">sla: {String(queueByWorkflow[wf.workflow_id][0]?.sla_state || "-")}</div>
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
