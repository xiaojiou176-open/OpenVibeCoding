import { useCallback, useEffect, useState } from "react";
import { getUiCopy, type UiLocale } from "@cortexpilot/frontend-shared/uiCopy";
import { detectPreferredUiLocale } from "@cortexpilot/frontend-shared/uiLocale";
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
  const locale: UiLocale = detectPreferredUiLocale();
  const contractsPageCopy = getUiCopy(locale).dashboard.contractsPage;
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
      <div className="section-header"><div><h1 className="page-title">{contractsPageCopy.title}</h1><p className="page-subtitle">{contractsPageCopy.subtitle}</p></div><Button onClick={load}>{locale === "zh-CN" ? "刷新" : "Refresh"}</Button></div>
      {error && <div className="alert alert-danger">{error}</div>}
      {loading ? <div className="skeleton-stack-lg"><div className="skeleton skeleton-row" /><div className="skeleton skeleton-row" /></div> : contracts.length === 0 ? <div className="empty-state-stack"><p className="muted">{contractsPageCopy.emptyTitle}</p><p className="muted">{contractsPageCopy.emptyHint}</p></div> : (
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
                  <CardTitle className="mono">{contract.task_id || contract.path || contractsPageCopy.fallbackValues.unknownContract}</CardTitle>
                </CardHeader>
                <CardBody>
                  <div className="data-list">
                    {contract.run_id && <div className="data-list-row"><span className="data-list-label">{contractsPageCopy.fieldLabels.runId}</span><span className="data-list-value mono">{String(contract.run_id)}</span></div>}
                    <div className="data-list-row"><span className="data-list-label">{contractsPageCopy.fieldLabels.assignedRole}</span><span className="data-list-value">{contract.assigned_role || contractsPageCopy.fallbackValues.notAssigned}</span></div>
                    <div className="data-list-row"><span className="data-list-label">{contractsPageCopy.fieldLabels.executionAuthority}</span><span className="data-list-value">{contract.execution_authority || contractsPageCopy.fallbackValues.notPublished}</span></div>
                    <div className="data-list-row"><span className="data-list-label">{contractsPageCopy.fieldLabels.skillsBundle}</span><span className="data-list-value">{contract.role_binding_read_model ? formatBindingReadModelLabel(contract.role_binding_read_model.skills_bundle_ref) : contractsPageCopy.fallbackValues.notDerived}</span></div>
                    <div className="data-list-row"><span className="data-list-label">{contractsPageCopy.fieldLabels.mcpBundle}</span><span className="data-list-value">{contract.role_binding_read_model ? formatBindingReadModelLabel(contract.role_binding_read_model.mcp_bundle_ref) : contractsPageCopy.fallbackValues.notDerived}</span></div>
                    <div className="data-list-row"><span className="data-list-label">{contractsPageCopy.fieldLabels.runtimeBinding}</span><span className="data-list-value mono">{contract.role_binding_read_model ? formatRoleBindingRuntimeSummary(contract.role_binding_read_model) : contractsPageCopy.fallbackValues.notDerived}</span></div>
                    <div className="data-list-row"><span className="data-list-label">{contractsPageCopy.fieldLabels.runtimeCapability}</span><span className="data-list-value mono">{contract.role_binding_read_model?.runtime_binding?.capability?.lane || contractsPageCopy.fallbackValues.notDerived}</span></div>
                    <div className="data-list-row"><span className="data-list-label">{contractsPageCopy.fieldLabels.toolExecution}</span><span className="data-list-value mono">{contract.role_binding_read_model ? formatRoleBindingRuntimeCapabilitySummary(contract.role_binding_read_model) : contractsPageCopy.fallbackValues.notDerived}</span></div>
                    {contract.allowed_paths && (
                      <div className="data-list-row"><span className="data-list-label">{contractsPageCopy.fieldLabels.allowedPaths}</span><span className="data-list-value"><div className="chip-list">{contract.allowed_paths.map((p) => <span key={p} className="chip">{p}</span>)}</div></span></div>
                    )}
                    {contract.acceptance_tests && (
                      <div className="data-list-row"><span className="data-list-label">{contractsPageCopy.fieldLabels.acceptanceTests}</span><span className="data-list-value"><div className="chip-list">{contract.acceptance_tests.map((t) => <span key={t} className="chip">{t}</span>)}</div></span></div>
                    )}
                    {hasToolPermissions && (
                      <div className="data-list-row"><span className="data-list-label">{contractsPageCopy.fieldLabels.toolPermissions}</span><span className="data-list-value"><pre className="pre-reset">{JSON.stringify(contract.tool_permissions, null, 2)}</pre></span></div>
                    )}
                    {!hasToolPermissions && <div className="data-list-row"><span className="data-list-label">{contractsPageCopy.fullJsonSummary}</span><span className="data-list-value"><pre className="pre-reset">{JSON.stringify(payload, null, 2)}</pre></span></div>}
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
