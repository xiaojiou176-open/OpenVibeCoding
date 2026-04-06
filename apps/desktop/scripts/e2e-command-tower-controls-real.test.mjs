import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const testFilePath = fileURLToPath(import.meta.url);
const scriptsDir = dirname(testFilePath);
const desktopDir = resolve(scriptsDir, "..");
const entryModulePath = resolve(desktopDir, "scripts", "e2e-command-tower-controls-real.mjs");

import {
  didPostMessageToExpectedSession,
  extractPmSessionIdFromCommandTowerUrl,
  isExecutedAsMain,
  resolveExpectedActivePmSessionId,
} from "./e2e-command-tower-controls-real.mjs";

describe("e2e-command-tower-controls-real", () => {
  it("resolves relative entry path as main-module invocation", () => {
    expect(
      isExecutedAsMain(
        entryModulePath,
        "./scripts/e2e-command-tower-controls-real.mjs",
        desktopDir,
      ),
    ).toBe(true);
  });

  it("resolveExpectedActivePmSessionId prefers clicked session id when desktop shell URL has no routed session", () => {
    const actual = resolveExpectedActivePmSessionId({
      pageUrl: "http://127.0.0.1:4173/command-tower",
      clickedSessionId: "pm_clicked_123",
      resolvedSessionId: "pm_seed_999",
    });

    expect(actual).toBe("pm_clicked_123");
  });

  it("resolveExpectedActivePmSessionId uses routed session id when URL includes command tower session route", () => {
    const actual = resolveExpectedActivePmSessionId({
      pageUrl: "http://127.0.0.1:4173/command-tower/sessions/pm_routed_456?tab=events",
      clickedSessionId: "pm_clicked_123",
      resolvedSessionId: "pm_seed_999",
    });

    expect(actual).toBe("pm_routed_456");
    expect(
      extractPmSessionIdFromCommandTowerUrl("http://127.0.0.1:4173/command-tower/sessions/pm_routed_456?tab=events"),
    ).toBe("pm_routed_456");
  });

  it("didPostMessageToExpectedSession validates POST against resolved expected session instead of stale fallback", () => {
    const actual = didPostMessageToExpectedSession(
      [
        {
          method: "POST",
          status: 200,
          url: "http://127.0.0.1:18500/api/pm/sessions/pm_clicked_123/messages",
        },
      ],
      "pm_clicked_123",
    );

    expect(actual).toEqual({
      messagePostSessionId: "pm_clicked_123",
      pass: true,
    });

    const staleFallbackResult = didPostMessageToExpectedSession(
      [
        {
          method: "POST",
          status: 200,
          url: "http://127.0.0.1:18500/api/pm/sessions/pm_clicked_123/messages",
        },
      ],
      "pm_seed_999",
    );

    expect(staleFallbackResult.pass).toBe(false);
    expect(staleFallbackResult.messagePostSessionId).toBe("pm_clicked_123");
  });
});
