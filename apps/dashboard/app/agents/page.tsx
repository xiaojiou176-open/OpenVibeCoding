import { cookies } from "next/headers";
import Link from "next/link";
import { getUiCopy } from "@openvibecoding/frontend-shared/uiCopy";
import { normalizeUiLocale, UI_LOCALE_STORAGE_KEY } from "@openvibecoding/frontend-shared/uiLocale";
import { fetchAgents, fetchAgentStatus } from "../../lib/api";
import { Button, buttonClasses } from "../../components/ui/button";
import { Badge, type BadgeVariant } from "../../components/ui/badge";
import { Card } from "../../components/ui/card";
import { Input, Select } from "../../components/ui/input";
import { RoleConfigControlPlane } from "../../components/control-plane/RoleConfigControlPlane";
import { safeLoad } from "../../lib/serverPageData";
import type { AgentCatalogPayload, AgentStatusPayload, RoleCatalogRecord } from "../../lib/types";
import { localizeRolePurpose } from "../../lib/rolePresentation";
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
  label: string;
  badgeVariant: BadgeVariant;
  rawStage: string;
  isFailed: boolean;
};

function resolveFlowStage(item: Record<string, unknown>, locale: "en" | "zh-CN"): FlowStagePresentation {
  const stage = stageText(item.stage);
  const hasAgent = String(item.agent_id ?? "").trim().length > 0;
  const labels =
    locale === "zh-CN"
      ? {
          failed: "失败",
          completed: "已完成",
          review: "复核中",
          pending: "待分配",
          progress: "执行中",
        }
      : {
          failed: "Failed",
          completed: "Completed",
          review: "In review",
          pending: "Pending assignment",
          progress: "In progress",
        };
  if (isFailedStage(stage)) {
    return { label: labels.failed, badgeVariant: "failed", rawStage: stage, isFailed: true };
  }
  if (stageIncludesAny(stage, ["DONE", "COMPLETE", "SUCCESS", "APPROVE", "ARCHIVE", "CLOSE", "FINISH"])) {
    return { label: labels.completed, badgeVariant: "success", rawStage: stage, isFailed: false };
  }
  if (stageIncludesAny(stage, ["VERIFY", "REVIEW", "TEST", "CHECK", "QA", "AUDIT", "APPROVAL", "MERGE"])) {
    return { label: labels.review, badgeVariant: "running", rawStage: stage, isFailed: false };
  }
  if (!hasAgent || isInitializingStage(stage) || stageIncludesAny(stage, ["QUEUE", "PENDING", "WAIT", "ASSIGN", "SCHEDULE"])) {
    return { label: labels.pending, badgeVariant: "warning", rawStage: stage, isFailed: false };
  }
  return { label: labels.progress, badgeVariant: "running", rawStage: stage, isFailed: false };
}

function fallbackRoleLabel(role: unknown, stage: unknown, locale: "en" | "zh-CN"): string {
  const rawRole = String(role ?? "").trim();
  if (rawRole) {
    return rawRole;
  }
  const stageLabel = stageText(stage);
  if (isInitializingStage(stageLabel)) {
    return locale === "zh-CN" ? "启动中" : "Bootstrapping";
  }
  return locale === "zh-CN" ? "系统任务" : "System task";
}

function fallbackAgentLabel(agentId: unknown, stage: unknown, locale: "en" | "zh-CN"): string {
  const raw = String(agentId ?? "").trim();
  if (raw) {
    return readableId("AGENT", raw);
  }
  const stageLabel = stageText(stage);
  if (isInitializingStage(stageLabel)) {
    return locale === "zh-CN" ? "启动中" : "Bootstrapping";
  }
  return locale === "zh-CN" ? "待分配" : "Unassigned";
}

function resolveExecutionContext(
  item: Record<string, unknown>,
  locale: "en" | "zh-CN",
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
  const detail = isInitializingStage(stageLabel)
    ? locale === "zh-CN" ? "启动阶段" : "INIT"
    : locale === "zh-CN" ? "系统" : "SYSTEM";
  return {
    primary: locale === "zh-CN" ? "未绑定" : "Unbound",
    detail,
    title: locale === "zh-CN" ? `未绑定工作树（${detail}）` : `Unbound worktree (${detail})`,
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
  const hasLiveSeatEvidence = statuses.length > 0 || registeredAgents > 0;
  const firstScreenNeedsCaution = Boolean(warning) || highRiskOps > 0 || !hasLiveSeatEvidence;
  const firstScreenBadge = !hasLiveSeatEvidence
    ? locale === "zh-CN" ? "等待实时席位" : "Awaiting live seats"
    : highRiskOps > 0
      ? agentsPageCopy.metricBadges.schedulerNeedsAction
      : agentsPageCopy.metricBadges.schedulerStable;
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
  const triageSpotlight = [...failedStatuses, ...statuses.filter((item) => !isFailedStage(stageText(item.stage)))]
    .filter((item, index, array) => array.findIndex((candidate) => statusRowKey(candidate, 0) === statusRowKey(item, 0)) === index)
    .slice(0, 3);

  return (
    <main className="grid" aria-labelledby="agents-page-title">
      <header className="app-section">
        <div className="section-header">
          <div>
            <h1 id="agents-page-title" className="page-title">{agentsPageCopy.title}</h1>
            <p className="page-subtitle">{agentsPageCopy.subtitle}</p>
            <p className="sr-only">
              {locale === "zh-CN"
                ? "先分诊风险，再确认谁真的在线，最后再下钻具体任务记录。"
                : "Triage blocked risk first, confirm available execution seats next, then drill into individual task records."}
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
      <section className="app-section">
        <div className="home-briefing-shell">
          <div className="home-briefing-copy">
            <p className="cell-sub mono muted">
              {locale === "zh-CN" ? "角色治理 / 首屏分诊" : "Role operations / first-screen triage"}
            </p>
            <h2 className="section-title">
              {locale === "zh-CN" ? "先看风险、席位和调度姿态" : "Read risk, seats, and scheduler posture first"}
            </h2>
            <p className="cell-sub mono muted">
              {locale === "zh-CN"
                ? "不要把这页做成注册表 dump。先判断失败队列、执行席位和调度姿态，再下钻 state machine、locks 和 role catalog。"
                : "Do not let this page read like a registry dump. Judge the failure queue, execution seats, and scheduler posture before drilling into state machines, locks, or the role catalog."}
            </p>
            <p className="desk-question">
              {locale === "zh-CN"
                ? "这张桌子第一眼只回答一个问题：哪张席位过载、缺位，或者需要你先处理。"
                : "This desk should answer one question first: which seat is overloaded, missing, or needs you right now."}
            </p>
            <nav className="home-briefing-actions" aria-label="Agent desk actions">
              <Button asChild variant={highRiskOps > 0 ? "warning" : "default"}>
                <Link href="#agents-state-machine-title">{agentsPageCopy.actions.inspectRiskDesk}</Link>
              </Button>
              <Button asChild variant="secondary" aria-label="Go to the full registered agent list">
                <Link href="#agents-role-catalog-title">{agentsPageCopy.actions.inspectRoleDesk}</Link>
              </Button>
              <Button asChild variant="secondary">
                <Link href="/events">{agentsPageCopy.actions.openFailedEvents}</Link>
              </Button>
            </nav>
          </div>
          <Card className="home-briefing-panel">
            <div className="home-briefing-panel-head">
              <span className="cell-sub mono muted">
                {locale === "zh-CN" ? "首屏判断" : "First-screen judgment"}
              </span>
              <Badge variant={firstScreenNeedsCaution ? "warning" : "success"}>{firstScreenBadge}</Badge>
            </div>
            <div className="home-briefing-signal-list" aria-label={agentsPageCopy.summaryAriaLabel}>
              <div className="home-briefing-signal">
                <span className="cell-sub mono muted">{agentsPageCopy.metricLabels.riskDesk}</span>
                <strong>{failedStatuses.length}</strong>
                <p>{agentsPageCopy.metricSublines.risk(statuses.length, healthyStatuses)}</p>
              </div>
              <div className="home-briefing-signal">
                <span className="cell-sub mono muted">{agentsPageCopy.metricLabels.executionSeats}</span>
                <strong>{registeredAgents}</strong>
                <p>{agentsPageCopy.metricSublines.execution(activeAgents, capacityRatio)}</p>
                <p className="cell-sub mono muted">
                  {agentsPageCopy.metricSublines.executionHint}
                </p>
              </div>
              <div className="home-briefing-signal">
                <span className="cell-sub mono muted">{agentsPageCopy.metricLabels.schedulerPosture}</span>
                <strong>{highRiskOps}</strong>
                <p>{agentsPageCopy.metricSublines.scheduler(unassignedStatuses, unassignedFailedStatuses)}</p>
              </div>
            </div>
          </Card>
        </div>
      </section>
      <section className="app-section" aria-labelledby="agents-ops-title">
        <div className="section-header">
          <div>
            <h2 id="agents-ops-title" className="section-title">{agentsPageCopy.filters.title}</h2>
            <p>{agentsPageCopy.filters.subtitle}</p>
            <p className="sr-only">
              {locale === "zh-CN"
                ? "用角色和关键词把已绑定代理、待调度积压和失败记录拆开看；不筛选时会显示完整检查视图。"
                : "Use role and keyword filters to separate bound agent records from pending scheduling backlog. Without filters, the page shows a full inspection view."}
            </p>
          </div>
        </div>
        <form method="get" className="toolbar toolbar--mt" data-testid="agents-filter-form">
          <label className="sr-only" htmlFor="agents-filter-q">
            {locale === "zh-CN" ? "搜索代理记录" : "Search agent records"}
          </label>
          <Input
            id="agents-filter-q"
            type="text"
            name="q"
            defaultValue={queryText}
            placeholder={agentsPageCopy.filters.searchPlaceholder}
            aria-label={locale === "zh-CN" ? "搜索代理记录" : "Search agent records"}
          />
          <label className="sr-only" htmlFor="agents-filter-role">
            {locale === "zh-CN" ? "按角色筛选" : "Filter by role"}
          </label>
          <Select
            id="agents-filter-role"
            name="role"
            defaultValue={roleFilter}
            aria-label={locale === "zh-CN" ? "按角色筛选" : "Filter by role"}
          >
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
            <h2 className="sr-only">{locale === "zh-CN" ? "调度与任务分诊细节" : "Scheduling and task triage detail"}</h2>
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
        {triageSpotlight.length > 0 ? (
          <div className="quick-grid quick-grid--triage-spotlight">
            {triageSpotlight.map((item, index) => {
              const flowStage = resolveFlowStage(item, locale);
              const runId = String(item.run_id || "").trim();
              const roleLabel = fallbackRoleLabel(item.role, item.stage, locale);
              const context = resolveExecutionContext(item, locale);
              return (
                <Card
                  key={`agents-spotlight:${statusRowKey(item, index)}`}
                  variant="detail"
                  className={`triage-spotlight-card ${flowStage.isFailed ? "triage-spotlight-card--critical" : "triage-spotlight-card--notice"}`}
                >
                  <div className="triage-spotlight-head">
                    <span className="cell-sub mono muted">
                      {locale === "zh-CN" ? `优先运行 ${index + 1}` : `Priority run ${index + 1}`}
                    </span>
                    <Badge variant={flowStage.badgeVariant}>{flowStage.label}</Badge>
                  </div>
                  <div className="triage-spotlight-body">
                    <strong className="triage-spotlight-title">
                      {runId ? readableId("RUN", runId) : agentsPageCopy.stateMachine.missingRunId}
                    </strong>
                    <p className="triage-spotlight-desc">
                      {locale === "zh-CN"
                        ? `${roleLabel} · ${context.primary} · ${context.detail}`
                        : `${roleLabel} · ${context.primary} · ${context.detail}`}
                    </p>
                    <p className="cell-sub mono muted">
                      {flowStage.isFailed
                        ? locale === "zh-CN"
                          ? "先进入详情复核失败原因和恢复路径。"
                          : "Open detail first to inspect failure cause and recovery path."
                        : locale === "zh-CN"
                          ? "先确认当前执行线是否继续推进，再决定是否派更多任务。"
                          : "Confirm whether this lane is still moving before you dispatch more work."}
                    </p>
                  </div>
                  {runId ? (
                    <div className="triage-spotlight-actions">
                      <Button asChild variant={flowStage.isFailed ? "warning" : "secondary"}>
                        <Link href={`/runs/${encodeURIComponent(runId)}`}>{agentsPageCopy.stateMachine.detail}</Link>
                      </Button>
                    </div>
                  ) : null}
                </Card>
              );
            })}
          </div>
        ) : null}
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
                  const flowStage = resolveFlowStage(item, locale);
                  const runId = String(item.run_id || "").trim();
                  const roleLabel = fallbackRoleLabel(item.role, item.stage, locale);
                  const roleIsFallback = !String(item.role ?? "").trim();
                  const agentLabel = fallbackAgentLabel(item.agent_id, item.stage, locale);
                  const agentIsFallback = !String(item.agent_id ?? "").trim();
                  const context = resolveExecutionContext(item, locale);
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
                            <span className="muted">
                              {localizeRolePurpose(roleEntry.role, roleEntry.purpose, locale) || agentsPageCopy.roleCatalog.noRolePurpose}
                            </span>
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

      <RoleConfigControlPlane roleCatalog={roleCatalogAll} />

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
