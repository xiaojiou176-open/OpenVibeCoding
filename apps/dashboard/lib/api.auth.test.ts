import { afterEach, describe, expect, it, vi } from "vitest";

describe("dashboard api auth headers", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    delete process.env.CORTEXPILOT_API_TOKEN;
    delete process.env.CORTEXPILOT_E2E_API_TOKEN;
    delete process.env.NEXT_PUBLIC_CORTEXPILOT_OPERATOR_ROLE;
    delete process.env.NEXT_PUBLIC_CORTEXPILOT_API_TOKEN;
  });

  it("never forwards NEXT_PUBLIC token as Authorization header", async () => {
    const previousToken = process.env.NEXT_PUBLIC_CORTEXPILOT_API_TOKEN;
    process.env.NEXT_PUBLIC_CORTEXPILOT_API_TOKEN = "sensitive-client-token";

    vi.resetModules();
    const api = await import("./api");

    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => ({
      ok: true,
      status: 200,
      headers: { get: () => "application/json" },
      json: async () => ({ ok: true }),
    }));
    vi.stubGlobal("fetch", fetchMock);

    await api.fetchRuns();
    const requestInit = (fetchMock.mock.calls[0]?.[1] ?? {}) as RequestInit;
    expect(requestInit.headers).not.toMatchObject({
      Authorization: expect.stringContaining("sensitive-client-token"),
    });

    if (previousToken === undefined) {
      delete process.env.NEXT_PUBLIC_CORTEXPILOT_API_TOKEN;
    } else {
      process.env.NEXT_PUBLIC_CORTEXPILOT_API_TOKEN = previousToken;
    }
  });

  it("uses CORTEXPILOT_API_TOKEN as the primary server token", async () => {
    process.env.CORTEXPILOT_API_TOKEN = "cortexpilot-token";
    vi.stubGlobal("window", undefined);
    vi.resetModules();
    const api = await import("./api");

    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => {
      return new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    await api.fetchRuns();
    const requestInit = (fetchMock.mock.calls[0]?.[1] ?? {}) as RequestInit;
    expect(requestInit.headers).toMatchObject({
      Authorization: "Bearer cortexpilot-token",
    });
  });

  it("injects server Authorization header from CORTEXPILOT_API_TOKEN", async () => {
    process.env.CORTEXPILOT_API_TOKEN = "primary-server-token";
    process.env.CORTEXPILOT_E2E_API_TOKEN = "fallback-token";
    vi.stubGlobal("window", undefined);
    vi.resetModules();
    const api = await import("./api");

    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => {
      return new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    await api.fetchRuns();
    const requestInit = (fetchMock.mock.calls[0]?.[1] ?? {}) as RequestInit;
    expect(requestInit.headers).toMatchObject({
      Authorization: "Bearer primary-server-token",
    });
  });

  it("falls back to CORTEXPILOT_E2E_API_TOKEN on server when primary token is absent", async () => {
    delete process.env.CORTEXPILOT_API_TOKEN;
    process.env.CORTEXPILOT_E2E_API_TOKEN = "fallback-token";
    vi.stubGlobal("window", undefined);
    vi.resetModules();
    const api = await import("./api");

    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => {
      return new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    await api.fetchRuns();
    const requestInit = (fetchMock.mock.calls[0]?.[1] ?? {}) as RequestInit;
    expect(requestInit.headers).toMatchObject({
      Authorization: "Bearer fallback-token",
    });
  });

  it("does not inject server Authorization header on client", async () => {
    process.env.CORTEXPILOT_API_TOKEN = "primary-server-token";
    process.env.CORTEXPILOT_E2E_API_TOKEN = "fallback-token";
    vi.stubGlobal("window", {} as Window & typeof globalThis);
    vi.resetModules();
    const api = await import("./api");

    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => {
      return new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    await api.fetchRuns();
    const requestInit = (fetchMock.mock.calls[0]?.[1] ?? {}) as RequestInit;
    expect(requestInit.headers).not.toMatchObject({
      Authorization: expect.stringContaining("Bearer"),
    });
  });

  it("attaches operator role header only for mutation requests", async () => {
    process.env.NEXT_PUBLIC_CORTEXPILOT_OPERATOR_ROLE = "tech_lead";
    vi.stubGlobal("window", {} as Window & typeof globalThis);
    vi.resetModules();
    const api = await import("./api");

    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => {
      return new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    await api.fetchRuns();
    await api.rollbackRun("run-1");

    const readInit = (fetchMock.mock.calls[0]?.[1] ?? {}) as RequestInit;
    const mutationInit = (fetchMock.mock.calls[1]?.[1] ?? {}) as RequestInit;

    expect(readInit.headers).not.toMatchObject({
      "x-cortexpilot-role": expect.any(String),
    });
    expect(mutationInit.headers).toMatchObject({
      "x-cortexpilot-role": "TECH_LEAD",
    });
    expect(api.mutationExecutionCapability()).toEqual({
      executable: true,
      operatorRole: "TECH_LEAD",
    });
  });

  it("reports mutation capability unavailable when operator role env is missing", async () => {
    delete process.env.NEXT_PUBLIC_CORTEXPILOT_OPERATOR_ROLE;
    vi.resetModules();
    const api = await import("./api");
    expect(api.mutationExecutionCapability()).toEqual({
      executable: false,
      operatorRole: null,
    });
  });
});
