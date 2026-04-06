import { describe, expect, it } from "vitest";

import { sanitizeTraceUrl } from "./safeUrl";

describe("sanitizeTraceUrl", () => {
  it("allows http/https URLs", () => {
    expect(sanitizeTraceUrl("https://trace.local/run/1")).toBe("https://trace.local/run/1");
    expect(sanitizeTraceUrl("http://trace.local/run/1")).toBe("http://trace.local/run/1");
  });

  it("blocks non-http protocols and malformed values", () => {
    expect(sanitizeTraceUrl("javascript:alert(1)")).toBe("");
    expect(sanitizeTraceUrl("data:text/html,<script>alert(1)</script>")).toBe("");
    expect(sanitizeTraceUrl("not a url")).toBe("");
  });
});
