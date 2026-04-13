import { cookies } from "next/headers";
import Link from "next/link";
import { getUiCopy } from "@cortexpilot/frontend-shared/uiCopy";
import { normalizeUiLocale, UI_LOCALE_STORAGE_KEY } from "@cortexpilot/frontend-shared/uiLocale";
import { fetchAgents, fetchAgentStatus } from "../../lib/api";
import { Button, buttonClasses } from "../../components/ui/button";
import { Badge, type BadgeVariant } from "../../components/ui/badge";
import { Card } from "../../components/ui/card";
import { Input, Select } from "../../components/ui/input";
import { RoleConfigControlPlane } from "../../components/control-plane/RoleConfigControlPlane";
import { safeLoad } from "../../lib/serverPageData";
import type { AgentCatalogPayload, AgentStatusPayload, RoleCatalogRecord } from "../../lib/types";
import { formatBindingReadModelLabel, formatRoleBindingRuntimeSummary } from "../../lib/types";

type AgentsPageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

function asRecordArray(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null);
}

function compactId(value: unknown, head = 8, tail = 6): string {
  const raw = String(value ?? "-");
  if (raw === "-" || raw.length <= head + tail + 3) {
    return raw;
  }
  return `${raw.slice(0, head)}...${raw.slice(-tail)}`;
}

function readableId(prefix: string, value: unknown): string {
  const raw = String(value ?? "").trim();
  if (!raw) {
    return "-";
  }
  const normalized = raw.replace(/[^a-zA-Z0-9]/g, "").toUpperCase();
  if (!normalized) {
    return prefix;
  }
  const tail = normalized.slice(-6);
  return `${prefix}-${tail}`;
}

function readQueryValue(value: string | string[] | undefined): string {
  if (Array.isArray(value)) {
    return String(value[0] || "").trim();
  }
  return String(value || "").trim();
}

function readPositiveInt(value: string | string[] | undefined, fallback: number): number {
  const parsed = Number.parseInt(readQueryValue(value), 10);
  if (Number.isFinite(parsed) && parsed > 0) {
    return parsed;
  }
  return fallback;
}

function includesQuery(record: Record<string, unknown>, query: string): boolean {
  if (!query) {
    return true;
  }
  const haystacks = [
    record.run_id,
    record.task_id,
    record.agent_id,
    record.lock_id,
    record.role,
    record.stage,
    record.path,
    record.worktree,
  ];
  const normalized = query.toLowerCase();
  return haystacks.some((value) => String(value ?? "").toLowerCase().includes(normalized));
}

function includesRoleCatalogQuery(record: RoleCatalogRecord, query: string): boolean {
  if (!query) {
    return true;
  }
  const normalized = query.toLowerCase();
  const roleBinding = record.role_binding_read_model;
  const haystacks = [
    record.role,
    record.purpose,
    record.system_prompt_ref,
    roleBinding?.skills_bundle_ref?.ref,
    roleBinding?.skills_bundle_ref?.bundle_id,
    ...(roleBinding?.skills_bundle_ref?.resolved_skill_set ?? []),
    roleBinding?.mcp_bundle_ref?.ref,
    ...(roleBinding?.mcp_bundle_ref?.resolved_mcp_tool_set ?? []),
    roleBinding?.runtime_binding?.summary?.runner,
    roleBinding?.runtime_binding?.summary?.provider,
    roleBinding?.runtime_binding?.summary?.model,
  ];
  return haystacks.some((value) => String(value ?? "").toLowerCase().includes(normalized));
}

function stageText(value: unknown): string {
  return String(value ?? "").trim().toUpperCase();
}

function stageIncludesAny(stage: string, tokens: string[]): boolean {
  return tokens.some((token) => stage.includes(token));
}

function isInitializingStage(stage: string): boolean {
  return ["INIT", "BOOT", "START", "PREP", "SETUP"].some((token) => stage.includes(token));
}

function isFailedStage(stage: string): boolean {
  return stageIncludesAny(stage, ["FAIL", "ERROR", "TIMEOUT", "DENY", "REJECT", "CANCEL", "ABORT", "BLOCK"]);
}

type FlowStagePresentation = {
  label: "Pending assignment" | "In progress" | "In review" | "Completed" | "Failed";
  badgeVariant: BadgeVariant;
  rawStage: string;
  isFailed: boolean;
};

function resolveFlowStage(item: Record<string, unknown>): FlowStagePresentation {
  const stage = stageText(item.stage);
  const hasAgent = String(item.agent_id ?? "").trim().length > 0;
  if (isFailedStage(stage)) {
    return { label: "Failed", badgeVariant: "failed", rawStage: stage, isFailed: true };
  }
  if (stageIncludesAny(stage, ["DONE", "COMPLETE", "SUCCESS", "APPROVE", "ARCHIVE", "CLOSE", "FINISH"])) {
    return { label: "Completed", badgeVariant: "success", rawStage: stage, isFailed: false };
  }
  if (stageIncludesAny(stage, ["VERIFY", "REVIEW", "TEST", "CHECK", "QA", "AUDIT", "APPROVAL", "MERGE"])) {
    return { label: "In review", badgeVariant: "running", rawStage: stage, isFailed: false };
  }
  if (!hasAgent || isInitializingStage(stage) || stageIncludesAny(stage, ["QUEUE", "PENDING", "WAIT", "ASSIGN", "SCHEDULE"])) {
    return { label: "Pending assignment", badgeVariant: "warning", rawStage: stage, isFailed: false };
  }
  return { label: "In progress", badgeVariant: "running", rawStage: stage, isFailed: false };
}

function fallbackRoleLabel(role: unknown, stage: unknown): string {
  const rawRole = String(role ?? "").trim();
  if (rawRole) {
    return rawRole;
  }
  const stageLabel = stageText(stage);
  if (isInitializingStage(stageLabel)) {
    return "Bootstrapping";
  }
  return "System task";
}

function fallbackAgentLabel(agentId: unknown, stage: unknown): string {
  const raw = String(agentId ?? "").trim();
  if (raw) {
    return readableId("AGENT", raw);
  }
  const stageLabel = stageText(stage);
  if (isInitializingStage(stageLabel)) {
    return "Bootstrapping";
  }
  return "Unassigned";
}

function resolveExecutionContext(
  item: Record<string, unknown>
): { primary: string; detail: string; title: string; isFallback: boolean } {
  const worktree = String(item.worktree ?? "").trim();
  const path = String(item.path ?? "").trim();
  const source = worktree || path;
  if (source) {
    const node = source.split("/").filter(Boolean).pop() ?? source;
    return {
      primary: compactId(source, 14, 10),
      detail: `Node ${compactId(node, 12, 8)}`,
      title: source,
      isFallback: false,
    };
  }
  const stageLabel = stageText(item.stage);
  const detail = isInitializingStage(stageLabel) ? "INIT" : "SYSTEM";
  return {
    primary: "Unbound",
    detail,
    title: `Unbound worktree (${detail})`,
    isFallback: true,
  };
}

function renderPaginationLink(label: string, href: string, disabled: boolean) {
  if (disabled) {
    return (
      <span className={buttonClasses("ghost")} aria-disabled="true">
        {label}
      </span>
    );
  }
  return (
    <Button asChild variant="ghost">
      <Link href={href}>{label}</Link>
    </Button>
  );
}

function statusRowKey(item: Record<string, unknown>, index: number): string {
  const runId = String(item.run_id ?? "").trim();
  const agentId = String(item.agent_id ?? "").trim();
  const taskId = String(item.task_id ?? "").trim();
  if (runId || agentId) {
    return `status:${runId || "no-run"}:${agentId || "no-agent"}:${taskId || index}`;
  }
  const stage = stageText(item.stage) || "NO_STAGE";
  const role = String(item.role ?? "").trim().toUpperCase() || "NO_ROLE";
  const source = String(item.worktree ?? item.path ?? "").trim() || "NO_SOURCE";
  return `status:fallback:${stage}:${role}:${source}:${index}`;
}

function lockRowKey(lock: Record<string, unknown>, index: number): string {
  const lockId = String(lock.lock_id ?? "").trim() || "NO_LOCK";
  const path = String(lock.path ?? "").trim() || "NO_PATH";
  const runId = String(lock.run_id ?? "").trim() || "NO_RUN";
  const agentId = String(lock.agent_id ?? "").trim() || "NO_AGENT";
  const ts = String(lock.ts ?? "").trim() || "NO_TS";
  return `lock:${lockId}:${path}:${runId}:${agentId}:${ts}:${index}`;
}

function groupedAgentRowKey(agentId: string, roles: string[], lockCount: number, lockedPaths: string[]): string {
  return `agent-group:${agentId}:${roles.join("|")}:${lockCount}:${lockedPaths.join("|") || "NO_PATHS"}`;
}

async function resolveDashboardLocale() {
  try {
    const cookieStore = await cookies();
    return normalizeUiLocale(cookieStore.get(UI_LOCALE_STORAGE_KEY)?.value);
  } catch {
    return normalizeUiLocale(undefined);
  }
}

export default async function AgentsPage({ searchParams }: AgentsPageProps) {
  const locale = await resolveDashboardLocale();
  const agentsPageCopy = getUiCopy(locale).dashboard.agentsPage;
  const params = searchParams ? await searchParams : {};
  const queryText = readQueryValue(params.q);
  const roleFilter = readQueryValue(params.role).toUpperCase();
  const pageNo = readPositiveInt(params.page, 1);
  const pageSize = 15;

  const { data: payload, warning: payloadWarning } = await safeLoad<AgentCatalogPayload>(
    fetchAgents,
    { agents: [], locks: [], role_catalog: [] },
    "Agent registry",
  );
  const { data: statusPayload, warning: statusWarning } = await safeLoad<AgentStatusPayload>(
    fetchAgentStatus,
    { agents: [] },
    "Agent state machine",
  );
  const warning = payloadWarning || statusWarning;
  const agentsAll = Array.isArray(payload.agents) ? payload.agents : [];
  const locksAll = asRecordArray(payload.locks);
  const roleCatalogAll = Array.isArray(payload.role_catalog) ? payload.role_catalog : [];
  const statusesAll = Array.isArray(statusPayload.agents) ? statusPayload.agents : [];
  const roles = Array.from(
    new Set(
      [...roleCatalogAll, ...agentsAll, ...statusesAll, ...locksAll]
        .map((item) => String(item.role || "").trim().toUpperCase())
        .filter((item) => item.length > 0)
    )
  ).sort();
  const roleMatches = (value: unknown) => !roleFilter || String(value || "").trim().toUpperCase() === roleFilter;
  const roleCatalog = roleCatalogAll.filter((item) => roleMatches(item.role) && includesRoleCatalogQuery(item, queryText));
  const agents = agentsAll.filter((item) => roleMatches(item.role) && includesQuery(item, queryText));
  const locks = locksAll.filter((item) => roleMatches(item.role) && includesQuery(item, queryText));
  const statuses = statusesAll.filter((item) => roleMatches(item.role) && includesQuery(item, queryText));
  const groupedAgents = Array.from(
    agents.reduce((acc, agent) => {
      const rawAgentId = String(agent.agent_id ?? "").trim() || "NO_AGENT";
      const entry = acc.get(rawAgentId) ?? {
        agentId: rawAgentId,
        roles: new Set<string>(),
        lockCount: 0,
        lockedPaths: new Set<string>(),
      };
      const role = String(agent.role ?? "").trim();
      if (role) {
        entry.roles.add(role);
      }
      entry.lockCount = Math.max(entry.lockCount, Number(agent.lock_count ?? 0) || 0);
      for (const path of Array.isArray(agent.locked_paths) ? agent.locked_paths : []) {
        const normalized = String(path).trim();
        if (normalized) {
          entry.lockedPaths.add(normalized);
        }
      }
      acc.set(rawAgentId, entry);
      return acc;
    }, new Map<string, { agentId: string; roles: Set<string>; lockCount: number; lockedPaths: Set<string> }>())
  )
    .map(([, entry]) => ({
      agentId: entry.agentId,
      roles: Array.from(entry.roles).sort(),
      lockCount: entry.lockCount,
      lockedPaths: Array.from(entry.lockedPaths).sort(),
    }))
    .sort((left, right) => left.agentId.localeCompare(right.agentId));
  const totalRows = Math.max(agents.length, locks.length, statuses.length, 1);
  const totalPages = Math.max(1, Math.ceil(totalRows / pageSize));
  const safePageNo = Math.min(pageNo, totalPages);
  const start = (safePageNo - 1) * pageSize;
  const end = start + pageSize;
  const statusesPage = statuses.slice(start, end);
  const visibleStatusesPage = statusesPage.slice(0, 8);
  const agentsPage = groupedAgents.slice(start, end);
  const locksPage = locks.slice(start, end);
  const hasActiveFilters = Boolean(queryText || roleFilter);
  const failedStatuses = statuses.filter((item) => isFailedStage(stageText(item.stage)));
  const failedStatusesPage = statusesPage.filter((item) => isFailedStage(stageText(item.stage)));
  const unassignedStatuses = statuses.filter((item) => !String(item.agent_id ?? "").trim()).length;
  const unassignedFailedStatuses = failedStatuses.filter((item) => !String(item.agent_id ?? "").trim()).length;
  const lockedAgentCount = groupedAgents.filter((agent) => agent.lockCount > 0).length;
  const activeAgentIds = new Set(
    statuses
      .map((item) => String(item.agent_id ?? "").trim())
      .filter((agentId) => agentId.length > 0)
  );
  const registeredAgents = groupedAgents.length;
  const activeAgents = activeAgentIds.size;
  const capacityRatio = registeredAgents > 0 ? Math.round((activeAgents / registeredAgents) * 100) : 0;
  const healthyStatuses = Math.max(0, statuses.length - failedStatuses.length);
  const highRiskOps = failedStatuses.length + unassignedStatuses;
  const baseQuery = new URLSearchParams();
  if (queryText) {
    baseQuery.set("q", queryText);
  }
  if (roleFilter) {
    baseQuery.set("role", roleFilter);
  }
  const prevHref = (() => {
    const next = new URLSearchParams(baseQuery);
    next.set("page", String(Math.max(1, safePageNo - 1)));
    return `/agents?${next.toString()}`;
  })();
  const nextHref = (() => {
    const next = new URLSearchParams(baseQuery);
    next.set("page", String(Math.min(totalPages, safePageNo + 1)));
    return `/agents?${next.toString()}`;
  })();

  return (
    <main className="grid" aria-labelledby="agents-page-title">
      <header className="app-section">
        <div className="section-header">
          <div>
            <h1 id="agents-page-title" className="page-title">{agentsPageCopy.title}</h1>
            <p className="page-subtitle">{agentsPageCopy.subtitle}</p>
            <p className="sr-only">
              Triage blocked risk first, confirm available execution seats next, then drill into individual task records.
            </p>
          </div>
          <div className="toolbar" role="group" aria-label="Page-level governance entry">
            <Button asChild variant="ghost">
              <Link href="/command-tower">{agentsPageCopy.openCommandTower}</Link>
            </Button>
          </div>
        </div>
      </header>
      {warning ? (
        <Card variant="compact" role="status" aria-live="polite">
          <p className="ct-home-empty-text">{agentsPageCopy.warningTitle}</p>
          <p className="mono muted">{agentsPageCopy.warningNextStep}</p>
          <p className="mono muted">{warning}</p>
        </Card>
      ) : null}
      <section className="stats-grid" aria-label={agentsPageCopy.summaryAriaLabel}>
        <article className="metric-card">
          <p className="metric-label">{agentsPageCopy.metricLabels.riskDesk}</p>
          <span className="sr-only">Failure-led queue</span>
          <p
            className={`metric-value ${failedStatuses.length > 0 ? "metric-value--danger" : "metric-value--primary"}`}
          >
            {failedStatuses.length}
          </p>
          <Badge variant={failedStatuses.length > 0 ? "failed" : "success"}>
            {failedStatuses.length > 0 ? agentsPageCopy.metricBadges.riskActive : agentsPageCopy.metricBadges.riskClear}
          </Badge>
          <p className="cell-sub mono muted">{agentsPageCopy.metricSublines.risk(statuses.length, healthyStatuses)}</p>
          <p className="cell-sub mono muted">{agentsPageCopy.metricSublines.riskHint}</p>
        </article>
        <article className="metric-card">
          <p className="metric-label">{agentsPageCopy.metricLabels.executionSeats}</p>
          <span className="sr-only">Registered capacity</span>
          <p className="metric-value">{registeredAgents}</p>
          <p className="cell-sub mono muted">{agentsPageCopy.metricSublines.execution(activeAgents, capacityRatio)}</p>
          <p className="cell-sub mono muted">{agentsPageCopy.metricSublines.executionHint}</p>
          <p className="sr-only">Pending tasks stay out of this card to avoid backlog confusion.</p>
        </article>
        <article className="metric-card">
          <p className="metric-label">{agentsPageCopy.metricLabels.schedulerPosture}</p>
          <span className="sr-only">Pending scheduling backlog</span>
          <p className={`metric-value ${highRiskOps > 0 ? "metric-value--warning" : "metric-value--primary"}`}>{highRiskOps}</p>
          <Badge variant={highRiskOps > 0 ? "failed" : "success"}>
            {highRiskOps > 0 ? agentsPageCopy.metricBadges.schedulerNeedsAction : agentsPageCopy.metricBadges.schedulerStable}
          </Badge>
          <div className="inline-stack">
            <Button asChild variant={highRiskOps > 0 ? "warning" : "default"}>
              <Link href="#agents-state-machine-title">{agentsPageCopy.actions.inspectRiskDesk}</Link>
            </Button>
            <Button asChild variant="secondary" aria-label="Go to the registered agent list">
              <Link href="#agents-role-catalog-title">{agentsPageCopy.actions.inspectRoleDesk}</Link>
            </Button>
            <Button asChild variant="secondary">
              <Link href="/events">{agentsPageCopy.actions.openFailedEvents}</Link>
            </Button>
          </div>
          <p className="cell-sub mono muted">{agentsPageCopy.metricSublines.scheduler(unassignedStatuses, unassignedFailedStatuses)}</p>
          <p className="cell-sub mono muted">{agentsPageCopy.metricSublines.schedulerHint(lockedAgentCount)}</p>
        </article>
      </section>
      <section className="app-section" aria-labelledby="agents-ops-title">
        <div className="section-header">
          <div>
            <h2 id="agents-ops-title" className="section-title">{agentsPageCopy.filters.title}</h2>
            <p>{agentsPageCopy.filters.subtitle}</p>
            <p className="sr-only">
              Use role and keyword filters to separate bound agent records from pending scheduling backlog. Without filters, the page shows a full inspection view.
            </p>
          </div>
        </div>
        <form method="get" className="toolbar toolbar--mt" data-testid="agents-filter-form">
          <label className="sr-only" htmlFor="agents-filter-q">Search agent records</label>
          <Input
            id="agents-filter-q"
            type="text"
            name="q"
            defaultValue={queryText}
            placeholder={agentsPageCopy.filters.searchPlaceholder}
            aria-label="Search agent records"
          />
          <label className="sr-only" htmlFor="agents-filter-role">Filter by role</label>
          <Select id="agents-filter-role" name="role" defaultValue={roleFilter} aria-label="Filter by role">
            <option value="">{agentsPageCopy.filters.allRoles}</option>
            {roles.map((role) => (
              <option key={role} value={role}>
                {role}
              </option>
            ))}
          </Select>
          {hasActiveFilters ? (
            <Button type="submit" variant="default">{agentsPageCopy.filters.applyFilter}</Button>
          ) : (
            <span className="mono muted">{agentsPageCopy.filters.hint}</span>
          )}
          <Button asChild variant="ghost">
            <Link href="/agents">{agentsPageCopy.filters.clearFilter}</Link>
          </Button>
        </form>
      </section>
      {/* ── Active State Machine ── */}
      <section className="app-section" aria-labelledby="agents-state-machine-title">
        <div className="section-header">
          <div>
            <h2 className="sr-only">Scheduling and task triage detail</h2>
            <h2 id="agents-state-machine-title" className="section-title">{agentsPageCopy.stateMachine.title}</h2>
            <p className="mono muted">{agentsPageCopy.stateMachine.subtitle}</p>
          </div>
          <div className="toolbar" role="group" aria-label="State machine batch actions">
            <Badge variant="running">{agentsPageCopy.stateMachine.summaryBadge(statuses.length, visibleStatusesPage.length)}</Badge>
            <Badge variant={failedStatuses.length > 0 ? "failed" : "success"}>
              {agentsPageCopy.stateMachine.failedBadge(failedStatuses.length, failedStatusesPage.length)}
            </Badge>
            {failedStatuses.length > 0 ? (
              <Button asChild variant={failedStatuses.length > 0 ? "warning" : "ghost"}>
                <Link href="/runs?status=FAILED">{agentsPageCopy.stateMachine.viewFailedRuns}</Link>
              </Button>
            ) : null}
            {failedStatuses.length > 0 ? (
              <Badge variant="warning">{agentsPageCopy.stateMachine.unassignedFailuresBadge(unassignedFailedStatuses)}</Badge>
            ) : null}
          </div>
        </div>
        {visibleStatusesPage.length === 0 ? (
          <Card>
            <div className="empty-state-stack">
              <span className="muted">{agentsPageCopy.stateMachine.emptyTitle}</span>
            </div>
          </Card>
        ) : (
          <Card variant="table">
            {statusesPage.length > visibleStatusesPage.length ? (
              <p className="mono muted" role="status">{agentsPageCopy.stateMachine.sampleHint(visibleStatusesPage.length)}</p>
            ) : null}
            <table className="run-table">
              <thead>
                <tr>
                  <th scope="col">{agentsPageCopy.stateMachine.headers.runId}</th>
                  <th scope="col">{agentsPageCopy.stateMachine.headers.taskId}</th>
                  <th scope="col">{agentsPageCopy.stateMachine.headers.role}</th>
                  <th scope="col">{agentsPageCopy.stateMachine.headers.agentId}</th>
                  <th scope="col">{agentsPageCopy.stateMachine.headers.flowStage}</th>
                  <th scope="col">{agentsPageCopy.stateMachine.headers.executionContext}</th>
                  <th scope="col">{agentsPageCopy.stateMachine.headers.governanceAction}</th>
                </tr>
              </thead>
              <tbody>
                {visibleStatusesPage.map((item, index) => {
                  const stage = stageText(item.stage);
                  const flowStage = resolveFlowStage(item);
                  const runId = String(item.run_id || "").trim();
                  const roleLabel = fallbackRoleLabel(item.role, stage);
                  const roleIsFallback = !String(item.role ?? "").trim();
                  const agentLabel = fallbackAgentLabel(item.agent_id, stage);
                  const agentIsFallback = !String(item.agent_id ?? "").trim();
                  const context = resolveExecutionContext(item);
                  return (
                    <tr key={statusRowKey(item, index)}>
                      <th scope="row">
                        <span className="mono" title={String(item.run_id || "-")}>
                          {readableId("RUN", item.run_id)}
                        </span>
                      </th>
                      <td>
                        <span className="mono" title={String(item.task_id || "-")}>
                          {readableId("TASK", item.task_id)}
                        </span>
                      </td>
                      <td>
                        <Badge variant={roleIsFallback ? "warning" : "default"} title={roleIsFallback ? "Role is not assigned yet. A semantic placeholder is shown." : roleLabel}>
                          {roleLabel}
                        </Badge>
                      </td>
                      <td>
                        {agentIsFallback ? (
                          <Badge title={agentsPageCopy.stateMachine.pendingSchedulingHint}>
                            {agentsPageCopy.stateMachine.pendingScheduling}
                          </Badge>
                        ) : (
                          <span className="mono" title={String(item.agent_id || "-")}>
                            {agentLabel}
                          </span>
                        )}
                      </td>
                      <td>
                        <Badge variant={flowStage.badgeVariant} title={flowStage.rawStage ? `Raw stage: ${flowStage.rawStage}` : "Raw stage is missing"}>
                          {flowStage.isFailed && agentIsFallback ? agentsPageCopy.stateMachine.schedulingFailed : flowStage.label}
                        </Badge>
                      </td>
                      <td>
                        <div className="toolbar" role="group" aria-label={agentsPageCopy.stateMachine.executionContextAriaLabel}>
                          {context.isFallback ? (
                            <Badge title={context.title}>{context.primary}</Badge>
                          ) : (
                            <span className="mono muted" title={context.title}>
                              {context.primary}
                            </span>
                          )}
                          <span className="mono muted" title={context.title}>
                            {context.detail}
                          </span>
                        </div>
                      </td>
                      <td>
                        {runId ? (
                          <div className="toolbar" role="group" aria-label={agentsPageCopy.stateMachine.governanceActionsAriaLabel}>
                            <Button asChild variant="ghost">
                              <Link
                                href={`/runs/${encodeURIComponent(runId)}`}
                                title={flowStage.isFailed ? agentsPageCopy.stateMachine.detailFailedTitle : agentsPageCopy.stateMachine.detailDefaultTitle}
                              >
                                {agentsPageCopy.stateMachine.detail}
                              </Link>
                            </Button>
                          </div>
                        ) : (
                          <span className="muted">{agentsPageCopy.stateMachine.missingRunId}</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </Card>
        )}
      </section>

      {/* ── Registered Agents ── */}
      <section className="app-section" aria-labelledby="agents-registered-title">
        <Card asChild>
          <details>
            <summary className="section-title" id="agents-registered-title">
              {agentsPageCopy.registeredInventory.title(groupedAgents.length)}
            </summary>
            <span className="sr-only">
              Registered agent inventory (expandable, {groupedAgents.length} items)
            </span>
            {payloadWarning ? (
              <div className="empty-state-stack">
                <span className="muted">{agentsPageCopy.registeredInventory.registryUnavailable}</span>
              </div>
            ) : null}
            {!payloadWarning && agentsPage.length === 0 ? (
              <div className="empty-state-stack">
                <span className="muted">{agentsPageCopy.registeredInventory.emptyTitle}</span>
              </div>
            ) : null}
            {!payloadWarning && agentsPage.length > 0 ? (
              <div
                className="table-card mt-2"
                tabIndex={0}
                aria-label={agentsPageCopy.registeredInventory.tableAriaLabel}
              >
                <table className="run-table">
                  <thead>
                    <tr>
                      <th scope="col">{agentsPageCopy.registeredInventory.headers.agentId}</th>
                      <th scope="col">{agentsPageCopy.registeredInventory.headers.role}</th>
                      <th scope="col">{agentsPageCopy.registeredInventory.headers.lockCount}</th>
                      <th scope="col">{agentsPageCopy.registeredInventory.headers.lockedPaths}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {agentsPage.map((agent) => {
                      return (
                        <tr key={groupedAgentRowKey(agent.agentId, agent.roles, agent.lockCount, agent.lockedPaths)}>
                          <th scope="row">
                            <span className="mono" title={String(agent.agentId || "-")}>
                              {readableId("AGENT", agent.agentId)}
                            </span>
                          </th>
                          <td>
                            <span className="chip-list">
                              {agent.roles.length > 0 ? agent.roles.map((role) => <Badge key={role}>{role}</Badge>) : <span className="muted">-</span>}
                            </span>
                          </td>
                          <td><span className="cell-primary">{String(agent.lockCount ?? 0)}</span></td>
                          <td>
                            {agent.lockedPaths.length > 0 ? (
                              <span className="chip-list">
                                {agent.lockedPaths.map((p: string) => <span key={p} className="chip">{p}</span>)}
                              </span>
                            ) : (
                              <span className="muted">-</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : null}
          </details>
        </Card>
      </section>

      {/* ── Locks ── */}
      <section className="app-section" aria-labelledby="agents-locks-title">
        <Card asChild>
          <details>
            <summary className="section-title" id="agents-locks-title">
              {agentsPageCopy.locks.title(locks.length, locksPage.length)}
            </summary>
            {locksPage.length === 0 ? (
              <div className="empty-state-stack">
                <span className="muted">{agentsPageCopy.locks.emptyTitle}</span>
              </div>
            ) : (
              <div
                className="table-card mt-2"
                tabIndex={0}
                aria-label={agentsPageCopy.locks.tableAriaLabel}
              >
                <table className="run-table">
                  <thead>
                    <tr>
                      <th scope="col">{agentsPageCopy.locks.headers.lockId}</th>
                      <th scope="col">{agentsPageCopy.locks.headers.runId}</th>
                      <th scope="col">{agentsPageCopy.locks.headers.agentId}</th>
                      <th scope="col">{agentsPageCopy.locks.headers.role}</th>
                      <th scope="col">{agentsPageCopy.locks.headers.path}</th>
                      <th scope="col">{agentsPageCopy.locks.headers.timestamp}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {locksPage.map((lock, index) => (
                      <tr key={lockRowKey(lock, start + index)}>
                        <th scope="row">
                          <span className="mono" title={String(lock.lock_id || "-")}>
                            {readableId("LOCK", lock.lock_id)}
                          </span>
                        </th>
                        <td>
                          <span className="mono" title={String(lock.run_id || "-")}>
                            {readableId("RUN", lock.run_id)}
                          </span>
                        </td>
                        <td>
                          <span className="mono" title={String(lock.agent_id || "-")}>
                            {readableId("AGENT", lock.agent_id)}
                          </span>
                        </td>
                        <td><Badge>{String(lock.role || "-")}</Badge></td>
                        <td><span className="chip">{String(lock.path)}</span></td>
                        <td><span className="mono muted">{String(lock.ts || "-")}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </details>
        </Card>
      </section>

      <RoleConfigControlPlane roleCatalog={roleCatalogAll} />
      <section className="app-section" aria-labelledby="agents-role-catalog-title">
        <Card asChild>
          <details>
            <summary className="section-title" id="agents-role-catalog-title">
              {agentsPageCopy.roleCatalog.title}
            </summary>
            <div className="section-header mt-2">
              <div>
                <p className="mono muted">{agentsPageCopy.roleCatalog.subtitle}</p>
              </div>
              <div className="toolbar" role="group" aria-label="Role catalog entry">
                <Button asChild variant="secondary" aria-label="Go to the full registered agent list">
                  <Link href="#agents-registered-title">{agentsPageCopy.roleCatalog.fullList}</Link>
                </Button>
              </div>
            </div>
            <div className="table-card mt-2">
              {payloadWarning ? (
                <p className="mono muted">{agentsPageCopy.roleCatalog.registryUnavailable}</p>
              ) : roleCatalog.length === 0 ? (
                <p className="mono muted">{agentsPageCopy.roleCatalog.noMatches}</p>
              ) : (
                <table className="run-table">
                  <thead>
                    <tr>
                      <th scope="col">{agentsPageCopy.roleCatalog.headers.role}</th>
                      <th scope="col">{agentsPageCopy.roleCatalog.headers.skillsBundle}</th>
                      <th scope="col">{agentsPageCopy.roleCatalog.headers.mcpBundle}</th>
                      <th scope="col">{agentsPageCopy.roleCatalog.headers.runtimeBinding}</th>
                      <th scope="col">{agentsPageCopy.roleCatalog.headers.executionAuthority}</th>
                      <th scope="col">{agentsPageCopy.roleCatalog.headers.registeredSeats}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {roleCatalog.map((roleEntry) => (
                      <tr key={`role-catalog:${roleEntry.role}`}>
                        <th scope="row">
                          <div className="stack-gap-2">
                            <Badge>{roleEntry.role}</Badge>
                            <span className="muted">{roleEntry.purpose || agentsPageCopy.roleCatalog.noRolePurpose}</span>
                          </div>
                        </th>
                        <td>
                          <span className="mono muted">
                            {formatBindingReadModelLabel(roleEntry.role_binding_read_model?.skills_bundle_ref)}
                          </span>
                        </td>
                        <td>
                          <span className="mono muted">
                            {formatBindingReadModelLabel(roleEntry.role_binding_read_model?.mcp_bundle_ref)}
                          </span>
                        </td>
                        <td><span className="mono muted">{formatRoleBindingRuntimeSummary(roleEntry.role_binding_read_model)}</span></td>
                        <td>
                          <div className="stack-gap-2">
                            <Badge variant="running">{roleEntry.role_binding_read_model.execution_authority}</Badge>
                            <span className="muted">{agentsPageCopy.roleCatalog.readOnlyMirror}</span>
                          </div>
                        </td>
                        <td>
                          <div className="stack-gap-2">
                            <span className="cell-primary">{roleEntry.registered_agent_count}</span>
                            <span className="mono muted">
                              {roleEntry.locked_agent_count} {agentsPageCopy.roleCatalog.lockedSuffix}
                            </span>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </details>
        </Card>
      </section>

      <section className="app-section" aria-label="Agent pagination navigation (footer)">
        <nav className="toolbar" aria-label="Agent pagination navigation (footer)">
          <span className="mono muted" role="status" aria-live="polite" aria-atomic="true">
            {agentsPageCopy.pagination.status(safePageNo, totalPages, pageSize)}
          </span>
          {renderPaginationLink(agentsPageCopy.pagination.previous, prevHref, safePageNo <= 1)}
          {renderPaginationLink(agentsPageCopy.pagination.next, nextHref, safePageNo >= totalPages)}
        </nav>
      </section>
    </main>
  );
}
