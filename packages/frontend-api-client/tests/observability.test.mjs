import test from "node:test";
import assert from "node:assert/strict";

import { buildFrontendLogEvent, emitFrontendLogEvent } from "../index.js";

test("buildFrontendLogEvent emits log_event.v2 defaults", () => {
  const event = buildFrontendLogEvent({
    event: "pm_send_attempt",
    surface: "dashboard",
    component: "pm_shell",
    run_id: "run_1",
    request_id: "req_1",
    trace_id: "trace_1",
  });

  assert.equal(event.schema_version, "log_event.v2");
  assert.equal(event.redaction_version, "redaction.v1");
  assert.equal(event.surface, "dashboard");
  assert.equal(event.service, "cortexpilot-dashboard");
  assert.equal(event.component, "pm_shell");
  assert.equal(event.event, "pm_send_attempt");
  assert.equal(event.lane, "runtime");
  assert.equal(event.source_kind, "app_log");
  assert.equal(event.correlation_kind, "run");
  assert.equal(event.run_id, "run_1");
  assert.equal(event.request_id, "req_1");
  assert.equal(event.trace_id, "trace_1");
  assert.equal(event.session_id, "");
  assert.equal(event.test_id, "");
});

test("emitFrontendLogEvent dispatches browser event and redacts sensitive metadata", () => {
  const captured = [];
  const consoleLines = [];
  const originalWindow = globalThis.window;
  const originalCustomEvent = globalThis.CustomEvent;
  const originalConsoleLog = console.log;

  class FakeCustomEvent {
    constructor(name, init) {
      this.type = name;
      this.detail = init?.detail;
    }
  }

  globalThis.window = {
    dispatchEvent(event) {
      captured.push(event);
    },
  };
  globalThis.CustomEvent = FakeCustomEvent;
  console.log = (value) => {
    consoleLines.push(String(value));
  };

  try {
    const event = emitFrontendLogEvent({
      surface: "desktop",
      component: "ux_telemetry",
      event: "pm_send_blocked",
      meta: { reason: "offline", api_key: "secret-value" },
    });
    assert.equal(captured.length, 1);
    assert.equal(captured[0].type, "cortexpilot:log-event");
    assert.equal(captured[0].detail.event, "pm_send_blocked");
    assert.equal(captured[0].detail.meta.api_key, "[REDACTED]");
    assert.match(consoleLines[0], /^CORTEXPILOT_LOG_EVENT /);
    assert.equal(event.meta.api_key, "[REDACTED]");
  } finally {
    globalThis.window = originalWindow;
    globalThis.CustomEvent = originalCustomEvent;
    console.log = originalConsoleLog;
  }
});

test("buildFrontendLogEvent rejects illegal enum values", () => {
  assert.throws(
    () => buildFrontendLogEvent({ surface: "frontend", component: "pm_shell", event: "pm_send_attempt" }),
    /surface must be one of/,
  );
  assert.throws(
    () => buildFrontendLogEvent({ surface: "dashboard", component: "pm_shell", event: "pm_send_attempt", source_kind: "raw" }),
    /source_kind must be one of/,
  );
  assert.throws(
    () => buildFrontendLogEvent({ surface: "dashboard", component: "pm_shell", event: "pm_send_attempt", meta: "raw" }),
    /meta must be an object/,
  );
});
