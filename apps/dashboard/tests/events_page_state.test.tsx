import { render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("../lib/api", () => ({
  fetchAllEvents: vi.fn(),
}));

import EventsPage from "../app/events/page";
import { fetchAllEvents } from "../lib/api";

describe("events page state rendering", () => {
  const mockFetchAllEvents = vi.mocked(fetchAllEvents);

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders empty state when there are no events", async () => {
    mockFetchAllEvents.mockResolvedValueOnce([] as never[]);

    render(await EventsPage());

    expect(screen.getByText("No events yet")).toBeInTheDocument();
    expect(screen.getByTestId("events-filter-form")).toBeInTheDocument();
    expect(document.querySelector("[data-testid^='events-run-link-']")).toBeNull();
  });

  it("shows warning when events loading fails", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    mockFetchAllEvents.mockRejectedValueOnce(new Error("events backend timeout"));

    render(await EventsPage());

    expect(screen.getByRole("status")).toHaveTextContent("Event stream is temporarily unavailable. Try again later.");
    expect(screen.getByRole("status")).toHaveTextContent("The event stream is currently in degraded snapshot mode. Re-check run detail before approval or rollback.");
    expect(screen.getByText("No events yet")).toBeInTheDocument();

    consoleSpy.mockRestore();
  });

  it("renders muted placeholder when run id is blank and keeps short run id untruncated", async () => {
    mockFetchAllEvents.mockResolvedValueOnce([
      {
        event: "RUN_NO_ID",
        run_id: "   ",
        ts: "2026-03-01T00:00:00Z",
      },
      {
        event: "RUN_SHORT_ID",
        run_id: "run-1",
        ts: "2026-03-01T00:00:01Z",
      },
    ] as never[]);

    render(await EventsPage());

    const noIdRow = screen.getByText("RUN_NO_ID").closest("tr");
    expect(noIdRow).not.toBeNull();
    expect(within(noIdRow as HTMLTableRowElement).queryByRole("link")).not.toBeInTheDocument();
    expect(within(noIdRow as HTMLTableRowElement).getByText("-")).toBeInTheDocument();

    const shortLink = screen.getByRole("link", { name: "run-1" });
    expect(shortLink).toHaveAttribute("href", "/runs/run-1");
  });

  it("highlights high-risk events and supports risk filtering", async () => {
    mockFetchAllEvents.mockResolvedValueOnce([
      {
        event: "RUN_FAILED",
        run_id: "run-risk-1",
        ts: "2026-03-01T01:00:00Z",
      },
      {
        event: "RUN_UPDATED",
        run_id: "run-normal-1",
        ts: "2026-03-01T01:00:01Z",
      },
    ] as never[]);

    render(await EventsPage({ searchParams: Promise.resolve({ risk: "HIGH" }) }));

    expect(screen.getByText("RUN_FAILED")).toBeInTheDocument();
    expect(screen.queryByText("RUN_UPDATED")).not.toBeInTheDocument();
    expect(screen.getAllByText("High risk").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Failures & rollback").length).toBeGreaterThan(0);
  });

  it("filters by category and query text across event payload hints", async () => {
    mockFetchAllEvents.mockResolvedValueOnce([
      {
        event: "AUTH_DENY",
        run_id: "run-security-1",
        ts: "2026-03-01T01:10:00Z",
        message: "gateway denied expired token",
        source: "gateway",
      },
      {
        event: "REVIEW_READY",
        run_id: "run-approval-1",
        ts: "2026-03-01T01:11:00Z",
        stage: "manual-review",
      },
    ] as never[]);

    render(await EventsPage({ searchParams: Promise.resolve({ q: "gateway", category: "SECURITY" }) }));

    expect(screen.getByText("AUTH_DENY")).toBeInTheDocument();
    expect(screen.queryByText("REVIEW_READY")).not.toBeInTheDocument();
    expect(screen.getAllByText("Security & access").length).toBeGreaterThan(0);
  });

  it("falls back invalid filters to all and keeps approval plus orchestration categories visible", async () => {
    mockFetchAllEvents.mockResolvedValueOnce([
      {
        event: "DIFF_GATE_REVIEW",
        run_id: "run-approval-2",
        ts: "2026-03-01T01:20:00Z",
        stage: "review",
      },
      {
        event: "PIPELINE_UPDATE",
        run_id: "run-orchestration-1",
        ts: "2026-03-01T01:21:00Z",
        status: "ok",
      },
    ] as never[]);

    render(await EventsPage({ searchParams: Promise.resolve({ risk: "unexpected", category: "nope" }) }));

    expect(screen.getByText("DIFF_GATE_REVIEW")).toBeInTheDocument();
    expect(screen.getByText("PIPELINE_UPDATE")).toBeInTheDocument();
    expect(screen.getAllByText("Approvals & review").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Runtime orchestration").length).toBeGreaterThan(0);
  });
});
