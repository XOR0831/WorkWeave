/**
 * One listening session against Gemini's transcription-only Live model (transport only).
 *
 * Protocol (Gemini Live API, WebSocket): send the server-locked `setup` first, wait for
 * `setupComplete`, then stream `realtimeInput.audio` (16 kHz PCM, base64). Tap-to-talk marks the
 * utterance with `activityStart`/`activityEnd` (server VAD is off); hands-free leaves voice activity
 * detection to the server. `serverContent.interimInputTranscription` updates live text and
 * `serverContent.inputTranscription` carries finalized text, assembled into one utterance per turn.
 *
 * Audio goes from the browser straight to Gemini with a single-use ephemeral token minted by our
 * backend; nothing is recorded or stored, and no vocal signals are analysed.
 */
import { StreamPlayer, type PcmStream } from "@/lib/voice/stream-player";
import { ChunkBuffer, TARGET_RATE, downsample } from "./pcm";

export type ListenMode = "TAP" | "HANDS_FREE";

export interface VoiceGrant {
  token: string;
  ws_url: string;
  model: string;
  mode: ListenMode;
  expires_at: string;
  setup: Record<string, unknown>;
  audio_mime_type: string;
  sample_rate: number;
}

export interface AudioSource {
  start(onFrames: (frames: Float32Array, sampleRate: number) => void): Promise<void>;
  stop(): void;
}

export type ListenerState = "connecting" | "listening" | "finishing" | "closed";

/** Gemini closes the Live socket with a quota/rate-limit reason when the API key's limit is used up. */
export function isQuotaClose(ev: Pick<CloseEvent, "code" | "reason"> | undefined): boolean {
  return Boolean(ev && /quota|exhaust|rate.?limit|too many requests|429/i.test(ev.reason ?? ""));
}

export function busyError(): VoiceError {
  return new VoiceError("BUSY", "Voice input is busy right now (shared demo limit). Type your answer instead; voice may work again later.");
}

export class VoiceError extends Error {
  constructor(
    public readonly kind: "MIC_BLOCKED" | "MIC_MISSING" | "CONNECTION" | "NO_SPEECH" | "BUSY",
    message: string,
  ) {
    super(message);
  }
}

export interface ListenerEvents {
  onState?(state: ListenerState): void;
  /** Live text: finalized words so far plus the current interim guess. */
  onInterim?(text: string): void;
  /** One finished utterance (tap-to-talk: after Stop; hands-free: when the server detects the end). */
  onUtterance?(text: string): void;
  onError?(error: VoiceError): void;
  /** Microphone loudness 0..1 (RMS), about 15 times a second, for a "hearing you" meter. */
  onLevel?(level: number): void;
}

type WS = Pick<WebSocket, "send" | "close" | "readyState"> & {
  onopen: ((ev: Event) => void) | null;
  onmessage: ((ev: MessageEvent) => void) | null;
  onclose: ((ev: CloseEvent) => void) | null;
  onerror: ((ev: Event) => void) | null;
};

export interface ListenerDeps {
  audio: AudioSource;
  socket?: (url: string) => WS;
  /** Hands-free: emit the utterance this long after the last final fragment if no turnComplete arrives. */
  settleMs?: number;
  /** Tap-to-talk: give up waiting for the final transcript after this long. */
  finalTimeoutMs?: number;
}

const OPEN = 1;

export class LiveListener {
  private ws: WS | null = null;
  private buffer = new ChunkBuffer();
  private finals: string[] = [];
  private interim = "";
  private paused = false;
  private ready = false;
  private settleTimer: ReturnType<typeof setTimeout> | null = null;
  private finishResolve: (() => void) | null = null;
  private state: ListenerState = "closed";
  /** Messages are parsed asynchronously (binary frames need Blob.text()); this keeps arrival order. */
  private inbox: Promise<void> = Promise.resolve();
  private lastLevelAt = 0;

  constructor(
    private readonly grant: VoiceGrant,
    private readonly events: ListenerEvents,
    private readonly deps: ListenerDeps,
  ) {}

  get mode(): ListenMode {
    return this.grant.mode;
  }

  private setState(s: ListenerState) {
    this.state = s;
    this.events.onState?.(s);
  }

  private send(msg: unknown) {
    if (this.ws && this.ws.readyState === OPEN) this.ws.send(JSON.stringify(msg));
  }

  /** Opens the socket, sends the locked setup, waits for setupComplete, then starts the microphone. */
  start(): Promise<void> {
    this.setState("connecting");
    const url = `${this.grant.ws_url}?access_token=${encodeURIComponent(this.grant.token)}`;
    const ws = (this.deps.socket ?? ((u: string) => new WebSocket(u) as unknown as WS))(url);
    this.ws = ws;
    return new Promise<void>((resolve, reject) => {
      ws.onopen = () => this.send({ setup: this.grant.setup });
      ws.onerror = () => undefined; // onclose follows with details
      ws.onclose = (ev) => {
        const wasReady = this.ready;
        this.cleanup();
        // The voice service's usage limit (shared demo quota): say so, and don't reconnect into it.
        const busy = isQuotaClose(ev);
        if (busy && wasReady) this.events.onError?.(busyError());
        if (!wasReady) reject(busy ? busyError() : new VoiceError("CONNECTION", "Couldn't start listening. Check your connection and try again, or type instead."));
        else if (this.state !== "closed") this.setState("closed");
        this.finishResolve?.();
      };
      ws.onmessage = (ev) => {
        this.inbox = this.inbox.then(() => readMessage(ev.data)).then((msg) => {
          if (!msg) return;
          if ("setupComplete" in msg && !this.ready) {
            this.ready = true;
            void this.startAudio().then(resolve, (e: unknown) => {
              this.close();
              reject(e);
            });
            return;
          }
          this.handle(msg);
        });
      };
    });
  }

  private async startAudio() {
    try {
      await this.deps.audio.start((frames, rate) => this.onFrames(frames, rate));
    } catch (e) {
      const name = (e as { name?: string })?.name;
      if (name === "NotAllowedError" || name === "SecurityError")
        throw new VoiceError("MIC_BLOCKED", "Microphone access is blocked. Select the microphone or lock icon in the address bar, allow the microphone for this site, then try again. You can keep typing meanwhile.");
      throw new VoiceError("MIC_MISSING", "No microphone is available. Connect one, or type instead.");
    }
    if (this.grant.mode === "TAP") this.send({ realtimeInput: { activityStart: {} } });
    this.setState("listening");
  }

  private onFrames(frames: Float32Array, rate: number) {
    if (!this.ready) return;
    const now = Date.now();
    if (this.events.onLevel && now - this.lastLevelAt >= 66) {
      this.lastLevelAt = now;
      this.events.onLevel(this.paused ? 0 : rms(frames));
    }
    if (this.paused) return;
    for (const data of this.buffer.push(downsample(frames, rate, TARGET_RATE))) this.send({ realtimeInput: { audio: { data, mimeType: this.grant.audio_mime_type } } });
  }

  private handle(msg: Record<string, unknown>) {
    const content = (msg.serverContent ?? {}) as {
      interimInputTranscription?: { text?: string };
      inputTranscription?: { text?: string };
      turnComplete?: boolean;
    };
    if (content.inputTranscription?.text) {
      this.finals.push(content.inputTranscription.text.trim());
      this.interim = "";
      this.emitInterim();
      if (this.grant.mode === "HANDS_FREE") this.armSettle();
    } else if (content.interimInputTranscription?.text) {
      this.interim = content.interimInputTranscription.text.trim();
      this.emitInterim();
    }
    if (content.turnComplete) this.emitUtterance();
  }

  private emitInterim() {
    this.events.onInterim?.([...this.finals, this.interim].filter(Boolean).join(" "));
  }

  private armSettle() {
    if (this.settleTimer) clearTimeout(this.settleTimer);
    this.settleTimer = setTimeout(() => this.emitUtterance(), this.deps.settleMs ?? 800);
  }

  private emitUtterance() {
    if (this.settleTimer) clearTimeout(this.settleTimer);
    this.settleTimer = null;
    const text = this.finals.join(" ").replace(/\s+/g, " ").trim();
    this.finals = [];
    this.interim = "";
    if (text) this.events.onUtterance?.(text);
    this.finishResolve?.();
  }

  /** Drop transcript text heard so far (e.g. the tutor's own voice picked up during playback). */
  discardPending() {
    if (this.settleTimer) clearTimeout(this.settleTimer);
    this.settleTimer = null;
    this.finals = [];
    this.interim = "";
  }

  /** Hands-free: stop sending audio (e.g. while a reply is being read aloud) without closing. */
  pause() {
    this.paused = true;
  }

  resume() {
    this.paused = false;
  }

  /** Tap-to-talk: the learner tapped Stop. Ends the utterance and waits for the final transcript. */
  async finish(): Promise<void> {
    if (!this.ready) return this.close();
    this.setState("finishing");
    const tail = this.buffer.flush();
    if (tail) this.send({ realtimeInput: { audio: { data: tail, mimeType: this.grant.audio_mime_type } } });
    this.deps.audio.stop();
    this.send(this.grant.mode === "TAP" ? { realtimeInput: { activityEnd: {} } } : { realtimeInput: { audioStreamEnd: true } });
    const hadSpeech = await new Promise<boolean>((resolve) => {
      const timer = setTimeout(() => {
        this.finishResolve = null;
        const text = this.finals.join(" ").trim();
        if (text) this.emitUtterance();
        resolve(Boolean(text));
      }, this.deps.finalTimeoutMs ?? 5000);
      this.finishResolve = () => {
        clearTimeout(timer);
        this.finishResolve = null;
        resolve(true);
      };
    });
    this.close();
    if (!hadSpeech) this.events.onError?.(new VoiceError("NO_SPEECH", "I didn't catch that. Try again, or type instead."));
  }

  close() {
    if (this.ws) {
      const ws = this.ws;
      this.ws = null;
      try {
        ws.close();
      } catch {
        /* already closed */
      }
    }
    this.cleanup();
    if (this.state !== "closed") this.setState("closed");
  }

  private cleanup() {
    if (this.settleTimer) clearTimeout(this.settleTimer);
    this.settleTimer = null;
    this.deps.audio.stop();
    this.ready = false;
  }
}

/** Root-mean-square loudness of one frame, scaled so normal speech reads around 0.3–0.8. */
export function rms(frames: Float32Array): number {
  if (!frames.length) return 0;
  let sum = 0;
  for (let i = 0; i < frames.length; i++) sum += frames[i]! * frames[i]!;
  return Math.min(1, Math.sqrt(sum / frames.length) * 4);
}

/** Live API frames may be text or binary JSON. */
async function readMessage(data: unknown): Promise<Record<string, unknown> | null> {
  try {
    if (typeof data === "string") return JSON.parse(data);
    if (data instanceof Blob) return JSON.parse(await data.text());
    if (data instanceof ArrayBuffer) return JSON.parse(new TextDecoder().decode(data));
  } catch {
    return null;
  }
  return null;
}

const WORKLET = `class WwMic extends AudioWorkletProcessor{process(inputs){const c=inputs[0]&&inputs[0][0];if(c)this.port.postMessage(c.slice(0));return true}}registerProcessor('ww-mic',WwMic);`;

/** Microphone capture via an AudioWorklet; frames are delivered at the device sample rate. */
export class MicCapture implements AudioSource {
  private stream: MediaStream | null = null;
  private ctx: AudioContext | null = null;
  private moduleUrl: string | null = null;

  async start(onFrames: (frames: Float32Array, sampleRate: number) => void) {
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
    const ctx = new AudioContext();
    this.ctx = ctx;
    this.moduleUrl = URL.createObjectURL(new Blob([WORKLET], { type: "application/javascript" }));
    await ctx.audioWorklet.addModule(this.moduleUrl);
    const node = new AudioWorkletNode(ctx, "ww-mic");
    node.port.onmessage = (e: MessageEvent<Float32Array>) => onFrames(e.data, ctx.sampleRate);
    const mute = ctx.createGain();
    mute.gain.value = 0; // keeps the graph running without playing the mic back
    ctx.createMediaStreamSource(this.stream).connect(node);
    node.connect(mute).connect(ctx.destination);
  }

  stop() {
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
    void this.ctx?.close().catch(() => undefined);
    this.ctx = null;
    if (this.moduleUrl) URL.revokeObjectURL(this.moduleUrl);
    this.moduleUrl = null;
  }
}

/** Plays committed tutor replies; one at a time. */
export class ReplySpeaker {
  private audio: HTMLAudioElement | null = null;
  private url: string | null = null;
  private streamer: StreamPlayer | null = null;

  constructor(private makeStreamPlayer: () => StreamPlayer = () => new StreamPlayer()) {}

  /** Streamed reply: sound starts within seconds, before the whole reply is generated. */
  async playStream(stream: PcmStream, on: { start?: () => void; done?: () => void }, rate = 1) {
    this.stop();
    this.streamer ??= this.makeStreamPlayer();
    await this.streamer.play(stream, on, rate);
  }

  async play(audio: Blob, onDone?: () => void, rate = 1) {
    this.stop();
    this.url = URL.createObjectURL(audio);
    const el = new Audio(this.url);
    el.playbackRate = rate;
    this.audio = el;
    const done = () => {
      if (this.audio === el) this.stop();
      onDone?.();
    };
    el.onended = done;
    el.onerror = done;
    await el.play().catch(() => done());
  }

  setRate(rate: number) {
    if (this.audio) this.audio.playbackRate = rate;
  }

  stop() {
    this.streamer?.stop();
    if (this.audio) {
      this.audio.onended = null;
      this.audio.pause();
    }
    this.audio = null;
    if (this.url) URL.revokeObjectURL(this.url);
    this.url = null;
  }
}
