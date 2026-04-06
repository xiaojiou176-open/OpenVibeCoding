import { FRONTEND_API_CONTRACT } from "@cortexpilot/frontend-api-contract";

function randomToken(prefix) {
  if (typeof globalThis.crypto?.randomUUID === "function") {
    return globalThis.crypto.randomUUID();
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function randomHex(length) {
  return randomToken("hex").replace(/-/g, "").slice(0, length).padEnd(length, "0");
}

export function createAuthCore(options = {}) {
  const resolveToken =
    typeof options.resolveToken === "function" ? options.resolveToken : () => undefined;

  function resolveBearerToken() {
    const token = resolveToken();
    if (token && String(token).trim()) {
      return String(token).trim();
    }
    return "";
  }

  function createTraceContext() {
    const requestId = randomToken("req");
    const traceId = randomHex(32);
    const spanId = randomHex(16);
    return {
      [FRONTEND_API_CONTRACT.headers.requestId]: requestId,
      [FRONTEND_API_CONTRACT.headers.traceId]: traceId,
      [FRONTEND_API_CONTRACT.headers.traceparent]: `00-${traceId}-${spanId}-01`,
    };
  }

  function authHeaders(extra = {}) {
    const token = resolveBearerToken();
    if (token) {
      return {
        ...createTraceContext(),
        ...extra,
        Authorization: `Bearer ${token}`,
      };
    }
    return {
      ...createTraceContext(),
      ...extra,
    };
  }

  function readOnlyHeaders(extra = {}) {
    const token = resolveBearerToken();
    if (!token) {
      return { ...extra };
    }
    return authHeaders(extra);
  }

  function authJsonHeaders(extra = {}) {
    return authHeaders({ "Content-Type": "application/json", ...extra });
  }

  return {
    authHeaders,
    authJsonHeaders,
    readOnlyHeaders,
  };
}
