import { useCallback, useEffect, useState } from "react";
import { getUiCopy, type UiLocale } from "@cortexpilot/frontend-shared/uiCopy";
import { detectPreferredUiLocale } from "@cortexpilot/frontend-shared/uiLocale";
import type { RunSummary } from "../lib/types";
import { fetchRuns } from "../lib/api";
import {
  statusLabelZh,
  badgeClass,
  statusDotClass,
  outcomeSemantic,
  outcomeSemanticBadgeClass,
  outcomeSemanticLabelZh,
  outcomeActionHintZh,
} from "../lib/statusPresentation";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import { Card } from "../components/ui/Card";

type RunsPageProps = {
  onNavigateToRun: (runId: string) => void;
};

export function RunsPage({ onNavigateToRun }: RunsPageProps) {
  const locale: UiLocale = detectPreferredUiLocale();
  const runsPageCopy = getUiCopy(locale).dashboard.runsPage;
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
          <p className="muted">{locale === "zh-CN" ? "当前还没有 runs。" : "No runs yet."}</p>
        </div>
      ) : (
        <Card className="table-card">
          <table className="run-table">
            <thead>
              <tr>
                <th>Run ID</th>
                <th>Task ID</th>
                <th>Status</th>
                <th>Owner</th>
                <th>Created</th>
                <th>Next action</th>
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
                    </td>
                    <td className="cell-primary">{run.task_id}</td>
                    <td>
                      <span className="status-inline">
                        <span className={statusDotClass(run.status)} />
                        <Badge className={badgeClass(run.status)}>{statusLabelZh(run.status)}</Badge>
                        <Badge
                          className={outcomeSemanticBadgeClass(
                            run.outcome_type,
                            run.status,
                            run.failure_class,
                            run.failure_code,
                          )}
                        >
                          {outcomeSemanticLabelZh(
                            run.outcome_type,
                            undefined,
                            run.status,
                            run.failure_class,
                            run.failure_code,
                          )}
                        </Badge>
                      </span>
                      {toFailureSummary(run) && (
                        <div className="muted text-xs mt-1">
                          {toFailureSummary(run)}
                        </div>
                      )}
                    </td>
                    <td className="mono">{run.owner_agent_id || run.owner_role || "-"}</td>
                    <td className="muted">{run.created_at ? new Date(run.created_at).toLocaleString("en-US") : "-"}</td>
                    <td className="muted text-xs">
                      {outcomeActionHintZh(
                        undefined,
                        run.outcome_type,
                        run.status,
                        run.failure_class,
                        run.failure_code,
                      )}
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
