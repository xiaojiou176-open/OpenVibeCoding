import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({
  fetchDiffGate: vi.fn(),
  fetchDiff: vi.fn(),
  mutationExecutionCapability: vi.fn(),
  rollbackRun: vi.fn(),
  rejectRun: vi.fn(),
}));

vi.mock("../components/DiffViewer", () => ({
  __esModule: true,
  default: ({ diff, allowedPaths }: { diff: string; allowedPaths: string[] }) => (
    <div data-testid="diff-viewer-mock">
      {diff}
      {"|"}
      {allowedPaths.join(",")}
    </div>
  ),
}));

import DiffGatePanel from "../components/DiffGatePanel";
import { fetchDiff, fetchDiffGate, mutationExecutionCapability, rejectRun, rollbackRun } from "../lib/api";
import type { JsonValue } from "../lib/types";

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

function makePendingItem(runId = "run/alpha", status = "FAILED"): Record<string, JsonValue> {
  return {
    run_id: runId,
    status,
    failure_reason: "worker rejected",
    allowed_paths: ["/src/a.ts", 42],
  };
}

function jsonResponse(payload: unknown, ok = true, status = 200): Response {
  return {
    ok,
    status,
    json: async () => payload,
  } as unknown as Response;
}

describe("DiffGatePanel coverage debt branches", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    vi.stubGlobal("fetch", vi.fn());
    vi.mocked(mutationExecutionCapability).mockReturnValue({
      executable: true,
      operatorRole: "TECH_LEAD",
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("covers loading to list flow and interactive diff/rollback/reject actions", async () => {
    const diffDeferred = createDeferred<{ diff?: string }>();
    vi.mocked(fetchDiffGate).mockResolvedValue([makePendingItem("run/alpha", "PENDING")]);
    vi.mocked(fetchDiff).mockImplementation(() => diffDeferred.promise as Promise<any>);
    vi.mocked(rollbackRun).mockResolvedValue({ ok: true } as any);
    vi.mocked(rejectRun).mockResolvedValue({ ok: false } as any);

    render(<DiffGatePanel />);

    expect(screen.getByTestId("diff-gate-loading-state")).toBeInTheDocument();
    expect(screen.getByTestId("diff-gate-loading-actions")).toBeInTheDocument();
    expect(screen.getByTestId("diff-gate-loading-approve")).toBeDisabled();
    expect(screen.getByTestId("diff-gate-loading-reject")).toBeDisabled();
    expect(screen.getByTestId("diff-gate-loading-rollback")).toBeDisabled();
    expect(screen.getByTestId("diff-gate-loading-audit-context")).toHaveTextContent("Run IDs, status snapshots, and recent audit timestamps will appear after the data returns.");
    const item = await screen.findByTestId("diff-gate-item-run_alpha");
    expect(item).toBeInTheDocument();
    expect(screen.getByText("worker rejected")).toBeInTheDocument();

    const details = within(item).getByText("Allowed paths").closest("details");
    details?.setAttribute("open", "true");
    expect(within(item).getByText(/42/)).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("diff-gate-toggle-diff-run_alpha"));
    await waitFor(() => {
      expect(screen.getByTestId("diff-gate-toggle-diff-run_alpha")).toBeDisabled();
      expect(screen.getByTestId("diff-gate-toggle-diff-run_alpha")).toHaveTextContent("Loading Diff...");
    });

    await act(async () => {
      diffDeferred.resolve({ diff: "@@ -1 +1 @@" });
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(screen.getByTestId("diff-gate-diff-region-run_alpha")).toBeInTheDocument();
      expect(screen.getByTestId("diff-viewer-mock")).toHaveTextContent("@@ -1 +1 @@|/src/a.ts,42");
    });

    fireEvent.click(screen.getByTestId("diff-gate-toggle-diff-run_alpha"));
    await waitFor(() => {
      expect(screen.queryByTestId("diff-gate-diff-region-run_alpha")).not.toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("diff-gate-rollback-run_alpha"));
    await waitFor(() => {
      expect(rollbackRun).toHaveBeenCalledWith("run/alpha");
      expect(screen.getByTestId("diff-gate-feedback-run_alpha")).toHaveTextContent("Rollback succeeded");
    });

    fireEvent.click(screen.getByTestId("diff-gate-reject-run_alpha"));
    await waitFor(() => {
      expect(rejectRun).toHaveBeenCalledWith("run/alpha");
      expect(screen.getByTestId("diff-gate-feedback-run_alpha")).toHaveTextContent("Reject failed");
    });
  });

  it("keeps current list context on soft refresh failure", async () => {
    vi.mocked(fetchDiffGate)
      .mockResolvedValueOnce([makePendingItem("run/keep")])
      .mockRejectedValueOnce(new Error("network timeout"));

    render(<DiffGatePanel />);
    await screen.findByTestId("diff-gate-item-run_keep");

    fireEvent.click(screen.getByTestId("diff-gate-refresh-list"));
    await waitFor(() => {
      expect(screen.getByTestId("diff-gate-soft-error")).toHaveTextContent("Refresh failed");
      expect(screen.getByTestId("diff-gate-item-run_keep")).toBeInTheDocument();
    });
  });

  it("forces a no-store network refresh call before falling back to API client", async () => {
    vi.mocked(fetchDiffGate).mockResolvedValueOnce([makePendingItem("run/seed")]);
    const fetchMock = global.fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValueOnce(jsonResponse([makePendingItem("run/network")]));

    render(<DiffGatePanel />);
    await screen.findByTestId("diff-gate-item-run_seed");

    fireEvent.click(screen.getByTestId("diff-gate-refresh-list"));
    await waitFor(() => {
      expect(screen.getByTestId("diff-gate-item-run_network")).toBeInTheDocument();
    });
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/diff-gate\?refresh_ts=/),
      expect.objectContaining({
        cache: "no-store",
        credentials: "same-origin",
      }),
    );
  });

  it("shows pre-gated disabled actions when operator role missing", async () => {
    vi.mocked(mutationExecutionCapability).mockReturnValue({
      executable: false,
      operatorRole: null,
    });
    vi.mocked(fetchDiffGate).mockResolvedValue([makePendingItem("run/no-role")]);
    vi.mocked(fetchDiff).mockResolvedValue({ diff: "@@ -0 +1 @@" } as any);

    render(<DiffGatePanel />);
    await screen.findByTestId("diff-gate-item-run_no-role");

    expect(screen.getByTestId("diff-gate-role-tip")).toBeInTheDocument();
    expect(screen.getByTestId("diff-gate-rollback-run_no-role")).toBeDisabled();
    expect(screen.getByTestId("diff-gate-reject-run_no-role")).toBeDisabled();
  });

  it("covers diff empty and diff fetch failure fallbacks", async () => {
    vi.mocked(fetchDiffGate).mockResolvedValue([makePendingItem("run/beta")]);
    vi.mocked(fetchDiff)
      .mockResolvedValueOnce({} as any)
      .mockRejectedValueOnce(new Error("403 forbidden"));

    render(<DiffGatePanel />);
    await screen.findByTestId("diff-gate-item-run_beta");

    fireEvent.click(screen.getByTestId("diff-gate-toggle-diff-run_beta"));
    await waitFor(() => {
      expect(screen.getByTestId("diff-gate-feedback-run_beta")).toHaveTextContent("No visible diff was produced for this run");
      expect(screen.getByTestId("diff-gate-readonly-empty-run_beta")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("diff-gate-toggle-diff-run_beta"));
    fireEvent.click(screen.getByTestId("diff-gate-toggle-diff-run_beta"));
    await waitFor(() => {
      expect(screen.getByTestId("diff-gate-feedback-run_beta")).toHaveTextContent("Failed to load Diff");
    });
  });

  it("uses actionable 422 copy for rollback/reject failures", async () => {
    vi.mocked(fetchDiffGate).mockResolvedValue([makePendingItem("run/422", "PENDING")]);
    vi.mocked(rollbackRun).mockRejectedValue(new Error("API /api/runs/run_422/rollback failed: 422"));
    vi.mocked(rejectRun).mockRejectedValue(new Error("API /api/runs/run_422/reject failed: 422"));

    render(<DiffGatePanel />);
    await screen.findByTestId("diff-gate-item-run_422");

    fireEvent.click(screen.getByTestId("diff-gate-rollback-run_422"));
    await waitFor(() => {
      expect(screen.getByTestId("diff-gate-feedback-run_422")).toHaveTextContent("does not satisfy the action precondition");
    });

    fireEvent.click(screen.getByTestId("diff-gate-reject-run_422"));
    await waitFor(() => {
      expect(screen.getByTestId("diff-gate-feedback-run_422")).toHaveTextContent("does not satisfy the action precondition");
    });
  });

  it("supports summary-first 10 rows with search/filter/expand", async () => {
    vi.mocked(fetchDiffGate).mockResolvedValue(
      Array.from({ length: 13 }).map((_, index) =>
        makePendingItem(`run-${index + 1}`, index < 8 ? "FAILED" : "SUCCESS"),
      ),
    );

    render(<DiffGatePanel />);
    await screen.findByTestId("diff-gate-item-run-13");

    expect(screen.getAllByRole("listitem")).toHaveLength(10);

    fireEvent.change(screen.getByTestId("diff-gate-status-filter"), { target: { value: "SUCCESS" } });
    await waitFor(() => {
      expect(screen.queryByTestId("diff-gate-item-run-9")).toBeInTheDocument();
      expect(screen.queryByTestId("diff-gate-item-run-1")).not.toBeInTheDocument();
    });

    fireEvent.change(screen.getByTestId("diff-gate-search-input"), { target: { value: "run-13" } });
    await waitFor(() => {
      expect(screen.queryByTestId("diff-gate-item-run-13")).toBeInTheDocument();
      expect(screen.queryByTestId("diff-gate-item-run-9")).not.toBeInTheDocument();
    });

    fireEvent.change(screen.getByTestId("diff-gate-status-filter"), { target: { value: "ALL" } });
    fireEvent.change(screen.getByTestId("diff-gate-search-input"), { target: { value: "" } });
    await waitFor(() => {
      expect(screen.getByTestId("diff-gate-expand-list")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("diff-gate-expand-list"));
    await waitFor(() => {
      expect(screen.queryByTestId("diff-gate-item-run-13")).toBeInTheDocument();
      expect(screen.getByTestId("diff-gate-collapse-footer")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("diff-gate-collapse-footer"));
    await waitFor(() => {
      expect(screen.getByTestId("diff-gate-expand-list")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("diff-gate-expand-list"));
    await waitFor(() => {
      expect(screen.getByTestId("diff-gate-collapse-list")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId("diff-gate-collapse-list"));
    await waitFor(() => {
      expect(screen.getByTestId("diff-gate-expand-list")).toBeInTheDocument();
    });
  });

  it("covers load error retry and empty-state refresh transitions", async () => {
    vi.mocked(fetchDiffGate)
      .mockRejectedValueOnce(new Error("load failed"));
    const retryDeferred = createDeferred<Response>();
    const fetchMock = global.fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockImplementationOnce(() => retryDeferred.promise);

    const firstRender = render(<DiffGatePanel />);
    const errorState = await screen.findByTestId("diff-gate-error-state");
    expect(within(errorState).getByRole("link", { name: "Open runs list for investigation" })).toHaveAttribute("href", "/runs");

    fireEvent.click(screen.getByTestId("diff-gate-retry-load"));
    expect(await screen.findByText("Retrying pending changes for review...")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/diff-gate\?refresh_ts=/),
      expect.objectContaining({
        cache: "no-store",
        credentials: "same-origin",
      }),
    );
    await act(async () => {
      retryDeferred.resolve(jsonResponse([makePendingItem("run/recover")]));
      await Promise.resolve();
    });
    await screen.findByTestId("diff-gate-item-run_recover");
    firstRender.unmount();

    vi.mocked(fetchDiffGate)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([makePendingItem("run/from-empty")]);

    render(<DiffGatePanel />);
    await screen.findByTestId("diff-gate-no-items");
    expect(screen.getByTestId("diff-gate-go-runs-list")).toHaveAttribute("href", "/runs");
    fireEvent.click(screen.getByTestId("diff-gate-refresh-list"));
    await screen.findByTestId("diff-gate-item-run_from-empty");
  });

  it("covers action-gate hints and rollback error copy variants", async () => {
    vi.mocked(fetchDiffGate).mockResolvedValue([
      makePendingItem("", "RUNNING"),
      {
        ...makePendingItem("run-blocked", "RUNNING"),
        blocked_actions: ["rollback", "reject"],
      },
      {
        ...makePendingItem("run-terminal", "DONE"),
      },
      {
        ...makePendingItem("run-rejected", "RUNNING"),
        failure_reason: "diff gate rejected by policy",
      },
      {
        ...makePendingItem("run-409", "RUNNING"),
        can_rollback: true,
      },
      {
        ...makePendingItem("run-auth", "RUNNING"),
        can_rollback: true,
      },
      {
        ...makePendingItem("run-net", "RUNNING"),
        can_rollback: true,
      },
      {
        ...makePendingItem("run-generic", "RUNNING"),
        can_rollback: true,
      },
      {
        ...makePendingItem("run-direct-false", "RUNNING"),
        can_rollback: false,
      },
      {
        ...makePendingItem("run-nested-false", "RUNNING"),
        diff_gate: { rollback_allowed: false },
      },
    ] as any);
    vi.mocked(rollbackRun).mockImplementation(async (runId: string) => {
      if (runId === "run-409") {
        throw new Error("API /api/runs/run-409/rollback failed: 409");
      }
      if (runId === "run-auth") {
        throw new Error("403 forbidden");
      }
      if (runId === "run-net") {
        throw new Error("network timeout");
      }
      throw new Error("unexpected");
    });

    render(<DiffGatePanel />);

    await screen.findByTestId("diff-gate-item-unknown");
    expect(screen.getByTestId("diff-gate-action-hint-unknown")).toHaveTextContent("Missing run_id");
    expect(screen.getByTestId("diff-gate-action-hint-run-blocked")).toHaveTextContent("policy blocks the action");
    expect(screen.getByTestId("diff-gate-action-hint-run-terminal")).toHaveTextContent("terminal state");
    expect(screen.getByTestId("diff-gate-action-hint-run-rejected")).toHaveTextContent("nothing to reject again");
    expect(screen.getByTestId("diff-gate-action-hint-run-direct-false")).toHaveTextContent("marked non-executable");
    expect(screen.getByTestId("diff-gate-action-hint-run-nested-false")).toHaveTextContent("marks this action non-executable");

    fireEvent.click(screen.getByTestId("diff-gate-rollback-run-409"));
    await waitFor(() => {
      expect(screen.getByTestId("diff-gate-feedback-run-409")).toHaveTextContent("record state changed");
    });

    fireEvent.click(screen.getByTestId("diff-gate-rollback-run-auth"));
    await waitFor(() => {
      expect(screen.getByTestId("diff-gate-feedback-run-auth")).toHaveTextContent("permission or authentication error");
    });

    fireEvent.click(screen.getByTestId("diff-gate-rollback-run-net"));
    await waitFor(() => {
      expect(screen.getByTestId("diff-gate-feedback-run-net")).toHaveTextContent("network error");
    });

    fireEvent.click(screen.getByTestId("diff-gate-rollback-run-generic"));
    await waitFor(() => {
      expect(screen.getByTestId("diff-gate-feedback-run-generic")).toHaveTextContent("check the event log and try again");
    });
  });

  it("covers force-network non-ok fallback and object payload items branch", async () => {
    vi.mocked(fetchDiffGate)
      .mockResolvedValueOnce([makePendingItem("run-seed")])
      .mockResolvedValueOnce([makePendingItem("run-fallback")]);

    const fetchMock = global.fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ error: "boom" }, false, 500))
      .mockResolvedValueOnce(
        jsonResponse({
          items: [makePendingItem("run-from-items")],
        }),
      );

    render(<DiffGatePanel />);
    await screen.findByTestId("diff-gate-item-run-seed");

    fireEvent.click(screen.getByTestId("diff-gate-refresh-list"));
    await waitFor(() => {
      expect(screen.getByTestId("diff-gate-item-run-fallback")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("diff-gate-refresh-list"));
    await waitFor(() => {
      expect(screen.getByTestId("diff-gate-item-run-from-items")).toBeInTheDocument();
    });
  });
});
