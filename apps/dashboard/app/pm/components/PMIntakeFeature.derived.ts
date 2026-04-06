import type { PMCopyVariant } from "./PMIntakeFeature.shared";

export function resolveHeaderHint(params: {
  workspaceBound: boolean;
  intakeId: string;
  questionsLength: number;
  runId: string;
}): string {
  const { workspaceBound, intakeId, questionsLength, runId } = params;
  if (!workspaceBound) {
    return "Bind Workspace and Repo first, then I will start moving immediately.";
  }
  if (!intakeId) {
    return "I will turn this request into a session automatically.";
  }
  if (questionsLength > 0) {
    return `Answer the remaining ${questionsLength} clarifiers to keep moving.`;
  }
  if (runId) {
    return "Execution is live. Ask for progress or add constraints at any time.";
  }
  return "Type /run when you're ready.";
}

export function resolveFirstRunStage(params: {
  workspaceBound: boolean;
  intakeId: string;
  questionsLength: number;
  runId: string;
}): string {
  const { workspaceBound, intakeId, questionsLength, runId } = params;
  if (!workspaceBound) {
    return "Current next step: fill in the workspace binding";
  }
  if (!intakeId) {
    return "Current next step: send the first request (enter it first)";
  }
  if (questionsLength > 0) {
    return `Current next step: answer clarifiers (${questionsLength} remaining)`;
  }
  if (runId) {
    return "Current next step: review the latest progress";
  }
  return "Current next step: type /run to start execution";
}

export function resolveFirstRunNextCta(params: {
  workspaceBound: boolean;
  intakeId: string;
  questionsLength: number;
  runId: string;
}): string {
  const { workspaceBound, intakeId, questionsLength, runId } = params;
  if (!workspaceBound) {
    return "Next: fill in the workspace binding";
  }
  if (!intakeId) {
    return "Next: send the first request";
  }
  if (questionsLength > 0) {
    return "Next: answer clarifiers";
  }
  if (runId) {
    return "Next: review the current progress";
  }
  return "Next: start execution with /run";
}

export function resolveChatPlaceholder(params: {
  copyVariant: PMCopyVariant;
  workspaceBound: boolean;
  intakeId: string;
  questionsLength: number;
  chatFlowBusy: boolean;
  currentSessionStatus: string;
  runId: string;
}): string {
  const { copyVariant, workspaceBound, intakeId, questionsLength, chatFlowBusy, currentSessionStatus, runId } = params;
  if (!workspaceBound) {
    return copyVariant === "b" ? "Fill in Workspace and Repo on the left first..." : "Fill in the Workspace and Repo fields on the left first...";
  }
  if (!intakeId) {
    return copyVariant === "b"
      ? "Start with the goal and acceptance criteria, e.g. add homepage onboarding and pass the existing tests"
      : "Enter a request (recommended: goal + acceptance criteria), e.g. add homepage onboarding and pass the existing tests...";
  }
  if (questionsLength > 0) {
    return copyVariant === "b" ? "Answer the current clarifier first. Add detail if needed..." : "Answer the current clarifying question first. Add detail if needed...";
  }
  if (chatFlowBusy) {
    return copyVariant === "b" ? "Working on it. You can still add more detail..." : "Working on it. You can keep adding more detail...";
  }
  if (currentSessionStatus.toLowerCase() === "failed") {
    return copyVariant === "b" ? "Ask for a retry, or tell CortexPilot exactly what to change..." : "Ask for a retry, or tell CortexPilot what to change...";
  }
  if (runId) {
    return "Execution is in progress. Ask for status or add a new requirement...";
  }
  return copyVariant === "b"
    ? "Type /run when you're ready, or keep adding requirements"
    : "Type /run to start execution, or keep adding requirements...";
}

export function resolvePmStageText(params: {
  chatBusy: boolean;
  busy: boolean;
  chatHistoryBusy: boolean;
  intakeId: string;
  questionsLength: number;
  liveRole: string;
  runId: string;
}): string {
  const { chatBusy, busy, chatHistoryBusy, intakeId, questionsLength, liveRole, runId } = params;
  if (chatBusy) {
    return "Reading your request...";
  }
  if (busy) {
    return "Preparing the execution plan...";
  }
  if (chatHistoryBusy) {
    return "Syncing this session...";
  }
  if (!intakeId) {
    return "Waiting for your first message...";
  }
  if (questionsLength > 0) {
    return "Waiting for your clarification...";
  }
  const normalizedRole = liveRole.trim().toUpperCase();
  if (normalizedRole === "TECH_LEAD") {
    return "TL is breaking down the work...";
  }
  if (normalizedRole === "WORKER") {
    return "Worker is executing...";
  }
  if (normalizedRole === "REVIEWER") {
    return "Running quality review...";
  }
  if (normalizedRole === "TEST_RUNNER") {
    return "Running regression validation...";
  }
  if (runId) {
    return "Preparing the result handoff...";
  }
  return "Preparing the next step...";
}
