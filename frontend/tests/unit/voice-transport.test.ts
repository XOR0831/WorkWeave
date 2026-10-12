import { afterEach, describe, expect, it, vi } from "vitest";
import { CHUNK_SAMPLES, ChunkBuffer, downsample, floatToPcm16, pcm16ToBase64 } from "@/lib/voice/pcm";
import { LiveListener, VoiceError, isQuotaClose, type AudioSource, type VoiceGrant } from "@/lib/voice/live-listener";

const fromB64 = (b64: string) => new Int16Array(Uint8Array.from(atob(b64), (c) => c.charCodeAt(0)).buffer);

describe("PCM conversion for Gemini Live (16 kHz, 16-bit, mono)", () => {
  it("resamples 48 kHz to 16 kHz and clamps to 16-bit", () => {
    expect(downsample(new Float32Array(4800), 48000).length).toBe(1600);
    expect(Array.from(floatToPcm16(new Float32Array([0, 1, -1, 2, -2])))).toEqual([0, 32767, -32768, 32767, -32768]);
    expect(Array.from(fromB64(pcm16ToBase64(new Int16Array([1, -2, 300]))))).toEqual([1, -2, 300]);
  });
  it("emits exact 100 ms chunks and flushes the remainder", () => {
    const b = new ChunkBuffer();
    expect(b.push(new Float32Array(1000))).toHaveLength(0);
    const chunks = b.push(new Float32Array(2500)); // 3500 buffered -> 2 chunks + 300 left
    expect(chunks.map((c) => fromB64(c).length)).toEqual([CHUNK_SAMPLES, CHUNK_SAMPLES]);
    expect(fromB64(b.flush()!).length).toBe(300);
    expect(b.flush()).toBeNull();
  });
});

class FakeSocket {
  readyState = 0;
  sent: Record<string, unknown>[] = [];
  closed = false;
  onopen: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onclose: ((ev: CloseEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  constructor(public url: string) {}
  send(data: string) {
    this.sent.push(JSON.parse(data));
  }
  close(code = 1000, reason = "") {
    if (this.closed) return;
    this.closed = true;
    this.readyState = 3;
    this.onclose?.({ code, reason } as CloseEvent);
  }
  open() {
    this.readyState = 1;
    this.onopen?.({} as Event);
  }
  receive(msg: unknown, binary = false) {
    const data = binary ? new Blob([JSON.stringify(msg)]) : JSON.stringify(msg);
    this.onmessage?.({ data } as MessageEvent);
  }
  kinds() {
    return this.sent.map((m) => (m.setup ? "setup" : Object.keys((m.realtimeInput as object) ?? {})[0]));
  }
}

class FakeAudio implements AudioSource {
  started = false;
  stopped = 0;
  onFrames: ((f: Float32Array, r: number) => void) | null = null;
  constructor(private failWith?: string) {}
  async start(onFrames: (f: Float32Array, r: number) => void) {
    if (this.failWith) throw Object.assign(new Error("no"), { name: this.failWith });
    this.started = true;
    this.onFrames = onFrames;
  }
  stop() {
    this.stopped += 1;
  }
  speak(ms = 100) {
    this.onFrames?.(new Float32Array((48000 * ms) / 1000).fill(0.1), 48000);
  }
}

const grant = (mode: "TAP" | "HANDS_FREE"): VoiceGrant => ({
  token: "auth_tokens/a b",
  ws_url: "wss://example.invalid/live",
  model: "gemini-transcribe-test",
  mode,
  expires_at: "2099-01-01T00:00:00Z",
  setup: { model: "models/gemini-transcribe-test", generationConfig: { responseModalities: ["TEXT"] } },
  audio_mime_type: "audio/pcm;rate=16000",
  sample_rate: 16000,
});

const flush = () => new Promise((r) => setTimeout(r, 0));

async function connect(mode: "TAP" | "HANDS_FREE", events = {}, audio = new FakeAudio(), deps = {}) {
  let sock!: FakeSocket;
  const l = new LiveListener(grant(mode), events, { audio, socket: (u) => (sock = new FakeSocket(u)), ...deps });
  const started = l.start();
  sock.open();
  expect(sock.kinds()).toEqual(["setup"]); // setup first, nothing else before setupComplete
  audio.speak();
  expect(sock.kinds()).toEqual(["setup"]);
  sock.receive({ setupComplete: {} });
  await started;
  return { l, sock, audio };
}

afterEach(() => vi.useRealTimers());

describe("LiveListener (Gemini Live transcription protocol)", () => {
  it("tap-to-talk: locked setup, activityStart, 100 ms audio chunks, activityEnd, one utterance", async () => {
    const utterances: string[] = [];
    const interim: string[] = [];
    const { l, sock, audio } = await connect("TAP", { onUtterance: (t: string) => utterances.push(t), onInterim: (t: string) => interim.push(t) });
    expect(sock.url).toBe("wss://example.invalid/live?access_token=auth_tokens%2Fa%20b");
    expect(sock.sent[0]).toEqual({ setup: grant("TAP").setup });
    audio.speak(250); // 250 ms -> two full chunks
    const audioMsgs = sock.sent.filter((m) => (m.realtimeInput as { audio?: unknown })?.audio);
    expect(audioMsgs).toHaveLength(2);
    expect((audioMsgs[0]!.realtimeInput as { audio: { mimeType: string } }).audio.mimeType).toBe("audio/pcm;rate=16000");
    sock.receive({ serverContent: { interimInputTranscription: { text: "use the" } } });
    await flush();
    expect(interim.at(-1)).toBe("use the");
    const done = l.finish();
    // A binary frame followed immediately by a text frame: processed in arrival order.
    sock.receive({ serverContent: { inputTranscription: { text: "Use the current version." } } }, true);
    sock.receive({ serverContent: { turnComplete: true } });
    await done;
    expect(sock.kinds()).toEqual(["setup", "activityStart", "audio", "audio", "audio", "activityEnd"]);
    expect(utterances).toEqual(["Use the current version."]);
    expect(sock.closed).toBe(true);
    expect(audio.stopped).toBeGreaterThan(0);
  });

  it("hands-free: server VAD, fragments assembled into one utterance, pause stops audio", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    const utterances: string[] = [];
    const { l, sock, audio } = await connect("HANDS_FREE", { onUtterance: (t: string) => utterances.push(t) }, new FakeAudio(), { settleMs: 800 });
    expect(sock.kinds()).toEqual(["setup"]); // no manual activity markers
    sock.receive({ serverContent: { inputTranscription: { text: "Follow the current" } } });
    await vi.advanceTimersByTimeAsync(0);
    sock.receive({ serverContent: { inputTranscription: { text: "approved version" } } });
    await vi.advanceTimersByTimeAsync(799);
    expect(utterances).toEqual([]);
    await vi.advanceTimersByTimeAsync(1);
    expect(utterances).toEqual(["Follow the current approved version"]);
    const before = sock.sent.length;
    l.pause();
    audio.speak(200);
    expect(sock.sent.length).toBe(before);
    l.resume();
    audio.speak(200);
    expect(sock.sent.length).toBeGreaterThan(before);
    l.close();
    expect(sock.closed).toBe(true);
  });

  it("reports a blocked microphone and closes the session", async () => {
    let sock!: FakeSocket;
    const l = new LiveListener(grant("TAP"), {}, { audio: new FakeAudio("NotAllowedError"), socket: (u) => (sock = new FakeSocket(u)) });
    const started = l.start();
    sock.open();
    sock.receive({ setupComplete: {} });
    await expect(started).rejects.toMatchObject({ kind: "MIC_BLOCKED" });
    expect(sock.closed).toBe(true);
  });

  it("reports a connection that closes before setup completes", async () => {
    let sock!: FakeSocket;
    const l = new LiveListener(grant("TAP"), {}, { audio: new FakeAudio(), socket: (u) => (sock = new FakeSocket(u)) });
    const started = l.start();
    sock.open();
    sock.close();
    await expect(started).rejects.toBeInstanceOf(VoiceError);
  });

  it("a usage-limit close before setup says voice is busy, so the learner types instead", async () => {
    let sock!: FakeSocket;
    const l = new LiveListener(grant("TAP"), {}, { audio: new FakeAudio(), socket: (u) => (sock = new FakeSocket(u)) });
    const started = l.start();
    sock.open();
    sock.close(1011, "You exceeded your current quota, please check your plan and billing details.");
    await expect(started).rejects.toMatchObject({ kind: "BUSY" });
  });

  it("a usage-limit close mid-session reports BUSY before the closed state", async () => {
    const seen: string[] = [];
    const { sock } = await connect("HANDS_FREE", { onError: (e: VoiceError) => seen.push(e.kind), onState: (s: string) => seen.push(s) });
    sock.close(1008, "RESOURCE_EXHAUSTED");
    expect(seen.slice(-2)).toEqual(["BUSY", "closed"]);
  });

  it("an ordinary close is not mistaken for a usage limit", () => {
    expect(isQuotaClose({ code: 1000, reason: "" })).toBe(false);
    expect(isQuotaClose({ code: 1011, reason: "Internal error encountered." })).toBe(false);
    expect(isQuotaClose({ code: 1011, reason: "Quota exceeded for requests per day" })).toBe(true);
  });

  it("tap-to-talk with no speech says so instead of sending anything", async () => {
    const errors: string[] = [];
    const utterances: string[] = [];
    const { l } = await connect("TAP", { onError: (e: VoiceError) => errors.push(e.kind), onUtterance: (t: string) => utterances.push(t) }, new FakeAudio(), { finalTimeoutMs: 10 });
    await l.finish();
    expect(errors).toEqual(["NO_SPEECH"]);
    expect(utterances).toEqual([]);
  });
});
