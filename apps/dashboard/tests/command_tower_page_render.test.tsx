import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { mockCookies } = vi.hoisted(() => ({
  mockCookies: vi.fn(),
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("next/headers", () => ({
  cookies: mockCookies,
}));

vi.mock("../app/command-tower/CommandTowerHomeLiveClient", () => ({
  default: ({ initialOverview, initialSessions }: { initialOverview: { total_sessions?: number }; initialSessions: unknown[] }) => (
    <div data-testid="ct-live-client">
      {`overview:${initialOverview.total_sessions ?? 0} sessions:${initialSessions.length}`}
    </div>
  ),
}));

vi.mock("../components/control-plane/ControlPlaneStatusCallout", () => ({
  default: ({
    title,
    summary,
    nextAction,
    actions,
  }: {
    title: string;
    summary: string;
    nextAction: string;
    actions: Array<{ href: string; label: string }>;
  }) => (
    <section data-testid="ct-callout">
      <h2>{title}</h2>
      <p>{summary}</p>
      <p>{nextAction}</p>
      {actions.map((action) => (
        <a key={action.href} href={action.href}>
          {action.label}
        </a>
      ))}
    </section>
  ),
}));

vi.mock("../lib/api", () => ({
  fetchCommandTowerOverview: vi.fn(),
  fetchPmSessions: vi.fn(),
}));

import {
  CommandTowerHomeSection,
  CommandTowerHomeSectionFallback,
  CommandTowerPageIntro,
  default as CommandTowerPage,
} from "../app/command-tower/page";
import CommandTowerLoading from "../app/command-tower/loading";
import { fetchCommandTowerOverview, fetchPmSessions } from "../lib/api";

describe("command tower page render", () => {
  const mockFetchCommandTowerOverview = vi.mocked(fetchCommandTowerOverview);
  const mockFetchPmSessions = vi.mocked(fetchPmSessions);

  beforeEach(() => {
    vi.clearAllMocks();
    mockCookies.mockResolvedValue({
      get: () => undefined,
      toString: () => "",
    });
    mockFetchCommandTowerOverview.mockResolvedValue({
      generated_at: "2026-04-15T00:00:00Z",
      total_sessions: 1,
      active_sessions: 1,
      failed_sessions: 0,
      blocked_sessions: 0,
      failed_ratio: 0,
      blocked_ratio: 0,
      failure_trend_30m: 0,
      top_blockers: [],
    } as never);
    mockFetchPmSessions.mockResolvedValue([
      {
        pm_session_id: "pm-1",
        status: "active",
        run_count: 1,
        running_runs: 1,
        failed_runs: 0,
        success_runs: 0,
        blocked_runs: 0,
      },
    ] as never);
  });

  it("renders the live client when command tower data is available", async () => {
    render(<CommandTowerPageIntro locale="en" />);
    render(await CommandTowerHomeSection({ locale: "en" }));

    expect(screen.getByRole("heading", { name: "Command Tower" })).toBeInTheDocument();
    expect(screen.getByText("Scan the live session board first")).toBeInTheDocument();
    expect(screen.getByTestId("ct-live-client")).toHaveTextContent("overview:1 sessions:1");
    expect(screen.queryByTestId("ct-callout")).toBeNull();
  });

  it("renders the full page live path when command tower data is available", async () => {
    render(await CommandTowerPage());

    expect(screen.getByRole("heading", { name: "Command Tower" })).toBeInTheDocument();
    expect(screen.getByText("L0 cockpit / live control desk")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Loading Command Tower live overview...");
    expect(screen.queryByTestId("ct-callout")).toBeNull();
  });

  it("renders unavailable callout when both overview and session data fail", async () => {
    mockFetchCommandTowerOverview.mockRejectedValueOnce(new Error("overview down"));
    mockFetchPmSessions.mockRejectedValueOnce(new Error("sessions down"));

    render(await CommandTowerHomeSection({ locale: "en" }));

    expect(screen.getByTestId("ct-callout")).toBeInTheDocument();
    expect(screen.getByText("Command Tower live overview is unavailable")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Reload Command Tower" })).toHaveAttribute("href", "/command-tower");
    expect(screen.getByRole("link", { name: "View runs" })).toHaveAttribute("href", "/runs");
    expect(screen.getByRole("link", { name: "Start from PM" })).toHaveAttribute("href", "/pm");
  });

  it("renders zh-CN copy, fallback, and degraded summary when overview fails but session data exists", async () => {
    mockFetchCommandTowerOverview.mockRejectedValueOnce(new Error("总览失败"));
    mockFetchPmSessions.mockResolvedValueOnce([
      {
        pm_session_id: "pm-zh",
        status: "active",
        run_count: 1,
        running_runs: 1,
        failed_runs: 0,
        success_runs: 0,
        blocked_runs: 0,
      },
    ] as never);

    render(<CommandTowerPageIntro locale="zh-CN" />);
    render(<CommandTowerHomeSectionFallback locale="zh-CN" />);
    render(await CommandTowerHomeSection({ locale: "zh-CN" }));

    expect(screen.getByRole("heading", { name: "指挥塔" })).toBeInTheDocument();
    expect(screen.getByText("L0 驾驶舱 / 实时控制桌")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("正在加载指挥塔实时总览...");
    expect(screen.queryByTestId("ct-callout")).toBeNull();
    expect(screen.getByTestId("ct-live-client")).toHaveTextContent("overview:0 sessions:1");
    expect(screen.getAllByRole("region", { name: "指挥塔实时总览" })).toHaveLength(2);
  });

  it("renders zh-CN aria labels for both live and fallback command tower sections", async () => {
    render(await CommandTowerHomeSection({ locale: "zh-CN" }));
    expect(screen.getByRole("region", { name: "指挥塔实时总览" })).toBeInTheDocument();

    render(<CommandTowerHomeSectionFallback locale="zh-CN" />);
    expect(screen.getAllByRole("region", { name: "指挥塔实时总览" })).toHaveLength(2);
  });

  it("renders zh-CN route loading copy when the locale cookie requests it", async () => {
    mockCookies.mockResolvedValue({
      get: (name: string) => (name === "openvibecoding.ui.locale" ? { value: "zh-CN" } : undefined),
      toString: () => "openvibecoding.ui.locale=zh-CN",
    });

    render(await CommandTowerLoading());

    expect(screen.getByRole("heading", { name: "正在加载指挥塔" })).toBeInTheDocument();
    expect(screen.getByText("请稍候，系统正在聚合会话总览、告警和实时状态。")).toBeInTheDocument();
    expect(screen.getByLabelText("指挥塔加载状态")).toBeInTheDocument();
    expect(screen.queryByText("Loading Command Tower")).not.toBeInTheDocument();
  });

  it("switches the page intro into partial-truth mode when warning data still has live context", async () => {
    mockFetchCommandTowerOverview.mockRejectedValueOnce(new Error("overview down"));
    mockFetchPmSessions.mockResolvedValueOnce([
      {
        pm_session_id: "pm-partial",
        status: "active",
        run_count: 1,
        running_runs: 1,
        failed_runs: 0,
        success_runs: 0,
        blocked_runs: 0,
      },
    ] as never);

    render(await CommandTowerPage());

    expect(screen.getByText("Partial truth / live surface degraded")).toBeInTheDocument();
    expect(screen.getByText("Command Tower is running with partial truth")).toBeInTheDocument();
    expect(screen.getByText("Partial context")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Command Tower overview is temporarily unavailable. The page is showing a partial snapshot, so verify runs or Workflow Cases directly before you act."
      )
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Reload Command Tower" })).toHaveAttribute("href", "/command-tower");
    expect(screen.getByRole("link", { name: "View runs" })).toHaveAttribute("href", "/runs");
    expect(screen.queryByTestId("ct-callout")).toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent("Loading Command Tower live overview...");
  });

  it("switches the page intro into zh-CN partial-truth mode when warning data still has live context", async () => {
    mockCookies.mockResolvedValue({
      get: (name: string) => (name === "openvibecoding.ui.locale" ? { value: "zh-CN" } : undefined),
      toString: () => "openvibecoding.ui.locale=zh-CN",
    });
    mockFetchCommandTowerOverview.mockRejectedValueOnce(new Error("总览失败"));
    mockFetchPmSessions.mockResolvedValueOnce([
      {
        pm_session_id: "pm-partial-zh",
        status: "active",
        run_count: 1,
        running_runs: 1,
        failed_runs: 0,
        success_runs: 0,
        blocked_runs: 0,
      },
    ] as never);

    render(await CommandTowerPage());

    expect(screen.getByText("部分真相 / 实时主面当前降级")).toBeInTheDocument();
    expect(screen.getByText("指挥塔当前只提供部分真相")).toBeInTheDocument();
    expect(screen.getByText("上下文不完整")).toBeInTheDocument();
    expect(screen.getByText("可见面板只算部分快照")).toBeInTheDocument();
    expect(
      screen.getByText("指挥塔总览暂时不可用。当前页面只显示部分快照，继续操作前请直接核对运行记录或工作流案例。")
    ).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("正在加载指挥塔实时总览...");
    expect(screen.getByRole("link", { name: "重载指挥塔" })).toHaveAttribute("href", "/command-tower");
    expect(screen.getByRole("link", { name: "查看运行记录" })).toHaveAttribute("href", "/runs");
    expect(screen.queryByTestId("ct-callout")).toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent("正在加载指挥塔实时总览...");
  });

  it("switches the page intro into recovery mode when live data is unavailable", async () => {
    mockFetchCommandTowerOverview.mockRejectedValueOnce(new Error("overview down"));
    mockFetchPmSessions.mockRejectedValueOnce(new Error("sessions down"));

    render(await CommandTowerPage());

    expect(screen.getByText("Recovery mode / live surface unavailable")).toBeInTheDocument();
    expect(
      screen.getByText("Command Tower cannot read the live overview right now. Verify the read-only truth first, then take one recovery path."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Command Tower overview and PM session list are temporarily unavailable. Try again later.")
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Reload Command Tower" })).toHaveAttribute("href", "/command-tower");
    expect(screen.getByRole("link", { name: "Start from PM" })).toHaveAttribute("href", "/pm");
    expect(screen.queryByTestId("ct-live-client")).toBeNull();
  });

  it("switches the page intro into zh-CN recovery mode when live data is unavailable", async () => {
    mockCookies.mockResolvedValue({
      get: (name: string) => (name === "openvibecoding.ui.locale" ? { value: "zh-CN" } : undefined),
      toString: () => "openvibecoding.ui.locale=zh-CN",
    });
    mockFetchCommandTowerOverview.mockRejectedValueOnce(new Error("总览失败"));
    mockFetchPmSessions.mockRejectedValueOnce(new Error("会话失败"));

    render(await CommandTowerPage());

    expect(screen.getByText("恢复模式 / 当前主面不可用")).toBeInTheDocument();
    expect(screen.getByText("指挥塔当前拿不到实时总览。先确认只读真相，再走一条恢复路径。")).toBeInTheDocument();
    expect(screen.getByText("实时总览暂时不可读")).toBeInTheDocument();
    expect(screen.getByText("指挥塔总览与 PM 会话列表当前都不可用。请稍后再试。")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "重载指挥塔" })).toHaveAttribute("href", "/command-tower");
    expect(screen.getByRole("link", { name: "回到 PM 入口" })).toHaveAttribute("href", "/pm");
    expect(screen.queryByTestId("ct-live-client")).toBeNull();
  });
});
