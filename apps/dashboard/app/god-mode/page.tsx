"use client";

import GodModePanel from "../../components/GodModePanel";
import { useDashboardLocale } from "../../components/DashboardLocaleContext";

export default function GodModePage() {
  const { uiCopy } = useDashboardLocale();
  const approvalCopy = uiCopy.dashboard.approval;

  return (
    <main className="grid" aria-labelledby="god-mode-page-title">
      <header className="app-section">
        <div className="section-header">
          <div>
            <h1 id="god-mode-page-title">{approvalCopy.pageTitle}</h1>
            <p>{approvalCopy.pageSubtitle}</p>
          </div>
        </div>
      </header>
      <section className="app-section" aria-label={approvalCopy.pageTitle}>
        <GodModePanel />
      </section>
    </main>
  );
}
