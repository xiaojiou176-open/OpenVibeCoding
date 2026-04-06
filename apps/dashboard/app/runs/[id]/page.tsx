import { cookies } from "next/headers";
import { getUiCopy } from "@cortexpilot/frontend-shared/uiCopy";
import { normalizeUiLocale, UI_LOCALE_STORAGE_KEY } from "@cortexpilot/frontend-shared/uiLocale";
import RunDetail from "../../../components/RunDetail";
import { Badge } from "../../../components/ui/badge";
import { Card } from "../../../components/ui/card";
import ControlPlaneStatusCallout from "../../../components/control-plane/ControlPlaneStatusCallout";
import OperatorCopilotPanel from "../../../components/control-plane/OperatorCopilotPanel";
import { fetchRun, fetchEvents, fetchDiff, fetchReports } from "../../../lib/api";
import { safeLoad } from "../../../lib/serverPageData";
import Link from "next/link";

type RunDetailPageParams = {
  id: string;
};

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function asNumber(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

export default async function RunDetailPage({
  params,
}: {
  params: Promise<RunDetailPageParams>;
}) {
  const cookieStore = await cookies();
  const locale = normalizeUiLocale(cookieStore.get(UI_LOCALE_STORAGE_KEY)?.value);
  const uiCopy = getUiCopy(locale);
  const runDetailPageCopy = uiCopy.dashboard.runDetailPage;
  const runDetailCopy = uiCopy.desktop.runDetail;
  const { id } = await params;
  const { data: run, warning: runWarning } = await safeLoad(() => fetchRun(id), { run_id: id, status: "UNKNOWN" } as any, "Run detail");
  const { data: events, warning: eventsWarning } = await safeLoad(() => fetchEvents(id), [] as any[], "Run events");
  const { data: diffResp, warning: diffWarning } = await safeLoad(() => fetchDiff(id), { diff: "" }, "Code diff");
  const { data: reports, warning: reportsWarning } = await safeLoad(() => fetchReports(id), [] as any[], "Run reports");
  const warning = runWarning || eventsWarning || diffWarning || reportsWarning;
  const diff = diffResp?.diff || "";
  const reportList = Array.isArray(reports) ? reports : [];
  const incidentPack = asRecord(reportList.find((item) => item?.name === "incident_pack.json")?.data);
  const proofPack = asRecord(reportList.find((item) => item?.name === "proof_pack.json")?.data);
  const compareSummary = asRecord(asRecord(reportList.find((item) => item?.name === "run_compare_report.json")?.data).compare_summary);
  const hasCompareSummary = Object.keys(compareSummary).length > 0;
  const compareDeltaCount =
    asNumber(compareSummary.mismatched_count) +
    asNumber(compareSummary.missing_count) +
    asNumber(compareSummary.extra_count) +
    asNumber(compareSummary.failed_report_checks_count);
  return (
    <main className="grid" aria-labelledby="run-detail-page-title">
      <section className="app-section">
        <div className="section-header">
          <div>
            <h1 id="run-detail-page-title" data-testid="run-detail-title">{runDetailPageCopy.title}</h1>
            <p>{runDetailPageCopy.subtitle}</p>
          </div>
          <div className="toolbar">
            <Badge className="mono">{id}</Badge>
            <Link href={`/runs/${encodeURIComponent(id)}/compare`}>{runDetailPageCopy.openCompareSurface}</Link>
          </div>
        </div>
        {warning ? (
          <ControlPlaneStatusCallout
            title={runDetailPageCopy.degradedTitle}
            summary={warning}
            nextAction={runDetailPageCopy.degradedNextAction}
            tone="warning"
            badgeLabel={runDetailPageCopy.degradedBadge}
            actions={[
              { href: `/runs/${encodeURIComponent(id)}`, label: runDetailPageCopy.reloadAction },
              { href: "/runs", label: runDetailPageCopy.backToRunsAction },
            ]}
          />
        ) : null}
        {(Object.keys(incidentPack).length > 0 || Object.keys(proofPack).length > 0 || hasCompareSummary) ? (
          <div className="grid grid-3">
            <Card>
              <h3>{runDetailPageCopy.compareDecisionTitle}</h3>
              <p className="muted">
                {!hasCompareSummary
                  ? runDetailPageCopy.compareMissing
                  : compareDeltaCount === 0
                  ? runDetailPageCopy.compareAligned
                  : runDetailPageCopy.compareNeedsReview}
              </p>
              <p className="mono">
                {!hasCompareSummary
                  ? runDetailPageCopy.compareNextStepMissing
                  : compareDeltaCount === 0
                  ? runDetailPageCopy.compareNextStepAligned
                  : runDetailPageCopy.compareNextStepNeedsReview}
              </p>
            </Card>
            <Card>
              <h3>{runDetailPageCopy.incidentActionTitle}</h3>
              <p className="muted">{String(incidentPack.summary || runDetailPageCopy.incidentMissing)}</p>
              <p className="mono">{runDetailCopy.fieldLabels.nextAction}: {String(incidentPack.next_action || runDetailPageCopy.incidentNextStepFallback)}</p>
            </Card>
            <Card>
              <h3>{runDetailPageCopy.proofActionTitle}</h3>
              <p className="muted">{String(proofPack.summary || runDetailPageCopy.proofMissing)}</p>
              <p className="mono">{runDetailCopy.fieldLabels.nextAction}: {String(proofPack.next_action || runDetailPageCopy.proofNextStepFallback)}</p>
            </Card>
          </div>
        ) : null}
        <OperatorCopilotPanel runId={id} />
        <RunDetail run={run} events={events} diff={diff} reports={reports} />
      </section>
    </main>
  );
}
