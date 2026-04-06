import { useCallback, useEffect, useState } from "react";
import type { JsonValue } from "../lib/types";
import { fetchWorktrees } from "../lib/api";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";

export function WorktreesPage() {
  const [trees, setTrees] = useState<Array<Record<string, JsonValue>>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { const data = await fetchWorktrees(); setTrees(Array.isArray(data) ? data : []); }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  return (
    <div className="content">
      <div className="section-header"><div><h1 className="page-title">Worktrees</h1><p className="page-subtitle">Git worktree status, branches, and lock information</p></div><Button onClick={load}>Refresh</Button></div>
      {error && <div className="alert alert-danger">{error}</div>}
      {loading ? <div className="skeleton-stack-lg"><div className="skeleton skeleton-row" /><div className="skeleton skeleton-row" /></div> : trees.length === 0 ? <div className="empty-state-stack"><p className="muted">No worktrees yet</p></div> : (
        <Card>
          <table className="run-table">
            <thead><tr><th>Path</th><th>Branch</th><th>Commit HEAD</th><th>Locked</th></tr></thead>
            <tbody>
              {trees.map((tree, i) => (
                <tr key={i}>
                  <td className="mono">{String(tree.path || "-")}</td>
                  <td>{String(tree.branch || "-")}</td>
                  <td className="mono">{String(tree.head || tree.commit || "-").slice(0, 12)}</td>
                  <td>{tree.locked ? <Badge variant="warning">Locked</Badge> : <span className="muted">-</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
