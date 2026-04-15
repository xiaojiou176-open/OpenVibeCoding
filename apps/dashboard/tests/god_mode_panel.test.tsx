import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({
  fetchPendingApprovals: vi.fn(),
  approveGodMode: vi.fn(),
  mutationExecutionCapability: vi.fn(),
}));

import GodModePanel from "../components/GodModePanel";
import { approveGodMode, fetchPendingApprovals, mutationExecutionCapability } from "../lib/api";
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

function withRole(role: string | null, executable = Boolean(role)) {
  vi.mocked(mutationExecutionCapability).mockReturnValue({
    executable,
    operatorRole: role,
  });
}

function openManualApproval() {
  fireEvent.click(screen.getByText("Handle a specific run manually"));
}

describe("god mode panel accessibility and high-risk actions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    withRole("TECH_LEAD");
    const pendingApprovals: Array<Record<string, JsonValue>> = [
      {
        run_id: "run-123",
        status: "WAITING_APPROVAL",
        reason: ["Waiting for human confirmation"],
        actions: ["Confirm risk acceptance"],
      },
    ];
    vi.mocked(fetchPendingApprovals).mockResolvedValue(pendingApprovals);
    vi.mocked(approveGodMode).mockResolvedValue({});
    vi.spyOn(console, "error").mockImplementation(() => undefined);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  async function openConfirmDialog() {
    render(<GodModePanel />);
    const trigger = await screen.findByRole("button", { name: "I am done, continue" });
    trigger.focus();
    fireEvent.click(trigger);
    const dialog = await screen.findByRole("dialog", { name: "Confirm approval" });
    return { trigger, dialog };
  }

  it("disables mutation paths when operator role missing", async () => {
    withRole(null, false);
    render(<GodModePanel />);
    openManualApproval();

    await waitFor(() => {
      expect(screen.getByTestId("god-mode-role-tip")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Approve" })).toBeDisabled();
    });
  });

  it("keeps focus looped within dialog for Tab and Shift+Tab", async () => {
    const { dialog } = await openConfirmDialog();

    const cancelButton = within(dialog).getByRole("button", { name: "Cancel" });
    const confirmButton = within(dialog).getByRole("button", { name: "Confirm approval" });

    await waitFor(() => expect(cancelButton).toHaveFocus());

    confirmButton.focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(cancelButton).toHaveFocus();

    cancelButton.focus();
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(confirmButton).toHaveFocus();
  });

  it("closes on Escape and restores focus to trigger", async () => {
    const { trigger } = await openConfirmDialog();

    fireEvent.keyDown(document, { key: "Escape" });

    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "Confirm approval" })).not.toBeInTheDocument();
      expect(trigger).toHaveFocus();
    });
  });

  it("approves from queue confirm action and updates status", async () => {
    const { dialog } = await openConfirmDialog();

    fireEvent.click(within(dialog).getByRole("button", { name: "Confirm approval" }));

    await waitFor(() => {
      expect(approveGodMode).toHaveBeenCalledWith("run-123");
      expect(screen.getByTestId("god-mode-status")).toHaveTextContent(/Approved\.|Pending approvals queue refreshed/);
    });
    expect(fetchPendingApprovals).toHaveBeenCalledTimes(2);
  });

  it("approves by manual run id input", async () => {
    render(<GodModePanel />);
    await screen.findByRole("button", { name: "I am done, continue" });
    openManualApproval();

    fireEvent.change(screen.getByRole("textbox", { name: "Run ID" }), {
      target: { value: "run-manual-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));

    await waitFor(() => {
      expect(approveGodMode).toHaveBeenCalledWith("run-manual-1");
      expect(screen.getByTestId("god-mode-status")).toHaveTextContent(/Approved\.|Pending approvals queue refreshed/);
    });
  });

  it("shows auth error message for 4xx failures", async () => {
    vi.mocked(approveGodMode).mockRejectedValueOnce(new Error("403 forbidden"));

    render(<GodModePanel />);
    await screen.findByRole("button", { name: "I am done, continue" });
    openManualApproval();

    fireEvent.change(screen.getByRole("textbox", { name: "Run ID" }), {
      target: { value: "run-auth" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));

    await waitFor(() => {
      expect(screen.getByTestId("god-mode-status")).toHaveTextContent(
        /Failed: (Approval failed: )?((permission|authentication) or (permission|authentication) issue|Authentication or permission issue)\./,
      );
    });
  });

  it("refreshes pending approvals from the inline refresh button", async () => {
    const refreshDeferred = createDeferred<Array<Record<string, JsonValue>>>();
    vi.mocked(fetchPendingApprovals)
      .mockResolvedValueOnce([
        {
          run_id: "run-123",
          status: "WAITING_APPROVAL",
          reason: ["Waiting for human confirmation"],
          actions: ["Confirm risk acceptance"],
        },
      ])
      .mockImplementationOnce(() => refreshDeferred.promise as Promise<any>);

    render(<GodModePanel />);
    await screen.findByRole("button", { name: "I am done, continue" });

    fireEvent.click(screen.getByTestId("god-mode-refresh-pending"));
    await waitFor(() => {
      expect(screen.getByTestId("god-mode-refresh-pending")).toHaveTextContent("Refreshing...");
      expect(screen.getByTestId("god-mode-status")).toHaveTextContent("Refreshing pending approvals queue...");
    });

    refreshDeferred.resolve([
      {
        run_id: "run-456",
        status: "WAITING_APPROVAL",
        reason: ["Waiting for human confirmation"],
        actions: ["Confirm risk acceptance"],
      },
    ]);

    await waitFor(() => {
      expect(fetchPendingApprovals).toHaveBeenCalledTimes(2);
      expect(screen.getByRole("button", { name: "I am done, continue" })).toBeInTheDocument();
      expect(screen.getByTestId("god-mode-status")).toHaveTextContent("Pending approvals queue refreshed");
    });
  });

  it("shows pending-load error with retry entry and recovers queue", async () => {
    vi.mocked(fetchPendingApprovals)
      .mockRejectedValueOnce(new Error("network timeout"))
      .mockResolvedValueOnce([
        {
          run_id: "run-retry",
          status: "WAITING_APPROVAL",
          reason: ["Waiting for human confirmation"],
          actions: ["Confirm risk acceptance"],
        },
      ]);

    render(<GodModePanel />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/Pending approvals queue fetch failed: (network error|network issue)\./);
    const queueBadge = screen.getByTestId("god-mode-queue-badge");
    expect(queueBadge).toHaveTextContent("Load failed");
    expect(queueBadge).not.toHaveTextContent("No pending items");
    expect(screen.getByRole("link", { name: "Open PM session to inspect connection" })).toHaveAttribute("href", "/pm");

    fireEvent.click(screen.getByRole("button", { name: "Retry fetch" }));

    await waitFor(() => {
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "I am done, continue" })).toBeInTheDocument();
    });
  });

  it("shows loading and explicit retry failure feedback for 403 on retry", async () => {
    const retryDeferred = createDeferred<Array<Record<string, JsonValue>>>();
    vi.mocked(fetchPendingApprovals).mockReset();
    vi.mocked(fetchPendingApprovals)
      .mockRejectedValueOnce(new Error("403 forbidden"))
      .mockImplementationOnce(() => retryDeferred.promise as Promise<any>);

    render(<GodModePanel />);

    await screen.findByRole("alert");
    fireEvent.click(screen.getByTestId("god-mode-retry-pending"));

    await waitFor(() => {
      expect(screen.getByTestId("god-mode-retry-pending")).toHaveTextContent("Retrying...");
      expect(screen.getByTestId("god-mode-retry-pending")).toBeDisabled();
      expect(screen.getByTestId("god-mode-loading-state")).toBeInTheDocument();
    });

    retryDeferred.reject(new Error("403 forbidden"));
    await waitFor(() => {
      expect(screen.queryByTestId("god-mode-status")).not.toBeInTheDocument();
      expect(screen.getByRole("alert")).toHaveTextContent(
        /Pending approval truth is unavailable: (permission|authentication|Authentication)/,
      );
      expect(screen.getByTestId("god-mode-last-attempt-at")).toHaveTextContent("Last attempt:");
    });
  });
});
