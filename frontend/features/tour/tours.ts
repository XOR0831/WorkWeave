/**
 * The optional page tours (owner, 2026-10-11): a few steps per module, each pointing at a real part of
 * the page by CSS selector. A step whose target isn't on the page (for example a shift lead's control
 * shown to a member, or an empty list) is skipped, so one tour fits every role. A step without a
 * target is a centred card.
 */
export interface TourStep {
  target?: string;
  title: string;
  body: string;
  /** Different text in the UI preview, where the control does something else. */
  preview?: { title: string; body: string };
}

export type TourKey =
  | "home"
  | "onboarding"
  | "onboarding-session"
  | "companion"
  | "ticket-system"
  | "handover"
  | "exit-kt"
  | "reviews"
  | "knowledge"
  | "curricula";

export interface Tour {
  name: string;
  steps: TourStep[];
}

export const TOURS: Record<TourKey, Tour> = {
  home: {
    name: "Home",
    steps: [
      { target: 'section[aria-labelledby="h-next"]', title: "Your next step", body: "The most useful thing to do now, picked from your role and today's work. Start here when you're not sure what's next." },
      { target: 'section[aria-labelledby="h-learning"]', title: "Learning", body: "Where your onboarding stands. Continue the conversation with the tutor from here." },
      { target: 'section[aria-labelledby="h-work"]', title: "Today's work", body: "Your tickets for the shift. Open the Work Companion to talk through them." },
      { target: 'section[aria-labelledby="h-shift"]', title: "Your shift", body: "How long the shift has left and, for shift leads, the handover to the next shift." },
      { target: 'section[aria-labelledby="h-kt"]', title: "Knowledge transfer", body: "Any departure or role change you're part of, and what's still open in it." },
      { target: 'nav[aria-label="Modules"]', title: "All modules", body: "Every module is here. Each one offers its own short tour the first time you open it." },
      { target: '[data-tour="demo-tools"]', title: "Demo tools", body: "Tools for exploring the demo. Advance to next shift moves this run's clock to the middle of the next shift, so you can see a handover arrive and the next shift's work. Only your demo copy changes.",
        preview: { title: "Review tools", body: "Tools for reviewing the preview: simulate slow or failing requests, show the voice listening state, revoke a source, move the shift clock, or reset the workspace. Nothing leaves this browser tab." } },
      { target: '[data-testid="demo-limits"]', title: "Demo limits", body: "How much of today's demo allowance this workspace has used, and where to enter an evaluator code." },
      { target: '[data-tour="page-tour"]', title: "See a tour again", body: "Use Page tour any time to replay the tour for the page you're on." },
    ],
  },
  onboarding: {
    name: "Onboarding",
    steps: [
      { target: 'section[aria-labelledby="h-progress"]', title: "Your progress", body: "How far you are through your assigned curriculum. Progress only moves when you show understanding in the conversation." },
      { target: 'section[aria-labelledby="h-progress"] .btn-primary', title: "Start or continue", body: "Opens the conversation with the tutor. It picks up where you left off." },
      { target: 'section[aria-labelledby="h-path"]', title: "Learning path", body: "The topics ahead, in order, from the approved company documents." },
    ],
  },
  "onboarding-session": {
    name: "Onboarding conversation",
    steps: [
      { target: 'section[aria-labelledby="h-tutor"]', title: "Learn by talking", body: "The tutor explains one idea at a time and checks your understanding with a question. Answer in your own words." },
      { target: 'section[aria-labelledby="h-tutor"] .composer', title: "Type or speak", body: "Type your answer, or tap the microphone to speak (hands-free is optional). Only the text is kept, never the audio." },
      { target: 'aside[aria-label="Learning path and reference"]', title: "Path and sources", body: "Where you are in the path, and the exact document excerpt the tutor is teaching from." },
    ],
  },
  companion: {
    name: "Work Companion",
    steps: [
      { target: 'aside[aria-label="Conversation"]', title: "Talk about your work", body: "Ask what to focus on, how to do a step, or say what happened, for example \"#829 is done, the cause was loose bolts\". Shift leads can also hand tickets to teammates here." },
      { target: 'aside[aria-label="Conversation"] .composer', title: "Type or speak", body: "Type, or use the microphone. Replies can be read aloud." },
      { target: 'section[aria-labelledby="h-dash"]', title: "Your shift at a glance", body: "Your tickets, what's due and what's blocked. It stays in place while you talk." },
      { target: 'section[aria-labelledby="h-canvas"]', title: "The work area follows the conversation", body: "When you ask about a ticket or a procedure, it opens here, with its sources." },
      { target: '[data-tour="ticket-system"]', title: "The ticket system", body: "Reporting work in the chat doesn't close a ticket. The ticket's assignee changes its status in the ticket system, and WorkWeave matches the two." },
      { target: '[data-tour="capture"]', title: "Capture knowledge", body: "Write down something worth keeping. It goes to a reviewer before anyone else can rely on it." },
    ],
  },
  "ticket-system": {
    name: "Ticket system",
    steps: [
      { target: "main table", title: "Your team's tickets", body: "A stand-in for the company's real ticket tool. Each ticket's status here is its real status." },
      { target: '[data-tour="ticket-detail"]', title: "Change a ticket", body: "Only the ticket's assignee can start, block, resolve or cancel it. Add a work note to say what changed." },
    ],
  },
  handover: {
    name: "Shift Handover",
    steps: [
      { target: ".handover-band", title: "This shift's handover", body: "Which shift hands over to which. You prepare it during your shift and publish it directly; there's no second reviewer." },
      { target: 'ol[aria-label="Shift occurrences"]', title: "Shifts", body: "The shifts on your team today, and which one is in progress." },
      { target: ".doc-panel", title: "The handover document", body: "Your team's template, one section at a time. Items carry over between shifts until they're resolved." },
      { target: 'aside[aria-label="Handover companion"]', title: "The handover companion", body: "Ask about anything in the handover. It answers from the records and can suggest an edit, which only changes the draft if you apply it." },
      { target: '[data-tour="check-gaps"]', title: "Check for gaps", body: "Looks for open work missing from the handover, outdated notes and duplicates. Its suggestions wait for your review." },
      { target: '[data-tour="publish"]', title: "Review and publish", body: "Publishing makes a snapshot the next shift's lead reads and confirms. The snapshot never changes afterwards." },
    ],
  },
  "exit-kt": {
    name: "Exit Knowledge Transfer",
    steps: [
      { target: 'section[aria-labelledby="h-case"]', title: "The case", body: "Who is leaving or changing role, who takes over, and how complete the transfer is." },
      { target: 'div[aria-label="Exit KT areas"]', title: "Areas", body: "Knowledge to capture, responsibilities to transfer, the successor package and the checklist. Each step needs a person to confirm it." },
      { target: ".kt-panel", title: "Work through an area", body: "Run discovery to see what the records show, interview for what's undocumented, and draft artifacts for review. Nothing becomes shared knowledge until it's approved." },
      { target: 'section[aria-label="Knowledge-transfer assistant"]', title: "Ask the assistant", body: "Questions about this case, answered from its records. Your conversation is private to you." },
    ],
  },
  reviews: {
    name: "Reviews",
    steps: [
      { target: ".page-head", title: "Your review queue", body: "Knowledge notes, Exit KT artifacts and successor packages waiting for your decision." },
      { target: "main .list-item", title: "Decide on one", body: "Read the exact submitted version, add a comment if you like, then approve or reject. Approving a note keeps it labelled as a reported observation." },
    ],
  },
  knowledge: {
    name: "Knowledge",
    steps: [
      { target: ".page-head", title: "Knowledge and history", body: "Approved knowledge and how it changed over time, with where each piece came from." },
      { target: '[data-tour="knowledge-filter"]', title: "Filter", body: "Show only what's current, what's historical, or what's still waiting for review." },
      { target: "main .list", title: "Open the source", body: "Each entry is labelled observed, reported, inferred or unknown. Open one to read the original text." },
    ],
  },
  curricula: {
    name: "Curricula & sources",
    steps: [
      { target: 'ol[aria-label="How a source becomes curriculum content"]', title: "From document to curriculum", body: "A source is uploaded, reviewed, indexed and then mapped to topics. Only approved versions are taught." },
      { target: ".curriculum-card", title: "A curriculum", body: "Its topics, sources and who it's assigned to. Open it to see the outline and the source behind each topic." },
    ],
  },
};

/** Which tour belongs to the page at `pathname` (most specific first). */
export function tourFor(pathname: string | null | undefined): TourKey | null {
  const p = pathname ?? "";
  const map: [string, TourKey | null][] = [
    ["/home", "home"],
    ["/onboarding/session", "onboarding-session"],
    ["/onboarding/progress", null], // the supervisor's team progress: no tour yet
    ["/onboarding", "onboarding"],
    ["/companion/tool", "ticket-system"],
    ["/companion", "companion"],
    ["/handover", "handover"],
    ["/exit-kt", "exit-kt"],
    ["/reviews", "reviews"],
    ["/memory", "knowledge"],
    ["/curricula", "curricula"],
  ];
  return map.find(([prefix]) => p.startsWith(prefix))?.[1] ?? null;
}
