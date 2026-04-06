import { useMemo, useState } from "react";
import type { JsonValue } from "../lib/types";
import { fetchRunSearch, promoteEvidence } from "../lib/api";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Input } from "../components/ui/Input";

/* ── helpers ── */
function getLatest(payload: Record<string, unknown> | null | undefined): Record<string, unknown> | null {
  if (!payload) return null;
  if (payload.latest && typeof payload.latest === "object") return payload.latest as Record<string, unknown>;
  return payload;
}

function groupByProvider(results: Array<Record<string, unknown>>) {
  const groups: { provider: string; items: Array<Record<string, unknown>> }[] = [];
  for (const entry of results) {
    const provider = String(entry?.provider || entry?.resolved_provider || entry?.mode || "unknown");
    const items = Array.isArray(entry?.results) ? (entry.results as Array<Record<string, unknown>>) : [];
    groups.push({ provider, items });
  }
  return groups;
}

function getNewsDigestResult(payload: Record<string, JsonValue> | null): Record<string, unknown> | null {
  if (!payload) return null;
  const candidate = payload.news_digest_result || payload.topic_brief_result || payload.page_brief_result;
  return candidate && typeof candidate === "object" ? (candidate as Record<string, unknown>) : null;
}

/* ── component ── */
export function SearchPage() {
  const [runId, setRunId] = useState("");
  const [data, setData] = useState<Record<string, JsonValue> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [promoteStatus, setPromoteStatus] = useState("");
  const [promoteTone, setPromoteTone] = useState<"success" | "error" | "">("");

  async function handleSearch() {
    if (!runId.trim()) { setError("Enter a Run ID."); return; }
    setLoading(true); setError(""); setPromoteStatus(""); setPromoteTone(""); setData(null);
    try { setData(await fetchRunSearch(runId.trim())); }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setLoading(false); }
  }

  async function handlePromote() {
    if (!runId.trim()) { setPromoteStatus("Missing Run ID."); setPromoteTone("error"); return; }
    setPromoteStatus("Promoting evidence...");
    setPromoteTone("");
    try {
      const resp = await promoteEvidence(runId.trim());
      if (resp?.ok) {
        setPromoteStatus("Promoted to EvidenceBundle.");
        setPromoteTone("success");
        const bundle = resp.bundle;
        if (bundle !== undefined) {
          setData((prev) => (prev ? { ...prev, evidence_bundle: bundle } : prev));
        }
      } else {
        setPromoteStatus("Promotion failed.");
        setPromoteTone("error");
      }
    } catch (err) {
      setPromoteStatus(err instanceof Error ? err.message : "Promotion failed.");
      setPromoteTone("error");
    }
  }

  /* derived data */
  const rawLatest = useMemo(() => getLatest(data?.raw as Record<string, unknown> | undefined), [data]);
  const newsDigestResult = useMemo(() => getNewsDigestResult(data), [data]);
  const browserLatest = useMemo(() => getLatest(data?.browser_results as Record<string, unknown> | undefined), [data]);
  const purifiedLatest = useMemo(() => {
    return getLatest(data?.purified as Record<string, unknown> | undefined) || getLatest(data?.search_summary as Record<string, unknown> | undefined);
  }, [data]);
  const verificationLatest = useMemo(() => getLatest(data?.verification as Record<string, unknown> | undefined), [data]);
  const verificationAiLatest = useMemo(() => getLatest(data?.verification_ai as Record<string, unknown> | undefined), [data]);

  const rawResults = useMemo(() => {
    if (!rawLatest) return [];
    const items = Array.isArray(rawLatest?.results) ? (rawLatest.results as Array<Record<string, unknown>>) : [];
    return groupByProvider(items);
  }, [rawLatest]);

  const consensusDomains = (purifiedLatest?.summary as Record<string, unknown>)?.consensus_domains || purifiedLatest?.consensus_domains || [];
  const divergentDomains = (purifiedLatest?.summary as Record<string, unknown>)?.divergent_domains || purifiedLatest?.divergent_domains || [];
  const providerCounts = (purifiedLatest?.summary as Record<string, unknown>)?.provider_counts || purifiedLatest?.provider_counts || {};

  return (
    <div className="content">
      <div className="section-header">
        <div><h1 className="page-title">Search</h1><p className="page-subtitle">Review search outputs, verification summaries, and evidence promotion state in one operator surface.</p></div>
      </div>

      {/* Search bar */}
      <Card className="p-4 stack-gap-3">
        <label className="row-start-gap-2">
          <span className="mono text-sm fw-500">Run ID</span>
          <Input className="input-max-400 flex-1" value={runId} onChange={(e) => setRunId(e.target.value)} placeholder="Enter run_id" onKeyDown={(e) => { if (e.key === "Enter") void handleSearch(); }} />
        </label>
        <div className="row-gap-2">
          <Button variant="primary" disabled={loading} onClick={handleSearch}>{loading ? "Loading..." : "Load"}</Button>
          <Button disabled={loading || !runId.trim()} onClick={handlePromote}>Promote to EvidenceBundle</Button>
        </div>
        {error && <div className="alert alert-danger">{error}</div>}
        {promoteStatus && <div className={`mono text-sm ${promoteTone === "error" ? "text-danger" : "text-success"}`}>{promoteStatus}</div>}
      </Card>

      {/* Results grid */}
      {data && (
        <div className="grid-2 mt-4">
          {newsDigestResult ? (
            <Card className="p-4 stack-gap-3" data-testid="desktop-news-digest-card">
              <h3 className="text-base fw-600">Primary result</h3>
              <p className="muted text-sm">{String(newsDigestResult.task_template || "public_digest")} shows the operator-readable summary first, followed by advanced evidence.</p>
              <div className="data-list">
                <div className="data-list-row"><span className="data-list-label">Status</span><span className="data-list-value mono">{String(newsDigestResult.status || "-")}</span></div>
                <div className="data-list-row"><span className="data-list-label">{String(newsDigestResult.task_template) === "page_brief" ? "Page" : "Topic"}</span><span className="data-list-value mono">{String(String(newsDigestResult.task_template) === "page_brief" ? (newsDigestResult.page_title || newsDigestResult.url || "-") : (newsDigestResult.topic || "-"))}</span></div>
                <div className="data-list-row"><span className="data-list-label">{String(newsDigestResult.task_template) === "page_brief" ? "Focus" : "Time range"}</span><span className="data-list-value mono">{String(String(newsDigestResult.task_template) === "page_brief" ? (newsDigestResult.focus || "-") : (newsDigestResult.time_range || "-"))}</span></div>
                <div className="data-list-row"><span className="data-list-label">Generated at</span><span className="data-list-value mono">{String(newsDigestResult.generated_at || "-")}</span></div>
              </div>
              <p>{String(newsDigestResult.summary || "-")}</p>
              {newsDigestResult.failure_reason_zh ? (
                <p className="text-sm muted">Failure reason: {String(newsDigestResult.failure_reason_zh)}</p>
              ) : null}
              {String(newsDigestResult.task_template) === "page_brief" ? (
                <>
                  <details className="collapsible">
                    <summary>Key points</summary>
                    <div className="collapsible-body"><pre>{JSON.stringify(newsDigestResult.key_points || [], null, 2)}</pre></div>
                  </details>
                  <details className="collapsible">
                    <summary>Screenshot evidence</summary>
                    <div className="collapsible-body"><pre>{JSON.stringify({ screenshot_artifact: newsDigestResult.screenshot_artifact || null }, null, 2)}</pre></div>
                  </details>
                </>
              ) : (
                <details className="collapsible">
                  <summary>Sources</summary>
                  <div className="collapsible-body"><pre>{JSON.stringify(newsDigestResult.sources || [], null, 2)}</pre></div>
                </details>
              )}
            </Card>
          ) : null}
          {/* Raw results */}
          <Card className="p-4 stack-gap-3">
            <h3 className="text-base fw-600">Raw results</h3>
            <p className="muted text-sm">Raw output is for comparison only and does not enter PM context.</p>
            {rawResults.length === 0 ? <p className="muted">No raw results yet.</p> : (
              <div className="stack-gap-2">
                {rawResults.map((group) => (
                  <Card key={group.provider} className="p-3">
                    <strong className="mono text-sm">{group.provider}</strong>
                    {group.items.length === 0 ? <p className="muted">No results.</p> : (
                      <ul className="list-pl-4 text-sm ul-reset-margin">
                        {group.items.slice(0, 6).map((item, idx) => (
                          <li key={idx} className="mono">{String(item?.title || item?.name || item?.href || "result")}</li>
                        ))}
                        {group.items.length > 6 && <li className="muted">... +{group.items.length - 6} more</li>}
                      </ul>
                    )}
                  </Card>
                ))}
              </div>
            )}

            {/* Verification */}
            <details className="collapsible">
              <summary>Verification</summary>
              <div className="collapsible-body"><pre>{JSON.stringify(verificationLatest || {}, null, 2)}</pre></div>
            </details>
            <details className="collapsible">
              <summary>AI verification</summary>
              <div className="collapsible-body"><pre>{JSON.stringify(verificationAiLatest || {}, null, 2)}</pre></div>
            </details>
          </Card>

          {/* Purified summary */}
          <Card className="p-4 stack-gap-3">
            <h3 className="text-base fw-600">Purified summary</h3>
            <p className="muted text-sm">Purified output is eligible for PM and Tech Lead decisions.</p>

            <div className="data-list">
              <div className="data-list-row"><span className="data-list-label">Provider counts</span><span className="data-list-value mono">{JSON.stringify(providerCounts)}</span></div>
              <div className="data-list-row"><span className="data-list-label">Consensus domains</span><span className="data-list-value mono">{JSON.stringify(consensusDomains)}</span></div>
              <div className="data-list-row"><span className="data-list-label">Divergent domains</span><span className="data-list-value mono">{JSON.stringify(divergentDomains)}</span></div>
            </div>

            <details className="collapsible">
              <summary>Purified summary (raw JSON)</summary>
              <div className="collapsible-body"><pre>{JSON.stringify(purifiedLatest || {}, null, 2)}</pre></div>
            </details>
          </Card>

          {/* Evidence bundle */}
          <Card className="p-4 stack-gap-3">
            <h3 className="text-base fw-600">Advanced Evidence</h3>
            {browserLatest ? <pre className="pre-scroll-300 text-sm">{JSON.stringify(browserLatest, null, 2)}</pre> : null}
            <pre className="pre-scroll-300 text-sm">{JSON.stringify(data?.evidence_bundle || {}, null, 2)}</pre>
          </Card>
        </div>
      )}
    </div>
  );
}
