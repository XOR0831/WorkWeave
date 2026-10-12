import { afterEach, describe, expect, it, vi } from "vitest";
import { createHttpClient } from "@/lib/clients/http/HttpClient";

const ok = (data: unknown) => new Response(JSON.stringify({ request_id: "r", data }), { status: 200, headers: { "content-type": "application/json" } });

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("watching the team's work (API mode)", () => {
  it("re-reads the screens only when someone else changed the team's work", async () => {
    const tokens = ["a", "a", "b", "b"];
    vi.stubGlobal("fetch", vi.fn(async (url: string) => (String(url).endsWith("/work-state") ? ok({ changes_token: tokens.shift() ?? "b" }) : ok(null))));
    const c = createHttpClient();
    await vi.waitFor(() => expect(c.isLoaded()).toBe(true));
    vi.useFakeTimers();
    const seen = vi.fn();
    c.subscribe(seen);
    const stop = c.watchWork(1000);
    await vi.advanceTimersByTimeAsync(1100); // a -> a: nothing changed
    expect(seen).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1000); // a -> b: e.g. the shift lead reassigned a ticket
    expect(seen).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1000); // b -> b
    expect(seen).toHaveBeenCalledTimes(1);
    stop();
  });
});
