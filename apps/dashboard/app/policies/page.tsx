import { Badge } from "../../components/ui/badge";
import { Card, CardContent, CardHeader } from "../../components/ui/card";
import { fetchPolicies } from "../../lib/api";
import { safeLoad } from "../../lib/serverPageData";

const SECTIONS = [
  { title: "Agent registry", key: "agent_registry", desc: "Registered agent roles and permission mappings" },
  { title: "Command allowlist", key: "command_allowlist", desc: "System commands that operators may execute" },
  { title: "Forbidden actions", key: "forbidden_actions", desc: "Globally blocked high-risk actions" },
  { title: "Tool registry", key: "tool_registry", desc: "Tools available to control-plane agents" },
];

export default async function PoliciesPage() {
  const { data: policies, warning } = await safeLoad(fetchPolicies, {} as Record<string, unknown>, "Policy config");

  return (
    <main className="grid" aria-labelledby="policies-page-title">
      <header className="app-section">
        <div className="section-header">
          <div>
            <h1 id="policies-page-title" className="page-title">Policies</h1>
            <p className="page-subtitle">Audit agent, command, and tool-governance settings from one policy surface.</p>
          </div>
        </div>
      </header>
      <section className="app-section" aria-label="Policy sections">
        {warning ? (
          <Card asChild variant="unstyled">
            <p className="alert alert-warning" role="status">{warning}</p>
          </Card>
        ) : null}
        <div className="grid-2">
          {SECTIONS.map((section) => {
            const data = policies?.[section.key] ?? {};
            const isEmpty = typeof data === "object" && Object.keys(data).length === 0;
            return (
              <Card key={section.key} variant="detail">
                <CardHeader>
                  <div>
                    <span className="card-header-title">{section.title}</span>
                    <p className="policy-section-desc">
                      {section.desc}
                    </p>
                  </div>
                  {!isEmpty && (
                    <Badge variant="success">Configured</Badge>
                  )}
                </CardHeader>
                <CardContent className="policy-section-body">
                  {isEmpty ? (
                    <span className="muted policy-empty-text">Not configured</span>
                  ) : (
                    <pre className="mono policy-json-pre">
                      {JSON.stringify(data, null, 2)}
                    </pre>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      </section>
    </main>
  );
}
