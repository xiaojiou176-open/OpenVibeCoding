import { describe, expect, it } from "vitest";
import { sanitizeUiError, uiErrorDetail } from "./uiError";

describe("uiError", () => {
  it("returns fallback for empty detail", () => {
    expect(sanitizeUiError("", "加载失败")).toBe("加载失败");
  });

  it("maps network-style messages", () => {
    expect(sanitizeUiError(new Error("Network timeout"), "加载失败")).toContain("未连接到本地服务");
    expect(sanitizeUiError(new Error("fetch failed"), "加载失败")).toContain("未连接到本地服务");
  });

  it("maps auth-style messages", () => {
    expect(sanitizeUiError(new Error("401 unauthorized"), "加载失败")).toContain("权限或认证异常");
    expect(sanitizeUiError(new Error("token invalid"), "加载失败")).toContain("权限或认证异常");
  });

  it("keeps generic fallback for unknown errors", () => {
    expect(sanitizeUiError(new Error("boom"), "加载失败")).toBe("加载失败");
  });

  it("maps backend 5xx-style messages", () => {
    expect(sanitizeUiError(new Error("API /path failed: 503"), "加载失败")).toContain("服务暂时不可用");
  });

  it("extracts detail from unknown payload", () => {
    expect(uiErrorDetail({ code: 1 })).toContain("[object Object]");
  });
});
