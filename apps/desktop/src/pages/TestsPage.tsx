import { useCallback, useEffect, useState } from "react";
import type { UiLocale } from "@openvibecoding/frontend-shared/uiCopy";
import { detectPreferredUiLocale } from "@openvibecoding/frontend-shared/uiLocale";
import type { JsonValue } from "../lib/types";
import { fetchTests } from "../lib/api";
import { statusLabelDesktop, statusVariant } from "../lib/statusPresentation";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card, CardBody, CardHeader, CardTitle } from "../components/ui/Card";

export function TestsPage({ locale = detectPreferredUiLocale() as UiLocale }: { locale?: UiLocale } = {}) {
  const copy =
    locale === "zh-CN"
      ? {
          title: "测试",
          subtitle: "查看验收测试和回归测试结果。",
          refresh: "刷新",
          empty: "当前还没有测试记录",
          refreshing: "刷新中...",
        }
      : {
          title: "Tests",
          subtitle: "Acceptance-test and regression-test results",
          refresh: "Refresh",
          empty: "No test records yet",
          refreshing: "Refreshing...",
        };
  const [tests, setTests] = useState<Array<Record<string, JsonValue>>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { const data = await fetchTests(); setTests(Array.isArray(data) ? data : []); }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  return (
    <div className="content">
      <div className="section-header"><div><h1 className="page-title">{copy.title}</h1><p className="page-subtitle">{copy.subtitle}</p></div><Button onClick={load}>{loading ? copy.refreshing : copy.refresh}</Button></div>
      {error && <div className="alert alert-danger">{error}</div>}
      {loading ? <div className="skeleton-stack-lg"><div className="skeleton skeleton-row" /><div className="skeleton skeleton-row" /></div> : tests.length === 0 ? <div className="empty-state-stack"><p className="muted">{copy.empty}</p></div> : (
        <div className="stack-gap-4">
          {tests.map((t, i) => {
            const status = String(t.status || "");
            const summary = String(t.summary || t.name || `Test ${i + 1}`);
            const command = String(t.command || "");
            const failureInfo = String(t.failure_info || t.error || "");
            return (
              <Card key={i}>
                <CardHeader className="row-between-mb-2">
                  <CardTitle>{summary}</CardTitle>
                  <Badge variant={statusVariant(status)}>{statusLabelDesktop(status, locale)}</Badge>
                </CardHeader>
                <CardBody>
                  {command && <p className="mono text-xs muted">{command}</p>}
                  {failureInfo && <p className="cell-danger text-sm mt-2">{failureInfo}</p>}
                </CardBody>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
