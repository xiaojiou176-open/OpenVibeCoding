import { cookies } from "next/headers";
import Link from "next/link";
import { getUiCopy } from "@cortexpilot/frontend-shared/uiCopy";
import { normalizeUiLocale, UI_LOCALE_STORAGE_KEY } from "@cortexpilot/frontend-shared/uiLocale";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader } from "../../components/ui/card";
import { Input } from "../../components/ui/input";
import { fetchContracts } from "../../lib/api";
import { safeLoad } from "../../lib/serverPageData";
import type { ContractRecord } from "../../lib/types";
import {
  formatBindingReadModelLabel,
  formatRoleBindingRuntimeCapabilitySummary,
  formatRoleBindingRuntimeSummary,
} from "../../lib/types";

function summarizeToolPermissions(value: unknown): string[] {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return [];
  }
  return Object.entries(value as Record<string, unknown>).map(([key, raw]) => `${key}: ${String(raw)}`);
}

const DEFAULT_CONTRACT_LIMIT = 10;

async function resolveDashboardLocale() {
  try {
    const cookieStore = await cookies();
    return normalizeUiLocale(cookieStore.get(UI_LOCALE_STORAGE_KEY)?.value);
  } catch {
    return normalizeUiLocale(undefined);
  }
}

export default async function ContractsPage({
  searchParams,
}: {
  searchParams?: Promise<{ q?: string; limit?: string }>;
}) {
  const locale = await resolveDashboardLocale();
  const contractsPageCopy = getUiCopy(locale).dashboard.contractsPage;
  const shellCopy =
    locale === "zh-CN"
      ? {
          actionTitle: "先做哪一步",
          actionSubtitle: "先确认哪份 contract 真能继续，哪份应该转去 Proof、Role 或 Workflow 再处理。",
          commandTowerAction: "打开 Command Tower",
          workflowAction: "打开 Workflow Cases",
          proofAction: "打开 Proof & Replay",
          riskTitle: "需要先处理的 contract",
          riskHint: "缺执行权、缺关联 run、或缺验收测试的 contract 优先处理。",
          proofLinkedTitle: "已绑定 Proof & Replay",
          proofLinkedHint: "已经能直接回到 run / proof room 的 contract 数量。",
          authorityTitle: "已发布执行权",
          authorityHint: "execution authority 已经明确对外可读的 contract 数量。",
          nextActionTitle: "下一步",
          openProofRoom: "打开关联证明室",
          inspectRoleDesk: "查看角色桌",
          inspectWorkflowDesk: "查看 Workflow desk",
          nextActionHintWithRun: "先回到 run / proof，确认这份 contract 当前是否真能继续。",
          nextActionHintWithoutRun:
            "这份 contract 还没有稳定的 run 下钻口，先回到 workflow 或 role desk 看 owner、authority 和 blocker。",
        }
      : {
          actionTitle: "Start with the next action",
          actionSubtitle:
            "Confirm which contracts can continue, which need proof review, and which should send you back to Workflow Cases or the role desk.",
          commandTowerAction: "Open Command Tower",
          workflowAction: "Open Workflow Cases",
          proofAction: "Open Proof & Replay",
          riskTitle: "Contracts needing triage",
          riskHint: "Prioritise contracts missing execution authority, linked runs, or acceptance tests.",
          proofLinkedTitle: "Contracts linked to proof",
          proofLinkedHint: "Contracts that already point straight back to a run / proof room.",
          authorityTitle: "Published execution authority",
          authorityHint: "Contracts whose execution authority is already explicit on the first screen.",
          nextActionTitle: "Next action",
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
          openProofRoom: "Open related proof room",
          inspectRoleDesk: "Inspect role desk",
          inspectWorkflowDesk: "Inspect workflow desk",
          nextActionHintWithRun:
            "Return to the related run first, then decide whether this contract is truly ready to continue.",
          nextActionHintWithoutRun:
            "This contract still needs workflow or role triage before you trust it to continue.",
          secondaryDetailsSummary: "Execution details",
        };
  const { data: contracts, warning } = await safeLoad(fetchContracts, [] as ContractRecord[], "Contract list");
  const resolvedSearchParams = (await searchParams) || {};
  const query = String(resolvedSearchParams.q || "").trim().toLowerCase();
  const limitRaw = Number.parseInt(String(resolvedSearchParams.limit || DEFAULT_CONTRACT_LIMIT), 10);
  const limit = Number.isFinite(limitRaw) && limitRaw > 0 ? limitRaw : DEFAULT_CONTRACT_LIMIT;
  const filteredContracts = contracts.filter((contract) => {
    if (!query) return true;
    const allowedPaths = Array.isArray(contract.allowed_paths) ? contract.allowed_paths : [];
    return [contract.path, contract.source, contract.task_id, contract.run_id, contract.assigned_role, ...allowedPaths.map((p) => String(p))]
      .map((value) => String(value || "").toLowerCase())
      .some((value) => value.includes(query));
  });
  const visibleContracts = filteredContracts.slice(0, limit);
  const canApplyFilter = Boolean(query);
  const contractsNeedingTriage = filteredContracts.filter((contract) => {
    const acceptanceTests = Array.isArray(contract.acceptance_tests) ? contract.acceptance_tests : [];
    return !contract.execution_authority || !contract.run_id || acceptanceTests.length === 0;
  }).length;
  const contractsWithRuns = filteredContracts.filter((contract) => Boolean(contract.run_id)).length;
  const contractsWithAuthority = filteredContracts.filter((contract) => Boolean(contract.execution_authority)).length;
  return (
    <main className="grid" aria-labelledby="contracts-page-title">
      <header className="app-section">
        <div className="section-header">
          <div>
            <h1 id="contracts-page-title" className="page-title">{contractsPageCopy.title}</h1>
            <p className="page-subtitle">{contractsPageCopy.subtitle}</p>
          </div>
          <Badge>{contractsPageCopy.countsBadge(contracts.length)}</Badge>
        </div>
        <div className="section-header">
          <div>
            <h2 className="section-title">{shellCopy.actionTitle}</h2>
            <p>{shellCopy.actionSubtitle}</p>
          </div>
          <nav aria-label="Contract desk actions">
            <Button asChild>
              <Link href="/command-tower">{shellCopy.commandTowerAction}</Link>
            </Button>
            <Button asChild variant="secondary">
              <Link href="/workflows">{shellCopy.workflowAction}</Link>
            </Button>
            <Button asChild variant="secondary">
              <Link href="/runs">{shellCopy.proofAction}</Link>
            </Button>
          </nav>
        </div>
        <div className="stats-grid" aria-label="Contract desk summary">
          <article className="metric-card">
            <p className="metric-label">{shellCopy.riskTitle}</p>
            <p className={`metric-value ${contractsNeedingTriage > 0 ? "metric-value--warning" : "metric-value--success"}`}>
              {contractsNeedingTriage}
            </p>
            <p className="muted text-xs">{shellCopy.riskHint}</p>
          </article>
          <article className="metric-card">
            <p className="metric-label">{shellCopy.proofLinkedTitle}</p>
            <p className="metric-value metric-value--primary">{contractsWithRuns}</p>
            <p className="muted text-xs">{shellCopy.proofLinkedHint}</p>
          </article>
          <article className="metric-card">
            <p className="metric-label">{shellCopy.authorityTitle}</p>
            <p className="metric-value metric-value--success">{contractsWithAuthority}</p>
            <p className="muted text-xs">{shellCopy.authorityHint}</p>
          </article>
        </div>
      </header>
      <section className="app-section" aria-label="Contract list">
        <Card>
          <form className="toolbar" method="get">
            <label className="diff-gate-filter-field">
              <span className="muted">{contractsPageCopy.searchLabel}</span>
              <Input type="search" name="q" defaultValue={query} placeholder={contractsPageCopy.searchPlaceholder} />
            </label>
            <input type="hidden" name="limit" value={String(limit)} />
            <Button type="submit" variant="secondary" disabled={!canApplyFilter}>{contractsPageCopy.applyFilter}</Button>
          </form>
          <p className="mono muted">
            {contractsPageCopy.filterSummary(visibleContracts.length, filteredContracts.length, DEFAULT_CONTRACT_LIMIT)}
          </p>
        </Card>
        {warning ? (
          <Card asChild variant="unstyled">
            <div className="alert alert-warning" role="status">
              <p>{contractsPageCopy.warningTitle}</p>
              <p className="mono">{contractsPageCopy.warningNextStep}</p>
              <p className="mono">{warning}</p>
            </div>
          </Card>
        ) : null}
        {visibleContracts.length > 0 ? (
          <Card variant="table">
            <div className="section-header">
              <div>
                <h2 className="section-title">{shellCopy.triageDeskTitle}</h2>
                <p>{shellCopy.triageDeskSubtitle}</p>
              </div>
            </div>
            <table className="run-table">
              <thead>
                <tr>
                  <th scope="col">{shellCopy.triageHeaders.contract}</th>
                  <th scope="col">{shellCopy.triageHeaders.role}</th>
                  <th scope="col">{shellCopy.triageHeaders.blocker}</th>
                  <th scope="col">{shellCopy.triageHeaders.action}</th>
                </tr>
              </thead>
              <tbody>
                {visibleContracts.map((contract, index) => {
                  const acceptanceTests = Array.isArray(contract.acceptance_tests) ? contract.acceptance_tests : [];
                  const blockers = [
                    !contract.execution_authority ? shellCopy.blockerMissingAuthority : "",
                    !contract.run_id ? shellCopy.blockerMissingRun : "",
                    acceptanceTests.length === 0 ? shellCopy.blockerMissingTests : "",
                  ].filter(Boolean);
                  const proofHref = contract.run_id ? `/runs/${contract.run_id}` : "/runs";
                  const roleDeskHref = contract.assigned_role
                    ? `/agents?role=${encodeURIComponent(String(contract.assigned_role))}`
                    : "/agents";
                  return (
                    <tr key={`triage:${contract.task_id || contract.path || index}`}>
                      <th scope="row">
                        <span className="mono" title={contract.path || contract.task_id || ""}>
                          {contract.task_id || contract.path || contractsPageCopy.fallbackValues.unknownContract}
                        </span>
                      </th>
                      <td>{contract.assigned_role || contractsPageCopy.fallbackValues.notAssigned}</td>
                      <td>
                        <Badge variant={blockers.length > 0 ? "warning" : "success"}>
                          {blockers.length > 0 ? blockers.join(" / ") : shellCopy.blockerReady}
                        </Badge>
                      </td>
                      <td>
                        <div className="toolbar">
                          <Button asChild>
                            <Link href={proofHref}>{shellCopy.openProofRoom}</Link>
                          </Button>
                          <Button asChild variant="secondary">
                            <Link href={roleDeskHref}>{shellCopy.inspectRoleDesk}</Link>
                          </Button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </Card>
        ) : null}
        {filteredContracts.length === 0 ? (
          <Card>
            <div className="empty-state-stack">
              <span className="muted">{contractsPageCopy.emptyTitle}</span>
              <span className="mono muted">{contractsPageCopy.emptyHint}</span>
            </div>
          </Card>
        ) : (
          <div className="grid-2">
            {visibleContracts.map((contract) => {
              const payload = contract.payload || {};
              const key = contract.path || contract.task_id || contract.run_id || JSON.stringify(payload).slice(0, 40);
              const allowedPaths = Array.isArray(contract.allowed_paths) ? contract.allowed_paths : [];
              const acceptanceTests = Array.isArray(contract.acceptance_tests) ? contract.acceptance_tests : [];
              const toolPermissions = contract.tool_permissions || {};
              const permissionSummary = summarizeToolPermissions(toolPermissions);
              const roleBinding = contract.role_binding_read_model;
              const proofHref = contract.run_id ? `/runs/${contract.run_id}` : "/runs";
              const roleDeskHref = contract.assigned_role
                ? `/agents?role=${encodeURIComponent(String(contract.assigned_role))}`
                : "/agents";
              return (
                <Card key={key} variant="detail">
                  <CardHeader>
                    <span className="card-header-title">
                      {contract.path || contract.task_id || contractsPageCopy.fallbackValues.unknownContract}
                    </span>
                    <Badge>{contract.source || contractsPageCopy.fallbackValues.unknownSource}</Badge>
                  </CardHeader>
                  <CardContent>
                    <div className="data-list">
                      {contract.task_id ? (
                        <div className="data-list-row">
                          <span className="data-list-label">{contractsPageCopy.fieldLabels.taskId}</span>
                          <span className="data-list-value mono">{contract.task_id}</span>
                        </div>
                      ) : null}
                      {contract.run_id ? (
                        <div className="data-list-row">
                          <span className="data-list-label">{contractsPageCopy.fieldLabels.runId}</span>
                          <span className="data-list-value mono">{contract.run_id}</span>
                        </div>
                      ) : null}
                      <div className="data-list-row">
                        <span className="data-list-label">{contractsPageCopy.fieldLabels.assignedRole}</span>
                        <span className="data-list-value">
                          {contract.assigned_role || contractsPageCopy.fallbackValues.notAssigned}
                        </span>
                      </div>
                      <div className="data-list-row">
                        <span className="data-list-label">{contractsPageCopy.fieldLabels.executionAuthority}</span>
                        <span className="data-list-value">
                          {contract.execution_authority ? (
                            <Badge variant="running">{contract.execution_authority}</Badge>
                          ) : (
                            <span className="muted">{contractsPageCopy.fallbackValues.notPublished}</span>
                          )}
                        </span>
                      </div>
                      <div className="data-list-row">
                        <span className="data-list-label">{contractsPageCopy.fieldLabels.allowedPaths}</span>
                        <span className="data-list-value">
                          {allowedPaths.length > 0 ? (
                            <span className="chip-list">
                              {allowedPaths.map((p) => (
                                <Badge key={String(p)} variant="unstyled" className="chip">{String(p)}</Badge>
                              ))}
                            </span>
                          ) : (
                            <span className="muted">{contractsPageCopy.fallbackValues.unrestricted}</span>
                          )}
                        </span>
                      </div>
                      <div className="data-list-row">
                        <span className="data-list-label">{contractsPageCopy.fieldLabels.acceptanceTests}</span>
                        <span className="data-list-value">
                          {acceptanceTests.length > 0 ? (
                            <span className="chip-list">
                              {acceptanceTests.map((t, i) => (
                                <Badge key={i} variant="unstyled" className="chip">{typeof t === "string" ? t : JSON.stringify(t)}</Badge>
                              ))}
                            </span>
                          ) : (
                            <span className="muted">{contractsPageCopy.fallbackValues.noAcceptanceTests}</span>
                          )}
                        </span>
                      </div>
                    </div>
                  </CardContent>
                  <div className="toolbar px-4 pb-4">
                    <Button asChild>
                      <Link href={proofHref}>{shellCopy.openProofRoom}</Link>
                    </Button>
                    <Button asChild variant="secondary">
                      <Link href={roleDeskHref}>{shellCopy.inspectRoleDesk}</Link>
                    </Button>
                    {!contract.run_id ? (
                      <Button asChild variant="ghost">
                        <Link href="/workflows">{shellCopy.inspectWorkflowDesk}</Link>
                      </Button>
                    ) : null}
                  </div>
                  <p className="mono muted px-4 pb-4">
                    {contract.run_id ? shellCopy.nextActionHintWithRun : shellCopy.nextActionHintWithoutRun}
                  </p>
                  <details className="collapsible">
                    <summary>{shellCopy.secondaryDetailsSummary}</summary>
                    <div className="collapsible-body">
                      <div className="data-list">
                        <div className="data-list-row">
                          <span className="data-list-label">{contractsPageCopy.fieldLabels.skillsBundle}</span>
                          <span className="data-list-value mono muted">
                            {roleBinding
                              ? formatBindingReadModelLabel(roleBinding.skills_bundle_ref)
                              : contractsPageCopy.fallbackValues.notDerived}
                          </span>
                        </div>
                        <div className="data-list-row">
                          <span className="data-list-label">{contractsPageCopy.fieldLabels.mcpBundle}</span>
                          <span className="data-list-value mono muted">
                            {roleBinding
                              ? formatBindingReadModelLabel(roleBinding.mcp_bundle_ref)
                              : contractsPageCopy.fallbackValues.notDerived}
                          </span>
                        </div>
                        <div className="data-list-row">
                          <span className="data-list-label">{contractsPageCopy.fieldLabels.runtimeBinding}</span>
                          <span className="data-list-value mono muted">
                            {roleBinding
                              ? formatRoleBindingRuntimeSummary(roleBinding)
                              : contractsPageCopy.fallbackValues.notDerived}
                          </span>
                        </div>
                        <div className="data-list-row">
                          <span className="data-list-label">{contractsPageCopy.fieldLabels.runtimeCapability}</span>
                          <span className="data-list-value mono muted">
                            {roleBinding?.runtime_binding?.capability?.lane || contractsPageCopy.fallbackValues.notDerived}
                          </span>
                        </div>
                        <div className="data-list-row">
                          <span className="data-list-label">{contractsPageCopy.fieldLabels.toolExecution}</span>
                          <span className="data-list-value mono muted">
                            {roleBinding
                              ? formatRoleBindingRuntimeCapabilitySummary(roleBinding)
                              : contractsPageCopy.fallbackValues.notDerived}
                          </span>
                        </div>
                        <div className="data-list-row">
                          <span className="data-list-label">{contractsPageCopy.fieldLabels.toolPermissions}</span>
                          <span className="data-list-value">
                            {permissionSummary.length > 0 ? (
                              <span className="chip-list">
                                {permissionSummary.map((entry) => (
                                  <Badge key={entry} variant="unstyled" className="chip">{entry}</Badge>
                                ))}
                              </span>
                            ) : (
                              <span className="muted">{contractsPageCopy.fallbackValues.defaultPermissions}</span>
                            )}
                          </span>
                        </div>
                      </div>
                      <p className="mono muted mt-4">{contractsPageCopy.fullJsonSummary}</p>
                      <pre className="mono">{JSON.stringify(payload || { raw_preview: contract.raw_preview }, null, 2)}</pre>
                    </div>
                  </details>
                </Card>
              );
            })}
          </div>
        )}
        {filteredContracts.length > limit ? (
          <Card>
            <p className="mono muted">{contractsPageCopy.moreHidden(filteredContracts.length - limit)}</p>
            <div className="toolbar mt-2">
              <Button asChild variant="secondary">
                <a href={`/contracts?${new URLSearchParams({ q: query, limit: String(filteredContracts.length) }).toString()}`}>
                  {contractsPageCopy.showAll}
                </a>
              </Button>
            </div>
          </Card>
        ) : null}
      </section>
    </main>
  );
}
