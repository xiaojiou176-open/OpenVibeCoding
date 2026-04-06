import { invoke } from "@tauri-apps/api/core";
type RuntimeEventLevel = "info" | "warning" | "error";

export type DesktopRuntimeEvent = {
  code: string;
  detail: string;
  level?: RuntimeEventLevel;
};

type RuntimeEventHandler = (event: DesktopRuntimeEvent) => void;
type PluginName = "RUST_PANIC_LISTENER" | "GLOBAL_SHORTCUT" | "DEEP_LINK";

function emitRuntimeEvent(handler: RuntimeEventHandler | undefined, event: DesktopRuntimeEvent) {
  if (handler) {
    handler(event);
  }
}

export function isTauriRuntime(): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  const internals = (window as typeof window & { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__;
  return Boolean(internals) && typeof invoke === "function";
}

function sanitizeDeepLink(url: string): string {
  try {
    const parsed = new URL(url);
    return `${parsed.protocol}//${parsed.host}${parsed.pathname}`;
  } catch {
    return "[REDACTED_DEEP_LINK]";
  }
}

function getUnavailableDetail(name: PluginName): string {
  switch (name) {
    case "RUST_PANIC_LISTENER":
      return "Rust panic listener unavailable; fallback to ErrorBoundary only";
    case "GLOBAL_SHORTCUT":
      return "Global shortcut plugin unavailable; fallback to in-app hotkeys";
    case "DEEP_LINK":
      return "Deep-link plugin unavailable";
    default:
      return "Runtime plugin unavailable";
  }
}

function getSkipDetail(name: PluginName): string {
  switch (name) {
    case "RUST_PANIC_LISTENER":
      return "Rust panic listener skipped; non-Tauri runtime detected";
    case "GLOBAL_SHORTCUT":
      return "Global shortcut plugin skipped; non-Tauri runtime detected";
    case "DEEP_LINK":
      return "Deep-link plugin skipped; non-Tauri runtime detected";
    default:
      return "Runtime plugin skipped; non-Tauri runtime detected";
  }
}

async function safeRegisterPlugin(
  name: PluginName,
  fn: () => Promise<void>,
  handler?: RuntimeEventHandler
) {
  try {
    await fn();
  } catch {
    emitRuntimeEvent(handler, {
      code: `${name}_UNAVAILABLE`,
      detail: getUnavailableDetail(name),
      level: "warning"
    });
  }
}

export async function initDesktopRuntimeBridges(handler?: RuntimeEventHandler) {
  if (!isTauriRuntime()) {
    (["RUST_PANIC_LISTENER", "GLOBAL_SHORTCUT", "DEEP_LINK"] as PluginName[]).forEach((name) => {
      emitRuntimeEvent(handler, {
        code: `${name}_SKIPPED`,
        detail: getSkipDetail(name),
        level: "warning"
      });
    });
    emitRuntimeEvent(handler, {
      code: "UPDATER_DISABLED",
      detail: "Updater runtime check disabled until signed endpoint/pubkey is configured"
    });
    return;
  }

  await safeRegisterPlugin("RUST_PANIC_LISTENER", async () => {
    const eventApi: any = await import("@tauri-apps/api/event");
    if (typeof eventApi.listen !== "function") {
      throw new Error("listen unavailable");
    }
    await eventApi.listen("rust-panic", (event: any) => {
      const payload = typeof event?.payload === "string" ? event.payload : "Rust panic captured";
      emitRuntimeEvent(handler, {
        code: "RUST_PANIC",
        detail: payload,
        level: "error"
      });
    });
    emitRuntimeEvent(handler, {
      code: "RUST_PANIC_LISTENER_READY",
      detail: "Rust panic listener initialized"
    });
  }, handler);

  await safeRegisterPlugin("GLOBAL_SHORTCUT", async () => {
    const shortcutApi: any = await import("@tauri-apps/plugin-global-shortcut");
    if (typeof shortcutApi.register !== "function") {
      throw new Error("register unavailable");
    }
    await shortcutApi.register("CommandOrControl+Shift+D", () => {
      emitRuntimeEvent(handler, {
        code: "GLOBAL_SHORTCUT_CHAIN_POPOUT",
        detail: "Detected global shortcut CommandOrControl+Shift+D"
      });
    });
    emitRuntimeEvent(handler, {
      code: "GLOBAL_SHORTCUT_READY",
      detail: "Global shortcut bridge initialized"
    });
  }, handler);

  await safeRegisterPlugin("DEEP_LINK", async () => {
    const deepLinkApi: any = await import("@tauri-apps/plugin-deep-link");
    if (typeof deepLinkApi.onOpenUrl !== "function") {
      throw new Error("onOpenUrl unavailable");
    }
    await deepLinkApi.onOpenUrl((urls: string[]) => {
      try {
        const detail =
          Array.isArray(urls) && urls.length > 0
            ? urls.map((item) => sanitizeDeepLink(item)).join(", ")
            : "empty deep-link payload";
        emitRuntimeEvent(handler, { code: "DEEP_LINK_OPENED", detail });
      } catch {
        emitRuntimeEvent(handler, {
          code: "DEEP_LINK_PAYLOAD_INVALID",
          detail: "Deep-link payload parse failed",
          level: "warning"
        });
      }
    });
    emitRuntimeEvent(handler, {
      code: "DEEP_LINK_READY",
      detail: "Deep-link bridge initialized"
    });
  }, handler);

  emitRuntimeEvent(handler, {
    code: "UPDATER_DISABLED",
    detail: "Updater runtime check disabled until signed endpoint/pubkey is configured"
  });
}
