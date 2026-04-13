import { fireEvent, render, screen, within } from "@testing-library/react";
import { waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";
import * as desktopUi from "./lib/desktopUi";

vi.mock("@xyflow/react", () => {
  return {
    ReactFlow: ({ nodes, onNodeClick, children }: any) => (
      <div aria-label="mock-react-flow">
        {nodes.map((node: any) => (
          <button
            key={node.id}
            type="button"
            onClick={() => onNodeClick?.({} as never, node)}
          >
            {node.data?.label || node.id}
          </button>
        ))}
        {children}
      </div>
    ),
    MiniMap: () => <div data-testid="flow-minimap" />,
    Controls: () => <div data-testid="flow-controls" />,
    Background: () => <div data-testid="flow-background" />
  };
});

let fetchMock: ReturnType<typeof vi.fn>;

describe("Desktop command center shell", { timeout: 15000 }, () => {
  beforeEach(() => {
    window.localStorage.clear();
    Object.defineProperty(window.navigator, "onLine", {
      configurable: true,
      value: true
    });
    fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (raw.includes("/api/command-tower/overview")) {
        return new Response(
          JSON.stringify({ total_sessions: 12, active_sessions: 4, failed_ratio: 0.08, blocked_sessions: 1 }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }
      if (raw.includes("/api/pm/sessions?") && init?.method !== "POST") {
        return new Response(
          JSON.stringify([
            { pm_session_id: "pm-live-1", status: "running", current_step: "reviewer" },
            { pm_session_id: "pm-live-2", status: "blocked", current_step: "worker" }
          ]),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }
      if (raw.includes("/api/command-tower/alerts")) {
        return new Response(JSON.stringify({ alerts: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/pm/task-packs")) {
        return new Response(JSON.stringify([
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
              { field_id: "sources", label: "Source domains", control: "textarea", required: true, default_value: "theverge.com" },
            ],
            ui_hint: { surface_group: "public_task_templates", default_label: "Public news digest" }
          }
        ]), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/pm/sessions/") && raw.includes("/messages") && init?.method === "POST") {
        return new Response(JSON.stringify({ pm_session_id: "pm-local", message: "TL 已拆解并派发执行。" }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      return new Response("{}", { status: 404, headers: { "Content-Type": "application/json" } });
    });

    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(window, "open").mockImplementation(() => null);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  async function expectActiveSession(sessionId: string) {
    await waitFor(() => {
      expect(screen.getByLabelText(/会话工具栏|Session toolbar/)).toHaveTextContent(new RegExp(`会话 ${sessionId}|Session ${sessionId}`));
    });
  }

  async function navigateToPmEntry(user?: ReturnType<typeof userEvent.setup>) {
    const pmEntry = await screen.findByRole("button", { name: /PM 入口|PM intake/ });
    if (user) {
      await user.click(pmEntry);
    } else {
      fireEvent.click(pmEntry);
    }
    await screen.findByLabelText(/对话面板|Conversation panel/);
  }

  function expectTopbarTitle(title: string) {
    const topbar = document.querySelector(".topbar-title");
    expect(topbar).not.toBeNull();
    expect(topbar).toHaveTextContent(title);
  }

  async function startGeneration(user: ReturnType<typeof userEvent.setup>, content: string) {
    await user.type(screen.getByLabelText(/继续对话|Continue the conversation/), content);
    await user.click(screen.getByRole("button", { name: /发送消息|Send message/ }));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /停止生成|Stop generation/ })).toBeEnabled();
    });
  }

  async function switchSessionWithHotkey(sessionKey: "1" | "2", sessionId: string) {
    fireEvent.keyDown(window, { key: sessionKey, metaKey: true });
    try {
      await expectActiveSession(sessionId);
    } catch {
      fireEvent.keyDown(window, { key: sessionKey, ctrlKey: true });
      await expectActiveSession(sessionId);
    }
  }

  it("renders workspace selector + chat + command chain", async () => {
    const user = userEvent.setup();
    render(<App />);
    await navigateToPmEntry(user);

    expect(screen.getByRole("main", { name: /桌面指挥台|desktop shell/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /跳到主内容|Skip to main content/ })).toHaveAttribute("href", "#desktop-main-content");
    expect(screen.getByLabelText(/对话面板|Conversation panel/)).toBeInTheDocument();
    expect(screen.getByLabelText(/会话工具栏|Session toolbar/)).toBeInTheDocument();
    expect(screen.getByLabelText(/会话消息|Session messages/)).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /Command Tower|活跃会话/ })).toBeInTheDocument();
    const chainPanels = await screen.findAllByLabelText(/Command Chain 面板|Command Chain panel/);
    expect(chainPanels.length).toBeGreaterThan(0);
  });

  it("sends message and renders delegation status", async () => {
    const user = userEvent.setup();
    render(<App />);
    await navigateToPmEntry(user);
    await expectActiveSession("pm-live-1");

    await user.type(screen.getByLabelText(/继续对话|Continue the conversation/), "请修复桌面端 UI 协议偏差");
    await user.click(screen.getByRole("button", { name: /发送消息|Send message/ }));

    expect(await screen.findByText(/委派至 Tech Lead|Delegated to Tech Lead/)).toBeInTheDocument();
    expect(await screen.findByText(/TL 已拆解并派发执行。|TL is breaking down the work/)).toBeInTheDocument();

    const messageCall = fetchMock.mock.calls.find(([input, init]) => {
      const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      return raw.includes("/api/pm/sessions/") && raw.includes("/messages") && init?.method === "POST";
    });
    expect(messageCall?.[1]).toMatchObject({ method: "POST" });
    const payload = JSON.parse(String(messageCall?.[1]?.body || "{}")) as Record<string, unknown>;
    expect(payload.message).toBe("请修复桌面端 UI 协议偏差");
    expect(payload.content).toBeUndefined();
  });

  it("toggles desktop chrome locale and persists the preference", async () => {
    const user = userEvent.setup();
    render(<App />);
    await navigateToPmEntry(user);

    await user.click(screen.getByRole("button", { name: "Switch to Chinese" }));

    expectTopbarTitle("PM 入口");
    expect(screen.getByRole("button", { name: "检索" })).toBeInTheDocument();
    expect(window.localStorage.getItem("cortexpilot.ui.locale")).toBe("zh-CN");
  });

  it("prevents duplicate send on rapid double click", async () => {
    const user = userEvent.setup();
    fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (raw.includes("/api/command-tower/overview")) {
        return new Response(
          JSON.stringify({ total_sessions: 12, active_sessions: 4, failed_ratio: 0.08, blocked_sessions: 1 }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }
      if (raw.includes("/api/pm/sessions?") && init?.method !== "POST") {
        return new Response(
          JSON.stringify([{ pm_session_id: "pm-live-1", status: "running", current_step: "reviewer" }]),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }
      if (raw.includes("/api/command-tower/alerts")) {
        return new Response(JSON.stringify({ alerts: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/pm/sessions/") && raw.includes("/messages") && init?.method === "POST") {
        return await new Promise<Response>((resolve) => {
          setTimeout(() => {
            resolve(
              new Response(JSON.stringify({ pm_session_id: "pm-live-1", message: "TL 已拆解并派发执行。" }), {
                status: 200,
                headers: { "Content-Type": "application/json" }
              })
            );
          }, 30);
        });
      }
      return new Response("{}", { status: 404, headers: { "Content-Type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    await navigateToPmEntry(user);
    await expectActiveSession("pm-live-1");

    await user.type(screen.getByLabelText(/继续对话|Continue the conversation/), "please run once");
    await user.dblClick(screen.getByRole("button", { name: /发送消息|Send message/ }));

    expect(await screen.findByText(/TL 已拆解并派发执行。|TL is breaking down the work/)).toBeInTheDocument();
    const messageCalls = fetchMock.mock.calls.filter(([request, init]) => {
      const raw = typeof request === "string" ? request : request instanceof URL ? request.toString() : request.url;
      return raw.includes("/api/pm/sessions/") && raw.includes("/messages") && init?.method === "POST";
    });
    expect(messageCalls).toHaveLength(1);
  });

  it("supports starter prompt chips for empty session", async () => {
    const user = userEvent.setup();
    render(<App />);
    await navigateToPmEntry(user);
    await expectActiveSession("pm-live-1");

    const starter = await screen.findByRole("button", {
      name: /帮我梳理这个需求的执行计划，并给出验收标准。|Help me break this request into an execution plan with acceptance criteria\./
    });
    await user.click(starter);

    const input = screen.getByLabelText(/继续对话|Continue the conversation/) as HTMLTextAreaElement;
    expect(input.value).toMatch(/帮我梳理这个需求的执行计划，并给出验收标准。|Help me break this request into an execution plan with acceptance criteria\./);
  });

  it("supports workspace and branch cycle controls", async () => {
    const user = userEvent.setup();
    render(<App />);
    await navigateToPmEntry(user);

    const workspaceBtn = screen.getByRole("button", { name: /切换工作区|Switch workspace/ });
    const branchBtn = screen.getByRole("button", { name: /切换分支|Switch branch/ });
    const branchBefore = branchBtn.textContent || "";
    await user.click(workspaceBtn);
    expect(branchBtn.textContent).not.toBe(branchBefore);

    const branchAfterWorkspace = branchBtn.textContent || "";
    await user.click(branchBtn);
    expect(branchBtn.textContent).not.toBe(branchAfterWorkspace);
  });

  it("shows explicit disabled reason before sending", async () => {
    const user = userEvent.setup();
    render(<App />);
    await navigateToPmEntry(user);
    await expectActiveSession("pm-live-1");

    expect(screen.getByText(/请先输入消息，再发送。|Enter a message before sending\./)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /发送消息|Send message/ })).toBeDisabled();
  });

  it("does not send when Enter is pressed during IME composing", async () => {
    const user = userEvent.setup();
    render(<App />);
    await navigateToPmEntry(user);
    await expectActiveSession("pm-live-1");

    const input = screen.getByLabelText(/继续对话|Continue the conversation/);
    fireEvent.change(input, { target: { value: "ime composing draft" } });
    fireEvent.keyDown(input, { key: "Enter", shiftKey: false, isComposing: true });

    const messageCalls = fetchMock.mock.calls.filter(([request, init]) => {
      const raw = typeof request === "string" ? request : request instanceof URL ? request.toString() : request.url;
      return raw.includes("/api/pm/sessions/") && raw.includes("/messages") && init?.method === "POST";
    });
    expect(messageCalls).toHaveLength(0);
  });

  it("keeps chat semantics consistent when backend send fails", async () => {
    const user = userEvent.setup();
    fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (raw.includes("/api/command-tower/overview")) {
        return new Response(JSON.stringify({ total_sessions: 12, active_sessions: 4, failed_ratio: 0.08, blocked_sessions: 1 }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/pm/sessions?") && init?.method !== "POST") {
        return new Response(JSON.stringify([{ pm_session_id: "pm-live-1", status: "running", current_step: "reviewer" }]), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/command-tower/alerts")) {
        return new Response(JSON.stringify({ alerts: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/pm/sessions/") && raw.includes("/messages") && init?.method === "POST") {
        return new Response(JSON.stringify({ error: "failed" }), {
          status: 500,
          headers: { "Content-Type": "application/json" }
        });
      }
      return new Response("{}", { status: 404, headers: { "Content-Type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    await navigateToPmEntry(user);
    await expectActiveSession("pm-live-1");
    await user.type(screen.getByLabelText(/继续对话|Continue the conversation/), "backend failure");
    await user.click(screen.getByRole("button", { name: /发送消息|Send message/ }));

    expect(await screen.findByText(/后端消息通道暂不可用，我已切换本地安全回退模式。|The backend message channel is temporarily unavailable, so I switched into a local safe fallback mode\./)).toBeInTheDocument();
    expect(screen.queryByText(/委派至 Tech Lead|Delegated to Tech Lead/)).not.toBeInTheDocument();
  });

  it.each([
    { status: 401, body: { detail: { reason: "token expired" } }, expected: /后端消息通道异常：权限或认证异常，请确认登录状态。|authentication or permission check failed/i },
    { status: 422, body: { detail: { reason: "invalid payload" } }, expected: /后端消息通道异常|The backend message channel failed/ },
    { status: 503, body: { detail: { reason: "upstream unavailable" } }, expected: /后端消息通道异常：服务暂时不可用，请稍后重试。|service is temporarily unavailable/i },
  ])(
    "folds backend failure into same fallback bubble but keeps mapped detail (status=$status)",
    async ({ status, body, expected }) => {
      const user = userEvent.setup();
      fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
        const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
        if (raw.includes("/api/command-tower/overview")) {
          return new Response(JSON.stringify({ total_sessions: 12, active_sessions: 4, failed_ratio: 0.08, blocked_sessions: 1 }), {
            status: 200,
            headers: { "Content-Type": "application/json" }
          });
        }
        if (raw.includes("/api/pm/sessions?") && init?.method !== "POST") {
          return new Response(JSON.stringify([{ pm_session_id: "pm-live-1", status: "running", current_step: "reviewer" }]), {
            status: 200,
            headers: { "Content-Type": "application/json" }
          });
        }
        if (raw.includes("/api/command-tower/alerts")) {
          return new Response(JSON.stringify({ alerts: [] }), {
            status: 200,
            headers: { "Content-Type": "application/json" }
          });
        }
        if (raw.includes("/api/pm/sessions/") && raw.includes("/messages") && init?.method === "POST") {
          return new Response(JSON.stringify(body), {
            status,
            headers: { "Content-Type": "application/json" }
          });
        }
        return new Response("{}", { status: 404, headers: { "Content-Type": "application/json" } });
      });
      vi.stubGlobal("fetch", fetchMock);

      render(<App />);
      await navigateToPmEntry(user);
      await expectActiveSession("pm-live-1");
      await user.type(screen.getByLabelText(/继续对话|Continue the conversation/), `backend failure ${status}`);
      await user.click(screen.getByRole("button", { name: /发送消息|Send message/ }));

      expect(await screen.findByText(/后端消息通道暂不可用，我已切换本地安全回退模式。|local safe fallback mode/)).toBeInTheDocument();
      expect(await screen.findByText(expected)).toBeInTheDocument();
    }
  );

  it.each([
    {
      title: "Error.name=TimeoutError",
      errorFactory: () => {
        const error = new Error("timeout");
        error.name = "TimeoutError";
        return error;
      }
    },
    {
      title: "timeout marker in message",
      errorFactory: () => new Error("request failed: timeout while waiting upstream")
    }
  ])("classifies timeout request failure branch via $title", async ({ errorFactory }) => {
    const user = userEvent.setup();
    fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (raw.includes("/api/command-tower/overview")) {
        return new Response(JSON.stringify({ total_sessions: 12, active_sessions: 4, failed_ratio: 0.08, blocked_sessions: 1 }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/pm/sessions?") && init?.method !== "POST") {
        return new Response(JSON.stringify([{ pm_session_id: "pm-live-1", status: "running", current_step: "reviewer" }]), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/command-tower/alerts")) {
        return new Response(JSON.stringify({ alerts: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/pm/sessions/") && raw.includes("/messages") && init?.method === "POST") {
        throw errorFactory();
      }
      return new Response("{}", { status: 404, headers: { "Content-Type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    await navigateToPmEntry(user);
    await expectActiveSession("pm-live-1");
    await user.type(screen.getByLabelText(/继续对话|Continue the conversation/), `timeout branch ${Date.now()}`);
    await user.click(screen.getByRole("button", { name: /发送消息|Send message/ }));

    expect(await screen.findByText(/后端消息通道暂不可用，我已切换本地安全回退模式。|local safe fallback mode/)).toBeInTheDocument();
    expect(await screen.findByText(new RegExp("Message delivery timed out"))).toBeInTheDocument();
  });

  it("supports Cmd/Ctrl+\\ layout toggle", async () => {
    const user = userEvent.setup();
    const { container } = render(<App />);
    await navigateToPmEntry(user);

    const panel = container.querySelector(".main-panel");
    expect(panel?.className).toContain("mode-dialog");

    await user.keyboard("{Meta>}\\{/Meta}");
    if (!panel?.className.includes("mode-split")) {
      await user.keyboard("{Control>}\\{/Control}");
    }
    expect(panel?.className).toContain("mode-split");
  });

  it("expands chain panel from focus peek button", async () => {
    const user = userEvent.setup();
    const nextLayoutModeSpy = vi.spyOn(desktopUi, "nextLayoutMode").mockReturnValue("focus");
    const { container } = render(<App />);
    await navigateToPmEntry(user);

    await user.keyboard("{Meta>}\\{/Meta}");
    const expandChainButton = await screen.findByRole("button", { name: /展开 Command Chain|Expand Command Chain/ });
    await user.click(expandChainButton);

    const panel = container.querySelector(".main-panel");
    expect(panel?.className).toContain("mode-split");
    nextLayoutModeSpy.mockRestore();
  });

  it("supports Cmd/Ctrl+Shift+D chain popout shortcut", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.keyboard("{Meta>}{Shift>}d{/Shift}{/Meta}");
    if ((window.open as unknown as { mock?: { calls: unknown[][] } }).mock?.calls.length === 0) {
      await user.keyboard("{Control>}{Shift>}d{/Shift}{/Control}");
    }
    expect(window.open).toHaveBeenCalled();
  });

  it("allows selecting decision card option", async () => {
    const user = userEvent.setup();
    render(<App />);
    await navigateToPmEntry(user);

    expect(await screen.findByText(/决策：本次执行模式|Decision:/)).toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: /选择|Choose/ })[0]);

    expect(await screen.findByText(/决策已收到|Decision received:/i)).toBeInTheDocument();
  });

  it("does not show blocking pending-decision hint on first entry", async () => {
    const user = userEvent.setup();
    render(<App />);
    await navigateToPmEntry(user);

    const input = await screen.findByLabelText(/继续对话|Continue the conversation/);
    expect(input).toHaveAttribute("placeholder", "After review, tell the PM to accept and merge or continue revising.");
    expect(screen.queryByText(/先完成上面的决策卡片，或继续补充你的约束...|Resolve the decision card above/)).not.toBeInTheDocument();
  });

  it("marks bootstrap decision as selected by default", async () => {
    const user = userEvent.setup();
    render(<App />);
    await navigateToPmEntry(user);

    expect(await screen.findByText(/决策：本次执行模式|Decision:/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /已选择|Selected/ })).toBeInTheDocument();
  });

  it("stops generation when stop button is clicked", async () => {
    const user = userEvent.setup();

    fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (raw.includes("/api/command-tower/overview")) {
        return new Response(JSON.stringify({ total_sessions: 1, active_sessions: 1, failed_ratio: 0, blocked_sessions: 0 }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/pm/sessions?") && init?.method !== "POST") {
        return new Response(JSON.stringify([{ pm_session_id: "pm-local", status: "running", current_step: "pm" }]), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/command-tower/alerts")) {
        return new Response(JSON.stringify({ alerts: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/pm/sessions/") && raw.includes("/messages") && init?.method === "POST") {
        return await new Promise<Response>((_resolve, reject) => {
          const signal = init.signal;
          signal?.addEventListener("abort", () => {
            reject(new DOMException("Aborted", "AbortError"));
          });
        });
      }
      return new Response("{}", { status: 404, headers: { "Content-Type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    await navigateToPmEntry(user);
    await expectActiveSession("pm-local");
    await user.type(screen.getByLabelText(/继续对话|Continue the conversation/), "请开始执行");
    await user.click(screen.getByRole("button", { name: /发送消息|Send message/ }));

    const stopButton = screen.getByRole("button", { name: /停止生成|Stop generation/ });
    expect(stopButton).toBeEnabled();
    await user.click(stopButton);

    expect(await screen.findByText(/已停止当前生成，现有上下文保留，你可以继续下达新指令。|The current generation was stopped\./)).toBeInTheDocument();
    expect(screen.queryByText(/后端消息通道暂不可用，我已切换本地安全回退模式。|local safe fallback mode/i)).not.toBeInTheDocument();
  });

  it("keeps newer generation state when an older aborted request settles later", async () => {
    const user = userEvent.setup();
    let messageCallCount = 0;

    fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (raw.includes("/api/command-tower/overview")) {
        return new Response(JSON.stringify({ total_sessions: 1, active_sessions: 1, failed_ratio: 0, blocked_sessions: 0 }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/pm/sessions?") && init?.method !== "POST") {
        return new Response(JSON.stringify([{ pm_session_id: "pm-local", status: "running", current_step: "pm" }]), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/command-tower/alerts")) {
        return new Response(JSON.stringify({ alerts: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/pm/sessions/") && raw.includes("/messages") && init?.method === "POST") {
        messageCallCount += 1;
        const signal = init.signal;
        if (messageCallCount === 1) {
          return await new Promise<Response>((_resolve, reject) => {
            signal?.addEventListener("abort", () => {
              setTimeout(() => reject(new DOMException("Aborted", "AbortError")), 80);
            }, { once: true });
          });
        }
        return await new Promise<Response>((_resolve, reject) => {
          signal?.addEventListener("abort", () => {
            reject(new DOMException("Aborted", "AbortError"));
          }, { once: true });
        });
      }
      return new Response("{}", { status: 404, headers: { "Content-Type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    await navigateToPmEntry(user);
    await expectActiveSession("pm-local");

    await user.type(screen.getByLabelText(/继续对话|Continue the conversation/), "first request");
    await user.click(screen.getByRole("button", { name: /发送消息|Send message/ }));
    await user.click(screen.getByRole("button", { name: /停止生成|Stop generation/ }));

    await user.type(screen.getByLabelText(/继续对话|Continue the conversation/), "second request");
    await user.click(screen.getByRole("button", { name: /发送消息|Send message/ }));
    await new Promise((resolve) => setTimeout(resolve, 120));

    expect(screen.getByRole("button", { name: /停止生成|Stop generation/ })).toBeEnabled();
    expect(screen.getByText(/请先停止当前生成，或等待完成后再发送。|Stop the current generation or wait for it to finish before sending another message\./)).toBeInTheDocument();
  });

  it("writes stop message into the original generation session", async () => {
    const user = userEvent.setup();
    fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (raw.includes("/api/command-tower/overview")) {
        return new Response(JSON.stringify({ total_sessions: 2, active_sessions: 2, failed_ratio: 0, blocked_sessions: 0 }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/pm/sessions?") && init?.method !== "POST") {
        return new Response(JSON.stringify([
          { pm_session_id: "pm-live-1", status: "running", current_step: "pm" },
          { pm_session_id: "pm-live-2", status: "running", current_step: "tl" }
        ]), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/command-tower/alerts")) {
        return new Response(JSON.stringify({ alerts: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/pm/sessions/") && raw.includes("/messages") && init?.method === "POST") {
        return await new Promise<Response>((_resolve, reject) => {
          init.signal?.addEventListener("abort", () => {
            reject(new DOMException("Aborted", "AbortError"));
          }, { once: true });
        });
      }
      return new Response("{}", { status: 404, headers: { "Content-Type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    await navigateToPmEntry(user);
    await expectActiveSession("pm-live-1");
    await startGeneration(user, "long request");
    await switchSessionWithHotkey("2", "pm-live-2");
    await user.click(screen.getByRole("button", { name: /停止生成|Stop generation/ }));
    expect(screen.queryByText(/已停止当前生成，现有上下文保留，你可以继续下达新指令。|The current generation was stopped\./)).not.toBeInTheDocument();

    await switchSessionWithHotkey("1", "pm-live-1");
    expect(await screen.findByText(/已停止当前生成，现有上下文保留，你可以继续下达新指令。|The current generation was stopped\./)).toBeInTheDocument();
  });

  it("classifies AbortError as neutral cancel message", async () => {
    const user = userEvent.setup();
    fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (raw.includes("/api/command-tower/overview")) {
        return new Response(JSON.stringify({ total_sessions: 1, active_sessions: 1, failed_ratio: 0, blocked_sessions: 0 }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/pm/sessions?") && init?.method !== "POST") {
        return new Response(JSON.stringify([{ pm_session_id: "pm-local", status: "running", current_step: "pm" }]), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/command-tower/alerts")) {
        return new Response(JSON.stringify({ alerts: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/pm/sessions/") && raw.includes("/messages") && init?.method === "POST") {
        throw new DOMException("Aborted", "AbortError");
      }
      return new Response("{}", { status: 404, headers: { "Content-Type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    await navigateToPmEntry(user);
    await expectActiveSession("pm-local");
    await user.type(screen.getByLabelText(/继续对话|Continue the conversation/), "请开始执行");
    await user.click(screen.getByRole("button", { name: /发送消息|Send message/ }));

    expect(await screen.findByText(/本次消息发送已取消。你可以直接继续输入新的指令。|This message send was cancelled\./)).toBeInTheDocument();
    expect(screen.queryByText(/后端消息通道暂不可用，我已切换本地安全回退模式。|local safe fallback mode/i)).not.toBeInTheDocument();
  });

  it("ignores Alt hotkeys while input is focused", async () => {
    const user = userEvent.setup();
    render(<App />);
    await navigateToPmEntry(user);
    await expectActiveSession("pm-live-1");

    const input = screen.getByLabelText(/继续对话|Continue the conversation/);
    input.focus();
    await user.keyboard("{Alt>}d{/Alt}");

    expect(screen.getByLabelText(/上下文抽屉|Context drawer/i)).toBeInTheDocument();
  });

  it("keeps page-level Alt+Shift shortcuts on command tower without triggering app-level Alt routing", async () => {
    const user = userEvent.setup();
    render(<App />);

    const pageNavigation = await screen.findByRole("navigation", { name: /页面组导航|Page group navigation/ });
    await user.click(within(pageNavigation).getByRole("button", { name: /指挥塔|Command Tower/ }));
    await screen.findByText(
      /OpenVibeCoding 的桌面端聚焦执行与操作决策；更深的治理分析仍留给 Web 视图。|OpenVibeCoding on desktop stays focused on execution and operator decisions/,
    );
    expect(await screen.findByRole("button", { name: /暂停自动更新|Pause auto-refresh/ })).toBeInTheDocument();

    fireEvent.keyDown(window, { key: "l", altKey: true, shiftKey: true });
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /恢复自动更新|Resume auto-refresh/ })).toBeInTheDocument();
    });
    expect(screen.queryByLabelText(/对话面板|Conversation panel/)).not.toBeInTheDocument();
  });

  it("keeps ct-session-detail Alt shortcuts page-scoped without jumping back to PM", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByRole("button", { name: /指挥塔|Command Tower/ }));
    await user.click(await screen.findByRole("button", { name: /继续处理|Resume work/ }));
    expect(await screen.findByRole("heading", { name: /会话透视|Session detail/ })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /暂停实时|Pause live/ })).toBeInTheDocument();

    fireEvent.keyDown(window, { key: "l", altKey: true });
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /恢复实时|Resume live/ })).toBeInTheDocument();
    });
    expect(screen.queryByLabelText(/对话面板|Conversation panel/)).not.toBeInTheDocument();
  });

  it("renders command chain legend and allows clicking node anchor", async () => {
    const user = userEvent.setup();
    render(<App />);
    await navigateToPmEntry(user);

    expect(screen.getByText("Command Chain")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByText(/正在初始化 Chain 引擎...|Initializing the chain engine.../)).not.toBeInTheDocument();
    }, { timeout: 8000 });
    const chainPanel = await screen.findByLabelText(/Command Chain 面板|Command Chain panel/);
    const pmNode = await within(chainPanel).findByRole("button", { name: /^PM$/i }, { timeout: 3000 });
    await user.click(pmNode);
    expect(screen.getByLabelText(/会话消息|Session messages/)).toBeInTheDocument();
  });

  it("restores recoverable draft from localStorage", async () => {
    const user = userEvent.setup();
    window.localStorage.setItem(
      "cortexpilot.desktop.draft:cortexpilot-main:pm-live-1",
      "这是未提交的草稿"
    );
    render(<App />);
    await navigateToPmEntry(user);

    expect(await screen.findByText(/检测到未提交草稿，是否恢复？|An unsent draft was found\. Restore it\?/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /恢复草稿|Restore draft/ }));

    const input = screen.getByLabelText(/继续对话|Continue the conversation/) as HTMLTextAreaElement;
    expect(input.value).toBe("这是未提交的草稿");
    expect(screen.queryByText(/检测到未提交草稿，是否恢复？|An unsent draft was found\. Restore it\?/)).not.toBeInTheDocument();
  });

  it("discards recoverable draft and removes prompt", async () => {
    const user = userEvent.setup();
    const draftKey = "cortexpilot.desktop.draft:cortexpilot-main:pm-live-1";
    window.localStorage.setItem(draftKey, "待丢弃草稿");
    render(<App />);
    await navigateToPmEntry(user);

    expect(await screen.findByText(/检测到未提交草稿，是否恢复？|An unsent draft was found\. Restore it\?/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /丢弃草稿|Discard draft/ }));

    expect(window.localStorage.getItem(draftKey)).toBeNull();
    expect(screen.queryByText(/检测到未提交草稿，是否恢复？|An unsent draft was found\. Restore it\?/)).not.toBeInTheDocument();
  });

  it("shows onboarding banner once and allows dismiss", async () => {
    const user = userEvent.setup();
    render(<App />);
    await navigateToPmEntry(user);

    expect(await screen.findByText(/首次使用按 3 步走|First run in 3 steps:/)).toBeInTheDocument();
    expect(screen.getByText(/当前阶段：待发送首条需求|Current stage: Waiting for the first request/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /第1步：先发一句需求|Step 1: send the first request/ })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /我已了解|Got it/ }));

    expect(window.localStorage.getItem("cortexpilot.desktop.onboarding.dismissed")).toBe("1");
    expect(screen.queryByText(/首次使用按 3 步走|First run in 3 steps:/)).not.toBeInTheDocument();
  });

  it("advances first-run CTA from first prompt to /run template", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: /PM 入口|PM intake/ }));
    await expectActiveSession("pm-live-1");

    await user.click(await screen.findByRole("button", { name: /第1步：先发一句需求|Step 1: send the first request|Step 0: create the first session/ }));
    const input = screen.getByLabelText(/继续对话|Continue the conversation/) as HTMLTextAreaElement;
    expect(input.value).toBe("objective: Complete a first task in apps/desktop/src that can be verified within 3 minutes.\nallowed_paths: [\"apps/desktop/src\"]");

    await user.click(screen.getByRole("button", { name: /发送消息|Send message/ }));
    expect(await screen.findByText(/委派至 Tech Lead|Delegated to Tech Lead/)).toBeInTheDocument();
    expect(screen.getByText(/当前阶段：可输入 \/run|Current stage: Ready for \/run/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /第2步：输入 \/run 开始执行|Step 2: type \/run to begin/ }));
    expect(input.value).toBe("/run");
  });

  it("renders Command Tower three primary actions", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: /指挥塔|Command Tower/ }));
    await screen.findByText(/OpenVibeCoding 的桌面端聚焦执行与操作决策；更深的治理分析仍留给 Web 视图。|OpenVibeCoding on desktop stays focused on execution and operator decisions/);

    expect(screen.getByRole("button", { name: /更新进展|Refresh progress/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /暂停自动更新|Pause auto-refresh/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /继续处理|Resume work/ })).toBeInTheDocument();
  });

  it("covers sidebar governance routes and keeps topbar title in sync", async () => {
    const user = userEvent.setup();
    render(<App />);
    const pageNavigation = await screen.findByRole("navigation", { name: /页面组导航|Page group navigation/ });

    const routeCases = [
      { nav: /运行记录|Proof & Replay|Runs/, title: "Proof & Replay" },
      { nav: /工作流|Workflow Cases|Workflows/, title: "Workflow Cases" },
      { nav: /事件流|Events/, title: "Events" },
      { nav: /合约桌|Contracts|Contract desk/, title: "Contract desk" },
      { nav: /评审|Reviews/, title: "Reviews" },
      { nav: /测试|Tests/, title: "Tests" },
      { nav: /策略|Policies/, title: "Policies" },
      { nav: /角色桌|Agents|Role desk/, title: "Role desk" },
      { nav: /锁管理|Locks/, title: "Locks" },
      { nav: /工作树|Worktrees/, title: "Worktrees" },
    ] as const;

    for (const routeCase of routeCases) {
      await user.click(within(pageNavigation).getByRole("button", { name: routeCase.nav }));
      await waitFor(() => {
        expectTopbarTitle(routeCase.title);
      });
    }
  });

  it("navigates from command tower to session detail route", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: /指挥塔|Command Tower/ }));
    await user.click(await screen.findByRole("button", { name: /继续处理|Resume work/ }));

    await waitFor(() => {
      expectTopbarTitle("Session View");
    });
  });

  it("navigates from runs list to run detail route", async () => {
    fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (raw.includes("/api/command-tower/overview")) {
        return new Response(JSON.stringify({ total_sessions: 12, active_sessions: 4, failed_ratio: 0.08, blocked_sessions: 1 }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/pm/sessions?") && init?.method !== "POST") {
        return new Response(JSON.stringify([{ pm_session_id: "pm-live-1", status: "running", current_step: "reviewer" }]), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/command-tower/alerts")) {
        return new Response(JSON.stringify({ alerts: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/runs") && !raw.includes("/events") && init?.method !== "POST") {
        return new Response(JSON.stringify([
          {
            run_id: "run-detail-target-001",
            task_id: "task-1",
            status: "running",
            created_at: new Date().toISOString(),
            outcome_type: "running",
            failure_class: null,
            failure_code: null,
            owner_agent_id: "TL",
            owner_role: "TECH_LEAD"
          }
        ]), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      return new Response("{}", { status: 404, headers: { "Content-Type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetchMock);

    const user = userEvent.setup();
    render(<App />);
    const pageNavigation = await screen.findByRole("navigation", { name: /页面组导航|Page group navigation/ });

    await user.click(within(pageNavigation).getByRole("button", { name: /运行记录|Proof & Replay|Runs/ }));
    await user.click(await screen.findByRole("button", { name: "run-detail-t" }));
    await waitFor(() => {
      expectTopbarTitle("Proof room");
    });
  });

  it("navigates from workflows list to workflow detail route", async () => {
    fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (raw.includes("/api/command-tower/overview")) {
        return new Response(JSON.stringify({ total_sessions: 12, active_sessions: 4, failed_ratio: 0.08, blocked_sessions: 1 }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/pm/sessions?") && init?.method !== "POST") {
        return new Response(JSON.stringify([{ pm_session_id: "pm-live-1", status: "running", current_step: "reviewer" }]), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/command-tower/alerts")) {
        return new Response(JSON.stringify({ alerts: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/queue")) {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/workflows") && !raw.includes("/api/workflows/") && init?.method !== "POST") {
        return new Response(JSON.stringify([
          { workflow_id: "wf-target-001", status: "running", namespace: "default", runs: [] }
        ]), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      return new Response("{}", { status: 404, headers: { "Content-Type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetchMock);

    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: /工作流|Workflow Cases|Workflows/ }));
    await user.click(await screen.findByRole("button", { name: "wf-target-001" }));
    await waitFor(() => {
      expectTopbarTitle("Workflow Case Detail");
    });
  });

  it("toggles sound reminder state", async () => {
    const user = userEvent.setup();
    render(<App />);
    await navigateToPmEntry(user);

    const button = await screen.findByRole("button", { name: /声音提醒：开启|Sound alerts: on/ });
    await user.click(button);
    expect(screen.getByRole("button", { name: /声音提醒：关闭|Sound alerts: off/ })).toBeInTheDocument();
  });

  it("keeps input enabled but disables send when there is no backend session", async () => {
    fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (raw.includes("/api/command-tower/overview")) {
        return new Response(JSON.stringify({ total_sessions: 0, active_sessions: 0, failed_ratio: 0, blocked_sessions: 0 }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/pm/sessions?") && init?.method !== "POST") {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/command-tower/alerts")) {
        return new Response(JSON.stringify({ alerts: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      return new Response("{}", { status: 404, headers: { "Content-Type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    await navigateToPmEntry();
    const input = await screen.findByLabelText(/继续对话|Continue the conversation/);
    expect(input).toBeEnabled();
    expect(screen.getByRole("button", { name: /端内创建首会话|Create first session in desktop/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /打开 Dashboard \/pm 手动创建|Open Dashboard \/pm and create it manually/ })).toBeInTheDocument();
    expect(screen.getByText(/^Click "Create first session in desktop" first\. If that fails, open Dashboard \/pm and create it manually\.$/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /发送消息|Send message/ })).toBeDisabled();
  });

  it("creates first session in-app with minimal intake schema", async () => {
    let intakeCreated = false;
    fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (raw.includes("/api/command-tower/overview")) {
        return new Response(JSON.stringify({ total_sessions: 0, active_sessions: 0, failed_ratio: 0, blocked_sessions: 0 }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/pm/sessions?") && init?.method !== "POST") {
        return new Response(JSON.stringify(intakeCreated ? [{ pm_session_id: "pm-first-1", status: "active" }] : []), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/command-tower/alerts")) {
        return new Response(JSON.stringify({ alerts: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/pm/task-packs")) {
        return new Response(JSON.stringify([
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
              { field_id: "sources", label: "Source domains", control: "textarea", required: true, default_value: "theverge.com" },
            ],
            ui_hint: { surface_group: "public_task_templates", default_label: "Public news digest" }
          }
        ]), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/pm/intake") && init?.method === "POST") {
        intakeCreated = true;
        return new Response(JSON.stringify({ intake_id: "pm-first-1", status: "NEEDS_INPUT", questions: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      return new Response("{}", { status: 404, headers: { "Content-Type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetchMock);

    const user = userEvent.setup();
    render(<App />);
    await navigateToPmEntry(user);

    await user.click(await screen.findByRole("button", { name: /端内创建首会话|Create first session in desktop/ }));

    await waitFor(() => {
      expect(screen.getByLabelText(/会话工具栏|Session toolbar/)).toHaveTextContent(/会话 pm-first-1|Session pm-first-1/);
    });
    const intakeCall = fetchMock.mock.calls.find(([request, init]) => {
      const raw = typeof request === "string" ? request : request instanceof URL ? request.toString() : request.url;
      return raw.includes("/api/pm/intake") && init?.method === "POST";
    });
    expect(intakeCall?.[1]).toMatchObject({ method: "POST" });
    const payload = JSON.parse(String(intakeCall?.[1]?.body ?? "{}")) as Record<string, unknown>;
    expect(payload.objective).toEqual(expect.any(String));
    expect(payload.allowed_paths).toEqual(["apps/desktop/src"]);
  });

  it("creates first session with selected task pack payload", async () => {
    let intakeCreated = false;
    fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (raw.includes("/api/command-tower/overview")) {
        return new Response(JSON.stringify({ total_sessions: 0, active_sessions: 0, failed_ratio: 0, blocked_sessions: 0 }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/pm/sessions?") && init?.method !== "POST") {
        return new Response(JSON.stringify(intakeCreated ? [{ pm_session_id: "pm-first-pack", status: "active" }] : []), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/command-tower/alerts")) {
        return new Response(JSON.stringify({ alerts: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/pm/task-packs")) {
        return new Response(JSON.stringify([
          {
            pack_id: "page_brief",
            version: "v1",
            title: "Public Page Brief",
            description: "Public, read-only page brief for a single URL.",
            visibility: "public",
            entry_mode: "pm_intake",
            task_template: "page_brief",
            input_fields: [
              { field_id: "url", label: "Page URL", control: "url", required: true, default_value: "https://example.com" },
              { field_id: "focus", label: "Focus", control: "textarea", required: true, default_value: "Summarize the page for a first-time reader." },
            ],
            ui_hint: { surface_group: "public_task_templates", default_label: "Public page brief" }
          }
        ]), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/pm/intake") && init?.method === "POST") {
        intakeCreated = true;
        return new Response(JSON.stringify({ intake_id: "pm-first-pack", status: "NEEDS_INPUT", questions: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      return new Response("{}", { status: 404, headers: { "Content-Type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetchMock);

    const user = userEvent.setup();
    render(<App />);
    await navigateToPmEntry(user);

    await user.selectOptions(await screen.findByLabelText("Desktop task pack"), "page_brief");
    await user.clear(screen.getByLabelText("Page URL"));
    await user.type(screen.getByLabelText("Page URL"), "https://openai.com");
    await user.clear(screen.getByLabelText("Focus"));
    await user.type(screen.getByLabelText("Focus"), "Summarize the page.");
    await user.click(screen.getByRole("button", { name: /端内创建首会话|Create first session in desktop/ }));

    await waitFor(() => {
      expect(screen.getByLabelText(/会话工具栏|Session toolbar/)).toHaveTextContent(/会话 pm-first-pack|Session pm-first-pack/);
    });
    const intakeCall = fetchMock.mock.calls.find(([request, init]) => {
      const raw = typeof request === "string" ? request : request instanceof URL ? request.toString() : request.url;
      return raw.includes("/api/pm/intake") && init?.method === "POST";
    });
    const payload = JSON.parse(String(intakeCall?.[1]?.body ?? "{}")) as Record<string, unknown>;
    expect(payload.task_template).toBe("page_brief");
    expect(payload.template_payload).toEqual({
      url: "https://openai.com",
      focus: "Summarize the page.",
    });
    expect(payload.allowed_paths).toEqual(["apps/desktop/src"]);
  });

  it("shows actionable fallback CTA when in-app first-session creation fails", async () => {
    fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (raw.includes("/api/command-tower/overview")) {
        return new Response(JSON.stringify({ total_sessions: 0, active_sessions: 0, failed_ratio: 0, blocked_sessions: 0 }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/pm/sessions?") && init?.method !== "POST") {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/command-tower/alerts")) {
        return new Response(JSON.stringify({ alerts: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/pm/intake") && init?.method === "POST") {
        return new Response(JSON.stringify({ detail: { reason: "bad payload" } }), {
          status: 400,
          headers: { "Content-Type": "application/json" }
        });
      }
      return new Response("{}", { status: 404, headers: { "Content-Type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetchMock);

    const user = userEvent.setup();
    render(<App />);
    await navigateToPmEntry(user);

    await user.click(await screen.findByRole("button", { name: /端内创建首会话|Create first session in desktop/ }));
    const fallbackHints = await screen.findAllByText(/请点击“打开 Dashboard \/pm 手动创建”|Open Dashboard \/pm and create it manually/);
    expect(fallbackHints.length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: /打开 Dashboard \/pm 手动创建|Open Dashboard \/pm and create it manually/ }));
    expect(window.open).toHaveBeenCalledWith(expect.stringContaining("/pm"), "_blank", "noopener,noreferrer");
  });

  it("shows fallback guidance when intake id is missing after in-app first-session creation", async () => {
    fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (raw.includes("/api/command-tower/overview")) {
        return new Response(JSON.stringify({ total_sessions: 0, active_sessions: 0, failed_ratio: 0, blocked_sessions: 0 }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/pm/sessions?") && init?.method !== "POST") {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/command-tower/alerts")) {
        return new Response(JSON.stringify({ alerts: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/pm/intake") && init?.method === "POST") {
        return new Response(JSON.stringify({ intake_id: "   " }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      return new Response("{}", { status: 404, headers: { "Content-Type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetchMock);

    const user = userEvent.setup();
    render(<App />);
    await navigateToPmEntry(user);
    await user.click(await screen.findByRole("button", { name: /端内创建首会话|Create first session in desktop/ }));

    const fallbackHints = await screen.findAllByText(/请点击“打开 Dashboard \/pm 手动创建”|Open Dashboard \/pm and create it manually/);
    expect(fallbackHints.length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /发送消息|Send message/ })).toBeDisabled();
  });

  it("keeps composer maxLength aligned with send limit", async () => {
    const user = userEvent.setup();
    render(<App />);
    await navigateToPmEntry(user);
    const input = await screen.findByLabelText(/继续对话|Continue the conversation/);
    expect(input).toHaveAttribute("maxLength", "4000");
  });

  it("clears active session when backend session list becomes empty", async () => {
    let sessionCalls = 0;
    fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (raw.includes("/api/command-tower/overview")) {
        return new Response(JSON.stringify({ total_sessions: 1, active_sessions: 1, failed_ratio: 0, blocked_sessions: 0 }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/pm/sessions?") && init?.method !== "POST") {
        sessionCalls += 1;
        const payload = sessionCalls === 1 ? [{ pm_session_id: "pm-live-1", status: "running" }] : [];
        return new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (raw.includes("/api/command-tower/alerts")) {
        return new Response(JSON.stringify({ alerts: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      return new Response("{}", { status: 404, headers: { "Content-Type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetchMock);

    const user = userEvent.setup();
    render(<App />);
    await navigateToPmEntry(user);
    await expectActiveSession("pm-live-1");
    await user.click(screen.getByRole("button", { name: /立即刷新|Refresh now/ }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /发送消息|Send message/ })).toBeDisabled();
    });
    expect(screen.getByText(/还没有会话。请先点击“端内创建首会话”；若失败请点击“打开 Dashboard \/pm 手动创建”。|No session exists yet\./)).toBeInTheDocument();
  });

  it("handles critical gate blocker confirm action", async () => {
    fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (raw.includes("/api/command-tower/overview")) {
        return new Response(JSON.stringify({ total_sessions: 1, active_sessions: 1, failed_ratio: 1, blocked_sessions: 1 }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/pm/sessions?") && init?.method !== "POST") {
        return new Response(JSON.stringify([{ pm_session_id: "pm-live-1", status: "blocked", current_step: "reviewer" }]), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/command-tower/alerts")) {
        return new Response(JSON.stringify({
          alerts: [{ code: "CRITICAL_GATE", severity: "critical", message: "gate hard fail" }]
        }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      return new Response("{}", { status: 404, headers: { "Content-Type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetchMock);

    const user = userEvent.setup();
    render(<App />);
    await navigateToPmEntry(user);
    const blocker = await screen.findByRole("dialog", { name: /CRITICAL 阻断告警|Critical blocker alert/ });
    expect(blocker).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /我已确认，进入人工裁决|I understand\. Move to manual adjudication\./ }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: /CRITICAL 阻断告警|Critical blocker alert/ })).not.toBeInTheDocument();
    });
  });

  it("closes critical gate blocker dialog on Escape key", async () => {
    fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (raw.includes("/api/command-tower/overview")) {
        return new Response(JSON.stringify({ total_sessions: 1, active_sessions: 1, failed_ratio: 1, blocked_sessions: 1 }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/pm/sessions?") && init?.method !== "POST") {
        return new Response(JSON.stringify([{ pm_session_id: "pm-live-1", status: "blocked", current_step: "reviewer" }]), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/command-tower/alerts")) {
        return new Response(JSON.stringify({
          alerts: [{ code: "CRITICAL_GATE", severity: "critical", message: "gate hard fail" }]
        }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      return new Response("{}", { status: 404, headers: { "Content-Type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetchMock);

    const user = userEvent.setup();
    render(<App />);
    await navigateToPmEntry(user);
    expect(await screen.findByRole("dialog", { name: /CRITICAL 阻断告警|Critical blocker alert/ })).toBeInTheDocument();

    await user.keyboard("{Escape}");
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: /CRITICAL 阻断告警|Critical blocker alert/ })).not.toBeInTheDocument();
    });
  });

  it("traps focus inside critical gate blocker dialog", async () => {
    fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (raw.includes("/api/command-tower/overview")) {
        return new Response(JSON.stringify({ total_sessions: 1, active_sessions: 1, failed_ratio: 1, blocked_sessions: 1 }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/pm/sessions?") && init?.method !== "POST") {
        return new Response(JSON.stringify([{ pm_session_id: "pm-live-1", status: "blocked", current_step: "reviewer" }]), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/command-tower/alerts")) {
        return new Response(JSON.stringify({
          alerts: [{ code: "CRITICAL_GATE", severity: "critical", message: "gate hard fail" }]
        }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      return new Response("{}", { status: 404, headers: { "Content-Type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetchMock);

    const user = userEvent.setup();
    render(<App />);
    await navigateToPmEntry(user);

    await screen.findByRole("dialog", { name: /CRITICAL 阻断告警|Critical blocker alert/ });
    const confirmButton = screen.getByRole("button", { name: /我已确认，进入人工裁决|I understand\. Move to manual adjudication\./ });
    await waitFor(() => {
      expect(confirmButton).toHaveFocus();
    });

    const composer = screen.getByLabelText(/继续对话|Continue the conversation/);
    composer.focus();
    await user.keyboard("{Tab}");
    expect(confirmButton).toHaveFocus();
    await user.keyboard("{Shift>}{Tab}{/Shift}");
    expect(confirmButton).toHaveFocus();
  });

  it("supports additional hotkey routing branches", async () => {
    const user = userEvent.setup();
    render(<App />);
    await navigateToPmEntry(user);
    await expectActiveSession("pm-live-1");

    fireEvent.keyDown(window, { key: "m", altKey: true });
    expect(await screen.findByRole("heading", { name: /指挥面总览|Command deck overview/ })).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "2", altKey: true });
    expect(await screen.findByLabelText(/继续对话|Continue the conversation/)).toBeInTheDocument();

    fireEvent.keyDown(window, { key: "3", altKey: true });
    expect(await screen.findByRole("heading", { name: /变更门禁|Diff gate/ })).toBeInTheDocument();

    fireEvent.keyDown(window, { key: "k", metaKey: true });
    if (!screen.queryByRole("heading", { name: /检索|Search/ })) {
      fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    }
    expect(await screen.findByRole("heading", { name: /检索|Search/ })).toBeInTheDocument();

    fireEvent.keyDown(window, { key: ".", metaKey: true });
    if (document.activeElement?.getAttribute("id") !== "desktop-chat-input") {
      fireEvent.keyDown(window, { key: ".", ctrlKey: true });
    }
    expect(await screen.findByLabelText(/继续对话|Continue the conversation/)).toHaveFocus();

    fireEvent.keyDown(window, { key: "c", metaKey: true, shiftKey: true });
    if (!screen.queryByRole("button", { name: /展开 Command Chain|Expand Command Chain/ })) {
      fireEvent.keyDown(window, { key: "c", ctrlKey: true, shiftKey: true });
    }
    await waitFor(() => {
      expect(
        Boolean(screen.queryByLabelText(/Command Chain 面板|Command Chain panel/)) ||
        Boolean(screen.queryByRole("button", { name: /展开 Command Chain|Expand Command Chain/ }))
      ).toBe(true);
    });

    fireEvent.keyDown(window, { key: "d", altKey: true });
    await waitFor(() => {
      expect(screen.queryByLabelText(/上下文抽屉|Context drawer/i)).not.toBeInTheDocument();
    });
    fireEvent.keyDown(window, { key: "p", altKey: true });
    fireEvent.keyDown(window, { key: "s", metaKey: true, shiftKey: true });
    if (!screen.queryByLabelText(/对话面板|Conversation panel/)) {
      fireEvent.keyDown(window, { key: "s", ctrlKey: true, shiftKey: true });
    }
    expect(screen.getByLabelText(/对话面板|Conversation panel/)).toBeInTheDocument();

    fireEvent.keyDown(window, { key: "5", altKey: true });
    expect((await screen.findAllByRole("heading", { name: /策略|Policies/ })).length).toBeGreaterThan(0);
  });

  it("blocks send while offline and keeps message endpoint untouched", async () => {
    const user = userEvent.setup();
    render(<App />);
    await navigateToPmEntry(user);
    await expectActiveSession("pm-live-1");

    Object.defineProperty(window.navigator, "onLine", {
      configurable: true,
      value: false
    });
    fireEvent(window, new Event("offline"));
    expect(await screen.findByText(/现在离线中，联网后会自动继续同步。|You are offline\./)).toBeInTheDocument();

    await user.type(screen.getByLabelText(/继续对话|Continue the conversation/), "offline should not send");
    fireEvent.keyDown(screen.getByLabelText(/继续对话|Continue the conversation/), { key: "Enter", shiftKey: false, isComposing: false });

    const messageCalls = fetchMock.mock.calls.filter(([request, init]) => {
      const raw = typeof request === "string" ? request : request instanceof URL ? request.toString() : request.url;
      return raw.includes("/api/pm/sessions/") && raw.includes("/messages") && init?.method === "POST";
    });
    expect(messageCalls).toHaveLength(0);
  });

  it("allows boundary composer input (4000 chars) to send", async () => {
    const user = userEvent.setup();
    render(<App />);
    await navigateToPmEntry(user);
    await expectActiveSession("pm-live-1");

    const boundaryInput = "x".repeat(4000);
    const input = screen.getByLabelText(/继续对话|Continue the conversation/);
    fireEvent.change(input, { target: { value: boundaryInput } });
    fireEvent.keyDown(input, { key: "Enter", shiftKey: false, isComposing: false });

    const messageCalls = await waitFor(() => {
      const calls = fetchMock.mock.calls.filter(([request, init]) => {
        const raw = typeof request === "string" ? request : request instanceof URL ? request.toString() : request.url;
        return raw.includes("/api/pm/sessions/") && raw.includes("/messages") && init?.method === "POST";
      });
      expect(calls.length).toBeGreaterThan(0);
      return calls;
    });
    const latestCall = messageCalls[messageCalls.length - 1];
    const payload = JSON.parse(String(latestCall?.[1]?.body ?? "{}")) as Record<string, unknown>;
    expect(String(payload.message ?? "")).toHaveLength(4000);
    expect(screen.queryByText(/请将输入缩短到 4000 字以内再发送。|Shorten the input to 4000 characters or fewer before sending\./)).not.toBeInTheDocument();
    const latestMessageCalls = fetchMock.mock.calls.filter(([request, init]) => {
      const raw = typeof request === "string" ? request : request instanceof URL ? request.toString() : request.url;
      return raw.includes("/api/pm/sessions/") && raw.includes("/messages") && init?.method === "POST";
    });
    expect(latestMessageCalls.length).toBeGreaterThan(0);
    await user.clear(input);
  });

  it("supports Cmd/Ctrl+N new conversation branch when no session exists", async () => {
    let intakeCreated = false;
    fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (raw.includes("/api/command-tower/overview")) {
        return new Response(JSON.stringify({ total_sessions: 0, active_sessions: 0, failed_ratio: 0, blocked_sessions: 0 }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/pm/sessions?") && init?.method !== "POST") {
        return new Response(JSON.stringify(intakeCreated ? [{ pm_session_id: "pm-hotkey-1", status: "active" }] : []), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/command-tower/alerts")) {
        return new Response(JSON.stringify({ alerts: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      if (raw.includes("/api/pm/intake") && init?.method === "POST") {
        intakeCreated = true;
        return new Response(JSON.stringify({ intake_id: "pm-hotkey-1", status: "NEEDS_INPUT", questions: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }
      return new Response("{}", { status: 404, headers: { "Content-Type": "application/json" } });
    });
    vi.stubGlobal("fetch", fetchMock);

    const user = userEvent.setup();
    render(<App />);
    await navigateToPmEntry(user);
    expect(screen.getByRole("button", { name: /端内创建首会话|Create first session in desktop/ })).toBeInTheDocument();

    fireEvent.keyDown(window, { key: "n", metaKey: true });
    if (!screen.queryByLabelText(/会话工具栏|Session toolbar/)?.textContent?.includes("pm-hotkey-1")) {
      fireEvent.keyDown(window, { key: "n", ctrlKey: true });
    }
    await waitFor(() => {
      expect(screen.getByLabelText(/会话工具栏|Session toolbar/)).toHaveTextContent(/会话 pm-hotkey-1|Session pm-hotkey-1/);
    });
  });

  it("navigates to god-mode page from sidebar", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: /快速审批|Quick approval/ }));
    expect(await screen.findByRole("heading", { name: /快速审批|Quick approval/ })).toBeInTheDocument();
  });

  it("renders chain popout mode when query flag is present", async () => {
    window.history.pushState({}, "", "/?chain-popout=1");
    render(<App />);

    expect(screen.getByRole("main", { name: /Command Chain 独立窗口|Command Chain pop-out window/ })).toBeInTheDocument();
    expect(await screen.findByLabelText(/Command Chain 面板|Command Chain panel/)).toBeInTheDocument();

    window.history.pushState({}, "", "/");
  });
});
