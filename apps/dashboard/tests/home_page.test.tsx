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
import { getUiCopy } from "@openvibecoding/frontend-shared/uiCopy";

const ORIGINAL_PUBLIC_DOCS_BASE_URL = process.env.NEXT_PUBLIC_OPENVIBECODING_PUBLIC_DOCS_BASE_URL;

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
    if (ORIGINAL_PUBLIC_DOCS_BASE_URL === undefined) delete process.env.NEXT_PUBLIC_OPENVIBECODING_PUBLIC_DOCS_BASE_URL;
    else process.env.NEXT_PUBLIC_OPENVIBECODING_PUBLIC_DOCS_BASE_URL = ORIGINAL_PUBLIC_DOCS_BASE_URL;
  });

  it("renders first-run CTA and onboarding guidance when no runs", async () => {
    render(await Home());
    const secondLayerGuides = screen.getByTestId("home-second-layer-guides");
    secondLayerGuides.setAttribute("open", "");

    expect(screen.getByRole("heading", { name: "The open command tower for AI engineering" })).toBeInTheDocument();
    expect(
      screen.getByText(/Stop babysitting AI coding work\./)
    ).toBeInTheDocument();
    expect(screen.getByText("Second-layer guides, not the first impression")).toBeInTheDocument();
    expect(screen.getByText("Open second-layer guides")).toBeInTheDocument();
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
    expect(screen.getByText("What unlocks after the first task lands")).toBeInTheDocument();
    expect(screen.getByText("Release-proven first run")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /news_digest/i })[0]).toHaveAttribute("href", "/pm?template=news_digest");
    expect(screen.getByText(/official public baseline/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open proof pack" })).toHaveAttribute(
      "href",
      "https://xiaojiou176-open.github.io/OpenVibeCoding/use-cases/"
    );
    expect(screen.getByText("Extended surfaces")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "See first proven workflow" })[0]).toHaveAttribute(
      "href",
      "https://xiaojiou176-open.github.io/OpenVibeCoding/use-cases/"
    );
    expect(screen.queryByRole("link", { name: "Open compatibility matrix" })).not.toBeInTheDocument();
    expect(screen.getByText("Compatibility matrix").closest("a")).toHaveAttribute(
      "href",
      "https://xiaojiou176-open.github.io/OpenVibeCoding/compatibility/"
    );
    expect(screen.getByText("Integration guide").closest("a")).toHaveAttribute(
      "href",
      "https://xiaojiou176-open.github.io/OpenVibeCoding/integrations/"
    );
    expect(screen.getByText("Skills quickstart").closest("a")).toHaveAttribute(
      "href",
      "https://xiaojiou176-open.github.io/OpenVibeCoding/skills/"
    );
    expect(screen.getByRole("link", { name: "Open AI + MCP + API surfaces" })).toHaveAttribute(
      "href",
      "https://xiaojiou176-open.github.io/OpenVibeCoding/ai-surfaces/"
    );
    expect(screen.getByRole("link", { name: "Open ecosystem map" })).toHaveAttribute(
      "href",
      "https://xiaojiou176-open.github.io/OpenVibeCoding/ecosystem/"
    );
    expect(screen.getByRole("link", { name: "Open builder quickstart" })).toHaveAttribute(
      "href",
      "https://xiaojiou176-open.github.io/OpenVibeCoding/builders/"
    );
    expect(screen.getByText("Read-only MCP quickstart").closest("a")).toHaveAttribute(
      "href",
      "https://xiaojiou176-open.github.io/OpenVibeCoding/mcp/"
    );
    expect(screen.getByText("API and contract quickstart").closest("a")).toHaveAttribute(
      "href",
      "https://xiaojiou176-open.github.io/OpenVibeCoding/api/"
    );
    expect(screen.getByText("Live Workflow Case gallery")).toBeInTheDocument();
    expect(screen.getByText("Latest results and runs")).toBeInTheDocument();
    expect(screen.getByText("Governance desks and release controls")).toBeInTheDocument();
    expect(screen.getByText("Live Workflow Case gallery").closest("a")).toHaveAttribute("href", "/workflows");
    expect(screen.getAllByRole("link", { name: "See first proven workflow" })[0]).toHaveAttribute(
      "href",
      "https://xiaojiou176-open.github.io/OpenVibeCoding/use-cases/"
    );
    expect(screen.getByText("Live command tower").closest("a")).toHaveAttribute("href", "/command-tower");
    expect(screen.queryByRole("link", { name: "Quick approval" })).not.toBeInTheDocument();
  }, 30000);

  it("keeps the shared home copy contract aligned across locales", () => {
    const en = getUiCopy("en").dashboard.homePhase2;
    const zh = getUiCopy("zh-CN").dashboard.homePhase2;
    const enPageBrief = en.publicTemplateCards.find((card) => card.title === "page_brief");
    const zhPageBrief = zh.publicTemplateCards.find((card) => card.title === "page_brief");

    expect(en.productSpineCards).toHaveLength(3);
    expect(zh.productSpineCards).toHaveLength(en.productSpineCards.length);
    expect(zh.publicTemplateCards).toHaveLength(en.publicTemplateCards.length);
    expect(zh.publicAdvantageCards).toHaveLength(en.publicAdvantageCards.length);
    expect(zh.integrationCards).toHaveLength(en.integrationCards.length);
    expect(zh.firstTaskGuideSteps).toHaveLength(en.firstTaskGuideSteps.length);
    expect(en.publicTemplatesDescription).toContain("`page_brief` now has a tracked browser-backed proof bundle");
    expect(zh.publicTemplatesDescription).toContain("`page_brief` 现在已经有已追踪的浏览器证明包");
    expect(enPageBrief?.badge).toBe("Tracked browser-backed bundle");
    expect(enPageBrief?.proof).toBe("Proof state: tracked browser-backed public proof bundle");
    expect(zhPageBrief?.badge).toBe("已追踪浏览器证明包");
    expect(zhPageBrief?.proof).toBe("Proof 状态：已追踪的浏览器公开证明包");
    expect(en.aiSurfacesActionHref).toBe("/ai-surfaces/");
    expect(en.publicTemplatesActionHref).toBe("/use-cases/");
    expect(zh.liveCaseGalleryActionHref).toBe("/workflows");
    expect(en.optionalApprovalStep.href).toBe("/god-mode");
    expect(zh.builderQuickstartCtaHref).toBe("/builders/");
  });

  it("routes public docs CTAs through the configured docs base", async () => {
    process.env.NEXT_PUBLIC_OPENVIBECODING_PUBLIC_DOCS_BASE_URL = "https://docs.example/openvibecoding/";

    render(await Home());
    const secondLayerGuides = screen.getByTestId("home-second-layer-guides");
    secondLayerGuides.setAttribute("open", "");

    expect(screen.getByRole("link", { name: "Open AI + MCP + API surfaces" })).toHaveAttribute(
      "href",
      "https://docs.example/openvibecoding/ai-surfaces/"
    );
    expect(screen.getByRole("link", { name: "Open ecosystem map" })).toHaveAttribute(
      "href",
      "https://docs.example/openvibecoding/ecosystem/"
    );
    expect(screen.getByRole("link", { name: "Open builder quickstart" })).toHaveAttribute(
      "href",
      "https://docs.example/openvibecoding/builders/"
    );
    expect(screen.getAllByRole("link", { name: "See first proven workflow" })[0]).toHaveAttribute(
      "href",
      "https://docs.example/openvibecoding/use-cases/"
    );
    expect(screen.getByText("Compatibility matrix").closest("a")).toHaveAttribute(
      "href",
      "https://docs.example/openvibecoding/compatibility/"
    );
    expect(screen.getByText("Integration guide").closest("a")).toHaveAttribute(
      "href",
      "https://docs.example/openvibecoding/integrations/"
    );
    expect(screen.getByText("Skills quickstart").closest("a")).toHaveAttribute(
      "href",
      "https://docs.example/openvibecoding/skills/"
    );
    expect(screen.getByText("Read-only MCP quickstart").closest("a")).toHaveAttribute(
      "href",
      "https://docs.example/openvibecoding/mcp/"
    );
    expect(screen.getByText("API and contract quickstart").closest("a")).toHaveAttribute(
      "href",
      "https://docs.example/openvibecoding/api/"
    );
    expect(screen.getByRole("link", { name: "Open ecosystem map" })).toHaveAttribute(
      "href",
      "https://docs.example/openvibecoding/ecosystem/"
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
      get: (name: string) => (name === "openvibecoding.ui.locale" ? { value: "zh-CN" } : undefined),
      toString: () => "openvibecoding.ui.locale=zh-CN",
    });

    render(await Home());
    const secondLayerGuides = screen.getByTestId("home-second-layer-guides");
    secondLayerGuides.setAttribute("open", "");

    expect(screen.getByRole("heading", { name: "AI 工程开放指挥塔" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "启动首个任务" })).toHaveAttribute("href", "/pm");
    expect(screen.getByText("延伸入口")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "打开 AI + MCP + API 页面" })).toHaveAttribute(
      "href",
      "https://xiaojiou176-open.github.io/OpenVibeCoding/ai-surfaces/"
    );
    expect(screen.getByRole("link", { name: "打开证明包" })).toHaveAttribute(
      "href",
      "https://xiaojiou176-open.github.io/OpenVibeCoding/use-cases/"
    );
    expect(screen.getByRole("link", { name: "打开 Builder 快速入口" })).toHaveAttribute(
      "href",
      "https://xiaojiou176-open.github.io/OpenVibeCoding/builders/"
    );
    expect(screen.getAllByRole("link", { name: "查看首个已证明工作流" })[0]).toHaveAttribute(
      "href",
      "https://xiaojiou176-open.github.io/OpenVibeCoding/use-cases/"
    );
    expect(screen.queryByRole("link", { name: "打开 compatibility matrix" })).not.toBeInTheDocument();
    expect(screen.getByText("兼容性矩阵").closest("a")).toHaveAttribute(
      "href",
      "https://xiaojiou176-open.github.io/OpenVibeCoding/compatibility/"
    );
    expect(screen.getByText("集成指南").closest("a")).toHaveAttribute(
      "href",
      "https://xiaojiou176-open.github.io/OpenVibeCoding/integrations/"
    );
    expect(screen.getAllByText("只读 MCP 快速入口").length).toBeGreaterThan(0);
    expect(screen.getAllByText("API 与契约快速入口").length).toBeGreaterThan(0);
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
    expect(screen.getByText("Where to go first")).toBeInTheDocument();
    expect(screen.getByText("Workflow plus Proof is the truth path")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Investigate high-risk failures" })).toHaveAttribute("href", "/events");
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
    expect(screen.getByText("Start in Command Tower or Events")).toBeInTheDocument();
    expect(screen.getByText("Workflow plus Proof is the truth path")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Investigate high-risk failures" })).toHaveAttribute("href", "/events");
    expect(screen.getAllByRole("link", { name: /Handle failure run-/ })).toHaveLength(3);
    expect(screen.getByRole("link", { name: "Handle failure run-1" })).toHaveAttribute("href", "/events?run_id=run-1");
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

    expect(screen.getAllByText("not-a-date")).toHaveLength(1);
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

  it("falls back to Unknown status label and workflow summary placeholders", async () => {
    mockFetchRuns.mockResolvedValueOnce([
      {
        run_id: "run-unknown",
        task_id: "task-unknown",
        status: "",
      },
    ] as never[]);
    mockFetchWorkflows.mockResolvedValueOnce([
      {
        workflow_id: "",
        status: "",
        summary: "",
        objective: "",
        verdict: "",
        owner_pm: "",
        project_key: "",
        run_ids: ["run-a", "run-b"],
      },
    ] as never[]);

    render(await Home());
    expect(screen.getAllByText("Unknown").length).toBeGreaterThan(0);
    expect(screen.getByText("No workflow summary is attached yet.")).toBeInTheDocument();
    expect(screen.getByText("Run mappings: 2")).toBeInTheDocument();
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

  it("renders zh-CN high-failure triage and first-screen limit for array status filters", async () => {
    mockCookies.mockResolvedValueOnce({
      get: (name: string) => (name === "openvibecoding.ui.locale" ? { value: "zh-CN" } : undefined),
      toString: () => "openvibecoding.ui.locale=zh-CN",
    });
    const zhRunsCopy = getUiCopy("zh-CN").dashboard.runsPage;
    mockFetchRuns.mockResolvedValueOnce([
      { run_id: "run-failed-1", task_id: "task-failed-1", status: "FAILED", outcome_type: "blocked", action_hint_zh: "先排查" },
      { run_id: "run-failed-2", task_id: "task-failed-2", status: "FAILED", outcome_type: "blocked", action_hint_zh: "先回放" },
      { run_id: "run-failed-3", task_id: "task-failed-3", status: "FAILED", outcome_type: "blocked", action_hint_zh: "先止血" },
      { run_id: "run-failed-4", task_id: "task-failed-4", status: "FAILED", outcome_type: "blocked", action_hint_zh: "先核对" },
      { run_id: "run-failed-5", task_id: "task-failed-5", status: "FAILED", outcome_type: "blocked", action_hint_zh: "先补证据" },
      { run_id: "run-failed-6", task_id: "task-failed-6", status: "FAILED", outcome_type: "blocked", action_hint_zh: "先复核" },
      { run_id: "run-failed-7", task_id: "task-failed-7", status: "FAILED", outcome_type: "blocked", action_hint_zh: "先确认" },
      { run_id: "run-failed-8", task_id: "task-failed-8", status: "FAILED", outcome_type: "blocked", action_hint_zh: "先检查" },
      { run_id: "run-success-zh", task_id: "task-success-zh", status: "SUCCESS", outcome_type: "proof_ready", action_hint_zh: "可分享" },
    ] as never[]);

    render(await RunsPage({ searchParams: Promise.resolve({ status: ["FAILED"] }) }));

    expect(screen.getByRole("heading", { name: zhRunsCopy.title })).toBeInTheDocument();
    expect(screen.getByText(zhRunsCopy.failureHeadline(8))).toBeInTheDocument();
    expect(screen.getByRole("link", { name: zhRunsCopy.operatorPrimaryActionFailed })).toHaveAttribute("href", "/runs?status=FAILED");
    expect(screen.getByRole("link", { name: zhRunsCopy.operatorSecondaryAction })).toHaveAttribute("href", "/events");
    expect(screen.getByRole("status")).toHaveTextContent(zhRunsCopy.firstScreenLimit(8));
  });

  it("renders degraded read-only snapshot guidance when runs fetch falls back with a warning", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const enRunsCopy = getUiCopy("en").dashboard.runsPage;
    mockFetchRuns.mockRejectedValueOnce(new Error("runs api unavailable"));

    render(await RunsPage({ searchParams: Promise.resolve({}) }));

    expect(screen.getByText(enRunsCopy.warningTitle)).toBeInTheDocument();
    expect(screen.getByText(enRunsCopy.warningNextStep)).toBeInTheDocument();
    expect(screen.getByText("Verify the current read-only snapshot first")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Inspect visible runs" })).toHaveAttribute("href", "/runs");
    expect(screen.queryByRole("link", { name: enRunsCopy.operatorSecondaryAction })).not.toBeInTheDocument();

    consoleSpy.mockRestore();
  });

  it("shows degraded risk summary when runs data is unavailable", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    mockFetchRuns.mockRejectedValueOnce(new Error("runs down"));

    render(await Home());

    expect(screen.getByText("The first run has not started yet")).toBeInTheDocument();
    expect(screen.getByText("The current job is to establish the first durable loop, not to chase noise.")).toBeInTheDocument();
    expect(screen.queryByText("Degraded inputs")).not.toBeInTheDocument();
    expect(screen.queryByText("Current posture: Degraded inputs")).not.toBeInTheDocument();
    expect(screen.queryByText("Primary risk: run list unavailable")).not.toBeInTheDocument();

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
    expect(screen.getByRole("link", { name: "OpenVibeCoding" })).toBeInTheDocument();
    expect(screen.getByText("plan / delegate / track / resume / prove")).toBeInTheDocument();
    expect(screen.getByText("OpenVibeCoding command tower")).toBeInTheDocument();
    expect(screen.getByLabelText("Platform status overview")).toBeInTheDocument();
    expect(screen.queryByText("Operator shell")).not.toBeInTheDocument();
    expect(screen.queryByText("Live read-back")).not.toBeInTheDocument();
    expect(screen.queryByText("Page contract")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Switch to Chinese" })).toBeInTheDocument();
  });
});
