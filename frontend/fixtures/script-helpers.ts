import type { SubtopicScript } from "./types";

/** Builds a short scripted subtopic (open → answer → check → hint/partial → complete). */
export function simpleSubtopic(p: {
  id: string;
  excerpt: string;
  opening: string;
  answerPrompt: string;
  teaching: string;
  check: string;
  partial: string;
  partialFeedback: string;
  correct: string;
  correctFeedback: string;
  hint: string;
}): SubtopicScript {
  return {
    subtopic_id: p.id,
    opening: [{ kind: "TEACHING", text: p.opening, excerpt_keys: [p.excerpt] }],
    resume: [{ kind: "OPENING", text: "Welcome back, {name}. Let's pick up where we left off.", excerpt_keys: [p.excerpt] }],
    steps: [
      {
        stage: 0,
        advances: true,
        prompt: { prompt_id: `${p.id}-a`, label: "Answer the question", text: p.answerPrompt },
        responses: [{ kind: "TEACHING", text: p.teaching, excerpt_keys: [p.excerpt] }],
      },
      {
        stage: 1,
        advances: true,
        prompt: { prompt_id: `${p.id}-ready`, label: "Ask to be checked", text: "Can you check my understanding?" },
        responses: [
          { kind: "CHECK", text: p.check, excerpt_keys: [p.excerpt], check: { question_id: `${p.id}-q`, objective_id: `${p.id}-obj` } },
        ],
      },
      {
        stage: 2,
        prompt: { prompt_id: `${p.id}-hint`, label: "Ask for a hint", text: "Can I have a hint?" },
        responses: [{ kind: "HINT", text: `${p.hint} A hint doesn't count as an answer; the question is still open.`, excerpt_keys: [p.excerpt] }],
      },
      {
        stage: 2,
        prompt: { prompt_id: `${p.id}-partial`, label: "Give a partial answer", text: p.partial },
        responses: [
          { kind: "FEEDBACK", text: p.partialFeedback, excerpt_keys: [p.excerpt], assessment: { outcome: "PARTIAL", note: "Part of the criteria met." } },
        ],
      },
      {
        stage: 2,
        advances: true,
        completes_subtopic: true,
        prompt: { prompt_id: `${p.id}-correct`, label: "Give a complete answer", text: p.correct },
        responses: [
          { kind: "FEEDBACK", text: p.correctFeedback, excerpt_keys: [p.excerpt], assessment: { outcome: "CORRECT", note: "Meets use_current_approved_evidence and keep_unknowns_explicit." } },
        ],
      },
    ],
  };
}
