import {
  answerIntake,
  createIntake,
  postPmSessionMessage,
  runIntake,
} from "../../../lib/api";
import type { JsonValue } from "../../../lib/types";
import {
  asString,
  asStringArray,
  isRequestAborted,
  PM_INTAKE_REQUEST_TIMEOUT_MS,
  sanitizeErrorMessage,
  type ChatCardPayload,
  type ChatItemKind,
  type ChatRole,
} from "./PMIntakeFeature.shared";

type AppendChatOptions = {
  kind?: ChatItemKind;
  card?: ChatCardPayload;
  createdAt?: string;
  origin?: "local" | "remote";
};

type RunChatSendFlowParams = {
  chatInput: string;
  chatFlowBusy: boolean;
  intakeId: string;
  runId: string;
  activeChatSessionId: string;
  questions: string[];
  effectiveBrowserPolicy: unknown;
  chatAbortRef: { current: AbortController | null };
  buildIntakePayload: (objective: string) => Record<string, JsonValue>;
  syncIntakeResult: (response: Record<string, JsonValue>) => { nextIntakeId: string; nextQuestions: string[] };
  moveDraftChatToSession: (sessionId: string) => void;
  appendChat: (role: ChatRole, text: string, sessionId: string, options?: AppendChatOptions) => void;
  refreshSessionHistory: () => void;
  setObjective: (value: string) => void;
  setRunId: (value: string) => void;
  setQuestions: (value: string[]) => void;
  setPlan: (value: unknown) => void;
  setTaskChain: (value: unknown) => void;
  setEffectiveBrowserPolicy: (value: unknown) => void;
  setChatInput: (value: string) => void;
  setChatBusy: (value: boolean) => void;
  setChatError: (value: string) => void;
  setChatNotice: (value: string) => void;
  logError: (message: string) => void;
};

export async function runChatSendFlow(params: RunChatSendFlowParams): Promise<void> {
  const {
    chatInput,
    chatFlowBusy,
    intakeId,
    runId,
    activeChatSessionId,
    questions,
    effectiveBrowserPolicy,
    chatAbortRef,
    buildIntakePayload,
    syncIntakeResult,
    moveDraftChatToSession,
    appendChat,
    refreshSessionHistory,
    setObjective,
    setRunId,
    setQuestions,
    setPlan,
    setTaskChain,
    setEffectiveBrowserPolicy,
    setChatInput,
    setChatBusy,
    setChatError,
    setChatNotice,
    logError,
  } = params;

  const message = chatInput.trim();
  if (!message || chatFlowBusy) {
    return;
  }

  const targetSessionId = intakeId || activeChatSessionId;
  appendChat("PM", message, targetSessionId, { kind: "message" });
  setChatInput("");
  setChatBusy(true);
  setChatError("");
  setChatNotice("");

  const controller = new AbortController();
  chatAbortRef.current = controller;

  try {
    if (message === "/run") {
      if (!intakeId) {
        const runMissingMessage = "No executable intake is available yet; the session has not been created.";
        setChatError(runMissingMessage);
        setChatNotice("");
        appendChat("OpenVibeCoding Command Tower", `Action failed: ${runMissingMessage}`, targetSessionId, {
          kind: "alert",
          card: { title: "Execution failed", subtitle: runMissingMessage },
        });
        setChatInput(message);
        return;
      }
      const runResponse = await runIntake(intakeId, {}, { signal: controller.signal, timeoutMs: PM_INTAKE_REQUEST_TIMEOUT_MS });
      const nextRunId = asString(runResponse.run_id);
      setRunId(nextRunId);
      setChatNotice(`Execution started (run_id: ${nextRunId || "-"})`);
      appendChat("OpenVibeCoding Command Tower", `Execution started, run_id: ${nextRunId || "(empty)"}`, intakeId, {
        kind: "delegation",
        card: {
          title: "Delegation summary",
          subtitle: "PM has handed the task to TL for follow-through.",
          bullets: ["Expected to break down into 3-4 subtasks", `run_id: ${nextRunId || "-"}`],
          actions: ["View full contract"],
        },
      });
      refreshSessionHistory();
      return;
    }

    if (!intakeId) {
      const payload = buildIntakePayload(message);
      setObjective(message);
      const response = await createIntake(payload, {
        signal: controller.signal,
        timeoutMs: PM_INTAKE_REQUEST_TIMEOUT_MS,
      });
      const { nextIntakeId, nextQuestions } = syncIntakeResult(response);
      moveDraftChatToSession(nextIntakeId);
      setRunId("");

      if (nextQuestions.length > 0) {
        setChatNotice(`Session ${nextIntakeId} created. ${nextQuestions.length} clarifiers remaining.`);
        appendChat("OpenVibeCoding Command Tower", `Created session ${nextIntakeId}. Continue by answering these clarifiers: ${nextQuestions.join("; ")}`, nextIntakeId, {
          kind: "decision",
          card: {
            title: "Decision required",
            subtitle: "Fill in these details before moving into execution.",
            options: nextQuestions.slice(0, 2).map((question) => ({
              label: question,
              description: "Answering this keeps plan generation moving.",
            })),
          },
        });
      } else {
        setChatNotice(`Session ${nextIntakeId} created. Type /run to start execution.`);
        appendChat(
          "OpenVibeCoding Command Tower",
          `Created session ${nextIntakeId}. There are no clarifiers right now. Keep chatting or type /run to start execution.`,
          nextIntakeId,
          {
            kind: "report",
            card: {
              title: "Session ready",
              subtitle: "Execution can start now, or you can keep adding context.",
              actions: ["Type /run", "Add more requirements"],
            },
          },
        );
      }
      return;
    }

    if (questions.length > 0) {
      const answerResponse = await answerIntake(
        intakeId,
        { answers: [message] },
        { signal: controller.signal, timeoutMs: PM_INTAKE_REQUEST_TIMEOUT_MS },
      );
      const nextQuestions = asStringArray(answerResponse.questions);
      setQuestions(nextQuestions);
      setPlan(answerResponse.plan || null);
      setTaskChain(answerResponse.task_chain || null);
      setEffectiveBrowserPolicy(answerResponse.effective_browser_policy ?? effectiveBrowserPolicy);

      if (nextQuestions.length > 0) {
        setChatNotice(`Answer saved. ${nextQuestions.length} clarifiers remaining.`);
        appendChat("OpenVibeCoding Command Tower", `Answer saved. Remaining clarifiers: ${nextQuestions.join("; ")}`, intakeId, {
          kind: "decision",
          card: {
            title: "More input needed",
            subtitle: "Keep answering before moving into /run.",
            options: nextQuestions.slice(0, 2).map((question) => ({
              label: question,
              description: "Reply with a clear one-sentence answer.",
            })),
          },
        });
      } else {
        setChatNotice("Clarifiers complete. Type /run to start execution.");
        appendChat("OpenVibeCoding Command Tower", "Clarifiers complete. Keep instructing OpenVibeCoding Command Tower or type /run.", intakeId, {
          kind: "report",
          card: {
            title: "Clarifiers complete",
            subtitle: "The current plan is executable.",
            actions: ["Type /run", "Add more requirements"],
          },
        });
      }
      return;
    }

    await postPmSessionMessage(
      intakeId,
      {
        message,
        from_role: "PM",
        to_role: "TECH_LEAD",
        kind: "chat",
      },
      { signal: controller.signal },
    );
    setChatNotice("Message sent. OpenVibeCoding Command Tower is continuing the flow.");
    appendChat("OpenVibeCoding Command Tower", "Message received. TL and the worker flow will continue from here. Use the right sidebar for live progress.", intakeId, {
      kind: "delegation",
      card: {
        title: "Delegated to Tech Lead",
        subtitle: "TL received your latest instruction.",
        bullets: ["Use Command Chain to inspect live node state", "You can ask for progress at any time"],
      },
    });
  } catch (cause) {
    if (isRequestAborted(cause)) {
      setChatError("");
      setChatNotice("The active request was cancelled.");
      appendChat("OpenVibeCoding Command Tower", "Cancelled the active request.", targetSessionId, {
        kind: "alert",
        card: { title: "Request cancelled", subtitle: "Existing context is preserved. You can enter a new instruction now." },
      });
      setChatInput(message);
      return;
    }
    logError(`[pm-intake] chat flow failed: intake=${intakeId || "-"}, run=${runId || "-"}, message=${message}`);
    const nextError = sanitizeErrorMessage(cause, "Conversation flow failed");
    setChatError(nextError);
    setChatNotice("");
    appendChat("OpenVibeCoding Command Tower", `Action failed: ${nextError}`, targetSessionId, {
      kind: "alert",
      card: { title: "Conversation flow failed", subtitle: nextError },
    });
    setChatInput(message);
  } finally {
    setChatBusy(false);
    if (chatAbortRef.current === controller) {
      chatAbortRef.current = null;
    }
  }
}
