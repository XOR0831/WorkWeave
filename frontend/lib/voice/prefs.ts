/**
 * Voice preferences remembered in this browser only (a per-viewer convenience). Storage can be
 * unavailable (private windows, blocked site data), so every read and write is guarded and the
 * defaults always work.
 */
export interface VoicePrefs {
  readAloud: boolean;
  voiceInterrupt: boolean;
  speed: 0.9 | 1 | 1.25;
  sounds: boolean;
  /** Hands-free was on last time. It is offered again, never switched on without a tap. */
  handsFree: boolean;
  /** The microphone explainer has been shown in this browser. */
  micExplained: boolean;
  /** The "hear the tutor?" offer has been answered (turned on or dismissed); it isn't shown again. */
  readAloudOffered: boolean;
}

const KEY = "ww.voice.prefs.v1";
export const SPEEDS: VoicePrefs["speed"][] = [0.9, 1, 1.25];

export function defaultPrefs(quiet = false): VoicePrefs {
  return { readAloud: false, voiceInterrupt: false, speed: 1, sounds: !quiet, handsFree: false, micExplained: false, readAloudOffered: false };
}

export function loadPrefs(quiet = false): VoicePrefs {
  const base = defaultPrefs(quiet);
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return base;
    const p = JSON.parse(raw) as Partial<VoicePrefs>;
    return {
      readAloud: typeof p.readAloud === "boolean" ? p.readAloud : base.readAloud,
      voiceInterrupt: typeof p.voiceInterrupt === "boolean" ? p.voiceInterrupt : base.voiceInterrupt,
      speed: SPEEDS.includes(p.speed as VoicePrefs["speed"]) ? (p.speed as VoicePrefs["speed"]) : base.speed,
      sounds: typeof p.sounds === "boolean" ? p.sounds : base.sounds,
      handsFree: typeof p.handsFree === "boolean" ? p.handsFree : base.handsFree,
      micExplained: typeof p.micExplained === "boolean" ? p.micExplained : base.micExplained,
      readAloudOffered: typeof p.readAloudOffered === "boolean" ? p.readAloudOffered : base.readAloudOffered,
    };
  } catch {
    return base;
  }
}

export function savePrefs(patch: Partial<VoicePrefs>, quiet = false): VoicePrefs {
  const next = { ...loadPrefs(quiet), ...patch };
  try {
    window.localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    /* storage unavailable: the preference lasts for this page only */
  }
  return next;
}

// A conversation the learner just started (Start conversation / Continue). Its opening is new, so it is
// read aloud (when read-aloud is on) even though it is already on screen when the page loads. Kept in
// this tab only; anything already on screen at a plain load or reload is history and is never replayed.
const FRESH = "ww.voice.fresh-start";

export function markFreshStart(learningSessionId: string): void {
  try {
    window.sessionStorage.setItem(FRESH, learningSessionId);
  } catch {
    /* storage unavailable: the opening simply isn't read aloud automatically */
  }
}

export function takeFreshStart(learningSessionId: string): boolean {
  try {
    const id = window.sessionStorage.getItem(FRESH);
    window.sessionStorage.removeItem(FRESH);
    return id === learningSessionId;
  } catch {
    return false;
  }
}

