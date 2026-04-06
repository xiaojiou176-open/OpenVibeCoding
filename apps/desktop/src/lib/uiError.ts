export function uiErrorDetail(error: unknown): string {
  return error instanceof Error ? error.message : String(error ?? "");
}

export function sanitizeUiError(error: unknown, fallback: string): string {
  const detail = uiErrorDetail(error).trim();
  if (!detail) {
    return fallback;
  }
  const normalized = detail.toLowerCase();
  if (
    normalized.includes("network") ||
    normalized.includes("fetch") ||
    normalized.includes("timeout") ||
    normalized.includes("econnrefused")
  ) {
    return `${fallback}: unable to reach the local service. Start the backend first.`;
  }
  if (normalized.includes("401") || normalized.includes("403") || normalized.includes("auth") || normalized.includes("token")) {
    return `${fallback}: authentication or permission check failed. Confirm your sign-in state.`;
  }
  if (normalized.includes("failed: 5")) {
    return `${fallback}: the service is temporarily unavailable. Try again in a moment.`;
  }
  return fallback;
}
