import { useCallback, useEffect, useState } from "react";
import type { UiLocale } from "@openvibecoding/frontend-shared/uiCopy";
import { detectPreferredUiLocale } from "@openvibecoding/frontend-shared/uiLocale";
import type { JsonValue } from "../lib/types";
import { fetchWorktrees } from "../lib/api";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";

export function WorktreesPage({ locale = detectPreferredUiLocale() as UiLocale }: { locale?: UiLocale } = {}) {
  const copy =
    locale === "zh-CN"
      ? {
          title: "工作树",
          subtitle: "查看 Git 工作树状态、分支和锁信息。",
          refresh: "刷新",
          refreshing: "刷新中...",
          empty: "当前还没有工作树",
          headers: { path: "路径", branch: "分支", head: "提交 HEAD", locked: "锁状态", lockedLabel: "已锁定" },
        }
      : {
          title: "Worktrees",
          subtitle: "Git worktree status, branches, and lock information",
          refresh: "Refresh",
          refreshing: "Refreshing...",
          empty: "No worktrees yet",
          headers: { path: "Path", branch: "Branch", head: "Commit HEAD", locked: "Locked", lockedLabel: "Locked" },
        };
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
      <div className="section-header"><div><h1 className="page-title">{copy.title}</h1><p className="page-subtitle">{copy.subtitle}</p></div><Button onClick={load}>{loading ? copy.refreshing : copy.refresh}</Button></div>
      {error && <div className="alert alert-danger">{error}</div>}
      {loading ? <div className="skeleton-stack-lg"><div className="skeleton skeleton-row" /><div className="skeleton skeleton-row" /></div> : trees.length === 0 ? <div className="empty-state-stack"><p className="muted">{copy.empty}</p></div> : (
        <Card>
          <table className="run-table">
            <thead><tr><th>{copy.headers.path}</th><th>{copy.headers.branch}</th><th>{copy.headers.head}</th><th>{copy.headers.locked}</th></tr></thead>
            <tbody>
              {trees.map((tree, i) => (
                <tr key={i}>
                  <td className="mono">{String(tree.path || "-")}</td>
                  <td>{String(tree.branch || "-")}</td>
                  <td className="mono">{String(tree.head || tree.commit || "-").slice(0, 12)}</td>
                  <td>{tree.locked ? <Badge variant="warning">{copy.headers.lockedLabel}</Badge> : <span className="muted">-</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
