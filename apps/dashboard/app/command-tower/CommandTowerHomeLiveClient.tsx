"use client";

import dynamic from "next/dynamic";
import { useMemo } from "react";
import { getUiCopy, type UiLocale } from "@cortexpilot/frontend-shared/uiCopy";

import type { CommandTowerOverviewPayload, PmSessionSummary } from "../../lib/types";

type CommandTowerHomeLiveClientProps = {
  initialOverview: CommandTowerOverviewPayload;
  initialSessions: PmSessionSummary[];
  locale?: UiLocale;
};

export default function CommandTowerHomeLiveClient({
  initialOverview,
  initialSessions,
  locale = "en",
}: CommandTowerHomeLiveClientProps) {
  const commandTowerPageCopy = getUiCopy(locale).dashboard.commandTowerPage;
  const CommandTowerHomeLive = useMemo(
    () =>
      dynamic(() => import("../../components/command-tower/CommandTowerHomeLive"), {
        ssr: false,
        loading: () => (
          <div className="compact-status-card" role="status" aria-live="polite">
            <p className="mono">{commandTowerPageCopy.fallbackLoading}</p>
          </div>
        ),
      }),
    [commandTowerPageCopy.fallbackLoading],
  );
  return <CommandTowerHomeLive initialOverview={initialOverview} initialSessions={initialSessions} locale={locale} />;
}
