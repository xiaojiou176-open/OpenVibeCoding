import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SearchPage } from "./SearchPage";

vi.mock("../lib/api", () => ({
  fetchRunSearch: vi.fn(),
  promoteEvidence: vi.fn(),
}));

import { fetchRunSearch, promoteEvidence } from "../lib/api";

describe("SearchPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchRunSearch).mockResolvedValue({ raw: {}, purified: {}, verification: {}, verification_ai: {} } as any);
    vi.mocked(promoteEvidence).mockResolvedValue({ ok: true, bundle: { run_id: "run-001" } } as any);
  });

  it("validates empty run id and handles search error", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchRunSearch).mockRejectedValueOnce(new Error("search failed"));

    render(<SearchPage />);

    await user.click(screen.getByRole("button", { name: "Load" }));
    expect(screen.getByText("Enter a Run ID.")).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText("Enter run_id"), "run-err");
    await user.click(screen.getByRole("button", { name: "Load" }));

    expect(await screen.findByText("search failed")).toBeInTheDocument();
  });

  it("renders grouped raw results, summary fields and truncation branch", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchRunSearch).mockResolvedValueOnce({
      raw: {
        latest: {
          results: [
            {
              provider: "google",
              results: [
                { title: "r1" },
                { title: "r2" },
                { title: "r3" },
                { title: "r4" },
                { title: "r5" },
                { title: "r6" },
                { title: "r7" },
              ],
            },
            { provider: "exa", results: [] },
          ],
        },
      },
      purified: {
        latest: {
          summary: {
            provider_counts: { google: 7, exa: 0 },
            consensus_domains: ["example.com"],
            divergent_domains: ["x.dev"],
          },
        },
      },
      verification: { latest: { ok: true } },
      verification_ai: { latest: { confidence: 0.9 } },
      evidence_bundle: { run_id: "run-001" },
    } as any);

    render(<SearchPage />);

    await user.type(screen.getByPlaceholderText("Enter run_id"), "run-001");
    await user.click(screen.getByRole("button", { name: "Load" }));

    expect(await screen.findByText("Raw results")).toBeInTheDocument();
    expect(screen.getByText("google")).toBeInTheDocument();
    expect(screen.getByText("exa")).toBeInTheDocument();
    expect(screen.getByText("No results.")).toBeInTheDocument();
    expect(screen.getByText("... +1 more")).toBeInTheDocument();
    expect(screen.getByText(/"google":7/)).toBeInTheDocument();
    expect(screen.getByText(/\["example.com"\]/)).toBeInTheDocument();
    expect(screen.getByText(/\["x.dev"\]/)).toBeInTheDocument();
  });

  it("renders news_digest summary card before advanced evidence", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchRunSearch).mockResolvedValueOnce({
      raw: { latest: { results: [] } },
      purified: { latest: { summary: {} } },
      news_digest_result: {
        task_template: "news_digest",
        status: "SUCCESS",
        topic: "Seattle AI",
        time_range: "24h",
        generated_at: "2026-03-24T00:00:00Z",
        max_results: 3,
        summary: 'Compiled 2 public sources for "Seattle AI".',
        sources: [{ title: "Title A", url: "https://example.com/a" }],
        evidence_refs: { raw: "artifacts/search_results.json" },
      },
    } as any);

    render(<SearchPage />);

    await user.type(screen.getByPlaceholderText("Enter run_id"), "run-news");
    await user.click(screen.getByRole("button", { name: "Load" }));

    expect(await screen.findByTestId("desktop-news-digest-card")).toHaveTextContent("Seattle AI");
    expect(screen.getByTestId("desktop-news-digest-card")).toHaveTextContent('Compiled 2 public sources for "Seattle AI".');
  });

  it("renders failed news_digest summary with human-readable failure reason", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchRunSearch).mockResolvedValueOnce({
      raw: { latest: { results: [] } },
      purified: { latest: { summary: {} } },
      news_digest_result: {
        task_template: "news_digest",
        status: "FAILED",
        topic: "Seattle AI",
        time_range: "24h",
        generated_at: "2026-03-24T00:00:00Z",
        max_results: 3,
        summary: '"Seattle AI" digest could not be completed.',
        sources: [],
        evidence_refs: { raw: "artifacts/search_results.json" },
        failure_reason_zh: "来源链路失败（provider=grok_web）：upstream timeout",
      },
    } as any);

    render(<SearchPage />);

    await user.type(screen.getByPlaceholderText("Enter run_id"), "run-digest-failed");
    await user.click(screen.getByRole("button", { name: "Load" }));

    expect(await screen.findByTestId("desktop-news-digest-card")).toHaveTextContent("Failure reason: 来源链路失败（provider=grok_web）：upstream timeout");
  });

  it("renders topic_brief summary through the same primary card", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchRunSearch).mockResolvedValueOnce({
      raw: { latest: { results: [] } },
      purified: { latest: { summary: {} } },
      topic_brief_result: {
        task_template: "topic_brief",
        status: "SUCCESS",
        topic: "Seattle AI",
        time_range: "7d",
        generated_at: "2026-03-24T00:00:00Z",
        max_results: 2,
        summary: 'Generated a public read-only topic brief for "Seattle AI".',
        sources: [{ title: "Title A", url: "https://example.com/a" }],
        evidence_refs: { raw: "artifacts/search_results.json" },
      },
    } as any);

    render(<SearchPage />);

    await user.type(screen.getByPlaceholderText("Enter run_id"), "run-topic-brief");
    await user.click(screen.getByRole("button", { name: "Load" }));

    expect(await screen.findByTestId("desktop-news-digest-card")).toHaveTextContent("topic_brief");
    expect(screen.getByTestId("desktop-news-digest-card")).toHaveTextContent('Generated a public read-only topic brief for "Seattle AI".');
  });

  it("renders page_brief summary through the same primary card", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchRunSearch).mockResolvedValueOnce({
      raw: { latest: { results: [] } },
      browser_results: { latest: { results: [{ task_id: "browser_0", ok: true }] } },
      purified: { latest: { summary: {} } },
      page_brief_result: {
        task_template: "page_brief",
        status: "SUCCESS",
        url: "https://example.com",
        resolved_url: "https://example.com/",
        page_title: "Example Domain",
        focus: "Summarize the page for a first-time reader.",
        generated_at: "2026-03-24T00:00:00Z",
        summary: "Example Domain: This domain is for use in illustrative examples in documents.",
        key_points: ["Example Domain", "This domain is for use in illustrative examples in documents."],
        screenshot_artifact: "artifacts/browser/example.png",
      },
    } as any);

    render(<SearchPage />);

    await user.type(screen.getByPlaceholderText("Enter run_id"), "run-page-brief");
    await user.click(screen.getByRole("button", { name: "Load" }));

    expect(await screen.findByTestId("desktop-news-digest-card")).toHaveTextContent("page_brief");
    expect(screen.getByTestId("desktop-news-digest-card")).toHaveTextContent("Example Domain");
    expect(screen.getByTestId("desktop-news-digest-card")).toHaveTextContent("artifacts/browser/example.png");
  });

  it("handles promote branches: success, not-ok and thrown error", async () => {
    const user = userEvent.setup();

    render(<SearchPage />);

    await user.type(screen.getByPlaceholderText("Enter run_id"), "run-001");
    await user.click(screen.getByRole("button", { name: "Promote to EvidenceBundle" }));
    await waitFor(() => {
      expect(promoteEvidence).toHaveBeenCalledWith("run-001");
      expect(screen.getByText("Promoted to EvidenceBundle.")).toBeInTheDocument();
    });

    vi.mocked(promoteEvidence).mockResolvedValueOnce({ ok: false } as any);
    await user.click(screen.getByRole("button", { name: "Promote to EvidenceBundle" }));
    expect(await screen.findByText("Promotion failed.")).toBeInTheDocument();

    vi.mocked(promoteEvidence).mockRejectedValueOnce(new Error("network down"));
    await user.click(screen.getByRole("button", { name: "Promote to EvidenceBundle" }));
    expect(await screen.findByText("network down")).toBeInTheDocument();
  });
});
