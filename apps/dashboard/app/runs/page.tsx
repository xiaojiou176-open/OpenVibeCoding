import { cookies } from "next/headers";
import Link from "next/link";
import type { Metadata } from "next";
import { getUiCopy } from "@openvibecoding/frontend-shared/uiCopy";
import { normalizeUiLocale, UI_LOCALE_STORAGE_KEY } from "@openvibecoding/frontend-shared/uiLocale";

import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import RunList from "../../components/RunList";
import { fetchRuns } from "../../lib/api";
import { safeLoad } from "../../lib/serverPageData";
import { statusVariant } from "../../lib/statusPresentation";

type RunsPageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

const CJK_TEXT_RE = /[\u3400-\u9fff]/;

export function buildRunsMetadata(locale: "en" | "zh-CN"): Metadata {
  if (locale === "zh-CN") {
    return {
      title: "证明与回放 | OpenVibeCoding",
      description:
        "在 OpenVibeCoding 的证明与回放桌面查看最新结果、回放姿态、失败线索和下一步操作。",
    };
  }

  return {
    title: "Proof & Replay | OpenVibeCoding",
    description:
      "Inspect latest outcomes, replay posture, failure clues, and next operator actions from the OpenVibeCoding proof and replay surface.",
  };
}

function queryValue(value: string | string[] | undefined): string {
  return Array.isArray(value) ? String(value[0] || "").trim() : String(value || "").trim();
}

function hasCjkText(value: string | undefined | null): boolean {
  return Boolean(value && CJK_TEXT_RE.test(value));
}

async function resolveDashboardLocale() {
  try {
    const cookieStore = await cookies();
    return normalizeUiLocale(cookieStore.get(UI_LOCALE_STORAGE_KEY)?.value);
  } catch {
    return normalizeUiLocale(undefined);
  }
}

export async function generateMetadata(): Promise<Metadata> {
  const locale = await resolveDashboardLocale();
  return buildRunsMetadata(locale);
}

export default async function RunsPage({ searchParams }: RunsPageProps) {
  const locale = await resolveDashboardLocale();
  const runsPageCopy = getUiCopy(locale).dashboard.runsPage;
  const params = searchParams ? await searchParams : {};
  const statusFilter = queryValue(params.status).toUpperCase();
  const { data: runs, warning } = await safeLoad(fetchRuns, [], "Run records");
  const filteredRuns = statusFilter
    ? runs.filter((run) => String(run.status || "").toUpperCase() === statusFilter)
    : runs;
  const visibleRuns = filteredRuns.slice(0, 8);
  const failed = runs.filter((run) => String(run.status || "").toUpperCase().includes("FAIL")).length;
  const success = runs.filter((run) => ["SUCCESS", "DONE", "PASSED"].includes(String(run.status || "").toUpperCase())).length;
  const running = Math.max(runs.length - failed - success, 0);
  const proofReady = runs.filter((run) => {
    const outcomeType = String(run.outcome_type || "").trim().toLowerCase();
    return statusVariant(run.status) === "success" || ["proof_ready", "share_ready", "release_ready"].includes(outcomeType);
  }).length;
  const hintedRuns = runs.filter((run) => String(run.action_hint_zh || "").trim()).length;
  const failureRate = runs.length > 0 ? failed / runs.length : 0;
  const highFailureMode = failed > 0 && failureRate >= 0.5;
  const distributionHeadline = highFailureMode
    ? runsPageCopy.failureHeadline(failed)
    : runsPageCopy.successHeadline(success);
  const distributionClass = highFailureMode
    ? "metric-value--danger"
    : failed > 0
      ? "metric-value--warning"
      : "metric-value--success";
  const distributionSubline = highFailureMode
    ? runsPageCopy.failureSubline(success, running)
    : runsPageCopy.successSubline(running, failed);
  const hasPartialTruthWarning = Boolean(warning);
  const governanceHeadline = hasPartialTruthWarning
    ? locale === "zh-CN"
      ? "先核对当前只读快照"
      : "Verify the current read-only snapshot first"
    : failed > 0
      ? runsPageCopy.operatorPriorityHeadline(failed)
      : runsPageCopy.operatorPriorityClearHeadline;
  const governanceCtaHref = hasPartialTruthWarning ? "/runs" : failed > 0 ? "/runs?status=FAILED" : "/pm";
  const governanceCtaLabel = hasPartialTruthWarning
    ? locale === "zh-CN"
      ? "检查当前运行列表"
      : "Inspect visible runs"
    : failed > 0
      ? runsPageCopy.operatorPrimaryActionFailed
      : runsPageCopy.operatorPrimaryActionClear;
  const governanceSubline = hasPartialTruthWarning
    ? locale === "zh-CN"
      ? "当前列表带有降级提示。先把可见运行当成快照核对，再决定要不要继续放行或发起新任务。"
      : "This list is currently degraded. Treat the visible runs as a snapshot before you promote, replay, or dispatch more work."
    : failed > 0
      ? runsPageCopy.operatorPrioritySubline
      : runsPageCopy.operatorPriorityClearSubline;
  const operatorDeskNote = locale === "zh-CN"
    ? `当前首屏会把 ${proofReady} 个可直接进入证明复核的运行和 ${hintedRuns} 个带动作提示的运行放回同一张操作列表，不再只把证明与回放当失败分诊表。`
    : `This first screen keeps ${proofReady} proof-ready runs and ${hintedRuns} runs with explicit operator hints in the same operator list, so Proof & Replay is not reduced to a failure queue.`;
  const warningDetail =
    locale === "zh-CN"
      ? hasCjkText(warning)
        ? String(warning)
        : "当前运行读面暂时不可用，请稍后再试。"
      : String(warning || "");
  return (
    <main className="grid" aria-labelledby="runs-page-title">
      <header className="app-section">
        <div className="section-header">
          <div>
            <p className="cell-sub mono muted">{locale === "zh-CN" ? "OpenVibeCoding / 证明与回放桌" : "OpenVibeCoding / proof and replay"}</p>
            <h1 id="runs-page-title" className="page-title">{runsPageCopy.title}</h1>
            <p className="page-subtitle">{runsPageCopy.subtitle}</p>
            <p className="desk-question">
              {locale === "zh-CN"
                ? "这张桌子第一眼只回答一个问题：现在哪条运行最值得立刻证明。"
                : "This desk should answer one question first: which run deserves proof right now."}
            </p>
          </div>
          <Badge>{runsPageCopy.countsBadge(runs.length)}</Badge>
        </div>
      </header>
      <section className="app-section" aria-label={locale === "zh-CN" ? "运行列表" : "Run list"}>
        {warning ? (
          <Card variant="compact" role="status" aria-live="polite">
            <p className="ct-home-empty-text">{runsPageCopy.warningTitle}</p>
            <p className="mono muted">{runsPageCopy.warningNextStep}</p>
            <p className="mono muted">{warningDetail}</p>
          </Card>
        ) : null}
        <Card variant="compact">
          <p className="mono muted">{operatorDeskNote}</p>
        </Card>
        <div className="stats-grid">
          <Card asChild variant="metric">
            <article>
              <p className="metric-label">{runsPageCopy.metricLabels.runInventory}</p>
              <p className="metric-value metric-value--primary">{runs.length}</p>
              <p className="cell-sub mono muted">{runsPageCopy.inventorySubline}</p>
            </article>
          </Card>
          <Card asChild variant="metric">
            <article>
              <p className="metric-label">{runsPageCopy.metricLabels.replayPosture}</p>
              <p className={`metric-value ${distributionClass}`}>{distributionHeadline}</p>
              <p className="cell-sub mono muted">{distributionSubline}</p>
            </article>
          </Card>
          <Card asChild variant="metric">
            <article>
              <p className="metric-label">{runsPageCopy.metricLabels.operatorPriority}</p>
              <p className={`metric-value ${hasPartialTruthWarning || failed > 0 ? "metric-value--warning" : "metric-value--success"}`}>{governanceHeadline}</p>
              <p className="cell-sub mono muted">{governanceSubline}</p>
              <div className="inline-stack">
                <Button asChild variant={hasPartialTruthWarning || failed > 0 ? "warning" : "secondary"}>
                  <Link href={governanceCtaHref}>{governanceCtaLabel}</Link>
                </Button>
                {failed > 0 ? (
                  <Button asChild variant="ghost">
                    <Link href="/events">{runsPageCopy.operatorSecondaryAction}</Link>
                  </Button>
                ) : null}
              </div>
            </article>
          </Card>
        </div>
        <div className="toolbar toolbar--mt" role="group" aria-label={runsPageCopy.filterAriaLabel}>
          <Button asChild variant={statusFilter === "" ? "default" : "ghost"}>
            <Link href="/runs">{runsPageCopy.filters.all}</Link>
          </Button>
          <Button asChild variant={statusFilter === "FAILED" ? "warning" : "ghost"}>
            <Link href="/runs?status=FAILED">{runsPageCopy.filters.failed}</Link>
          </Button>
          <Button asChild variant={statusFilter === "RUNNING" ? "secondary" : "ghost"}>
            <Link href="/runs?status=RUNNING">{runsPageCopy.filters.running}</Link>
          </Button>
          <Button asChild variant={statusFilter === "SUCCESS" ? "secondary" : "ghost"}>
            <Link href="/runs?status=SUCCESS">{runsPageCopy.filters.success}</Link>
          </Button>
        </div>
        {runs.length > visibleRuns.length ? (
          <p className="mono muted" role="status">
            {runsPageCopy.firstScreenLimit(visibleRuns.length)}
          </p>
        ) : null}
        <RunList runs={visibleRuns} locale={locale} />
      </section>
    </main>
  );
}
