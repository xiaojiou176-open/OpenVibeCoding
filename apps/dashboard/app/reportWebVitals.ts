import type { NextWebVitalsMetric } from "next/app";
import { resolveDashboardApiBase } from "../lib/env";

const DEFAULT_API_BASE = "http://127.0.0.1:18180";
const PAGE_VIEW_ID_KEY = "cortexpilot_rum_page_view_id";

function resolveApiBase(): string {
  return resolveDashboardApiBase() || DEFAULT_API_BASE;
}

function safeNowIso(): string {
  try {
    return new Date().toISOString();
  } catch {
    return "";
  }
}

function createPageViewId(): string {
  if (typeof globalThis.crypto?.randomUUID === "function") {
    return globalThis.crypto.randomUUID();
  }
  return `pv-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function resolvePageViewId(): string {
  if (typeof window === "undefined") {
    return "";
  }
  try {
    const existing = window.sessionStorage.getItem(PAGE_VIEW_ID_KEY);
    if (existing) {
      return existing;
    }
    const next = createPageViewId();
    window.sessionStorage.setItem(PAGE_VIEW_ID_KEY, next);
    return next;
  } catch {
    return "";
  }
}

export function reportWebVitals(metric: NextWebVitalsMetric): void {
  if (typeof window === "undefined") {
    return;
  }

  const endpoint = `${resolveApiBase()}/api/rum/web-vitals`;
  const payload = {
    ...metric,
    ts: safeNowIso(),
    page_view_id: resolvePageViewId(),
    pathname: window.location.pathname,
    href: window.location.href,
    user_agent: window.navigator.userAgent,
  };

  try {
    const body = JSON.stringify(payload);
    if (typeof navigator.sendBeacon === "function") {
      const blob = new Blob([body], { type: "application/json" });
      navigator.sendBeacon(endpoint, blob);
      return;
    }
    void fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      keepalive: true,
    });
  } catch {
    // RUM is best-effort only.
  }
}
