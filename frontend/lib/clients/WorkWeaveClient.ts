/**
 * WorkWeaveClient — the only data boundary screens may use (blueprint/02-frontend.md).
 *
 * Each method names the canonical route it will call once an HTTP adapter exists
 * (blueprint/07-api-contracts.md). In this phase the only implementation is the labelled
 * PreviewClient (fixture playback + in-memory state). No HTTP adapter is wired yet; adding
 * one is backend-phase work after screen/flow approval.
 *
 * Commands take an idempotency key and, where the contract requires, an expected revision.
 * Failures throw WorkWeaveError with the canonical {code, message, retryable} shape.
 */
import type { PcmStream } from "@/lib/voice/stream-player";
import type { ListenMode, VoiceGrant } from "@/lib/voice/live-listener";
import type {
  Capabilities,
  DelegationProposal,
  TicketSystemItem,
  TicketSystemView,
  DemoSession,
  LocalDemoRun,
  ExitKtCase,
  AssignmentCandidate,
  AssignmentExplanation,
  CalendarStatus,
  GuidanceProjection,
  HandoverSectionDraft,
  HandoverWorkspace,
  InboxNotification,
  MemoryDraft,
  OnboardingOverview,
  OnboardingSessionView,
  Persona,
  ReviewQueueItem,
  ShiftClock,
  ScenarioCard,
  ScenarioKey,
  SourceExcerpt,
  DocumentVersion,
  SupervisorProgressRow,
  TimelineEntry,
  WorkDashboard,
  WorkEvent,
  WorkItem,
  WorkSessionView,
  CaseKind,
  TemplateSectionInput,
  CurriculaCatalog,
  Curriculum,
  CurriculumObjective,
  CurriculumTopicDef,
  SectionMapping,
  StageSourceInput,
  AccessInfo,
  DemoUsage,
} from "@/types/contracts";

export interface Command {
  idempotency_key: string;
  expected_revision?: number;
}

export interface TurnInput extends Command {
  client_turn_id: string;
  /** API: the learner cut off the previous reply while it was being read aloud. */
  interrupted_previous_reply?: boolean;
  text: string;
  input_kind: "TEXT" | "VOICE_TRANSCRIPT";
  /** Preview only: which recorded script step the reviewer selected. Never inferred from text. */
  preview_prompt_id?: string;
  /** API: plain-language step labels while the tutor works ("Writing a reply…"). Not part of the request. */
  onProgress?: (label: string) => void;
}

export interface WorkWeaveClient {
  // Platform — GET /scenarios, POST /demo-sessions, GET /personas, POST /demo-sessions/current/persona, GET /ready
  listScenarios(): Promise<ScenarioCard[]>;
  /**
   * POST /demo-sessions with explicit intent: resume this visitor's run for the company, or
   * create a fresh isolated run. A fresh run replaces only this visitor's run for this company,
   * and only after it is ready; a failure leaves the existing run usable.
   */
  startDemoSession(key: ScenarioKey, fresh: boolean): Promise<DemoSession>;
  /**
   * Local lookup of a run this browser already holds for the company (no new authority).
   * The HTTP adapter will check its stored scoped session for that company.
   */
  getLocalDemoRun(key: ScenarioKey): Promise<LocalDemoRun | null>;
  getSession(): Promise<DemoSession | null>;
  endSession(): Promise<void>;
  listPersonas(): Promise<Persona[]>;
  switchPersona(employee_id: string): Promise<DemoSession>;
  getCapabilities(): Promise<Capabilities>;
  /** API: evaluator access (ADR-029) — GET/POST/DELETE /demo-access. The preview has no limits. */
  getAccess(): Promise<AccessInfo>;
  redeemAccessCode(code: string): Promise<AccessInfo>;
  leaveAccess(): Promise<AccessInfo>;
  /** API: the tier's daily caps and this run's use (GET /demo-usage). The preview has none (null). */
  getDemoUsage(): Promise<DemoUsage | null>;

  // Onboarding — GET /onboarding, POST /onboarding/sessions, GET /onboarding/sessions/{id},
  // POST .../turns, POST .../pause, GET /onboarding/progress
  getOnboarding(): Promise<OnboardingOverview | null>;
  startOnboardingSession(): Promise<OnboardingSessionView>;
  getOnboardingSession(): Promise<OnboardingSessionView | null>;
  sendOnboardingTurn(input: TurnInput): Promise<OnboardingSessionView>;
  continueOnboarding(cmd: Command): Promise<OnboardingSessionView>;
  pauseOnboarding(cmd: Command): Promise<OnboardingSessionView>;
  /** API: single-use grant to stream the mic to Gemini transcription (POST /onboarding/sessions/{id}/voice/listen). */
  getVoiceListenGrant(mode: ListenMode): Promise<VoiceGrant>;
  /** API: WAV of a committed tutor reply in the open session (GET .../voice/speech/{message_id}). */
  getReplySpeech(message_id: string): Promise<Blob>;
  /** API: the same reply as raw PCM streamed while it is generated (GET …/voice/speech/{id}/stream). */
  streamReplySpeech(message_id: string): Promise<PcmStream>;
  getSupervisorProgress(): Promise<SupervisorProgressRow[]>;

  // Companion — POST /work-sessions, POST /work-sessions/{id}/messages, GET /work-state,
  // GET /assignments, GET /work-events, POST /work-items/{id}/reports (ADR-033: no validation)
  startWorkSession(): Promise<WorkSessionView>;
  sendWorkMessage(input: TurnInput): Promise<WorkSessionView>;
  getWorkDashboard(): Promise<WorkDashboard>;
  /** API: single-use voice grant for the open work session (POST /work-sessions/{id}/voice/listen). */
  getWorkVoiceListenGrant(mode: ListenMode): Promise<VoiceGrant>;
  /** API: a companion reply read aloud, raw PCM streamed (GET /work-sessions/{id}/voice/speech/{message_id}/stream). */
  streamWorkReplySpeech(message_id: string): Promise<PcmStream>;
  /** API (ADR-045): voice for the lead's handover copilot (POST /handover/voice/listen; GET /handover/voice/speech/{id}/stream). */
  getHandoverVoiceListenGrant(mode: ListenMode): Promise<VoiceGrant>;
  streamHandoverReplySpeech(message_id: string): Promise<PcmStream>;
  /** API (ADR-045): voice for the Exit KT copilot and the employee's interview (POST /exit-kt/voice/listen; GET /exit-kt/voice/speech/{id}/stream). */
  getKtVoiceListenGrant(mode: ListenMode): Promise<VoiceGrant>;
  streamKtReplySpeech(message_id: string): Promise<PcmStream>;
  /** API: re-read the screens when someone else changes the team's work (polls GET /work-state). Returns a stop function. */
  watchWork(everyMs?: number): () => void;
  /** API: why the ticket went to its assignee (ADR-035). */
  getAssignmentExplanation(work_item_id: string): Promise<AssignmentExplanation>;
  /** API: members on the lead's shift who may take the ticket, with their fit. */
  getAssignmentCandidates(work_item_id: string): Promise<AssignmentCandidate[]>;
  /** API: the shift lead assigns the ticket, or overrides who has it (POST /work-items/{id}/assignee). */
  reassignWorkItem(work_item_id: string, employee_id: string, cmd: Command): Promise<AssignmentExplanation>;
  /** API: whether the calendar service is signed in to Google (GET /calendar/status). */
  getCalendarStatus(): Promise<CalendarStatus>;
  listWorkItems(): Promise<WorkItem[]>;
  listWorkEvents(): Promise<WorkEvent[]>;
  getGuidance(guidance_id: string): Promise<GuidanceProjection>;
  reportWorkEvent(work_item_id: string, event_type: "COMMENTED" | "REPORTED_COMPLETE" | "BLOCKED", description: string, cmd: Command): Promise<WorkEvent>;
  /** API: the (simulated) ticket system, GET /ticket-system. */
  getTicketSystem(): Promise<TicketSystemView>;
  /** API: a status change made in the ticket system by the ticket's assignee (the real status). */
  updateTicketStatus(work_item_id: string, status: "IN_PROGRESS" | "BLOCKED" | "COMPLETED" | "CANCELLED", note: string, cmd: Command): Promise<TicketSystemItem>;
  dismissPendingReport(): Promise<WorkSessionView>;

  // Delegation — GET/PATCH /delegation-proposals/{id}, POST .../confirm, POST .../reject
  /** The lead's delegation proposals, open ones first (GET /delegation-proposals). */
  listProposals(): Promise<DelegationProposal[]>;
  getProposal(id: string): Promise<DelegationProposal>;
  editProposalItem(id: string, work_item_id: string, final_employee_id: string, cmd: Command): Promise<DelegationProposal>;
  confirmProposal(id: string, cmd: Command): Promise<DelegationProposal>;
  rejectProposal(id: string, reason: string, cmd: Command): Promise<DelegationProposal>;

  // Capture — POST /sessions (consent), POST /memory-drafts, PATCH/DELETE /memory-drafts/{id}, POST .../review
  createMemoryDraft(content: string, audience: MemoryDraft["requested_audience"], cmd: Command): Promise<MemoryDraft>;
  listMyMemoryDrafts(): Promise<MemoryDraft[]>;
  submitMemoryDraft(draft_id: string, cmd: Command): Promise<MemoryDraft>;
  deleteMemoryDraft(draft_id: string, cmd: Command): Promise<void>;

  // Shift Handover — GET /handovers/active, PATCH /handovers/{id}, suggestions accept/ignore,
  // POST /handovers/{id}/publish, POST /handovers/{id}/receipt, POST /handover-items/{id}/confirm-completion,
  // POST /handover-acknowledgements/{id}/acknowledge|dispute
  getHandoverWorkspace(): Promise<HandoverWorkspace>;
  editDraftSection(section_id: string, content: string, declaration: { kind?: "UNKNOWN_WITH_FOLLOW_UP" | "NOT_APPLICABLE"; reason?: string }, cmd: Command): Promise<HandoverWorkspace>;
  /** POST /handover-suggestions/{id}/accept. `note` is the lead's edited activity note (screens/smart-handover: change preview). */
  acceptSuggestion(suggestion_id: string, mode: "APPLY" | "REPORT_ONLY" | "VALIDATE_COMPLETION", cmd: Command, note?: string): Promise<HandoverWorkspace>;
  /** POST /handover-templates/{id}/versions: versioned sections/requirements; existing publications keep their version. */
  createTemplateVersion(sections: TemplateSectionInput[], cmd: Command): Promise<HandoverWorkspace>;
  ignoreSuggestion(suggestion_id: string, cmd: Command): Promise<HandoverWorkspace>;
  publishHandover(cmd: Command): Promise<HandoverWorkspace>;
  confirmHandoverReceipt(publication_id: string, cmd: Command): Promise<HandoverWorkspace>;
  acknowledgeCompletion(cycle_id: string, decision: "ACKNOWLEDGE" | "DISPUTE", comment: string, cmd: Command): Promise<HandoverWorkspace>;
  confirmItemCompletion(handover_item_id: string, cmd: Command): Promise<HandoverWorkspace>;
  askHandoverCopilot(input: TurnInput): Promise<HandoverWorkspace>;
  /** POST /handovers/{id}/gap-check (docs/31): outgoing lead; suggestions and questions from the records. */
  runHandoverGapCheck(cmd: Command): Promise<HandoverWorkspace>;
  /** POST /handovers/{id}/section-drafts: proposed text for the editor, never stored. */
  draftHandoverSections(section_ids: string[]): Promise<HandoverSectionDraft[]>;

  // Exit KT — /exit-kt, findings review, interviews/messages, kt-artifacts edit/submit/decide/promote,
  // packages assemble/submit/approve/receipt, responsibility-transfers edit/confirm, checklist resolve, complete
  getExitKtCase(): Promise<ExitKtCase | null>;
  createExitKtCase(input: { employee_id: string; case_kind: CaseKind; final_working_date?: string; reviewer_employee_id: string }, cmd: Command): Promise<ExitKtCase>;
  addKnowledgeItem(title: string, description: string, cmd: Command): Promise<ExitKtCase>;
  linkExistingKnowledge(kt_item_id: string, cmd: Command): Promise<ExitKtCase>;
  reviewFinding(finding_id: string, decision: "CONFIRM" | "DISMISS" | "RESOLVE", reason: string, cmd: Command): Promise<ExitKtCase>;
  runDiscovery(): Promise<ExitKtCase>;
  startInterview(kt_item_id: string, consent: boolean, cmd: Command): Promise<ExitKtCase>;
  sendInterviewMessage(interview_id: string, input: TurnInput): Promise<ExitKtCase>;
  draftArtifactFromInterview(interview_id: string): Promise<ExitKtCase>;
  createManualArtifact(kt_item_id: string, title: string, content: string, cmd: Command): Promise<ExitKtCase>;
  editArtifact(artifact_id: string, content: string, cmd: Command): Promise<ExitKtCase>;
  submitArtifact(artifact_id: string, artifact_revision_id: string, audience: "TEAM" | "ORGANIZATION", cmd: Command): Promise<ExitKtCase>;
  decideArtifact(artifact_id: string, artifact_revision_id: string, decision: "APPROVE" | "REQUEST_REVISION" | "REJECT", comment: string, cmd: Command): Promise<ExitKtCase>;
  promoteArtifact(artifact_id: string, artifact_revision_id: string, cmd: Command): Promise<ExitKtCase>;
  /** A FAILED search index of promoted knowledge is tried again (ADR-053); never re-approves or re-promotes. */
  retryKtIndexing(artifact_id: string, artifact_revision_id: string, cmd: Command): Promise<ExitKtCase>;
  editTransfer(transfer_id: string, final_owner_employee_id: string, cmd: Command): Promise<ExitKtCase>;
  reviewEffectiveTime(transfer_id: string, cmd: Command): Promise<ExitKtCase>;
  assemblePackage(cmd: Command): Promise<ExitKtCase>;
  submitPackage(cmd: Command): Promise<ExitKtCase>;
  decidePackage(decision: "APPROVE" | "REJECT", comment: string, cmd: Command): Promise<ExitKtCase>;
  receivePackage(package_version_id: string, cmd: Command): Promise<ExitKtCase>;
  askPackage(input: TurnInput): Promise<ExitKtCase>;
  confirmTransfer(transfer_id: string, cmd: Command): Promise<ExitKtCase>;
  resolveChecklistItem(item_id: string, evidence_ref: string, cmd: Command): Promise<ExitKtCase>;
  recordChecklistException(item_id: string, reason: string, cmd: Command): Promise<ExitKtCase>;
  completeExitKtCase(cmd: Command): Promise<ExitKtCase>;
  /** API (docs/32): successor recommendations (the manager confirms each transfer separately). */
  recommendSuccessors(cmd: Command): Promise<ExitKtCase>;
  /** API: the manager accepts (optionally as required) or declines an AI-proposed plan item. */
  decidePlanItem(item_id: string, decision: "ACCEPT" | "DECLINE", required: boolean, cmd: Command): Promise<ExitKtCase>;
  /** API: the employee's or manager's conversation with the knowledge-transfer assistant. */
  askKtCopilot(input: TurnInput): Promise<ExitKtCase>;
  /** API: the manager names the package's successor; it never transfers ownership. */
  assignSuccessor(successor_employee_id: string, cmd: Command): Promise<ExitKtCase>;

  // Reviewer workspace — GET /reviews (+ decisions via the resource routes above / memory-drafts approve|reject)
  /** Demo shift clock (ADR-042), visitor runs only: GET /demo-sessions/current/shift-clock */
  getShiftClock(): Promise<ShiftClock>;
  /** POST /demo-sessions/current/shift-clock/advance: the run moves to the middle of the next shift. */
  advanceShiftClock(confirm_unpublished: boolean, cmd: Command): Promise<ShiftClock>;
  listReviews(): Promise<ReviewQueueItem[]>;
  decideMemoryDraft(draft_id: string, decision: "APPROVE" | "REJECT", comment: string, cmd: Command): Promise<void>;

  // Inbox — GET /notifications, PATCH /notifications/{id}/read
  listNotifications(): Promise<InboxNotification[]>;
  markNotificationRead(notification_id: string): Promise<void>;

  // Knowledge — GET /timeline, GET /sources/{id}/content
  getTimeline(): Promise<TimelineEntry[]>;
  listDocumentVersions(): Promise<DocumentVersion[]>;
  getSourceContent(document_version_id: string): Promise<{ version: DocumentVersion; text: string }>;
  getExcerpt(source_id: string): Promise<SourceExcerpt>;

  // ---------------------------------------------------------------- curricula & sources (coordinator)
  // PROPOSED endpoints: blueprint/07-api-contracts.md defines POST /ingest and
  // POST /documents/{id}/versions/{version_id}/approve but no curriculum-authoring routes yet.
  // These signatures are UI-first proposals backed by the data model (blueprint/04) and need
  // contract approval before backend wiring. Parsing is an external capability (build_spec §Knowledge).
  /** PROPOSED GET /curricula */
  listCurricula(): Promise<CurriculaCatalog>;
  /** PROPOSED GET /curricula/{id} */
  getCurriculum(curriculum_id: string): Promise<Curriculum>;
  /** PROPOSED POST /curricula → new DRAFT curriculum with a new ID */
  createCurriculum(input: { name: string; version: string; description?: string }, cmd: Command): Promise<Curriculum>;
  /** POST /curricula/{id}/revisions → DRAFT copy of a published curriculum (or the open one), ADR-050 */
  createCurriculumRevision(curriculum_id: string, cmd: Command): Promise<Curriculum>;
  /** API (ADR-050), drafts: DELETE /curricula/{id}/sources/{source}, leave a subtopic out or back in, move a topic. */
  removeCurriculumSource(curriculum_id: string, curriculum_source_id: string, cmd: Command): Promise<Curriculum>;
  setSubtopicIncluded(curriculum_id: string, subtopic_id: string, included: boolean, cmd: Command): Promise<Curriculum>;
  moveCurriculumTopic(curriculum_id: string, topic_id: string, direction: "UP" | "DOWN", cmd: Command): Promise<Curriculum>;
  /** POST /ingest with the curriculum ID supplied by the page (curriculum binding is PROPOSED). */
  stageCurriculumSource(curriculum_id: string, input: StageSourceInput, cmd: Command): Promise<Curriculum>;
  /** External parsing capability; the preview replays a recorded outline for the synthetic sample only. */
  parseCurriculumSource(curriculum_id: string, source_id: string, cmd: Command): Promise<Curriculum>;
  /** PROPOSED PUT /curricula/{id}/topics: reviewed learning path (e.g. accepted from a parsed outline). */
  saveLearningPath(curriculum_id: string, topics: CurriculumTopicDef[], cmd: Command): Promise<Curriculum>;
  /** PROPOSED PUT /curricula/{id}/sources/{source_id}/mappings (confirm = coordinator confirmation). */
  saveSourceMappings(curriculum_id: string, source_id: string, mappings: Record<string, SectionMapping>, confirm: boolean, cmd: Command): Promise<Curriculum>;
  /** PROPOSED PUT /curricula/{id}/subtopics/{subtopic_id}/objective */
  saveObjective(curriculum_id: string, subtopic_id: string, objective: CurriculumObjective, cmd: Command): Promise<Curriculum>;
  /** PROPOSED POST /curricula/{id}/sources/{source_id}/submit: exact version to review */
  submitSourceForReview(curriculum_id: string, source_id: string, cmd: Command): Promise<Curriculum>;
  /** APPROVE maps to POST /documents/{id}/versions/{version_id}/approve; REJECT is PROPOSED. */
  reviewSourceVersion(curriculum_id: string, source_id: string, decision: "APPROVED" | "REJECTED", reason: string, cmd: Command, reviewedExactVersion?: boolean): Promise<Curriculum>;
  /** POST /curricula/{id}/ingestion-jobs/{job_id}/retry (ADR-040): re-run a failed ingestion. */
  retryIngestion(curriculum_id: string, job_id: string, cmd: Command): Promise<Curriculum>;
  /** PROPOSED POST /curricula/{id}/publish (separate from source approval and from assignment) */
  publishCurriculum(curriculum_id: string, cmd: Command): Promise<Curriculum>;
}
