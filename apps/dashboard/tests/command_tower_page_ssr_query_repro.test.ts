import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";
import { metadata } from "../app/command-tower/page";

describe("command tower page SSR query reproduction", () => {
  it("uses fixed PM sessions fetch on first load and does not read searchParams", () => {
    const pagePath = path.resolve(process.cwd(), "app/command-tower/page.tsx");
    const source = fs.readFileSync(pagePath, "utf8");

    expect(source).toContain("safeLoad(() => fetchPmSessions({ limit: 40 })");
    expect(source).toContain("export default async function CommandTowerPage()");
    expect(source).toContain("const cookieStore = await cookies()");
    expect(source).not.toContain("searchParams");
    expect(source).not.toContain("project_key");
    expect(source).not.toContain("status[]");
    expect(source).not.toContain("sort");
  });

  it("publishes route-level metadata for discoverability", () => {
    expect(metadata.title).toBe("Command Tower | CortexPilot");
    expect(String(metadata.description)).toContain("operator visibility");
  });
});
