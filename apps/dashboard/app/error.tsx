"use client";

import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { sanitizeUiError, uiErrorDetail } from "../lib/uiError";

export default function Error({ error, reset }: { error: Error; reset: () => void }) {
  const safeMessage = sanitizeUiError(error, "Page load failed");
  console.error(`[dashboard-error-boundary] ${uiErrorDetail(error)}`);

  return (
    <main className="grid" aria-labelledby="dashboard-error-title">
      <header className="app-section">
        <div className="section-header">
          <div>
            <h1 id="dashboard-error-title">Page load failed</h1>
            <p>The dashboard could not load its control-plane data. Retry or inspect backend health first.</p>
          </div>
        </div>
      </header>
      <section className="app-section" aria-label="Error state">
        <Card className="alert alert-danger" role="alert">
          <p className="mono">{safeMessage}</p>
          <div className="toolbar mt-2">
            <Button type="button" variant="default" onClick={reset}>
              Retry load
            </Button>
          </div>
        </Card>
      </section>
    </main>
  );
}
