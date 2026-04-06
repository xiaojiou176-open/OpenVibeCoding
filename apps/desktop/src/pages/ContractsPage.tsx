import { useCallback, useEffect, useState } from "react";
import type { ContractRecord } from "../lib/types";
import { fetchContracts } from "../lib/api";
import { Button } from "../components/ui/Button";
import { Card, CardBody, CardHeader, CardTitle } from "../components/ui/Card";
import {
  formatBindingReadModelLabel,
  formatRoleBindingRuntimeCapabilitySummary,
  formatRoleBindingRuntimeSummary,
} from "../lib/types";

export function ContractsPage() {
  const [contracts, setContracts] = useState<ContractRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { const data = await fetchContracts(); setContracts(Array.isArray(data) ? data : []); }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  return (
    <div className="content">
      <div className="section-header"><div><h1 className="page-title">Contracts</h1><p className="page-subtitle">Read-only contract inspector for bundle posture, runtime binding, and task envelope detail.</p></div><Button onClick={load}>Refresh</Button></div>
      {error && <div className="alert alert-danger">{error}</div>}
      {loading ? <div className="skeleton-stack-lg"><div className="skeleton skeleton-row" /><div className="skeleton skeleton-row" /></div> : contracts.length === 0 ? <div className="empty-state-stack"><p className="muted">No contracts yet</p></div> : (
        <div className="grid-2">
          {contracts.map((c, i) => {
            const contract = c;
            const payload = c.payload || {};
            const hasToolPermissions =
              Boolean(contract.tool_permissions)
              && typeof contract.tool_permissions === "object"
              && !Array.isArray(contract.tool_permissions);
            return (
              <Card key={`${contract.task_id || contract.path || ""}-${i}`}>
                <CardHeader>
                  <CardTitle className="mono">{contract.task_id || contract.path || "Unknown contract"}</CardTitle>
                </CardHeader>
                <CardBody>
                  <div className="data-list">
                    {contract.run_id && <div className="data-list-row"><span className="data-list-label">Run ID</span><span className="data-list-value mono">{String(contract.run_id)}</span></div>}
                    <div className="data-list-row"><span className="data-list-label">Assigned role</span><span className="data-list-value">{contract.assigned_role || "Not assigned"}</span></div>
                    <div className="data-list-row"><span className="data-list-label">Execution authority</span><span className="data-list-value">{contract.execution_authority || "Not published"}</span></div>
                    <div className="data-list-row"><span className="data-list-label">Skills bundle</span><span className="data-list-value">{contract.role_binding_read_model ? formatBindingReadModelLabel(contract.role_binding_read_model.skills_bundle_ref) : "Not derived"}</span></div>
                    <div className="data-list-row"><span className="data-list-label">MCP bundle</span><span className="data-list-value">{contract.role_binding_read_model ? formatBindingReadModelLabel(contract.role_binding_read_model.mcp_bundle_ref) : "Not derived"}</span></div>
                    <div className="data-list-row"><span className="data-list-label">Runtime binding</span><span className="data-list-value mono">{contract.role_binding_read_model ? formatRoleBindingRuntimeSummary(contract.role_binding_read_model) : "Not derived"}</span></div>
                    <div className="data-list-row"><span className="data-list-label">Runtime capability</span><span className="data-list-value mono">{contract.role_binding_read_model?.runtime_binding?.capability?.lane || "Not derived"}</span></div>
                    <div className="data-list-row"><span className="data-list-label">Tool execution</span><span className="data-list-value mono">{contract.role_binding_read_model ? formatRoleBindingRuntimeCapabilitySummary(contract.role_binding_read_model) : "Not derived"}</span></div>
                    {contract.allowed_paths && (
                      <div className="data-list-row"><span className="data-list-label">Allowed paths</span><span className="data-list-value"><div className="chip-list">{contract.allowed_paths.map((p) => <span key={p} className="chip">{p}</span>)}</div></span></div>
                    )}
                    {contract.acceptance_tests && (
                      <div className="data-list-row"><span className="data-list-label">Acceptance tests</span><span className="data-list-value"><div className="chip-list">{contract.acceptance_tests.map((t) => <span key={t} className="chip">{t}</span>)}</div></span></div>
                    )}
                    {hasToolPermissions && (
                      <div className="data-list-row"><span className="data-list-label">Tool permissions</span><span className="data-list-value"><pre className="pre-reset">{JSON.stringify(contract.tool_permissions, null, 2)}</pre></span></div>
                    )}
                    {!hasToolPermissions && <div className="data-list-row"><span className="data-list-label">Contract payload</span><span className="data-list-value"><pre className="pre-reset">{JSON.stringify(payload, null, 2)}</pre></span></div>}
                  </div>
                </CardBody>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
