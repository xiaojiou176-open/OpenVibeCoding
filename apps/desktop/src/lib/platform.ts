function resolveBasePlatformLabel(): string {
  if (typeof navigator === "undefined") {
    return "unknown";
  }
  const value = (((navigator as any).userAgentData?.platform as string | undefined) || navigator.platform || "").toLowerCase();
  if (value.includes("mac")) return "macos";
  if (value.includes("win")) return "windows";
  if (value.includes("linux")) return "linux";
  return value || "unknown";
}

let listenersBound = false;
let platformSyncHandler: (() => void) | null = null;

function syncPlatformAttributes(platformLabel: string) {
  if (typeof document === "undefined" || typeof window === "undefined") {
    return;
  }
  const root = document.documentElement;
  root.setAttribute("data-platform", platformLabel);
  root.setAttribute("data-dpr", String(Math.round(window.devicePixelRatio * 100) / 100));
  root.setAttribute("data-network", navigator.onLine ? "online" : "offline");
}

export async function initPlatformAttributes() {
  const fallback = resolveBasePlatformLabel();
  syncPlatformAttributes(fallback);

  if (typeof window === "undefined") {
    return;
  }

  try {
    const osPlugin = await import("@tauri-apps/plugin-os");
    const tauriPlatform = await osPlugin.platform();
    syncPlatformAttributes(tauriPlatform || fallback);
  } catch {
    syncPlatformAttributes(fallback);
  }

  if (listenersBound) {
    return;
  }
  platformSyncHandler = () =>
    syncPlatformAttributes(document.documentElement.getAttribute("data-platform") || fallback);
  window.addEventListener("online", platformSyncHandler);
  window.addEventListener("offline", platformSyncHandler);
  window.addEventListener("resize", platformSyncHandler);
  listenersBound = true;
}
