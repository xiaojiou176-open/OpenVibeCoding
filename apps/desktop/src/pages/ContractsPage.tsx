import { useCallback, useEffect, useState } from "react";
import { getUiCopy, type UiLocale } from "@openvibecoding/frontend-shared/uiCopy";
import { detectPreferredUiLocale } from "@openvibecoding/frontend-shared/uiLocale";
import type { ContractRecord } from "../lib/types";
import { fetchContracts } from "../lib/api";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card, CardBody, CardHeader, CardTitle } from "../components/ui/Card";
import {
  formatBindingReadModelLabel,
  formatRoleBindingRuntimeCapabilitySummary,
  formatRoleBindingRuntimeSummary,
} from "../lib/types";

type ContractsPageProps = {
  onNavigate?: (page: "command-tower" | "workflows" | "agents" | "runs") => void;
  onNavigateToRun?: (runId: string) => void;
};

export function ContractsPage({ onNavigate, onNavigateToRun }: ContractsPageProps = {}) {
  const locale: UiLocale = detectPreferredUiLocale();
  const contractsPageCopy = getUiCopy(locale).dashboard.contractsPage;
  const shellCopy =
    locale === "zh-CN"
      ? {
          actionTitle: "先处理哪份 contract",
          actionSubtitle: "先看哪份 contract 缺执行权、缺 run 或缺验收，再决定回到哪个 desk 继续处理。",
          openTower: "打开指挥塔",
          openProof: "打开证明室",
          openRoleDesk: "查看角色桌",
          riskTitle: "需要先分诊的 contract",
          riskHint: "缺 execution authority、缺 linked run 或缺 acceptance tests 的 contract 优先处理。",
          proofTitle: "已连到证明室",
          proofHint: "已经能直接回到 run / proof room 的 contract 数量。",
          authorityTitle: "执行权已可读",
          authorityHint: "首屏已经能直接判断 execution authority 的 contract 数量。",
          triageDeskTitle: "Contract 分诊队列",
          triageDeskSubtitle: "先看哪份 contract 缺执行权、缺 run 或缺验收，再决定回到哪个 desk 继续处理。",
          triageHeaders: {
            contract: "Contract",
            role: "角色",
            blocker: "下一阻塞点",
            action: "下一步",
          },
          blockerReady: "已可进入证明复核",
          blockerMissingAuthority: "缺执行权",
          blockerMissingRun: "缺关联 run",
          blockerMissingTests: "缺验收测试",
          nextActionHintWithRun: "先回到关联 run，再决定是否继续执行。",
          nextActionHintWithoutRun: "这份 contract 还需要回到 workflow 或 role desk 先分诊。",
          secondaryDetailsSummary: "Execution details",
        }
      : {
          actionTitle: "Start with the contract that needs triage",
          actionSubtitle:
            "Check which contracts are missing execution authority, linked runs, or acceptance tests before you trust them to continue.",
          openTower: "Open command tower",
          openProof: "Open proof room",
          openRoleDesk: "Inspect role desk",
          riskTitle: "Contracts needing triage",
          riskHint: "Prioritise contracts missing execution authority, linked runs, or acceptance tests.",
          proofTitle: "Contracts linked to proof",
          proofHint: "Contracts that already point back to a run / proof room.",
          authorityTitle: "Readable execution authority",
          authorityHint: "Contracts whose execution authority is already explicit on the first screen.",
          triageDeskTitle: "Contract triage queue",
          triageDeskSubtitle:
            "Start from the contract that is missing authority, run linkage, or acceptance evidence, then open proof or the role desk from there.",
          triageHeaders: {
            contract: "Contract",
            role: "Role",
            blocker: "Next blocker",
            action: "Next action",
          },
          blockerReady: "Ready for proof review",
          blockerMissingAuthority: "Missing execution authority",
          blockerMissingRun: "Missing linked run",
          blockerMissingTests: "Missing acceptance tests",
          nextActionHintWithRun: "Return to the linked run first, then decide whether the contract can continue.",
          nextActionHintWithoutRun: "This contract still needs workflow or role triage before you trust it to continue.",
          secondaryDetailsSummary: "Execution details",
        };
  const [contracts, setContracts] = useState<ContractRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { const data = await fetchContracts(); setContracts(Array.isArray(data) ? data : []); }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); } finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  const contractsNeedingTriage = contracts.filter((contract) => {
    const acceptanceTests = Array.isArray(contract.acceptance_tests) ? contract.acceptance_tests : [];
    return !contract.execution_authority || !contract.run_id || acceptanceTests.length === 0;
  }).length;
  const contractsWithRuns = contracts.filter((contract) => Boolean(contract.run_id)).length;
  const contractsWithAuthority = contracts.filter((contract) => Boolean(contract.execution_authority)).length;

  return (
    <div className="content">
      <div className="section-header"><div><h1 className="page-title">{contractsPageCopy.title}</h1><p className="page-subtitle">{contractsPageCopy.subtitle}</p></div><Button onClick={load}>{locale === "zh-CN" ? "刷新" : "Refresh"}</Button></div>
      <section className="app-section" aria-label={shellCopy.actionTitle}>
        <div className="section-header">
          <div>
            <h2 className="section-title">{shellCopy.actionTitle}</h2>
            <p className="section-subtitle">{shellCopy.actionSubtitle}</p>
          </div>
          {onNavigate ? (
            <div className="toolbar">
              <Button variant="secondary" onClick={() => onNavigate("command-tower")}>{shellCopy.openTower}</Button>
              <Button variant="secondary" onClick={() => onNavigate("runs")}>{shellCopy.openProof}</Button>
              <Button variant="secondary" onClick={() => onNavigate("agents")}>{shellCopy.openRoleDesk}</Button>
            </div>
          ) : null}
        </div>
        <div className="stats-grid" aria-label="Contract desk summary">
          <article className="metric-card">
            <p className="metric-label">{shellCopy.riskTitle}</p>
            <p className={`metric-value ${contractsNeedingTriage > 0 ? "metric-value--warning" : "metric-value--success"}`}>{contractsNeedingTriage}</p>
            <p className="muted text-xs">{shellCopy.riskHint}</p>
          </article>
          <article className="metric-card">
            <p className="metric-label">{shellCopy.proofTitle}</p>
            <p className="metric-value metric-value--primary">{contractsWithRuns}</p>
            <p className="muted text-xs">{shellCopy.proofHint}</p>
          </article>
          <article className="metric-card">
            <p className="metric-label">{shellCopy.authorityTitle}</p>
            <p className="metric-value metric-value--success">{contractsWithAuthority}</p>
            <p className="muted text-xs">{shellCopy.authorityHint}</p>
          </article>
        </div>
      </section>
      {error && <div className="alert alert-danger">{error}</div>}
      {contracts.length > 0 ? (
        <section className="app-section" aria-label={shellCopy.triageDeskTitle}>
          <h2 className="section-title">{shellCopy.triageDeskTitle}</h2>
          <p className="section-subtitle">{shellCopy.triageDeskSubtitle}</p>
          <Card className="table-card">
            <table className="run-table">
              <thead>
                <tr>
                  <th>{shellCopy.triageHeaders.contract}</th>
                  <th>{shellCopy.triageHeaders.role}</th>
                  <th>{shellCopy.triageHeaders.blocker}</th>
                  <th>{shellCopy.triageHeaders.action}</th>
                </tr>
              </thead>
              <tbody>
                {contracts.map((contract, index) => {
                  const acceptanceTests = Array.isArray(contract.acceptance_tests) ? contract.acceptance_tests : [];
                  const blockers = [
                    !contract.execution_authority ? shellCopy.blockerMissingAuthority : "",
                    !contract.run_id ? shellCopy.blockerMissingRun : "",
                    acceptanceTests.length === 0 ? shellCopy.blockerMissingTests : "",
                  ].filter(Boolean);
                  const runId = String(contract.run_id || "").trim();
                  return (
                    <tr key={`triage:${contract.task_id || contract.path || index}`}>
                      <th scope="row" className="mono">{contract.task_id || contract.path || contractsPageCopy.fallbackValues.unknownContract}</th>
                      <td>{contract.assigned_role || contractsPageCopy.fallbackValues.notAssigned}</td>
                      <td>
                        <Badge variant={blockers.length > 0 ? "warning" : "success"}>
                          {blockers.length > 0 ? blockers.join(" / ") : shellCopy.blockerReady}
                        </Badge>
                      </td>
                      <td>
                        <div className="toolbar">
                          {runId && onNavigateToRun ? (
                            <Button onClick={() => onNavigateToRun(runId)}>{shellCopy.openProof}</Button>
                          ) : null}
                          {onNavigate ? (
                            <Button variant="secondary" onClick={() => onNavigate(contract.assigned_role ? "agents" : "workflows")}>
                              {contract.assigned_role ? shellCopy.openRoleDesk : shellCopy.openTower}
                            </Button>
                          ) : null}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </Card>
        </section>
      ) : null}
      {loading ? <div className="skeleton-stack-lg"><div className="skeleton skeleton-row" /><div className="skeleton skeleton-row" /></div> : contracts.length === 0 ? <div className="empty-state-stack"><p className="muted">{contractsPageCopy.emptyTitle}</p><p className="muted">{contractsPageCopy.emptyHint}</p></div> : (
        <div className="grid-2">
          {contracts.map((c, i) => {
            const contract = c;
            const payload = c.payload || {};
            const hasToolPermissions =
              Boolean(contract.tool_permissions)
              && typeof contract.tool_permissions === "object"
              && !Array.isArray(contract.tool_permissions);
            const runId = String(contract.run_id || "").trim();
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
                    {contract.allowed_paths && (
                      <div className="data-list-row"><span className="data-list-label">{contractsPageCopy.fieldLabels.allowedPaths}</span><span className="data-list-value"><div className="chip-list">{contract.allowed_paths.map((p) => <span key={p} className="chip">{p}</span>)}</div></span></div>
                    )}
                    {contract.acceptance_tests && (
                      <div className="data-list-row"><span className="data-list-label">{contractsPageCopy.fieldLabels.acceptanceTests}</span><span className="data-list-value"><div className="chip-list">{contract.acceptance_tests.map((t) => <span key={t} className="chip">{t}</span>)}</div></span></div>
                    )}
                  </div>
                  {(onNavigate || onNavigateToRun) ? (
                    <div className="toolbar mt-4">
                      {runId && onNavigateToRun ? (
                        <Button onClick={() => onNavigateToRun(runId)}>{shellCopy.openProof}</Button>
                      ) : null}
                      {onNavigate ? (
                        <Button variant="secondary" onClick={() => onNavigate(contract.assigned_role ? "agents" : "workflows")}>
                          {contract.assigned_role ? shellCopy.openRoleDesk : shellCopy.openTower}
                        </Button>
                      ) : null}
                    </div>
                  ) : null}
                  <p className="muted text-xs mt-3">
                    {runId ? shellCopy.nextActionHintWithRun : shellCopy.nextActionHintWithoutRun}
                  </p>
                  <details className="collapsible mt-4">
                    <summary>{shellCopy.secondaryDetailsSummary}</summary>
                    <div className="collapsible-body">
                      <div className="data-list">
                        <div className="data-list-row"><span className="data-list-label">{contractsPageCopy.fieldLabels.skillsBundle}</span><span className="data-list-value">{contract.role_binding_read_model ? formatBindingReadModelLabel(contract.role_binding_read_model.skills_bundle_ref) : contractsPageCopy.fallbackValues.notDerived}</span></div>
                        <div className="data-list-row"><span className="data-list-label">{contractsPageCopy.fieldLabels.mcpBundle}</span><span className="data-list-value">{contract.role_binding_read_model ? formatBindingReadModelLabel(contract.role_binding_read_model.mcp_bundle_ref) : contractsPageCopy.fallbackValues.notDerived}</span></div>
                        <div className="data-list-row"><span className="data-list-label">{contractsPageCopy.fieldLabels.runtimeBinding}</span><span className="data-list-value mono">{contract.role_binding_read_model ? formatRoleBindingRuntimeSummary(contract.role_binding_read_model) : contractsPageCopy.fallbackValues.notDerived}</span></div>
                        <div className="data-list-row"><span className="data-list-label">{contractsPageCopy.fieldLabels.runtimeCapability}</span><span className="data-list-value mono">{contract.role_binding_read_model?.runtime_binding?.capability?.lane || contractsPageCopy.fallbackValues.notDerived}</span></div>
                        <div className="data-list-row"><span className="data-list-label">{contractsPageCopy.fieldLabels.toolExecution}</span><span className="data-list-value mono">{contract.role_binding_read_model ? formatRoleBindingRuntimeCapabilitySummary(contract.role_binding_read_model) : contractsPageCopy.fallbackValues.notDerived}</span></div>
                        {hasToolPermissions ? (
                          <div className="data-list-row"><span className="data-list-label">{contractsPageCopy.fieldLabels.toolPermissions}</span><span className="data-list-value"><pre className="pre-reset">{JSON.stringify(contract.tool_permissions, null, 2)}</pre></span></div>
                        ) : (
                          <div className="data-list-row"><span className="data-list-label">{contractsPageCopy.fullJsonSummary}</span><span className="data-list-value"><pre className="pre-reset">{JSON.stringify(payload, null, 2)}</pre></span></div>
                        )}
                      </div>
                    </div>
                  </details>
                </CardBody>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
