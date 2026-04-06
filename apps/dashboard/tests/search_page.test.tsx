import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({
  fetchRunSearch: vi.fn(),
  promoteEvidence: vi.fn(),
}));

import SearchPage from "../app/search/page";
import { fetchRunSearch, promoteEvidence } from "../lib/api";

describe("search page copy and interaction", () => {
  const mockFetchRunSearch = vi.mocked(fetchRunSearch);
  const mockPromoteEvidence = vi.mocked(promoteEvidence);

  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchRunSearch.mockResolvedValue({
      raw: { latest: { results: [] } },
      purified: { latest: { summary: {} } },
    });
    mockPromoteEvidence.mockResolvedValue({ ok: true, bundle: { id: "bundle-1" } } as never);
  });

  it("uses Run ID wording and avoids run_id copy", async () => {
    render(<SearchPage />);

    expect(screen.getByText("Run ID")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Run ID")).toBeInTheDocument();
    expect(screen.getByText("Next: enter a run ID, load the result, then promote an evidence bundle only if the output looks correct.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Load" }));
    expect(await screen.findByTestId("search-status-message")).toHaveTextContent("Enter a run ID.");

    fireEvent.change(screen.getByTestId("search-run-id-input"), { target: { value: "run-123" } });
    fireEvent.click(screen.getByRole("button", { name: "Load" }));
    await waitFor(() => {
      expect(mockFetchRunSearch).toHaveBeenCalledWith("run-123");
    });
    expect(await screen.findByTestId("search-status-message")).toHaveTextContent("Loaded run ID: run-123");
  });

  it("surfaces sanitized load failure and attempted empty state", async () => {
    mockFetchRunSearch.mockRejectedValueOnce(new Error("network timeout"));

    render(<SearchPage />);

    fireEvent.change(screen.getByTestId("search-run-id-input"), { target: { value: "run-fail" } });
    fireEvent.click(screen.getByRole("button", { name: "Load" }));

    expect(await screen.findByTestId("search-status-message")).toHaveTextContent("Load failed: network issue. Try again later.");
    expect(screen.getByTestId("search-empty-state")).toHaveTextContent("No search result to display yet");
  });

  it("blocks evidence promotion when run id is missing", async () => {
    render(<SearchPage />);

    fireEvent.click(screen.getByRole("button", { name: "Promote to evidence bundle" }));

    expect(await screen.findByTestId("search-promote-status-message")).toHaveTextContent("Run ID is required.");
    expect(mockPromoteEvidence).not.toHaveBeenCalled();
  });

  it("updates evidence bundle when promote succeeds after loading data", async () => {
    render(<SearchPage />);

    fireEvent.change(screen.getByTestId("search-run-id-input"), { target: { value: "run-123" } });
    fireEvent.click(screen.getByRole("button", { name: "Load" }));
    expect(await screen.findByTestId("search-status-message")).toHaveTextContent("Loaded run ID: run-123");

    fireEvent.click(screen.getByRole("button", { name: "Promote to evidence bundle" }));

    await waitFor(() => {
      expect(mockPromoteEvidence).toHaveBeenCalledWith("run-123");
    });
    await waitFor(() => {
      expect(screen.getByTestId("search-promote-status-message")).toHaveTextContent("Promoted to EvidenceBundle");
    });
    expect(screen.getByTestId("search-evidence-bundle-card")).toHaveTextContent("bundle-1");
  });

  it("shows promote failure when backend returns non-ok result", async () => {
    mockPromoteEvidence.mockResolvedValueOnce({ ok: false } as never);

    render(<SearchPage />);

    fireEvent.change(screen.getByTestId("search-run-id-input"), { target: { value: "run-456" } });
    fireEvent.click(screen.getByRole("button", { name: "Load" }));
    expect(await screen.findByTestId("search-status-message")).toHaveTextContent("Loaded run ID: run-456");

    fireEvent.click(screen.getByRole("button", { name: "Promote to evidence bundle" }));

    await waitFor(() => {
      expect(screen.getByTestId("search-promote-status-message")).toHaveTextContent("Promotion failed");
    });
  });

  it("clears loaded result and returns to initial empty-state guidance", async () => {
    render(<SearchPage />);

    fireEvent.change(screen.getByTestId("search-run-id-input"), { target: { value: "run-clear" } });
    fireEvent.click(screen.getByRole("button", { name: "Load" }));
    expect(await screen.findByTestId("search-status-message")).toHaveTextContent("Loaded run ID: run-clear");

    fireEvent.click(screen.getByRole("button", { name: "Clear result" }));

    expect(await screen.findByTestId("search-status-message")).toHaveTextContent("Cleared the current result. Enter a run ID to load again.");
    expect(screen.getByTestId("search-empty-state")).toHaveTextContent("Search has not started yet");
  });

  it("maps raw provider groups when payload omits latest wrapper", async () => {
    mockFetchRunSearch.mockResolvedValueOnce({
      raw: {
        results: [
          { provider: "exa", results: [{ title: "Title A" }] },
          { resolved_provider: "tavily", results: [{ name: "Name B" }, { href: "https://example.test/c" }] },
          { mode: "fallback", results: [] },
        ],
      },
      purified: {
        summary: {
          provider_counts: { exa: 1, tavily: 2 },
          consensus_domains: ["docs.example.com"],
          divergent_domains: ["api.example.com"],
        },
      },
      verification: { ok: true },
      verification_ai: { score: 0.9 },
    } as never);

    render(<SearchPage />);

    fireEvent.change(screen.getByTestId("search-run-id-input"), { target: { value: "run-provider" } });
    fireEvent.click(screen.getByRole("button", { name: "Load" }));

    expect(await screen.findByTestId("search-raw-results-card")).toHaveTextContent("exa");
    expect(screen.getByTestId("search-raw-results-card")).toHaveTextContent("tavily");
    expect(screen.getByTestId("search-raw-results-card")).toHaveTextContent("fallback");
    expect(screen.getByTestId("search-raw-results-card")).toHaveTextContent("Title A");
    expect(screen.getByTestId("search-raw-results-card")).toHaveTextContent("Name B");
    expect(screen.getByTestId("search-raw-results-card")).toHaveTextContent("https://example.test/c");
    expect(screen.getByTestId("search-purified-summary-card")).toHaveTextContent("docs.example.com");
    expect(screen.getByTestId("search-purified-summary-card")).toHaveTextContent("api.example.com");
  });

  it("prioritizes news_digest summary before advanced evidence", async () => {
    mockFetchRunSearch.mockResolvedValueOnce({
      raw: { latest: { results: [] } },
      purified: { latest: { summary: {} } },
      news_digest_result: {
        task_template: "news_digest",
        status: "SUCCESS",
        topic: "Seattle AI",
        time_range: "24h",
        generated_at: "2026-03-24T00:00:00Z",
        max_results: 3,
        summary: "已围绕“Seattle AI”汇总 2 条公开来源。",
        sources: [{ title: "Title A", url: "https://example.com/a" }],
        evidence_refs: { raw: "artifacts/search_results.json" },
      },
    } as never);

    render(<SearchPage />);

    fireEvent.change(screen.getByTestId("search-run-id-input"), { target: { value: "run-digest" } });
    fireEvent.click(screen.getByRole("button", { name: "Load" }));

    expect(await screen.findByTestId("search-news-digest-card")).toHaveTextContent('Public digest for "Seattle AI" is ready.');
    expect(screen.getByTestId("search-evidence-bundle-card")).toHaveTextContent("Advanced Evidence");
  });

  it("shows human-readable failure reason when news_digest result is failed", async () => {
    mockFetchRunSearch.mockResolvedValueOnce({
      raw: { latest: { results: [] } },
      purified: { latest: { summary: {} } },
      news_digest_result: {
        task_template: "news_digest",
        status: "FAILED",
        topic: "Seattle AI",
        time_range: "24h",
        generated_at: "2026-03-24T00:00:00Z",
        max_results: 3,
        summary: "“Seattle AI”资讯摘要未能完成。",
        sources: [],
        evidence_refs: { raw: "artifacts/search_results.json" },
        failure_reason_zh: "来源链路失败（provider=grok_web）：upstream timeout",
      },
    } as never);

    render(<SearchPage />);

    fireEvent.change(screen.getByTestId("search-run-id-input"), { target: { value: "run-digest-failed" } });
    fireEvent.click(screen.getByRole("button", { name: "Load" }));

    expect(await screen.findByTestId("search-news-digest-card")).toHaveTextContent('Public digest for "Seattle AI" did not complete.');
    expect(await screen.findByTestId("search-news-digest-card")).toHaveTextContent("Failure reason");
    expect(screen.getByTestId("search-news-digest-card")).toHaveTextContent("Source pipeline failed (provider=grok_web): upstream timeout");
  });

  it("renders topic_brief summary through the same product-first card", async () => {
    mockFetchRunSearch.mockResolvedValueOnce({
      raw: { latest: { results: [] } },
      purified: { latest: { summary: {} } },
      topic_brief_result: {
        task_template: "topic_brief",
        status: "SUCCESS",
        topic: "Seattle AI",
        time_range: "7d",
        generated_at: "2026-03-24T00:00:00Z",
        max_results: 2,
        summary: 'Public read-only topic brief for "Seattle AI" is ready.',
        sources: [{ title: "Title A", url: "https://example.com/a" }],
        evidence_refs: { raw: "artifacts/search_results.json" },
      },
    } as never);

    render(<SearchPage />);

    fireEvent.change(screen.getByTestId("search-run-id-input"), { target: { value: "run-topic-brief" } });
    fireEvent.click(screen.getByRole("button", { name: "Load" }));

    expect(await screen.findByTestId("search-news-digest-card")).toHaveTextContent("topic_brief");
    expect(screen.getByTestId("search-news-digest-card")).toHaveTextContent('Public read-only topic brief for "Seattle AI" is ready.');
  });

  it("renders page_brief summary through the same product-first card", async () => {
    mockFetchRunSearch.mockResolvedValueOnce({
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
    } as never);

    render(<SearchPage />);

    fireEvent.change(screen.getByTestId("search-run-id-input"), { target: { value: "run-page-brief" } });
    fireEvent.click(screen.getByRole("button", { name: "Load" }));

    expect(await screen.findByTestId("search-news-digest-card")).toHaveTextContent("page_brief");
    expect(screen.getByTestId("search-news-digest-card")).toHaveTextContent("Example Domain");
    expect(screen.getByTestId("search-evidence-bundle-card")).toHaveTextContent("browser_0");
  });

  it("shows sanitized promote network error when evidence promotion throws", async () => {
    mockPromoteEvidence.mockRejectedValueOnce(new Error("timeout from upstream"));

    render(<SearchPage />);

    fireEvent.change(screen.getByTestId("search-run-id-input"), { target: { value: "run-promote-fail" } });
    fireEvent.click(screen.getByRole("button", { name: "Load" }));
    expect(await screen.findByTestId("search-status-message")).toHaveTextContent("Loaded run ID: run-promote-fail");

    fireEvent.click(screen.getByRole("button", { name: "Promote to evidence bundle" }));

    await waitFor(() => {
      expect(screen.getByTestId("search-promote-status-message")).toHaveTextContent("Promotion failed: network issue. Try again later.");
    });
  });
});
