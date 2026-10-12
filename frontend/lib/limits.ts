import type { ApiError, DemoLimits, LimitInfo, LimitKind, LimitScope } from "@/types/contracts";

/** "8:00 AM" (today) or "Sat 8:00 AM" (another day), in the visitor's own time zone. */
export function resetTime(iso: string, now: Date = new Date()): string {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return "tomorrow";
  const time = at.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  return at.toDateString() === now.toDateString() ? time : `${at.toLocaleDateString(undefined, { weekday: "short" })} ${time}`;
}

/** The cap a LIMIT_REACHED error refers to, if it is one. */
export function limitOf(error: ApiError | null | undefined, kind?: LimitKind): LimitInfo | null {
  if (!error || error.code !== "LIMIT_REACHED" || !error.limit) return null;
  return !kind || error.limit.kind === kind ? error.limit : null;
}

export type Blocked = { scope: LimitScope; resets_at: string };

/** A capped feature is blocked if the server reported it or a request was just refused. */
export function blockedFrom(limits: DemoLimits | undefined, key: "tutor_turn" | "voice_listen" | "voice_speech", hit: LimitInfo | null): Blocked | null {
  if (hit) return { scope: hit.scope, resets_at: hit.resets_at };
  const s = limits?.[key];
  return s && !s.available ? { scope: s.scope ?? "GLOBAL", resets_at: limits.resets_at } : null;
}

/** Show a gentle count only when the allowance is nearly used. */
export const LOW_REMAINING = 10;
