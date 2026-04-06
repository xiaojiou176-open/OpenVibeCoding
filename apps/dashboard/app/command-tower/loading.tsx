export default function CommandTowerLoading() {
  return (
    <main className="grid" aria-labelledby="command-tower-loading-title" aria-busy="true">
      <header className="app-section">
        <div className="section-header">
          <div>
            <h1 id="command-tower-loading-title">Loading Command Tower</h1>
            <p>Gathering session overview, alerts, and live status. Please wait.</p>
          </div>
        </div>
      </header>
      <section className="app-section" aria-label="Command Tower loading state">
        <div className="stats-grid">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="metric-card skeleton-stack">
              <div className="skeleton skeleton-text skeleton-w-50" />
              <div className="skeleton skeleton-metric skeleton-w-40" />
            </div>
          ))}
        </div>
        <div className="grid-2 skeleton-gap-top">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="skeleton skeleton-card skeleton-card-tall" />
          ))}
        </div>
      </section>
    </main>
  );
}
