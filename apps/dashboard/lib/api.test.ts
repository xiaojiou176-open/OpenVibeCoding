import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchPmSessionEvents, fetchPmSessions, rollbackRun } from "./api";

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("dashboard api query/error contract", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("serializes status filter with both scalar and array aliases", async () => {
    const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(async () =>
      jsonResponse([]),
    );
    vi.stubGlobal("fetch", fetchMock);

    await fetchPmSessions({ status: ["active", "failed"] });
    const url = String(fetchMock.mock.calls[0]?.[0] ?? "");
    const parsed = new URL(url);
    expect(parsed.searchParams.getAll("status")).toEqual(["active", "failed"]);
    expect(parsed.searchParams.getAll("status[]")).toEqual(["active", "failed"]);
  });

  it("serializes event types with both scalar and array aliases", async () => {
    const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(async () =>
      jsonResponse([]),
    );
    vi.stubGlobal("fetch", fetchMock);

    await fetchPmSessionEvents("pm-1", { types: ["CHAIN_HANDOFF"] });
    const url = String(fetchMock.mock.calls[0]?.[0] ?? "");
    const parsed = new URL(url);
    expect(parsed.searchParams.getAll("types")).toEqual(["CHAIN_HANDOFF"]);
    expect(parsed.searchParams.getAll("types[]")).toEqual(["CHAIN_HANDOFF"]);
  });

  it("parses rollback error reason from api detail payload", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({ detail: { code: "ROLLBACK_FAILED", reason: "worktree_ref missing" } }, 422)),
    );

    await expect(rollbackRun("run-1")).rejects.toThrow("Rollback failed: 422 (worktree_ref missing)");
  });
});
