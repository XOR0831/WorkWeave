import { afterEach, describe, expect, it, vi } from "vitest";
import { createHttpClient } from "@/lib/clients/http/HttpClient";

/** Read-aloud sentence by sentence (owner, 2026-10-13): one request per part, one piece of audio per part. */
const pcm = (bytes: number[], parts?: number) =>
  new Response(new Uint8Array(bytes), { status: 200, headers: { "x-sample-rate": "24000", ...(parts ? { "x-speech-parts": String(parts) } : {}) } });

const partOf = (url: string) => new URL(url, "http://x").searchParams.get("part");
/** The client also loads its session on creation; only the speech requests matter here. */
const speechCalls = (f: ReturnType<typeof vi.fn>) => f.mock.calls.filter(([u]) => String(u).includes("/voice/speech/"));
const json = (data: unknown) => new Response(JSON.stringify({ request_id: "r", data }), { status: 200, headers: { "content-type": "application/json" } });

async function readAll(body: ReadableStream<Uint8Array>) {
  const reader = body.getReader();
  const chunks: number[][] = [];
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return chunks;
    chunks.push(Array.from(value));
  }
}

afterEach(() => vi.unstubAllGlobals());

describe("read-aloud in parts", () => {
  it("fetches the parts in order and hands each one over whole", async () => {
    const audio: Record<string, number[]> = { "0": [1, 0, 2, 0], "1": [3, 0], "2": [4, 0, 5, 0, 6, 0] };
    const fetch = vi.fn(async (url: string) => (partOf(url) ? pcm(audio[partOf(url)!]!, 3) : json(null)));
    vi.stubGlobal("fetch", fetch);
    const s = await createHttpClient().streamHandoverReplySpeech("m1");
    expect(s.rate).toBe(24000);
    expect(await readAll(s.body)).toEqual([audio["0"], audio["1"], audio["2"]]);
    expect(speechCalls(fetch).map(([u]) => partOf(u))).toEqual(["0", "1", "2"]);
    expect(String(speechCalls(fetch)[0]![0])).toMatch(/\/handover\/voice\/speech\/m1\/stream\?part=0$/);
  });

  it("asks for the next part only once the one before it has been taken (one ahead, never all at once)", async () => {
    const fetch = vi.fn(async (url: string) => (partOf(url) ? pcm([Number(partOf(url)), 0], 4) : json(null)));
    vi.stubGlobal("fetch", fetch);
    const s = await createHttpClient().streamKtReplySpeech("m1");
    const reader = s.body.getReader();
    await new Promise((r) => setTimeout(r, 10));
    expect(speechCalls(fetch)).toHaveLength(1); // part 0 is waiting to be read; nothing fetched ahead of it
    await reader.read(); // part 0 goes to the player ...
    await vi.waitFor(() => expect(speechCalls(fetch)).toHaveLength(2)); // ... and part 1 is fetched while it plays
    await new Promise((r) => setTimeout(r, 10));
    expect(speechCalls(fetch)).toHaveLength(2);
  });

  it("stopping cancels the part being fetched", async () => {
    let signal: AbortSignal | undefined;
    const fetch = vi.fn(async (url: string, init?: RequestInit) => {
      if (!partOf(url)) return json(null);
      if (partOf(url) === "0") return pcm([1, 0], 2);
      signal = init?.signal ?? undefined;
      return new Promise<Response>((_, reject) => signal!.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError"))));
    });
    vi.stubGlobal("fetch", fetch);
    const s = await createHttpClient().streamHandoverReplySpeech("m1");
    const reader = s.body.getReader();
    await reader.read();
    await vi.waitFor(() => expect(signal).toBeDefined());
    await reader.cancel();
    expect(signal!.aborted).toBe(true);
  });

  it("a part that fails ends the stream with an error (the player stops; the text stays on screen)", async () => {
    const fetch = vi.fn(async (url: string) =>
      !partOf(url) ? json(null) : partOf(url) === "0" ? pcm([1, 0], 2) : new Response(JSON.stringify({ request_id: "r", error: { code: "DEPENDENCY_UNAVAILABLE", message: "x", retryable: true } }), { status: 503 }),
    );
    vi.stubGlobal("fetch", fetch);
    const s = await createHttpClient().streamHandoverReplySpeech("m1");
    const reader = s.body.getReader();
    expect((await reader.read()).value).toEqual(new Uint8Array([1, 0]));
    await expect(reader.read()).rejects.toMatchObject({ error: { code: "DEPENDENCY_UNAVAILABLE" } });
  });

  it("a server without parts streams the whole reply as before", async () => {
    const fetch = vi.fn(async (url: string) => (partOf(url) ? pcm([1, 0, 2, 0]) : json(null)));
    vi.stubGlobal("fetch", fetch);
    const s = await createHttpClient().streamHandoverReplySpeech("m1");
    expect((await readAll(s.body)).flat()).toEqual([1, 0, 2, 0]);
    expect(speechCalls(fetch)).toHaveLength(1);
  });

  it("an error on the first part (e.g. the read-aloud limit) is thrown before anything plays", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => (partOf(url) ? new Response(JSON.stringify({ request_id: "r", error: { code: "LIMIT_REACHED", message: "limit", retryable: false } }), { status: 429 }) : json(null))));
    await expect(createHttpClient().streamHandoverReplySpeech("m1")).rejects.toMatchObject({ error: { code: "LIMIT_REACHED" } });
  });
});
