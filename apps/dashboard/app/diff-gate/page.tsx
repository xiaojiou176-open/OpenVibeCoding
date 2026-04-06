import DiffGatePanel from "../../components/DiffGatePanel";

export default async function DiffGatePage() {
  return (
    <main className="grid" aria-labelledby="diff-gate-page-title">
      <header className="app-section">
        <div className="section-header">
          <div>
            <h1 id="diff-gate-page-title" className="page-title">Diff gate</h1>
            <p className="page-subtitle">Review change scope, trigger rollback or reject actions, and preserve the evidence trail.</p>
          </div>
        </div>
      </header>
      <section className="app-section" aria-label="Diff gate queue">
        <DiffGatePanel />
      </section>
    </main>
  );
}
