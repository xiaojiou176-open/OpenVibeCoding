const LOG_EVENT_NAME = "cortexpilot:log-event";
const LOG_PREFIX = "CORTEXPILOT_LOG_EVENT ";
const REDACTION_VERSION = "redaction.v1";
const SCHEMA_VERSION = "log_event.v2";
const SENSITIVE_KEY_PATTERN = /(token|secret|password|credential|api[_-]?key|bearer)/i;
const ALLOWED_DOMAINS = new Set(["runtime", "api", "ui", "desktop", "ci", "e2e", "test", "governance"]);
const ALLOWED_SURFACES = new Set(["backend", "dashboard", "desktop", "ci", "tooling"]);
const ALLOWED_SOURCE_KINDS = new Set(["app_log", "test_log", "ci_log", "artifact_manifest", "event_stream"]);
const ALLOWED_LANES = new Set(["runtime", "error", "access", "e2e", "ci", "governance"]);
const ALLOWED_CORRELATION_KINDS = new Set(["run", "session", "test", "request", "trace", "none"]);

function sanitizeValue(value) {
  if (Array.isArray(value)) {
    return value.map((item) => sanitizeValue(item));
  }
  if (value && typeof value === "object") {
    return sanitizeMeta(value);
  }
  return value;
}

function sanitizeMeta(meta) {
  if (meta == null) {
    return {};
  }
  if (typeof meta !== "object" || Array.isArray(meta)) {
    throw new Error("[frontend-log-event] meta must be an object");
  }
  const sanitized = {};
  for (const [key, value] of Object.entries(meta)) {
    sanitized[key] = SENSITIVE_KEY_PATTERN.test(key) ? "[REDACTED]" : sanitizeValue(value);
  }
  return sanitized;
}

function normalizeOptionalString(value) {
  return typeof value === "string" && value.trim() ? value.trim() : "";
}

function normalizeRequiredString(name, value, fallback = "") {
  if (typeof value === "string" && value.trim()) {
    return value.trim();
  }
  if (fallback) {
    return fallback;
  }
  throw new Error(`[frontend-log-event] ${name} must be a non-empty string`);
}

function normalizeEnum(name, value, allowedValues, fallback) {
  const normalized = normalizeRequiredString(name, value, fallback);
  if (!allowedValues.has(normalized)) {
    throw new Error(`[frontend-log-event] ${name} must be one of: ${Array.from(allowedValues).join(", ")}`);
  }
  return normalized;
}

function inferService(surface) {
  if (surface === "dashboard") return "cortexpilot-dashboard";
  if (surface === "desktop") return "cortexpilot-desktop";
  if (surface === "ci") return "cortexpilot-ci";
  return "cortexpilot-tooling";
}

function inferLane(domain, inputLane) {
  if (typeof inputLane === "string" && inputLane.trim()) {
    return normalizeEnum("lane", inputLane, ALLOWED_LANES, "runtime");
  }
  if (domain === "e2e") return "e2e";
  if (domain === "ci") return "ci";
  if (domain === "governance") return "governance";
  return "runtime";
}

function inferCorrelationKind(input) {
  if (typeof input.correlation_kind === "string" && input.correlation_kind.trim()) {
    return normalizeEnum("correlation_kind", input.correlation_kind, ALLOWED_CORRELATION_KINDS, "none");
  }
  if (normalizeOptionalString(input.run_id)) return "run";
  if (normalizeOptionalString(input.session_id)) return "session";
  if (normalizeOptionalString(input.test_id)) return "test";
  if (normalizeOptionalString(input.request_id)) return "request";
  if (normalizeOptionalString(input.trace_id)) return "trace";
  return "none";
}

export function buildFrontendLogEvent(input = {}) {
  const domain = normalizeEnum("domain", input.domain, ALLOWED_DOMAINS, "ui");
  const surface = normalizeEnum("surface", input.surface, ALLOWED_SURFACES, "dashboard");
  const service = normalizeRequiredString("service", input.service, inferService(surface));
  const component = normalizeRequiredString("component", input.component, "frontend_api_client");
  const event = normalizeRequiredString("event", input.event);
  const sourceKind = normalizeEnum("source_kind", input.source_kind, ALLOWED_SOURCE_KINDS, "app_log");
  const lane = inferLane(domain, input.lane);
  const correlationKind = inferCorrelationKind(input);

  return {
    ts: new Date().toISOString(),
    level: input.level || "info",
    domain,
    surface,
    service,
    component,
    event,
    lane,
    run_id: normalizeOptionalString(input.run_id),
    request_id: normalizeOptionalString(input.request_id),
    trace_id: normalizeOptionalString(input.trace_id),
    session_id: normalizeOptionalString(input.session_id),
    test_id: normalizeOptionalString(input.test_id),
    source_kind: sourceKind,
    artifact_kind: normalizeOptionalString(input.artifact_kind),
    correlation_kind: correlationKind,
    meta: sanitizeMeta(input.meta),
    redaction_version: REDACTION_VERSION,
    schema_version: SCHEMA_VERSION,
  };
}

export function emitFrontendLogEvent(input = {}) {
  const event = buildFrontendLogEvent(input);
  if (typeof window !== "undefined" && typeof window.dispatchEvent === "function" && typeof CustomEvent === "function") {
    window.dispatchEvent(new CustomEvent(LOG_EVENT_NAME, { detail: event }));
  }
  if (typeof console !== "undefined" && typeof console.log === "function") {
    console.log(`${LOG_PREFIX}${JSON.stringify(event)}`);
  }
  return event;
}
