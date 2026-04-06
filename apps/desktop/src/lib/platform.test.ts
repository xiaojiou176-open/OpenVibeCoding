import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { platformMock } = vi.hoisted(() => ({
  platformMock: vi.fn<() => Promise<string>>()
}));

vi.mock("@tauri-apps/plugin-os", () => ({
  platform: platformMock,
}));

const originalNavigator = globalThis.navigator;

describe("platform attributes init", () => {
  beforeEach(() => {
    vi.resetModules();
    platformMock.mockReset();
    Object.defineProperty(globalThis, "navigator", {
      configurable: true,
      value: {
        ...originalNavigator,
        platform: "MacIntel",
        onLine: true,
        userAgentData: undefined,
      },
    });
  });

  afterEach(() => {
    Object.defineProperty(globalThis, "navigator", {
      configurable: true,
      value: originalNavigator,
    });
  });

  it("is idempotent for event listener binding", async () => {
    platformMock.mockResolvedValue("macos");
    const addListenerSpy = vi.spyOn(window, "addEventListener");
    const { initPlatformAttributes } = await import("./platform");

    await initPlatformAttributes();
    await initPlatformAttributes();

    expect(document.documentElement.getAttribute("data-platform")).toBe("macos");
    expect(document.documentElement.getAttribute("data-dpr")).not.toBeNull();
    expect(document.documentElement.getAttribute("data-network")).toBe("online");
    expect(addListenerSpy.mock.calls.filter(([event]) => event === "online")).toHaveLength(1);
    expect(addListenerSpy.mock.calls.filter(([event]) => event === "offline")).toHaveLength(1);
    expect(addListenerSpy.mock.calls.filter(([event]) => event === "resize")).toHaveLength(1);
  });

  it("falls back to navigator platform when os plugin rejects", async () => {
    platformMock.mockRejectedValue(new Error("plugin unavailable"));
    const { initPlatformAttributes } = await import("./platform");

    await initPlatformAttributes();

    expect(document.documentElement.getAttribute("data-platform")).toBe("macos");
  });

  it("uses plugin platform when provided and falls back when empty", async () => {
    platformMock.mockResolvedValueOnce("windows").mockResolvedValueOnce("");

    const first = await import("./platform");
    await first.initPlatformAttributes();
    expect(document.documentElement.getAttribute("data-platform")).toBe("windows");

    vi.resetModules();
    Object.defineProperty(globalThis, "navigator", {
      configurable: true,
      value: {
        ...originalNavigator,
        platform: "Linux x86_64",
        onLine: true,
        userAgentData: undefined,
      },
    });

    const second = await import("./platform");
    await second.initPlatformAttributes();
    expect(document.documentElement.getAttribute("data-platform")).toBe("linux");
  });

  it("resolves unknown label and reacts to online/offline/resize events", async () => {
    platformMock.mockRejectedValue(new Error("plugin unavailable"));
    Object.defineProperty(globalThis, "navigator", {
      configurable: true,
      value: {
        ...originalNavigator,
        platform: "",
        onLine: false,
        userAgentData: { platform: "" },
      },
    });

    Object.defineProperty(window, "devicePixelRatio", {
      configurable: true,
      value: 1.234,
    });

    const { initPlatformAttributes } = await import("./platform");
    await initPlatformAttributes();

    expect(document.documentElement.getAttribute("data-platform")).toBe("unknown");
    expect(document.documentElement.getAttribute("data-dpr")).toBe("1.23");
    expect(document.documentElement.getAttribute("data-network")).toBe("offline");

    Object.defineProperty(globalThis, "navigator", {
      configurable: true,
      value: {
        ...originalNavigator,
        platform: "",
        onLine: true,
        userAgentData: { platform: "" },
      },
    });
    window.dispatchEvent(new Event("online"));
    expect(document.documentElement.getAttribute("data-network")).toBe("online");

    Object.defineProperty(window, "devicePixelRatio", {
      configurable: true,
      value: 2.456,
    });
    window.dispatchEvent(new Event("resize"));
    expect(document.documentElement.getAttribute("data-dpr")).toBe("2.46");
  });
});
