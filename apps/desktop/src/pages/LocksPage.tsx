import { useCallback, useEffect, useState } from "react";
import type { JsonValue } from "../lib/types";
import { fetchLocks } from "../lib/api";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";

export function LocksPage() {
  const [locks, setLocks] = useState<Array<Record<string, JsonValue>>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { const data = await fetchLocks(); setLocks(Array.isArray(data) ? data : []); }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  return (
    <div className="content">
      <div className="section-header"><div><h1 className="page-title">Locks</h1><p className="page-subtitle">File-lock and resource-lock records</p></div><Button onClick={load}>Refresh</Button></div>
      {error && <div className="alert alert-danger">{error}</div>}
      {loading ? <div className="skeleton-stack-lg"><div className="skeleton skeleton-row" /><div className="skeleton skeleton-row" /></div> : locks.length === 0 ? <div className="empty-state-stack"><p className="muted">No lock records yet</p></div> : (
        <Card>
          <table className="run-table">
            <thead><tr><th>Path</th><th>Holder</th><th>Type</th><th>Acquired At</th></tr></thead>
            <tbody>
              {locks.map((lock, i) => (
                <tr key={i}>
                  <td className="mono">{String(lock.path || lock.resource || "-")}</td>
                  <td>{String(lock.holder || lock.agent_id || "-")}</td>
                  <td className="muted">{String(lock.type || lock.lock_type || "-")}</td>
                  <td className="muted">{lock.acquired_at ? new Date(String(lock.acquired_at)).toLocaleString("zh-CN") : "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
