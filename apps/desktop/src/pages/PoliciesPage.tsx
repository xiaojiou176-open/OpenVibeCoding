import { useCallback, useEffect, useState } from "react";
import type { JsonValue } from "../lib/types";
import { fetchPolicies } from "../lib/api";
import { Button } from "../components/ui/Button";
import { Card, CardBody, CardHeader, CardTitle } from "../components/ui/Card";

const POLICY_SECTIONS = [
  "control_plane_runtime_policy",
  "agent_registry",
  "command_allowlist",
  "forbidden_actions",
  "tool_registry",
] as const;
const SECTION_LABELS: Record<string, string> = {
  control_plane_runtime_policy: "Control-plane runtime policy",
  agent_registry: "Agent registry",
  command_allowlist: "Command allowlist",
  forbidden_actions: "Forbidden actions",
  tool_registry: "Tool registry",
};

export function PoliciesPage() {
  const [policies, setPolicies] = useState<Record<string, JsonValue>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { setPolicies(await fetchPolicies()); } catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  return (
    <div className="content">
      <div className="section-header"><div><h1 className="page-title">Policies</h1><p className="page-subtitle">Audit control-plane runtime rules, agent registry, command allowlist, tool permissions, and forbidden actions from one policy desk.</p></div><Button onClick={load} disabled={loading}>{loading ? "Refreshing..." : "Refresh"}</Button></div>
      {error && <div className="alert alert-danger" role="alert" aria-live="assertive">{error}</div>}
      {loading ? <div className="skeleton-stack-lg"><div className="skeleton skeleton-row" /><div className="skeleton skeleton-row" /></div> : (
        <div className="grid-2">
          {POLICY_SECTIONS.map((key) => {
            const data = policies[key];
            return (
              <Card key={key}>
                <CardHeader>
                  <CardTitle>{SECTION_LABELS[key] || key}</CardTitle>
                </CardHeader>
                <CardBody>
                  {data ? <pre className="pre-scroll-320">{typeof data === "string" ? data : JSON.stringify(data, null, 2)}</pre> : <p className="muted">No data</p>}
                </CardBody>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
