/**
 * In-memory workspace state for the UI preview.
 *
 * Mirrors the shape of an isolated, version-pinned demo workspace so screens can be reviewed.
 * Guards applied by the preview engine imitate the documented contract rules for review purposes
 * only; they are not authorization, persistence or transaction evidence.
 */
import { PACKS } from "@/fixtures";
import type { PackFixture } from "@/fixtures/types";
import type {
  CompletionCycle,
  DelegationProposal,
  DocumentVersion,
  DraftSection,
  ExitKtCase,
  HandoverItem,
  HandoverItemEvent,
  HandoverPublication,
  HandoverSuggestion,
  HandoverStatus,
  InboxNotification,
  MemoryDraft,
  ProgressStatus,
  ScenarioKey,
  ShiftOccurrence,
  TimelineEntry,
  TranscriptMessage,
  WorkEvent,
  WorkItem,
  WorkMessage,
  CanvasView,
  TemplateSection,
  Curriculum,
  SourceReviewReceipt,
} from "@/types/contracts";

export interface LearnerSession {
  learning_session_id: string;
  revision: number;
  status: "ACTIVE" | "PAUSED" | "COMPLETED";
  transcript: TranscriptMessage[];
  current_subtopic_id: string;
  stage: Record<string, number>;
  played: string[];
  pending_check?: { question_id: string; objective_id: string; text: string };
  awaiting_continue: boolean;
}

export interface LearnerState {
  employee_id: string;
  learning_assignment_id: string;
  progress: Record<string, ProgressStatus>;
  saved_label?: string;
  session?: LearnerSession;
}

export interface WorkSessionState {
  work_session_id: string;
  revision: number;
  transcript: WorkMessage[];
  canvas: CanvasView;
  pending_report?: { work_item_id: string; draft: string };
}

/** The lead's latest unpublished changes (the preview's "Just updated" highlight). */
export type ChangeEntry =
  | { kind: "SECTION"; section_id: string; previous: DraftSection; label: string }
  | { kind: "ITEM"; item: HandoverItem; suggestion_id?: string; created?: boolean; label: string };

export interface HandoverState {
  handover_id: string;
  revision: number;
  status: HandoverStatus;
  occurrences: ShiftOccurrence[];
  source_id: string;
  target_id: string;
  items: HandoverItem[];
  draft_sections: DraftSection[];
  suggestions: HandoverSuggestion[];
  publications: HandoverPublication[];
  cycles: CompletionCycle[];
  item_events: HandoverItemEvent[];
  changes: ChangeEntry[];
  copilot: Record<string, WorkMessage[]>;
  /** Lead-created template version; absent means the pack's template version is in use. */
  template?: { version: string; sections: TemplateSection[] };
}

export interface WorkspaceState {
  key: ScenarioKey;
  workspace_id: string;
  persona_id: string;
  persona_selected: boolean;
  pack_version: string;
  seq: number;
  learners: Record<string, LearnerState>;
  items: WorkItem[];
  events: WorkEvent[];
  proposal: DelegationProposal;
  workSessions: Record<string, WorkSessionState>;
  memoryDrafts: MemoryDraft[];
  handover: HandoverState;
  exitKt: ExitKtCase;
  extraCases: ExitKtCase[];
  notifications: Record<string, InboxNotification[]>;
  extraDocuments: DocumentVersion[];
  extraTimeline: TimelineEntry[];
  revokedVersions: string[];
  /** Coordinator curricula; created lazily so runs saved before this feature keep loading. */
  curricula?: { items: Curriculum[]; receipts: SourceReviewReceipt[] };
}

const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v)) as T;

export function createWorkspace(key: ScenarioKey): WorkspaceState {
  const pack: PackFixture = PACKS[key];
  const learners: Record<string, LearnerState> = {};
  for (const l of pack.onboarding.learners) {
    const progress: Record<string, ProgressStatus> = {};
    for (const t of pack.onboarding.topics) for (const s of t.subtopics) progress[s.subtopic_id] = "NOT_STARTED";
    for (const id of l.completed) progress[id] = "COMPLETED";
    if (l.in_progress) progress[l.in_progress] = "IN_PROGRESS";
    learners[l.employee_id] = {
      employee_id: l.employee_id,
      learning_assignment_id: l.learning_assignment_id,
      progress,
      saved_label: l.completed.length || l.in_progress ? "Saved yesterday" : undefined,
    };
  }
  const h = pack.handover;
  return {
    key,
    workspace_id: `ws-${key}-${Math.random().toString(36).slice(2, 8)}`,
    persona_id: pack.personas[0]!.employee_id,
    persona_selected: false,
    pack_version: pack.card.pack_version,
    seq: 1,
    learners,
    items: clone(pack.work_items),
    events: clone(pack.work_events),
    proposal: clone(pack.proposal),
    workSessions: {},
    memoryDrafts: [],
    handover: {
      handover_id: `${key}-handover-current`,
      revision: 1,
      status: "DRAFT",
      occurrences: clone(h.occurrences),
      source_id: h.source_shift_id,
      target_id: h.target_shift_id,
      items: clone(h.items),
      draft_sections: clone(h.draft_sections),
      suggestions: clone(h.suggestions),
      publications: clone(h.publications),
      cycles: [],
      item_events: h.items.map((i) => ({
        event_id: `${i.handover_item_id}-created`,
        handover_item_id: i.handover_item_id,
        label: "Carried into handover",
        shift_name: h.occurrences.find((o) => o.shift_instance_id === i.originating_shift_instance_id)?.name ?? "",
      })),
      changes: [],
      copilot: {},
    },
    exitKt: clone(pack.exit_kt.case),
    extraCases: [],
    notifications: {},
    extraDocuments: [],
    extraTimeline: [],
    revokedVersions: [],
  };
}
