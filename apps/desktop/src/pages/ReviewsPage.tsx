import { useCallback, useEffect, useState } from "react";
import type { UiLocale } from "@openvibecoding/frontend-shared/uiCopy";
import { detectPreferredUiLocale } from "@openvibecoding/frontend-shared/uiLocale";
import type { JsonValue } from "../lib/types";
import { fetchReviews } from "../lib/api";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card, CardBody, CardHeader, CardTitle } from "../components/ui/Card";

export function ReviewsPage({ locale = detectPreferredUiLocale() as UiLocale }: { locale?: UiLocale } = {}) {
  const copy =
    locale === "zh-CN"
      ? {
          title: "评审",
          subtitle: "查看代码评审记录、结论和证据。",
          refreshing: "刷新中...",
          refresh: "刷新",
          empty: "当前还没有评审记录",
          scope: "范围",
          pending: "待定",
          reviewLabel: (i: number) => `评审 ${i + 1}`,
        }
      : {
          title: "Reviews",
          subtitle: "Code review records, verdicts, and evidence",
          refreshing: "Refreshing...",
          refresh: "Refresh",
          empty: "No review records yet",
          scope: "Scope",
          pending: "PENDING",
          reviewLabel: (i: number) => `Review ${i + 1}`,
        };
  const [reviews, setReviews] = useState<Array<Record<string, JsonValue>>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { const data = await fetchReviews(); setReviews(Array.isArray(data) ? data : []); }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const verdictVariant = (v: string) => (v === "pass" ? "success" : v === "fail" ? "failed" : "muted");

  return (
    <div className="content">
      <div className="section-header"><div><h1 className="page-title">{copy.title}</h1><p className="page-subtitle">{copy.subtitle}</p></div><Button onClick={load} disabled={loading}>{loading ? copy.refreshing : copy.refresh}</Button></div>
      {error && <div className="alert alert-danger" role="alert" aria-live="assertive">{error}</div>}
      {loading ? <div className="skeleton-stack-lg"><div className="skeleton skeleton-row" /><div className="skeleton skeleton-row" /></div> : reviews.length === 0 ? <div className="empty-state-stack"><p className="muted">{copy.empty}</p></div> : (
        <div className="stack-gap-4">
          {reviews.map((r, i) => {
            const verdict = String(r.verdict || "");
            const summary = String(r.summary || r.details || "");
            const scopeCheck = String(r.scope_check || "");
            const evidence = Array.isArray(r.evidence) ? r.evidence : [];
            return (
              <Card key={i}>
                <CardHeader className="row-between-mb-3">
                  <CardTitle className="mono">{String(r.run_id || r.task_id || copy.reviewLabel(i))}</CardTitle>
                  <Badge variant={verdictVariant(verdict)} className="text-sm fw-600">{verdict.toUpperCase() || copy.pending}</Badge>
                </CardHeader>
                <CardBody>
                  {summary && <p className="text-secondary text-sm mb-2">{summary}</p>}
                  {scopeCheck && <p className="text-xs muted">{copy.scope}: {scopeCheck}</p>}
                  {evidence.length > 0 && <div className="chip-list mt-2">{evidence.map((e, j) => <span key={j} className="chip">{String(e)}</span>)}</div>}
                </CardBody>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
