/**
 * Frontend DTOs for the WorkWeave UI preview.
 *
 * Enum values and field names follow blueprint/04-data-model.md and build_spec.md §6.
 * Envelope/error shapes follow blueprint/07-api-contracts.md "Common transport".
 * These are view projections, not a database schema; the backend phase will
 * replace the preview adapter with an HTTP adapter implementing the same interface.
 */

// ---------- Transport ----------
export type ErrorCode =
  | "MALFORMED_INPUT"
  | "SESSION_EXPIRED"
  | "FORBIDDEN"
  | "NOT_FOUND"
  | "REVISION_CONFLICT"
  | "GUARD_FAILED"
  | "INVALID_SCHEMA"
  | "CAPABILITY_UNAVAILABLE"
  | "DEPENDENCY_UNAVAILABLE"
  | "LIMIT_REACHED"
  | "MODEL_OUTPUT_INVALID";

export interface ApiError {
  code: ErrorCode;
  message: string;
  retryable: boolean;
  /** LIMIT_REACHED only: which public-demo daily cap was hit and when it resets. */
  limit?: LimitInfo;
}

export type LimitKind = "DEMO_RUN" | "TUTOR_TURN" | "VOICE_LISTEN" | "VOICE_SPEECH";
/** RUN: this demo workspace's allowance. CODE: an access code's new workspaces. GLOBAL: the shared allowance. */
export type LimitScope = "RUN" | "CODE" | "GLOBAL";

export interface LimitInfo {
  kind: LimitKind;
  scope: LimitScope;
  /** ISO time (next 00:00 UTC). */
  resets_at: string;
}

export interface LimitState {
  available: boolean;
  scope: LimitScope | null;
  /** The smaller of this run's and the shared allowance left today; null when uncapped. */
  remaining: number | null;
}

export interface DemoLimits {
  tier?: "PUBLIC" | "EVALUATOR";
  resets_at: string;
  tutor_turn: LimitState;
  voice_listen: LimitState;
  voice_speech: LimitState;
}

export class WorkWeaveError extends Error {
  constructor(public readonly error: ApiError, public readonly request_id: string) {
    super(error.message);
    this.name = "WorkWeaveError";
  }
}

/** Every client response carries a request id (07-api-contracts). */
export interface Envelope<T> {
  request_id: string;
  data: T;
}

// ---------- Shared vocabulary ----------
export type ScenarioKey = "northstar" | "harbor" | "acme";
export type EvidenceType = "OBSERVED" | "REPORTED" | "INFERRED" | "UNKNOWN";
/** AI_ENGINE: prepared by the AI work assistant from a shift lead's request (ADR-034); a person confirms it. */
export type Origin = "SYNTHETIC_SEED" | "MANUAL" | "PREVIEW_FIXTURE" | "AI_ENGINE";

/** Pack-driven terminology so core screens never hardcode industry nouns. */
export interface Terminology {
  workItem: string; // "ticket", "case", "incident"
  workItems: string;
  team: string;
  asset?: string; // "machine", "account", "service"
  queue?: string; // BPO only
}

export interface ScenarioCard {
  scenario_id: string;
  key: ScenarioKey;
  company_name: string;
  industry: string;
  story: string;
  pack_version: string;
  status: "READY" | "UNAVAILABLE";
  role_in_review: string;
  terminology: Terminology;
}

export type TeamRole = "MEMBER" | "SHIFT_LEAD" | "TEAM_LEAD" | "MANAGER";
export type EmploymentStatus = "ONBOARDING" | "ACTIVE" | "NOTICE_PERIOD" | "EXITED";

/** Preview-only grant labels. Real grants are server-resolved permission_grants. */
export type PreviewGrant =
  | "onboarding.learn"
  | "onboarding.supervise"
  | "work.report"
  | "work.validate"
  | "delegation.confirm"
  | "handover.publish"
  | "handover.receive"
  | "knowledge.review"
  | "exitkt.subject"
  | "exitkt.successor"
  | "responsibility.confirm"
  /** Coordinator: author draft curricula, stage sources, map sections, publish (preview grant). */
  | "curriculum.manage"
  /** API: explicit, workspace-scoped curriculum:read grant (read-only Curricula screens). */
  | "curriculum.read";

export interface Persona {
  employee_id: string;
  first_name: string;
  last_name: string;
  role_name: string;
  team_name: string;
  team_role: TeamRole;
  employment_status: EmploymentStatus;
  scenario_note: string;
  grants: PreviewGrant[];
  /** API: shown on the demo page (up to four per pack); every persona stays switchable inside WorkWeave. */
  featured?: boolean;
  /** API: what a visitor can try with this persona (featured personas only; from the reviewed pack). */
  showcase?: PersonaShowcase;
}

export type ShowcaseModule = "ONBOARDING" | "COMPANION" | "HANDOVER" | "EXIT_KT" | "REVIEWS" | "CURRICULA";

export interface PersonaShowcase {
  label: string;
  headline: string;
  features: { module: ShowcaseModule; text: string }[];
}

export interface DemoSession {
  session_id: string;
  scenario: ScenarioCard;
  workspace_id: string;
  /** Pack version this visitor workspace is pinned to. */
  pack_version: string;
  persona: Persona;
  /** False until the visitor picks a persona on /demo/company/ (first entry). */
  persona_selected: boolean;
  expires_at: string;
  /** API mode: evaluator access (ADR-029). Absent in the preview. */
  access?: AccessInfo;
}

/** Evaluator access (ADR-029): the tier and until when. The code itself is never returned. */
export interface AccessInfo {
  tier: "PUBLIC" | "EVALUATOR";
  expires_at: string | null;
}

/** GET /demo-usage: the tier's daily caps and the open run's use of them (counts only). */
export interface DemoUsage {
  tier: "PUBLIC" | "EVALUATOR";
  resets_at: string;
  run_open: boolean;
  items: { kind: LimitKind; limit: number | null; used: number | null; shared_full: boolean }[];
  new_workspaces_per_day: number | null;
}

/** What this browser already holds for a company's demo run (ADR-024 resume / start fresh). */
export interface LocalDemoRun {
  key: ScenarioKey;
  scenario_id: string;
  workspace_id: string;
  pinned_pack_version: string;
  active_pack_version: string;
  persona_selected: boolean;
  persona?: Persona;
  is_active_session: boolean;
}

// ---------- Knowledge / sources ----------
export type ApprovalStatus = "DRAFT" | "PENDING_REVIEW" | "APPROVED" | "REJECTED";
export type TemporalStatus = "CURRENT" | "SUPERSEDED" | "ARCHIVED";

export interface DocumentVersion {
  document_version_id: string;
  document_id: string;
  document_code: string;
  title: string;
  version: string;
  approval_status: ApprovalStatus;
  temporal_status: TemporalStatus;
  approved_by?: string;
  effective_label: string;
  document_type: "SOP" | "PROCEDURE" | "GUIDE" | "CHECKLIST" | "REFERENCE" | "KT_ARTIFACT";
  index_status?: "PENDING" | "READY" | "FAILED" | "REVOKED";
}

export interface SourceExcerpt {
  source_id: string;
  document_version_id: string;
  heading_path: string[];
  text: string;
  evidence_type: EvidenceType;
  illustrative?: boolean;
}

export interface Citation {
  citation_id: string;
  label: string;
  excerpt: SourceExcerpt;
}

// ---------- Onboarding ----------
export type ProgressStatus = "NOT_STARTED" | "IN_PROGRESS" | "COMPLETED";
export type AssessmentOutcome = "CORRECT" | "PARTIAL" | "INCORRECT" | "UNASSESSABLE";

export interface Subtopic {
  subtopic_id: string;
  name: string;
  order_index: number;
  objective: string;
  status: ProgressStatus;
  /** API: no required objective (e.g. SOP reference aids); doesn't count toward completion. */
  optional?: boolean;
}

export interface Topic {
  topic_id: string;
  name: string;
  order_index: number;
  subtopics: Subtopic[];
}

export interface OnboardingOverview {
  learning_assignment_id: string;
  curriculum_name: string;
  curriculum_version: string;
  source_versions: DocumentVersion[];
  topics: Topic[];
  current_subtopic_id?: string;
  session_status: "NONE" | "ACTIVE" | "PAUSED" | "COMPLETED";
  saved_at?: string;
  /** API mode: the open learning session to resume, if any (GET /onboarding resume information). */
  learning_session_id?: string | null;
}

export type TutorMessageKind =
  | "OPENING"
  | "TEACHING"
  | "EXAMPLE"
  | "HINT"
  | "CHECK"
  | "FEEDBACK"
  | "COMPLETION"
  | "PAUSE"
  | "NOT_INTERPRETED"
  | "SYSTEM";

export interface TranscriptMessage {
  message_id: string;
  sender: "AI" | "EMPLOYEE" | "SYSTEM";
  input_kind?: "TEXT" | "VOICE_TRANSCRIPT";
  kind: TutorMessageKind;
  text: string;
  citations: Citation[];
  assessment?: { outcome: AssessmentOutcome; criteria_version: string; note: string };
  /** Preview fixture provenance shown to reviewers; API: TUTOR_ENGINE (validated reply) or BACKEND_RECORD (recorded progress). */
  provenance: "SCRIPTED_FIXTURE" | "EMPLOYEE_INPUT" | "PREVIEW_SYSTEM" | "TUTOR_ENGINE" | "BACKEND_RECORD";
  created_at: string;
}

export interface ScriptPrompt {
  prompt_id: string;
  label: string;
  /** Text inserted as the employee message when selected. */
  text: string;
}

export interface OnboardingSessionView {
  learning_session_id: string;
  revision: number;
  overview: OnboardingOverview;
  transcript: TranscriptMessage[];
  pending_check?: { question_id: string; objective_id: string; text: string } | null;
  awaiting_continue: boolean;
  script_prompts: ScriptPrompt[];
  status: "ACTIVE" | "PAUSED" | "COMPLETED";
  /** API mode: whether a tutor engine is connected. "unavailable" means no reply is generated. */
  tutor?: { status: "ok" | "unavailable"; message: string };
  /** API mode: public-demo daily caps for this run (absent in preview). */
  demo_limits?: DemoLimits;
}

export interface SupervisorProgressRow {
  employee_name: string;
  curriculum_name: string;
  curriculum_version: string;
  subtopics: { name: string; status: ProgressStatus }[];
}

// ---------- Work / Companion ----------
export type WorkItemType = "TASK" | "TICKET" | "INCIDENT" | "CHANGE" | "ACTIVITY" | "WORK_ORDER" | "OTHER";
export type WorkStatus = "ACTIVE" | "IN_PROGRESS" | "BLOCKED" | "COMPLETED" | "CANCELLED" | "CLOSED";
export type WorkEventType =
  | "STARTED"
  | "STATUS_CHANGED"
  | "INVESTIGATED"
  | "BLOCKED"
  | "UNBLOCKED"
  | "ESCALATED"
  | "COMMENTED"
  | "REPORTED_COMPLETE"
  | "COMPLETED"
  | "VALIDATED"
  | "REOPENED";

export interface WorkItem {
  work_item_id: string;
  external_id: string;
  work_item_type: WorkItemType;
  title: string;
  description: string;
  priority: "HIGH" | "MEDIUM" | "LOW";
  status: WorkStatus;
  due_label: string;
  assignee_id?: string;
  revision: number;
  historical?: boolean;
  /** API: the latest thing someone reported about it in the Companion. Never the ticket's status (ADR-033). */
  report?: ReportedState | null;
  /** API: how the current assignee got it (AUTOMATIC: by the competency rule, ADR-035). */
  assignment_source?: "MANUAL" | "AI_RECOMMENDED" | "HANDOVER" | "EXTERNAL_SYSTEM" | "AUTOMATIC" | null;
}

/** API: why a ticket went to its assignee (GET /work-items/{id}/assignment; the assignee or the shift lead only). */
export interface AssignmentExplanation {
  work_item_id: string;
  assigned: boolean;
  summary: string;
  assignee_id?: string;
  assignee_name?: string;
  source?: NonNullable<WorkItem["assignment_source"]>;
  rule?: string | null;
  assigned_by_name?: string | null;
  assigned_label?: string;
  requirements?: { name: string; required_level?: number | null; met: boolean; evidence?: string | null }[];
  availability?: string | null;
  /** Shift lead only: how the members on the shift compared. */
  compared?: { name: string; gaps: number; open_work: number; availability: string }[];
}

/** API: a member the shift lead may give the ticket to, with their fit for it. */
export interface AssignmentCandidate {
  employee_id: string;
  name: string;
  gaps: string[];
  open_work: number;
  availability: string;
}

/** ADR-033: a Companion report waits until the ticket system shows the same status. */
export type SyncStatus = "AWAITING_SOURCE" | "MATCHED" | "NEEDS_REVIEW" | "SUPERSEDED";
export type ReportedStatus = "IN_PROGRESS" | "BLOCKED" | "DONE";

export interface ReportedState {
  reported_status: ReportedStatus;
  sync_status: SyncStatus;
  employee_id: string;
  reported_label: string;
}

export interface TicketHistoryEntry {
  work_event_id: string;
  employee_id: string;
  event_type: WorkEventType;
  from_status?: WorkStatus | null;
  to_status?: WorkStatus | null;
  note: string;
  observed_label: string;
}

export interface TicketSystemItem extends WorkItem {
  /** The viewer is the ticket's assignee (or its last assignee, to reopen it). */
  can_update: boolean;
  history: TicketHistoryEntry[];
}

/** The company's ticket tool, simulated for the demo: the tickets' real status. */
export interface TicketSystemView {
  system_name: string;
  items: TicketSystemItem[];
}

export interface WorkEvent {
  work_event_id: string;
  work_item_id: string;
  employee_id: string;
  event_type: WorkEventType;
  description: string;
  evidence_type: EvidenceType;
  observed_label: string;
  validation?: "PENDING" | "VALIDATED" | "REJECTED";
  /** API: where the entry came from (a ticket-system change, a Companion report, or a seeded record). */
  source?: "TICKET_SYSTEM" | "COMPANION" | "RECORD";
  /** API: for Companion reports, whether the ticket system has caught up. */
  sync_status?: SyncStatus;
}

export type DerivedWorkState = "ON_TRACK" | "NEEDS_FOCUS" | "BLOCKED" | "NEEDS_SUPPORT" | "HIGH_WORKLOAD";

export interface WorkDashboard {
  active_count: number;
  blocked_count: number;
  overdue_count: number;
  work_state: DerivedWorkState;
  shift_label?: string;
  incoming_continuity?: string;
  priorities: string[];
  /** API: lead actions (assigning) belong to the lead of the shift in progress (changes with the clock). */
  can_delegate?: boolean;
  /** API: what the lists cover, the team (lead of the shift in progress) or only this person's tickets. */
  scope?: "TEAM" | "OWN";
  /** API, shift lead only: the team's open tickets nobody holds (ADR-035). */
  unassigned_count?: number;
  /** API: open items reported done in the Companion that the ticket system hasn't confirmed yet. */
  awaiting_sync_count?: number;
  needs_review_count?: number;
  /** API: the company's ticket tool, e.g. "Northstar Manufacturing ticket system". */
  system_name?: string;
  /** API: changes when the team's work changes; the page polls it to stay current. */
  changes_token?: string;
}

/** Allowlisted ui_action values (07-api-contracts §AI Work Companion). */
export const UI_ACTIONS = [
  "SHOW_BRIEFING",
  "SHOW_WORK_ITEMS",
  "SHOW_WORK_UPDATES",
  "SHOW_FOCUS_PLAN",
  "SHOW_GUIDANCE",
  "SHOW_DELEGATION_PROPOSAL",
  "NO_VIEW_CHANGE",
  "REQUEST_CLARIFICATION",
] as const;
export type UiActionType = (typeof UI_ACTIONS)[number];

export interface UiAction {
  type: UiActionType;
  filters?: { status?: WorkStatus[] };
  resource_refs?: string[];
}

export type CanvasView =
  | { view: "BRIEFING" }
  | { view: "WORK_ITEMS"; filters?: { status?: WorkStatus[] }; selected_id?: string }
  | { view: "WORK_UPDATES" }
  | { view: "FOCUS_PLAN" }
  | { view: "GUIDANCE"; guidance_id: string }
  | { view: "DELEGATION_PROPOSAL"; proposal_id: string };

export interface GuidanceProjection {
  guidance_id: string;
  question: string;
  answer: string;
  answer_status: "ANSWERED" | "INSUFFICIENT_EVIDENCE";
  citations: Citation[];
  unknowns: string[];
  related_work_item_id?: string;
}

export interface WorkMessage {
  message_id: string;
  sender: "AI" | "EMPLOYEE" | "SYSTEM";
  text: string;
  citations: Citation[];
  /** API: WORK_ENGINE is the AI engine's reply (ADR-034). */
  provenance: "SCRIPTED_FIXTURE" | "EMPLOYEE_INPUT" | "PREVIEW_SYSTEM" | "WORK_ENGINE" | "HANDOVER_ENGINE" | "KT_ENGINE" | "BACKEND_RECORD";
  /** Shift Handover copilot (docs/31): an edit the outgoing lead may apply; never applied by itself. */
  proposed_edit?: { section_id: string; content: string };
  /** Shift Handover copilot: a gap-check question or the incoming lead's brief. */
  kind?: "QUESTION" | "BRIEF";
  ui_action?: UiActionType;
  rejected_action?: string;
  /** API: a page the reply points to, e.g. the ticket on the ticket system page (the chat only opens it). */
  link?: { label: string; href: string };
  /** API: a setting the reply asks this browser to apply (read-aloud commands said in the chat). */
  client_action?: "READ_ALOUD_ON" | "READ_ALOUD_OFF" | "STOP_READING" | "SPEAK_SLOWER" | "SPEAK_FASTER" | "NORMAL_SPEED";
}

export interface WorkSessionView {
  work_session_id: string;
  revision: number;
  transcript: WorkMessage[];
  canvas: CanvasView;
  script_prompts: ScriptPrompt[];
  /** A report draft awaiting the employee's explicit review and submit (never auto-submitted). */
  pending_report?: { work_item_id: string; draft: string };
  /** API: whether the Companion's AI engine is connected ("unavailable": no replies yet). */
  assistant?: { status: "ok" | "unavailable"; message: string };
  /** API: the latest reply needs Google Calendar connected; the button opens connect_url, then retry_text is asked again. */
  calendar_connect?: { connect_url: string; retry_text: string };
}

export interface CalendarStatus {
  enabled: boolean;
  connected: boolean;
  reachable?: boolean;
}

export type ProposalStatus = "PROPOSED" | "EDITED" | "CONFIRMED" | "REJECTED";

export interface ProposalItem {
  proposal_item_id: string;
  work_item_id: string;
  recommended_employee_id: string;
  final_employee_id?: string;
  recommendation_reason: string;
  evidence: string[];
  uncertainty?: string;
}

export interface DelegationProposal {
  delegation_proposal_id: string;
  status: ProposalStatus;
  revision: number;
  origin: Origin;
  items: ProposalItem[];
  /** API: who may receive this proposal's work (a shift lead's hand-over: teammates on the same shift). */
  candidate_ids?: string[];
  /** API: every ticket in it already has someone (e.g. assigned automatically); it can't be confirmed. */
  overtaken?: boolean;
}

export interface MemoryDraft {
  draft_id: string;
  owner_employee_id: string;
  content: string;
  requested_audience: "PRIVATE" | "TEAM" | "ORGANIZATION";
  status: ApprovalStatus;
  evidence_type: EvidenceType;
  revision: number;
  review_comment?: string;
}

// ---------- Shift Handover ----------
export type HandoverStatus = "DRAFT" | "UNDER_REVIEW" | "PUBLISHED" | "ACKNOWLEDGED";
export type AckStatus = "NOT_REQUIRED" | "PENDING" | "ACKNOWLEDGED" | "DISPUTED";
export type SuggestionType = "MISSING_ITEM" | "STATUS_UPDATE" | "SCHEDULE_CHANGE" | "POSSIBLE_DUPLICATE" | "STALE_INFORMATION";

export interface ShiftOccurrence {
  shift_instance_id: string;
  name: string;
  window_label: string;
  lead_employee_id: string;
  member_ids: string[];
  status: "SCHEDULED" | "ACTIVE" | "COMPLETED";
}

export interface TemplateSection {
  section_id: string;
  name: string;
  order_index: number;
  is_required: boolean;
}

export interface HandoverItem {
  handover_item_id: string;
  display_id: string;
  work_item_id?: string;
  title: string;
  description: string;
  originating_shift_instance_id: string;
  work_status: WorkStatus;
  acknowledgement_status: AckStatus;
  completion_cycle_id?: string;
  section_id: string;
  evidence_type: EvidenceType;
  source_label: string;
}

export interface DraftSection {
  section_id: string;
  content: string;
  declaration?: "UNKNOWN_WITH_FOLLOW_UP" | "NOT_APPLICABLE";
  declaration_reason?: string;
}

export interface HandoverSuggestion {
  suggestion_id: string;
  suggestion_type: SuggestionType;
  handover_item_id?: string;
  title: string;
  reason: string;
  before?: string;
  proposed: string;
  source_label: string;
  evidence_type: EvidenceType;
  status: "PENDING" | "ACCEPTED" | "IGNORED";
  report_event_id?: string;
  /** API: proposed by the handover graph from the cited records. */
  origin?: "AI_ENGINE";
}

/** API (docs/31): proposed text for one template section; saved only if the lead saves it. */
export interface HandoverSectionDraft {
  section_id: string;
  section_name: string;
  content: string;
  unknowns: string[];
  citations: { source_type: string; source_id: string; label: string }[];
}

export interface PublicationEntry {
  handover_item_id: string;
  display_id: string;
  title: string;
  section_id: string;
  snapshot_work_status: WorkStatus;
  snapshot_acknowledgement_status: AckStatus;
  snapshot_description: string;
}

export interface HandoverPublication {
  publication_id: string;
  publication_number: number;
  source_shift_instance_id: string;
  target_shift_instance_id: string;
  template_version: string;
  sections: DraftSection[];
  entries: PublicationEntry[];
  published_by: string;
  published_label: string;
  receipts: { employee_id: string; received_label: string }[];
}

export interface CompletionCycle {
  completion_cycle_id: string;
  handover_item_id: string;
  completed_in_shift_instance_id: string;
  requested_from_shift_instance_id: string;
  status: AckStatus;
  comment?: string;
}

export interface HandoverItemEvent {
  event_id: string;
  handover_item_id: string;
  label: string;
  shift_name: string;
}

export interface HandoverWorkspace {
  handover_id: string;
  revision: number;
  status: HandoverStatus;
  template_name: string;
  template_version: string;
  sections: TemplateSection[];
  draft_sections: DraftSection[];
  source: ShiftOccurrence;
  target: ShiftOccurrence;
  occurrences: ShiftOccurrence[];
  items: HandoverItem[];
  suggestions: HandoverSuggestion[];
  publications: HandoverPublication[];
  cycles: CompletionCycle[];
  item_events: HandoverItemEvent[];
  /** Section touched by the latest unpublished change (highlighted after confirmation). */
  last_change_section_id?: string;
  /** The lead can create a new template version (POST /handover-templates/{id}/versions). */
  can_configure_template: boolean;
  script_prompts: ScriptPrompt[];
  copilot: WorkMessage[];
  /** API (docs/31): the handover graph is reachable; the gap check and drafts are for the outgoing lead. */
  copilot_available?: boolean;
  can_check?: boolean;
}

/** One section in a proposed template version. A missing section_id adds a new optional section. */
export interface TemplateSectionInput {
  section_id?: string;
  name: string;
  is_required: boolean;
}

// ---------- Exit KT ----------
export type CaseKind = "DEPARTURE" | "ROLE_TRANSITION";
export type DocumentationStatus = "DOCUMENTED" | "MISSING" | "OUTDATED" | "NEEDS_REVIEW";
export type KtStatus =
  | "NOT_STARTED"
  | "EXISTING_KNOWLEDGE"
  | "INTERVIEW_REQUIRED"
  | "INTERVIEW_IN_PROGRESS"
  | "DRAFT_CREATED"
  | "PENDING_REVIEW"
  | "COMPLETE";
export type FindingType =
  | "UNDOCUMENTED_KNOWLEDGE"
  | "OUTDATED_DOCUMENTATION"
  | "SOLE_KNOWLEDGE_HOLDER"
  | "MISSING_SUCCESSOR"
  | "PROCESS_DISCREPANCY";
export type FindingStatus = "OPEN" | "CONFIRMED" | "DISMISSED" | "RESOLVED";
export type ArtifactRevisionStatus = "DRAFT" | "PENDING_REVIEW" | "APPROVED" | "REJECTED" | "REVISION_REQUIRED";
export type TransferStatus = "DISCOVERED" | "PROPOSED" | "EDITED" | "CONFIRMED" | "TRANSFERRED";

export interface KtKnowledgeItem {
  kt_item_id: string;
  title: string;
  description: string;
  documentation_status: DocumentationStatus;
  kt_status: KtStatus;
  risk_level: "LOW" | "MEDIUM" | "HIGH";
  origin: Origin;
  linked_source?: string;
  artifact_id?: string;
  /** API (docs/32): the deterministic knowledge-at-risk score and the factors behind it. */
  risk_score?: number;
  risk_factors?: KtRiskFactor[];
}

export interface KtCitation {
  source_type: string;
  source_id: string;
  label: string;
}

export interface KtRiskFactor {
  factor: "SOLE_OWNER" | "MISSING_DOCUMENTATION" | "NO_SUCCESSOR" | "OPEN_WORK" | "RECENT_CHANGE" | "HIGH_CASE_FREQUENCY";
  weight: number;
  established: boolean;
  note: string;
  sources: KtCitation[];
}

export interface KtRisk {
  area_type: "RESPONSIBILITY" | "KNOWLEDGE_ITEM";
  area_id: string;
  title: string;
  score: number;
  level: "LOW" | "MEDIUM" | "HIGH";
  factors: KtRiskFactor[];
}

/** API (docs/32): the latest discovery, a proposal kept on the case until the next run. */
export interface KtDiscovery {
  overview: string;
  responsibilities: { responsibility_id?: string; title: string; ownership: "CONFIRMED" | "INFERRED"; note: string; citations: KtCitation[] }[];
  expertise: { text: string; evidence_type: EvidenceType; citations: KtCitation[] }[];
  changes: { text: string; evidence_type: EvidenceType; citations: KtCitation[] }[];
  documents: { document_version_id: string; label: string; temporal_status: string; effective: string | null }[];
  open_work: { work_item_id: string; label: string; status: string }[];
  risks: KtRisk[];
  risk_explanations: { text: string; citations: KtCitation[] }[];
  unknowns: string[];
  discovered_at: string;
}

export interface KtFinding {
  finding_id: string;
  kt_item_id?: string;
  finding_type: FindingType;
  description: string;
  evidence: string[];
  status: FindingStatus;
  origin: Origin;
  review_reason?: string;
}

export interface InterviewMessage {
  message_id: string;
  sender_type: "EMPLOYEE" | "AI" | "REVIEWER";
  content: string;
  provenance: "SCRIPTED_FIXTURE" | "EMPLOYEE_INPUT" | "PREVIEW_SYSTEM" | "KT_ENGINE";
}

export interface KtInterview {
  interview_id: string;
  kt_item_id: string;
  status: "NOT_STARTED" | "IN_PROGRESS" | "PAUSED" | "COMPLETED";
  consent_accepted: boolean;
  messages: InterviewMessage[];
  script_prompts: ScriptPrompt[];
}

export interface ArtifactRevision {
  artifact_revision_id: string;
  version: number;
  content: string;
  status: ArtifactRevisionStatus;
  audience: "PRIVATE" | "TEAM" | "ORGANIZATION";
  review_comment?: string;
  reviewed_by?: string;
}

export interface KtArtifact {
  artifact_id: string;
  kt_item_id: string;
  artifact_type:
    | "PROCEDURE"
    | "PROCESS"
    | "TROUBLESHOOTING_GUIDE"
    | "CONTACT_GUIDE"
    | "CHECKLIST"
    | "REFERENCE"
    | "SOP_UPDATE_PROPOSAL";
  title: string;
  revisions: ArtifactRevision[];
  current_revision_id: string;
  promotion?: { document_version_label: string; index_status: "PENDING" | "READY" | "FAILED" | "REVOKED" };
}

export interface Responsibility {
  responsibility_id: string;
  responsibility_type: "PROJECT" | "SYSTEM" | "PROCESS" | "RECURRING_TASK" | "VENDOR_RELATIONSHIP" | "WORK_ITEM" | "OTHER";
  title: string;
  owner_employee_id: string;
  ownership_revision: number;
}

export interface ResponsibilityTransfer {
  transfer_id: string;
  responsibility_id: string;
  current_owner_employee_id: string;
  recommended_owner_employee_id?: string;
  final_owner_employee_id?: string;
  recommendation_reason?: string;
  status: TransferStatus;
  effective_label: string;
  effective_reached: boolean;
  expected_owner_revision: number;
  origin: Origin;
}

export interface PackageVersion {
  package_version_id: string;
  content_revision: number;
  sections: { title: string; content: string; evidence_type?: EvidenceType }[];
  approved_by: string;
}

export interface SuccessorPackage {
  package_id: string;
  successor_employee_id: string;
  status: "DRAFT" | "SUBMITTED" | "APPROVED" | "REJECTED";
  draft_sections: { title: string; content: string; evidence_type?: EvidenceType }[];
  versions: PackageVersion[];
  current_approved_version_id?: string;
  receipts: { package_version_id: string; employee_id: string }[];
  revision: number;
  review_comment?: string;
}

export interface KtChecklistItem {
  checklist_item_id: string;
  label: string;
  required: boolean;
  status: "OPEN" | "IN_PROGRESS" | "RESOLVED";
  evidence_refs: string[];
  exception_reason?: string;
  /** API (docs/32): the knowledge-transfer plan lives on the checklist; the AI's items wait for the manager. */
  method?: "DOCUMENT_REVIEW" | "GUIDED_WALKTHROUGH" | "SHADOWING" | "PRACTICAL_DEMONSTRATION" | "HISTORICAL_CASE_REVIEW" | "SOP_VERIFICATION" | "QA_SESSION" | "OWNERSHIP_TRANSFER";
  priority?: number;
  completion_criteria?: string;
  origin?: "SCENARIO" | "MANUAL" | "AI_ENGINE";
  proposal_status?: "PROPOSED" | "ACCEPTED" | "DECLINED";
  evidence_sources?: KtCitation[];
}

export interface ExitKtCase {
  exit_kt_case_id: string;
  employee_id: string;
  case_kind: CaseKind;
  final_working_date?: string;
  status: "DISCOVERY" | "IN_PROGRESS" | "PENDING_REVIEW" | "COMPLETE";
  reviewer_employee_id: string;
  revision: number;
  knowledge_items: KtKnowledgeItem[];
  findings: KtFinding[];
  interviews: KtInterview[];
  artifacts: KtArtifact[];
  responsibilities: Responsibility[];
  transfers: ResponsibilityTransfer[];
  package: SuccessorPackage;
  checklist: KtChecklistItem[];
  open_work_note: string;
  successor_prompts: ScriptPrompt[];
  successor_qa: WorkMessage[];
  /** API (docs/32): this person's conversation with the knowledge-transfer assistant, and whether it's reachable. */
  copilot?: WorkMessage[];
  kt_available?: boolean;
  discovery?: KtDiscovery;
  can_manage?: boolean;
  can_review?: boolean;
}

// ---------- Reviews / inbox / memory ----------
export interface ReviewQueueItem {
  review_id: string;
  kind: "MEMORY_DRAFT" | "KT_ARTIFACT" | "KT_PACKAGE";
  title: string;
  submitted_by: string;
  revision_label: string;
  content: string;
  audience: string;
  resource_id: string;
  href: string;
}

/** Demo shift clock (ADR-042): the run's shift in progress and the next one. */
export interface ShiftClockShift {
  shift_instance_id: string;
  name: string;
  lead_name: string;
  window_label: string;
}
export interface ShiftClock {
  current: ShiftClockShift | null;
  next: ShiftClockShift | null;
  handover_unpublished: boolean;
  moved_hours?: number;
}

export interface InboxNotification {
  notification_id: string;
  type: string;
  minimal_message: string;
  resource_href: string;
  created_label: string;
  /** API: when it was delivered (ISO). */
  created_at?: string;
  read_at?: string;
}

export interface TimelineEntry {
  entry_id: string;
  label: string;
  detail: string;
  kind: "DOCUMENT_VERSION" | "WORK_HISTORY" | "MEMORY_RECORD" | "KT_PROMOTION";
  temporal: "CURRENT" | "HISTORICAL" | "PENDING";
  evidence_type: EvidenceType;
  document_version_id?: string;
}

export interface Capabilities {
  /** API: AVAILABLE once a tutor engine is connected. */
  conversation_engine: "UNAVAILABLE" | "AVAILABLE";
  /** API: AVAILABLE when the server has voice (Gemini transcription + speech) configured. */
  voice_adapter: "UNAVAILABLE" | "AVAILABLE";
  semantic_indexing: "UNAVAILABLE";
  kt_drafting: "UNAVAILABLE";
  recommendation: "UNAVAILABLE";
  inbox_delivery: "SIMULATED";
}

// ---------- Curricula & sources (coordinator) ----------
// Mirrors blueprint/04-data-model.md: curricula, curriculum_topics/subtopics, learning_objectives,
// curriculum_sources (exact document-version bridge), knowledge_sections (H2/H3) and
// curriculum_source_sections (section → subtopic). Preview IDs are browser-local, not database rows.

/** ARCHIVED exists in the database (curricula.status); the preview never produces it. */
export type CurriculumStatus = "DRAFT" | "PUBLISHED" | "ARCHIVED";

export interface CurriculumObjective {
  description: string;
  assessment_criteria: string;
}

export interface CurriculumSubtopicDef {
  subtopic_id: string;
  name: string;
  order_index: number;
  /** Human-reviewed objective and criteria; required before publication. */
  objective?: CurriculumObjective;
  /** API only: every stored learning_objectives row for this subtopic. */
  objectives?: CurriculumObjectiveRecord[];
  /** API, draft editor only (ADR-050): left out of the path; it keeps its objective. */
  left_out?: boolean;
}

/** A stored learning objective (API). assessment_criteria is the stored JSON, verbatim. */
export interface CurriculumObjectiveRecord {
  objective_id: string;
  description: string;
  assessment_criteria: string;
  criteria_version: string;
  required: boolean;
}

export interface CurriculumTopicDef {
  topic_id: string;
  name: string;
  order_index: number;
  subtopics: CurriculumSubtopicDef[];
  /** API only: set for document-bound topics (order is local to that document version); null for learner-path topics. */
  document_version_id?: string | null;
}

/**
 * Processing stage of one exact document version linked to this curriculum.
 * STAGED: metadata recorded; PARSED: H2/H3 outline available; MAPPED: coordinator confirmed
 * mappings; PENDING_REVIEW: submitted; APPROVED: exact version approved (not curriculum publication).
 * Rejected sources are removed; only a non-content receipt remains.
 */
export type SourceStage = "STAGED" | "PARSED" | "MAPPED" | "PENDING_REVIEW" | "APPROVED";

/** SYNTHETIC_FIXTURE has a recorded parse outline; FILENAME_ONLY means a local filename was selected and nothing was read. */
export type SourceOrigin = "SYNTHETIC_FIXTURE" | "FILENAME_ONLY" | "SEEDED_APPROVED";

/** Section mapping value: a subtopic ID, explicitly reference-only, or unresolved. */
export type SectionMapping = { kind: "SUBTOPIC"; subtopic_id: string } | { kind: "REFERENCE_ONLY" } | { kind: "UNRESOLVED" };

export interface ParsedSourceSection {
  section_id: string;
  /** Stable key within the exact document version, e.g. "h2:1/h3:2". */
  section_key: string;
  topic_heading: string;
  topic_order_index: number;
  subtopic_heading: string;
  subtopic_order_index: number;
  /** Fixture classification shown for review; not an AI judgement. */
  kind: "INSTRUCTION" | "REFERENCE";
  excerpt: string;
  /** H4+ headings kept inside this section's content (not curriculum hierarchy). */
  nested_headings: string[];
  /** Name-match suggestion from the fixture; never applied without confirmation. */
  suggested_subtopic_id?: string;
  mapping: SectionMapping;
}

export interface CurriculumSource {
  curriculum_source_id: string;
  document_id: string;
  document_version_id: string;
  document_code: string;
  title: string;
  version: string;
  /** What the coordinator selected. For FILENAME_ONLY, bytes were never read or uploaded. */
  file_label: string;
  origin: SourceOrigin;
  stage: SourceStage;
  sections: ParsedSourceSection[];
  mappings_confirmed: boolean;
  submitted_by?: string;
  approved_by?: string;
  revision: number;
}

export interface SourceReviewReceipt {
  receipt_id: string;
  curriculum_id: string;
  document_code: string;
  version: string;
  decision: "APPROVED" | "REJECTED";
  reason?: string;
  reviewer: string;
  label: string;
}

/** API: one stored parsed H2/H3 section (headings only) and its recorded subtopic links. */
export interface LinkedSourceSection {
  section_id: string;
  section_key: string;
  topic_heading: string;
  subtopic_heading: string;
  topic_order_index: number;
  subtopic_order_index: number;
  /** curriculum_source_sections rows. Empty means no link is recorded (reference-only vs unresolved isn't stored). */
  links: { topic_id: string; subtopic_id: string; relationship_type: "TEACHES" | "SUPPORTS" }[];
}

/** API: a curriculum_sources row with its exact document version, as stored. */
export interface LinkedSourceVersion {
  curriculum_source_id: string;
  document_id: string;
  document_version_id: string;
  document_code: string;
  title: string;
  version: string;
  relationship_type: "TEACHES" | "SUPPORTS";
  approval_status: "DRAFT" | "PENDING_REVIEW" | "APPROVED" | "REJECTED";
  temporal_status: "CURRENT" | "SUPERSEDED" | "ARCHIVED";
  is_current_version: boolean;
  approved_by: string | null;
  approved_at: string | null;
  source_revoked: boolean;
  revision: number;
  /** null when the source is revoked: its headings are withheld. */
  sections: LinkedSourceSection[] | null;
  /** API (ADR-040): the tracked ingestion job of this version, once it was approved. */
  ingestion?: IngestionJob | null;
}

export interface IngestionJob {
  job_id: string;
  status: "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED";
  attempts: number;
  error_summary: string | null;
}

export interface Curriculum {
  curriculum_id: string;
  name: string;
  version: string;
  status: CurriculumStatus;
  description?: string;
  revision: number;
  topics: CurriculumTopicDef[];
  sources: CurriculumSource[];
  derived_from_curriculum_id?: string;
  published_label?: string;
  /** True for the pack's seeded curriculum; false for IDs generated in this browser tab. */
  seeded: boolean;
  /** API only: when the curriculum was published. */
  published_at?: string | null;
  /** API only: stored source links. The API leaves `sources` (preview authoring state) empty. */
  linked_sources?: LinkedSourceVersion[];
  /** API (ADR-040): this persona holds curriculum:manage (create, upload, approve, publish). */
  can_manage?: boolean;
  /** API: whether the server can run the AI engineer's ingestion. */
  ingestion_available?: boolean;
  /** API: publication checks, for managers on a draft. */
  readiness?: ReadinessCheck[];
  /** API (ADR-050): this curriculum's other versions (same name). */
  other_versions?: { curriculum_id: string; version: string; status: CurriculumStatus }[];
  /** API (ADR-050), managers on a published version: the open draft revision to continue. */
  draft_revision?: { curriculum_id: string; version: string };
}

export interface CurriculumSummary {
  curriculum_id: string;
  name: string;
  version: string;
  status: CurriculumStatus;
  topic_count: number;
  subtopic_count: number;
  source_count: number;
  pending_review_count: number;
}

export interface CurriculaCatalog {
  curricula: CurriculumSummary[];
  receipts: SourceReviewReceipt[];
  /** Whether this pack offers the synthetic sample source with a recorded parse outline. */
  sample_available: boolean;
}

export interface StageSourceInput {
  document_code: string;
  title: string;
  version: string;
  /** Selected local file metadata only; contents are never read (preview). */
  file?: { name: string; size: number };
  use_sample: boolean;
  /** API (ADR-040): the uploaded Markdown text, read in the browser, and the document's type. */
  content?: string;
  document_type?: "SOP" | "PROCEDURE" | "GUIDE" | "CHECKLIST" | "REFERENCE";
}

export interface ReadinessCheck {
  key: "PATH" | "SOURCE_APPROVED" | "SOURCES_SETTLED" | "OBJECTIVES" | "COVERAGE";
  label: string;
  passed: boolean;
  detail: string;
}
