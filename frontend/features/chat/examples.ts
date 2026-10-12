/**
 * Example things to say in each chat (owner feedback, 2026-10-13). Each one is something that module's
 * graph handles, worded as the person would say it, so it can be clicked (sent as typed) or read aloud
 * in hands-free mode. Names and ticket numbers come from the current demo, never hard-coded.
 */
export interface Example {
  /** Sent exactly as shown. */
  text: string;
}

const ex = (...texts: (string | false | undefined)[]): Example[] => texts.filter((t): t is string => Boolean(t)).map((text) => ({ text }));

/** "Ticket #829 · Machine #14 inspection · Due in 1 h" -> "Ticket #829" (dashboard priority lines). */
export function ticketOf(priority: string | undefined): string | undefined {
  const head = priority?.split(" · ")[0]?.trim();
  return head && /#\d+|[A-Z]+-\d+/.test(head) ? head : undefined;
}

/** Work Companion: the shift lead plans and delegates; a member works their own tickets. */
export function companionExamples(o: { lead: boolean; ticket?: string; teammate?: string }): Example[] {
  if (o.lead)
    return ex(
      "What should the team focus on first?",
      "List the team's open tickets",
      o.ticket && `Who should take ${o.ticket}?`,
      o.ticket && o.teammate && `Assign ${o.ticket} to ${o.teammate}`,
      "Check my schedule today",
      "Read replies aloud",
    );
  return ex(
    "What's on my plate today?",
    "List my tickets",
    o.ticket && `How do I do the next step on ${o.ticket}?`,
    o.ticket && `I've started ${o.ticket}`,
    o.ticket && `I'm blocked on ${o.ticket}`,
    "Check my schedule today",
    "Read replies aloud",
  );
}

/** Onboarding tutor: how the learner steers the lesson (answers to its questions are their own). */
export const ONBOARDING_EXAMPLES: Example[] = ex(
  "I'm ready, let's start",
  "Can you explain that more simply?",
  "Give me an example",
  "Why does that step matter?",
  "Can you repeat the last part?",
  "Let's take a break",
);

/** Shift Handover companion: the outgoing lead prepares the handover; the incoming lead catches up. */
export function handoverExamples(o: { outgoing: boolean; item?: string }): Example[] {
  if (o.outgoing)
    return ex(
      "What's missing from this handover?",
      "What should I tell the incoming lead?",
      "What's still blocked?",
      o.item && `Summarize ${o.item}`,
      "What changed this shift?",
    );
  return ex("What do I need to know for my shift?", "What's still blocked?", "What changed since the last shift?", o.item && `Summarize ${o.item}`, "What's most urgent?");
}

/** Exit KT companion (the case workspace). */
export function ktExamples(o: { responsibility?: string }): Example[] {
  return ex(
    "What's most at risk?",
    "What still needs capturing?",
    o.responsibility && `Who could take over ${o.responsibility}?`,
    "What should my successor learn first?",
    "Which procedures does this cover?",
  );
}
