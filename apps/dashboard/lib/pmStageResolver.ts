import type { PmJourneyContext, PmJourneyStage } from "./frontendApiContract";

type ResolvePmJourneyInput = {
  intakeId?: string;
  runId?: string;
  sessionStatus?: string;
  hasUserMessage?: boolean;
  hasEvidence?: boolean;
  questions?: string[];
};

const TERMINAL_STATUSES = new Set(["done", "failed", "archived"]);

export function stageLabel(stage: PmJourneyStage): string {
  if (stage === "discover") return "Discover";
  if (stage === "clarify") return "Clarify";
  if (stage === "execute") return "Execute";
  return "Verify";
}

export function resolvePmJourneyContext(input: ResolvePmJourneyInput): PmJourneyContext {
  const intakeId = String(input.intakeId || "").trim();
  const runId = String(input.runId || "").trim();
  const status = String(input.sessionStatus || "").trim().toLowerCase();
  const questions = Array.isArray(input.questions) ? input.questions.filter(Boolean) : [];
  const hasUserMessage = Boolean(input.hasUserMessage);
  const hasEvidence = Boolean(input.hasEvidence || runId);
  const isTerminal = TERMINAL_STATUSES.has(status);

  if (!intakeId && !hasUserMessage) {
    return {
      stage: "discover",
      reason: "No intake has been created yet, so the session is still in discovery.",
      primaryAction: "Send the first request",
      secondaryActions: ["Add acceptance criteria", "Confirm workspace binding"],
    };
  }

  if (questions.length > 0) {
    return {
      stage: "clarify",
      reason: `There are still ${questions.length} follow-up question${questions.length === 1 ? "" : "s"} waiting for confirmation.`,
      primaryAction: "Answer follow-up questions",
      secondaryActions: ["Clarify scope boundaries", "Confirm success criteria"],
    };
  }

  if (isTerminal && hasEvidence) {
    return {
      stage: "verify",
      reason: "The run reached a terminal state and results are ready for review.",
      primaryAction: "Review results and decide",
      secondaryActions: ["Inspect replay evidence", "Decide whether to retry or archive"],
    };
  }

  return {
    stage: "execute",
    reason: runId
      ? "Execution has started. Monitor live progress and exceptions."
      : "Key inputs are ready. Execution can start.",
    primaryAction: runId ? "Monitor execution progress" : "Send /run to start execution",
    secondaryActions: ["Track the Command Chain", "Add constraints when needed"],
  };
}
