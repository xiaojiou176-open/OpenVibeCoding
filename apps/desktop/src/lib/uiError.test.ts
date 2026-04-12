import { describe, expect, it } from "vitest";
import { sanitizeUiError, uiErrorDetail } from "./uiError";

describe("uiError", () => {
  it("returns fallback for empty detail", () => {
    expect(sanitizeUiError("", "加载失败")).toBe("加载失败");
  });

  it("maps network-style messages", () => {
    expect(sanitizeUiError(new Error("Network timeout"), "Load failed")).toContain("unable to reach the local service");
    expect(sanitizeUiError(new Error("fetch failed"), "Load failed")).toContain("unable to reach the local service");
  });

  it("maps auth-style messages", () => {
    expect(sanitizeUiError(new Error("401 unauthorized"), "Load failed")).toContain("authentication or permission check failed");
    expect(sanitizeUiError(new Error("token invalid"), "Load failed")).toContain("authentication or permission check failed");
  });

  it("keeps generic fallback for unknown errors", () => {
    expect(sanitizeUiError(new Error("boom"), "加载失败")).toBe("加载失败");
  });

  it("maps backend 5xx-style messages", () => {
    expect(sanitizeUiError(new Error("API /path failed: 503"), "Load failed")).toContain("service is temporarily unavailable");
  });

  it("extracts detail from unknown payload", () => {
    expect(uiErrorDetail({ code: 1 })).toContain("[object Object]");
  });
});
