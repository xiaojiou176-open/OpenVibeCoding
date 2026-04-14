import { beforeEach, describe, expect, it, vi } from "vitest";

const { invokeMock, listenMock, registerMock, onOpenUrlMock } = vi.hoisted(() => ({
  invokeMock: vi.fn(),
  listenMock: vi.fn(),
  registerMock: vi.fn(),
  onOpenUrlMock: vi.fn()
}));

vi.mock("@tauri-apps/api/core", () => ({ invoke: invokeMock }));
vi.mock("@tauri-apps/api/event", () => ({ listen: listenMock }));
vi.mock("@tauri-apps/plugin-global-shortcut", () => ({ register: registerMock }));
vi.mock("@tauri-apps/plugin-deep-link", () => ({ onOpenUrl: onOpenUrlMock }));

import { initDesktopRuntimeBridges, type DesktopRuntimeEvent, isTauriRuntime } from "./runtimeBridge";

function getCodes(events: DesktopRuntimeEvent[]): string[] {
  return events.map((event) => event.code);
}

describe("runtimeBridge", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    delete (window as Window & { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__;
  });

  it("returns false for browser runtime without tauri internals", () => {
    expect(isTauriRuntime()).toBe(false);
  });

  it("returns true only when tauri internals exist", () => {
    (window as Window & { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__ = {};
    expect(isTauriRuntime()).toBe(true);
  });

  it("skips plugin registration outside tauri runtime and emits warnings", async () => {
    const events: DesktopRuntimeEvent[] = [];

    await initDesktopRuntimeBridges((event) => events.push(event));

    expect(listenMock).not.toHaveBeenCalled();
    expect(registerMock).not.toHaveBeenCalled();
    expect(onOpenUrlMock).not.toHaveBeenCalled();
    expect(getCodes(events)).toEqual(
      expect.arrayContaining([
        "RUST_PANIC_LISTENER_SKIPPED",
        "GLOBAL_SHORTCUT_SKIPPED",
        "DEEP_LINK_SKIPPED",
        "UPDATER_DISABLED"
      ])
    );
  });

  it("emits ready/runtime events when all plugins register", async () => {
    (window as Window & { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__ = {};
    let panicListener: ((event: { payload?: unknown }) => void) | undefined;
    listenMock.mockImplementation(async (_name: string, cb: (event: { payload?: unknown }) => void) => {
      panicListener = cb;
    });

    let shortcutHandler: (() => void) | undefined;
    registerMock.mockImplementation(async (_shortcut: string, cb: () => void) => {
      shortcutHandler = cb;
    });

    onOpenUrlMock.mockImplementation(async (cb: (urls: string[]) => void) => {
      cb([]);
    });

    const events: DesktopRuntimeEvent[] = [];
    await initDesktopRuntimeBridges((event) => events.push(event));

    panicListener?.({ payload: 123 });
    shortcutHandler?.();

    const panic = events.find((event) => event.code === "RUST_PANIC");
    expect(panic?.detail).toBe("Rust panic captured");
    expect(getCodes(events)).toEqual(
      expect.arrayContaining([
        "RUST_PANIC_LISTENER_READY",
        "GLOBAL_SHORTCUT_READY",
        "DEEP_LINK_READY",
        "DEEP_LINK_OPENED",
        "GLOBAL_SHORTCUT_CHAIN_POPOUT",
        "UPDATER_DISABLED"
      ])
    );

    const opened = events.find((event) => event.code === "DEEP_LINK_OPENED");
    expect(opened?.detail).toBe("empty deep-link payload");
  });

  it("awaits deep-link registration and redacts callback payload", async () => {
    (window as Window & { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__ = {};
    listenMock.mockResolvedValue(undefined);
    registerMock.mockResolvedValue(undefined);
    onOpenUrlMock.mockImplementation(async (cb: (urls: string[]) => void) => {
      await Promise.resolve();
      cb(["openvibecoding://open/path?token=abc", "invalid-url"]);
    });

    const events: DesktopRuntimeEvent[] = [];
    await initDesktopRuntimeBridges((event) => events.push(event));

    expect(onOpenUrlMock).toHaveBeenCalledTimes(1);
    const opened = events.find((event) => event.code === "DEEP_LINK_OPENED");
    expect(opened).toMatchObject({ code: "DEEP_LINK_OPENED" });
    expect(opened?.detail).toContain("openvibecoding://open/path");
    expect(opened?.detail).not.toContain("token=abc");
    expect(opened?.detail).toContain("[REDACTED_DEEP_LINK]");
    expect(getCodes(events)).toContain("DEEP_LINK_READY");
  });

  it("emits unavailable warnings when individual plugin registration fails", async () => {
    (window as Window & { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__ = {};
    listenMock.mockRejectedValue(new Error("listen unavailable"));
    registerMock.mockRejectedValue(new Error("register unavailable"));
    onOpenUrlMock.mockRejectedValue(new Error("onOpenUrl unavailable"));

    const events: DesktopRuntimeEvent[] = [];
    await expect(initDesktopRuntimeBridges((event) => events.push(event))).resolves.toBeUndefined();

    expect(getCodes(events)).toEqual(
      expect.arrayContaining([
        "RUST_PANIC_LISTENER_UNAVAILABLE",
        "GLOBAL_SHORTCUT_UNAVAILABLE",
        "DEEP_LINK_UNAVAILABLE",
        "UPDATER_DISABLED"
      ])
    );
  });

  it("catches deep-link payload transform failures and emits payload warning", async () => {
    (window as Window & { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__ = {};
    listenMock.mockResolvedValue(undefined);
    registerMock.mockResolvedValue(undefined);
    onOpenUrlMock.mockImplementation(async (cb: (urls: string[]) => void) => {
      const corrupted = ["openvibecoding://open/path"] as unknown as string[] & {
        map: () => never;
      };
      corrupted.map = () => {
        throw new Error("boom");
      };
      cb(corrupted);
    });

    const events: DesktopRuntimeEvent[] = [];
    await initDesktopRuntimeBridges((event) => events.push(event));

    const invalid = events.find((event) => event.code === "DEEP_LINK_PAYLOAD_INVALID");
    expect(invalid?.level).toBe("warning");
    expect(invalid?.detail).toBe("Deep-link payload parse failed");
  });
});
