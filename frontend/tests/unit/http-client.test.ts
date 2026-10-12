import { afterEach, describe, expect, it, vi } from "vitest";
import { createHttpClient } from "@/lib/clients/http/HttpClient";
import { WorkWeaveError } from "@/types/contracts";

const ok = (data: unknown) => new Response(JSON.stringify({ request_id: "r1", data }), { status: 200, headers: { "content-type": "application/json" } });
const fail = (status: number, code: string) => new Response(JSON.stringify({ request_id: "r2", error: { code, message: code, retryable: false } }), { status });

afterEach(() => vi.unstubAllGlobals());

describe("HttpClient (demo-entry slice)", () => {
  it("rejects methods outside this slice with CAPABILITY_UNAVAILABLE, never fixture data", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ok(null)));
    const c = createHttpClient();
    // Preview-only actions (ADR-033: the ticket system decides completion; reports aren't kept as drafts).
    await expect(c.confirmItemCompletion("i1", { idempotency_key: "k" })).rejects.toMatchObject({ error: { code: "CAPABILITY_UNAVAILABLE", message: "This screen isn't connected to the WorkWeave backend yet." } });
    await expect(c.dismissPendingReport()).rejects.toBeInstanceOf(WorkWeaveError);
  });

  it("does not notify listeners when a read returns unchanged data (no refetch loop)", async () => {
    const persona = { employee_id: "e1", first_name: "Sam", last_name: "Kim", role_name: "", team_name: "", team_role: "MEMBER", employment_status: "ACTIVE", scenario_note: "", grants: [] };
    const fetch = vi.fn(async (url: string) => (String(url).endsWith("/personas") ? ok([persona]) : ok(null)));
    vi.stubGlobal("fetch", fetch);
    const c = createHttpClient();
    await vi.waitFor(() => expect(c.isLoaded()).toBe(true));
    const seen = vi.fn();
    c.subscribe(seen);
    await c.getSession();
    await c.getSession();
    expect(seen).not.toHaveBeenCalled();
  });

  it("sends the client header and same-origin credentials on commands, and clears state on expiry", async () => {
    const fetch = vi.fn(async (url: string, _init?: RequestInit) => {
      if (String(url).endsWith("/demo-sessions/current/persona")) return fail(401, "SESSION_EXPIRED");
      return ok(null);
    });
    vi.stubGlobal("fetch", fetch);
    const c = createHttpClient();
    await expect(c.switchPersona("e1")).rejects.toMatchObject({ error: { code: "SESSION_EXPIRED" } });
    const init = fetch.mock.calls.find(([u]) => String(u).endsWith("/persona"))![1]!;
    expect(init.credentials).toBe("same-origin");
    expect((init.headers as Record<string, string>)["X-WorkWeave-Client"]).toBe("web");
    expect(c.peekSession()).toBeNull();
  });

  it("maps an unreachable API to a retryable DEPENDENCY_UNAVAILABLE", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))));
    const c = createHttpClient();
    await expect(c.listScenarios()).rejects.toMatchObject({ error: { code: "DEPENDENCY_UNAVAILABLE", retryable: true } });
  });

  it("reads the curricula catalog and one curriculum from the API, encoding the ID", async () => {
    const catalog = { curricula: [{ curriculum_id: "c1", name: "Machine Fundamentals", version: "1.0", status: "PUBLISHED", topic_count: 1, subtopic_count: 3, source_count: 1, pending_review_count: 0 }], receipts: [], sample_available: false };
    const fetch = vi.fn(async (url: string) => (String(url).endsWith("/curricula") ? ok(catalog) : ok({ curriculum_id: "a/b", name: "X", linked_sources: [] })));
    vi.stubGlobal("fetch", fetch);
    const c = createHttpClient();
    expect(await c.listCurricula()).toEqual(catalog);
    expect((await c.getCurriculum("a/b")).curriculum_id).toBe("a/b");
    expect(fetch.mock.calls.map(([u]) => String(u))).toEqual(expect.arrayContaining(["/api/curricula", "/api/curricula/a%2Fb"]));
  });

  it("surfaces a forbidden curricula read as FORBIDDEN, not as empty data", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => (String(url).includes("/curricula") ? fail(403, "FORBIDDEN") : ok(null))));
    const c = createHttpClient();
    await expect(c.listCurricula()).rejects.toMatchObject({ error: { code: "FORBIDDEN" } });
    await expect(c.getCurriculum("c1")).rejects.toMatchObject({ error: { code: "FORBIDDEN" } });
  });

  it("sends a UUID client_turn_id, reused when the same command is retried", async () => {
    const bodies: Record<string, unknown>[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if (String(url).endsWith("/onboarding")) return ok({ learning_session_id: "s1" });
        if (String(url).endsWith("/turns/stream")) bodies.push(JSON.parse(String(init!.body)));
        return ok({ learning_session_id: "s1", transcript: [] });
      }),
    );
    const c = createHttpClient();
    const turn = (key: string) => c.sendOnboardingTurn({ idempotency_key: key, client_turn_id: "turn-abc-1", expected_revision: 2, text: "Hi", input_kind: "TEXT" });
    await turn("k1");
    await turn("k1"); // retry of the same command
    await turn("k2");
    await c.sendOnboardingTurn({ idempotency_key: "k3", client_turn_id: "turn-x", expected_revision: 3, text: "Wait", input_kind: "VOICE_TRANSCRIPT", interrupted_previous_reply: true });
    expect(bodies.at(-1)).toMatchObject({ interrupted_previous_reply: true, input_kind: "VOICE_TRANSCRIPT" });
    expect(bodies[0]).not.toHaveProperty("interrupted_previous_reply");
    const ids = bodies.slice(0, 3).map((b) => b.client_turn_id as string);
    expect(ids[0]).toMatch(/^[0-9a-f-]{36}$/);
    expect(ids[1]).toBe(ids[0]);
    expect(ids[2]).not.toBe(ids[0]);
  });

  it("streams progress labels while the tutor works, then returns the saved view", async () => {
    const enc = new TextEncoder();
    const sse = (e: string, d: unknown) => `event: ${e}\ndata: ${JSON.stringify(d)}\n\n`;
    const text = sse("progress", { label: "Understanding your message…" }) + sse("progress", { label: "Writing a reply…" }) + sse("done", { request_id: "r", data: { learning_session_id: "s1", transcript: [], revision: 4 } });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (String(url).endsWith("/onboarding")) return ok({ learning_session_id: "s1" });
        // Split mid-event to prove events are reassembled across network chunks.
        const cut = 37;
        const body = new ReadableStream<Uint8Array>({
          start(c) {
            c.enqueue(enc.encode(text.slice(0, cut)));
            c.enqueue(enc.encode(text.slice(cut)));
            c.close();
          },
        });
        return new Response(body, { status: 200, headers: { "content-type": "text/event-stream" } });
      }),
    );
    const labels: string[] = [];
    const view = await createHttpClient().sendOnboardingTurn({ idempotency_key: "k", client_turn_id: "t", expected_revision: 3, text: "Hi", input_kind: "TEXT", onProgress: (l) => labels.push(l) });
    expect(labels).toEqual(["Understanding your message…", "Writing a reply…"]);
    expect(view).toMatchObject({ learning_session_id: "s1", revision: 4 });
  });

  it("a streamed error becomes the usual typed error", async () => {
    const body = `event: progress\ndata: {"label":"Writing a reply…"}\n\nevent: error\ndata: {"request_id":"r9","error":{"code":"DEPENDENCY_UNAVAILABLE","message":"The tutor couldn't reply.","retryable":true}}\n\n`;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        String(url).endsWith("/onboarding") ? ok({ learning_session_id: "s1" }) : new Response(body, { status: 200, headers: { "content-type": "text/event-stream" } }),
      ),
    );
    await expect(createHttpClient().sendOnboardingTurn({ idempotency_key: "k", client_turn_id: "t", expected_revision: 3, text: "Hi", input_kind: "TEXT" })).rejects.toMatchObject({
      error: { code: "DEPENDENCY_UNAVAILABLE", retryable: true },
      request_id: "r9",
    });
  });

  it("wires voice: capabilities, a listening grant for the open session, and reply audio", async () => {
    const calls: { url: string; init?: RequestInit }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        calls.push({ url: String(url), init });
        if (String(url).endsWith("/capabilities")) return ok({ voice_adapter: "AVAILABLE", conversation_engine: "UNAVAILABLE" });
        if (String(url).endsWith("/onboarding")) return ok({ learning_session_id: "s1" });
        if (String(url).endsWith("/voice/listen")) return ok({ token: "t", mode: "HANDS_FREE" });
        if (String(url).includes("/voice/speech/")) return new Response(new TextEncoder().encode("RIFF"), { status: 200, headers: { "content-type": "audio/wav" } });
        return ok(null);
      }),
    );
    const c = createHttpClient();
    await vi.waitFor(() => expect(c.isLoaded()).toBe(true));
    expect((await c.getCapabilities()).voice_adapter).toBe("AVAILABLE");
    const seen = vi.fn();
    c.subscribe(seen);
    expect((await c.getVoiceListenGrant("HANDS_FREE")).token).toBe("t");
    const listen = calls.find((x) => x.url.endsWith("/onboarding/sessions/s1/voice/listen"))!;
    expect(JSON.parse(String(listen.init!.body))).toEqual({ mode: "HANDS_FREE" });
    expect((listen.init!.headers as Record<string, string>)["X-WorkWeave-Client"]).toBe("web");
    await new Promise((r) => setTimeout(r, 0));
    expect(seen).not.toHaveBeenCalled(); // a token isn't a state change: screens aren't re-read
    const audio = await c.getReplySpeech("turn1:out");
    expect(audio.size).toBe(4);
    expect(calls.some((x) => x.url.endsWith("/onboarding/sessions/s1/voice/speech/turn1%3Aout"))).toBe(true);
  });

  it("notifies screens after a successful command so they re-read committed state", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ok({ learning_session_id: "s1", status: "PAUSED" })));
    const c = createHttpClient();
    await vi.waitFor(() => expect(c.isLoaded()).toBe(true));
    const seen = vi.fn();
    c.subscribe(seen);
    await c.startOnboardingSession();
    await vi.waitFor(() => expect(seen).toHaveBeenCalled());
  });
});
