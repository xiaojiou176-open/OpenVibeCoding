import { Card } from "../components/ui/card";

export default function Loading() {
  return (
    <main className="grid" aria-labelledby="dashboard-loading-title" aria-busy="true">
      <header className="app-section">
        <div className="section-header">
          <div>
            <h1 id="dashboard-loading-title">Loading dashboard data</h1>
            <p>Please wait while the control plane aggregates runs, sessions, and governance signals.</p>
          </div>
        </div>
      </header>
      <section className="app-section" aria-label="Loading state">
        <div className="stats-grid">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="metric-card skeleton-stack">
              <div className="skeleton skeleton-text skeleton-w-40" />
              <div className="skeleton skeleton-metric" />
            </div>
          ))}
        </div>
        <Card variant="table" className="skeleton-gap-top">
          <div className="skeleton-stack-md">
            <div className="skeleton skeleton-heading" />
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="skeleton skeleton-row" />
            ))}
          </div>
        </Card>
      </section>
    </main>
  );
}
