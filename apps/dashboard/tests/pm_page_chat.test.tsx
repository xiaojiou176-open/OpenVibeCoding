import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterAll, afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/link", () => ({
  default: ({ href, children, prefetch: _prefetch, ...props }: { href: string; children: ReactNode; prefetch?: boolean }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("../lib/api", () => ({
  answerIntake: vi.fn(),
  createIntake: vi.fn(),
  fetchPmSession: vi.fn(),
  fetchPmSessionEvents: vi.fn(),
  fetchPmSessions: vi.fn(),
  fetchTaskPacks: vi.fn(),
  postPmSessionMessage: vi.fn(),
  previewIntake: vi.fn(),
  runIntake: vi.fn(),
}));

import PMIntakePage from "../app/pm/page";
import {
  answerIntake,
  createIntake,
  fetchPmSession,
  fetchPmSessionEvents,
  fetchPmSessions,
  fetchTaskPacks,
  postPmSessionMessage,
  runIntake,
} from "../lib/api";

const DEFAULT_ALLOWED_PATHS = ["apps/dashboard", "apps/orchestrator/src"];
const PM_CHAT_INPUT_LABEL = /PM composer|PM chat input/i;
const ORIGINAL_PM_COPY_VARIANT = process.env.NEXT_PUBLIC_PM_COPY_VARIANT;

function createAbortError(message = "aborted"): Error {
  const error = new Error(message) as Error & { name: string };
  error.name = "AbortError";
  return error;
}

async function sendChat(text: string) {
  await act(async () => {
    fireEvent.change(screen.getByLabelText(PM_CHAT_INPUT_LABEL), { target: { value: text } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
  });
}

async function clickFormButton(name: string) {
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name }));
  });
}

async function flushReactUpdates() {
  await act(async () => {
    await Promise.resolve();
  });
}

describe("pm page chat-driven flow", () => {
  const mockCreateIntake = vi.mocked(createIntake);
  const mockAnswerIntake = vi.mocked(answerIntake);
  const mockRunIntake = vi.mocked(runIntake);
  const mockPostPmSessionMessage = vi.mocked(postPmSessionMessage);
  const mockFetchPmSessions = vi.mocked(fetchPmSessions);
  const mockFetchPmSessionEvents = vi.mocked(fetchPmSessionEvents);
  const mockFetchPmSession = vi.mocked(fetchPmSession);
  const mockFetchTaskPacks = vi.mocked(fetchTaskPacks);

  beforeEach(() => {
    vi.clearAllMocks();
    if (ORIGINAL_PM_COPY_VARIANT === undefined) {
      delete process.env.NEXT_PUBLIC_PM_COPY_VARIANT;
    } else {
      process.env.NEXT_PUBLIC_PM_COPY_VARIANT = ORIGINAL_PM_COPY_VARIANT;
    }
    mockCreateIntake.mockResolvedValue({
      intake_id: "pm-1",
      questions: ["请补充验收标准"],
    });
    mockAnswerIntake.mockResolvedValue({
      intake_id: "pm-1",
      questions: [],
      plan: { stage: "ready" },
      task_chain: { chain_id: "chain-1" },
    });
    mockRunIntake.mockResolvedValue({ run_id: "run-1" });
    mockPostPmSessionMessage.mockResolvedValue({ ok: true });
    mockFetchPmSessions.mockResolvedValue([
      {
        pm_session_id: "pm-history-1",
        status: "active",
        current_step: "pm",
        run_count: 1,
        running_runs: 1,
        failed_runs: 0,
        success_runs: 0,
        blocked_runs: 0,
      },
      {
        pm_session_id: "pm-history-2",
        status: "failed",
        current_step: "reviewer",
        run_count: 1,
        running_runs: 0,
        failed_runs: 1,
        success_runs: 0,
        blocked_runs: 1,
      },
    ]);
    mockFetchPmSession.mockResolvedValue({
      session: {
        pm_session_id: "pm-history-1",
        status: "active",
        run_count: 1,
        running_runs: 1,
        failed_runs: 0,
        success_runs: 0,
        blocked_runs: 0,
        latest_run_id: "run-history-1",
      },
      run_ids: [],
      runs: [],
    });
    mockFetchPmSessionEvents.mockResolvedValue([]);
    mockFetchTaskPacks.mockResolvedValue([
      {
        pack_id: "news_digest",
        version: "v1",
        title: "Public News Digest",
        description: "Public, read-only digest over recent sources for one topic.",
        visibility: "public",
        entry_mode: "pm_intake",
        task_template: "news_digest",
        input_fields: [
          { field_id: "topic", label: "Topic", control: "text", required: true, default_value: "Seattle tech and AI" },
        ],
        ui_hint: { surface_group: "public_task_templates", default_label: "Public news digest" },
      },
    ] as never);
  });

  afterAll(() => {
    if (ORIGINAL_PM_COPY_VARIANT === undefined) {
      delete process.env.NEXT_PUBLIC_PM_COPY_VARIANT;
      return;
    }
    process.env.NEXT_PUBLIC_PM_COPY_VARIANT = ORIGINAL_PM_COPY_VARIANT;
  });

  afterEach(async () => {
    await flushReactUpdates();
  });

  it("renders conversational shell with session history", async () => {
    render(<PMIntakePage />);

    expect(screen.getByRole("heading", { name: "PM" })).toBeInTheDocument();
    expect(screen.getByLabelText("Session history sidebar")).toBeInTheDocument();
    expect(screen.getByLabelText("PM conversation area")).toBeInTheDocument();
    expect(screen.getByLabelText("Context sidebar")).toBeInTheDocument();
    expect(await screen.findByText("pm-history-1")).toBeInTheDocument();
  });

  it("supports layout mode switching via buttons and shortcut", async () => {
    render(<PMIntakePage />);
    await screen.findByText("pm-history-1");

    const page = document.querySelector("main.pm-claude-page");
    expect(page).toHaveClass("pm-layout-dialog");

    await act(async () => {
      fireEvent.click(screen.getByRole("tab", { name: "Split" }));
    });
    expect(page).toHaveClass("pm-layout-split");

    await act(async () => {
      fireEvent.keyDown(window, { key: "\\", ctrlKey: true });
    });
    expect(page).toHaveClass("pm-layout-dialog");
  });

  it("supports global shortcuts for reset and focus controls", async () => {
    render(<PMIntakePage />);
    await screen.findByText("pm-history-1");

    await sendChat("快捷键创建会话");
    await waitFor(() => expect(mockCreateIntake).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/Session pm-1 created/)).toBeInTheDocument();

    const input = screen.getByLabelText(PM_CHAT_INPUT_LABEL);
    const splitButton = screen.getByRole("tab", { name: "Split" });
    splitButton.focus();
    expect(document.activeElement).toBe(splitButton);

    await act(async () => {
      fireEvent.keyDown(window, { key: ".", ctrlKey: true });
    });
    expect(document.activeElement).toBe(input);

    await act(async () => {
      fireEvent.keyDown(window, { key: "C", ctrlKey: true, shiftKey: true });
    });
    const page = document.querySelector("main.pm-claude-page");
    expect(page).toHaveClass("pm-layout-split");
    expect(document.activeElement).toBe(screen.getByLabelText("Command Chain panel"));

    await act(async () => {
      fireEvent.keyDown(window, { key: "n", ctrlKey: true });
    });
    expect(screen.getByText("No session yet. Send the first request")).toBeInTheDocument();
    expect(screen.getByLabelText(PM_CHAT_INPUT_LABEL)).toHaveValue("");
  });

  it("uses Ctrl/Cmd+Shift+C to exit focus layout and focus Command Chain", async () => {
    render(<PMIntakePage />);
    await screen.findByText("pm-history-1");

    await act(async () => {
      fireEvent.click(screen.getByRole("tab", { name: "Focus chat" }));
    });
    const page = document.querySelector("main.pm-claude-page");
    expect(page).toHaveClass("pm-layout-focus");

    await act(async () => {
      fireEvent.keyDown(window, { key: "C", ctrlKey: true, shiftKey: true });
    });
    expect(page).toHaveClass("pm-layout-split");
    expect(document.activeElement).toBe(screen.getByLabelText("Command Chain panel"));
  });

  it("updates chat placeholder with conversation context", async () => {
    render(<PMIntakePage />);

    const input = screen.getByLabelText(PM_CHAT_INPUT_LABEL);
    expect(input).toHaveAttribute("placeholder", "Enter a request (recommended: goal + acceptance criteria), e.g. add homepage onboarding and pass the existing tests...");

    await sendChat("创建会话并触发补充问题");
    await waitFor(() => expect(mockCreateIntake).toHaveBeenCalledTimes(1));

    expect(screen.getByLabelText(PM_CHAT_INPUT_LABEL)).toHaveAttribute(
      "placeholder",
      "Answer the current clarifying question first. Add detail if needed...",
    );
  });

  it("uses variant-a copy by default", async () => {
    delete process.env.NEXT_PUBLIC_PM_COPY_VARIANT;

    render(<PMIntakePage />);
    await screen.findByText("pm-history-1");

    const contextDesc = document.querySelector(".pm-context-card-desc");
    expect(screen.getByText(/First-run path: send request/)).toBeInTheDocument();
    expect(contextDesc).toHaveTextContent("Current next step: send the first request");
    expect(contextDesc).toHaveTextContent("I will turn this request into a session automatically.");
    expect(screen.getByRole("button", { name: /Next: enter the first request/ })).toBeInTheDocument();
    expect(screen.getByLabelText(PM_CHAT_INPUT_LABEL)).toHaveAttribute(
      "placeholder",
      "Enter a request (recommended: goal + acceptance criteria), e.g. add homepage onboarding and pass the existing tests...",
    );
  });

  it("uses variant-b copy when NEXT_PUBLIC_PM_COPY_VARIANT=b", async () => {
    process.env.NEXT_PUBLIC_PM_COPY_VARIANT = "b";

    render(<PMIntakePage />);
    await screen.findByText("pm-history-1");

    const contextDesc = document.querySelector(".pm-context-card-desc");
    expect(screen.getByText(/First-run path: send request/)).toBeInTheDocument();
    expect(contextDesc).toHaveTextContent("Current next step: send the first request");
    expect(contextDesc).toHaveTextContent("I will turn this request into a session automatically.");
    expect(screen.getByRole("button", { name: /Next: enter the first request/ })).toBeInTheDocument();
    expect(screen.getByLabelText(PM_CHAT_INPUT_LABEL)).toHaveAttribute(
      "placeholder",
      "Start with the goal and acceptance criteria, e.g. add homepage onboarding and pass the existing tests",
    );
  });

  it("focuses composer when clicking draft session item", async () => {
    render(<PMIntakePage />);

    const input = screen.getByLabelText(PM_CHAT_INPUT_LABEL);
    expect(document.activeElement).not.toBe(input);

    await act(async () => {
      fireEvent.click(screen.getByTestId("pm-session-item-draft"));
    });
    expect(document.activeElement).toBe(input);
  });

  it("drives first-run CTA from empty state to /run action", async () => {
    mockCreateIntake.mockResolvedValueOnce({
      intake_id: "pm-cta",
      questions: [],
    });

    render(<PMIntakePage />);

    expect(screen.getByText(/No session yet/)).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Next: enter the first request/ }));
    });
    const ctaPrefill = String((screen.getByLabelText(PM_CHAT_INPUT_LABEL) as HTMLTextAreaElement).value ?? "");
    expect(ctaPrefill).toBe("");

    await sendChat("创建 CTA 会话");
    await waitFor(() => {
      expect(mockCreateIntake).toHaveBeenCalledTimes(1);
    });
    expect(screen.getByRole("button", { name: /Next:/ })).toHaveTextContent("Next: review the current progress");
  });

  it("switches session and syncs latest run snapshot", async () => {
    render(<PMIntakePage />);

    const sessionButton = (await screen.findByText("pm-history-1")).closest("button");
    expect(sessionButton).not.toBeNull();
    await act(async () => {
      fireEvent.click(sessionButton as HTMLButtonElement);
    });

    await waitFor(() => {
      expect(mockFetchPmSession).toHaveBeenCalledWith("pm-history-1");
    });
    const runIdMatches = await screen.findAllByText("run-history-1");
    expect(runIdMatches.length).toBeGreaterThan(0);
  });

  it("creates intake from first chat message", async () => {
    render(<PMIntakePage />);

    await sendChat("给 command tower 增加 PM 聊天闭环");

    await waitFor(() => {
      expect(mockCreateIntake).toHaveBeenCalledTimes(1);
    });

    expect(mockCreateIntake).toHaveBeenCalledWith(
      expect.objectContaining({
        allowed_paths: DEFAULT_ALLOWED_PATHS,
        mcp_tool_set: ["codex"],
        task_template: "news_digest",
        requester_role: "PM",
      }),
      expect.objectContaining({ signal: expect.any(AbortSignal), timeoutMs: 180000 }),
    );

    const chatLog = screen.getByRole("log");
    expect(chatLog).toHaveTextContent(/Decision required|Type \/run/);
  });

  it("creates intake from chat and shows no-clarification branch", async () => {
    mockCreateIntake.mockResolvedValueOnce({
      intake_id: "pm-empty-q",
      questions: [],
    });

    render(<PMIntakePage />);

    await sendChat("直接创建无问题会话");

    await waitFor(() => {
      expect(mockCreateIntake).toHaveBeenCalledTimes(1);
    });

    expect(await screen.findByText(/Session pm-empty-q created.*\/run to start execution/)).toBeInTheDocument();
  });

  it("answers pending intake questions from chat", async () => {
    render(<PMIntakePage />);

    await sendChat("创建会话");
    await waitFor(() => expect(mockCreateIntake).toHaveBeenCalledTimes(1));

    await sendChat("验收标准是回归脚本全绿");

    await waitFor(() => {
      expect(mockAnswerIntake).toHaveBeenCalledWith(
        "pm-1",
        { answers: ["验收标准是回归脚本全绿"] },
        expect.objectContaining({ signal: expect.any(AbortSignal) }),
      );
    });

    expect(screen.getAllByText(/Clarifiers complete/).length).toBeGreaterThan(0);
  });

  it("posts session message when no pending questions", async () => {
    render(<PMIntakePage />);

    await sendChat("创建会话");
    await waitFor(() => expect(mockCreateIntake).toHaveBeenCalledTimes(1));

    await sendChat("先补齐文档，再做 perf smoke");
    await waitFor(() => expect(mockAnswerIntake).toHaveBeenCalledTimes(1));

    await sendChat("请 TL 先安排 reviewer");

    await waitFor(() => {
      expect(mockPostPmSessionMessage).toHaveBeenCalledWith(
        "pm-1",
        expect.objectContaining({
          message: "请 TL 先安排 reviewer",
          from_role: "PM",
          to_role: "TECH_LEAD",
          kind: "chat",
        }),
        expect.objectContaining({ signal: expect.any(AbortSignal) }),
      );
    });
  });

  it("runs intake when chat command is /run", async () => {
    render(<PMIntakePage />);

    await sendChat("创建会话");
    await waitFor(() => expect(mockCreateIntake).toHaveBeenCalledTimes(1));

    await sendChat("/run");

    await waitFor(() => {
      expect(mockRunIntake).toHaveBeenCalledWith("pm-1", {}, expect.objectContaining({ signal: expect.any(AbortSignal) }));
    });

    const runIdMatches = await screen.findAllByText(/run_id:\s*run-1/);
    expect(runIdMatches.length).toBeGreaterThan(0);
  });

  it("keeps manual scroll position and shows jump-to-bottom after new messages", async () => {
    render(<PMIntakePage />);

    await sendChat("创建会话");
    await waitFor(() => expect(mockCreateIntake).toHaveBeenCalledTimes(1));

    const chatLog = screen.getByRole("log");
    const scrollToMock = vi.fn();
    Object.defineProperty(chatLog, "scrollTo", { value: scrollToMock, configurable: true });
    Object.defineProperty(chatLog, "scrollHeight", { value: 1200, configurable: true });
    Object.defineProperty(chatLog, "clientHeight", { value: 320, configurable: true });
    Object.defineProperty(chatLog, "scrollTop", { value: 0, writable: true, configurable: true });

    await act(async () => {
      fireEvent.scroll(chatLog, { target: { scrollTop: 0 } });
    });

    await sendChat("验收标准是回归脚本全绿");
    await waitFor(() => {
      expect(mockAnswerIntake).toHaveBeenCalledTimes(1);
    });

    const jumpButton = await screen.findByRole("button", { name: /Back to bottom/ });
    expect(jumpButton).toHaveAttribute("aria-label", expect.stringMatching(/^Back to bottom/));

    await act(async () => {
      fireEvent.click(jumpButton);
    });

    expect(scrollToMock).toHaveBeenCalled();
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: /Back to bottom/ })).not.toBeInTheDocument();
    });
  });

  it("keeps optimistic chat bubbles when remote timeline is temporarily empty", async () => {
    render(<PMIntakePage />);

    await sendChat("临时空时间线也要保留");
    await waitFor(() => expect(mockCreateIntake).toHaveBeenCalledTimes(1));

    await waitFor(() => {
      expect(mockFetchPmSessionEvents).toHaveBeenCalled();
    });
    const chatLog = screen.getByRole("log");
    expect(within(chatLog).getByText("临时空时间线也要保留")).toBeInTheDocument();
  });

  it("merges local chat bubbles with remote timeline messages", async () => {
    mockFetchPmSessionEvents.mockImplementation(async (sessionId: string) => {
      if (sessionId === "pm-1") {
        return [{ ts: "2026-02-16T02:00:00Z", context: { from_role: "TECH_LEAD", message: "远端进度" } }];
      }
      return [];
    });

    render(<PMIntakePage />);
    await sendChat("只清本地");
    await waitFor(() => expect(mockCreateIntake).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("远端进度")).toBeInTheDocument();

    const chatLog = screen.getByRole("log");
    expect(within(chatLog).getByText("远端进度")).toBeInTheDocument();
    expect(within(chatLog).getByText("只清本地")).toBeInTheDocument();
    const remoteBubble = within(chatLog).getByText("远端进度").closest(".pm-chat-bubble");
    expect(remoteBubble).not.toBeNull();
    expect(within(remoteBubble as HTMLElement).getByText("OpenVibeCoding Command Tower")).toBeInTheDocument();
  });

  it("deduplicates optimistic user message when matching remote event arrives", async () => {
    const now = new Date().toISOString();
    mockFetchPmSessionEvents.mockImplementation(async (sessionId: string) => {
      if (sessionId === "pm-1") {
        return [{ ts: now, context: { from_role: "PM", message: "创建会话" } }];
      }
      return [];
    });

    render(<PMIntakePage />);
    await sendChat("创建会话");
    await waitFor(() => expect(mockCreateIntake).toHaveBeenCalledTimes(1));

    const chatLog = screen.getByRole("log");
    await waitFor(() => {
      expect(within(chatLog).getAllByText("创建会话")).toHaveLength(1);
    });
  });

  it("links chain node hover with related chat messages", async () => {
    render(<PMIntakePage />);
    await sendChat("创建会话");
    await waitFor(() => expect(mockCreateIntake).toHaveBeenCalledTimes(1));
    await sendChat("/run");
    await waitFor(() => expect(mockRunIntake).toHaveBeenCalledTimes(1));

    await act(async () => {
      fireEvent.click(screen.getByRole("tab", { name: "Split" }));
    });

    const chainPanel = screen.getByLabelText("Command Chain panel");
    const tlNode = within(chainPanel).getByText("TL").closest(".pm-chain-node");
    expect(tlNode).not.toBeNull();

    await act(async () => {
      fireEvent.mouseEnter(tlNode as Element);
    });

    expect(document.querySelectorAll(".pm-chain-node.is-linked").length).toBeGreaterThan(0);
    expect(document.querySelectorAll(".pm-chat-message-wrap.is-linked").length).toBeGreaterThan(0);
  });

  it("supports keyboard focus linking between chain nodes and chat messages", async () => {
    render(<PMIntakePage />);
    await sendChat("创建会话");
    await waitFor(() => expect(mockCreateIntake).toHaveBeenCalledTimes(1));
    await sendChat("/run");
    await waitFor(() => expect(mockRunIntake).toHaveBeenCalledTimes(1));

    await act(async () => {
      fireEvent.click(screen.getByRole("tab", { name: "Split" }));
    });

    const chainPanel = screen.getByLabelText("Command Chain panel");
    const tlNode = within(chainPanel).getByText("TL").closest(".pm-chain-node");
    expect(tlNode).not.toBeNull();

    await act(async () => {
      (tlNode as HTMLElement).focus();
    });
    expect(document.querySelectorAll(".pm-chain-node.is-linked").length).toBeGreaterThan(0);
    expect(document.querySelectorAll(".pm-chat-message-wrap.is-linked").length).toBeGreaterThan(0);

    await act(async () => {
      fireEvent.blur(tlNode as HTMLElement);
    });
    expect(document.querySelectorAll(".pm-chain-node.is-linked").length).toBe(0);

    const focusableMessage = document.querySelector(".pm-chat-message-wrap[tabindex='0']");
    expect(focusableMessage).not.toBeNull();
    await act(async () => {
      (focusableMessage as HTMLElement).focus();
    });
    expect(document.querySelectorAll(".pm-chain-node.is-linked").length).toBeGreaterThan(0);
  });

  it("shows chat error when /run is issued before intake exists", async () => {
    render(<PMIntakePage />);

    await sendChat("/run");

    expect(mockRunIntake).not.toHaveBeenCalled();
    expect(await screen.findByRole("alert")).toHaveTextContent("No executable intake is available yet; the session has not been created.");
    expect(screen.getByText(/Action failed: No executable intake is available yet; the session has not been created\./)).toBeInTheDocument();
  });

  it("supports Enter send, ignores Shift+Enter, and blocks IME composing Enter", async () => {
    render(<PMIntakePage />);

    await act(async () => {
      fireEvent.change(screen.getByLabelText(PM_CHAT_INPUT_LABEL), { target: { value: "shift-enter" } });
      fireEvent.keyDown(screen.getByLabelText(PM_CHAT_INPUT_LABEL), { key: "Enter", shiftKey: true });
    });

    expect(mockCreateIntake).not.toHaveBeenCalled();

    await act(async () => {
      fireEvent.change(screen.getByLabelText(PM_CHAT_INPUT_LABEL), { target: { value: "ime-composing-enter" } });
      fireEvent.keyDown(screen.getByLabelText(PM_CHAT_INPUT_LABEL), { key: "Enter", shiftKey: false, isComposing: true });
    });

    expect(mockCreateIntake).not.toHaveBeenCalled();

    await act(async () => {
      fireEvent.change(screen.getByLabelText(PM_CHAT_INPUT_LABEL), { target: { value: "enter-send" } });
      fireEvent.keyDown(screen.getByLabelText(PM_CHAT_INPUT_LABEL), { key: "Enter", shiftKey: false });
    });

    await waitFor(() => {
      expect(mockCreateIntake).toHaveBeenCalledWith(
        expect.objectContaining({ task_template: "news_digest" }),
        expect.objectContaining({ signal: expect.any(AbortSignal) }),
      );
    });
  });

  it("validates custom browser policy JSON in form mode", async () => {
    render(<PMIntakePage />);

    await act(async () => {
      fireEvent.change(screen.getByLabelText("Public task template"), { target: { value: "general" } });
      fireEvent.change(screen.getByLabelText("Requester role"), { target: { value: "TECH_LEAD" } });
      fireEvent.change(screen.getByLabelText("Browser preset"), { target: { value: "custom" } });
    });

    await act(async () => {
      fireEvent.change(screen.getByLabelText("Custom browser policy JSON"), { target: { value: "{" } });
    });

    await clickFormButton("Generate questions");

    expect(await screen.findByText("Custom browser policy JSON is invalid")).toBeInTheDocument();
  });

  it("disables custom browser preset for non-privileged role", async () => {
    render(<PMIntakePage />);
    await waitFor(() => expect(mockFetchPmSessions).toHaveBeenCalledTimes(1));

    const customOption = screen.getByRole("option", { name: "custom" });
    expect(customOption).toBeDisabled();
  });

  it("normalizes form list fields and requester role into intake payload", async () => {
    render(<PMIntakePage />);
    await act(async () => {
      fireEvent.change(screen.getByLabelText("Public task template"), { target: { value: "general" } });
      fireEvent.click(screen.getByText("Advanced parameters"));
    });

    await act(async () => {
      fireEvent.change(screen.getByLabelText("Objective"), { target: { value: "payload-shape" } });
      fireEvent.change(screen.getByLabelText("Allowed paths"), {
        target: { value: "apps/a\napps/b,apps/c" },
      });
      fireEvent.change(screen.getByLabelText("Constraints / preferences"), {
        target: { value: "safe, deterministic" },
      });
      fireEvent.change(screen.getByLabelText("Search queries"), {
        target: { value: "query-1\nquery-2" },
      });
      fireEvent.change(screen.getByLabelText("Requester role"), { target: { value: "TECH_LEAD" } });
    });

    await clickFormButton("Generate questions");

    await waitFor(() => {
      expect(mockCreateIntake).toHaveBeenCalledWith(
        expect.objectContaining({
          objective: "payload-shape",
          allowed_paths: ["apps/a", "apps/b", "apps/c"],
          constraints: ["workspace=apps/dashboard", "repo=openvibecoding", "safe", "deterministic"],
          search_queries: ["query-1", "query-2"],
          mcp_tool_set: ["codex"],
          requester_role: "TECH_LEAD",
        }),
        expect.objectContaining({ timeoutMs: 180000 }),
      );
    });
  });

  it("keeps answer/run form buttons disabled before intake exists", async () => {
    render(<PMIntakePage />);
    await waitFor(() => expect(mockFetchPmSessions).toHaveBeenCalledTimes(1));

    const answerButton = screen.getByRole("button", { name: "Generate plan" });
    const runButton = screen.getByRole("button", { name: "Start execution" });

    expect(answerButton).toBeDisabled();
    expect(runButton).toBeDisabled();
  });

  it("surfaces answer/run errors in form mode after intake exists", async () => {
    render(<PMIntakePage />);
    await act(async () => {
      fireEvent.click(screen.getByText("Advanced parameters"));
    });

    await clickFormButton("Generate questions");
    await waitFor(() => expect(mockCreateIntake).toHaveBeenCalledTimes(1));

    mockAnswerIntake.mockRejectedValueOnce(new Error("answer failed"));
    await clickFormButton("Generate plan");
    expect(await screen.findByText("Generate plan failed")).toBeInTheDocument();

    mockRunIntake.mockRejectedValueOnce(new Error("run failed"));
    await clickFormButton("Start execution");
    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("Start execution failed");
    });
  });

  it("restores chat input when send flow fails", async () => {
    mockCreateIntake.mockRejectedValueOnce(new Error("network down"));
    render(<PMIntakePage />);

    await sendChat("失败后要保留");

    expect(await screen.findByRole("alert")).toHaveTextContent("Conversation flow failed: network error, please try again.");
    expect(screen.getByLabelText(PM_CHAT_INPUT_LABEL)).toHaveValue("失败后要保留");
  });

  it("loads per-session chat timeline without cross-session contamination", async () => {
    mockFetchPmSession.mockImplementation(async (sessionId: string) => ({
      session: {
        pm_session_id: sessionId,
        status: "active",
        run_count: 1,
        running_runs: 1,
        failed_runs: 0,
        success_runs: 0,
        blocked_runs: 0,
        latest_run_id: `run-${sessionId}`,
      },
      run_ids: [],
      runs: [],
    }));
    mockFetchPmSessionEvents.mockImplementation(async (sessionId: string) => {
      if (sessionId === "pm-history-1") {
        return [{ ts: "2026-02-16T01:00:00Z", context: { from_role: "PM", message: "会话一消息" } }];
      }
      if (sessionId === "pm-history-2") {
        return [{ ts: "2026-02-16T01:00:01Z", context: { from_role: "PM", message: "会话二消息" } }];
      }
      return [];
    });

    render(<PMIntakePage />);

    const firstSession = (await screen.findByText("pm-history-1")).closest("button");
    expect(firstSession).not.toBeNull();
    await act(async () => {
      fireEvent.click(firstSession as HTMLButtonElement);
    });
    expect(await screen.findByText("会话一消息")).toBeInTheDocument();

    const secondSession = screen.getByText("pm-history-2").closest("button");
    expect(secondSession).not.toBeNull();
    await act(async () => {
      fireEvent.click(secondSession as HTMLButtonElement);
    });
    expect(await screen.findByText("会话二消息")).toBeInTheDocument();
    expect(screen.queryByText("会话一消息")).not.toBeInTheDocument();
  });

  it("renders session-history error state when history query fails", async () => {
    mockFetchPmSessions.mockRejectedValue(new Error("network down"));
    render(<PMIntakePage />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Failed to load session history: network error, please try again.");
  });

  it("cancels in-flight chat request and keeps input draft", async () => {
    mockCreateIntake.mockImplementationOnce(
      (_payload: Record<string, unknown>, options?: { signal?: AbortSignal }) =>
        new Promise((_, reject) => {
          options?.signal?.addEventListener("abort", () => reject(createAbortError()));
        }),
    );
    render(<PMIntakePage />);

    await act(async () => {
      fireEvent.change(screen.getByLabelText(PM_CHAT_INPUT_LABEL), { target: { value: "需要取消的请求" } });
      fireEvent.click(screen.getByRole("button", { name: "Send" }));
    });
    expect(screen.getByRole("button", { name: /\+ New chat/ })).toBeDisabled();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Stop generation" }));
    });

    expect(await screen.findByText("The active request was cancelled.")).toBeInTheDocument();
    expect(screen.getByLabelText(PM_CHAT_INPUT_LABEL)).toHaveValue("需要取消的请求");
  });

  it("disables session switch while chat request is in flight", async () => {
    window.history.replaceState({}, "", "/pm");
    mockCreateIntake.mockImplementationOnce(
      (_payload: Record<string, unknown>, options?: { signal?: AbortSignal }) =>
        new Promise((_, reject) => {
          options?.signal?.addEventListener("abort", () => reject(createAbortError()));
        }),
    );
    render(<PMIntakePage />);

    const firstSessionButton = (await screen.findByText("pm-history-1")).closest("button");
    expect(firstSessionButton).not.toBeNull();

    await act(async () => {
      fireEvent.change(screen.getByLabelText(PM_CHAT_INPUT_LABEL), { target: { value: "锁定切换测试" } });
      fireEvent.click(screen.getByRole("button", { name: "Send" }));
    });

    await waitFor(() => {
      expect(firstSessionButton).toBeDisabled();
      expect(screen.getByRole("button", { name: /\+ New chat/ })).toBeDisabled();
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Stop generation" }));
    });
    await screen.findByText("The active request was cancelled.");
    await waitFor(() => {
      expect(firstSessionButton).not.toBeDisabled();
    });
  });
});
