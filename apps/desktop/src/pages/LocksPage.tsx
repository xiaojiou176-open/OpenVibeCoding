import { useCallback, useEffect, useState } from "react";
import type { UiLocale } from "@openvibecoding/frontend-shared/uiCopy";
import { detectPreferredUiLocale } from "@openvibecoding/frontend-shared/uiLocale";
import type { JsonValue } from "../lib/types";
import { fetchLocks } from "../lib/api";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";

export function LocksPage({ locale = detectPreferredUiLocale() as UiLocale }: { locale?: UiLocale } = {}) {
  const copy =
    locale === "zh-CN"
      ? {
          title: "锁管理",
          subtitle: "查看文件锁和资源锁记录。",
          refresh: "刷新",
          refreshing: "刷新中...",
          empty: "当前还没有锁记录",
          headers: { path: "路径", holder: "持有者", type: "类型", acquiredAt: "获取时间", locked: "已锁定" },
        }
      : {
          title: "Locks",
          subtitle: "File-lock and resource-lock records",
          refresh: "Refresh",
          refreshing: "Refreshing...",
          empty: "No lock records yet",
          headers: { path: "Path", holder: "Holder", type: "Type", acquiredAt: "Acquired At", locked: "Locked" },
        };
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
      <div className="section-header"><div><h1 className="page-title">{copy.title}</h1><p className="page-subtitle">{copy.subtitle}</p></div><Button onClick={load}>{loading ? copy.refreshing : copy.refresh}</Button></div>
      {error && <div className="alert alert-danger">{error}</div>}
      {loading ? <div className="skeleton-stack-lg"><div className="skeleton skeleton-row" /><div className="skeleton skeleton-row" /></div> : locks.length === 0 ? <div className="empty-state-stack"><p className="muted">{copy.empty}</p></div> : (
        <Card>
          <table className="run-table">
            <thead><tr><th>{copy.headers.path}</th><th>{copy.headers.holder}</th><th>{copy.headers.type}</th><th>{copy.headers.acquiredAt}</th></tr></thead>
            <tbody>
              {locks.map((lock, i) => (
                <tr key={i}>
                  <td className="mono">{String(lock.path || lock.resource || "-")}</td>
                  <td>{String(lock.holder || lock.agent_id || "-")}</td>
                  <td className="muted">{String(lock.type || lock.lock_type || "-")}</td>
                  <td className="muted">{lock.acquired_at ? new Date(String(lock.acquired_at)).toLocaleString(locale === "zh-CN" ? "zh-CN" : "en-US") : "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
