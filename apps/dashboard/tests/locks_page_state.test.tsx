import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
  fetchLocks: vi.fn(),
  releaseLocks: vi.fn(),
  mutationExecutionCapability: vi.fn(),
}));

import LocksPage from "../app/locks/page";
import { fetchLocks, mutationExecutionCapability, releaseLocks } from "../lib/api";

type Deferred<T> = {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (reason?: unknown) => void;
};

function createDeferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe("locks page state rendering", () => {
  const mockFetchLocks = vi.mocked(fetchLocks);
  const mockReleaseLocks = vi.mocked(releaseLocks);
  const mockMutationCapability = vi.mocked(mutationExecutionCapability);

  beforeEach(() => {
    vi.clearAllMocks();
    mockMutationCapability.mockReturnValue({
      executable: true,
      operatorRole: "TECH_LEAD",
    });
    mockReleaseLocks.mockResolvedValue({ ok: true } as never);
  });

  it("renders empty state when there are no lock records", async () => {
    mockFetchLocks.mockResolvedValueOnce([] as never[]);

    render(<LocksPage />);

    await waitFor(() => {
      expect(screen.getByTestId("locks-count-badge")).toHaveTextContent("0 locks");
    });
    expect(await screen.findByTestId("locks-empty-state")).toBeInTheDocument();
    expect(screen.queryByTestId("locks-table-card")).not.toBeInTheDocument();
  });

  it("renders lock table and fallback placeholders for missing optional fields", async () => {
    mockFetchLocks.mockResolvedValueOnce([
      {
        lock_id: "lock-1",
        run_id: "run-1",
        agent_id: "agent-1",
        role: "WORKER",
        path: "/tmp/a",
        ts: "2026-03-01T00:00:00Z",
      },
      {
        lock_id: "lock-2",
        path: "/tmp/b",
      },
    ] as never[]);

    render(<LocksPage />);

    await waitFor(() => {
      expect(screen.getByTestId("locks-count-badge")).toHaveTextContent("2 locks");
    });
    const tableCard = await screen.findByTestId("locks-table-card");
    expect(tableCard).toBeInTheDocument();
    expect(screen.getByText("lock-1")).toBeInTheDocument();

    const secondRow = screen.getByText("lock-2").closest("tr");
    expect(secondRow).not.toBeNull();
    expect(within(secondRow as HTMLTableRowElement).getAllByText("-").length).toBeGreaterThan(0);
  });

  it("shows warning status when lock loading fails", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    mockFetchLocks.mockRejectedValueOnce(new Error("locks backend timeout"));

    render(<LocksPage />);

    expect(await screen.findByTestId("locks-warning-state")).toHaveTextContent("Lock records are unavailable right now. Please try again later.");
    expect(await screen.findByTestId("locks-empty-state")).toBeInTheDocument();

    consoleSpy.mockRestore();
  });

  it("provides single release action with feedback and role gate", async () => {
    mockMutationCapability.mockReturnValue({
      executable: false,
      operatorRole: null,
    });
    mockFetchLocks
      .mockResolvedValueOnce([
        {
          lock_id: "lock-1",
          run_id: "run-1",
          path: "/tmp/a",
        },
      ] as never[])
      .mockResolvedValueOnce([
        {
          lock_id: "lock-1",
          run_id: "run-1",
          path: "/tmp/a",
        },
      ] as never[]);

    render(<LocksPage />);
    await screen.findByTestId("locks-table-card");

    const releaseButton = screen.getByTestId("locks-release-action-lock-1");
    expect(releaseButton).toBeDisabled();
    expect(screen.getByTestId("locks-role-tip")).toBeInTheDocument();

    mockMutationCapability.mockReturnValue({
      executable: true,
      operatorRole: "TECH_LEAD",
    });
    fireEvent.click(screen.getByTestId("locks-refresh-action"));
    await screen.findByTestId("locks-table-card");

    fireEvent.click(screen.getByTestId("locks-release-action-lock-1"));
    await waitFor(() => {
      expect(mockReleaseLocks).toHaveBeenCalledWith(["/tmp/a"]);
      expect(screen.getByTestId("locks-release-feedback")).toHaveTextContent("Lock release succeeded");
    });
  });

  it("shows loading feedback and last updated timestamp during manual refresh", async () => {
    const refreshDeferred = createDeferred<Array<Record<string, unknown>>>();
    mockFetchLocks
      .mockResolvedValueOnce([
        { lock_id: "lock-1", run_id: "run-1", path: "/tmp/a" },
      ] as never[])
      .mockImplementationOnce(() => refreshDeferred.promise as Promise<any>);

    render(<LocksPage />);
    await screen.findByTestId("locks-table-card");
    expect(screen.getByTestId("locks-last-updated")).toHaveTextContent("Last refreshed:");

    fireEvent.click(screen.getByTestId("locks-refresh-action"));
    await waitFor(() => {
      expect(screen.getByTestId("locks-refresh-action")).toHaveTextContent("Refreshing...");
      expect(screen.getByTestId("locks-refresh-feedback")).toHaveTextContent("Refreshing lock list...");
    });

    refreshDeferred.resolve([{ lock_id: "lock-1", run_id: "run-1", path: "/tmp/a" }]);
    await waitFor(() => {
      expect(screen.getByTestId("locks-refresh-feedback")).toHaveTextContent("Lock list refreshed");
      expect(screen.getByTestId("locks-last-updated")).not.toHaveTextContent("Last refreshed: --");
    });
  });

  it("keeps lock list/count in sync after release even when backend refresh is stale", async () => {
    mockFetchLocks
      .mockResolvedValueOnce([
        { lock_id: "lock-1", run_id: "run-1", path: "/tmp/a" },
        { lock_id: "lock-2", run_id: "run-2", path: "/tmp/b" },
      ] as never[])
      .mockResolvedValueOnce([
        { lock_id: "lock-1", run_id: "run-1", path: "/tmp/a" },
        { lock_id: "lock-2", run_id: "run-2", path: "/tmp/b" },
      ] as never[]);
    mockReleaseLocks.mockResolvedValueOnce({ ok: true } as never);

    render(<LocksPage />);
    await screen.findByTestId("locks-table-card");
    expect(screen.getByTestId("locks-count-badge")).toHaveTextContent("2 locks");

    fireEvent.click(screen.getByTestId("locks-release-action-lock-1"));
    await waitFor(() => {
      expect(mockReleaseLocks).toHaveBeenCalledWith(["/tmp/a"]);
      expect(screen.getByTestId("locks-release-feedback")).toHaveTextContent("Lock release succeeded");
      expect(screen.getByTestId("locks-count-badge")).toHaveTextContent("1 locks");
      expect(screen.queryByText("lock-1")).not.toBeInTheDocument();
      expect(screen.getByText("lock-2")).toBeInTheDocument();
    });
  });

  it("expands to show all locks when more than the default rows exist", async () => {
    mockFetchLocks.mockResolvedValueOnce(
      Array.from({ length: 11 }).map((_, index) => ({
        lock_id: `lock-${index + 1}`,
        run_id: `run-${index + 1}`,
        path: `/tmp/${index + 1}`,
      })) as never[],
    );

    render(<LocksPage />);
    await screen.findByTestId("locks-table-card");

    expect(screen.getByText("1 more lock records are hidden.")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("locks-show-all"));

    await waitFor(() => {
      expect(screen.getByText("lock-11")).toBeInTheDocument();
      expect(screen.queryByTestId("locks-show-all")).not.toBeInTheDocument();
    });
  });
});
