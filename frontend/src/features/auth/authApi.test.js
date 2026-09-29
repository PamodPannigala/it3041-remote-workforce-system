import { afterEach, describe, expect, it, vi } from "vitest";
import { loginUser } from "./authApi";

describe("authentication API requests", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("aborts a login request that exceeds the request timeout", async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_url, { signal }) =>
          new Promise((_resolve, reject) => {
            signal.addEventListener("abort", () => {
              reject(new DOMException("Aborted", "AbortError"));
            });
          })
      )
    );

    const loginRequest = loginUser({ email: "user@example.com", password: "password" });
    const rejection = expect(loginRequest).rejects.toThrow(/request timed out/i);
    await vi.advanceTimersByTimeAsync(15000);
    await rejection;
  });
});