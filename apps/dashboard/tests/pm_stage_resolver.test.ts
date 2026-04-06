import { describe, expect, it } from "vitest";

import { resolvePmJourneyContext } from "../lib/pmStageResolver";

describe("pm stage resolver", () => {
  it("returns discover when intake is missing and no user message", () => {
    const context = resolvePmJourneyContext({
      intakeId: "",
      hasUserMessage: false,
      questions: [],
    });
    expect(context.stage).toBe("discover");
    expect(context.primaryAction).toContain("Send the first request");
  });

  it("returns clarify when pending questions exist", () => {
    const context = resolvePmJourneyContext({
      intakeId: "pm-1",
      questions: ["Please add acceptance criteria"],
      hasUserMessage: true,
    });
    expect(context.stage).toBe("clarify");
    expect(context.primaryAction).toContain("Answer follow-up questions");
  });

  it("returns execute when no pending question and session not terminal", () => {
    const context = resolvePmJourneyContext({
      intakeId: "pm-1",
      runId: "run-1",
      sessionStatus: "active",
      questions: [],
      hasUserMessage: true,
      hasEvidence: true,
    });
    expect(context.stage).toBe("execute");
  });

  it("returns verify when terminal status has evidence", () => {
    const context = resolvePmJourneyContext({
      intakeId: "pm-1",
      runId: "run-1",
      sessionStatus: "done",
      questions: [],
      hasUserMessage: true,
      hasEvidence: true,
    });
    expect(context.stage).toBe("verify");
    expect(context.primaryAction).toContain("decide");
  });
});
