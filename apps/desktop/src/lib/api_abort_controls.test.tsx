import { describe, expect, it, vi, afterEach } from "vitest";
import { postDesktopPmMessage } from "./api";

describe("postDesktopPmMessage abort controls", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("cancels request when caller aborts", async () => {
    const aborted = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_input: string | URL | Request, init?: RequestInit) => {
        return await new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            aborted();
            reject(new DOMException("Aborted", "AbortError"));
          });
        });
      }),
    );

    const controller = new AbortController();
    const request = postDesktopPmMessage(
      "pm-1",
      { message: "hello", strict_acceptance: true },
      { signal: controller.signal, timeoutMs: 10_000 },
    );
    const rejection = request.then(
      () => ({ ok: true as const }),
      (error) => ({ ok: false as const, error }),
    );
    controller.abort();

    const result = await rejection;
    expect(result.ok).toBe(false);
    if (result.ok) throw new Error("expected request to reject");
    expect(result.error).toMatchObject({ name: "AbortError" });
    expect(aborted).toHaveBeenCalledTimes(1);
  });

  it("cancels request when timeout elapses", async () => {
    const aborted = vi.fn();
    vi.useFakeTimers();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_input: string | URL | Request, init?: RequestInit) => {
        return await new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            aborted();
            reject(new DOMException("Aborted", "AbortError"));
          });
        });
      }),
    );

    const request = postDesktopPmMessage(
      "pm-1",
      { message: "hello", strict_acceptance: true },
      { timeoutMs: 5 },
    );
    const rejection = request.then(
      () => ({ ok: true as const }),
      (error) => ({ ok: false as const, error }),
    );

    await vi.advanceTimersByTimeAsync(10);
    const result = await rejection;
    expect(result.ok).toBe(false);
    if (result.ok) throw new Error("expected request to reject");
    expect(result.error).toMatchObject({ name: "TimeoutError" });
    expect(aborted).toHaveBeenCalledTimes(1);
  });
});
