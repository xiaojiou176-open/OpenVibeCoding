import { useMemo, useState } from "react";
import type { UiLocale } from "@openvibecoding/frontend-shared/uiCopy";
import { detectPreferredUiLocale } from "@openvibecoding/frontend-shared/uiLocale";
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
export function SearchPage({ locale = detectPreferredUiLocale() as UiLocale }: { locale?: UiLocale } = {}) {
  const copy =
    locale === "zh-CN"
      ? {
          title: "检索",
          subtitle: "在同一张操作页里查看检索输出、核验摘要和证据提升状态。",
          runId: "运行 ID",
          placeholder: "输入 run_id",
          load: "加载",
          loading: "加载中...",
          promote: "提升为 EvidenceBundle",
          promoting: "正在提升证据...",
          missingRunId: "请先输入运行 ID。",
          missingPromoteRunId: "缺少运行 ID。",
          promoteSuccess: "已提升为 EvidenceBundle。",
          promoteFailed: "提升失败。",
          primaryResult: "主结果",
          primaryIntro: "先显示操作者可读摘要，再显示更深的证据层。",
          rawResults: "原始结果",
          rawIntro: "原始输出只用于对比，不直接进入 PM 上下文。",
          noResults: "暂无结果。",
          verification: "核验",
          aiVerification: "AI 核验",
          purifiedSummary: "净化摘要",
          purifiedIntro: "净化后的输出可以进入 PM 和技术负责人判断。",
          advancedEvidence: "高级证据",
          status: "状态",
          topic: "主题",
          page: "页面",
          focus: "关注点",
          timeRange: "时间范围",
          generatedAt: "生成时间",
          failureReason: "失败原因",
          keyPoints: "关键点",
          screenshotEvidence: "截图证据",
          providerCounts: "提供方计数",
          consensusDomains: "共识域名",
          divergentDomains: "分歧域名",
          purifiedRaw: "净化摘要（原始 JSON）",
          searchTitle: "Search",
        }
      : {
          title: "Search",
          subtitle: "Review search outputs, verification summaries, and evidence promotion state in one operator surface.",
          runId: "Run ID",
          placeholder: "Enter run_id",
          load: "Load",
          loading: "Loading...",
          promote: "Promote to EvidenceBundle",
          promoting: "Promoting evidence...",
          missingRunId: "Enter a Run ID.",
          missingPromoteRunId: "Missing Run ID.",
          promoteSuccess: "Promoted to EvidenceBundle.",
          promoteFailed: "Promotion failed.",
          primaryResult: "Primary result",
          primaryIntro: "Raw output is for comparison only and does not enter PM context.",
          rawResults: "Raw results",
          rawIntro: "Raw output is for comparison only and does not enter PM context.",
          noResults: "No results.",
          verification: "Verification",
          aiVerification: "AI verification",
          purifiedSummary: "Purified summary",
          purifiedIntro: "Purified output is eligible for PM and Tech Lead decisions.",
          advancedEvidence: "Advanced Evidence",
          status: "Status",
          topic: "Topic",
          page: "Page",
          focus: "Focus",
          timeRange: "Time range",
          generatedAt: "Generated at",
          failureReason: "Failure reason",
          keyPoints: "Key points",
          screenshotEvidence: "Screenshot evidence",
          providerCounts: "Provider counts",
          consensusDomains: "Consensus domains",
          divergentDomains: "Divergent domains",
          purifiedRaw: "Purified summary (raw JSON)",
          searchTitle: "Search",
        };
  const [runId, setRunId] = useState("");
  const [data, setData] = useState<Record<string, JsonValue> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [promoteStatus, setPromoteStatus] = useState("");
  const [promoteTone, setPromoteTone] = useState<"success" | "error" | "">("");

  async function handleSearch() {
    if (!runId.trim()) { setError(copy.missingRunId); return; }
    setLoading(true); setError(""); setPromoteStatus(""); setPromoteTone(""); setData(null);
    try { setData(await fetchRunSearch(runId.trim())); }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setLoading(false); }
  }

  async function handlePromote() {
    if (!runId.trim()) { setPromoteStatus(copy.missingPromoteRunId); setPromoteTone("error"); return; }
    setPromoteStatus(copy.promoting);
    setPromoteTone("");
    try {
      const resp = await promoteEvidence(runId.trim());
      if (resp?.ok) {
        setPromoteStatus(copy.promoteSuccess);
        setPromoteTone("success");
        const bundle = resp.bundle;
        if (bundle !== undefined) {
          setData((prev) => (prev ? { ...prev, evidence_bundle: bundle } : prev));
        }
      } else {
        setPromoteStatus(copy.promoteFailed);
        setPromoteTone("error");
      }
    } catch (err) {
      setPromoteStatus(err instanceof Error ? err.message : copy.promoteFailed);
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
        <div><h1 className="page-title">{copy.title}</h1><p className="page-subtitle">{copy.subtitle}</p></div>
      </div>

      {/* Search bar */}
      <Card className="p-4 stack-gap-3">
        <label className="row-start-gap-2">
          <span className="mono text-sm fw-500">{copy.runId}</span>
          <Input className="input-max-400 flex-1" value={runId} onChange={(e) => setRunId(e.target.value)} placeholder={copy.placeholder} onKeyDown={(e) => { if (e.key === "Enter") void handleSearch(); }} />
        </label>
        <div className="row-gap-2">
          <Button variant="primary" disabled={loading} onClick={handleSearch}>{loading ? copy.loading : copy.load}</Button>
          <Button disabled={loading || !runId.trim()} onClick={handlePromote}>{copy.promote}</Button>
        </div>
        {error && <div className="alert alert-danger">{error}</div>}
        {promoteStatus && <div className={`mono text-sm ${promoteTone === "error" ? "text-danger" : "text-success"}`}>{promoteStatus}</div>}
      </Card>

      {/* Results grid */}
      {data && (
        <div className="grid-2 mt-4">
          {newsDigestResult ? (
            <Card className="p-4 stack-gap-3" data-testid="desktop-news-digest-card">
              <h3 className="text-base fw-600">{copy.primaryResult}</h3>
              <p className="muted text-sm">{locale === "zh-CN" ? `${String(newsDigestResult.task_template || "public_digest")} 会先显示操作者可读摘要，再显示更深的证据。` : `${String(newsDigestResult.task_template || "public_digest")} shows the operator-readable summary first, followed by advanced evidence.`}</p>
              <div className="data-list">
                <div className="data-list-row"><span className="data-list-label">{copy.status}</span><span className="data-list-value mono">{String(newsDigestResult.status || "-")}</span></div>
                <div className="data-list-row"><span className="data-list-label">{String(newsDigestResult.task_template) === "page_brief" ? copy.page : copy.topic}</span><span className="data-list-value mono">{String(String(newsDigestResult.task_template) === "page_brief" ? (newsDigestResult.page_title || newsDigestResult.url || "-") : (newsDigestResult.topic || "-"))}</span></div>
                <div className="data-list-row"><span className="data-list-label">{String(newsDigestResult.task_template) === "page_brief" ? copy.focus : copy.timeRange}</span><span className="data-list-value mono">{String(String(newsDigestResult.task_template) === "page_brief" ? (newsDigestResult.focus || "-") : (newsDigestResult.time_range || "-"))}</span></div>
                <div className="data-list-row"><span className="data-list-label">{copy.generatedAt}</span><span className="data-list-value mono">{String(newsDigestResult.generated_at || "-")}</span></div>
              </div>
              <p>{String(newsDigestResult.summary || "-")}</p>
              {newsDigestResult.failure_reason_zh ? (
                <p className="text-sm muted">{copy.failureReason}: {String(newsDigestResult.failure_reason_zh)}</p>
              ) : null}
              {String(newsDigestResult.task_template) === "page_brief" ? (
                <>
                  <details className="collapsible">
                    <summary>{copy.keyPoints}</summary>
                    <div className="collapsible-body"><pre>{JSON.stringify(newsDigestResult.key_points || [], null, 2)}</pre></div>
                  </details>
                  <details className="collapsible">
                    <summary>{copy.screenshotEvidence}</summary>
                    <div className="collapsible-body"><pre>{JSON.stringify({ screenshot_artifact: newsDigestResult.screenshot_artifact || null }, null, 2)}</pre></div>
                  </details>
                </>
              ) : (
                <details className="collapsible">
                  <summary>{locale === "zh-CN" ? "来源" : "Sources"}</summary>
                  <div className="collapsible-body"><pre>{JSON.stringify(newsDigestResult.sources || [], null, 2)}</pre></div>
                </details>
              )}
            </Card>
          ) : null}
          {/* Raw results */}
          <Card className="p-4 stack-gap-3">
            <h3 className="text-base fw-600">{copy.rawResults}</h3>
            <p className="muted text-sm">{copy.rawIntro}</p>
            {rawResults.length === 0 ? <p className="muted">{locale === "zh-CN" ? "当前还没有原始结果。" : "No raw results yet."}</p> : (
              <div className="stack-gap-2">
                {rawResults.map((group) => (
                  <Card key={group.provider} className="p-3">
                    <strong className="mono text-sm">{group.provider}</strong>
                    {group.items.length === 0 ? <p className="muted">{copy.noResults}</p> : (
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
              <summary>{copy.verification}</summary>
              <div className="collapsible-body"><pre>{JSON.stringify(verificationLatest || {}, null, 2)}</pre></div>
            </details>
            <details className="collapsible">
              <summary>{copy.aiVerification}</summary>
              <div className="collapsible-body"><pre>{JSON.stringify(verificationAiLatest || {}, null, 2)}</pre></div>
            </details>
          </Card>

          {/* Purified summary */}
          <Card className="p-4 stack-gap-3">
            <h3 className="text-base fw-600">{copy.purifiedSummary}</h3>
            <p className="muted text-sm">{copy.purifiedIntro}</p>

            <div className="data-list">
              <div className="data-list-row"><span className="data-list-label">{copy.providerCounts}</span><span className="data-list-value mono">{JSON.stringify(providerCounts)}</span></div>
              <div className="data-list-row"><span className="data-list-label">{copy.consensusDomains}</span><span className="data-list-value mono">{JSON.stringify(consensusDomains)}</span></div>
              <div className="data-list-row"><span className="data-list-label">{copy.divergentDomains}</span><span className="data-list-value mono">{JSON.stringify(divergentDomains)}</span></div>
            </div>

            <details className="collapsible">
              <summary>{copy.purifiedRaw}</summary>
              <div className="collapsible-body"><pre>{JSON.stringify(purifiedLatest || {}, null, 2)}</pre></div>
            </details>
          </Card>

          {/* Evidence bundle */}
          <Card className="p-4 stack-gap-3">
            <h3 className="text-base fw-600">{copy.advancedEvidence}</h3>
            {browserLatest ? <pre className="pre-scroll-300 text-sm">{JSON.stringify(browserLatest, null, 2)}</pre> : null}
            <pre className="pre-scroll-300 text-sm">{JSON.stringify(data?.evidence_bundle || {}, null, 2)}</pre>
          </Card>
        </div>
      )}
    </div>
  );
}
