"use client";

import { useMemo } from "react";
import { Card } from "../../components/ui/card";

type SearchPayload = Record<string, unknown>;

function getLatest(payload: SearchPayload | null | undefined): SearchPayload | null {
  if (!payload) {
    return null;
  }
  if (payload.latest && typeof payload.latest === "object") {
    return payload.latest as SearchPayload;
  }
  return payload;
}

function groupByProvider(results: Array<SearchPayload>) {
  const grouped: { provider: string; items: Array<SearchPayload> }[] = [];
  for (const entry of results) {
    const provider = String(entry?.provider || entry?.resolved_provider || entry?.mode || "unknown");
    const items = Array.isArray(entry?.results) ? (entry.results as Array<SearchPayload>) : [];
    grouped.push({ provider, items });
  }
  return grouped;
}

function asRecord(value: unknown): SearchPayload | null {
  return typeof value === "object" && value !== null ? (value as SearchPayload) : null;
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function readText(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function containsHanText(value: string): boolean {
  return /[\u4e00-\u9fff]/.test(value);
}

function taskResultTargetLabel(result: SearchPayload): string {
  const taskTemplate = readText(result.task_template);
  if (taskTemplate === "page_brief") {
    return readText(result.page_title) || readText(result.url) || "the requested page";
  }
  return readText(result.topic) || "the requested topic";
}

function fallbackTaskSummary(result: SearchPayload): string {
  const taskTemplate = readText(result.task_template);
  const status = readText(result.status).toUpperCase();
  const target = taskResultTargetLabel(result);

  if (taskTemplate === "news_digest") {
    if (status === "FAILED") return `Public digest for "${target}" did not complete.`;
    if (status === "EMPTY") return `Public digest for "${target}" returned no matched public sources.`;
    return `Public digest for "${target}" is ready.`;
  }
  if (taskTemplate === "topic_brief") {
    if (status === "FAILED") return `Topic brief for "${target}" did not complete.`;
    if (status === "EMPTY") return `Topic brief for "${target}" returned no matched public sources.`;
    return `Public read-only topic brief for "${target}" is ready.`;
  }
  if (taskTemplate === "page_brief") {
    if (status === "FAILED") return `Page brief for "${target}" did not complete.`;
    if (status === "EMPTY") return `Page brief for "${target}" returned no readable page result.`;
    return `Page brief for "${target}" is ready.`;
  }
  return status ? `Task result status: ${status}.` : "Task result is available.";
}

function taskResultSummary(result: SearchPayload): string {
  const explicitEnglish = [result.summary_en, result.summary].map(readText).find((value) => value && !containsHanText(value));
  if (explicitEnglish) {
    return explicitEnglish;
  }
  const rawSummary = readText(result.summary);
  if (!rawSummary || containsHanText(rawSummary)) {
    return fallbackTaskSummary(result);
  }
  return rawSummary;
}

function taskFailureReason(result: SearchPayload): string {
  const explicitEnglish = [result.failure_reason_en, result.failure_reason].map(readText).find(Boolean);
  if (explicitEnglish) {
    return explicitEnglish;
  }

  const localizedReason = readText(result.failure_reason_zh);
  if (!localizedReason) {
    return "";
  }

  const providerMatch = localizedReason.match(/provider=([^)）\s]+)/i);
  const segments = localizedReason.split(/[：:]/);
  const trailingDetail = segments.length > 1 ? segments.slice(1).join(":").trim() : "";
  if (containsHanText(localizedReason) && providerMatch) {
    const providerPart = providerMatch ? ` (provider=${providerMatch[1]})` : "";
    return `Source pipeline failed${providerPart}${trailingDetail ? `: ${trailingDetail}` : ""}`;
  }
  if (trailingDetail) {
    return `Task failed: ${trailingDetail}`;
  }
  return "Task failed. Check raw results for details.";
}

function getPrimaryPublicDigestResult(payload: SearchPayload | null | undefined): SearchPayload | null {
  return asRecord(payload?.news_digest_result) || asRecord(payload?.topic_brief_result) || asRecord(payload?.page_brief_result);
}

export default function SearchResultsPanel({ data }: { data: SearchPayload }) {
  const rawLatest = useMemo(() => getLatest(data?.raw as SearchPayload | undefined), [data]);
  const newsDigestResult = useMemo(() => getPrimaryPublicDigestResult(data), [data]);
  const browserLatest = useMemo(() => getLatest(data?.browser_results as SearchPayload | undefined), [data]);
  const purifiedLatest = useMemo(() => {
    return getLatest(data?.purified as SearchPayload | undefined) || getLatest(data?.search_summary as SearchPayload | undefined);
  }, [data]);
  const verificationLatest = useMemo(() => getLatest(data?.verification as SearchPayload | undefined), [data]);
  const verificationAiLatest = useMemo(() => getLatest(data?.verification_ai as SearchPayload | undefined), [data]);

  const rawResults = useMemo(() => {
    if (!rawLatest) {
      return [];
    }
    const items = Array.isArray(rawLatest?.results) ? (rawLatest.results as Array<SearchPayload>) : [];
    return groupByProvider(items);
  }, [rawLatest]);

  const purifiedSummary = asRecord(purifiedLatest?.summary);
  const consensusDomains = asArray(purifiedSummary?.consensus_domains ?? purifiedLatest?.consensus_domains);
  const divergentDomains = asArray(purifiedSummary?.divergent_domains ?? purifiedLatest?.divergent_domains);
  const providerCounts = asRecord(purifiedSummary?.provider_counts ?? purifiedLatest?.provider_counts) ?? {};
  const digestSummary = newsDigestResult ? taskResultSummary(newsDigestResult) : "-";
  const digestFailureReason = newsDigestResult ? taskFailureReason(newsDigestResult) : "";

  return (
    <div className="grid grid-2">
      {newsDigestResult ? (
        <Card data-testid="search-news-digest-card">
          <h3>Task result</h3>
          <div className="mono">{String(newsDigestResult.task_template || "public_digest")} appears in a readable summary first, with Raw / Evidence moved to the advanced section.</div>
          <div className="search-card-section">
            <strong>Summary</strong>
            <p>{digestSummary}</p>
          </div>
          {digestFailureReason ? (
            <div className="search-card-section">
              <strong>Failure reason</strong>
              <p>{digestFailureReason}</p>
            </div>
          ) : null}
          <div className="search-card-section">
            <strong>{String(newsDigestResult.task_template) === "page_brief" ? "Page metadata" : "Topic"}</strong>
            <pre className="mono">{JSON.stringify(
              String(newsDigestResult.task_template) === "page_brief"
                ? {
                    url: newsDigestResult.url,
                    resolved_url: newsDigestResult.resolved_url,
                    page_title: newsDigestResult.page_title,
                    focus: newsDigestResult.focus,
                    status: newsDigestResult.status,
                    generated_at: newsDigestResult.generated_at,
                  }
                : {
                    topic: newsDigestResult.topic,
                    time_range: newsDigestResult.time_range,
                    max_results: newsDigestResult.max_results,
                    status: newsDigestResult.status,
                    generated_at: newsDigestResult.generated_at,
                  },
              null,
              2,
            )}</pre>
          </div>
          {String(newsDigestResult.task_template) === "page_brief" ? (
            <>
              <div className="search-card-section">
                <strong>Key points</strong>
                <pre className="mono">{JSON.stringify(newsDigestResult.key_points || [], null, 2)}</pre>
              </div>
              <div className="search-card-section">
                <strong>Screenshot evidence</strong>
                <pre className="mono">{JSON.stringify({ screenshot_artifact: newsDigestResult.screenshot_artifact || null }, null, 2)}</pre>
              </div>
            </>
          ) : (
            <>
              <div className="search-card-section">
                <strong>Sources</strong>
                <pre className="mono">{JSON.stringify(newsDigestResult.sources || [], null, 2)}</pre>
              </div>
              <div className="search-card-section">
                <strong>Evidence refs</strong>
                <pre className="mono">{JSON.stringify(newsDigestResult.evidence_refs || {}, null, 2)}</pre>
              </div>
            </>
          )}
        </Card>
      ) : null}

      <Card data-testid="search-raw-results-card">
        <h3>Raw results</h3>
        <div className="mono">Raw output stays comparison-only and does not enter PM context.</div>
        {rawResults.length === 0 ? (
          <div className="mono search-card-section">No raw results yet</div>
        ) : (
          <div className="search-provider-grid">
            {rawResults.map((group) => (
              <Card key={group.provider}>
                <div className="mono">{group.provider}</div>
                {group.items.length === 0 ? (
                  <div className="mono">No results yet</div>
                ) : (
                  <ul>
                    {group.items.slice(0, 6).map((item, idx) => (
                      <li key={`${group.provider}-${idx}`} className="mono">
                        {String(item?.title ?? item?.name ?? item?.href ?? "result")}
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            ))}
          </div>
        )}
        <div className="search-card-section">
          <strong>Verification</strong>
          <pre className="mono">{JSON.stringify(verificationLatest || {}, null, 2)}</pre>
          <strong>AI verification</strong>
          <pre className="mono">{JSON.stringify(verificationAiLatest || {}, null, 2)}</pre>
        </div>
      </Card>

      <Card data-testid="search-purified-summary-card">
        <h3>Purified summary</h3>
        <div className="mono">Purified output is safe to use in PM / Tech Lead decision loops.</div>
        <div className="search-card-section">
          <strong>Provider counts</strong>
          <pre className="mono">{JSON.stringify(providerCounts || {}, null, 2)}</pre>
        </div>
        <div className="search-card-section">
          <strong>Consensus domains</strong>
          <pre className="mono">{JSON.stringify(consensusDomains || [], null, 2)}</pre>
        </div>
        <div className="search-card-section">
          <strong>Divergent domains</strong>
          <pre className="mono">{JSON.stringify(divergentDomains || [], null, 2)}</pre>
        </div>
        <div className="search-card-section">
          <strong>Purified summary (raw JSON)</strong>
          <pre className="mono">{JSON.stringify(purifiedLatest || {}, null, 2)}</pre>
        </div>
      </Card>

      <Card data-testid="search-evidence-bundle-card">
        <h3>Advanced Evidence</h3>
        {browserLatest ? (
          <div className="search-card-section">
            <strong>Browser Results</strong>
            <pre className="mono">{JSON.stringify(browserLatest, null, 2)}</pre>
          </div>
        ) : null}
        <pre className="mono">{JSON.stringify(data?.evidence_bundle || {}, null, 2)}</pre>
      </Card>
    </div>
  );
}
