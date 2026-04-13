import { useCallback, useEffect, useState } from "react";
import { getUiCopy, type UiLocale } from "@cortexpilot/frontend-shared/uiCopy";
import {
  formatBindingReadModelLabel,
  formatRoleBindingRuntimeSummary,
  type QueueItemRecord,
  type WorkflowDetailPayload,
} from "../lib/types";
import { enqueueRunQueue, fetchQueue, fetchWorkflow, fetchWorkflowCopilotBrief, runNextQueue } from "../lib/api";
import { formatDesktopDateTime, statusLabelDesktop, statusVariant } from "../lib/statusPresentation";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card, CardBody, CardHeader, CardTitle } from "../components/ui/Card";
import { Input } from "../components/ui/Input";
import { DesktopCopilotPanel } from "../components/copilot/DesktopCopilotPanel";

type Props = { workflowId: string; onBack: () => void; onNavigateToRun: (runId: string) => void; locale?: UiLocale };

function toUtcIsoOrEmpty(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) {
    return "";
  }
  const parsed = new Date(trimmed);
  return Number.isNaN(parsed.getTime()) ? "" : parsed.toISOString();
}

export function WorkflowDetailPage({ workflowId, onBack, onNavigateToRun, locale = "en" }: Props) {
  const [data, setData] = useState<WorkflowDetailPayload | null>(null);
  const [queueItems, setQueueItems] = useState<QueueItemRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [queueBusy, setQueueBusy] = useState(false);
  const [queueNotice, setQueueNotice] = useState("");
  const [queuePriority, setQueuePriority] = useState("0");
  const [queueScheduledAt, setQueueScheduledAt] = useState("");
  const [queueDeadlineAt, setQueueDeadlineAt] = useState("");
  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [workflowPayload, queuePayload] = await Promise.all([fetchWorkflow(workflowId), fetchQueue(workflowId)]);
      setData(workflowPayload);
      setQueueItems(Array.isArray(queuePayload) ? queuePayload : []);
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setLoading(false); }
  }, [workflowId]);
  useEffect(() => { void load(); }, [load]);

  if (loading) return <div className="content"><div className="skeleton-stack-lg"><div className="skeleton skeleton-row" /></div></div>;
  if (error) return <div className="content"><div className="alert alert-danger">{error}</div><Button onClick={onBack}>Back</Button></div>;
  if (!data) return null;
  const workflowData = {
    ...data,
    workflow: data.workflow ?? { workflow_id: workflowId },
  };
  const workflowCaseReadModel = workflowData.workflow.workflow_case_read_model;
  const roleBindingSummary = workflowCaseReadModel?.role_binding_summary;
  const skillsBundle = roleBindingSummary?.skills_bundle_ref;
  const mcpBundle = roleBindingSummary?.mcp_bundle_ref;
  const workflowDetailCopy = getUiCopy(locale).desktop.workflowDetail;
  const recommendedAction =
    queueItems.length > 0
      ? workflowDetailCopy.recommendedActionQueued
      : workflowData.runs.length > 0
      ? workflowDetailCopy.recommendedActionNoQueue
      : workflowDetailCopy.recommendedActionNoRun;

  function resolveLatestRunId(): string {
    const runs = [...workflowData.runs];
    runs.sort((lhs, rhs) => {
      const lhsTs = Date.parse(String(lhs.created_at || ""));
      const rhsTs = Date.parse(String(rhs.created_at || ""));
      return (Number.isFinite(rhsTs) ? rhsTs : 0) - (Number.isFinite(lhsTs) ? lhsTs : 0);
    });
    return String(runs[0]?.run_id || "").trim();
  }

  async function handleQueueLatestRun() {
    const latestRunId = resolveLatestRunId();
    if (!latestRunId) {
      setQueueNotice(workflowDetailCopy.noRunAvailable);
      return;
    }
    setQueueBusy(true);
    setQueueNotice("");
    try {
      const priority = Number.parseInt(queuePriority, 10);
      const payload: Record<string, string | number> = {};
      if (Number.isFinite(priority)) {
        payload.priority = priority;
      }
      const scheduledAtIso = toUtcIsoOrEmpty(queueScheduledAt);
      if (scheduledAtIso) {
        payload.scheduled_at = scheduledAtIso;
      }
      const deadlineAtIso = toUtcIsoOrEmpty(queueDeadlineAt);
      if (deadlineAtIso) {
        payload.deadline_at = deadlineAtIso;
      }
      const result = await enqueueRunQueue(latestRunId, payload);
      setQueueNotice(workflowDetailCopy.queuedNotice(String(result.task_id || latestRunId)));
      await load();
    } catch (err) {
      setQueueNotice(err instanceof Error ? err.message : String(err));
    } finally {
      setQueueBusy(false);
    }
  }

  async function handleRunNextQueue() {
    setQueueBusy(true);
    setQueueNotice("");
    try {
      const result = await runNextQueue({});
      setQueueNotice(
        result?.ok
          ? workflowDetailCopy.startedNotice(String(result.run_id || "-"))
          : String(result?.reason || workflowDetailCopy.queueEmptyReason),
      );
      await load();
    } catch (err) {
      setQueueNotice(err instanceof Error ? err.message : String(err));
    } finally {
      setQueueBusy(false);
    }
  }

  return (
    <div className="content">
      <Button variant="ghost" className="mb-2" onClick={onBack}>{workflowDetailCopy.backToList}</Button>
      <div className="section-header"><div><h1 className="page-title mono">{workflowData.workflow.workflow_id}</h1></div><Badge variant={statusVariant(workflowData.workflow.status)}>{statusLabelDesktop(workflowData.workflow.status, locale)}</Badge></div>
      <div className="grid-2 mb-3">
        <Card>
          <CardHeader>
            <CardTitle>{workflowDetailCopy.nextOperatorActionTitle}</CardTitle>
          </CardHeader>
          <CardBody>
            <div className="stack-gap-2">
              <div className="mono">{recommendedAction}</div>
              <div className="muted">{workflowDetailCopy.nextOperatorActionHint}</div>
            </div>
          </CardBody>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{workflowDetailCopy.summaryTitle}</CardTitle>
          </CardHeader>
          <CardBody>
            <div className="stack-gap-2">
              <div className="mono">{workflowDetailCopy.summaryLabels.status}: {statusLabelDesktop(workflowData.workflow.status || "-", locale)}</div>
              <div className="mono">{workflowDetailCopy.summaryLabels.objective}: {workflowData.workflow.objective || "-"}</div>
              <div className="mono">{workflowDetailCopy.summaryLabels.owner}: {workflowData.workflow.owner_pm || "-"}</div>
              <div className="mono">{workflowDetailCopy.summaryLabels.project}: {workflowData.workflow.project_key || "-"}</div>
              <div className="mono">{workflowDetailCopy.summaryLabels.verdict}: {workflowData.workflow.verdict || "-"}</div>
              <div className="mono">{workflowDetailCopy.summaryLabels.pmSessions}: {(workflowData.workflow.pm_session_ids || []).join(", ") || "-"}</div>
              <div className="mono">{workflowDetailCopy.summaryLabels.summary}: {workflowData.workflow.summary || "-"}</div>
            </div>
          </CardBody>
        </Card>
      </div>
      <div className="row-gap-2 mb-2">
        <Input
          type="number"
          aria-label={workflowDetailCopy.queuePriority}
          value={queuePriority}
          onChange={(event) => setQueuePriority(event.target.value)}
          placeholder={workflowDetailCopy.queuePriority}
        />
        <Input
          type="datetime-local"
          aria-label={workflowDetailCopy.queueScheduledAt}
          value={queueScheduledAt}
          onChange={(event) => setQueueScheduledAt(event.target.value)}
          placeholder={workflowDetailCopy.queueScheduledAt}
        />
        <Input
          type="datetime-local"
          aria-label={workflowDetailCopy.queueDeadlineAt}
          value={queueDeadlineAt}
          onChange={(event) => setQueueDeadlineAt(event.target.value)}
          placeholder={workflowDetailCopy.queueDeadlineAt}
        />
        <Button variant="secondary" onClick={() => void handleQueueLatestRun()} disabled={queueBusy || workflowData.runs.length === 0}>{workflowDetailCopy.queueLatestRun}</Button>
        <Button variant="secondary" onClick={() => void handleRunNextQueue()} disabled={queueBusy}>{queueBusy ? workflowDetailCopy.runningTask : workflowDetailCopy.runNextQueuedTask}</Button>
      </div>
      {queueNotice ? <div className="alert alert-warning">{queueNotice}</div> : null}
      <div className="mb-4">
        <DesktopCopilotPanel
          title={workflowDetailCopy.workflowCopilotTitle}
          intro={workflowDetailCopy.workflowCopilotIntro}
          buttonLabel={workflowDetailCopy.workflowCopilotButton}
          questionSet={workflowDetailCopy.workflowCopilotQuestions}
          takeawaysHeading={workflowDetailCopy.workflowCopilotTakeaways}
          postureHeading={workflowDetailCopy.workflowCopilotPosture}
          loadBrief={() => fetchWorkflowCopilotBrief(workflowId)}
        />
      </div>
      <div className="grid-2">
        <Card>
          <CardHeader>
            <CardTitle>{workflowDetailCopy.readModelTitle}</CardTitle>
          </CardHeader>
          <CardBody>
            {!workflowCaseReadModel ? (
              <div className="mono">{workflowDetailCopy.noReadModel}</div>
            ) : (
              <div className="stack-gap-2">
                <div className="mono">{workflowDetailCopy.readModelLabels.authority}: {String(workflowCaseReadModel.authority || "-")}</div>
                <div className="mono">{workflowDetailCopy.readModelLabels.executionAuthority}: {String(workflowCaseReadModel.execution_authority || "-")}</div>
                <div className="mono">{workflowDetailCopy.readModelLabels.source}: {String(workflowCaseReadModel.source || "-")}</div>
                <div className="mono">{workflowDetailCopy.readModelLabels.sourceRunId}: {String(workflowCaseReadModel.source_run_id || "-")}</div>
                <div className="mono">{workflowDetailCopy.readModelLabels.skillsBundle}: {formatBindingReadModelLabel(skillsBundle)}</div>
                <div className="mono">{workflowDetailCopy.readModelLabels.mcpBundle}: {formatBindingReadModelLabel(mcpBundle)}</div>
                <div className="mono">{workflowDetailCopy.readModelLabels.runtimeBinding}: {formatRoleBindingRuntimeSummary(roleBindingSummary)}</div>
                <div className="muted">
                  {workflowDetailCopy.readModelLabels.readOnlyNote}
                </div>
              </div>
            )}
          </CardBody>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{workflowDetailCopy.relatedRunsTitle(workflowData.runs.length)}</CardTitle>
          </CardHeader>
          <CardBody>
            {workflowData.runs.length === 0 ? <p className="muted">{workflowDetailCopy.noRelatedRuns}</p> : (
              <div className="stack-gap-2">
                {workflowData.runs.map((r) => (
                  <div key={r.run_id} className="row-between py-2 border-bottom-subtle">
                    <Button variant="unstyled" className="run-link run-link-reset" onClick={() => onNavigateToRun(r.run_id)}>{r.run_id.slice(0, 12)}</Button>
                    <Badge variant={statusVariant(r.status)}>{statusLabelDesktop(r.status, locale)}</Badge>
                  </div>
                ))}
              </div>
            )}
          </CardBody>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{workflowDetailCopy.eventsTitle(workflowData.events.length)}</CardTitle>
          </CardHeader>
          <CardBody>
            {workflowData.events.length === 0 ? <p className="muted">{workflowDetailCopy.noEvents}</p> : (
              <div className="stack-gap-2 max-h-400 overflow-auto">
                {workflowData.events.map((evt, i) => (
                  <div key={`${evt.ts}-${i}`} className="row-between text-xs py-1 border-bottom-subtle">
                    <span className="muted">{evt.ts ? formatDesktopDateTime(evt.ts, locale) : "-"}</span>
                    <span>{evt.event || evt.event_type || "-"}</span>
                  </div>
                ))}
              </div>
            )}
          </CardBody>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{workflowDetailCopy.queueSlaTitle(queueItems.length)}</CardTitle>
          </CardHeader>
          <CardBody>
            {queueItems.length === 0 ? <p className="muted">{workflowDetailCopy.noQueuedWork}</p> : (
              <div className="stack-gap-2">
                {queueItems.map((item) => (
                  <div key={item.queue_id} className="row-between py-2 border-bottom-subtle">
                    <div className="mono">
                      <div>{item.task_id}</div>
                      <div className="muted">{workflowDetailCopy.queueMeta(String(item.priority ?? "-"), String(item.sla_state || "-"))}</div>
                    </div>
                    <Badge variant={statusVariant(item.status)}>{statusLabelDesktop(item.status, locale)}</Badge>
                  </div>
                ))}
              </div>
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
