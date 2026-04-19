import { useCallback, useEffect, useState } from "react";
import type { UiLocale } from "@openvibecoding/frontend-shared/uiCopy";
import { detectPreferredUiLocale } from "@openvibecoding/frontend-shared/uiLocale";
import type { JsonValue } from "../lib/types";
import { fetchDiffGate, fetchDiff, rollbackRun, rejectRun } from "../lib/api";
import { badgeClass, statusLabelDesktop } from "../lib/statusPresentation";
import { toast } from "sonner";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";

export function ChangeGatesPage({ locale = detectPreferredUiLocale() as UiLocale }: { locale?: UiLocale } = {}) {
  const copy =
    locale === "zh-CN"
      ? {
          title: "Diff Gate",
          subtitle: "变更审查与回滚控制",
          refresh: "刷新",
          banner:
            "这个面板会把 gate 阻塞、缺少 review 真相、以及操作员动作分开显示。列表为空只代表当前没有待审记录，不代表历史变更都已经放行。",
          empty: "当前没有等待审查的 Diff Gate 记录。这只说明没有加载到当前待处理记录，不代表历史变更都已通过。",
          gateLabel: (index: number) => `Gate ${index}`,
          allowedPaths: (count: number) => `允许路径（${count}）`,
          hideDiff: "收起 diff",
          viewDiff: "查看 diff",
          rollback: "回滚",
          rejectChange: "拒绝变更",
          rollbackDone: "回滚动作已完成",
          rejectDone: "拒绝动作已完成",
          loadFailed: "（加载失败）",
          emptyDiff: "（空）",
        }
      : {
          title: "Diff gate",
          subtitle: "Diff Gate: change review and rollback control",
          refresh: "Refresh",
          banner:
            "This surface separates gate-blocked changes, missing review truth, and operator actions. An empty list is not proof that every historical change already passed.",
          empty: "No Diff Gate records are waiting for review right now. That means no current pending review record is loaded, not that every historical change is already approved.",
          gateLabel: (index: number) => `Gate ${index}`,
          allowedPaths: (count: number) => `Allowed paths (${count})`,
          hideDiff: "Hide diff",
          viewDiff: "View diff",
          rollback: "Rollback",
          rejectChange: "Reject change",
          rollbackDone: "Rollback action completed",
          rejectDone: "Reject action completed",
          loadFailed: "(load failed)",
          emptyDiff: "(empty)",
        };
  const [gates, setGates] = useState<Array<Record<string, JsonValue>>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [expandedDiff, setExpandedDiff] = useState<Record<string, string>>({});
  const [actionBusy, setActionBusy] = useState<Record<string, boolean>>({});

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { const data = await fetchDiffGate(); setGates(Array.isArray(data) ? data : []); }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function loadDiff(runId: string) {
    if (expandedDiff[runId] !== undefined) { setExpandedDiff((p) => { const n = { ...p }; delete n[runId]; return n; }); return; }
    try { const d = await fetchDiff(runId); setExpandedDiff((p) => ({ ...p, [runId]: d.diff || copy.emptyDiff })); }
    catch { setExpandedDiff((p) => ({ ...p, [runId]: copy.loadFailed })); }
  }

  async function handleAction(runId: string, action: "rollback" | "reject") {
    setActionBusy((p) => ({ ...p, [runId]: true }));
    try {
      if (action === "rollback") await rollbackRun(runId); else await rejectRun(runId);
      toast.success(action === "rollback" ? copy.rollbackDone : copy.rejectDone);
      void load();
    } catch (err) { toast.error(err instanceof Error ? err.message : String(err)); }
    finally { setActionBusy((p) => ({ ...p, [runId]: false })); }
  }

  return (
    <div className="content">
      <div className="section-header">
        <div><h1 className="page-title">{copy.title}</h1><p className="page-subtitle">{copy.subtitle}</p></div>
        <Button onClick={load} disabled={loading}>{copy.refresh}</Button>
      </div>
      <div className="alert alert-warning">
        {copy.banner}
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      {loading ? (
        <div className="skeleton-stack-lg"><div className="skeleton skeleton-card-tall" /><div className="skeleton skeleton-card-tall" /></div>
      ) : gates.length === 0 ? (
        <div className="empty-state-stack"><p className="muted">{copy.empty}</p></div>
      ) : (
        <div className="diff-gate-list">
          {gates.map((gate, i) => {
            const runId = String(gate.run_id || "");
            const status = String(gate.status || gate.gate_status || "");
            const allowedPaths = Array.isArray(gate.allowed_paths) ? gate.allowed_paths : [];
            const busy = !!actionBusy[runId];
            return (
              <div key={runId || i} className="diff-gate-item">
                <div className="diff-gate-item-header">
                  <span className="diff-gate-run-link mono">{runId || copy.gateLabel(i + 1)}</span>
                  <Badge className={badgeClass(status)}>{statusLabelDesktop(status, locale)}</Badge>
                </div>

                {gate.failure_reason && <div className="diff-gate-failure">{String(gate.failure_reason)}</div>}

                {/* Allowed paths -- same as Dashboard's DiffGatePanel */}
                {allowedPaths.length > 0 && (
                  <details className="collapsible">
                    <summary>{copy.allowedPaths(allowedPaths.length)}</summary>
                    <div className="collapsible-body">
                      <div className="chip-list">
                        {allowedPaths.map((p, j) => <span key={j} className="chip">{String(p)}</span>)}
                      </div>
                    </div>
                  </details>
                )}

                <div className="diff-gate-actions">
                  <Button variant="ghost" onClick={() => loadDiff(runId)}>
                    {expandedDiff[runId] !== undefined ? copy.hideDiff : copy.viewDiff}
                  </Button>
                  <Button variant="secondary" disabled={busy} onClick={() => handleAction(runId, "rollback")}>{copy.rollback}</Button>
                  <Button variant="destructive" disabled={busy} onClick={() => handleAction(runId, "reject")}>{copy.rejectChange}</Button>
                </div>

                {expandedDiff[runId] !== undefined && (
                  <div className="diff-gate-diff-region">
                    <pre className="pre-scroll-400">{expandedDiff[runId]}</pre>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
