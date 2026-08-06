import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchWithTimeout } from "./util";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("fetchWithTimeout", () => {
  it("resolves normally when the request completes before the timeout", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("ok", { status: 200 })),
    );
    const res = await fetchWithTimeout("https://example.com", {}, 5000);
    expect(res.status).toBe(200);
  });

  it("aborts the request once it exceeds the timeout, instead of hanging forever", async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "fetch",
      vi.fn((_url: string, init?: RequestInit) => {
        return new Promise((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            reject(new DOMException("Aborted", "AbortError"));
          });
        });
      }),
    );

    const pending = fetchWithTimeout("https://example.com", {}, 1000);
    const assertion = expect(pending).rejects.toThrow("Aborted");
    await vi.advanceTimersByTimeAsync(1000);
    await assertion;
  });
});
