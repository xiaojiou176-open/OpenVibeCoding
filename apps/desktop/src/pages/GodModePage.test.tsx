import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { GodModePage } from "./GodModePage";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock("../lib/api", () => ({
  fetchPendingApprovals: vi.fn(),
  approveGodMode: vi.fn(),
}));

import { fetchPendingApprovals, approveGodMode } from "../lib/api";
import { toast } from "sonner";

describe("GodModePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchPendingApprovals).mockResolvedValue([] as any);
    vi.mocked(approveGodMode).mockResolvedValue({ ok: true } as any);
  });

  it("shows load error then recovers after refresh", async () => {
    vi.mocked(fetchPendingApprovals)
      .mockRejectedValueOnce(new Error("queue unavailable"))
      .mockResolvedValueOnce([] as any);

    const user = userEvent.setup();
    render(<GodModePage />);

    expect(await screen.findByText(/queue unavailable/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Refresh" }));

    await waitFor(() => {
      expect(screen.queryByText(/queue unavailable/i)).not.toBeInTheDocument();
    });
    expect(fetchPendingApprovals).toHaveBeenCalledTimes(2);
  });

  it("approves from confirm dialog and handles focus trap + escape", async () => {
    vi.mocked(fetchPendingApprovals).mockResolvedValueOnce([
      { run_id: "run-001", task_id: "task-001", failure_reason: "needs approval" },
    ] as any);

    const user = userEvent.setup();
    render(<GodModePage />);

    const openButton = await screen.findByRole("button", { name: "Approve execution" });
    openButton.focus();
    await user.click(openButton);

    const cancelButton = screen.getByRole("button", { name: "Cancel" });
    const confirmButton = screen.getByRole("button", { name: "Confirm approval" });

    expect(cancelButton).toHaveFocus();
    await user.keyboard("{Tab}");
    expect(confirmButton).toHaveFocus();
    await user.keyboard("{Tab}");
    expect(cancelButton).toHaveFocus();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Approval confirmation dialog" })).not.toBeInTheDocument();
    expect(openButton).toHaveFocus();

    await user.click(openButton);
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog", { name: "Approval confirmation dialog" })).not.toBeInTheDocument();
    expect(openButton).toHaveFocus();

    await user.click(openButton);
    await user.click(screen.getByRole("button", { name: "Confirm approval" }));

    await waitFor(() => {
      expect(approveGodMode).toHaveBeenCalledWith("run-001");
      expect(toast.success).toHaveBeenCalledWith("Approved run-001");
    });
    expect(screen.queryByRole("dialog", { name: "Approval confirmation dialog" })).not.toBeInTheDocument();
  });

  it("surfaces approve error in confirm flow", async () => {
    vi.mocked(fetchPendingApprovals).mockResolvedValueOnce([{ run_id: "run-err" }] as any);
    vi.mocked(approveGodMode).mockRejectedValueOnce(new Error("approve failed"));

    const user = userEvent.setup();
    render(<GodModePage />);

    await user.click(await screen.findByRole("button", { name: "Approve execution" }));
    await user.click(screen.getByRole("button", { name: "Confirm approval" }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("approve failed");
    });
  });

  it("supports manual approve success and failure", async () => {
    const user = userEvent.setup();
    vi.mocked(approveGodMode)
      .mockResolvedValueOnce({ ok: true } as any)
      .mockRejectedValueOnce(new Error("manual failed"));

    render(<GodModePage />);
    const input = await screen.findByLabelText("Run ID");

    await user.type(input, "  run-manual  ");
    await user.keyboard("{Enter}");

    await waitFor(() => {
      expect(approveGodMode).toHaveBeenCalledWith("run-manual");
      expect(screen.getByText("Approved run-manual")).toBeInTheDocument();
    });
    expect(input).toHaveValue("");

    await user.type(input, "run-manual-fail");
    await user.click(screen.getByRole("button", { name: "Approve" }));

    await waitFor(() => {
      expect(approveGodMode).toHaveBeenCalledWith("run-manual-fail");
      expect(screen.getByText("manual failed")).toBeInTheDocument();
    });
  });
});
