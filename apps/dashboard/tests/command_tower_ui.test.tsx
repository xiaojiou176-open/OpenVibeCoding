import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

const mockUsePathname = vi.fn(() => "/");

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => mockUsePathname(),
}));

import AppNav from "../components/AppNav";
import BlockerPanel from "../components/command-tower/BlockerPanel";
import ConversationGraph from "../components/command-tower/ConversationGraph";
import SessionBoard from "../components/command-tower/SessionBoard";
import { metadata as commandTowerMetadata } from "../app/command-tower/page";
import { getUiCopy } from "@cortexpilot/frontend-shared/uiCopy";

function getRequiredSessionRow(sessionId: string): HTMLTableRowElement {
  const sessionLink = document.querySelector(`a[href="/command-tower/sessions/${sessionId}"]`);
  expect(sessionLink).not.toBeNull();
  const row = sessionLink?.closest("tr");
  expect(row).not.toBeNull();
  return row as HTMLTableRowElement;
}

function expectSessionAnnouncement(
  row: HTMLTableRowElement,
  status: string,
  health: string,
  options?: { stale?: boolean },
): void {
  const announcement = within(row).getByText(
    (content) => content.includes(`Session status: ${status}`) && content.includes(`health: ${health}`),
  );
  expect(announcement).toHaveClass("sr-only");
  const text = announcement.textContent || "";
  const hasStaleSuffix = text.includes("update is stale");
  expect(hasStaleSuffix).toBe(Boolean(options?.stale));
}

describe("command tower ui surfaces", () => {
  it("renders empty session board state with accessible caption", () => {
    render(<SessionBoard sessions={[]} />);

    const sessionTable = screen.getByRole("table", { name: /command tower/i });
    expect(sessionTable).toBeInTheDocument();
    expect(within(sessionTable).getByRole("link", { name: /Create a session from PM/i })).toHaveAttribute("href", "/pm");

    const columnHeaders = within(sessionTable).getAllByRole("columnheader");
    expect(columnHeaders).toHaveLength(4);
    columnHeaders.forEach((header) => {
      expect(header).toHaveAttribute("scope", "col");
    });
  });

  it("renders session status variants and link navigation", async () => {
    render(
      <SessionBoard
        sessions={[
          {
            pm_session_id: "pm-active",
            status: "active",
            run_count: 1,
            running_runs: 1,
            failed_runs: 0,
            success_runs: 0,
            blocked_runs: 0,
            current_role: "PM",
            current_step: "intake",
            objective: "A",
          },
          {
            pm_session_id: "pm-paused",
            status: "paused",
            run_count: 2,
            running_runs: 0,
            failed_runs: 0,
            success_runs: 1,
            blocked_runs: 1,
            current_role: "TL",
            current_step: "review",
            objective: "B",
          },
          {
            pm_session_id: "pm-failed",
            status: "failed",
            run_count: 2,
            running_runs: 0,
            failed_runs: 1,
            success_runs: 0,
            blocked_runs: 1,
            current_role: "Worker",
            current_step: "test",
            objective: "C",
          },
          {
            pm_session_id: "pm-done",
            status: "done",
            run_count: 3,
            running_runs: 0,
            failed_runs: 0,
            success_runs: 3,
            blocked_runs: 0,
            current_role: "PM",
            current_step: "close",
            objective: "D",
          },
          {
            pm_session_id: "pm-unknown",
            status: "" as any,
            run_count: 0,
            running_runs: 0,
            failed_runs: 0,
            success_runs: 0,
            blocked_runs: 0,
            current_role: "",
            current_step: "",
            objective: "",
            created_at: "2026-02-09T00:00:00Z",
            updated_at: "",
          },
          {
            pm_session_id: "pm-stale",
            status: "done",
            run_count: 1,
            running_runs: 0,
            failed_runs: 0,
            success_runs: 1,
            blocked_runs: 0,
            current_role: "PM",
            current_step: "close",
            objective: "stale session",
            created_at: "2000-01-01T00:00:00Z",
            updated_at: "2000-01-01T00:00:00Z",
          },
        ]}
      />,
    );

    expect(within(getRequiredSessionRow("pm-active")).getByRole("link", { name: "A" })).toHaveAttribute(
      "href",
      "/command-tower/sessions/pm-active",
    );

    const sessionExpectations = [
      { id: "pm-active", status: "active", health: "Running", completion: "Early sample" },
      { id: "pm-paused", status: "paused", health: "Blocked", completion: "Success rate 50%" },
      { id: "pm-failed", status: "failed", health: "High risk", completion: "Failure path 1" },
      { id: "pm-done", status: "done", health: "Stable", completion: "Success rate 100%" },
      { id: "pm-unknown", status: "unknown", health: "Not started", completion: "Early sample", stale: true },
      { id: "pm-stale", status: "done", health: "Stable", completion: "Success rate 100%", stale: true },
    ];

    sessionExpectations.forEach((item) => {
      const row = getRequiredSessionRow(item.id);
      const rowScope = within(row);
      expect(rowScope.getAllByRole("link")[0]).toHaveAttribute(
        "href",
        `/command-tower/sessions/${item.id}`,
      );
      const progressbar = rowScope.queryByRole("progressbar", { name: `Session ${item.id} success rate` });
      const earlySample = rowScope.queryByText("Early sample");
      const failureBadge = rowScope.queryByText(/Failure path/);
      const completionSignal =
        progressbar?.getAttribute("aria-valuetext")
        ?? earlySample?.textContent
        ?? failureBadge?.textContent
        ?? null;
      expect(completionSignal).toBe(item.completion);
      expectSessionAnnouncement(row, item.status, item.health, { stale: Boolean(item.stale) });
    });

    const activeRow = getRequiredSessionRow("pm-active");
    expect(within(activeRow).getByText("Running")).toBeInTheDocument();
    expect(within(activeRow).getAllByText("Running 1").length).toBeGreaterThan(0);
    expect(within(activeRow).getByText("Runs 1 · Success 0")).toBeInTheDocument();

    expect(within(getRequiredSessionRow("pm-unknown")).getByText(/\d+d ago/)).toHaveAttribute("title", "2026-02-09T00:00:00Z");
    expect(within(getRequiredSessionRow("pm-stale")).getByText("Stale")).toBeInTheDocument();
  });

  it("shows snapshot labels instead of relative freshness when snapshot mode is enabled", () => {
    render(
      <SessionBoard
        snapshotStatus={{ enabled: true, label: "Cached snapshot (refresh failed)" }}
        sessions={[
          {
            pm_session_id: "pm-snapshot",
            status: "active",
            run_count: 1,
            running_runs: 1,
            failed_runs: 0,
            success_runs: 0,
            blocked_runs: 0,
            current_role: "PM",
            current_step: "intake",
            objective: "snapshot test",
            created_at: "2026-02-09T00:00:00Z",
            updated_at: "2026-02-09T00:00:00Z",
          },
        ]}
      />,
    );

    expect(screen.getByText(/Cached snapshot \(refresh failed\)/)).toBeInTheDocument();
    const row = getRequiredSessionRow("pm-snapshot");
    expect(within(row).getByText(/\d+d ago|just now|\d+m ago|\d+h ago/)).toHaveAttribute("title", "2026-02-09T00:00:00Z");
    expect(within(row).getByText("Snapshot time · hover to see the full timestamp")).toBeInTheDocument();
    expect(within(row).queryByText("Stale")).not.toBeInTheDocument();
  });

  it("marks active sidebar link with aria-current", () => {
    mockUsePathname.mockReturnValue("/command-tower/sessions/demo");
    render(<AppNav />);

    expect(screen.getByRole("navigation", { name: "Dashboard navigation" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Command Tower" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Overview" })).not.toHaveAttribute("aria-current");
  });

  it("supports zh-CN dashboard navigation copy when locale is provided", () => {
    render(<AppNav locale="zh-CN" />);

    expect(screen.getByRole("navigation", { name: "控制台导航" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "指挥塔" })).toBeInTheDocument();
    expect(screen.getByText(/低频工具\s*8/)).toBeInTheDocument();
  });

  it("keeps command tower page copy aligned across locales", () => {
    const en = getUiCopy("en").dashboard.commandTowerPage;
    const zh = getUiCopy("zh-CN").dashboard.commandTowerPage;

    expect(en.actions.reload).toBe("Reload Command Tower");
    expect(zh.actions.reload).toBe("重载指挥塔");
    expect(en.actions.openWorkflowCases).toBe("Open Workflow Cases");
    expect(zh.actions.openWorkflowCases).toBe("打开工作流案例");
    expect(en.fallbackLoading).toContain("Command Tower");
    expect(zh.fallbackLoading).toContain("指挥塔");
    expect(en.liveHome.focusModeLabels.highRisk).toBe("high risk");
    expect(zh.liveHome.focusModeLabels.highRisk).toBe("高风险");
    expect(en.liveHome.layout.overviewTitle).toBe("Live posture and action entrypoints");
    expect(zh.liveHome.layout.overviewTitle).toBe("实时态势与动作入口");
  });

  it("exports command tower metadata for route-level discoverability", () => {
    expect(commandTowerMetadata.title).toBe("Command Tower | OpenVibeCoding");
    expect(commandTowerMetadata.description).toContain("Workflow Cases");
  });

  it("renders empty conversation graph state", () => {
    render(
      <ConversationGraph
        graph={{
          pm_session_id: "pm-1",
          window: "24h",
          nodes: [],
          edges: [],
          stats: { node_count: 0, edge_count: 0 },
        }}
      />,
    );

    expect(screen.queryByRole("list", { name: /Node traffic list|node traffic/i })).toBeNull();
    expect(screen.queryByRole("list", { name: /Hot path list|hot path/i })).toBeNull();
    expect(screen.getByRole("list", { name: "Graph summary metrics" })).toBeInTheDocument();
    const handoffTable = screen.getByRole("table", { name: /handoff/i });
    expect(handoffTable).toBeInTheDocument();
    expect(within(handoffTable).getAllByRole("row")).toHaveLength(2);
  });

  it("renders conversation graph nodes and edges", () => {
    render(
      <ConversationGraph
        graph={{
          pm_session_id: "pm-2",
          window: "2h",
          nodes: ["PM", "TL", "Worker"],
          edges: [
            {
              from_role: "PM",
              to_role: "TL",
              run_id: "run-1",
              ts: "2026-02-09T10:00:00Z",
              event_ref: "evt-1",
            },
            {
              from_role: "TL",
              to_role: "Worker",
              run_id: "run-2",
              ts: "2026-02-09T10:01:00Z",
              event_ref: "evt-2",
            },
            {
              from_role: "",
              to_role: undefined,
              run_id: "",
              ts: undefined,
              event_ref: "",
            },
          ],
          stats: { node_count: 3, edge_count: 3 },
        }}
      />,
    );

    const nodeTrafficList = screen.getByRole("list", { name: /Node traffic list|node traffic/i });
    expect(within(nodeTrafficList).getAllByRole("listitem").length).toBeGreaterThanOrEqual(3);
    const hotPathList = screen.getByRole("list", { name: /Hot path list|hot path/i });
    expect(within(hotPathList).getAllByRole("listitem").length).toBeGreaterThanOrEqual(2);

    expect(screen.getByRole("cell", { name: "evt-1" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "evt-2" })).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Graph summary metrics" })).toHaveTextContent(/Window\s*2h/i);
    const handoffTable = screen.getByRole("table", { name: /handoff/i });
    expect(within(handoffTable).getAllByRole("row").length).toBeGreaterThan(2);
    expect(within(handoffTable).getAllByText("-", { selector: "td" }).length).toBeGreaterThan(0);
  });

  it("renders blocker panel empty and populated states", () => {
    const { rerender } = render(<BlockerPanel blockers={[]} />);
    expect(screen.getByRole("status")).toHaveTextContent(/No blocked sessions right now|no blocker/i);

    rerender(
      <BlockerPanel
        blockers={[
          {
            pm_session_id: "pm-blocked",
            objective: "recover chain",
            blocked_runs: 3,
            running_runs: 1,
            failed_runs: 2,
            success_runs: 0,
            owner_pm: "terry",
            status: "failed",
            run_count: 4,
          },
          {
            pm_session_id: "pm-blocked-empty",
            objective: "",
            blocked_runs: 1,
            running_runs: 0,
            failed_runs: 1,
            success_runs: 0,
            owner_pm: "",
            status: "failed",
            run_count: 1,
          },
        ]}
      />,
    );

    const blockedLink = screen.getByRole("link", { name: "pm-blocked" });
    expect(blockedLink).toHaveAttribute("href", "/command-tower/sessions/pm-blocked");
    const blockedCard = blockedLink.closest("article");
    expect(blockedCard).not.toBeNull();
    const blockedScope = within(blockedCard as HTMLElement);
    expect(blockedScope.getByText("Blocked 3")).toBeInTheDocument();
    expect(blockedScope.getByText("Running 1")).toBeInTheDocument();
    expect(blockedScope.getByText("Failed 2")).toBeInTheDocument();
    expect(blockedScope.getByText("Owner terry")).toBeInTheDocument();

    const blockedEmptyLink = screen.getByRole("link", { name: "pm-blocked-empty" });
    expect(blockedEmptyLink).toHaveAttribute("href", "/command-tower/sessions/pm-blocked-empty");
    const blockedEmptyCard = blockedEmptyLink.closest("article");
    expect(blockedEmptyCard).not.toBeNull();
    const blockedEmptyScope = within(blockedEmptyCard as HTMLElement);
    expect(blockedEmptyScope.getByText("Owner -")).toBeInTheDocument();
    expect(blockedEmptyScope.getByText("-", { selector: "p.blocker-panel__item-objective" })).toBeInTheDocument();
  });
});
