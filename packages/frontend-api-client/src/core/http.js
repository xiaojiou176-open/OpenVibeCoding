import { FRONTEND_API_CONTRACT } from "@openvibecoding/frontend-api-contract";
import { emitFrontendLogEvent } from "./observability.js";

const READ_ONLY_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);
const MUTATION_ROLE_HEADERS = ["x-openvibecoding-role"];

function normalizeMutationRole(value) {
  if (typeof value !== "string") {
    return "";
  }
  const role = value.trim().toUpperCase();
  return role;
}

function headerExists(headers, targetKey) {
  const target = targetKey.toLowerCase();
  return Object.keys(headers).some((key) => key.toLowerCase() === target);
}

function toHeaderObject(headers) {
  if (!headers) {
    return {};
  }
  if (typeof Headers !== "undefined" && headers instanceof Headers) {
    const normalized = {};
    headers.forEach((value, key) => {
      normalized[key] = value;
    });
    return normalized;
  }
  if (Array.isArray(headers)) {
    return Object.fromEntries(headers);
  }
  if (typeof headers === "object") {
    return { ...headers };
  }
  return {};
}

function withMutationRoleHeader(headers, role) {
  const normalized = toHeaderObject(headers);
  for (const headerName of MUTATION_ROLE_HEADERS) {
    if (!headerExists(normalized, headerName)) {
      normalized[headerName] = role;
    }
  }
  return normalized;
}

function withCorrelationHeaders(headers, requestOptions = {}) {
  const normalized = toHeaderObject(headers);
  const runId = typeof requestOptions.runId === "string" ? requestOptions.runId.trim() : "";
  if (runId && !headerExists(normalized, FRONTEND_API_CONTRACT.headers.runId)) {
    normalized[FRONTEND_API_CONTRACT.headers.runId] = runId;
  }
  return normalized;
}

function parseErrorReason(payload) {
  if (!payload || typeof payload !== "object") {
    return "";
  }
  const detail = payload.detail && typeof payload.detail === "object" ? payload.detail : payload;
  for (const key of ["reason", "message", "code"]) {
    const value = detail[key];
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }
  return "";
}

async function resolveApiErrorMessage(response, fallback) {
  let reason = "";
  try {
    const contentType = response.headers?.get?.("content-type") || "";
    if (contentType.includes("application/json") && typeof response.json === "function") {
      reason = parseErrorReason(await response.json());
    } else if (typeof response.text === "function") {
      reason = (await response.text()).trim();
    }
  } catch {
    reason = "";
  }
  return reason ? `${fallback}: ${response.status} (${reason})` : `${fallback}: ${response.status}`;
}

function isAbortLikeError(error) {
  return Boolean(error && typeof error === "object" && "name" in error && error.name === "AbortError");
}

function stringifyErrorMessage(error) {
  if (error && typeof error === "object" && "message" in error && typeof error.message === "string") {
    return error.message;
  }
  return String(error);
}

export function createHttpCore(options) {
  const fetchImpl = options.fetchImpl || globalThis.fetch;
  const baseUrl = String(options.baseUrl || "").replace(/\/$/, "");
  const defaultTimeoutMs = Number.isFinite(options.defaultTimeoutMs)
    ? Math.max(0, Math.floor(options.defaultTimeoutMs))
    : 10_000;
  const auth = options.auth;
  const resolveMutationRole =
    typeof options.resolveMutationRole === "function" ? options.resolveMutationRole : () => undefined;
  const surface = typeof options.surface === "string" && options.surface.trim() ? options.surface.trim() : "dashboard";
  const component = typeof options.component === "string" && options.component.trim()
    ? options.component.trim()
    : "frontend_api_client";

  if (typeof fetchImpl !== "function") {
    throw new Error("fetch implementation is required");
  }

  function resolveTimeoutMs(value) {
    if (typeof value === "number" && Number.isFinite(value) && value > 0) {
      return Math.floor(value);
    }
    return defaultTimeoutMs;
  }

  function resolvePath(path) {
    if (!path.startsWith("/")) {
      return `/${path}`;
    }
    return path;
  }

  function getMutationRole() {
    return normalizeMutationRole(resolveMutationRole());
  }

  function canExecuteMutations() {
    return Boolean(getMutationRole());
  }

  async function request(method, path, requestOptions = {}) {
    const { signal: parentSignal, timeoutMs: _unusedTimeout, ...restRequestOptions } = requestOptions;
    const normalizedMethod =
      typeof method === "string" && method.trim() ? method.trim().toUpperCase() : "GET";
    const timeoutMs = resolveTimeoutMs(requestOptions.timeoutMs);
    const controller = new AbortController();
    let didTimeoutAbort = false;
    const signal =
      typeof AbortSignal !== "undefined" &&
      typeof AbortSignal.any === "function" &&
      parentSignal
        ? AbortSignal.any([controller.signal, parentSignal])
        : controller.signal;

    if (parentSignal && typeof AbortSignal.any !== "function") {
      if (parentSignal.aborted) {
        controller.abort();
      } else {
        parentSignal.addEventListener("abort", () => controller.abort(), { once: true });
      }
    }

    const timeoutHandle =
      timeoutMs > 0
        ? setTimeout(() => {
            didTimeoutAbort = true;
            controller.abort();
          }, timeoutMs)
        : null;

    try {
      const mutationRole = !READ_ONLY_METHODS.has(normalizedMethod) ? getMutationRole() : "";
      const headersWithCorrelation = withCorrelationHeaders(restRequestOptions.headers, requestOptions);
      const headers = mutationRole
        ? withMutationRoleHeader(headersWithCorrelation, mutationRole)
        : headersWithCorrelation;
      emitFrontendLogEvent({
        domain: "api",
        surface,
        component,
        event: "api_request_started",
        run_id: headers[FRONTEND_API_CONTRACT.headers.runId],
        request_id: headers[FRONTEND_API_CONTRACT.headers.requestId],
        trace_id: headers[FRONTEND_API_CONTRACT.headers.traceId],
        source_kind: "event_stream",
        meta: { method: normalizedMethod, path: resolvePath(path) },
      });
      const response = await fetchImpl(`${baseUrl}${resolvePath(path)}`, {
        method: normalizedMethod,
        cache: "no-store",
        credentials: FRONTEND_API_CONTRACT.network.fetchCredentials,
        signal,
        ...restRequestOptions,
        headers,
      });
      emitFrontendLogEvent({
        domain: "api",
        surface,
        component,
        event: "api_request_completed",
        level: response.ok ? "info" : "warn",
        run_id: headers[FRONTEND_API_CONTRACT.headers.runId],
        request_id: headers[FRONTEND_API_CONTRACT.headers.requestId],
        trace_id: headers[FRONTEND_API_CONTRACT.headers.traceId],
        source_kind: "event_stream",
        meta: { method: normalizedMethod, path: resolvePath(path), status: response.status, ok: response.ok },
      });
      return response;
    } catch (error) {
      const message = stringifyErrorMessage(error);
      emitFrontendLogEvent({
        domain: "api",
        surface,
        component,
        event: "api_request_failed",
        level: "error",
        run_id: requestOptions.runId,
        source_kind: "event_stream",
        meta: { method: normalizedMethod, path: resolvePath(path), message },
      });
      if (isAbortLikeError(error)) {
        if (requestOptions.signal?.aborted) {
          throw new Error(`API ${path} request failed: aborted`);
        }
        if (didTimeoutAbort) {
          throw new Error(`API ${path} request failed: timeout`);
        }
        throw new Error(`API ${path} request failed: aborted`);
      }
      throw new Error(`API ${path} request failed: ${message}`);
    } finally {
      if (timeoutHandle) {
        clearTimeout(timeoutHandle);
      }
    }
  }

  async function getJson(path, options = {}) {
    const response = await request("GET", path, {
      headers: auth.readOnlyHeaders(),
      signal: options.signal,
      timeoutMs: options.timeoutMs,
      runId: options.runId,
    });

    if (!response.ok) {
      throw new Error(await resolveApiErrorMessage(response, `API ${path} failed`));
    }
    return response.json();
  }

  async function postJson(path, payload, errorFallback, options = {}) {
    const response = await request("POST", path, {
      headers: auth.authJsonHeaders(),
      body: JSON.stringify(payload),
      signal: options.signal,
      timeoutMs: options.timeoutMs,
      runId: options.runId,
    });

    if (!response.ok) {
      throw new Error(await resolveApiErrorMessage(response, errorFallback));
    }
    return response.json();
  }

  return {
    request,
    getJson,
    postJson,
    canExecuteMutations,
    getMutationRole,
  };
}
