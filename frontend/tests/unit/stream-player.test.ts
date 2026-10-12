import { describe, expect, it } from "vitest";
import { StreamPlayer, pcm16ToFloat, type AudioOut } from "@/lib/voice/stream-player";

class FakeSource {
  buffer: { duration: number; samples: Float32Array } | null = null;
  playbackRate = { value: 1 };
  onended: (() => void) | null = null;
  startAt = -1;
  stopped = false;
  connect() {}
  start(at: number) {
    this.startAt = at;
  }
  stop() {
    this.stopped = true;
  }
}

class FakeOut {
  currentTime = 10;
  state: AudioContextState = "running";
  destination = {} as AudioNode;
  sources: FakeSource[] = [];
  async resume() {}
  createBuffer(_c: number, length: number, rate: number) {
    const b = { duration: length / rate, samples: new Float32Array(length), copyToChannel: (s: Float32Array) => b.samples.set(s) };
    return b as unknown as AudioBuffer;
  }
  createBufferSource() {
    const s = new FakeSource();
    this.sources.push(s);
    return s as unknown as AudioBufferSourceNode;
  }
}

function stream(chunks: number[][]) {
  return {
    rate: 1000,
    body: new ReadableStream<Uint8Array>({
      start(c) {
        for (const ch of chunks) c.enqueue(new Uint8Array(ch));
        c.close();
      },
    }),
  };
}

describe("streamed reply playback", () => {
  it("converts little-endian 16-bit PCM to samples", () => {
    expect(Array.from(pcm16ToFloat(new Uint8Array([0x00, 0x40, 0x00, 0xc0, 0x7f])))).toEqual([0.5, -0.5]); // odd byte ignored
  });

  it("schedules chunks back to back after a short buffer, keeping samples across odd chunk edges", async () => {
    const out = new FakeOut();
    const player = new StreamPlayer(() => out as unknown as AudioOut);
    const events: string[] = [];
    // 3 chunks: 2 samples, then 1.5 samples, then 0.5 + 2 samples (a sample split across chunks)
    await player.play(stream([[0, 64, 0, 64], [0, 64, 0], [64, 0, 64, 0, 64]]), { start: () => events.push("start"), done: () => events.push("done") }, 1);
    const [a, b, c] = out.sources;
    expect(out.sources).toHaveLength(3);
    expect(a!.startAt).toBeCloseTo(10.4); // first sound after the 0.4 s buffer
    expect(b!.startAt).toBeCloseTo(10.4 + 2 / 1000); // right after the previous chunk
    expect(c!.startAt).toBeCloseTo(10.4 + 3 / 1000);
    expect(a!.buffer!.samples.length + b!.buffer!.samples.length + c!.buffer!.samples.length).toBe(6); // 12 bytes = 6 samples, none lost
    expect(events).toEqual(["start"]); // still playing
    a!.onended!();
    b!.onended!();
    expect(events).toEqual(["start"]);
    c!.onended!();
    expect(events).toEqual(["start", "done"]); // done only when the last chunk finishes
  });

  it("plays at the chosen speed, so chunk spacing shrinks", async () => {
    const out = new FakeOut();
    await new StreamPlayer(() => out as unknown as AudioOut).play(stream([[0, 64, 0, 64], [0, 64, 0, 64]]), {}, 2);
    expect(out.sources[0]!.playbackRate.value).toBe(2);
    expect(out.sources[1]!.startAt - out.sources[0]!.startAt).toBeCloseTo(1 / 1000); // 2 samples at 1 kHz, played 2× faster
  });

  it("stop silences everything immediately and nothing more is scheduled", async () => {
    const out = new FakeOut();
    const player = new StreamPlayer(() => out as unknown as AudioOut);
    let push!: (b: Uint8Array) => void;
    const done: string[] = [];
    const body = new ReadableStream<Uint8Array>({ start: (c) => (push = (b) => c.enqueue(b)) });
    const playing = player.play({ rate: 1000, body }, { done: () => done.push("done") });
    push(new Uint8Array([0, 64, 0, 64]));
    await new Promise((r) => setTimeout(r, 0));
    expect(out.sources).toHaveLength(1);
    player.stop();
    await playing;
    expect(out.sources[0]!.stopped).toBe(true);
    expect(out.sources).toHaveLength(1);
    expect(done).toEqual([]); // an interrupted reply doesn't report a natural end
  });

  it("an empty stream ends at once without sound", async () => {
    const out = new FakeOut();
    const done: string[] = [];
    await new StreamPlayer(() => out as unknown as AudioOut).play(stream([]), { done: () => done.push("done") });
    expect(out.sources).toHaveLength(0);
    expect(done).toEqual(["done"]);
  });
});
