export const API_BASE = "http://127.0.0.1:10000";

type MockResponse = {
  ok: boolean;
  status: number;
  headers?: { get: (name: string) => string };
  json?: () => Promise<unknown>;
  text?: () => Promise<string>;
};

export function jsonResponse(payload: unknown, status = 200): MockResponse {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => "application/json" },
    json: async () => payload,
  };
}

export function extractCall(calls: unknown[][], index: number): { url: string; init: RequestInit } {
  const rawCall = calls[index];
  if (!Array.isArray(rawCall) || rawCall.length < 1) {
    throw new Error(`missing fetch call #${index}`);
  }

  const url = String(rawCall?.[0] ?? "");
  const init = ((rawCall?.[1] ?? {}) as RequestInit) ?? {};
  return { url, init };
}
