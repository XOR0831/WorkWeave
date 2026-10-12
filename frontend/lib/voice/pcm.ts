/**
 * Audio helpers for Gemini Live transcription: microphone Float32 frames at the device rate become
 * 16-bit little-endian mono PCM at 16 kHz, sent as base64 in ~100 ms chunks.
 */
export const TARGET_RATE = 16000;
export const CHUNK_SAMPLES = 1600; // 100 ms at 16 kHz

/** Linear-interpolation resample to 16 kHz (mono). */
export function downsample(input: Float32Array, fromRate: number, toRate = TARGET_RATE): Float32Array {
  if (fromRate === toRate) return input;
  const ratio = fromRate / toRate;
  const out = new Float32Array(Math.floor(input.length / ratio));
  for (let i = 0; i < out.length; i++) {
    const pos = i * ratio;
    const lo = Math.floor(pos);
    const hi = Math.min(lo + 1, input.length - 1);
    out[i] = input[lo]! + (input[hi]! - input[lo]!) * (pos - lo);
  }
  return out;
}

export function floatToPcm16(input: Float32Array): Int16Array {
  const out = new Int16Array(input.length);
  for (let i = 0; i < input.length; i++) {
    const s = Math.max(-1, Math.min(1, input[i]!));
    out[i] = s < 0 ? Math.round(s * 0x8000) : Math.round(s * 0x7fff);
  }
  return out;
}

export function pcm16ToBase64(pcm: Int16Array): string {
  const bytes = new Uint8Array(pcm.buffer, pcm.byteOffset, pcm.byteLength);
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(bin);
}

/** Accumulates resampled audio and yields base64 chunks of exactly CHUNK_SAMPLES samples. */
export class ChunkBuffer {
  private pending = new Float32Array(0);
  push(samples: Float32Array): string[] {
    const merged = new Float32Array(this.pending.length + samples.length);
    merged.set(this.pending);
    merged.set(samples, this.pending.length);
    const chunks: string[] = [];
    let at = 0;
    for (; at + CHUNK_SAMPLES <= merged.length; at += CHUNK_SAMPLES) chunks.push(pcm16ToBase64(floatToPcm16(merged.subarray(at, at + CHUNK_SAMPLES))));
    this.pending = merged.slice(at);
    return chunks;
  }
  /** Remaining audio (shorter than a chunk), e.g. when the learner stops talking. */
  flush(): string | null {
    if (!this.pending.length) return null;
    const out = pcm16ToBase64(floatToPcm16(this.pending));
    this.pending = new Float32Array(0);
    return out;
  }
}
