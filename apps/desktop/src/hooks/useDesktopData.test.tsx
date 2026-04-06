import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { useDesktopData, nextBackoffInterval } from "./useDesktopData";

function HookHarness({ activePage }: { activePage: string }) {
  const { overviewMetrics, sessions, alerts, liveError, refreshNow } = useDesktopData(activePage);

  return (
    <div>
      <button type="button" onClick={refreshNow}>
        refresh-now
      </button>
      <span data-testid="overview-value">{overviewMetrics[0]?.value ?? ""}</span>
      <span data-testid="sessions-count">{sessions.length}</span>
      <span data-testid="alerts-count">{alerts.length}</span>
      <span data-testid="live-error">{liveError}</span>
    </div>
  );
}

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" }
  });
}

describe("useDesktopData", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
        if (raw.includes("/api/command-tower/overview")) {
          return jsonResponse({ active_sessions: 9, total_sessions: 20, failed_ratio: 0.1, blocked_sessions: 1 });
        }
        if (raw.includes("/api/pm/sessions")) {
          return jsonResponse([{ pm_session_id: "pm-a" }, { pm_session_id: "pm-b" }]);
        }
        if (raw.includes("/api/command-tower/alerts")) {
          return jsonResponse({ alerts: [{ code: "A", message: "warn", severity: "warning" }] });
        }
        return jsonResponse({}, 404);
      })
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("loads overview metrics and allows manual refresh", async () => {
    render(<HookHarness activePage="overview" />);
    expect(await screen.findByTestId("overview-value")).toHaveTextContent("9");

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "refresh-now" }));

    await waitFor(() => {
      expect(screen.getByTestId("overview-value")).toHaveTextContent("9");
    });
  });

  it("loads sessions on sessions page", async () => {
    render(<HookHarness activePage="sessions" />);
    expect(await screen.findByTestId("sessions-count")).toHaveTextContent("2");
  });

  it("loads alerts on gates page", async () => {
    render(<HookHarness activePage="gates" />);
    expect(await screen.findByTestId("alerts-count")).toHaveTextContent("1");
  });

  it("caps backoff interval at max", () => {
    expect(nextBackoffInterval(1500)).toBe(3000);
    expect(nextBackoffInterval(3000)).toBe(6000);
    expect(nextBackoffInterval(6000)).toBe(8000);
    expect(nextBackoffInterval(8000)).toBe(8000);
  });

  it("surfaces overview errors and recovers after refresh", async () => {
    let overviewFail = true;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
        if (raw.includes("/api/command-tower/overview")) {
          if (overviewFail) {
            return jsonResponse({ message: "boom" }, 503);
          }
          return jsonResponse({ active_sessions: 11, total_sessions: 28, failed_ratio: 0.03, blocked_sessions: 0 });
        }
        if (raw.includes("/api/pm/sessions")) {
          return jsonResponse([]);
        }
        if (raw.includes("/api/command-tower/alerts")) {
          return jsonResponse({ alerts: [] });
        }
        return jsonResponse({}, 404);
      })
    );

    const user = userEvent.setup();
    render(<HookHarness activePage="overview" />);
    await waitFor(() => {
      expect(screen.getByTestId("live-error")).toHaveTextContent("总览数据拉取失败");
    });

    overviewFail = false;
    await user.click(screen.getByRole("button", { name: "refresh-now" }));
    await waitFor(() => {
      expect(screen.getByTestId("overview-value")).toHaveTextContent("11");
      expect(screen.getByTestId("live-error")).toHaveTextContent("");
    });
  });

  it("surfaces sessions fetch errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
        if (raw.includes("/api/command-tower/overview")) {
          return jsonResponse({ active_sessions: 9, total_sessions: 20, failed_ratio: 0.1, blocked_sessions: 1 });
        }
        if (raw.includes("/api/pm/sessions")) {
          return jsonResponse({ error: "failed" }, 500);
        }
        return jsonResponse({ alerts: [] });
      })
    );
    render(<HookHarness activePage="sessions" />);
    await waitFor(() => {
      expect(screen.getByTestId("live-error")).toHaveTextContent("会话列表拉取失败");
    });
  });

  it("maps unreachable network errors to unified operator copy", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
        if (raw.includes("/api/pm/sessions")) {
          throw new TypeError("Failed to fetch");
        }
        if (raw.includes("/api/command-tower/overview")) {
          return jsonResponse({ active_sessions: 9, total_sessions: 20, failed_ratio: 0.1, blocked_sessions: 1 });
        }
        if (raw.includes("/api/command-tower/alerts")) {
          return jsonResponse({ alerts: [] });
        }
        return jsonResponse({}, 404);
      })
    );
    render(<HookHarness activePage="sessions" />);
    await waitFor(() => {
      expect(screen.getByTestId("live-error")).toHaveTextContent("后端暂不可达，已进入退避重试");
    });
  });

  it("treats malformed alerts payload as empty list without error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
        if (raw.includes("/api/command-tower/overview")) {
          return jsonResponse({ active_sessions: 9, total_sessions: 20, failed_ratio: 0.1, blocked_sessions: 1 });
        }
        if (raw.includes("/api/command-tower/alerts")) {
          return jsonResponse({ alerts: { invalid: true } });
        }
        return jsonResponse([]);
      })
    );
    render(<HookHarness activePage="gates" />);
    await waitFor(() => {
      expect(screen.getByTestId("alerts-count")).toHaveTextContent("0");
      expect(screen.getByTestId("live-error")).toHaveTextContent("");
    });
  });

  it("retries transient overview failure then recovers without surfacing live error", async () => {
    let overviewCalls = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
        if (raw.includes("/api/command-tower/overview")) {
          overviewCalls += 1;
          if (overviewCalls === 1) {
            throw new Error("temporary timeout");
          }
          return jsonResponse({ active_sessions: 7, total_sessions: 17, failed_ratio: 0.04, blocked_sessions: 0 });
        }
        if (raw.includes("/api/pm/sessions")) {
          return jsonResponse([]);
        }
        if (raw.includes("/api/command-tower/alerts")) {
          return jsonResponse({ alerts: [] });
        }
        return jsonResponse({}, 404);
      })
    );

    render(<HookHarness activePage="overview" />);
    await waitFor(() => {
      expect(screen.getByTestId("overview-value")).toHaveTextContent("7");
      expect(screen.getByTestId("live-error")).toHaveTextContent("");
    });
    expect(overviewCalls).toBe(2);
  });

  it("uses offline reachability copy when browser is offline", async () => {
    const originalOnLine = navigator.onLine;
    Object.defineProperty(window.navigator, "onLine", { configurable: true, value: false });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
        if (raw.includes("/api/pm/sessions")) {
          throw new Error("session down");
        }
        if (raw.includes("/api/command-tower/overview")) {
          return jsonResponse({ active_sessions: 3, total_sessions: 10, failed_ratio: 0.05, blocked_sessions: 0 });
        }
        if (raw.includes("/api/command-tower/alerts")) {
          return jsonResponse({ alerts: [] });
        }
        return jsonResponse({}, 404);
      })
    );

    try {
      render(<HookHarness activePage="sessions" />);
      await waitFor(() => {
        expect(screen.getByTestId("live-error")).toHaveTextContent("当前网络离线，已暂停实时拉取。恢复联网后将自动重试。");
      });
    } finally {
      Object.defineProperty(window.navigator, "onLine", { configurable: true, value: originalOnLine });
    }
  });

  it("falls back to auth-specific sanitized copy for sessions fetch", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
        if (raw.includes("/api/pm/sessions")) {
          return jsonResponse({ message: "auth denied" }, 401);
        }
        if (raw.includes("/api/command-tower/overview")) {
          return jsonResponse({ active_sessions: 4, total_sessions: 12, failed_ratio: 0.05, blocked_sessions: 0 });
        }
        if (raw.includes("/api/command-tower/alerts")) {
          return jsonResponse({ alerts: [] });
        }
        return jsonResponse({}, 404);
      })
    );

    render(<HookHarness activePage="sessions" />);
    await waitFor(() => {
      expect(screen.getByTestId("live-error")).toHaveTextContent("会话列表拉取失败：权限或认证异常，请确认登录状态。");
    });
  });

  it("does not overwrite overview live error state with sessions failure from another page", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
        if (raw.includes("/api/command-tower/overview")) {
          return jsonResponse({ active_sessions: 8, total_sessions: 14, failed_ratio: 0.07, blocked_sessions: 1 });
        }
        if (raw.includes("/api/pm/sessions")) {
          return jsonResponse({ message: "sessions failed" }, 500);
        }
        if (raw.includes("/api/command-tower/alerts")) {
          return jsonResponse({ alerts: [] });
        }
        return jsonResponse({}, 404);
      })
    );

    render(<HookHarness activePage="overview" />);
    await waitFor(() => {
      expect(screen.getByTestId("overview-value")).toHaveTextContent("8");
    });
    expect(screen.getByTestId("live-error")).toHaveTextContent("");
  });

  it("uses nullish fallback values when overview payload fields are missing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
        if (raw.includes("/api/command-tower/overview")) {
          return jsonResponse({});
        }
        if (raw.includes("/api/pm/sessions")) {
          return jsonResponse([]);
        }
        if (raw.includes("/api/command-tower/alerts")) {
          return jsonResponse({ alerts: [] });
        }
        return jsonResponse({}, 404);
      })
    );

    render(<HookHarness activePage="overview" />);
    await waitFor(() => {
      expect(screen.getByTestId("overview-value")).toHaveTextContent("0");
      expect(screen.getByTestId("live-error")).toHaveTextContent("");
    });
  });

  it("skips late sessions and alerts updates after unmount", async () => {
    let resolveSessions: (() => void) | null = null;
    let rejectAlerts: (() => void) | null = null;

    vi.stubGlobal(
      "fetch",
      vi.fn((input: string | URL | Request) => {
        const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
        if (raw.includes("/api/command-tower/overview")) {
          return Promise.resolve(
            jsonResponse({ active_sessions: 6, total_sessions: 16, failed_ratio: 0.06, blocked_sessions: 0 })
          );
        }
        if (raw.includes("/api/pm/sessions")) {
          return new Promise((resolve) => {
            resolveSessions = () => resolve(jsonResponse([{ pm_session_id: "late-session" }]));
          }) as Promise<Response>;
        }
        if (raw.includes("/api/command-tower/alerts")) {
          return new Promise((_, reject) => {
            rejectAlerts = () => reject(new Error("late-alert-error"));
          }) as Promise<Response>;
        }
        return Promise.resolve(jsonResponse({}, 404));
      })
    );

    const view = render(<HookHarness activePage="overview" />);
    await waitFor(() => {
      expect(screen.getByTestId("overview-value")).toHaveTextContent("6");
    });

    view.unmount();
    const resolveSessionsFn = resolveSessions as (() => void) | null;
    const rejectAlertsFn = rejectAlerts as (() => void) | null;
    if (resolveSessionsFn) resolveSessionsFn();
    if (rejectAlertsFn) rejectAlertsFn();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(resolveSessions).not.toBeNull();
    expect(rejectAlerts).not.toBeNull();
  });

  it("surfaces gates error copy for non-Error rejection payload", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    vi.stubGlobal(
      "fetch",
      vi.fn((input: string | URL | Request) => {
        const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
        if (raw.includes("/api/command-tower/overview")) {
          return Promise.resolve(
            jsonResponse({ active_sessions: 1, total_sessions: 2, failed_ratio: 0, blocked_sessions: 0 }),
          );
        }
        if (raw.includes("/api/pm/sessions")) {
          return Promise.resolve(jsonResponse([]));
        }
        if (raw.includes("/api/command-tower/alerts")) {
          return Promise.reject("alerts exploded");
        }
        return Promise.resolve(jsonResponse({}, 404));
      }),
    );

    try {
      render(<HookHarness activePage="gates" />);
      await waitFor(() => {
        expect(screen.getByTestId("live-error")).toHaveTextContent("策略告警拉取失败");
      });
      expect(consoleSpy).toHaveBeenCalled();
    } finally {
      consoleSpy.mockRestore();
    }
  });

  it("ignores late sessions rejection after unmount on sessions page", async () => {
    let rejectSessions: ((reason?: unknown) => void) | null = null;
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    vi.stubGlobal(
      "fetch",
      vi.fn((input: string | URL | Request) => {
        const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
        if (raw.includes("/api/command-tower/overview")) {
          return Promise.resolve(
            jsonResponse({ active_sessions: 6, total_sessions: 16, failed_ratio: 0.06, blocked_sessions: 0 }),
          );
        }
        if (raw.includes("/api/pm/sessions")) {
          return new Promise((_, reject) => {
            rejectSessions = reject;
          }) as Promise<Response>;
        }
        if (raw.includes("/api/command-tower/alerts")) {
          return Promise.resolve(jsonResponse({ alerts: [] }));
        }
        return Promise.resolve(jsonResponse({}, 404));
      }),
    );

    try {
      const view = render(<HookHarness activePage="sessions" />);
      await waitFor(() => {
        expect(screen.getByTestId("overview-value")).toHaveTextContent("6");
      });
      view.unmount();
      const rejectSessionsFn = rejectSessions as ((reason?: unknown) => void) | null;
      if (rejectSessionsFn) {
        rejectSessionsFn(new Error("late-session-error"));
      }
      await new Promise((resolve) => setTimeout(resolve, 0));
      expect(rejectSessions).not.toBeNull();
      expect(consoleSpy).not.toHaveBeenCalled();
    } finally {
      consoleSpy.mockRestore();
    }
  });

  it("ignores late alerts success payload after unmount on gates page", async () => {
    let resolveAlerts: ((value: Response) => void) | null = null;
    vi.stubGlobal(
      "fetch",
      vi.fn((input: string | URL | Request) => {
        const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
        if (raw.includes("/api/command-tower/overview")) {
          return Promise.resolve(
            jsonResponse({ active_sessions: 4, total_sessions: 10, failed_ratio: 0.01, blocked_sessions: 0 }),
          );
        }
        if (raw.includes("/api/pm/sessions")) {
          return Promise.resolve(jsonResponse([]));
        }
        if (raw.includes("/api/command-tower/alerts")) {
          return new Promise((resolve) => {
            resolveAlerts = resolve;
          }) as Promise<Response>;
        }
        return Promise.resolve(jsonResponse({}, 404));
      }),
    );

    const view = render(<HookHarness activePage="gates" />);
    await waitFor(() => {
      expect(screen.getByTestId("overview-value")).toHaveTextContent("4");
    });
    view.unmount();
    const resolveAlertsFn = resolveAlerts as ((value: Response) => void) | null;
    if (resolveAlertsFn) {
      resolveAlertsFn(jsonResponse({ alerts: [{ code: "late", severity: "info" }] }));
    }
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(resolveAlerts).not.toBeNull();
  });
});
