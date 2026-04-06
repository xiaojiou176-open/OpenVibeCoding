export function uiErrorDetail(error: unknown): string {
  return error instanceof Error ? error.message : String(error ?? "");
}

export function sanitizeUiError(error: unknown, fallback: string): string {
  const detail = uiErrorDetail(error).trim();
  if (!detail) {
    return fallback;
  }
  const normalized = detail.toLowerCase();
  if (normalized.includes("network") || normalized.includes("fetch") || normalized.includes("timeout")) {
    return `${fallback}: network issue. Try again later.`;
  }
  if (normalized.includes("401") || normalized.includes("403") || normalized.includes("auth") || normalized.includes("token")) {
    return `${fallback}: authentication or permission issue. Confirm the current sign-in state.`;
  }
  return fallback;
}
