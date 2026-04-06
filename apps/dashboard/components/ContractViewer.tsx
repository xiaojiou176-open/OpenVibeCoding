import type { RunContract } from "../lib/types";
import { Badge } from "./ui/badge";
import { Card } from "./ui/card";

function countLabel(count: number, singular: string, plural: string): string {
  return `${count} ${count === 1 ? singular : plural}`;
}

function FieldRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="contract-field-row">
      <span className="contract-field-label">
        {label}
      </span>
      <div className="contract-field-value">{children}</div>
    </div>
  );
}

export default function ContractViewer({
  contract,
  schemaVersion,
}: {
  contract: RunContract | null | undefined;
  schemaVersion?: string;
}) {
  const resolvedContract: RunContract = contract || {};
  const allowedPaths = Array.isArray(resolvedContract.allowed_paths) ? resolvedContract.allowed_paths : [];
  const acceptance = Array.isArray(resolvedContract.acceptance_tests) ? resolvedContract.acceptance_tests : [];
  const toolPermissions = resolvedContract.tool_permissions || {};
  const owner = resolvedContract.owner_agent || {};
  const assigned = resolvedContract.assigned_agent || {};
  const hasToolPermissions = Object.keys(toolPermissions).length > 0;

  return (
    <div className="contract-viewer">
      <div className="contract-viewer-header">
        <h4 className="contract-viewer-title">Contract</h4>
        <Badge>{schemaVersion || "v1"}</Badge>
      </div>

      <Card className="contract-viewer-card">
        <FieldRow label="Owner agent">
          <span className="mono">
            {owner.role || "-"} {owner.agent_id ? `(${owner.agent_id})` : ""}
          </span>
        </FieldRow>
        <FieldRow label="Assigned agent">
          <span className="mono">
            {assigned.role || "-"} {assigned.agent_id ? `(${assigned.agent_id})` : ""}
          </span>
        </FieldRow>
        <FieldRow label="Allowed paths">
          {allowedPaths.length > 0 ? (
            <div className="contract-chip-list">
              {allowedPaths.map((path, i) => (
                <Badge key={i}>{path}</Badge>
              ))}
            </div>
          ) : (
            <span className="muted">-</span>
          )}
        </FieldRow>
        <FieldRow label="Acceptance tests">
          <span className="mono">{countLabel(acceptance.length, "test", "tests")}</span>
        </FieldRow>
        <FieldRow label="Tool permissions">
          <span className="mono">{hasToolPermissions ? countLabel(Object.keys(toolPermissions).length, "permission", "permissions") : "None"}</span>
        </FieldRow>
      </Card>

      {(acceptance.length > 0 || hasToolPermissions) && (
        <details className="contract-json-details">
          <summary className="contract-json-summary">
            View full contract JSON
          </summary>
          <pre className="mono contract-json-body">
            {JSON.stringify(resolvedContract, null, 2)}
          </pre>
        </details>
      )}
    </div>
  );
}
