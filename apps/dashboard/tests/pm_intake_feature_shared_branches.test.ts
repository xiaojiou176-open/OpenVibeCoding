import { describe, expect, it } from "vitest";
import {
  buildChainNodes,
  buildSessionMiniChain,
  inferActiveRole,
  mergeChatTimeline,
  sanitizeErrorMessage,
  shortTime,
  splitLines,
  type ChatItem,
} from "../app/pm/components/PMIntakeFeature.shared";
import type { EventRecord, PmSessionSummary } from "../lib/types";

describe("pm intake shared helpers", () => {
  const sessionBase = {
    run_count: 1,
    running_runs: 0,
    failed_runs: 0,
    success_runs: 0,
    blocked_runs: 0,
  };

  it("normalizes and sanitizes error messages for fallback paths", () => {
    expect(sanitizeErrorMessage(undefined, "Create failed")).toBe("Create failed");
    expect(sanitizeErrorMessage(new Error("network timeout"), "Create failed")).toBe("Create failed: network error, please try again.");
    expect(sanitizeErrorMessage(new Error("auth 403"), "Create failed")).toBe(
      "Create failed: authentication or permission error, please confirm your session."
    );
    expect(sanitizeErrorMessage(new Error("当前没有可执行的 intake"), "Create failed")).toBe(
      "No executable intake is available yet; the session has not been created."
    );
    expect(sanitizeErrorMessage(new Error("Custom browser policy JSON is invalid"), "Create failed")).toBe(
      "Custom browser policy JSON is invalid"
    );
    expect(splitLines("a,b\n c ")).toEqual(["a", "b", "c"]);
  });

  it("merges chat timeline with echo-dedup, ordering, and empty-remote fallback", () => {
    const local: ChatItem[] = [
      {
        id: "local-1",
        role: "PM",
        text: "hello",
        createdAt: "2026-03-01T10:00:00.000Z",
        kind: "message",
        origin: "local",
      },
    ];
    expect(mergeChatTimeline(local, [])).toBe(local);

    const remote: ChatItem[] = [
      {
        id: "remote-1",
        role: "PM",
        text: "hello",
        createdAt: "2026-03-01T10:00:20.000Z",
        kind: "message",
        origin: "remote",
      },
      {
        id: "remote-2",
        role: "OpenVibeCoding Command Tower",
        text: "reply",
        createdAt: "2026-03-01T10:01:00.000Z",
        kind: "message",
        origin: "remote",
      },
    ];

    const merged = mergeChatTimeline(local, remote);
    expect(merged).toHaveLength(2);
    expect(merged[0].origin).toBe("remote");
    expect(merged[1].text).toBe("reply");
  });

  it("builds chain/session state for terminal, active, failed, and unknown statuses", () => {
    const nodes = buildChainNodes("TECH_LEAD", "active");
    expect(nodes.map((item) => item.state)).toEqual(["done", "active", "idle", "idle", "idle"]);
    expect(buildChainNodes("PM", "done").every((item) => item.state === "done")).toBe(true);
    expect(buildChainNodes("PM", "archived").every((item) => item.state === "done")).toBe(true);

    const activeSession: PmSessionSummary = { pm_session_id: "pm-1", status: "active", current_role: "WORKER", ...sessionBase };
    expect(buildSessionMiniChain(activeSession)).toEqual(["done", "done", "active", "idle", "idle"]);

    const failedSession: PmSessionSummary = { pm_session_id: "pm-2", status: "failed", current_role: "REVIEWER", ...sessionBase };
    expect(buildSessionMiniChain(failedSession)).toEqual(["done", "done", "done", "failed", "idle"]);

    const archivedSession: PmSessionSummary = { pm_session_id: "pm-3", status: "archived", ...sessionBase };
    expect(buildSessionMiniChain(archivedSession)).toEqual(["done", "done", "done", "done", "done"]);

    const unknownSession = { pm_session_id: "pm-4", status: "unknown", ...sessionBase } as unknown as PmSessionSummary;
    expect(buildSessionMiniChain(unknownSession)).toEqual(["idle", "idle", "idle", "idle", "idle"]);
  });

  it("infers active role from event context with fallback and formats short time safely", () => {
    const events: EventRecord[] = [
      { event: "CHAIN_HANDOFF", ts: "2026-03-01T10:00:00.000Z", context: { current_role: "worker" } },
      { event: "CHAIN_HANDOFF", ts: "2026-03-01T10:01:00.000Z", context: { to_role: "reviewer" } },
    ];
    expect(inferActiveRole(events, "pm")).toBe("REVIEWER");
    expect(inferActiveRole([{ event: "noop", ts: "2026-03-01T10:01:00.000Z", context: null }] as EventRecord[], "pm")).toBe("PM");
    expect(shortTime(undefined)).toBe("--:--");
    expect(shortTime("not-a-time")).toBe("--:--");
  });
});
