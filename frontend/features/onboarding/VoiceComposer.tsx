"use client";

/**
 * API-mode composer with real voice: visible tap-to-talk (default) and opt-in hands-free.
 *
 * Tap to talk: tap (or Space) to start, tap Stop (or Space); the transcript fills the box for review,
 * then Send. A level meter shows the mic is hearing you. Tap-to-talk stops by itself after 10 s of
 * silence or 2 minutes (with a warning), keeping what was said.
 * Hands-free: Gemini's voice activity detection decides when you've finished; the transcript is
 * shown with a visible 1-second countdown you can cancel (typing also cancels), then it's sent. If
 * the connection drops, it reconnects quietly (at most twice a minute). It's remembered per
 * browser but only ever offered again; the mic never opens without a tap.
 * The first time, a short explainer comes before the browser's microphone prompt.
 * While a reply plays, the mic button becomes Interrupt (also Space). With the optional voice
 * interrupt (hands-free, off by default) speaking over the reply stops it; an echo filter ignores
 * the tutor's own words. Start/stop tones can be switched off and are off for reduced-motion users.
 * A transcript is sent as input_kind VOICE_TRANSCRIPT; audio is never stored.
 * Demo caps: when voice input reaches its daily limit (or the free voice service is busy), the mic
 * controls switch off with a plain explanation and typing carries on as normal.
 */
import { useEffect, useId, useRef, useState } from "react";
import type { ListenerEvents, ListenMode, VoiceGrant } from "@/lib/voice/live-listener";
import { VoiceError } from "@/lib/voice/live-listener";
import { isBargeIn } from "@/lib/voice/barge-in";
import type { Cue } from "@/lib/voice/cues";
import { resetTime, type Blocked } from "@/lib/limits";
import { WorkWeaveError, type LimitInfo } from "@/types/contracts";

export interface Listener {
  readonly mode: ListenMode;
  start(): Promise<void>;
  finish(): Promise<void>;
  pause(): void;
  resume(): void;
  discardPending(): void;
  close(): void;
}

export interface ComposerVoicePrefs {
  sounds: boolean;
  handsFree: boolean;
  micExplained: boolean;
}

type Status = "idle" | "connecting" | "tap" | "finishing" | "hands-free";
// Long enough to read the transcript and cancel; short so the tutor answers sooner (owner, 2026-10-04).
const COUNTDOWN_SECONDS = 1;
/** Voice interrupt ignores speech in the first moments of playback (the reply's own onset). */
export const BARGE_IN_GRACE_MS = 500;
export const TAP_MAX_MS = 120_000;
export const TAP_WARN_MS = 105_000;
export const TAP_SILENCE_MS = 10_000;
const LOUD = 0.08;
const RECONNECTS_PER_MINUTE = 2;
/** Wall clock, read only from event handlers and timers (never during render). */
const clock = () => Date.now();

export function VoiceComposer({
  onSend,
  disabled,
  pending,
  placeholder = "Type a question or answer",
  label,
  voiceAvailable: voiceConfigured,
  voiceBlocked = null,
  onLimit,
  unavailableReason = "Voice isn't configured on this server.",
  speaking = false,
  speakingText = "",
  onInterrupt,
  voiceInterrupt = false,
  prefs = { sounds: true, handsFree: false, micExplained: true },
  onPrefsChange,
  playCue,
  micPermission,
  getGrant,
  createListener,
}: {
  onSend: (text: string, inputKind: "TEXT" | "VOICE_TRANSCRIPT") => Promise<boolean>;
  disabled?: boolean;
  pending?: boolean;
  placeholder?: string;
  label: string;
  voiceAvailable: boolean;
  /** Voice input reached a demo cap: the mic switches off until it resets. */
  voiceBlocked?: Blocked | null;
  /** A listening grant was refused by a demo cap. */
  onLimit?: (limit: LimitInfo) => void;
  unavailableReason?: string;
  /** A reply is being read aloud: hands-free listening pauses so it doesn't transcribe the speaker. */
  speaking?: boolean;
  /** The reply text being read aloud (for the voice-interrupt echo filter). */
  speakingText?: string;
  /** Stop the reply being read aloud (Interrupt button, Space, or voice). */
  onInterrupt?: () => void;
  /** Hands-free only: speaking over a reply interrupts it. Off by default (speakers can echo). */
  voiceInterrupt?: boolean;
  prefs?: ComposerVoicePrefs;
  onPrefsChange?: (patch: Partial<ComposerVoicePrefs>) => void;
  playCue?: (cue: Cue) => void;
  /** Resolves the browser's microphone permission ("granted" skips the explainer). */
  micPermission?: () => Promise<PermissionState | "unknown">;
  getGrant: (mode: ListenMode) => Promise<VoiceGrant>;
  createListener: (grant: VoiceGrant, events: ListenerEvents) => Listener;
}) {
  const id = useId();
  const [text, setText] = useState("");
  const [kind, setKind] = useState<"TEXT" | "VOICE_TRANSCRIPT">("TEXT");
  const [status, setStatus] = useState<Status>("idle");
  // Which mode is connecting, so the UI can say "don't talk yet" until the voice service is ready.
  const [connectingMode, setConnectingMode] = useState<ListenMode>("TAP");
  const [interim, setInterim] = useState("");
  const [countdown, setCountdown] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  // The free voice service reported its usage limit; temporary, so the learner can try again later.
  const [serviceBusy, setServiceBusy] = useState(false);
  const voiceAvailable = voiceConfigured && !voiceBlocked && !serviceBusy;
  const [level, setLevel] = useState(0);
  const [explain, setExplain] = useState<ListenMode | null>(null);
  const [offerHandsFree, setOfferHandsFree] = useState(prefs.handsFree);
  const [tapElapsed, setTapElapsed] = useState(0);
  const listener = useRef<Listener | null>(null);
  // Latest facts for listener callbacks and timers (updated in effects, read in handlers).
  const live = useRef({ speaking: false, speakingText: "", voiceInterrupt: false, since: 0, onInterrupt: undefined as (() => void) | undefined, status: "idle" as Status, sounds: prefs.sounds });
  const lastLoud = useRef(0);
  const reconnects = useRef<number[]>([]);
  const quotaHit = useRef(false); // the voice service reported its usage limit: stop instead of reconnecting
  const spaceRef = useRef<() => void>(() => undefined);
  const busy = Boolean(disabled || pending);

  const cue = (c: Cue) => {
    if (live.current.sounds) playCue?.(c);
  };
  const close = () => {
    const l = listener.current;
    listener.current = null; // set first: the resulting "closed" event is then ours, not a drop
    l?.close();
    setInterim("");
    setLevel(0);
  };
  useEffect(() => close, []);

  useEffect(() => {
    const v = live.current;
    if (speaking && !v.speaking) v.since = Date.now();
    Object.assign(v, { speaking, speakingText, voiceInterrupt, onInterrupt, status, sounds: prefs.sounds });
  }, [speaking, speakingText, voiceInterrupt, onInterrupt, status, prefs.sounds]);

  // When the conversation can't take a message (an item just completed, waiting for Continue), stop
  // listening and drop any unsent voice transcript, so nothing said meanwhile is sent afterwards.
  // Hands-free stays off until the learner turns it on again; it never restarts by itself.
  useEffect(() => {
    if (!disabled) return;
    const t = setTimeout(() => {
      const wasListening = listener.current !== null || live.current.status !== "idle";
      close();
      setCountdown(null);
      if (kind === "VOICE_TRANSCRIPT") {
        setText("");
        setKind("TEXT");
      }
      if (wasListening) {
        setStatus("idle");
        cue("stop");
        setNotice("Hands-free is off while this item is complete. Turn it on again after you continue.");
      }
    }, 0);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [disabled]);

  // Hands-free never listens while sending, nor during playback unless voice interrupt is on.
  useEffect(() => {
    if (status !== "hands-free" || !listener.current) return;
    if (pending || (speaking && !voiceInterrupt)) listener.current.pause();
    else listener.current.resume();
  }, [status, pending, speaking, voiceInterrupt]);

  const submit = async (value = text, inputKind = kind) => {
    if (!value.trim() || busy) return false;
    setCountdown(null);
    const ok = await onSend(value.trim(), inputKind);
    if (ok) {
      setText("");
      setKind("TEXT");
    }
    return ok;
  };

  // Hands-free auto-send after a visible countdown (COUNTDOWN_SECONDS, then send).
  // A countdown already running when the box locks (item complete) is cancelled, never sent later.
  useEffect(() => {
    if (countdown === null || disabled) return;
    const t = setTimeout(() => {
      if (countdown <= 1) {
        setCountdown(null);
        void submit(text, "VOICE_TRANSCRIPT");
      } else setCountdown(countdown - 1);
    }, 1000);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [countdown, text, disabled]);

  const fail = (e: unknown) => {
    close();
    setStatus("idle");
    if (e instanceof WorkWeaveError && e.error.code === "LIMIT_REACHED" && e.error.limit) {
      onLimit?.(e.error.limit); // the composer shows the limit notice; no error line on top of it
      return;
    }
    if (e instanceof VoiceError && e.kind === "BUSY") {
      setServiceBusy(true);
      return;
    }
    setError(e instanceof VoiceError || e instanceof Error ? e.message : "Voice stopped working. Type instead, or try again.");
  };

  const open = async (mode: ListenMode, opts: { skipExplainer?: boolean; reconnect?: boolean } = {}) => {
    setError(null);
    setNotice(null);
    if (!opts.skipExplainer && !prefs.micExplained) {
      const permission = micPermission ? await micPermission().catch(() => "unknown" as const) : "unknown";
      if (permission !== "granted") {
        setExplain(mode);
        return;
      }
    }
    setConnectingMode(mode);
    setStatus("connecting");
    try {
      const grant = await getGrant(mode);
      const l = createListener(grant, {
        onLevel: (v) => {
          if (v > LOUD) lastLoud.current = Date.now();
          setLevel(v);
        },
        onInterim: (t) => {
          if (listener.current !== l) return; // a late transcript from a closed listener
          const v = live.current;
          if (v.speaking) {
            // During playback the mic may hear the tutor. Only a real barge-in counts; echo is dropped.
            if (!(v.voiceInterrupt && Date.now() - v.since > BARGE_IN_GRACE_MS && isBargeIn(t, v.speakingText))) return;
            v.speaking = false;
            v.onInterrupt?.();
            l.discardPending();
          }
          setInterim(t);
        },
        onUtterance: (t) => {
          if (listener.current !== l) return; // a late transcript from a closed listener (e.g. item completed)
          if (live.current.speaking) return; // heard during playback without a barge-in: the tutor's echo
          setInterim("");
          setKind("VOICE_TRANSCRIPT");
          if (mode === "HANDS_FREE") {
            setText((prev) => (prev.trim() ? `${prev.trim()} ${t}` : t));
            setCountdown(COUNTDOWN_SECONDS);
          } else setText(t);
        },
        onError: (e) => {
          if (e.kind === "BUSY") quotaHit.current = true;
          if (e.kind === "BUSY") setServiceBusy(true);
          else setError(e.message);
        },
        onState: (s) => {
          if (s !== "closed" || listener.current !== l) return; // our own close, or an older listener
          // The Live session ended on its own (time limit, network, usage limit).
          listener.current = null;
          setInterim("");
          setLevel(0);
          if (quotaHit.current) {
            quotaHit.current = false;
            setStatus("idle");
            cue("stop");
          } else if (live.current.status === "hands-free") void reconnectHandsFree();
          else if (live.current.status === "tap") {
            setStatus("idle");
            cue("stop");
          }
        },
      });
      listener.current = l;
      await l.start();
      lastLoud.current = clock();
      setTapElapsed(0);
      setStatus(mode === "TAP" ? "tap" : "hands-free");
      if (!opts.reconnect) cue("start");
    } catch (e) {
      fail(e);
    }
  };

  const reconnectHandsFree = async () => {
    const now = clock();
    reconnects.current = reconnects.current.filter((t) => now - t < 60_000);
    if (reconnects.current.length >= RECONNECTS_PER_MINUTE) {
      setStatus("idle");
      cue("stop");
      setError("Hands-free stopped because the connection kept dropping. Turn it on again when you're ready, or type.");
      return;
    }
    reconnects.current.push(now);
    await open("HANDS_FREE", { skipExplainer: true, reconnect: true });
  };

  const stopTap = async (why?: string) => {
    const l = listener.current;
    if (!l) return;
    setStatus("finishing");
    await l.finish();
    if (listener.current === l) listener.current = null;
    setInterim("");
    setLevel(0);
    setStatus("idle");
    cue("stop");
    if (why) setNotice(why);
  };

  // Tap-to-talk limits: warn near 2 minutes, stop at 2 minutes or after 10 s of silence.
  useEffect(() => {
    if (status !== "tap") return;
    const started = Date.now();
    const t = setInterval(() => {
      const elapsed = Date.now() - started;
      setTapElapsed(elapsed);
      if (elapsed >= TAP_MAX_MS) void stopTap("Stopped after 2 minutes. Review the transcript and send it, or talk again.");
      else if (Date.now() - lastLoud.current >= TAP_SILENCE_MS) void stopTap("Stopped after 10 seconds of silence. Review the transcript and send it, or talk again.");
    }, 1000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  const toggleHandsFree = () => {
    if (status === "hands-free") {
      setCountdown(null);
      close();
      setStatus("idle");
      cue("stop");
      onPrefsChange?.({ handsFree: false });
    } else {
      setOfferHandsFree(false);
      onPrefsChange?.({ handsFree: true });
      void open("HANDS_FREE");
    }
  };

  /** Stop the reply being read aloud; in tap-to-talk, start listening right away. */
  const interrupt = () => {
    if (!speaking) return;
    onInterrupt?.();
    listener.current?.discardPending();
    if (status === "idle" && voiceAvailable && !busy) void open("TAP");
  };

  // Space mirrors the mic button: interrupt a reply, start tap-to-talk, or stop and review.
  const onSpace = () => {
    if (speaking && (status === "idle" || status === "hands-free")) return interrupt();
    if (!voiceAvailable || busy || explain) return;
    if (status === "idle") void open("TAP");
    else if (status === "tap") void stopTap();
  };
  useEffect(() => {
    spaceRef.current = onSpace;
  });
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.code !== "Space" && e.key !== " ") || e.repeat || e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
      const t = e.target as HTMLElement | null;
      if (t && (["TEXTAREA", "INPUT", "SELECT", "BUTTON", "A"].includes(t.tagName) || t.isContentEditable || t.closest?.('[role="dialog"]'))) return;
      e.preventDefault();
      spaceRef.current();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const listening = status === "tap" || status === "hands-free";
  const shown = listening && interim ? interim : text;
  const help = `${id}-voice`;
  const hearing = listening && level > LOUD;

  return (
    <div className="composer">
      {explain && (
        <div className="notice notice-info" role="note">
          <span className="notice-title">Your browser will ask to use the microphone</span>
          <span>Speech goes straight to speech-to-text and comes back as text you can review. Audio isn&apos;t recorded or stored.</span>
          <span className="row" style={{ marginTop: 8 }}>
            <button
              className="btn btn-small btn-primary"
              onClick={() => {
                const mode = explain;
                setExplain(null);
                onPrefsChange?.({ micExplained: true });
                void open(mode, { skipExplainer: true });
              }}
            >
              Continue
            </button>
            <button className="btn btn-small" onClick={() => setExplain(null)}>
              Not now
            </button>
          </span>
        </div>
      )}
      {voiceBlocked && voiceConfigured && (
        <div className="notice notice-quiet" role="status" data-testid="voice-limit">
          <span className="notice-title">Voice input is paused for today</span>
          <span>
            {voiceBlocked.scope === "RUN" ? "This demo workspace has used its voice inputs." : "The demo's shared voice allowance is used up."} Keep going by typing; the tutor
            treats typed answers exactly the same. Voice is back at {resetTime(voiceBlocked.resets_at)}.
          </span>
        </div>
      )}
      {serviceBusy && !voiceBlocked && voiceConfigured && (
        <div className="notice notice-quiet" role="status" data-testid="voice-busy">
          <span className="notice-title">Voice is busy right now</span>
          <span>The voice service is at its free usage limit. Keep going by typing; you can try voice again in a few minutes.</span>
          <span>
            <button className="btn btn-small" onClick={() => setServiceBusy(false)}>
              Try voice again
            </button>
          </span>
        </div>
      )}
      {offerHandsFree && voiceAvailable && status === "idle" && !explain && (
        <div className="listening" role="note">
          <span style={{ flex: 1 }}>Hands-free was on last time.</span>
          <button className="btn btn-small" onClick={toggleHandsFree} disabled={busy}>
            Turn on hands-free
          </button>
          <button
            className="btn btn-small btn-ghost"
            onClick={() => {
              setOfferHandsFree(false);
              onPrefsChange?.({ handsFree: false });
            }}
          >
            Dismiss
          </button>
        </div>
      )}
      {status === "connecting" && (
        <div className="listening listening-wait" role="status" aria-live="polite" data-testid="voice-connecting">
          <span className="listening-dot listening-dot-wait" aria-hidden="true" />
          <span style={{ flex: 1 }}>
            {connectingMode === "HANDS_FREE" ? "Connecting hands-free…" : "Connecting…"} <b>Wait a moment before you talk.</b>
          </span>
        </div>
      )}
      {listening && (
        <div className="listening" role="status" aria-live="polite" data-testid="voice-ready">
          <span className="listening-dot" aria-hidden="true" />
          <span className="mic-meter" aria-hidden="true">
            <span style={{ width: `${Math.round(Math.min(1, level) * 100)}%` }} />
          </span>
          <span style={{ flex: 1 }}>
            {status === "tap"
              ? tapElapsed >= TAP_WARN_MS
                ? `Stopping in ${Math.max(0, Math.ceil((TAP_MAX_MS - tapElapsed) / 1000))}s. Tap Stop or press Space to finish now.`
                : hearing
                  ? "Hearing you. Tap Stop or press Space when you're done."
                  : <><b>You can talk now.</b> Tap Stop or press Space when you&apos;re done.</>
              : speaking && !voiceInterrupt
                ? "Hands-free paused while the reply is read aloud."
                : pending
                  ? "Hands-free paused while sending."
                  : hearing
                    ? "Hearing you. Pause when you're done and I'll send it."
                    : <><b>You can talk now.</b> Hands-free is listening; pause when you&apos;re done and I&apos;ll send it.</>}
          </span>
        </div>
      )}
      {countdown !== null && (
        <div className="listening" role="status" aria-live="assertive">
          <span style={{ flex: 1 }}>Sending in {countdown}s…</span>
          <button className="btn btn-small" onClick={() => setCountdown(null)}>
            Cancel and edit
          </button>
        </div>
      )}
      {error && (
        <p className="small" role="alert">
          {error}
        </p>
      )}
      {notice && !error && (
        <p className="small muted" role="status">
          {notice}
        </p>
      )}
      {kind === "VOICE_TRANSCRIPT" && !listening && countdown === null && text && <span className="small muted">Voice transcript. Edit it if needed, then send.</span>}
      <label className="composer-label" htmlFor={`${id}-input`}>
        {label}
      </label>
      <textarea
        id={`${id}-input`}
        value={shown}
        rows={2}
        placeholder={placeholder}
        disabled={disabled}
        readOnly={listening && Boolean(interim)}
        onChange={(e) => {
          setCountdown(null); // typing always takes over from an auto-send
          setText(e.target.value);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            void submit();
          }
        }}
      />
      <div className="composer-controls">
        <div className="row">
          {speaking && (status === "idle" || status === "hands-free") ? (
            <button className="btn btn-small mic" onClick={interrupt} aria-keyshortcuts="Space" title="Stop the reply and talk (Space)">
              Interrupt (Space)
            </button>
          ) : status === "tap" || status === "finishing" ? (
            <button className="btn btn-small mic" onClick={() => void stopTap()} disabled={status === "finishing"} aria-keyshortcuts="Space">
              {status === "finishing" ? "Finishing…" : "Stop (Space)"}
            </button>
          ) : (
            <button
              className="btn btn-small mic"
              aria-describedby={help}
              disabled={!voiceAvailable || busy || status !== "idle" || Boolean(explain)}
              onClick={() => void open("TAP")}
              aria-keyshortcuts="Space"
              title="Tap to talk (Space)"
            >
              {status === "connecting" ? "Connecting…" : "Tap to talk"}
            </button>
          )}
          <label className="small row" style={{ gap: 6 }}>
            <input
              type="checkbox"
              role="switch"
              checked={status === "hands-free"}
              disabled={!voiceAvailable || Boolean(disabled) || status === "tap" || status === "finishing" || status === "connecting" || Boolean(explain)}
              onChange={toggleHandsFree}
            />
            Hands-free
          </label>
          <label className="small row" style={{ gap: 6 }}>
            <input type="checkbox" checked={prefs.sounds} disabled={!voiceAvailable} onChange={(e) => onPrefsChange?.({ sounds: e.target.checked })} />
            Sounds
          </label>
          <span id={help} className="small muted">
            {voiceAvailable ? "Press Space to talk. Transcripts appear here before they're sent." : voiceBlocked || serviceBusy ? "Voice is paused; type your message." : unavailableReason}
          </span>
        </div>
        <button className="btn btn-primary" onClick={() => void submit()} disabled={busy || !text.trim() || countdown !== null}>
          {pending ? "Sending…" : "Send"}
        </button>
      </div>
    </div>
  );
}
