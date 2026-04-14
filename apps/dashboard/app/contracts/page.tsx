import { cookies } from "next/headers";
import Link from "next/link";
import { getUiCopy } from "@openvibecoding/frontend-shared/uiCopy";
import { normalizeUiLocale, UI_LOCALE_STORAGE_KEY } from "@openvibecoding/frontend-shared/uiLocale";
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

function compactContractLabel(contract: ContractRecord, fallback: string): string {
  const taskId = String(contract.task_id || "").trim();
  if (taskId) return taskId;
  const path = String(contract.path || "").trim();
  if (!path) return fallback;
  const segments = path.split("/").filter(Boolean);
  return segments.at(-1) || path;
}

function contractPathHint(contract: ContractRecord): string {
  const path = String(contract.path || "").trim();
  if (!path) return "";
  const segments = path.split("/").filter(Boolean);
  const tail = segments.slice(-3).join(" / ");
  return tail || path;
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
          actionSubtitle: "先确认哪份合约真能继续，哪份应该转去证明室、角色桌或工作流案例再处理。",
          commandTowerAction: "打开指挥塔",
          workflowAction: "打开工作流案例",
          proofAction: "打开证明室",
          triageDeskTitle: "合约分诊台",
          triageDeskSubtitle: "先处理缺执行权、缺关联 run、或缺验收证据的合约，再决定去证明室、角色桌还是工作流案例。",
          triageHeaders: {
            contract: "合约",
            role: "角色",
            blocker: "当前阻碍",
            action: "下一步",
          },
          riskTitle: "需要先处理的合约",
          riskHint: "缺执行权、缺关联运行、或缺验收测试的合约优先处理。",
          proofLinkedTitle: "已绑定证明室",
          proofLinkedHint: "已经能直接回到运行详情或证明室的合约数量。",
          authorityTitle: "已发布执行权",
          authorityHint: "执行权已经明确、可以继续往下判断的合约数量。",
          blockerReady: "可进入证明复核",
          blockerMissingAuthority: "缺少执行权",
          blockerMissingRun: "缺少关联 run",
          blockerMissingTests: "缺少验收测试",
          nextActionTitle: "下一步",
          openProofRoom: "打开关联证明室",
          inspectRoleDesk: "查看角色桌",
          inspectWorkflowDesk: "查看工作流案例",
          nextActionHintWithRun: "先回到运行详情或证明室，确认这份合约当前是否真能继续。",
          nextActionHintWithoutRun:
            "这份合约还没有稳定的运行下钻口，先回到工作流案例或角色桌，看 owner、authority 和 blocker。",
          secondaryDetailsSummary: "执行细节",
          inspectionDeckTitle: "检查归档",
          inspectionDeckSubtitle: "首屏先做分诊和下一步判断；只有在需要 payload、权限或 runtime 绑定时，再展开细节。",
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
          inspectionDeckTitle: "Inspection archive",
          inspectionDeckSubtitle:
            "Keep the first screen for triage and next action. Open the archive only when you need payload, permissions, or runtime binding detail.",
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
  const noContractsVisible = filteredContracts.length === 0;
  const firstScreenBadge = noContractsVisible
    ? locale === "zh-CN" ? "等待首份合约" : "Awaiting first contract"
    : contractsNeedingTriage > 0
      ? locale === "zh-CN" ? "先分诊" : "Triage first"
      : locale === "zh-CN" ? "可继续" : "Continue-ready";
  const firstScreenBadgeVariant = noContractsVisible || contractsNeedingTriage > 0 ? "warning" : "success";
  const spotlightContracts = visibleContracts.slice(0, 3);
  const showFullQueue = filteredContracts.length > 0;
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
        <div className="home-briefing-shell">
          <div className="home-briefing-copy">
            <p className="cell-sub mono muted">
              {locale === "zh-CN" ? "合约分诊 / 先判断再下钻" : "Contract desk / triage-first"}
            </p>
            <h2 className="section-title">{shellCopy.actionTitle}</h2>
            <p>{shellCopy.actionSubtitle}</p>
            <p className="desk-question">
              {locale === "zh-CN"
                ? "这张桌子第一眼只回答一个问题：现在哪份合约还不值得信。"
                : "This desk should answer one question first: which contract is still not trustworthy."}
            </p>
            <p className="cell-sub mono muted">
              {locale === "zh-CN"
                ? "不要先扎进 JSON。先判断哪份合约缺执行权、缺证明入口或缺验收，再去对应桌面。"
                : "Do not dive into JSON first. Decide which contract is missing authority, proof, or acceptance before you open the next desk."}
            </p>
            <nav aria-label="Contract desk actions" className="home-briefing-actions">
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
          <Card className="home-briefing-panel">
            <div className="home-briefing-panel-head">
              <span className="cell-sub mono muted">
                {locale === "zh-CN" ? "首屏判断" : "First-screen judgment"}
              </span>
              <Badge variant={firstScreenBadgeVariant}>{firstScreenBadge}</Badge>
            </div>
            <div className="home-briefing-signal-list" aria-label="Contract desk summary">
              <div className="home-briefing-signal">
                <span className="cell-sub mono muted">{shellCopy.riskTitle}</span>
                <strong>{contractsNeedingTriage}</strong>
                <p>{shellCopy.riskHint}</p>
              </div>
              <div className="home-briefing-signal">
                <span className="cell-sub mono muted">{shellCopy.proofLinkedTitle}</span>
                <strong>{contractsWithRuns}</strong>
                <p>{shellCopy.proofLinkedHint}</p>
              </div>
              <div className="home-briefing-signal">
                <span className="cell-sub mono muted">{shellCopy.authorityTitle}</span>
                <strong>{contractsWithAuthority}</strong>
                <p>{shellCopy.authorityHint}</p>
              </div>
            </div>
          </Card>
        </div>
      </header>
      <section className="app-section" aria-label="Contract list">
        {spotlightContracts.length > 0 ? (
          <div className="quick-grid quick-grid--triage-spotlight">
            {spotlightContracts.map((contract, index) => {
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
                <Card
                  key={`spotlight:${contract.path || contract.task_id || index}`}
                  variant="detail"
                  className={`triage-spotlight-card ${blockers.length > 1 ? "triage-spotlight-card--critical" : "triage-spotlight-card--notice"}`}
                >
                  <div className="triage-spotlight-head">
                    <span className="cell-sub mono muted">
                      {locale === "zh-CN" ? `优先合约 ${index + 1}` : `Priority contract ${index + 1}`}
                    </span>
                    <Badge variant={blockers.length > 0 ? "warning" : "success"}>
                      {blockers.length > 0 ? blockers.length : shellCopy.blockerReady}
                    </Badge>
                  </div>
                  <div className="triage-spotlight-body">
                    <strong className="triage-spotlight-title">
                      {compactContractLabel(contract, contractsPageCopy.fallbackValues.unknownContract)}
                    </strong>
                    <p className="triage-spotlight-desc">
                      {blockers.length > 0 ? blockers.join(" / ") : shellCopy.nextActionHintWithRun}
                    </p>
                    <p className="cell-sub mono muted">
                      {contractPathHint(contract) || contractsPageCopy.fallbackValues.unknownSource}
                    </p>
                  </div>
                  <div className="triage-spotlight-actions">
                    <Button asChild>
                      <Link href={proofHref}>{shellCopy.openProofRoom}</Link>
                    </Button>
                    <Button asChild variant="secondary">
                      <Link href={roleDeskHref}>{shellCopy.inspectRoleDesk}</Link>
                    </Button>
                  </div>
                </Card>
              );
            })}
          </div>
        ) : null}
        {showFullQueue ? (
          <Card asChild>
            <details className="collapsible" data-testid="contracts-full-queue" open={Boolean(query)}>
              <summary>
                {locale === "zh-CN"
                  ? `展开完整合约队列（${filteredContracts.length}）`
                  : `Open full contract queue (${filteredContracts.length})`}
              </summary>
              <div className="collapsible-body">
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
                                <div className="stack-gap-1">
                                  <span className="mono" title={contract.path || contract.task_id || ""}>
                                    {compactContractLabel(contract, contractsPageCopy.fallbackValues.unknownContract)}
                                  </span>
                                  {contract.path ? (
                                    <span className="cell-sub mono muted">{contractPathHint(contract)}</span>
                                  ) : null}
                                </div>
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
              </div>
            </details>
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
          <Card asChild>
            <details className="collapsible">
              <summary>{shellCopy.inspectionDeckTitle}</summary>
              <div className="collapsible-body">
                <p className="mono muted mb-4">{shellCopy.inspectionDeckSubtitle}</p>
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
              </div>
            </details>
          </Card>
        )}
      </section>
    </main>
  );
}
