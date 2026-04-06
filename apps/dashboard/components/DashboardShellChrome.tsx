"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { DEFAULT_UI_LOCALE, getUiCopy, type UiLocale } from "@cortexpilot/frontend-shared/uiCopy";
import {
  detectPreferredUiLocale,
  readPreferredUiLocaleCookie,
  persistPreferredUiLocale,
  toggleUiLocale,
} from "@cortexpilot/frontend-shared/uiLocale";
import AppNav from "./AppNav";
import { DashboardLocaleProvider } from "./DashboardLocaleContext";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";

type DashboardShellChromeProps = {
  children: ReactNode;
};

export default function DashboardShellChrome({ children }: DashboardShellChromeProps) {
  const router = useRouter();
  const [locale, setLocale] = useState<UiLocale>(DEFAULT_UI_LOCALE);

  useEffect(() => {
    const detected = detectPreferredUiLocale();
    const cookieLocale = readPreferredUiLocaleCookie(document.cookie);
    setLocale(detected);
    if (cookieLocale !== detected) {
      persistPreferredUiLocale(detected);
      router.refresh();
    }
  }, [router]);

  const uiCopy = useMemo(() => getUiCopy(locale), [locale]);

  return (
    <DashboardLocaleProvider locale={locale} setLocale={setLocale}>
      <a className="skip-link" href="#dashboard-content">
        {uiCopy.dashboard.skipToMainContent}
      </a>
      <div className="app-shell">
        <aside className="sidebar" aria-label={uiCopy.dashboard.navigationAriaLabel}>
          <div className="sidebar-brand">
            <Link href="/" className="brand-link">
              {uiCopy.brandTitle}
            </Link>
            <p className="sidebar-subtitle">{uiCopy.brandSubtitle}</p>
          </div>
          <AppNav locale={locale} />
        </aside>

        <div className="app-main">
          <header className="topbar" role="banner">
            <p className="topbar-title">{uiCopy.dashboard.topbarTitle}</p>
            <div className="home-section-health" role="group" aria-label={uiCopy.dashboard.platformStatusAriaLabel}>
              <Badge>{uiCopy.dashboard.badges.governanceView}</Badge>
              <Badge>{uiCopy.dashboard.badges.liveVerificationRequired}</Badge>
              <Badge>{uiCopy.dashboard.badges.pageLevelStatus}</Badge>
              <Button
                variant="ghost"
                aria-label={uiCopy.dashboard.localeToggleAriaLabel}
                onClick={() => {
                  setLocale((previous) => {
                    const next = toggleUiLocale(previous);
                    persistPreferredUiLocale(next);
                    router.refresh();
                    return next;
                  });
                }}
              >
                {uiCopy.dashboard.localeToggleButtonLabel}
              </Button>
            </div>
          </header>
          <div className="content" id="dashboard-content">
            {children}
          </div>
        </div>
      </div>
    </DashboardLocaleProvider>
  );
}
