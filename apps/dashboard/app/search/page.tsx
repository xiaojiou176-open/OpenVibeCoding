"use client";

import dynamic from "next/dynamic";
import { useState } from "react";
import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import { Input } from "../../components/ui/input";
import { fetchRunSearch, promoteEvidence } from "../../lib/api";
import { sanitizeUiError, uiErrorDetail } from "../../lib/uiError";

const LazySearchResultsPanel = dynamic(() => import("./SearchResultsPanel"));

export default function SearchPage() {
  const [runId, setRunId] = useState("");
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [promoteStatus, setPromoteStatus] = useState<string | null>(null);
  const [hasAttemptedLoad, setHasAttemptedLoad] = useState(false);
  const [loading, setLoading] = useState(false);
  const [promoting, setPromoting] = useState(false);

  async function load() {
    if (!runId.trim()) {
      setStatus("Enter a run ID.");
      return;
    }
    setHasAttemptedLoad(true);
    setLoading(true);
    setStatus(null);
    setPromoteStatus(null);
    try {
      const resp = await fetchRunSearch(runId.trim());
      setData(resp);
      setStatus(`Loaded run ID: ${runId.trim()}`);
    } catch (err: unknown) {
      console.error(`[search-page] load failed: ${uiErrorDetail(err)}`);
      setStatus(sanitizeUiError(err, "Load failed"));
      setData(null);
    } finally {
      setLoading(false);
    }
  }

  async function handlePromote() {
    if (!runId.trim()) {
      setPromoteStatus("Run ID is required.");
      return;
    }
    setPromoting(true);
    setPromoteStatus("Promoting evidence...");
    try {
      const resp = await promoteEvidence(runId.trim());
      if (resp?.ok) {
        setPromoteStatus("Promoted to EvidenceBundle");
        setData((prev) => (prev ? { ...prev, evidence_bundle: (resp as Record<string, unknown>).bundle } : prev));
      } else {
        setPromoteStatus("Promotion failed");
      }
    } catch (err: unknown) {
      console.error(`[search-page] promote failed: ${uiErrorDetail(err)}`);
      setPromoteStatus(sanitizeUiError(err, "Promotion failed"));
    } finally {
      setPromoting(false);
    }
  }

  function clearResult() {
    setData(null);
    setStatus("Cleared the current result. Enter a run ID to load again.");
    setPromoteStatus(null);
    setHasAttemptedLoad(false);
  }

  const hasErrorStatus = Boolean(status && (status.includes("failed") || status.includes("error")));
  const hasWarningStatus = Boolean(status && (status.includes("Enter") || status.includes("required")));
  const hasPromoteError = Boolean(promoteStatus && (promoteStatus.includes("failed") || promoteStatus.includes("error")));
  const hasPromoteWarning = Boolean(promoteStatus && promoteStatus.includes("required"));

  return (
    <main className="grid" aria-labelledby="search-page-title">
      <header className="app-section">
        <div className="section-header">
          <div>
            <h1 id="search-page-title" className="page-title">Search</h1>
            <p className="page-subtitle">Review search results, verification summaries, and evidence-promotion status from one place.</p>
          </div>
        </div>
      </header>
      <section className="app-section" aria-label="Search page content">
        <Card data-testid="search-control-card">
          <label className="search-run-label" htmlFor="search-run-id">
            <span className="mono">Run ID</span>
            <Input
              id="search-run-id"
              variant="unstyled"
              className="search-run-input"
              data-testid="search-run-id-input"
              value={runId}
              onChange={(event) => setRunId(event.target.value)}
              placeholder="Run ID"
            />
          </label>
          <div className="toolbar mt-2">
            <Button variant="default" type="button" onClick={load} disabled={loading} data-testid="search-load-button">
              {loading ? "Loading..." : "Load"}
            </Button>
            <Button variant="secondary" type="button" onClick={handlePromote} disabled={loading || promoting} data-testid="search-promote-button">
              {promoting ? "Promoting..." : "Promote to evidence bundle"}
            </Button>
            <Button variant="ghost" type="button" onClick={clearResult} disabled={loading || promoting} data-testid="search-clear-button">
              Clear result
            </Button>
          </div>
          <div className="mono muted search-card-section">Next: enter a run ID, load the result, then promote an evidence bundle only if the output looks correct.</div>
          {status ? (
            <div
              className={`alert ${hasErrorStatus ? "alert-danger" : hasWarningStatus ? "alert-warning" : "alert-success"} search-status`}
              role={hasErrorStatus ? "alert" : "status"}
              data-testid="search-status-message"
            >
              {status}
            </div>
          ) : null}
          {promoteStatus ? (
            <div
              className={`alert ${hasPromoteError ? "alert-danger" : hasPromoteWarning ? "alert-warning" : "alert-success"} search-promote-status`}
              role={hasPromoteError ? "alert" : "status"}
              data-testid="search-promote-status-message"
            >
              {promoteStatus}
            </div>
          ) : null}
        </Card>

        {loading ? (
          <Card role="status" aria-live="polite" aria-busy="true" data-testid="search-loading-state">
            <div className="mono muted">Loading search results...</div>
            <div className="skeleton skeleton-card skeleton-card-tall" />
          </Card>
        ) : null}

        {!data && !loading ? (
          <Card data-testid="search-empty-state">
            <div className="empty-state-stack">
              <strong>{hasAttemptedLoad ? "No search result to display yet" : "Search has not started yet"}</strong>
              <span className="muted">
                {hasAttemptedLoad
                  ? "Check whether the run ID is valid, then retry the load."
                  : "Enter a run ID first, then click Load to inspect the raw result and purified summary."}
              </span>
              <span className="mono muted">Suggested flow: load result {"->"} verify summary {"->"} promote evidence only when needed.</span>
            </div>
          </Card>
        ) : null}

        {data ? <LazySearchResultsPanel data={data} /> : null}
      </section>
    </main>
  );
}
