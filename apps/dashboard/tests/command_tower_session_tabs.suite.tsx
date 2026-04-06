import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  baseEvents,
  baseGraph,
  baseMetrics,
  baseSessionDetail,
  getCommandTowerAsyncMocks,
  setupCommandTowerAsyncDefaultMocks,
  teardownCommandTowerAsyncMocks,
} from "./command_tower_async.shared";
import CommandTowerSessionLive from "../components/command-tower/CommandTowerSessionLive";

describe("command tower session tabs", () => {
  const mocks = getCommandTowerAsyncMocks();

  beforeEach(() => {
    setupCommandTowerAsyncDefaultMocks(mocks);
  });

  afterEach(() => {
    teardownCommandTowerAsyncMocks();
  });

  it("switches between run/table, graph and timeline panels", () => {
    render(
      <CommandTowerSessionLive
        pmSessionId="pm-tabs"
        initialDetail={baseSessionDetail("active", "run-tabs")}
        initialEvents={baseEvents()}
        initialGraph={baseGraph()}
        initialMetrics={baseMetrics()}
      />,
    );

    const runsPanel = screen.getByTestId("ct-session-panel-runs");

    expect(runsPanel).toBeVisible();
    expect(screen.queryByTestId("ct-session-panel-graph")).toBeNull();
    expect(screen.queryByTestId("ct-session-panel-timeline")).toBeNull();

    fireEvent.click(screen.getByTestId("ct-session-tab-graph"));
    expect(screen.getByTestId("ct-session-panel-graph")).toBeVisible();
    expect(screen.queryByTestId("ct-session-panel-runs")).toBeNull();

    fireEvent.click(screen.getByTestId("ct-session-tab-timeline"));
    expect(screen.getByTestId("ct-session-panel-timeline")).toBeVisible();
    expect(screen.queryByTestId("ct-session-panel-graph")).toBeNull();

    fireEvent.click(screen.getByTestId("ct-session-tab-runs"));
    expect(screen.getByTestId("ct-session-panel-runs")).toBeVisible();
    expect(screen.queryByTestId("ct-session-panel-timeline")).toBeNull();
  });

  it("supports tab keyboard navigation with ArrowLeft/ArrowRight/Home/End", () => {
    render(
      <CommandTowerSessionLive
        pmSessionId="pm-tabs-keyboard"
        initialDetail={baseSessionDetail("active", "run-tabs-keyboard")}
        initialEvents={baseEvents()}
        initialGraph={baseGraph()}
        initialMetrics={baseMetrics()}
      />,
    );

    const runsTab = screen.getByTestId("ct-session-tab-runs");
    const graphTab = screen.getByTestId("ct-session-tab-graph");
    const timelineTab = screen.getByTestId("ct-session-tab-timeline");

    runsTab.focus();
    expect(runsTab).toHaveFocus();
    expect(runsTab).toHaveAttribute("aria-selected", "true");

    fireEvent.keyDown(runsTab, { key: "ArrowRight" });
    expect(graphTab).toHaveFocus();
    expect(graphTab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("ct-session-panel-graph")).toBeVisible();

    fireEvent.keyDown(graphTab, { key: "End" });
    expect(timelineTab).toHaveFocus();
    expect(timelineTab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("ct-session-panel-timeline")).toBeVisible();

    fireEvent.keyDown(timelineTab, { key: "Home" });
    expect(runsTab).toHaveFocus();
    expect(runsTab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("ct-session-panel-runs")).toBeVisible();

    fireEvent.keyDown(runsTab, { key: "ArrowLeft" });
    expect(timelineTab).toHaveFocus();
    expect(timelineTab).toHaveAttribute("aria-selected", "true");
  });

  it("shows disabled run detail action when latest run is missing", async () => {
    mocks.mockFetchPmSession.mockResolvedValue(baseSessionDetail("active", ""));
    render(
      <CommandTowerSessionLive
        pmSessionId="pm-tabs-missing-run"
        initialDetail={baseSessionDetail("active", "")}
        initialEvents={baseEvents()}
        initialGraph={baseGraph()}
        initialMetrics={baseMetrics()}
      />,
    );

    fireEvent.click(screen.getByTestId("ct-session-open-run-detail-trigger"));
    const state = screen.getByTestId("ct-session-run-detail-state");
    await waitFor(() => expect(state).toHaveAttribute("data-state", "empty"));
    expect(screen.getByTestId("ct-session-run-detail-state-message")).toHaveTextContent("There is no run detail available for this session yet.");
    const pmActionLink = screen.getByRole("link", { name: "Go to the PM session and trigger /run" });
    expect(pmActionLink).toHaveAccessibleName("Go to the PM session and trigger /run");
    expect(pmActionLink).toHaveAttribute("href", "/pm");
    expect(pmActionLink).toHaveAttribute("data-testid", "ct-session-open-run-detail-next-action");
    fireEvent.click(pmActionLink);
    expect(screen.queryByRole("link", { name: "Open run detail" })).toBeNull();
  });

  it("allows retrying run detail lookup after transient failure", async () => {
    mocks.mockFetchPmSession
      .mockRejectedValueOnce(new Error("fetch failed"))
      .mockResolvedValueOnce(baseSessionDetail("active", ""));

    render(
      <CommandTowerSessionLive
        pmSessionId="pm-tabs-retry"
        initialDetail={baseSessionDetail("active", "")}
        initialEvents={baseEvents()}
        initialGraph={baseGraph()}
        initialMetrics={baseMetrics()}
      />,
    );

    fireEvent.click(screen.getByTestId("ct-session-open-run-detail-trigger"));
    await waitFor(() =>
      expect(screen.getByTestId("ct-session-run-detail-state")).toHaveAttribute("data-state", "error"),
    );
    fireEvent.click(screen.getByTestId("ct-session-open-run-detail-retry"));
    await waitFor(() =>
      expect(screen.getByTestId("ct-session-run-detail-state")).toHaveAttribute("data-state", "empty"),
    );
    expect(screen.getByRole("link", { name: "Go to the PM session and trigger /run" })).toHaveAttribute("href", "/pm");
  });

  it("opens run detail link with encoded run id when latest run exists", async () => {
    mocks.mockFetchPmSession.mockResolvedValue(baseSessionDetail("active", "run/ready 1"));

    render(
      <CommandTowerSessionLive
        pmSessionId="pm-tabs-ready-run"
        initialDetail={baseSessionDetail("active", "")}
        initialEvents={baseEvents()}
        initialGraph={baseGraph()}
        initialMetrics={baseMetrics()}
      />,
    );

    fireEvent.click(screen.getByTestId("ct-session-open-run-detail-trigger"));
    await waitFor(() =>
      expect(screen.getByTestId("ct-session-run-detail-state")).toHaveAttribute("data-state", "ready"),
    );
    const runDetailLink = screen.getByRole("link", { name: "Open run detail" });
    expect(runDetailLink).toHaveAccessibleName("Open run detail");
    expect(runDetailLink).toHaveAttribute("href", "/runs/run%2Fready%201");
    expect(runDetailLink).toHaveAttribute("data-run-id", "run/ready 1");
    expect(runDetailLink).toHaveAttribute("title", "run/ready 1");
    expect(runDetailLink).toHaveAttribute("data-testid", "ct-session-open-run-detail-ready-link");
    fireEvent.click(runDetailLink);
    expect(screen.queryByRole("link", { name: "Go to the PM session and trigger /run" })).toBeNull();
  });
});
