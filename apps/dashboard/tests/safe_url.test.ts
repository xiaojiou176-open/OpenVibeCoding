import { describe, expect, it } from "vitest";

import { sanitizeTraceUrl } from "../lib/safeUrl";

describe("sanitizeTraceUrl", () => {
  it("returns empty string for blank-like input", () => {
    expect(sanitizeTraceUrl("")).toBe("");
    expect(sanitizeTraceUrl("   ")).toBe("");
  });

  it("keeps valid http/https urls", () => {
    expect(sanitizeTraceUrl("https://example.com/path?q=1")).toBe("https://example.com/path?q=1");
    expect(sanitizeTraceUrl("http://example.com")).toBe("http://example.com/");
  });

  it("blocks unsupported protocols", () => {
    expect(sanitizeTraceUrl("javascript:alert(1)")).toBe("");
    expect(sanitizeTraceUrl("file:///tmp/a")).toBe("");
  });

  it("returns empty string when URL parsing fails", () => {
    expect(sanitizeTraceUrl("not a valid url")).toBe("");
  });
});
