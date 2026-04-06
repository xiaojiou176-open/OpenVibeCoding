import { useCallback, useEffect, useState } from "react";
import type { JsonValue } from "../lib/types";
import { fetchDiffGate, fetchDiff, rollbackRun, rejectRun } from "../lib/api";
import { statusLabelZh, badgeClass } from "../lib/statusPresentation";
import { toast } from "sonner";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";

export function ChangeGatesPage() {
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
    try { const d = await fetchDiff(runId); setExpandedDiff((p) => ({ ...p, [runId]: d.diff || "(empty)" })); }
    catch { setExpandedDiff((p) => ({ ...p, [runId]: "(load failed)" })); }
  }

  async function handleAction(runId: string, action: "rollback" | "reject") {
    setActionBusy((p) => ({ ...p, [runId]: true }));
    try {
      if (action === "rollback") await rollbackRun(runId); else await rejectRun(runId);
      toast.success(`${action === "rollback" ? "Rollback" : "Reject"} action completed`);
      void load();
    } catch (err) { toast.error(err instanceof Error ? err.message : String(err)); }
    finally { setActionBusy((p) => ({ ...p, [runId]: false })); }
  }

  return (
    <div className="content">
      <div className="section-header">
        <div><h1 className="page-title">Diff gate</h1><p className="page-subtitle">Diff Gate: change review and rollback control</p></div>
        <Button onClick={load} disabled={loading}>Refresh</Button>
      </div>
      <div className="alert alert-warning">
        This surface separates gate-blocked changes, missing review truth, and operator actions. An empty list is not proof that every historical change already passed.
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      {loading ? (
        <div className="skeleton-stack-lg"><div className="skeleton skeleton-card-tall" /><div className="skeleton skeleton-card-tall" /></div>
      ) : gates.length === 0 ? (
        <div className="empty-state-stack"><p className="muted">No Diff Gate records are waiting for review right now. That means no current pending review record is loaded, not that every historical change is already approved.</p></div>
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
                  <span className="diff-gate-run-link mono">{runId || `Gate ${i + 1}`}</span>
                  <Badge className={badgeClass(status)}>{statusLabelZh(status)}</Badge>
                </div>

                {gate.failure_reason && <div className="diff-gate-failure">{String(gate.failure_reason)}</div>}

                {/* Allowed paths -- same as Dashboard's DiffGatePanel */}
                {allowedPaths.length > 0 && (
                  <details className="collapsible">
                    <summary>Allowed paths ({allowedPaths.length})</summary>
                    <div className="collapsible-body">
                      <div className="chip-list">
                        {allowedPaths.map((p, j) => <span key={j} className="chip">{String(p)}</span>)}
                      </div>
                    </div>
                  </details>
                )}

                <div className="diff-gate-actions">
                  <Button variant="ghost" onClick={() => loadDiff(runId)}>
                    {expandedDiff[runId] !== undefined ? "Hide diff" : "View diff"}
                  </Button>
                  <Button variant="secondary" disabled={busy} onClick={() => handleAction(runId, "rollback")}>Rollback</Button>
                  <Button variant="destructive" disabled={busy} onClick={() => handleAction(runId, "reject")}>Reject change</Button>
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
