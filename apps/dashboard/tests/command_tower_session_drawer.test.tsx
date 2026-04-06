import { createRef, type ComponentProps } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import CommandTowerSessionDrawer from "../components/command-tower/CommandTowerSessionDrawer";
import type { PmSessionDetailPayload } from "../lib/types";

function buildProps(
  overrides: Partial<ComponentProps<typeof CommandTowerSessionDrawer>> = {},
): ComponentProps<typeof CommandTowerSessionDrawer> {
  return {
    drawerCollapsed: false,
    drawerPinned: true,
    sessionDrawerFeedbackId: "drawer-feedback-id",
    sessionDrawerStatusId: "drawer-status-id",
    sessionMetricsRegionId: "metrics-region-id",
    sessionRunsRegionId: "runs-region-id",
    sessionTimelineRegionId: "timeline-region-id",
    sessionMainRegionId: "main-region-id",
    sessionMessageInputId: "message-input-id",
    sessionMessageHintId: "message-hint-id",
    liveMode: "running",
    liveEnabled: true,
    handleToggleLive: vi.fn(),
    handleManualRefresh: vi.fn().mockResolvedValue(undefined),
    refreshing: false,
    focusMessageComposer: vi.fn(),
    setDrawerCollapsed: vi.fn(),
    setDrawerPinned: vi.fn(),
    drawerActionFeedback: "Drawer ready",
    transportLabel: "SSE",
    transportDescription: "Prefer SSE, fallback to polling",
    refreshIntervalMs: 1500,
    sseFailures: 1,
    lastUpdated: "2026-02-28T12:34:56Z",
    liveModeLabel: "Live refresh active",
    liveAnnouncement: "Live refresh enabled",
    errorMessage: "",
    errorKind: "unknown",
    sessionStatus: "running",
    contextRunCount: 1,
    contextBlockedRuns: 0,
    contextLastEventTs: "2026-02-28T12:34:56Z",
    contextLatestRun: "run/latest",
    messageInputRef: createRef<HTMLTextAreaElement>(),
    messageDraft: "",
    setMessageDraft: vi.fn(),
    handleSendMessage: vi.fn().mockResolvedValue(undefined),
    messageSending: false,
    messageOk: "",
    messageError: "",
    detail: {
      runs: [{ run_id: "run/latest" }],
    } as unknown as PmSessionDetailPayload,
    ...overrides,
  };
}

describe("CommandTowerSessionDrawer", () => {
  it("renders collapsed mode with persistent controls and accessibility states", () => {
    const props = buildProps({ drawerCollapsed: true, liveEnabled: false });
    render(<CommandTowerSessionDrawer {...props} />);

    expect(screen.getByTestId("ct-session-context-drawer")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Resume live refresh" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: "Expand drawer" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByRole("heading", { name: "Live status" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "PM session chat" })).not.toBeInTheDocument();
  });

  it("covers error and no-run branches and supports manual refresh trigger", async () => {
    const handleManualRefresh = vi.fn().mockRejectedValue(new Error("manual refresh failed"));
    const props = buildProps({
      errorMessage: "server 500",
      errorKind: "server",
      contextLatestRun: "",
      detail: { runs: [] } as unknown as PmSessionDetailPayload,
      handleManualRefresh,
    });

    render(<CommandTowerSessionDrawer {...props} />);

    fireEvent.click(screen.getByRole("button", { name: "Manual refresh" }));
    await waitFor(() => expect(handleManualRefresh).toHaveBeenCalledTimes(1));

    expect(screen.getByRole("alert")).toHaveTextContent("Error type: Service error");
    expect(screen.getByText("No runs available to jump to")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Jump to latest run" })).not.toBeInTheDocument();
  });

  it("sends message on Enter and keeps Shift+Enter for newline", async () => {
    const handleSendMessage = vi.fn().mockResolvedValue(undefined);
    const focusMessageComposer = vi.fn();
    const setMessageDraft = vi.fn();
    const setDrawerCollapsed = vi.fn();
    const setDrawerPinned = vi.fn();
    const props = buildProps({ handleSendMessage, focusMessageComposer, setMessageDraft });
    props.setDrawerCollapsed = setDrawerCollapsed;
    props.setDrawerPinned = setDrawerPinned;

    render(<CommandTowerSessionDrawer {...props} />);

    fireEvent.click(screen.getByRole("button", { name: "Focus PM message input" }));
    expect(focusMessageComposer).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "Collapse drawer" }));
    fireEvent.click(screen.getByRole("button", { name: "Unpin drawer" }));
    expect(setDrawerCollapsed).toHaveBeenCalledTimes(1);
    expect(setDrawerPinned).toHaveBeenCalledTimes(1);

    const input = screen.getByRole("textbox", { name: "PM session message input" });
    fireEvent.change(input, { target: { value: "hello" } });
    expect(setMessageDraft).toHaveBeenCalled();

    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => expect(handleSendMessage).toHaveBeenCalledTimes(1));

    fireEvent.keyDown(input, { key: "Enter", shiftKey: true });
    expect(handleSendMessage).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "Send to session" }));
    await waitFor(() => expect(handleSendMessage).toHaveBeenCalledTimes(2));
  });

  it("renders message sending, success and error signals", () => {
    render(
      <CommandTowerSessionDrawer
        {...buildProps({
          messageSending: true,
          messageOk: "Message sent",
          messageError: "Send failed",
        })}
      />,
    );

    expect(screen.getByRole("button", { name: "Sending..." })).toBeDisabled();
    expect(screen.getByText("Message sent")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Send failed");
  });
});
