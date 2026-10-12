/**
 * Shape of a UI-preview fixture pack.
 *
 * Packs are labelled synthetic review fixtures derived from src/local/postgres/02_seed.sql
 * (and the Northstar alignment overlay / SOP-001 Markdown sources). They are NOT validated
 * scenario packs (blueprint/16) and contain no real employee or customer data.
 *
 * Scripted conversation steps are recorded fixture playback for screen review. The preview
 * engine never inspects free text to choose a step (no keyword routing, build_spec.md §4/§9).
 */
import type {
  CanvasView,
  DelegationProposal,
  DocumentVersion,
  DraftSection,
  ExitKtCase,
  GuidanceProjection,
  HandoverItem,
  HandoverPublication,
  HandoverSuggestion,
  Persona,
  ScenarioCard,
  ScriptPrompt,
  ShiftOccurrence,
  SourceExcerpt,
  TemplateSection,
  TimelineEntry,
  Topic,
  TutorMessageKind,
  AssessmentOutcome,
  UiAction,
  WorkEvent,
  WorkItem,
} from "@/types/contracts";

export interface FixtureTutorMessage {
  kind: TutorMessageKind;
  text: string;
  excerpt_keys: string[];
  assessment?: { outcome: AssessmentOutcome; note: string };
  check?: { question_id: string; objective_id: string };
}

export interface OnboardingStep {
  prompt: ScriptPrompt;
  /** Steps are offered only while the subtopic script is at this stage. */
  stage: number;
  /** Playing this step moves the script to stage + 1. */
  advances?: boolean;
  responses: FixtureTutorMessage[];
  /** Fixture outcome that, once "saved", completes the current subtopic. */
  completes_subtopic?: boolean;
}

export interface SubtopicScript {
  subtopic_id: string;
  opening: FixtureTutorMessage[];
  resume: FixtureTutorMessage[];
  steps: OnboardingStep[];
}

export interface LearnerFixture {
  employee_id: string;
  learning_assignment_id: string;
  completed: string[];
  in_progress?: string;
}

export interface OnboardingFixture {
  curriculum_name: string;
  curriculum_version: string;
  source_version_ids: string[];
  topics: Topic[];
  learners: LearnerFixture[];
  scripts: SubtopicScript[];
  new_learner_greeting: string;
  curriculum_complete_text: string;
}

export type CompanionEffect =
  | { kind: "EDIT_PROPOSAL"; edits: { work_item_id: string; final_employee_id: string }[] }
  | { kind: "OPEN_REPORT"; work_item_id: string; draft: string }
  | { kind: "INVALID_ACTION"; attempted: string };

export interface CompanionStep {
  prompt: ScriptPrompt;
  reply: string;
  excerpt_keys: string[];
  ui_action: UiAction;
  canvas?: CanvasView;
  effect?: CompanionEffect;
}

export interface CompanionScript {
  employee_id: string;
  opening: string;
  steps: CompanionStep[];
}

export interface CopilotStep {
  prompt: ScriptPrompt;
  reply: string;
  excerpt_keys: string[];
  audience: "LEAD" | "INCOMING";
}

export interface HandoverFixture {
  template_name: string;
  template_version: string;
  sections: TemplateSection[];
  occurrences: ShiftOccurrence[];
  source_shift_id: string;
  target_shift_id: string;
  items: HandoverItem[];
  draft_sections: DraftSection[];
  suggestions: HandoverSuggestion[];
  publications: HandoverPublication[];
  copilot_opening: string;
  copilot_steps: CopilotStep[];
}

export interface ExitKtFixture {
  case: ExitKtCase;
  interview_opening: string;
  interview_steps: { prompt: ScriptPrompt; ai_follow_up: string }[];
  successor_steps: { prompt: ScriptPrompt; reply: string; excerpt_keys: string[] }[];
  draft_artifact_template: string;
}

export interface PackFixture {
  card: ScenarioCard;
  personas: Persona[];
  documents: DocumentVersion[];
  excerpts: Record<string, SourceExcerpt>;
  full_text: Record<string, string>;
  onboarding: OnboardingFixture;
  supervisor_ids: string[];
  work_items: WorkItem[];
  work_events: WorkEvent[];
  companion_scripts: CompanionScript[];
  guidance: GuidanceProjection[];
  proposal: DelegationProposal;
  priorities: Record<string, string[]>;
  handover: HandoverFixture;
  exit_kt: ExitKtFixture;
  timeline: TimelineEntry[];
}
