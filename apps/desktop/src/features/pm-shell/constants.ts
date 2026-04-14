export const COMPOSER_MAX_CHARS = 4000;
export const SCROLL_FOLLOW_THRESHOLD_PX = 100;
export const DRAFT_SAVE_INTERVAL_MS = 30_000;
export const DRAFT_STORAGE_PREFIX = "openvibecoding.desktop.draft";
export const ONBOARDING_STORAGE_KEY = "openvibecoding.desktop.onboarding.dismissed";
export const CHAIN_PANEL_IDLE_DELAY_MS = 200;
export const FIRST_SESSION_ALLOWED_PATHS = ["apps/desktop/src"] as const;

export function isAbortRequestError(error: unknown): boolean {
  return (
    error instanceof Error &&
    (error.name === "AbortError" || /request failed: aborted/i.test(error.message))
  );
}

export function isTimeoutRequestError(error: unknown): boolean {
  return (
    error instanceof Error &&
    (error.name === "TimeoutError" || /request failed: timeout/i.test(error.message))
  );
}

export function draftStorageKey(workspaceId: string, sessionId: string): string {
  return `${DRAFT_STORAGE_PREFIX}:${workspaceId}:${sessionId}`;
}
