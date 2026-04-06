import { useCallback, useEffect, useState } from "react";
import type { AgentCatalogPayload, AgentCatalogRecord, AgentStatusPayload, AgentStatusRecord, RoleCatalogRecord } from "../lib/types";
import { fetchAgents, fetchAgentStatus } from "../lib/api";
import { stageVariant } from "../lib/statusPresentation";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import { Card } from "../components/ui/Card";
import { formatBindingReadModelLabel, formatRoleBindingRuntimeSummary } from "../lib/types";
import { AgentsRoleConfigPanel } from "./AgentsRoleConfigPanel";

function stageBadgeVariant(stage: string | null | undefined): "default" | "success" | "warning" | "info" | "running" {
  const variant = stageVariant(stage);
  if (variant === "todo") return "warning";
  if (variant === "active") return "running";
  if (variant === "verify") return "info";
  if (variant === "done") return "success";
  return "default";
}

export function AgentsPage() {
  const [agents, setAgents] = useState<AgentCatalogPayload>({ agents: [], locks: [], role_catalog: [] });
  const [agentStatus, setAgentStatus] = useState<AgentStatusPayload>({ agents: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [a, s] = await Promise.all([fetchAgents(), fetchAgentStatus()]);
      setAgents(a || { agents: [], locks: [], role_catalog: [] });
      setAgentStatus(s || { agents: [] });
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const registry = Array.isArray(agents.agents) ? agents.agents : [];
  const roleCatalog = Array.isArray(agents.role_catalog) ? agents.role_catalog : [];
  const runtimeStates = Array.isArray(agentStatus.agents) ? agentStatus.agents : [];

  function renderRoleCatalogRow(roleEntry: RoleCatalogRecord) {
    return (
      <tr key={`role-${roleEntry.role}`}>
        <td>
          <div className="stack-gap-2">
            <Badge>{roleEntry.role}</Badge>
            <span className="muted">{roleEntry.purpose || "No role purpose published yet"}</span>
          </div>
        </td>
        <td className="muted">{formatBindingReadModelLabel(roleEntry.role_binding_read_model.skills_bundle_ref)}</td>
        <td className="muted">{formatBindingReadModelLabel(roleEntry.role_binding_read_model.mcp_bundle_ref)}</td>
        <td className="mono muted">{formatRoleBindingRuntimeSummary(roleEntry.role_binding_read_model)}</td>
        <td>
          <div className="stack-gap-2">
            <Badge className="ui-badge ui-badge--running">{roleEntry.role_binding_read_model.execution_authority}</Badge>
            <span className="muted">Read-only derived mirror</span>
          </div>
        </td>
      </tr>
    );
  }

  function renderRuntimeRow(snapshot: AgentStatusRecord, index: number) {
    return (
      <tr key={`${snapshot.run_id || "run"}-${snapshot.agent_id || "agent"}-${index}`}>
        <td className="mono">{String(snapshot.agent_id || "-")}</td>
        <td>{String(snapshot.role || "-")}</td>
        <td><Badge variant={stageBadgeVariant(snapshot.stage)}>{String(snapshot.stage || "-")}</Badge></td>
        <td className="mono">{String(snapshot.run_id || "-").slice(0, 12)}</td>
      </tr>
    );
  }

  function renderRegistryRow(agent: AgentCatalogRecord, index: number) {
    return (
      <tr key={`${agent.agent_id || "agent"}-${index}`}>
        <td className="mono">{String(agent.agent_id || "-")}</td>
        <td>{String(agent.role || "-")}</td>
        <td className="muted">{String(agent.notes || "-")}</td>
        <td className="muted">{String(agent.lock_count || 0)}</td>
      </tr>
    );
  }

  return (
    <div className="content">
      <div className="section-header"><div><h1 className="page-title">Agents</h1><p className="page-subtitle">Read-only role catalog, active state machines, and registered execution seats.</p></div><Button onClick={load} disabled={loading}>{loading ? "Refreshing..." : "Refresh"}</Button></div>
      {error && <div className="alert alert-danger" role="alert" aria-live="assertive">{error}</div>}
      {loading ? <div className="skeleton-stack-lg"><div className="skeleton skeleton-card-tall" /><div className="skeleton skeleton-card-tall" /></div> : (
        <div className="grid">
          <AgentsRoleConfigPanel roleCatalog={roleCatalog} onApplied={load} />
          <div className="app-section"><h2 className="section-title">Role Catalog ({roleCatalog.length})</h2>
            {roleCatalog.length === 0 ? <div className="empty-state-stack"><p className="muted">No role catalog entries yet</p></div> : (
              <Card className="table-card"><table className="run-table"><thead><tr><th>Role</th><th>Skills bundle</th><th>MCP bundle</th><th>Runtime binding</th><th>Execution authority</th></tr></thead>
                <tbody>{roleCatalog.map((roleEntry) => renderRoleCatalogRow(roleEntry))}</tbody></table></Card>
            )}
          </div>
          {runtimeStates.length > 0 && (
            <div className="app-section"><h2 className="section-title">Active State Machines</h2>
              <Card className="table-card"><table className="run-table"><thead><tr><th>Agent ID</th><th>Role</th><th>Status</th><th>Run ID</th></tr></thead>
                <tbody>{runtimeStates.map((snapshot, index) => renderRuntimeRow(snapshot, index))}</tbody></table></Card>
            </div>
          )}
          <div className="app-section"><h2 className="section-title">Registered Agents ({registry.length})</h2>
            {registry.length === 0 ? <div className="empty-state-stack"><p className="muted">No agents are registered yet</p></div> : (
              <Card className="table-card"><table className="run-table"><thead><tr><th>Agent ID</th><th>Role</th><th>Notes</th><th>Locks</th></tr></thead>
                <tbody>{registry.map((agent, index) => renderRegistryRow(agent, index))}</tbody></table></Card>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
