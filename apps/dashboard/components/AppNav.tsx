"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactElement } from "react";
import { DEFAULT_UI_LOCALE, getUiCopy, type UiLocale } from "@openvibecoding/frontend-shared/uiCopy";
import { Badge } from "./ui/badge";

type NavItem = {
  href: string;
  label: string;
  icon: string;
};

type NavSection = {
  title: string;
  items: NavItem[];
};

function buildNavSections(locale: UiLocale): NavSection[] {
  const uiCopy = getUiCopy(locale);
  return [
    {
      title: uiCopy.dashboard.sectionPrimary,
      items: [
        { href: "/", label: uiCopy.dashboard.labels.overview, icon: "grid" },
        { href: "/pm", label: uiCopy.dashboard.labels.pmIntake, icon: "message" },
        { href: "/planner", label: uiCopy.dashboard.labels.planner, icon: "map" },
        { href: "/command-tower", label: uiCopy.dashboard.labels.commandTower, icon: "tower" },
        { href: "/workflows", label: uiCopy.dashboard.labels.workflowCases, icon: "workflow" },
        { href: "/runs", label: uiCopy.dashboard.labels.runs, icon: "play" },
        { href: "/god-mode", label: uiCopy.dashboard.labels.quickApproval, icon: "zap" },
        { href: "/agents", label: uiCopy.dashboard.labels.agents, icon: "bot" },
        { href: "/contracts", label: uiCopy.dashboard.labels.contracts, icon: "file" },
      ],
    },
    {
      title: uiCopy.dashboard.sectionAdvanced,
      items: [
        { href: "/search", label: uiCopy.dashboard.labels.search, icon: "search" },
        { href: "/events", label: uiCopy.dashboard.labels.events, icon: "activity" },
        { href: "/reviews", label: uiCopy.dashboard.labels.reviews, icon: "check" },
        { href: "/diff-gate", label: uiCopy.dashboard.labels.diffGate, icon: "shield" },
        { href: "/tests", label: uiCopy.dashboard.labels.tests, icon: "test" },
        { href: "/policies", label: uiCopy.dashboard.labels.policies, icon: "lock" },
        { href: "/locks", label: uiCopy.dashboard.labels.locks, icon: "key" },
        { href: "/worktrees", label: uiCopy.dashboard.labels.worktrees, icon: "tree" },
      ],
    },
  ];
}

const ICON_MAP: Record<string, ReactElement> = {
  grid: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="2" width="5" height="5" rx="1" />
      <rect x="9" y="2" width="5" height="5" rx="1" />
      <rect x="2" y="9" width="5" height="5" rx="1" />
      <rect x="9" y="9" width="5" height="5" rx="1" />
    </svg>
  ),
  message: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 3h10a1 1 0 011 1v6a1 1 0 01-1 1H6l-3 3V4a1 1 0 011-1z" />
    </svg>
  ),
  tower: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M8 2v12M4 6h8M5 2h6M3 14h10" />
    </svg>
  ),
  play: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="8" cy="8" r="6" />
      <path d="M6.5 5.5l4 2.5-4 2.5z" fill="currentColor" />
    </svg>
  ),
  workflow: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="4" cy="4" r="2" />
      <circle cx="12" cy="8" r="2" />
      <circle cx="4" cy="12" r="2" />
      <path d="M6 4h4l2 4M6 12h4l2-4" />
    </svg>
  ),
  map: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2.5 3.5l3-1.5 5 2 3-1.5v10l-3 1.5-5-2-3 1.5z" />
      <path d="M5.5 2v10M10.5 4v10" />
    </svg>
  ),
  activity: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 8h3l1.5-4 3 8L11 8h3" />
    </svg>
  ),
  search: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="7" cy="7" r="4.5" />
      <path d="M10.5 10.5L14 14" />
    </svg>
  ),
  shield: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M8 2l5 2v4c0 3-2.5 5-5 6-2.5-1-5-3-5-6V4l5-2z" />
    </svg>
  ),
  file: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 2h5l4 4v8a1 1 0 01-1 1H4a1 1 0 01-1-1V3a1 1 0 011-1z" />
      <path d="M9 2v4h4" />
    </svg>
  ),
  check: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="8" cy="8" r="6" />
      <path d="M5.5 8l2 2 3.5-3.5" />
    </svg>
  ),
  test: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M6 2v4l-3 7h10l-3-7V2M5 2h6" />
    </svg>
  ),
  lock: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="7" width="10" height="7" rx="1" />
      <path d="M5 7V5a3 3 0 016 0v2" />
    </svg>
  ),
  bot: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="4" width="10" height="9" rx="2" />
      <circle cx="6" cy="8" r="1" fill="currentColor" />
      <circle cx="10" cy="8" r="1" fill="currentColor" />
      <path d="M8 1v3" />
    </svg>
  ),
  key: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="5.5" cy="10.5" r="3" />
      <path d="M8 8l5-5M11 3l2 2" />
    </svg>
  ),
  tree: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 14V8h0M8 14V2M12 14V6" />
      <circle cx="4" cy="8" r="1.5" />
      <circle cx="8" cy="2" r="1.5" />
      <circle cx="12" cy="6" r="1.5" />
    </svg>
  ),
  zap: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 1L3 9h5l-1 6 6-8H8l1-6z" />
    </svg>
  ),
};

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

type AppNavProps = {
  locale?: UiLocale;
};

export default function AppNav({ locale = DEFAULT_UI_LOCALE }: AppNavProps) {
  const pathname = usePathname() || "/";
  const uiCopy = getUiCopy(locale);
  const navSections = buildNavSections(locale);

  return (
    <nav className="sidebar-nav" aria-label={uiCopy.dashboard.navigationAriaLabel}>
      {navSections.map((section) => (
        <section key={section.title} className="sidebar-section">
          {section.title === uiCopy.dashboard.sectionAdvanced ? (
            <details
              className="sidebar-section-details"
              open={section.items.some((item) => isActive(pathname, item.href))}
            >
              <summary className="sidebar-section-summary">
                <span className="sidebar-section-title">{section.title}</span>
                <Badge>{uiCopy.dashboard.lowFrequencyToolsLabel} {section.items.length}</Badge>
              </summary>
              <ul className="sidebar-list">
                {section.items.map((item) => {
                  const isCurrent = isActive(pathname, item.href);
                  return (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        aria-current={isCurrent ? "page" : undefined}
                        className={`sidebar-link ${isCurrent ? "is-active" : ""}`}
                      >
                        {ICON_MAP[item.icon] || null}
                        {item.label}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </details>
          ) : (
            <>
              <h2 className="sidebar-section-title">{section.title}</h2>
              <ul className="sidebar-list">
                {section.items.map((item) => {
                  const isCurrent = isActive(pathname, item.href);
                  return (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        aria-current={isCurrent ? "page" : undefined}
                        className={`sidebar-link ${isCurrent ? "is-active" : ""}`}
                      >
                        {ICON_MAP[item.icon] || null}
                        {item.label}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </>
          )}
        </section>
      ))}
    </nav>
  );
}
