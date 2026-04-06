import { afterEach, describe, expect, it } from "vitest";

import { FRONTEND_API_CONTRACT } from "@cortexpilot/frontend-api-contract";

import { resolveDesktopApiBase, resolveDesktopApiToken } from "./env";

const ORIGINAL_API_BASE = process.env.VITE_CORTEXPILOT_API_BASE;
const ORIGINAL_API_TOKEN = process.env.VITE_CORTEXPILOT_API_TOKEN;

function restoreEnv(): void {
  if (ORIGINAL_API_BASE === undefined) delete process.env.VITE_CORTEXPILOT_API_BASE;
  else process.env.VITE_CORTEXPILOT_API_BASE = ORIGINAL_API_BASE;

  if (ORIGINAL_API_TOKEN === undefined) delete process.env.VITE_CORTEXPILOT_API_TOKEN;
  else process.env.VITE_CORTEXPILOT_API_TOKEN = ORIGINAL_API_TOKEN;
}

describe("desktop env helpers", () => {
  afterEach(() => {
    restoreEnv();
  });

  it("uses process env fallback for api base and trims trailing slashes", () => {
    process.env.VITE_CORTEXPILOT_API_BASE = " https://desktop.example/api/// ";

    expect(resolveDesktopApiBase()).toBe("https://desktop.example/api");
  });

  it("falls back to the frontend contract default when api base is missing", () => {
    delete process.env.VITE_CORTEXPILOT_API_BASE;

    expect(resolveDesktopApiBase()).toBe(FRONTEND_API_CONTRACT.defaultApiBase);
  });

  it("reads the desktop api token from process env fallback", () => {
    process.env.VITE_CORTEXPILOT_API_TOKEN = " desktop-token ";

    expect(resolveDesktopApiToken()).toBe("desktop-token");
  });
});
