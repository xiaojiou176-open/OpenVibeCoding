import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

describe("command tower session page resilience", () => {
  it("uses settled loading with safe fallbacks instead of fail-fast Promise.all", () => {
    const pagePath = path.resolve(process.cwd(), "app/command-tower/sessions/[id]/page.tsx");
    const source = fs.readFileSync(pagePath, "utf8");

    expect(source).toContain("Promise.allSettled");
    expect(source).toContain("safeLoad(() => fetchPmSession(id)");
    expect(source).toContain("safeLoad(() => fetchPmSessionEvents(id, { limit: 800, tail: true })");
    expect(source).toContain("alert alert-warning");
    expect(source).not.toContain("const [detail, events, graph, metrics] = await Promise.all([");
  });
});
