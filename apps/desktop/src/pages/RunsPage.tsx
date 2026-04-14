import { useCallback, useEffect, useState } from "react";
import { getUiCopy, type UiLocale } from "@openvibecoding/frontend-shared/uiCopy";
import { detectPreferredUiLocale } from "@openvibecoding/frontend-shared/uiLocale";
import type { RunSummary } from "../lib/types";
import { fetchRuns } from "../lib/api";
import {
  statusLabelDesktop,
  badgeClass,
  statusDotClass,
  outcomeSemantic,
  outcomeSemanticLabel,
  outcomeActionHint,
} from "../lib/statusPresentation";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import { Card } from "../components/ui/Card";

type RunsPageProps = {
  onNavigateToRun: (runId: string) => void;
};

function runsPageText(locale: UiLocale) {
  if (locale === "zh-CN") {
    return {
      empty: "当前还没有 runs。",
      noProof: "当前还没有 proof posture。",
      runningProof: "证据仍在形成中。",
      noExtraProof: "当前没有额外的 failure 或 root-event 摘要。",
      noAction: "先打开 Run Detail 做进一步判断。",
      headers: {
        run: "Run",
        operator: "操作者姿态",
        proof: "Proof 姿态",
        next: "下一步",
        updated: "最近更新",
      },
      prefixes: {
        task: "Task",
        workflow: "Workflow",
        owner: "Owner",
        assignee: "Assignee",
      },
      actions: {
        openRun: "打开 Run Detail",
        openProof: "打开 Proof & Replay",
      },
    };
  }
  return {
    empty: "No runs yet.",
    noProof: "No proof posture is attached yet.",
    runningProof: "Evidence is still forming on this run.",
    noExtraProof: "No extra failure or root-event summary is attached.",
    noAction: "Open run detail before deciding what happens next.",
    headers: {
      run: "Run",
      operator: "Operator posture",
      proof: "Proof posture",
      next: "Next operator action",
      updated: "Updated",
    },
    prefixes: {
      task: "Task",
      workflow: "Workflow",
      owner: "Owner",
      assignee: "Assignee",
    },
    actions: {
      openRun: "Open Run Detail",
      openProof: "Open Proof & Replay",
    },
  };
}

export function RunsPage({ onNavigateToRun }: RunsPageProps) {
  const locale: UiLocale = detectPreferredUiLocale();
  const runsPageCopy = getUiCopy(locale).dashboard.runsPage;
  const text = runsPageText(locale);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await fetchRuns();
      setRuns(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const toFailureSummary = (run: RunSummary): string | undefined => {
    const preferred = [run.failure_reason, run.failure_code]
      .find((value) => typeof value === "string" && value.trim());
    return preferred?.trim();
  };

  const toProofPrimary = (run: RunSummary): string => {
    const label = outcomeSemanticLabel(
      run.outcome_type,
      undefined,
      run.status,
      locale,
      run.failure_class,
      run.failure_code,
    );
    return label || text.noProof;
  };

  const toProofSecondary = (run: RunSummary): string => {
    return (
      String(run.failure_summary_zh || "").trim()
      || String(run.root_event || "").trim()
      || toFailureSummary(run)
      || text.noExtraProof
    );
  };

  const toNextAction = (run: RunSummary): string => {
    const hint = outcomeActionHint(
      undefined,
      run.outcome_type,
      run.status,
      locale,
      run.failure_class,
      run.failure_code,
    );
    return hint || text.noAction;
  };

  return (
    <div className="content">
      <div className="section-header">
        <div>
          <h1 className="page-title">{runsPageCopy.title}</h1>
          <p className="page-subtitle">{runsPageCopy.subtitle}</p>
        </div>
        <Button onClick={load}>{locale === "zh-CN" ? "刷新" : "Refresh"}</Button>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      {loading ? (
        <div className="skeleton-stack-lg">
          <div className="skeleton skeleton-row" />
          <div className="skeleton skeleton-row" />
          <div className="skeleton skeleton-row" />
        </div>
      ) : runs.length === 0 ? (
        <div className="empty-state-stack">
          <p className="muted">{text.empty}</p>
        </div>
      ) : (
        <Card className="table-card">
          <table className="run-table">
            <thead>
              <tr>
                <th>{text.headers.run}</th>
                <th>{text.headers.operator}</th>
                <th>{text.headers.proof}</th>
                <th>{text.headers.next}</th>
                <th>{text.headers.updated}</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => {
                const semantic = outcomeSemantic(run.outcome_type, run.status, run.failure_class, run.failure_code);
                const rowClass =
                  semantic === "environment_error" || semantic === "functional_failure" ? "session-row--failed" :
                  semantic === "gate_blocked" || semantic === "manual_pending" ? "session-row--blocked" :
                  run.status === "running" ? "session-row--running" : "";
                return (
                  <tr key={run.run_id} className={rowClass}>
                    <td>
                      <Button
                        variant="unstyled"
                        className="run-link run-link-reset"
                        onClick={() => onNavigateToRun(run.run_id)}
                      >
                        {run.run_id.slice(0, 12)}
                      </Button>
                      <div className="cell-sub mono muted">{`${text.prefixes.task}: ${run.task_id || "-"}`}</div>
                      <div className="cell-sub mono muted">{`${text.prefixes.workflow}: ${run.workflow_status || "-"}`}</div>
                    </td>
                    <td>
                      <span className="status-inline">
                        <span className={statusDotClass(run.status)} />
                        <Badge className={badgeClass(run.status)}>{statusLabelDesktop(run.status, locale)}</Badge>
                      </span>
                      <div className="cell-sub mono muted">
                        {`${text.prefixes.owner}: ${run.owner_role || run.owner_agent_id || "-"}${run.assigned_role || run.assigned_agent_id ? ` · ${text.prefixes.assignee}: ${run.assigned_role || run.assigned_agent_id}` : ""}`}
                      </div>
                    </td>
                    <td>
                      <div className={`mono ${semantic === "environment_error" || semantic === "functional_failure" ? "cell-danger" : "cell-primary"}`}>
                        {toProofPrimary(run)}
                      </div>
                      <div className="cell-sub mono muted">{toProofSecondary(run)}</div>
                    </td>
                    <td>
                      <div className="mono">{toNextAction(run)}</div>
                      <div className="cell-sub mono inline-stack">
                        <Button
                          variant={semantic === "environment_error" || semantic === "functional_failure" ? "primary" : "secondary"}
                          onClick={() => onNavigateToRun(run.run_id)}
                        >
                          {semantic === "environment_error" || semantic === "functional_failure" ? text.actions.openProof : text.actions.openRun}
                        </Button>
                      </div>
                    </td>
                    <td className="muted">
                      {run.created_at ? new Date(run.created_at).toLocaleString(locale === "zh-CN" ? "zh-CN" : "en-US") : "-"}
                      <div className="cell-sub mono muted">{run.workflow_status || toProofPrimary(run)}</div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
