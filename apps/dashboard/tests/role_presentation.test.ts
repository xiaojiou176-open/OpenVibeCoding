import { describe, expect, it } from "vitest";

import { localizeRolePurpose } from "../lib/rolePresentation";

describe("role presentation localization", () => {
  it("returns the original purpose for english locale", () => {
    expect(localizeRolePurpose("WORKER", "Execute code and produce artifacts", "en")).toBe(
      "Execute code and produce artifacts",
    );
  });

  it("returns localized zh purpose for a known role", () => {
    expect(localizeRolePurpose("WORKER", "Execute code and produce artifacts", "zh-CN")).toContain(
      "负责在允许路径内完成具体改动",
    );
  });

  it("falls back to the original purpose for unknown zh role names", () => {
    expect(localizeRolePurpose("UNKNOWN_ROLE", "Fallback purpose", "zh-CN")).toBe("Fallback purpose");
  });
});
