/**
 * Short start/stop tones so hands-free learners know when listening begins and ends without
 * looking. Generated with Web Audio (no files). Off when the person prefers reduced motion, and
 * switchable in the voice settings.
 */
let ctx: AudioContext | null = null;

export type Cue = "start" | "stop";

export function playCue(kind: Cue) {
  try {
    ctx ??= new AudioContext();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    const t = ctx.currentTime;
    const [from, to] = kind === "start" ? [660, 880] : [880, 520];
    osc.frequency.setValueAtTime(from, t);
    osc.frequency.linearRampToValueAtTime(to, t + 0.09);
    gain.gain.setValueAtTime(0.0001, t);
    gain.gain.exponentialRampToValueAtTime(0.08, t + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.12);
    osc.connect(gain).connect(ctx.destination);
    osc.start(t);
    osc.stop(t + 0.13);
  } catch {
    /* audio unavailable: cues are optional */
  }
}

export function prefersQuiet(): boolean {
  try {
    return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
  } catch {
    return false;
  }
}
