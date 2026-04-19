"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { DEFAULT_UI_LOCALE, getUiCopy, type UiLocale } from "@openvibecoding/frontend-shared/uiCopy";
import {
  normalizeUiLocale,
  readPreferredUiLocaleCookie,
  persistPreferredUiLocale,
  toggleUiLocale,
  UI_LOCALE_STORAGE_KEY,
} from "@openvibecoding/frontend-shared/uiLocale";
import AppNav from "./AppNav";
import { DashboardLocaleProvider } from "./DashboardLocaleContext";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";

type DashboardShellChromeProps = {
  children: ReactNode;
  initialLocale?: UiLocale;
};

export default function DashboardShellChrome({
  children,
  initialLocale = DEFAULT_UI_LOCALE,
}: DashboardShellChromeProps) {
  const router = useRouter();
  const pathname = usePathname();
  const isLanding = pathname === "/";
  const [locale, setLocale] = useState<UiLocale>(initialLocale);

  useEffect(() => {
    const cookieLocale = readPreferredUiLocaleCookie(document.cookie);
    const hasCookie = document.cookie.includes(`${UI_LOCALE_STORAGE_KEY}=`);
    const storedLocale = window.localStorage.getItem(UI_LOCALE_STORAGE_KEY);
    const explicitLocale = storedLocale ? normalizeUiLocale(storedLocale) : hasCookie ? cookieLocale : undefined;
    const nextLocale = initialLocale !== DEFAULT_UI_LOCALE ? initialLocale : explicitLocale ?? initialLocale;

    setLocale(nextLocale);

    if (storedLocale !== nextLocale || cookieLocale !== nextLocale) {
      persistPreferredUiLocale(nextLocale);
    }

    if (nextLocale !== initialLocale) {
      router.refresh();
    }
  }, [initialLocale, router]);

  const uiCopy = useMemo(() => getUiCopy(locale), [locale]);

  return (
    <DashboardLocaleProvider locale={locale} setLocale={setLocale}>
      <a className="skip-link" href="#dashboard-content">
        {uiCopy.dashboard.skipToMainContent}
      </a>
      <div className={`app-shell ${isLanding ? "app-shell--landing" : ""}`}>
        <aside className="sidebar" aria-label={uiCopy.dashboard.navigationAriaLabel}>
          <div className="sidebar-brand">
            <Link href="/" className="brand-link" aria-label={uiCopy.brandTitle} title={uiCopy.brandTitle}>
              {isLanding ? "OVC" : uiCopy.brandTitle}
            </Link>
            <p className="sidebar-subtitle">{uiCopy.brandSubtitle}</p>
          </div>
          <AppNav locale={locale} compact={isLanding} />
        </aside>

        <div className="app-main">
          <header className="topbar" role="banner">
            <div className="topbar-copy">
              <p className="topbar-eyebrow">
                {locale === "zh-CN" ? "实时操作壳层" : "Live operator shell"}
              </p>
              <p className="topbar-title">{uiCopy.dashboard.topbarTitle}</p>
            </div>
            <div className="home-section-health" role="group" aria-label={uiCopy.dashboard.platformStatusAriaLabel}>
              {!isLanding ? (
                <>
                  <Badge>{uiCopy.dashboard.badges.governanceView}</Badge>
                  <Badge>{uiCopy.dashboard.badges.liveVerificationRequired}</Badge>
                  <Badge>{uiCopy.dashboard.badges.pageLevelStatus}</Badge>
                </>
              ) : null}
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
