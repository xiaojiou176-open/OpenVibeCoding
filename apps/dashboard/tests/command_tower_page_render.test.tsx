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
    expect(screen.getByText("这一页应该先告诉你：现在发生什么、哪条线危险、下一步该去哪个真相入口。")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("正在加载指挥塔实时总览...");
    expect(screen.getByTestId("ct-callout")).toHaveTextContent("指挥塔当前只提供部分真相");
    expect(screen.getByTestId("ct-live-client")).toHaveTextContent("overview:0 sessions:1");
  });

  it("switches the page intro into recovery mode when live data is unavailable", async () => {
    mockFetchCommandTowerOverview.mockRejectedValueOnce(new Error("overview down"));
    mockFetchPmSessions.mockRejectedValueOnce(new Error("sessions down"));

    render(await CommandTowerPage());

    expect(screen.getByText("Recovery mode / live surface unavailable")).toBeInTheDocument();
    expect(
      screen.getByText("Command Tower cannot read the live overview right now. Verify the read-only truth first, then take one recovery path."),
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
    expect(screen.getByText("指挥塔当前拿不到 live 总览。先确认只读真相，再走一条恢复路径。")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "重载指挥塔" })).toHaveAttribute("href", "/command-tower");
    expect(screen.getByRole("link", { name: "回到 PM 入口" })).toHaveAttribute("href", "/pm");
    expect(screen.queryByTestId("ct-live-client")).toBeNull();
  });
});
