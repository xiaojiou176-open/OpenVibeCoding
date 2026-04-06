import { Card } from "../../components/ui/card";

export default function PmPageLoading() {
  return (
    <main className="grid" aria-labelledby="pm-loading-title" aria-busy="true">
      <header className="app-section">
        <div className="section-header">
          <div>
            <h1 id="pm-loading-title">Loading the PM workspace</h1>
            <p>Syncing sessions and chat context. Please wait.</p>
          </div>
        </div>
      </header>
      <section className="app-section" aria-label="PM page loading state">
        <Card className="skeleton-stack-lg">
          <div className="skeleton skeleton-heading skeleton-w-45" />
          <div className="skeleton-stack-md">
            <div className="skeleton skeleton-input-narrow" />
            <div className="skeleton skeleton-input-wide" />
            <div className="skeleton skeleton-block" />
          </div>
          <div className="skeleton skeleton-btn" />
        </Card>
      </section>
    </main>
  );
}
