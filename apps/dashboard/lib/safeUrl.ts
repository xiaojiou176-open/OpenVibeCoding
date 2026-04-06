const ALLOWED_EXTERNAL_PROTOCOLS = new Set(["http:", "https:"]);

export function sanitizeTraceUrl(raw: string): string {
  const value = String(raw || "").trim();
  if (!value) {
    return "";
  }
  try {
    const parsed = new URL(value);
    if (!ALLOWED_EXTERNAL_PROTOCOLS.has(parsed.protocol)) {
      return "";
    }
    return parsed.toString();
  } catch (e) {
    console.debug("sanitizeTraceUrl parse failed:", e);
    return "";
  }
}
