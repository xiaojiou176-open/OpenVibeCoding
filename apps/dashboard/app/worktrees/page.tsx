import { Badge } from "../../components/ui/badge";
import { Card } from "../../components/ui/card";
import { fetchWorktrees } from "../../lib/api";
import { safeLoad } from "../../lib/serverPageData";

export default async function WorktreesPage() {
  const { data: worktrees, warning } = await safeLoad(fetchWorktrees, [] as Record<string, unknown>[], "Worktree list");

  return (
    <main className="grid" aria-labelledby="worktrees-page-title">
      <header className="app-section">
        <div className="section-header">
          <div>
            <h1 id="worktrees-page-title" className="page-title">Worktrees</h1>
            <p className="page-subtitle">Inspect worktree paths, branches, head commits, and lock state.</p>
          </div>
          <Badge>{worktrees.length} worktrees</Badge>
        </div>
      </header>
      <section className="app-section" aria-label="Worktree list">
        {warning ? <p className="alert alert-warning" role="status">{warning}</p> : null}
        {worktrees.length === 0 ? (
          <Card>
            <div className="empty-state-stack">
              <span className="muted">No worktrees yet</span>
              <span className="mono muted">Records appear here after an agent creates a worktree.</span>
            </div>
          </Card>
        ) : (
          <Card variant="table">
            <table className="run-table">
              <caption className="sr-only">Worktree list</caption>
              <thead>
                <tr>
                  <th scope="col">Path</th>
                  <th scope="col">Run ID</th>
                  <th scope="col">Branch</th>
                  <th scope="col">Head commit</th>
                  <th scope="col">Lock</th>
                </tr>
              </thead>
              <tbody>
                {worktrees.map((wt: Record<string, unknown>) => (
                  <tr key={`${wt.path}-${wt.branch}`}>
                    <th scope="row"><span className="chip">{String(wt.path)}</span></th>
                    <td><span className="mono">{String(wt.run_id || "-")}</span></td>
                    <td><Badge variant="running">{String(wt.branch || "-")}</Badge></td>
                    <td>
                      <span className="mono muted">
                        {String(wt.head || "-").length > 8 ? `${String(wt.head).slice(0, 8)}...` : String(wt.head || "-")}
                      </span>
                    </td>
                    <td>
                      {wt.locked ? (
                        <Badge variant="warning">Locked</Badge>
                      ) : (
                        <Badge variant="success">Idle</Badge>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
      </section>
    </main>
  );
}
