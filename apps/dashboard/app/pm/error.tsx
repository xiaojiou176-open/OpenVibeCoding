"use client";

import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import { sanitizeUiError, uiErrorDetail } from "../../lib/uiError";

export default function PmPageError({ error, reset }: { error: Error; reset: () => void }) {
  const safeMessage = sanitizeUiError(error, "Failed to load the PM workspace");
  console.error(`[pm-page-error-boundary] ${uiErrorDetail(error)}`);

  return (
    <main className="grid" aria-labelledby="pm-error-title">
      <header className="app-section">
        <div className="section-header">
          <div>
            <h1 id="pm-error-title">Failed to load the PM workspace</h1>
            <p>Session or message data is temporarily unavailable. Retry or check backend health.</p>
          </div>
        </div>
      </header>
      <section className="app-section" aria-label="PM page error state">
        <Card className="alert alert-danger" role="alert">
          <p className="mono">{safeMessage}</p>
          <div className="toolbar mt-2">
            <Button variant="default" onClick={reset}>
              Retry loading
            </Button>
          </div>
        </Card>
      </section>
    </main>
  );
}
