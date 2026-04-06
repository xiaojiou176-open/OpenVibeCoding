import { describe, expect, it, vi } from "vitest";

import { safeLoad } from "../lib/serverPageData";

describe("safeLoad contract", () => {
  it("returns loaded data when loader succeeds", async () => {
    const result = await safeLoad(async () => ({ ok: true }), { ok: false }, "Test data");
    expect(result.data).toEqual({ ok: true });
    expect(result.warning).toBeNull();
  });

  it("returns fallback and sanitized warning when loader throws", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    try {
      const result = await safeLoad(async () => {
        throw new Error("db timeout details");
      }, { ok: false }, "Test data");

      expect(result.data).toEqual({ ok: false });
      expect(result.warning).toBe("Test data is temporarily unavailable. Try again later.");
      expect(result.warning).not.toContain("db timeout details");
      expect(consoleSpy).toHaveBeenCalledWith("[safeLoad] Test data load failed: db timeout details");
    } finally {
      consoleSpy.mockRestore();
    }
  });
});
