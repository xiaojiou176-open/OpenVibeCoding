import { render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { mockCookies } = vi.hoisted(() => ({
  mockCookies: vi.fn(),
}));

vi.mock("next/link", () => ({
  default: ({ href, children, prefetch: _prefetch, ...props }: { href: string; children: ReactNode; prefetch?: boolean }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("../lib/api", () => ({
  fetchRuns: vi.fn(),
  fetchWorkflows: vi.fn(),
}));

vi.mock("next/headers", () => ({
  cookies: mockCookies,
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    refresh: vi.fn(),
  }),
  usePathname: () => "/",
}));

import Home from "../app/page";
import RunsPage from "../app/runs/page";
import { metadata } from "../app/layout";
import DashboardShellChrome from "../components/DashboardShellChrome";
import { fetchRuns, fetchWorkflows } from "../lib/api";
import { getUiCopy } from "@cortexpilot/frontend-shared/uiCopy";

const ORIGINAL_PUBLIC_DOCS_BASE_URL = process.env.NEXT_PUBLIC_CORTEXPILOT_PUBLIC_DOCS_BASE_URL;

describe("dashboard home run-summary clarity", () => {
  const mockFetchRuns = vi.mocked(fetchRuns);
  const mockFetchWorkflows = vi.mocked(fetchWorkflows);

  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchRuns.mockResolvedValue([]);
    mockFetchWorkflows.mockResolvedValue([]);
    mockCookies.mockResolvedValue({
      get: () => undefined,
      toString: () => "",
    });
    if (ORIGINAL_PUBLIC_DOCS_BASE_URL === undefined) delete process.env.NEXT_PUBLIC_CORTEXPILOT_PUBLIC_DOCS_BASE_URL;
    else process.env.NEXT_PUBLIC_CORTEXPILOT_PUBLIC_DOCS_BASE_URL = ORIGINAL_PUBLIC_DOCS_BASE_URL;
  });

  it("renders first-run CTA and onboarding guidance when no runs", async () => {
    render(await Home());

    expect(screen.getByRole("heading", { name: "The open command tower for AI engineering" })).toBeInTheDocument();
    expect(
      screen.getByText(/Stop babysitting AI coding work\./)
    ).toBeInTheDocument();
    expect(screen.getByText("Method layer, not the hero")).toBeInTheDocument();
    expect(screen.getByText("Prompt Engineering")).toBeInTheDocument();
    expect(screen.getByText("Context Engineering")).toBeInTheDocument();
    expect(screen.getByText("Harness Engineering")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Start first task" })).toHaveAttribute("href", "/pm");
    expect(screen.getAllByRole("link", { name: /Workflow Cases/ })[0]).toHaveAttribute("href", "/workflows");

    const firstLoop = screen.getByLabelText("Start your first task in four steps");
    expect(within(firstLoop).getByRole("link", { name: /Describe the request \(goal \+ acceptance\)/ })).toHaveAttribute("href", "/pm");
    expect(within(firstLoop).getByRole("link", { name: /Watch live progress \(confirm it is moving\)/ })).toHaveAttribute("href", "/command-tower");
    expect(within(firstLoop).getByRole("link", { name: /Confirm the Workflow Case/ })).toHaveAttribute("href", "/workflows");
    expect(within(firstLoop).getByRole("link", { name: /Inspect Proof & Replay/ })).toHaveAttribute("href", "/runs");
    expect(screen.getByRole("link", { name: /Approval checkpoint \(only when review is required\)/ })).toHaveAttribute("href", "/god-mode");

    expect(within(firstLoop).getAllByText(/Step\s[1-4]/)).toHaveLength(4);
    expect(within(firstLoop).getByText(/Start with the request, watch Command Tower, confirm the Workflow Case, then inspect Proof & Replay\./)).toBeInTheDocument();
    expect(screen.getByText(/Each entry keeps the task ID, failure clue, and next operator action visible\./)).toBeInTheDocument();
    expect(screen.getByText("Release-proven first run")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /news_digest/i })[0]).toHaveAttribute("href", "/pm?template=news_digest");
    expect(screen.getByText("Proof state: official public baseline")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open proof pack" })).toHaveAttribute(
      "href",
      "https://xiaojiou176-open.github.io/CortexPilot-public/use-cases/"
    );
    expect(screen.getByText("Extended surfaces")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "See first proven workflow" })).toHaveAttribute(
      "href",
      "https://xiaojiou176-open.github.io/CortexPilot-public/use-cases/"
    );
    expect(screen.queryByRole("link", { name: "Open compatibility matrix" })).not.toBeInTheDocument();
    expect(screen.getByText("Compatibility matrix").closest("a")).toHaveAttribute(
      "href",
      "https://xiaojiou176-open.github.io/CortexPilot-public/compatibility/"
    );
    expect(screen.getByText("Integration guide").closest("a")).toHaveAttribute(
      "href",
      "https://xiaojiou176-open.github.io/CortexPilot-public/integrations/"
    );
    expect(screen.getByText("Skills quickstart").closest("a")).toHaveAttribute(
      "href",
      "https://xiaojiou176-open.github.io/CortexPilot-public/skills/"
    );
    expect(screen.getByRole("link", { name: "Open AI + MCP + API surfaces" })).toHaveAttribute(
      "href",
      "https://xiaojiou176-open.github.io/CortexPilot-public/ai-surfaces/"
    );
    expect(screen.getByRole("link", { name: "Open ecosystem map" })).toHaveAttribute(
      "href",
      "https://xiaojiou176-open.github.io/CortexPilot-public/ecosystem/"
    );
    expect(screen.getByRole("link", { name: "Open builder quickstart" })).toHaveAttribute(
      "href",
      "https://xiaojiou176-open.github.io/CortexPilot-public/builders/"
    );
    expect(screen.getByText("Read-only MCP quickstart").closest("a")).toHaveAttribute(
      "href",
      "https://xiaojiou176-open.github.io/CortexPilot-public/mcp/"
    );
    expect(screen.getByText("API and contract quickstart").closest("a")).toHaveAttribute(
      "href",
      "https://xiaojiou176-open.github.io/CortexPilot-public/api/"
    );
    expect(screen.getByText("Live Workflow Case gallery")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Open Workflow Cases" })[0]).toHaveAttribute("href", "/workflows");
    expect(screen.getByRole("link", { name: "See first proven workflow" })).toHaveAttribute(
      "href",
      "https://xiaojiou176-open.github.io/CortexPilot-public/use-cases/"
    );
    expect(screen.getByText("Risk summary")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Governance entry: open runs" })).toHaveAttribute("href", "/runs");
    expect(screen.getByText("Stable: no recent failed runs (0%)")).toHaveClass("badge--success");
    expect(screen.getByRole("progressbar", { name: "Failure share 0/0" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View all runs" })).toHaveAttribute("href", "/runs");
    expect(screen.getByRole("link", { name: "Open Command Tower" })).toHaveAttribute("href", "/command-tower");
    expect(screen.queryByRole("link", { name: "Quick approval" })).not.toBeInTheDocument();
  }, 30000);

  it("keeps the shared home copy contract aligned across locales", () => {
    const en = getUiCopy("en").dashboard.homePhase2;
    const zh = getUiCopy("zh-CN").dashboard.homePhase2;

    expect(en.productSpineCards).toHaveLength(3);
    expect(zh.productSpineCards).toHaveLength(en.productSpineCards.length);
    expect(zh.publicTemplateCards).toHaveLength(en.publicTemplateCards.length);
    expect(zh.publicAdvantageCards).toHaveLength(en.publicAdvantageCards.length);
    expect(zh.integrationCards).toHaveLength(en.integrationCards.length);
    expect(zh.firstTaskGuideSteps).toHaveLength(en.firstTaskGuideSteps.length);
    expect(en.aiSurfacesActionHref).toBe("/ai-surfaces/");
    expect(en.publicTemplatesActionHref).toBe("/use-cases/");
    expect(zh.liveCaseGalleryActionHref).toBe("/workflows");
    expect(en.optionalApprovalStep.href).toBe("/god-mode");
    expect(zh.builderQuickstartCtaHref).toBe("/builders/");
  });

  it("routes public docs CTAs through the configured docs base", async () => {
    process.env.NEXT_PUBLIC_CORTEXPILOT_PUBLIC_DOCS_BASE_URL = "https://docs.example/cortexpilot/";

    render(await Home());

    expect(screen.getByRole("link", { name: "Open AI + MCP + API surfaces" })).toHaveAttribute(
      "href",
      "https://docs.example/cortexpilot/ai-surfaces/"
    );
    expect(screen.getByRole("link", { name: "Open ecosystem map" })).toHaveAttribute(
      "href",
      "https://docs.example/cortexpilot/ecosystem/"
    );
    expect(screen.getByRole("link", { name: "Open builder quickstart" })).toHaveAttribute(
      "href",
      "https://docs.example/cortexpilot/builders/"
    );
    expect(screen.getByRole("link", { name: "See first proven workflow" })).toHaveAttribute(
      "href",
      "https://docs.example/cortexpilot/use-cases/"
    );
    expect(screen.getByText("Compatibility matrix").closest("a")).toHaveAttribute(
      "href",
      "https://docs.example/cortexpilot/compatibility/"
    );
    expect(screen.getByText("Integration guide").closest("a")).toHaveAttribute(
      "href",
      "https://docs.example/cortexpilot/integrations/"
    );
    expect(screen.getByText("Skills quickstart").closest("a")).toHaveAttribute(
      "href",
      "https://docs.example/cortexpilot/skills/"
    );
    expect(screen.getByText("Read-only MCP quickstart").closest("a")).toHaveAttribute(
      "href",
      "https://docs.example/cortexpilot/mcp/"
    );
    expect(screen.getByText("API and contract quickstart").closest("a")).toHaveAttribute(
      "href",
      "https://docs.example/cortexpilot/api/"
    );
    expect(screen.getByRole("link", { name: "Open ecosystem map" })).toHaveAttribute(
      "href",
      "https://docs.example/cortexpilot/ecosystem/"
    );
  });

  it("switches CTA wording once run history exists", async () => {
    mockFetchRuns.mockResolvedValueOnce([
      {
        run_id: "run-0",
        task_id: "task-0",
        status: "SUCCESS",
      },
    ] as never[]);

    render(await Home());
    expect(screen.getByRole("link", { name: "Start new task" })).toHaveAttribute("href", "/pm");
    expect(screen.queryByRole("link", { name: "Start first task" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Start your first task in four steps")).not.toBeInTheDocument();
  });

  it("renders zh-CN home copy when the locale cookie requests it", async () => {
    mockCookies.mockResolvedValue({
      get: (name: string) => (name === "cortexpilot.ui.locale" ? { value: "zh-CN" } : undefined),
      toString: () => "cortexpilot.ui.locale=zh-CN",
    });

    render(await Home());

    expect(screen.getByRole("heading", { name: "面向 AI 工程的开放指挥塔" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "启动首个任务" })).toHaveAttribute("href", "/pm");
    expect(screen.getByText("延伸入口")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "打开 AI + MCP + API 页面" })).toHaveAttribute(
      "href",
      "https://xiaojiou176-open.github.io/CortexPilot-public/ai-surfaces/"
    );
    expect(screen.getByRole("link", { name: "打开证明包" })).toHaveAttribute(
      "href",
      "https://xiaojiou176-open.github.io/CortexPilot-public/use-cases/"
    );
    expect(screen.getByRole("link", { name: "打开 builder 快速入口" })).toHaveAttribute(
      "href",
      "https://xiaojiou176-open.github.io/CortexPilot-public/builders/"
    );
    expect(screen.getByRole("link", { name: "查看首个已证明工作流" })).toHaveAttribute(
      "href",
      "https://xiaojiou176-open.github.io/CortexPilot-public/use-cases/"
    );
    expect(screen.queryByRole("link", { name: "打开 compatibility matrix" })).not.toBeInTheDocument();
    expect(screen.getByText("Compatibility matrix").closest("a")).toHaveAttribute(
      "href",
      "https://xiaojiou176-open.github.io/CortexPilot-public/compatibility/"
    );
    expect(screen.getByText("Integration guide").closest("a")).toHaveAttribute(
      "href",
      "https://xiaojiou176-open.github.io/CortexPilot-public/integrations/"
    );
    expect(screen.getAllByText("Read-only MCP quickstart").length).toBeGreaterThan(0);
    expect(screen.getAllByText("API and contract quickstart").length).toBeGreaterThan(0);
    expect(screen.getByText("显示四步首跑流程")).toBeInTheDocument();
  });

  it("maps latest failure category to semantic label and provides governance link", async () => {
    mockFetchRuns.mockResolvedValueOnce([
      {
        run_id: "run-1",
        task_id: "task-1",
        status: "FAILED",
        failure_class: "manual",
        action_hint_zh: "完成人工确认后继续",
      },
    ] as never[]);

    render(await Home());
    expect(screen.getByText("Risk summary")).toBeInTheDocument();
    expect(screen.getByText("Failure category: Manual review required")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Governance entry: inspect failure events" })).toHaveAttribute("href", "/events");
    expect(screen.queryByText(/^manual$/i)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Run run-1" })).toHaveAttribute("href", "/runs/run-1");
    expect(screen.getByText(/Task: task-1 · Manual review required/)).toBeInTheDocument();
    const handleFailureLink = screen.getByRole("link", { name: "Handle failure run-1" });
    expect(handleFailureLink).toHaveAttribute("href", "/events?run_id=run-1");
    expect(handleFailureLink.closest("span")).toHaveClass("cell-danger");
  });

  it("shows high-risk distribution semantics when failure rate is high", async () => {
    mockFetchRuns.mockResolvedValueOnce([
      { run_id: "run-1", task_id: "task-1", status: "FAILED" },
      { run_id: "run-2", task_id: "task-2", status: "ERROR" },
      { run_id: "run-3", task_id: "task-3", status: "FAILURE" },
      { run_id: "run-4", task_id: "task-4", status: "SUCCESS" },
    ] as never[]);

    render(await Home());
    expect(screen.getByText("Success 1 / Running 0 / Failed 3")).toHaveClass("metric-value--danger");
    expect(screen.getByText("High risk: failure rate is elevated, investigate first (75%)")).toHaveClass("badge--failed");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Investigate high-risk failures" })).toHaveAttribute("href", "/events");
    expect(screen.getAllByRole("link", { name: /Handle failure run-/ })).toHaveLength(3);
    expect(screen.getByRole("link", { name: "Handle failure run-1" })).toHaveAttribute("href", "/events?run_id=run-1");
    const progressBar = screen.getByRole("progressbar", { name: "Failure share 3/4" });
    expect(progressBar).toHaveAttribute("max", "4");
    expect(progressBar).toHaveAttribute("value", "3");
  });

  it("renders long run id with suffix-plus-task format for faster distinction", async () => {
    mockFetchRuns.mockResolvedValueOnce([
      {
        run_id: "run-20260221-aaaaaaaa11111111",
        task_id: "task-20260221-abcde12345",
        status: "SUCCESS",
      },
    ] as never[]);

    render(await Home());
    const runLink = screen.getByRole("link", { name: "Run run-20260221-aaaaaaaa11111111" });
    expect(runLink).toHaveTextContent("aa11111111 · abcde12345");
    expect(runLink).toHaveAttribute("title", "run-20260221-aaaaaaaa11111111");
  });

  it("falls back to raw timestamps and placeholder ids when run metadata is incomplete", async () => {
    mockFetchRuns.mockResolvedValueOnce([
      {
        run_id: "",
        task_id: "",
        status: "RUNNING",
        created_at: "not-a-date",
      },
    ] as never[]);

    render(await Home());

    expect(screen.getAllByText("not-a-date")).toHaveLength(2);
    expect(screen.getByText("Task: - · Unclassified")).toBeInTheDocument();
    expect(screen.getByText("-", { selector: "span.mono.muted" })).toBeInTheDocument();
  });

  it("renders long run id head-tail format when task id is absent", async () => {
    mockFetchRuns.mockResolvedValueOnce([
      {
        run_id: "run-20260221-aaaaaaaa11111111",
        task_id: "",
        status: "SUCCESS",
      },
    ] as never[]);

    render(await Home());

    const runLink = screen.getByRole("link", { name: "Run run-20260221-aaaaaaaa11111111" });
    expect(runLink).toHaveTextContent("run-2026…aa11111111");
    expect(screen.getByText("Task: - · Unclassified")).toBeInTheDocument();
  });

  it("formats valid timestamps with en-US local display", async () => {
    const createdAt = "2026-02-21T08:09:00Z";
    mockFetchRuns.mockResolvedValueOnce([
      {
        run_id: "run-timestamp-1",
        task_id: "task-timestamp-1",
        status: "SUCCESS",
        created_at: createdAt,
      },
    ] as never[]);

    render(await Home());

    expect(screen.getAllByText(new Date(createdAt).toLocaleString("en-US", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    })).length).toBeGreaterThan(0);
  });

  it("renders runs governance entry and status-filter links for failed-focused triage", async () => {
    mockFetchRuns.mockResolvedValueOnce([
      { run_id: "run-fail-1", task_id: "task-fail-1", status: "FAILED" },
      { run_id: "run-running-1", task_id: "task-running-1", status: "RUNNING" },
      { run_id: "run-success-1", task_id: "task-success-1", status: "SUCCESS" },
    ] as never[]);

    render(await RunsPage({ searchParams: Promise.resolve({}) }));

    expect(screen.getByRole("link", { name: "Open failed proof lane" })).toHaveAttribute("href", "/runs?status=FAILED");
    expect(screen.getByRole("link", { name: "View failed events" })).toHaveAttribute("href", "/events");
    expect(screen.getByRole("link", { name: "All runs" })).toHaveAttribute("href", "/runs");
    expect(screen.getByRole("link", { name: "Failed" })).toHaveAttribute("href", "/runs?status=FAILED");
    expect(screen.getByRole("link", { name: "Running" })).toHaveAttribute("href", "/runs?status=RUNNING");
    expect(screen.getByRole("link", { name: "Succeeded" })).toHaveAttribute("href", "/runs?status=SUCCESS");
  });

  it("falls back governance CTA to PM creation when there is no failure", async () => {
    mockFetchRuns.mockResolvedValueOnce([
      { run_id: "run-success-2", task_id: "task-success-2", status: "SUCCESS" },
    ] as never[]);

    render(await RunsPage({ searchParams: Promise.resolve({ status: "SUCCESS" }) }));

    expect(screen.getByRole("link", { name: "Start a new task" })).toHaveAttribute("href", "/pm");
    expect(screen.queryByRole("link", { name: "View failed events" })).not.toBeInTheDocument();
  });

  it("shows degraded risk summary when runs data is unavailable", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    mockFetchRuns.mockRejectedValueOnce(new Error("runs down"));

    render(await Home());

    expect(screen.getByText("Data degraded")).toHaveClass("metric-value--warning");
    expect(screen.getByText("Latest status: Data degraded")).toBeInTheDocument();
    expect(screen.getByText("Failure category: unavailable while data is degraded")).toHaveClass("cell-warning");
    expect(screen.getByRole("link", { name: "Governance entry: inspect data sources and the run list" })).toHaveAttribute("href", "/runs");
    expect(screen.getByText("Data degraded: the run list is temporarily unavailable (0%)")).toHaveClass("badge--warning");
    expect(screen.getByText("Total: -")).toBeInTheDocument();

    consoleSpy.mockRestore();
  });

  it("renders the public shell with English-first layout metadata and chrome copy", () => {
    expect(metadata.title).toBe("OpenVibeCoding | The open command tower for AI engineering");
    expect(metadata.description).toContain("Stop babysitting AI coding work.");

    render(
      <DashboardShellChrome>
        <div>content</div>
      </DashboardShellChrome>
    );

    expect(screen.getByRole("link", { name: "Skip to dashboard content" })).toHaveAttribute("href", "#dashboard-content");
    expect(screen.getAllByLabelText("Dashboard navigation").length).toBeGreaterThan(0);
    expect(screen.getByText("OpenVibeCoding")).toBeInTheDocument();
    expect(screen.getByText("plan / delegate / track / resume / prove")).toBeInTheDocument();
    expect(screen.getByText("OpenVibeCoding command tower")).toBeInTheDocument();
    expect(screen.getByLabelText("Platform status overview")).toBeInTheDocument();
    expect(screen.getByText("Governance view")).toBeInTheDocument();
    expect(screen.getByText("Live verification required")).toBeInTheDocument();
    expect(screen.getByText("Page-level status")).toBeInTheDocument();
  });
});
