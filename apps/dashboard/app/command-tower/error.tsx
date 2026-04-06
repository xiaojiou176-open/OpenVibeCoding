"use client";

import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import { sanitizeUiError, uiErrorDetail } from "../../lib/uiError";

export default function CommandTowerError({ error, reset }: { error: Error; reset: () => void }) {
  const safeMessage = sanitizeUiError(error, "Command Tower failed to load");
  console.error(`[command-tower-error-boundary] ${uiErrorDetail(error)}`);

  return (
    <main className="grid" aria-labelledby="command-tower-error-title">
      <header className="app-section">
        <div className="section-header">
          <div>
            <h1 id="command-tower-error-title">Command Tower failed to load</h1>
            <p>Live session data is unavailable right now. Try again later or inspect the backend service.</p>
          </div>
        </div>
      </header>
      <section className="app-section" aria-label="Command Tower error state">
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
