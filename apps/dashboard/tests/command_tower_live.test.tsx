import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import SessionTimeline from "../components/command-tower/SessionTimeline";

describe("command tower live timeline", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-02-09T10:00:00Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders empty timeline state", () => {
    render(<SessionTimeline events={[]} />);
    expect(screen.getByText("No session events yet")).toBeInTheDocument();
  });

  it("renders summary-first event cards with context details", () => {
    // Given: timeline events with sensitive context
    // When: render timeline cards
    // Then: summary/JSON are sanitized without breaking layout
    render(
      <SessionTimeline
        events={[
          {
            ts: "2026-02-09T09:59:30Z",
            event: "CHAIN_STEP_RESULT",
            run_id: "run-1",
            context: {
              message: "Bearer tok-123",
              status: "ok",
              tool: "search",
              cmd: "rg foo",
              token: "tok-123",
            },
          },
          {
            ts: "2026-02-09T09:58:00Z",
            event: "CHAIN_HANDOFF",
            run_id: "run-2",
            context: {
              alpha: 1,
              beta: true,
              gamma: [1],
            },
          },
          {
            ts: "bad-ts",
            event: "CUSTOM_EVENT",
            run_id: "run-3",
            context: {},
          },
        ]}
      />,
    );

    expect(screen.getByText(/summary: message=Bearer \[REDACTED\] \| status=ok \| tool=search/)).toBeInTheDocument();
    expect(screen.getByText(/summary: alpha=1 \| beta=true \| gamma=Array\(1\)/)).toBeInTheDocument();
    expect(screen.getByText(/summary: No context summary/)).toBeInTheDocument();
    expect(screen.getAllByText(/Expand context JSON/).length).toBeGreaterThan(0);
    expect(screen.getByText(/ts: bad-ts/)).toBeInTheDocument();
    expect(screen.getByText((content) => content.includes('"token": "[REDACTED]"'))).toBeInTheDocument();
    expect(screen.queryByText(/tok-123/)).not.toBeInTheDocument();
  });

  it("supports event_type/_ts/_run_id fallbacks and unknown event names", () => {
    render(
      <SessionTimeline
        events={[
          {
            _ts: "2026-02-09T09:59:20Z",
            event_type: "CHAIN_STEP_RESULT",
            _run_id: "run-fallback",
            context: { message: "fallback fields" },
          },
          {
            ts: "2026-02-09T09:59:10Z",
            event: "",
            event_type: "",
            run_id: "",
            context: { misc: "x" },
          },
        ]}
      />,
    );

    expect(screen.getByText("CHAIN_STEP_RESULT")).toBeInTheDocument();
    expect(screen.getByText(/run: run-fallback/)).toBeInTheDocument();
    expect(screen.getByText(/UNKNOWN_EVENT/)).toBeInTheDocument();
    expect(screen.getByText(/summary: misc=x/)).toBeInTheDocument();
  });

  it("renders relative time buckets across seconds/minutes/hours/days", () => {
    render(
      <SessionTimeline
        events={[
          {
            ts: "2026-02-09T09:59:58Z",
            event: "CHAIN_STARTED",
            run_id: "run-now",
            context: { summary: "now" },
          },
          {
            ts: "2026-02-09T09:59:30Z",
            event: "CHAIN_STARTED",
            run_id: "run-sec",
            context: { summary: "sec" },
          },
          {
            ts: "2026-02-09T09:55:00Z",
            event: "CHAIN_STARTED",
            run_id: "run-min",
            context: { summary: "min" },
          },
          {
            ts: "2026-02-09T08:00:00Z",
            event: "CHAIN_STARTED",
            run_id: "run-hour",
            context: { summary: "hour" },
          },
          {
            ts: "2026-02-07T10:00:00Z",
            event: "CHAIN_STARTED",
            run_id: "run-day",
            context: { summary: "day" },
          },
        ]}
      />,
    );

    expect(screen.getByText(/just now/)).toBeInTheDocument();
    expect(screen.getByText(/30s ago/)).toBeInTheDocument();
    expect(screen.getByText(/5m ago/)).toBeInTheDocument();
    expect(screen.getByText(/2h ago/)).toBeInTheDocument();
    expect(screen.getByText(/2d ago/)).toBeInTheDocument();
  });

  it("maps severity badges for error, warning, success and running events", () => {
    render(
      <SessionTimeline
        events={[
          {
            ts: "2026-02-09T09:59:00Z",
            event: "CHAIN_ERROR",
            run_id: "run-e",
            context: { message: "error" },
          },
          {
            ts: "2026-02-09T09:58:00Z",
            event: "HUMAN_APPROVAL_REQUIRED",
            run_id: "run-w",
            context: { message: "warn" },
          },
          {
            ts: "2026-02-09T09:57:00Z",
            event: "CHAIN_SUCCESS",
            run_id: "run-s",
            context: { message: "success" },
          },
          {
            ts: "2026-02-09T09:56:00Z",
            event: "CHAIN_STEP_STARTED",
            run_id: "run-r",
            context: { message: "running" },
          },
        ]}
      />,
    );

    expect(screen.getByText("CHAIN_ERROR")).toHaveClass("badge--failed");
    expect(screen.getByText("HUMAN_APPROVAL_REQUIRED")).toHaveClass("badge--warning");
    expect(screen.getByText("CHAIN_SUCCESS")).toHaveClass("badge--success");
    expect(screen.getByText("CHAIN_STEP_STARTED")).toHaveClass("badge--running");
  });
});
