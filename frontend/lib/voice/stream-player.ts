/**
 * Plays a spoken reply while it is still being generated (GET …/voice/speech/{id}/stream).
 *
 * The backend passes Gemini's audio through as raw 16-bit mono little-endian PCM. Each chunk is
 * converted and scheduled right after the previous one with the Web Audio API, after a short
 * initial buffer that absorbs network jitter (generation runs slightly faster than real time).
 * Speeds other than 1× use the source's playback rate, which also shifts the pitch a little.
 */

export interface PcmStream {
  rate: number;
  body: ReadableStream<Uint8Array>;
}

/** The parts of AudioContext the player uses (a fake in tests). */
export interface AudioOut {
  readonly currentTime: number;
  readonly destination: AudioNode;
  readonly state: AudioContextState;
  resume(): Promise<void>;
  createBuffer(channels: number, length: number, sampleRate: number): AudioBuffer;
  createBufferSource(): AudioBufferSourceNode;
}

/** Seconds of audio scheduled ahead before the first sound, and the minimum lead afterwards. */
const START_LEAD_S = 0.4;
const LEAD_S = 0.02;

export function pcm16ToFloat(bytes: Uint8Array): Float32Array<ArrayBuffer> {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength - (bytes.byteLength % 2));
  const out = new Float32Array(view.byteLength / 2);
  for (let i = 0; i < out.length; i++) out[i] = view.getInt16(i * 2, true) / 32768;
  return out;
}

export class StreamPlayer {
  private out: AudioOut | null = null;
  private sources = new Set<AudioBufferSourceNode>();
  private reader: ReadableStreamDefaultReader<Uint8Array> | null = null;
  private generation = 0;

  constructor(private makeOut: () => AudioOut = () => new AudioContext()) {}

  /** Resolves when the stream has been read (playback may continue); onDone fires when sound ends. */
  async play(stream: PcmStream, on: { start?: () => void; done?: () => void } = {}, rate = 1): Promise<void> {
    this.stop();
    const gen = ++this.generation;
    const out = (this.out ??= this.makeOut());
    if (out.state === "suspended") await out.resume().catch(() => undefined);
    const reader = stream.body.getReader();
    this.reader = reader;
    let next = 0;
    let carry: Uint8Array | null = null;
    let started = false;
    let playing = 0;
    let readDone = false;
    const finish = () => {
      if (gen === this.generation && readDone && playing === 0) {
        this.reader = null;
        on.done?.();
      }
    };

    for (;;) {
      const { value, done } = await reader.read().catch(() => ({ value: undefined, done: true as const }));
      if (gen !== this.generation) return; // stopped or replaced
      if (done || !value) break;
      // Keep sample alignment across chunk boundaries.
      let bytes = value;
      if (carry) {
        const joined = new Uint8Array(carry.length + value.length);
        joined.set(carry);
        joined.set(value, carry.length);
        bytes = joined;
        carry = null;
      }
      if (bytes.length % 2) {
        carry = bytes.slice(bytes.length - 1);
        bytes = bytes.slice(0, bytes.length - 1);
      }
      if (!bytes.length) continue;
      const samples = pcm16ToFloat(bytes);
      const buffer = out.createBuffer(1, samples.length, stream.rate);
      buffer.copyToChannel(samples, 0);
      const src = out.createBufferSource();
      src.buffer = buffer;
      src.playbackRate.value = rate;
      src.connect(out.destination);
      const at = Math.max(next, out.currentTime + (started ? LEAD_S : START_LEAD_S));
      src.start(at);
      next = at + buffer.duration / rate;
      playing += 1;
      this.sources.add(src);
      src.onended = () => {
        this.sources.delete(src);
        playing -= 1;
        finish();
      };
      if (!started) {
        started = true;
        on.start?.();
      }
    }
    readDone = true;
    if (!started) {
      if (gen === this.generation) on.done?.();
      return;
    }
    finish();
  }

  stop() {
    this.generation += 1;
    for (const src of this.sources) {
      src.onended = null;
      try {
        src.stop();
      } catch {
        /* not started yet */
      }
    }
    this.sources.clear();
    void this.reader?.cancel().catch(() => undefined);
    this.reader = null;
  }
}
