import { describe, expect, it } from "vitest";

import {
  classifyErrorMessage,
  homeLiveBadgeText,
} from "../components/command-tower/CommandTowerHomeLive";
import {
  alertsBadgeVariant,
  homeLiveBadgeVariant,
  sectionStatusBadgeVariant,
  sectionStatusLabel,
} from "../components/command-tower/commandTowerHomeHelpers";
import {
  classifyError,
  errorKindLabel,
  eventFingerprint,
  eventName,
  eventTsValue,
  extractErrorMessage,
  isTerminalStatus,
  lastEventTs,
  mergeEventWindow,
  sessionLiveBadgeVariant,
  sessionLiveBadgeText,
} from "../components/command-tower/CommandTowerSessionLive";
import type { EventRecord } from "../lib/types";

describe("Command Tower helper functions", () => {
  it("classifies home-level error messages", () => {
    expect(classifyErrorMessage("Failed to fetch upstream")).toEqual({
      type: "network",
      label: "Network issue",
    });
    expect(classifyErrorMessage("token expired with 401")).toEqual({
      type: "auth",
      label: "Auth issue",
    });
    expect(classifyErrorMessage("internal panic")).toEqual({
      type: "server",
      label: "Service issue",
    });

    expect(homeLiveBadgeVariant("backoff")).toBe("failed");
    expect(homeLiveBadgeVariant("paused")).toBe("warning");
    expect(homeLiveBadgeVariant("running")).toBe("running");
    expect(homeLiveBadgeText("paused")).toBe("Paused");
    expect(homeLiveBadgeText("backoff")).toBe("Backoff");
    expect(homeLiveBadgeText("running")).toBe("Live");

    expect(alertsBadgeVariant("critical")).toBe("failed");
    expect(alertsBadgeVariant("degraded")).toBe("warning");
    expect(alertsBadgeVariant("healthy")).toBe("running");
    expect(sectionStatusBadgeVariant("ok")).toBe("success");
    expect(sectionStatusBadgeVariant("error")).toBe("failed");
    expect(sectionStatusLabel("ok")).toBe("Healthy");
    expect(sectionStatusLabel("error")).toBe("Issue");
  });

  it("covers session event primitives", () => {
    const eventA: EventRecord = {
      ts: "2026-02-09T09:59:00Z",
      event: "CHAIN_STEP_STARTED",
      run_id: "run-1",
      context: { step: "plan" },
    };
    const eventB: EventRecord = {
      _ts: "2026-02-09T09:59:01Z",
      event_type: "CHAIN_STEP_RESULT",
      _run_id: "run-2",
      context: { status: "ok" },
    };
    const eventC: EventRecord = {
      event: "",
      event_type: "",
      context: undefined,
    };

    expect(eventTsValue(eventA)).toBe("2026-02-09T09:59:00Z");
    expect(eventTsValue(eventB)).toBe("2026-02-09T09:59:01Z");
    expect(eventTsValue(eventC)).toBe("");

    expect(lastEventTs([])).toBe("");
    expect(lastEventTs([eventA, eventB])).toBe("2026-02-09T09:59:01Z");

    expect(eventName(eventA)).toBe("CHAIN_STEP_STARTED");
    expect(eventName(eventB)).toBe("CHAIN_STEP_RESULT");
    expect(eventName(eventC)).toBe("UNKNOWN_EVENT");

    expect(eventFingerprint(eventA)).toContain("CHAIN_STEP_STARTED");
    expect(eventFingerprint(eventB)).toContain("run-2");
    expect(eventFingerprint(eventC)).toContain("UNKNOWN_EVENT");
  });

  it("covers mergeEventWindow dedupe, sort and window slicing", () => {
    const existing: EventRecord[] = [
      { ts: "2026-02-09T09:59:00Z", event: "A", run_id: "run-1", context: { v: 1 } },
      { ts: "2026-02-09T09:59:01Z", event: "B", run_id: "run-1", context: { v: 2 } },
    ];

    const incoming: EventRecord[] = [
      { ts: "2026-02-09T09:59:01Z", event: "B", run_id: "run-1", context: { v: 2 } },
      { ts: "2026-02-09T09:59:02Z", event: "C", run_id: "run-1", context: { v: 3 } },
    ];

    const merged = mergeEventWindow(existing, incoming);
    expect(merged.length).toBe(3);
    expect(String(merged[0]?.event)).toBe("A");
    expect(String(merged[2]?.event)).toBe("C");

    const huge = Array.from({ length: 810 }, (_, index) => ({
      ts: `2026-02-09T09:${String(Math.floor(index / 60)).padStart(2, "0")}:${String(index % 60).padStart(2, "0")}Z`,
      event: `E-${index}`,
      run_id: "run-huge",
      context: {},
    })) as EventRecord[];

    const trimmed = mergeEventWindow(huge, []);
    expect(trimmed.length).toBe(800);
    expect(String(trimmed[0]?.event)).toBe("E-10");

    const base = Array.from({ length: 790 }, (_, index) => ({
      ts: `2026-02-09T10:${String(Math.floor(index / 60)).padStart(2, "0")}:${String(index % 60).padStart(2, "0")}Z`,
      event: `B-${index}`,
      run_id: "run-base",
      context: {},
    })) as EventRecord[];
    const incomingLarge = Array.from({ length: 40 }, (_, index) => ({
      ts: `2026-02-09T11:${String(Math.floor(index / 60)).padStart(2, "0")}:${String(index % 60).padStart(2, "0")}Z`,
      event: `N-${index}`,
      run_id: "run-base",
      context: {},
    })) as EventRecord[];
    const trimmedAfterMerge = mergeEventWindow(base, incomingLarge);
    expect(trimmedAfterMerge.length).toBe(800);
    expect(String(trimmedAfterMerge[0]?.event)).toBe("B-30");
  });

  it("covers terminal status and error helpers", () => {
    expect(isTerminalStatus("done")).toBe(true);
    expect(isTerminalStatus("FAILED")).toBe(true);
    expect(isTerminalStatus("archived")).toBe(true);
    expect(isTerminalStatus("active")).toBe(false);
    expect(isTerminalStatus(undefined as unknown as string)).toBe(false);

    expect(extractErrorMessage(new Error("boom"))).toBe("boom");
    expect(extractErrorMessage("plain-text")).toBe("plain-text");
    expect(extractErrorMessage(undefined)).toBe("unknown error");

    expect(classifyError("request timeout")).toBe("network");
    expect(classifyError("401 unauthorized")).toBe("auth");
    expect(classifyError("503 server unavailable")).toBe("server");
    expect(classifyError("unexpected shape")).toBe("unknown");
    expect(classifyError("" as string)).toBe("unknown");

    expect(errorKindLabel("network")).toBe("Network error");
    expect(errorKindLabel("auth")).toBe("Auth error");
    expect(errorKindLabel("server")).toBe("Service error");
    expect(errorKindLabel("unknown")).toBe("Unknown error");

    expect(sessionLiveBadgeVariant("backoff")).toBe("failed");
    expect(sessionLiveBadgeVariant("running")).toBe("running");
    expect(sessionLiveBadgeText("paused")).toBe("Paused");
    expect(sessionLiveBadgeText("stopped")).toBe("Stopped");
    expect(sessionLiveBadgeText("backoff")).toBe("Backoff");
    expect(sessionLiveBadgeText("running")).toBe("Live");
  });
});
