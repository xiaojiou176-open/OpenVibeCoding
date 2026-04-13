import type { Metadata } from "next";
import { cookies } from "next/headers";
import { getUiCopy } from "@cortexpilot/frontend-shared/uiCopy";
import { normalizeUiLocale, UI_LOCALE_STORAGE_KEY } from "@cortexpilot/frontend-shared/uiLocale";
import Link from "next/link";
import { Suspense } from "react";
import CommandTowerHomeLiveClient from "./CommandTowerHomeLiveClient";
import ControlPlaneStatusCallout from "../../components/control-plane/ControlPlaneStatusCallout";
import { fetchCommandTowerOverview, fetchPmSessions } from "../../lib/api";
import { safeLoad } from "../../lib/serverPageData";
import type { CommandTowerOverviewPayload, PmSessionSummary } from "../../lib/types";
import type { UiLocale } from "@cortexpilot/frontend-shared/uiCopy";

export const metadata: Metadata = {
  title: "Command Tower | OpenVibeCoding",
  description:
    "Monitor live operator visibility, linked Workflow Cases, blockers, and next operator actions from the OpenVibeCoding command tower cockpit.",
};

async function CommandTowerHomeSection({ locale }: { locale: UiLocale }) {
  const commandTowerCopy = getUiCopy(locale).dashboard.commandTowerPage;
  const fallbackOverview: CommandTowerOverviewPayload = {
    generated_at: new Date().toISOString(),
    total_sessions: 0,
    active_sessions: 0,
    failed_sessions: 0,
    blocked_sessions: 0,
    failed_ratio: 0,
    blocked_ratio: 0,
    failure_trend_30m: 0,
    top_blockers: [],
  };
  const fallbackSessions: PmSessionSummary[] = [];

  const settled = await Promise.allSettled([
    safeLoad(fetchCommandTowerOverview, fallbackOverview, "Command Tower overview"),
    safeLoad(() => fetchPmSessions({ limit: 40 }), fallbackSessions, "PM session list"),
  ]);

  const overviewResult =
    settled[0].status === "fulfilled"
      ? settled[0].value
      : { data: fallbackOverview, warning: "Command Tower overview is unavailable right now. Please try again later." };
  const sessionsResult =
    settled[1].status === "fulfilled"
      ? settled[1].value
      : { data: fallbackSessions, warning: "The PM session list is unavailable right now. Please try again later." };

  const overview = overviewResult.data;
  const sessions = sessionsResult.data;
  const overviewWarning = overviewResult.warning;
  const sessionsWarning = sessionsResult.warning;
  const warning = [overviewWarning, sessionsWarning].filter(Boolean).join(" ");
  const hasLiveData =
    (overview.total_sessions || 0) > 0 ||
    (overview.active_sessions || 0) > 0 ||
    (sessions?.length || 0) > 0;

  return (
    <>
      {warning && !hasLiveData ? (
        <ControlPlaneStatusCallout
          title={commandTowerCopy.unavailableTitle}
          summary={warning}
          nextAction={commandTowerCopy.unavailableNextAction}
          tone="warning"
          badgeLabel={commandTowerCopy.unavailableBadge}
          actions={[
            { href: "/command-tower", label: commandTowerCopy.actions.reload },
            { href: "/runs", label: commandTowerCopy.actions.viewRuns },
            { href: "/pm", label: commandTowerCopy.actions.startFromPm },
          ]}
        />
      ) : null}
      {warning && hasLiveData ? (
        <ControlPlaneStatusCallout
          title={commandTowerCopy.partialTitle}
          summary={warning}
          nextAction={commandTowerCopy.partialNextAction}
          tone="warning"
          badgeLabel={commandTowerCopy.partialBadge}
          actions={[
            { href: "/runs", label: commandTowerCopy.actions.openRuns },
            { href: "/workflows", label: commandTowerCopy.actions.openWorkflowCases },
          ]}
        />
      ) : null}
      <section aria-label="Command Tower live overview" aria-describedby="command-tower-page-subtitle">
        <CommandTowerHomeLiveClient initialOverview={overview} initialSessions={sessions} locale={locale} />
      </section>
    </>
  );
}

function CommandTowerHomeSectionFallback({ locale }: { locale: UiLocale }) {
  const commandTowerCopy = getUiCopy(locale).dashboard.commandTowerPage;
  return (
    <section aria-label="Command Tower live overview" aria-describedby="command-tower-page-subtitle" aria-busy="true">
      <p className="mono" role="status">{commandTowerCopy.fallbackLoading}</p>
    </section>
  );
}

export default async function CommandTowerPage() {
  const cookieStore = await cookies();
  const locale = normalizeUiLocale(cookieStore.get(UI_LOCALE_STORAGE_KEY)?.value);
  const commandTowerCopy = getUiCopy(locale).dashboard.commandTowerPage;
  return (
    <main className="grid" aria-labelledby="command-tower-page-title" aria-describedby="command-tower-page-subtitle">
      <h1 id="command-tower-page-title" className="sr-only">
        {commandTowerCopy.srTitle}
      </h1>
      <p id="command-tower-page-subtitle" className="sr-only">
        {commandTowerCopy.srSubtitle}
      </p>
      <Suspense fallback={<CommandTowerHomeSectionFallback locale={locale} />}>
        <CommandTowerHomeSection locale={locale} />
      </Suspense>
    </main>
  );
}
