import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { DiffReviewModal } from "./DiffReviewModal";

function renderModal(
  reviewDecision: "pending" | "accepted" | "rework" = "pending",
  open = true,
  onClose = vi.fn(),
  onAccept = vi.fn(),
  onRework = vi.fn()
) {
  render(
    <DiffReviewModal
      open={open}
      reviewDecision={reviewDecision}
      onClose={onClose}
      onAccept={onAccept}
      onRework={onRework}
    />
  );
  return { onClose, onAccept, onRework };
}

describe("DiffReviewModal", () => {
  it("does not render dialog when closed", () => {
    renderModal("pending", false);
    expect(screen.queryByRole("dialog", { name: "Diff Review" })).not.toBeInTheDocument();
  });

  it("renders decision text and actions, then dispatches accept/rework callbacks", () => {
    const { onAccept, onRework } = renderModal("accepted");
    expect(screen.getByText("Default policy: review before merge. Current status: Accepted.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Accept and merge" }));
    fireEvent.click(screen.getByRole("button", { name: "Request changes" }));

    expect(onAccept).toHaveBeenCalledTimes(1);
    expect(onRework).toHaveBeenCalledTimes(1);
  });

  it("closes on Escape and keeps focus trapped on Tab cycles", async () => {
    const user = userEvent.setup();
    const { onClose } = renderModal("rework");
    expect(screen.getByText("Default policy: review before merge. Current status: Changes requested.")).toBeInTheDocument();

    const closeButton = screen.getByRole("button", { name: "Close diff review" });
    const acceptButton = screen.getByRole("button", { name: "Accept and merge" });
    const reworkButton = screen.getByRole("button", { name: "Request changes" });

    closeButton.focus();
    await user.tab({ shift: true });
    expect(document.activeElement).toBe(reworkButton);

    reworkButton.focus();
    await user.tab();
    expect(document.activeElement).toBe(closeButton);

    closeButton.focus();
    await user.tab();
    expect(document.activeElement).toBe(acceptButton);

    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("restores focus to previous trigger on unmount", async () => {
    const trigger = document.createElement("button");
    trigger.textContent = "open-diff";
    document.body.appendChild(trigger);
    trigger.focus();

    const { unmount } = render(
      <DiffReviewModal
        open
        reviewDecision="pending"
        onClose={vi.fn()}
        onAccept={vi.fn()}
        onRework={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "Close diff review" })).toHaveFocus();
    unmount();
    await waitFor(() => {
      expect(trigger).toHaveFocus();
    });
    trigger.remove();
  });

  it("does not restore focus while open when onClose reference changes", async () => {
    const trigger = document.createElement("button");
    trigger.textContent = "open-diff";
    document.body.appendChild(trigger);
    trigger.focus();

    const firstOnClose = vi.fn();
    const { rerender } = render(
      <DiffReviewModal
        open
        reviewDecision="pending"
        onClose={firstOnClose}
        onAccept={vi.fn()}
        onRework={vi.fn()}
      />,
    );
    const closeButton = screen.getByRole("button", { name: "Close diff review" });
    expect(closeButton).toHaveFocus();

    rerender(
      <DiffReviewModal
        open
        reviewDecision="pending"
        onClose={vi.fn()}
        onAccept={vi.fn()}
        onRework={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(closeButton).toHaveFocus();
      expect(trigger).not.toHaveFocus();
    });
    trigger.remove();
  });

  it("uses latest onClose callback when Escape is pressed after rerender", () => {
    const firstOnClose = vi.fn();
    const secondOnClose = vi.fn();
    const { rerender } = render(
      <DiffReviewModal
        open
        reviewDecision="pending"
        onClose={firstOnClose}
        onAccept={vi.fn()}
        onRework={vi.fn()}
      />,
    );

    rerender(
      <DiffReviewModal
        open
        reviewDecision="pending"
        onClose={secondOnClose}
        onAccept={vi.fn()}
        onRework={vi.fn()}
      />,
    );

    fireEvent.keyDown(window, { key: "Escape" });
    expect(firstOnClose).not.toHaveBeenCalled();
    expect(secondOnClose).toHaveBeenCalledTimes(1);
  });
});
