import { describe, expect, it } from "vitest";

import { sanitizeUiError, uiErrorDetail } from "../lib/uiError";

describe("uiError contract", () => {
  it("extracts detail from Error and unknown values", () => {
    expect(uiErrorDetail(new Error("boom"))).toBe("boom");
    expect(uiErrorDetail("text error")).toBe("text error");
  });

  it("maps network and auth issues to safe actionable messages", () => {
    expect(sanitizeUiError(new Error("network timeout"), "Load failed")).toBe("Load failed: network issue. Try again later.");
    expect(sanitizeUiError(new Error("401 unauthorized"), "Load failed")).toBe("Load failed: authentication or permission issue. Confirm the current sign-in state.");
  });

  it("falls back to generic safe message for unknown failures", () => {
    expect(sanitizeUiError(new Error("sql state 42p01"), "Load failed")).toBe("Load failed");
    expect(sanitizeUiError(null, "Load failed")).toBe("Load failed");
  });
});
