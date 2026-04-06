import { useCallback, useEffect, useState } from "react";
import type { JsonValue } from "../lib/types";
import { fetchTests } from "../lib/api";
import { statusLabelZh, statusVariant } from "../lib/statusPresentation";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card, CardBody, CardHeader, CardTitle } from "../components/ui/Card";

export function TestsPage() {
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
      <div className="section-header"><div><h1 className="page-title">Tests</h1><p className="page-subtitle">Acceptance-test and regression-test results</p></div><Button onClick={load}>Refresh</Button></div>
      {error && <div className="alert alert-danger">{error}</div>}
      {loading ? <div className="skeleton-stack-lg"><div className="skeleton skeleton-row" /><div className="skeleton skeleton-row" /></div> : tests.length === 0 ? <div className="empty-state-stack"><p className="muted">No test records yet</p></div> : (
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
                  <Badge variant={statusVariant(status)}>{statusLabelZh(status)}</Badge>
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
