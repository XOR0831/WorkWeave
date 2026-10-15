/**
 * PreviewClient — labelled UI-preview implementation of WorkWeaveClient.
 *
 * - Conversation responses are recorded fixture playback selected by an explicit
 *   `preview_prompt_id`. Free text is never inspected; it receives a "not interpreted" reply.
 * - Guards mirror documented contract rules (12-implementation-contracts, 07-api-contracts) so
 *   reviewers can see blocked/denied/stale states. They are NOT backend authorization.
 * - State lives in memory and sessionStorage for this browser tab only.
 */
import { PACKS, PACK_ORDER } from "@/fixtures";
import type { PackFixture, CompanionScript } from "@/fixtures/types";
import {
  type AccessInfo,
  UI_ACTIONS,
  WorkWeaveError,
  type ApiError,
  type Capabilities,
  type CanvasView,
  type CaseKind,
  type Citation,
  type DelegationProposal,
  type DemoSession,
  type LocalDemoRun,
  type DocumentVersion,
  type ErrorCode,
  type ExitKtCase,
  type GuidanceProjection,
  type HandoverItem,
  type HandoverWorkspace,
  type InboxNotification,
  type MemoryDraft,
  type OnboardingOverview,
  type OnboardingSessionView,
  type Persona,
  type PreviewGrant,
  type ReviewQueueItem,
  type ShiftClock,
  type HandoverSectionDraft,
  type ScenarioCard,
  type ScenarioKey,
  type ScriptPrompt,
  type SourceExcerpt,
  type SupervisorProgressRow,
  type TimelineEntry,
  type TranscriptMessage,
  type UiAction,
  type WorkDashboard,
  type WorkEvent,
  type WorkItem,
  type WorkSessionView,
  type TemplateSection,
  type TemplateSectionInput,
  type CurriculaCatalog,
  type Curriculum,
  type CurriculumObjective,
  type CurriculumTopicDef,
  type SectionMapping,
  type StageSourceInput,
} from "@/types/contracts";
import { SAMPLE_SOURCES, headingKey, seedCurricula } from "@/fixtures/curricula";
import type { Command, TurnInput, WorkWeaveClient } from "../WorkWeaveClient";
import { checklistEvidence, curriculumReadiness, missingRequiredSections, transferBlockers } from "@/lib/domain/rules";
import { createWorkspace, type LearnerSession, type LearnerState, type WorkspaceState, type HandoverState } from "./state";

export type FailureMode = "none" | "fail_next" | "stale_next" | "deny_next" | "expire" | "slow";

export interface PreviewControls {
  getFailureMode(): FailureMode;
  setFailureMode(mode: FailureMode): void;
  advanceShift(): void;
  toggleRevokedSource(document_version_id: string): void;
  isRevoked(document_version_id: string): boolean;
  subscribe(fn: () => void): () => void;
}

const STORAGE_KEY = "workweave-ui-preview-v2";
const BASE_LATENCY = 220;
const SLOW_LATENCY = 2600;

interface Persisted {
  session_key?: ScenarioKey;
  expires_at?: string;
  workspaces: Partial<Record<ScenarioKey, WorkspaceState>>;
}

const NOT_INTERPRETED =
  "Not interpreted. The conversation engine isn't connected in this preview, so free text isn't analyzed and nothing has changed. Choose a preview script prompt to continue the walkthrough.";

export class PreviewClient implements WorkWeaveClient, PreviewControls {
  private data: Persisted = { workspaces: {} };
  private failure: FailureMode = "none";
  private listeners = new Set<() => void>();
  private requestSeq = 0;

  constructor(
    private readonly storage: Storage | null = typeof window !== "undefined" ? safeSession() : null,
    private readonly latency = BASE_LATENCY,
  ) {
    this.load();
    // Like an HTTP adapter, hand out serialized copies so UI state never aliases store state.
    for (const name of CLIENT_METHODS) {
      const original = (this[name] as (...a: unknown[]) => Promise<unknown>).bind(this);
      (this as unknown as Record<string, unknown>)[name] = async (...args: unknown[]) => {
        const result = await original(...args);
        return result === undefined ? result : structuredClone(result);
      };
    }
  }

  // ---------------------------------------------------------------- infra
  private load() {
    try {
      const raw = this.storage?.getItem(STORAGE_KEY);
      if (raw) this.data = JSON.parse(raw) as Persisted;
    } catch {
      this.data = { workspaces: {} };
    }
  }
  private save() {
    try {
      this.storage?.setItem(STORAGE_KEY, JSON.stringify(this.data));
    } catch {
      /* storage unavailable: preview continues in memory */
    }
  }
  private version = 0;
  private lastEmit = 0;
  private emit() {
    this.save();
    this.version += 1;
    this.lastEmit = Date.now();
    this.listeners.forEach((fn) => fn());
  }
  /** Monotonic state version for useSyncExternalStore. */
  readonly mode = "preview" as const;
  getVersion() {
    return this.version;
  }
  /** Preview state is synchronous (sessionStorage), so it's always loaded. */
  isLoaded() {
    return true;
  }
  loadError() {
    return null;
  }
  subscribe = (fn: () => void) => {
    this.listeners.add(fn);
    return () => {
      this.listeners.delete(fn);
    };
  };
  getFailureMode() {
    return this.failure;
  }
  setFailureMode(mode: FailureMode) {
    this.failure = mode;
    this.version += 1;
    this.listeners.forEach((fn) => fn());
  }

  private rid() {
    this.requestSeq += 1;
    return `preview-req-${this.requestSeq}`;
  }
  private fail(code: ErrorCode, message: string, retryable = false): never {
    const error: ApiError = { code, message, retryable };
    throw new WorkWeaveError(error, this.rid());
  }

  /** Simulated latency and reviewer-selected failure injection. */
  private async gate(kind: "read" | "command") {
    // Refresh reads right after a change resolve immediately so screens never show stale revisions.
    const refresh = kind === "read" && Date.now() - this.lastEmit < 1500 && this.failure !== "slow";
    await new Promise((r) => setTimeout(r, refresh ? 0 : this.failure === "slow" ? SLOW_LATENCY : this.latency));
    if (this.failure === "expire") {
      this.failure = "none";
      this.data.session_key = undefined;
      this.emit();
      this.fail("SESSION_EXPIRED", "Your preview session expired. Start a new isolated workspace from the catalog.");
    }
    if (kind === "command") {
      if (this.failure === "fail_next") {
        this.failure = "none";
        this.fail("DEPENDENCY_UNAVAILABLE", "The save didn't go through (simulated outage). Nothing was committed; your input is kept, so you can retry.", true);
      }
      if (this.failure === "deny_next") {
        this.failure = "none";
        this.fail("FORBIDDEN", "You don't have permission for this action (simulated denial).");
      }
    }
  }
  private takeStale(): boolean {
    if (this.failure === "stale_next") {
      this.failure = "none";
      return true;
    }
    return false;
  }

  private ws(): WorkspaceState {
    const key = this.data.session_key;
    const ws = key ? this.data.workspaces[key] : undefined;
    if (!key || !ws) this.fail("SESSION_EXPIRED", "No active preview workspace. Choose a company in the catalog.");
    return ws;
  }
  private pack(): PackFixture {
    return PACKS[this.ws().key];
  }
  private persona(id?: string): Persona {
    const pid = id ?? this.ws().persona_id;
    const p = this.pack().personas.find((x) => x.employee_id === pid);
    if (!p) this.fail("NOT_FOUND", "Persona not found in this workspace.");
    return p;
  }
  private has(grant: PreviewGrant) {
    return this.persona().grants.includes(grant);
  }
  private require(grant: PreviewGrant, message: string) {
    if (!this.has(grant)) this.fail("FORBIDDEN", message);
  }
  name(id?: string) {
    const p = this.pack().personas.find((x) => x.employee_id === id);
    return p ? `${p.first_name} ${p.last_name}` : "Unknown";
  }
  private next(prefix: string) {
    const ws = this.ws();
    ws.seq += 1;
    return `${prefix}-${ws.seq}`;
  }
  private notify(employee_id: string, type: string, minimal_message: string, resource_href: string) {
    const ws = this.ws();
    const list = (ws.notifications[employee_id] ??= []);
    list.unshift({ notification_id: this.next("ntf"), type, minimal_message, resource_href, created_label: "Just now" });
  }
  private citations(keys: string[]): Citation[] {
    const pack = this.pack();
    const ws = this.ws();
    return keys
      .map((k) => pack.excerpts[k])
      .filter((e): e is SourceExcerpt => Boolean(e))
      .filter((e) => !ws.revokedVersions.includes(e.document_version_id))
      .map((e) => ({ citation_id: e.source_id, label: this.citationLabel(e), excerpt: e }));
  }
  private citationLabel(e: SourceExcerpt) {
    const doc = this.allDocuments().find((d) => d.document_version_id === e.document_version_id);
    const last = e.heading_path[e.heading_path.length - 1] ?? "";
    return doc ? `${doc.document_code} v${doc.version} · ${last}` : e.heading_path.join(" · ");
  }
  private allDocuments(): DocumentVersion[] {
    return [...this.pack().documents, ...this.ws().extraDocuments];
  }

  // ---------------------------------------------------------------- PreviewControls
  advanceShift() {
    const h = this.ws().handover;
    const idx = h.occurrences.findIndex((o) => o.shift_instance_id === h.target_id);
    const target = h.occurrences[idx];
    if (!target) return;
    h.occurrences.forEach((o) => {
      if (o.shift_instance_id === h.source_id) o.status = "COMPLETED";
    });
    target.status = "ACTIVE";
    let nextOcc = h.occurrences[idx + 1];
    if (!nextOcc) {
      const first = h.occurrences[0]!;
      nextOcc = { ...first, shift_instance_id: `${first.shift_instance_id}-next`, name: `${first.name} (next day)`, status: "SCHEDULED" };
      h.occurrences.push(nextOcc);
    }
    h.source_id = target.shift_instance_id;
    h.target_id = nextOcc.shift_instance_id;
    h.status = "DRAFT";
    h.changes = [];
    h.revision += 1;
    this.emit();
  }
  toggleRevokedSource(id: string) {
    const ws = this.ws();
    ws.revokedVersions = ws.revokedVersions.includes(id) ? ws.revokedVersions.filter((x) => x !== id) : [...ws.revokedVersions, id];
    this.emit();
  }
  isRevoked(id: string) {
    const key = this.data.session_key;
    return key ? Boolean(this.data.workspaces[key]?.revokedVersions.includes(id)) : false;
  }

  // ---------------------------------------------------------------- platform
  async listScenarios(): Promise<ScenarioCard[]> {
    await this.gate("read");
    return PACK_ORDER.map((k) => PACKS[k].card);
  }
  hasWorkspace(key: ScenarioKey) {
    return Boolean(this.data.workspaces[key]);
  }
  async getLocalDemoRun(key: ScenarioKey): Promise<LocalDemoRun | null> {
    await this.gate("read");
    const ws = this.data.workspaces[key];
    if (!ws) return null;
    const pack = PACKS[key];
    return {
      key,
      scenario_id: pack.card.scenario_id,
      workspace_id: ws.workspace_id,
      pinned_pack_version: ws.pack_version,
      active_pack_version: pack.card.pack_version,
      persona_selected: ws.persona_selected,
      persona: ws.persona_selected ? pack.personas.find((p) => p.employee_id === ws.persona_id) : undefined,
      is_active_session: this.data.session_key === key,
    };
  }
  async startDemoSession(key: ScenarioKey, fresh: boolean): Promise<DemoSession> {
    // Failure is simulated before anything changes, so an existing run stays usable.
    await this.gate("command");
    if (!PACKS[key] || PACKS[key].card.status !== "READY") this.fail("NOT_FOUND", "This company isn't available in the demo catalog.");
    if (fresh || !this.data.workspaces[key]) this.data.workspaces[key] = createWorkspace(key);
    this.data.session_key = key;
    this.data.expires_at = new Date(Date.now() + 4 * 3600_000).toISOString();
    this.emit();
    return this.sessionView();
  }
  private sessionView(): DemoSession {
    const ws = this.ws();
    return {
      session_id: `preview-session-${ws.workspace_id}`,
      scenario: this.pack().card,
      workspace_id: ws.workspace_id,
      pack_version: ws.pack_version,
      persona: this.persona(),
      persona_selected: ws.persona_selected,
      expires_at: this.data.expires_at ?? "",
    };
  }
  /** Synchronous peek used by the shell; never throws. */
  peekSession(): DemoSession | null {
    try {
      return this.data.session_key ? this.sessionView() : null;
    } catch {
      return null;
    }
  }
  /** Synchronous roster peek for name lookups (same data as GET /personas). */
  peekPersonas(): Persona[] {
    const key = this.data.session_key;
    return key && this.data.workspaces[key] ? PACKS[key].personas : [];
  }
  async getSession(): Promise<DemoSession | null> {
    await this.gate("read");
    return this.peekSession();
  }
  async endSession() {
    this.data.session_key = undefined;
    this.emit();
  }
  async listPersonas(): Promise<Persona[]> {
    await this.gate("read");
    return this.pack().personas;
  }
  async switchPersona(employee_id: string): Promise<DemoSession> {
    await this.gate("command");
    this.persona(employee_id);
    this.ws().persona_id = employee_id;
    this.ws().persona_selected = true;
    this.emit();
    return this.sessionView();
  }
  async getVoiceListenGrant(): Promise<never> {
    await this.gate("read");
    this.fail("CAPABILITY_UNAVAILABLE", "Voice isn't connected in this preview. Use the simulated tap-to-talk in Review tools, or type.");
  }
  async getWorkVoiceListenGrant(): Promise<never> {
    await this.gate("read");
    this.fail("CAPABILITY_UNAVAILABLE", "Voice isn't connected in this preview.");
  }
  async streamReplySpeech(): Promise<never> {
    await this.gate("read");
    this.fail("CAPABILITY_UNAVAILABLE", "Spoken replies aren't connected in this preview.");
  }
  async getReplySpeech(): Promise<never> {
    await this.gate("read");
    this.fail("CAPABILITY_UNAVAILABLE", "Spoken replies aren't connected in this preview.");
  }
  /** The preview's state changes only in this tab, so there is nothing to watch. */
  watchWork(): () => void {
    return () => undefined;
  }
  async getAssignmentExplanation(): Promise<never> {
    await this.gate("read");
    this.fail("CAPABILITY_UNAVAILABLE", "Automatic assignment isn't part of this preview.");
  }
  async getAssignmentCandidates(): Promise<never> {
    await this.gate("read");
    this.fail("CAPABILITY_UNAVAILABLE", "Automatic assignment isn't part of this preview.");
  }
  async reassignWorkItem(): Promise<never> {
    await this.gate("command");
    this.fail("CAPABILITY_UNAVAILABLE", "Automatic assignment isn't part of this preview.");
  }
  async getCalendarStatus(): Promise<never> {
    await this.gate("read");
    this.fail("CAPABILITY_UNAVAILABLE", "Google Calendar isn't connected in this preview.");
  }
  async streamWorkReplySpeech(): Promise<never> {
    await this.gate("read");
    this.fail("CAPABILITY_UNAVAILABLE", "Spoken replies aren't connected in this preview.");
  }
  async getHandoverVoiceListenGrant(): Promise<never> {
    return this.getWorkVoiceListenGrant();
  }
  async streamHandoverReplySpeech(): Promise<never> {
    return this.streamWorkReplySpeech();
  }
  async getKtVoiceListenGrant(): Promise<never> {
    return this.getWorkVoiceListenGrant();
  }
  async streamKtReplySpeech(): Promise<never> {
    return this.streamWorkReplySpeech();
  }
  // Evaluator access codes only exist on the hosted API; the preview has no limits to lift.
  async getAccess(): Promise<AccessInfo> {
    return { tier: "PUBLIC", expires_at: null };
  }
  async getDemoUsage(): Promise<null> {
    return null;
  }
  async redeemAccessCode(): Promise<never> {
    this.fail("CAPABILITY_UNAVAILABLE", "Evaluator codes apply to the hosted demo. This preview has no usage limits.");
  }
  async leaveAccess(): Promise<AccessInfo> {
    return { tier: "PUBLIC", expires_at: null };
  }
  async getCapabilities(): Promise<Capabilities> {
    return {
      conversation_engine: "UNAVAILABLE",
      voice_adapter: "UNAVAILABLE",
      semantic_indexing: "UNAVAILABLE",
      kt_drafting: "UNAVAILABLE",
      recommendation: "UNAVAILABLE",
      inbox_delivery: "SIMULATED",
    };
  }

  // ---------------------------------------------------------------- onboarding
  private learner(): LearnerState | undefined {
    return this.ws().learners[this.ws().persona_id];
  }
  private orderedSubtopics() {
    return this.pack().onboarding.topics.flatMap((t) => t.subtopics);
  }
  private currentSubtopicId(l: LearnerState): string | undefined {
    const subs = this.orderedSubtopics();
    return subs.find((s) => l.progress[s.subtopic_id] === "IN_PROGRESS")?.subtopic_id ?? subs.find((s) => l.progress[s.subtopic_id] === "NOT_STARTED")?.subtopic_id;
  }
  private overview(l: LearnerState): OnboardingOverview {
    const o = this.pack().onboarding;
    return {
      learning_assignment_id: l.learning_assignment_id,
      curriculum_name: o.curriculum_name,
      curriculum_version: o.curriculum_version,
      source_versions: this.allDocuments().filter((d) => o.source_version_ids.includes(d.document_version_id)),
      topics: o.topics.map((t) => ({ ...t, subtopics: t.subtopics.map((s) => ({ ...s, status: l.progress[s.subtopic_id] ?? "NOT_STARTED" })) })),
      current_subtopic_id: l.session?.current_subtopic_id ?? this.currentSubtopicId(l),
      session_status: l.session ? l.session.status : "NONE",
      saved_at: l.saved_label,
    };
  }
  async getOnboarding(): Promise<OnboardingOverview | null> {
    await this.gate("read");
    const l = this.learner();
    return l ? this.overview(l) : null;
  }
  private tutorMessages(msgs: PackFixture["onboarding"]["scripts"][number]["opening"], session: Pick<LearnerSession, "pending_check">): TranscriptMessage[] {
    const first = this.persona().first_name;
    return msgs.map((m) => {
      if (m.check) session.pending_check = { ...m.check, text: m.text };
      return {
        message_id: this.next("msg"),
        sender: "AI",
        kind: m.kind,
        text: m.text.replaceAll("{name}", first),
        citations: this.citations(m.excerpt_keys),
        assessment: m.assessment ? { outcome: m.assessment.outcome, criteria_version: "synthetic-criteria-v1", note: m.assessment.note } : undefined,
        provenance: "SCRIPTED_FIXTURE",
        created_at: "Just now",
      };
    });
  }
  private script(subtopic_id: string) {
    const s = this.pack().onboarding.scripts.find((x) => x.subtopic_id === subtopic_id);
    if (!s) this.fail("NOT_FOUND", "No preview script for this subtopic.");
    return s;
  }
  private sessionView2(l: LearnerState): OnboardingSessionView {
    const s = l.session!;
    let prompts: ScriptPrompt[] = [];
    if (s.status === "ACTIVE" && !s.awaiting_continue) {
      const sc = this.script(s.current_subtopic_id);
      const stage = s.stage[s.current_subtopic_id] ?? 0;
      prompts = sc.steps.filter((st) => st.stage === stage && !s.played.includes(st.prompt.prompt_id)).map((st) => st.prompt);
    }
    return {
      learning_session_id: s.learning_session_id,
      revision: s.revision,
      overview: this.overview(l),
      transcript: s.transcript,
      pending_check: s.pending_check,
      awaiting_continue: s.awaiting_continue,
      script_prompts: prompts,
      status: s.status,
    };
  }
  async startOnboardingSession(): Promise<OnboardingSessionView> {
    await this.gate("command");
    const l = this.learner();
    if (!l) this.fail("NOT_FOUND", "No onboarding is assigned to you.");
    const current = this.currentSubtopicId(l);
    if (!l.session) {
      if (!current) this.fail("GUARD_FAILED", "Every required subtopic is already complete.");
      const resuming = l.progress[current] === "IN_PROGRESS";
      const session: LearnerSession = {
        learning_session_id: this.next("ls"),
        revision: 1,
        status: "ACTIVE",
        transcript: [],
        current_subtopic_id: current,
        stage: {},
        played: [],
        awaiting_continue: false,
      };
      l.progress[current] = "IN_PROGRESS";
      const sc = this.script(current);
      session.transcript = this.tutorMessages(resuming ? sc.resume : sc.opening, session);
      l.session = session;
    } else if (l.session.status === "PAUSED") {
      const s = l.session;
      s.status = "ACTIVE";
      s.revision += 1;
      if (s.awaiting_continue) {
        const nextSub = this.orderedSubtopics().find((x) => x.subtopic_id === current);
        s.transcript.push(...this.tutorMessages([{ kind: "OPENING", text: `Welcome back, {name}. Your completed work is saved. Next is "${nextSub?.name ?? "the next subtopic"}" — continue, or take a break?`, excerpt_keys: [] }], s));
      } else {
        s.transcript.push(...this.tutorMessages(this.script(s.current_subtopic_id).resume, s));
      }
    }
    l.saved_label = "Saved just now";
    this.emit();
    return this.sessionView2(l);
  }
  async getOnboardingSession(): Promise<OnboardingSessionView | null> {
    await this.gate("read");
    const l = this.learner();
    return l?.session ? this.sessionView2(l) : null;
  }
  private checkRevision(expected: number | undefined, actual: number) {
    if (this.takeStale() || (expected !== undefined && expected !== actual)) {
      this.fail("REVISION_CONFLICT", "This was changed somewhere else (stale revision). Reload to see the latest state; your input is kept.");
    }
  }
  async sendOnboardingTurn(input: TurnInput): Promise<OnboardingSessionView> {
    await this.gate("command");
    const l = this.learner();
    const s = l?.session;
    if (!l || !s) this.fail("NOT_FOUND", "Start the conversation first.");
    this.checkRevision(input.expected_revision, s.revision);
    if (s.status !== "ACTIVE") this.fail("GUARD_FAILED", "This conversation is paused. Resume it to continue.");
    s.transcript.push({ message_id: this.next("msg"), sender: "EMPLOYEE", input_kind: input.input_kind, kind: "SYSTEM", text: input.text, citations: [], provenance: "EMPLOYEE_INPUT", created_at: "Just now" });
    const sc = this.script(s.current_subtopic_id);
    const stage = s.stage[s.current_subtopic_id] ?? 0;
    const step = input.preview_prompt_id
      ? sc.steps.find((st) => st.prompt.prompt_id === input.preview_prompt_id && st.stage === stage && !s.played.includes(st.prompt.prompt_id))
      : undefined;
    if (!step || s.awaiting_continue) {
      s.transcript.push({ message_id: this.next("msg"), sender: "SYSTEM", kind: "NOT_INTERPRETED", text: NOT_INTERPRETED + (s.pending_check ? " The question above is still open." : ""), citations: [], provenance: "PREVIEW_SYSTEM", created_at: "Just now" });
    } else {
      s.played.push(step.prompt.prompt_id);
      if (step.advances) s.stage[s.current_subtopic_id] = stage + 1;
      const msgs = this.tutorMessages(step.responses, s);
      if (step.responses.some((r) => r.assessment?.outcome === "CORRECT")) s.pending_check = undefined;
      s.transcript.push(...msgs);
      if (step.completes_subtopic) {
        l.progress[s.current_subtopic_id] = "COMPLETED";
        s.pending_check = undefined;
        const subs = this.orderedSubtopics();
        const done = subs.find((x) => x.subtopic_id === s.current_subtopic_id);
        const nextSub = subs.find((x) => l.progress[x.subtopic_id] === "NOT_STARTED");
        if (nextSub) {
          s.awaiting_continue = true;
          s.transcript.push(...this.tutorMessages([{ kind: "COMPLETION", text: `You've completed "${done?.name}". Next is "${nextSub.name}". Continue now, or take a break?`, excerpt_keys: [] }], s));
        } else {
          s.status = "COMPLETED";
          s.transcript.push(...this.tutorMessages([{ kind: "COMPLETION", text: this.pack().onboarding.curriculum_complete_text, excerpt_keys: [] }], s));
        }
      }
    }
    s.revision += 1;
    l.saved_label = "Saved just now";
    this.emit();
    return this.sessionView2(l);
  }
  async continueOnboarding(cmd: Command): Promise<OnboardingSessionView> {
    await this.gate("command");
    const l = this.learner();
    const s = l?.session;
    if (!l || !s) this.fail("NOT_FOUND", "Start the conversation first.");
    this.checkRevision(cmd.expected_revision, s.revision);
    if (!s.awaiting_continue) this.fail("GUARD_FAILED", "There's still an objective to finish in this subtopic before moving on.");
    const nextId = this.currentSubtopicId(l);
    if (!nextId) this.fail("GUARD_FAILED", "No next subtopic is eligible.");
    s.current_subtopic_id = nextId;
    s.awaiting_continue = false;
    s.status = "ACTIVE";
    l.progress[nextId] = "IN_PROGRESS";
    s.transcript.push(...this.tutorMessages(this.script(nextId).opening, s));
    s.revision += 1;
    l.saved_label = "Saved just now";
    this.emit();
    return this.sessionView2(l);
  }
  async pauseOnboarding(cmd: Command): Promise<OnboardingSessionView> {
    await this.gate("command");
    const l = this.learner();
    const s = l?.session;
    if (!l || !s) this.fail("NOT_FOUND", "Start the conversation first.");
    this.checkRevision(cmd.expected_revision, s.revision);
    const subs = this.orderedSubtopics();
    const done = subs.filter((x) => l.progress[x.subtopic_id] === "COMPLETED").length;
    const text = s.awaiting_continue
      ? `Progress saved: ${done} of ${subs.length} subtopics complete. The next subtopic stays not started until you choose to continue.`
      : `Progress saved: ${done} of ${subs.length} subtopics complete. We'll resume "${subs.find((x) => x.subtopic_id === s.current_subtopic_id)?.name}" where you left off${s.pending_check ? ", including the open question" : ""}.`;
    s.transcript.push({ message_id: this.next("msg"), sender: "AI", kind: "PAUSE", text, citations: [], provenance: "SCRIPTED_FIXTURE", created_at: "Just now" });
    s.status = "PAUSED";
    s.revision += 1;
    l.saved_label = "Saved just now";
    this.emit();
    return this.sessionView2(l);
  }
  async getSupervisorProgress(): Promise<SupervisorProgressRow[]> {
    await this.gate("read");
    this.require("onboarding.supervise", "Only an authorized supervisor can see team onboarding progress.");
    const o = this.pack().onboarding;
    return Object.values(this.ws().learners).map((l) => ({
      employee_name: this.name(l.employee_id),
      curriculum_name: o.curriculum_name,
      curriculum_version: o.curriculum_version,
      subtopics: this.orderedSubtopics().map((s) => ({ name: s.name, status: l.progress[s.subtopic_id] ?? "NOT_STARTED" })),
    }));
  }

  // ---------------------------------------------------------------- companion
  private companionScript(): CompanionScript {
    const pack = this.pack();
    const me = this.persona();
    const found = pack.companion_scripts.find((c) => c.employee_id === me.employee_id);
    if (found) return found;
    const t = pack.card.terminology;
    return {
      employee_id: me.employee_id,
      opening: `Hi ${me.first_name}. Here's your work briefing. Nothing is assigned to you right now; your team's open ${t.workItems} are listed for reference.`,
      steps: [
        { prompt: { prompt_id: "g-work", label: `Show team ${t.workItems}`, text: `Show the team's ${t.workItems}.` }, reply: `Here are the open ${t.workItems} you can see.`, excerpt_keys: [], ui_action: { type: "SHOW_WORK_ITEMS", filters: { status: ["ACTIVE", "IN_PROGRESS", "BLOCKED"] } } },
        { prompt: { prompt_id: "g-updates", label: "Show recent updates", text: "Show recent updates." }, reply: "Here are the permitted updates.", excerpt_keys: [], ui_action: { type: "SHOW_WORK_UPDATES" } },
        { prompt: { prompt_id: "g-brief", label: "Back to my briefing", text: "Back to my briefing." }, reply: "Here's your briefing again.", excerpt_keys: [], ui_action: { type: "SHOW_BRIEFING" } },
      ],
    };
  }
  private workSession() {
    const ws = this.ws();
    return ws.workSessions[ws.persona_id];
  }
  private workView(): WorkSessionView {
    const s = this.workSession()!;
    return { work_session_id: s.work_session_id, revision: s.revision, transcript: s.transcript, canvas: s.canvas, script_prompts: this.companionScript().steps.map((x) => x.prompt), pending_report: s.pending_report };
  }
  async startWorkSession(): Promise<WorkSessionView> {
    await this.gate("read");
    const ws = this.ws();
    if (!ws.workSessions[ws.persona_id]) {
      ws.workSessions[ws.persona_id] = {
        work_session_id: this.next("wsn"),
        revision: 1,
        canvas: { view: "BRIEFING" },
        transcript: [{ message_id: this.next("wm"), sender: "AI", text: this.companionScript().opening, citations: [], provenance: "SCRIPTED_FIXTURE", ui_action: "SHOW_BRIEFING" }],
      };
      this.emit();
    }
    return this.workView();
  }
  /** Validates a fixture ui_action against the allowlist and authorized resources. */
  private resolveCanvas(action: UiAction, current: CanvasView): CanvasView | { rejected: string } {
    if (!(UI_ACTIONS as readonly string[]).includes(action.type)) return { rejected: action.type };
    const ws = this.ws();
    const ref = action.resource_refs?.[0];
    switch (action.type) {
      case "SHOW_BRIEFING":
        return { view: "BRIEFING" };
      case "SHOW_WORK_ITEMS":
        if (ref && !ws.items.some((i) => i.work_item_id === ref)) return { rejected: `unknown resource ${ref}` };
        return { view: "WORK_ITEMS", filters: action.filters, selected_id: ref };
      case "SHOW_WORK_UPDATES":
        return { view: "WORK_UPDATES" };
      case "SHOW_FOCUS_PLAN":
        return { view: "FOCUS_PLAN" };
      case "SHOW_GUIDANCE":
        if (!ref || !this.pack().guidance.some((g) => g.guidance_id === ref)) return { rejected: "unknown guidance" };
        return { view: "GUIDANCE", guidance_id: ref };
      case "SHOW_DELEGATION_PROPOSAL":
        if (!this.has("delegation.confirm")) return { rejected: "delegation proposal requires a scoped lead" };
        return { view: "DELEGATION_PROPOSAL", proposal_id: ws.proposal.delegation_proposal_id };
      default:
        return current;
    }
  }
  async sendWorkMessage(input: TurnInput): Promise<WorkSessionView> {
    await this.gate("command");
    const s = this.workSession();
    if (!s) this.fail("NOT_FOUND", "Open the Companion first.");
    this.checkRevision(input.expected_revision, s.revision);
    s.transcript.push({ message_id: this.next("wm"), sender: "EMPLOYEE", text: input.text, citations: [], provenance: "EMPLOYEE_INPUT" });
    const step = input.preview_prompt_id ? this.companionScript().steps.find((x) => x.prompt.prompt_id === input.preview_prompt_id) : undefined;
    if (!step) {
      s.transcript.push({ message_id: this.next("wm"), sender: "SYSTEM", text: NOT_INTERPRETED, citations: [], provenance: "PREVIEW_SYSTEM", ui_action: "NO_VIEW_CHANGE" });
    } else if (step.effect?.kind === "INVALID_ACTION") {
      s.transcript.push({ message_id: this.next("wm"), sender: "SYSTEM", text: `Rejected an unsupported view action (${step.effect.attempted}). Only allowlisted views can be shown, so the current view is unchanged.`, citations: [], provenance: "PREVIEW_SYSTEM", rejected_action: step.effect.attempted });
    } else {
      let reply = step.reply;
      if (step.effect?.kind === "EDIT_PROPOSAL") {
        const p = this.ws().proposal;
        if (p.status === "CONFIRMED" || p.status === "REJECTED") {
          reply = `This proposal is already ${p.status.toLowerCase()}, so it can't be edited. Ask for a new proposal instead.`;
        } else if (this.has("delegation.confirm")) {
          for (const e of step.effect.edits) {
            const item = p.items.find((i) => i.work_item_id === e.work_item_id);
            if (item) item.final_employee_id = e.final_employee_id;
          }
          p.status = "EDITED";
          p.revision += 1;
        }
      }
      if (step.effect?.kind === "OPEN_REPORT") {
        const item = this.ws().items.find((i) => i.work_item_id === (step.effect as { work_item_id: string }).work_item_id);
        if (item?.assignee_id !== this.ws().persona_id) {
          reply = `You aren't assigned to ${item?.external_id ?? "that item"}, so you can't report on it. Ask your lead if it should be assigned to you.`;
        } else {
          s.pending_report = { work_item_id: item.work_item_id, draft: step.effect.draft };
        }
      }
      const resolved = this.resolveCanvas(step.ui_action, s.canvas);
      if ("rejected" in resolved) {
        s.transcript.push({ message_id: this.next("wm"), sender: "SYSTEM", text: `That view isn't available to you (${resolved.rejected}). The current view is unchanged.`, citations: [], provenance: "PREVIEW_SYSTEM", rejected_action: step.ui_action.type });
      } else {
        s.canvas = resolved;
        s.transcript.push({ message_id: this.next("wm"), sender: "AI", text: reply, citations: this.citations(step.excerpt_keys), provenance: "SCRIPTED_FIXTURE", ui_action: step.ui_action.type });
      }
    }
    s.revision += 1;
    this.emit();
    return this.workView();
  }
  async dismissPendingReport(): Promise<WorkSessionView> {
    const s = this.workSession();
    if (s) {
      s.pending_report = undefined;
      this.emit();
    }
    return this.workView();
  }
  async getWorkDashboard(): Promise<WorkDashboard> {
    await this.gate("read");
    const ws = this.ws();
    const open = ws.items.filter((i) => !i.historical && !["COMPLETED", "CANCELLED", "CLOSED"].includes(i.status));
    const mine = open.filter((i) => i.assignee_id === ws.persona_id);
    const blocked = open.filter((i) => i.status === "BLOCKED").length;
    const isLead = this.has("delegation.confirm");
    const scope = isLead ? open : mine;
    const h = ws.handover;
    const lastPub = h.publications[h.publications.length - 1];
    const occ = h.occurrences.find((o) => o.shift_instance_id === h.source_id);
    const inShift = h.occurrences.some((o) => o.lead_employee_id === ws.persona_id || o.member_ids.includes(ws.persona_id));
    return {
      active_count: scope.filter((i) => i.status !== "BLOCKED").length,
      blocked_count: isLead ? blocked : mine.filter((i) => i.status === "BLOCKED").length,
      overdue_count: 0,
      work_state: (isLead ? blocked : mine.filter((i) => i.status === "BLOCKED").length) > 0 ? "BLOCKED" : scope.length >= 4 ? "HIGH_WORKLOAD" : "ON_TRACK",
      shift_label: inShift && occ ? `${occ.name} shift · ${occ.window_label}` : undefined,
      incoming_continuity: inShift && lastPub ? `Handover publication #${lastPub.publication_number} (${this.occName(lastPub.source_shift_instance_id)} → ${this.occName(lastPub.target_shift_instance_id)}) with ${lastPub.entries.length} items` : undefined,
      priorities: this.pack().priorities[ws.persona_id] ?? [],
    };
  }
  private occName(id: string) {
    return this.ws().handover.occurrences.find((o) => o.shift_instance_id === id)?.name ?? id;
  }
  async listWorkItems(): Promise<WorkItem[]> {
    await this.gate("read");
    return this.ws().items;
  }
  async listWorkEvents(): Promise<WorkEvent[]> {
    await this.gate("read");
    return [...this.ws().events].reverse();
  }
  async getGuidance(id: string): Promise<GuidanceProjection> {
    await this.gate("read");
    const g = this.pack().guidance.find((x) => x.guidance_id === id);
    if (!g) this.fail("NOT_FOUND", "Guidance not found.");
    const keyMap: Record<string, string[]> = {
      "g-ns-cause": ["sop-2.3", "ticket-492"],
      "g-ns-current": ["sop-1.2", "v33-1"],
      "g-ns-coolant": ["sop-C3", "sop-1.3"],
      "g-ac-timeout": ["ops-2", "ev-131"],
      "g-hb-escalate": ["bpo-3", "case-104"],
    };
    return { ...g, citations: this.citations(keyMap[id] ?? []) };
  }
  async getTicketSystem(): Promise<never> {
    await this.gate("read");
    this.fail("CAPABILITY_UNAVAILABLE", "The ticket system is only available with the WorkWeave backend.");
  }
  async updateTicketStatus(): Promise<never> {
    await this.gate("command");
    this.fail("CAPABILITY_UNAVAILABLE", "The ticket system is only available with the WorkWeave backend.");
  }
  async reportWorkEvent(work_item_id: string, event_type: "COMMENTED" | "REPORTED_COMPLETE" | "BLOCKED", description: string, cmd: Command): Promise<WorkEvent> {
    await this.gate("command");
    const ws = this.ws();
    const item = ws.items.find((i) => i.work_item_id === work_item_id);
    if (!item) this.fail("NOT_FOUND", "Work item not found.");
    if (item.assignee_id !== ws.persona_id) this.fail("FORBIDDEN", "Only the assigned member can report on this item.");
    if (!description.trim()) this.fail("MALFORMED_INPUT", "Describe what you did or observed before submitting.");
    this.checkRevision(cmd.expected_revision, item.revision);
    // ADR-033: a report never changes the ticket; it waits until the ticket system shows the same status.
    const reported_status = event_type === "REPORTED_COMPLETE" ? "DONE" : event_type === "BLOCKED" ? "BLOCKED" : "IN_PROGRESS";
    const sync_status = (reported_status === "IN_PROGRESS" && item.status === "IN_PROGRESS") || (reported_status === "BLOCKED" && item.status === "BLOCKED") ? "MATCHED" : "AWAITING_SOURCE";
    const ev: WorkEvent = { work_event_id: this.next("ev"), work_item_id, employee_id: ws.persona_id, event_type, description, evidence_type: "REPORTED", observed_label: "Just now", source: "COMPANION", sync_status };
    item.report = { reported_status, sync_status, employee_id: ws.persona_id, reported_label: "Just now" };
    ws.events.push(ev);
    const s = this.workSession();
    if (s) {
      s.pending_report = undefined;
      s.transcript.push({ message_id: this.next("wm"), sender: "SYSTEM", text: `Report saved on ${item.external_id}. ${event_type === "REPORTED_COMPLETE" ? "It doesn't change the ticket: it stays on your list, at lower priority, until the ticket system shows it resolved." : "It's recorded as a progress update."}`, citations: [], provenance: "PREVIEW_SYSTEM" });
    }
    const h = ws.handover;
    const hi = h.items.find((i) => i.work_item_id === work_item_id);
    if (hi && event_type === "REPORTED_COMPLETE") {
      h.suggestions.push({ suggestion_id: this.next("sg"), suggestion_type: "STATUS_UPDATE", handover_item_id: hi.handover_item_id, title: `${item.external_id} reported complete`, reason: `${this.name(ws.persona_id)} reported completion just now. Review the evidence before changing the draft. (Suggestion simulated by the preview.)`, before: hi.work_status, proposed: "COMPLETED (after your validation)", source_label: `Work event · ${this.name(ws.persona_id)} · reported`, evidence_type: "REPORTED", status: "PENDING", report_event_id: ev.work_event_id });
    }
    const lead = h.occurrences.find((o) => o.shift_instance_id === h.source_id)?.lead_employee_id;
    if (lead && lead !== ws.persona_id) this.notify(lead, "WORK_REPORTED", `New report on ${item.external_id}`, "/companion/");
    this.emit();
    return ev;
  }
  /** Lead-confirmed completion: work COMPLETED; linked handover item COMPLETED + source ack PENDING (new cycle). */
  private completeWork(work_item_id: string, ev?: WorkEvent) {
    const ws = this.ws();
    const item = ws.items.find((i) => i.work_item_id === work_item_id)!;
    if (ev) ev.validation = "VALIDATED";
    item.status = "COMPLETED";
    item.revision += 1;
    ws.events.push({ work_event_id: this.next("ev"), work_item_id, employee_id: ws.persona_id, event_type: "VALIDATED", description: `${this.name(ws.persona_id)} validated the completion report.`, evidence_type: "OBSERVED", observed_label: "Just now" });
    const h = ws.handover;
    const hi = h.items.find((i) => i.work_item_id === work_item_id);
    if (hi) this.openCycle(h, hi);
    h.suggestions.filter((sg) => sg.handover_item_id === hi?.handover_item_id && sg.suggestion_type === "STATUS_UPDATE" && sg.status === "PENDING").forEach((sg) => (sg.status = "ACCEPTED"));
  }
  private openCycle(h: HandoverState, hi: HandoverItem) {
    const cycle = { completion_cycle_id: this.next("cycle"), handover_item_id: hi.handover_item_id, completed_in_shift_instance_id: h.source_id, requested_from_shift_instance_id: hi.originating_shift_instance_id, status: "PENDING" as const };
    h.cycles.push(cycle);
    hi.work_status = "COMPLETED";
    hi.acknowledgement_status = "PENDING";
    hi.completion_cycle_id = cycle.completion_cycle_id;
    h.item_events.push({ event_id: this.next("hie"), handover_item_id: hi.handover_item_id, label: `Completed (cycle ${cycle.completion_cycle_id}); source acknowledgement pending`, shift_name: this.occName(h.source_id) });
    const originLead = h.occurrences.find((o) => o.shift_instance_id === hi.originating_shift_instance_id)?.lead_employee_id;
    if (originLead) this.notify(originLead, "ACK_REQUESTED", `Acknowledge completion of ${hi.display_id}`, "/handover/");
  }

  // ---------------------------------------------------------------- delegation
  async listProposals(): Promise<DelegationProposal[]> {
    await this.gate("read");
    this.require("delegation.confirm", "Only the scoped lead can view delegation proposals.");
    return [this.ws().proposal];
  }
  async getProposal(id: string): Promise<DelegationProposal> {
    await this.gate("read");
    this.require("delegation.confirm", "Only the scoped lead can view delegation proposals.");
    const p = this.ws().proposal;
    if (p.delegation_proposal_id !== id) this.fail("NOT_FOUND", "Proposal not found.");
    return p;
  }
  async editProposalItem(id: string, work_item_id: string, final_employee_id: string, cmd: Command): Promise<DelegationProposal> {
    await this.gate("command");
    this.require("delegation.confirm", "Only the scoped lead can edit this proposal.");
    const p = this.ws().proposal;
    this.checkRevision(cmd.expected_revision, p.revision);
    if (p.status === "CONFIRMED" || p.status === "REJECTED") this.fail("GUARD_FAILED", "This proposal can't be edited any more.");
    const item = p.items.find((i) => i.work_item_id === work_item_id);
    if (!item) this.fail("NOT_FOUND", "Proposal item not found.");
    item.final_employee_id = final_employee_id === item.recommended_employee_id ? undefined : final_employee_id;
    p.status = "EDITED";
    p.revision += 1;
    this.emit();
    return p;
  }
  async confirmProposal(id: string, cmd: Command): Promise<DelegationProposal> {
    await this.gate("command");
    this.require("delegation.confirm", "Only the scoped lead can confirm assignments.");
    const ws = this.ws();
    const p = ws.proposal;
    if (p.status === "CONFIRMED") return p; // replay returns the committed result
    if (p.status === "REJECTED") this.fail("GUARD_FAILED", "This proposal was rejected. Ask for a new proposal.");
    this.checkRevision(cmd.expected_revision, p.revision);
    for (const it of p.items) {
      const assignee = it.final_employee_id ?? it.recommended_employee_id;
      const wi = ws.items.find((w) => w.work_item_id === it.work_item_id);
      if (wi) {
        wi.assignee_id = assignee;
        wi.revision += 1;
        this.notify(assignee, "ASSIGNMENT", `You've been assigned ${wi.external_id}`, "/companion/");
      }
    }
    p.status = "CONFIRMED";
    p.revision += 1;
    this.emit();
    return p;
  }
  async rejectProposal(id: string, reason: string, cmd: Command): Promise<DelegationProposal> {
    await this.gate("command");
    this.require("delegation.confirm", "Only the scoped lead can reject this proposal.");
    const p = this.ws().proposal;
    this.checkRevision(cmd.expected_revision, p.revision);
    if (!reason.trim()) this.fail("MALFORMED_INPUT", "Give a reason for rejecting the proposal.");
    p.status = "REJECTED";
    p.revision += 1;
    this.emit();
    return p;
  }

  // ---------------------------------------------------------------- capture / memory
  async createMemoryDraft(content: string, audience: MemoryDraft["requested_audience"], cmd: Command): Promise<MemoryDraft> {
    await this.gate("command");
    void cmd;
    if (!content.trim()) this.fail("MALFORMED_INPUT", "Write the explanation you want to keep.");
    const d: MemoryDraft = { draft_id: this.next("md"), owner_employee_id: this.ws().persona_id, content, requested_audience: audience, status: "DRAFT", evidence_type: "REPORTED", revision: 1 };
    this.ws().memoryDrafts.push(d);
    this.emit();
    return d;
  }
  async listMyMemoryDrafts(): Promise<MemoryDraft[]> {
    await this.gate("read");
    return this.ws().memoryDrafts.filter((d) => d.owner_employee_id === this.ws().persona_id);
  }
  async submitMemoryDraft(draft_id: string, cmd: Command): Promise<MemoryDraft> {
    await this.gate("command");
    const d = this.ws().memoryDrafts.find((x) => x.draft_id === draft_id && x.owner_employee_id === this.ws().persona_id);
    if (!d) this.fail("NOT_FOUND", "Draft not found.");
    this.checkRevision(cmd.expected_revision, d.revision);
    if (d.requested_audience === "PRIVATE") this.fail("GUARD_FAILED", "Private notes stay with you. Choose a team or organization audience to submit for review.");
    d.status = "PENDING_REVIEW";
    d.revision += 1;
    for (const p of this.pack().personas.filter((x) => x.grants.includes("knowledge.review") && x.employee_id !== d.owner_employee_id)) {
      this.notify(p.employee_id, "REVIEW_REQUESTED", "A knowledge note is waiting for review", "/reviews/");
    }
    this.emit();
    return d;
  }
  async deleteMemoryDraft(draft_id: string, cmd: Command): Promise<void> {
    await this.gate("command");
    void cmd;
    const ws = this.ws();
    ws.memoryDrafts = ws.memoryDrafts.filter((d) => !(d.draft_id === draft_id && d.owner_employee_id === ws.persona_id && d.status === "DRAFT"));
    this.emit();
  }

  // ---------------------------------------------------------------- curricula & sources (coordinator)
  // Local implementations of PROPOSED endpoints (see WorkWeaveClient). Nothing here uploads bytes,
  // parses documents, creates embeddings or writes PostgreSQL rows.
  private curricula() {
    const ws = this.ws();
    return (ws.curricula ??= { items: seedCurricula(ws.key, this.pack()), receipts: [] });
  }
  private requireCoordinator() {
    const who = this.pack().personas.filter((p) => p.grants.includes("curriculum.manage")).map((p) => `${p.first_name} ${p.last_name}`);
    this.require("curriculum.manage", `Curricula & sources is for onboarding coordinators.${who.length ? ` In this pack that's ${who.join(", ")}; switch persona to review it.` : ""}`);
  }
  private findCurriculum(id: string) {
    const c = this.curricula().items.find((x) => x.curriculum_id === id);
    if (!c) this.fail("NOT_FOUND", "This curriculum doesn't exist in this workspace. It may belong to a run you discarded.");
    return c;
  }
  private draftCommand(id: string, cmd: Command) {
    this.requireCoordinator();
    const c = this.findCurriculum(id);
    if (c.status !== "DRAFT") this.fail("GUARD_FAILED", "Published curricula are frozen. Create a draft revision to change sources or the learning path.");
    this.checkRevision(cmd.expected_revision, c.revision);
    return c;
  }
  private touch(c: Curriculum) {
    c.revision += 1;
    this.emit();
    return c;
  }
  private findSource(c: Curriculum, source_id: string) {
    const s = c.sources.find((x) => x.curriculum_source_id === source_id);
    if (!s) this.fail("NOT_FOUND", "This source isn't linked to the curriculum any more. It may have been rejected and removed.");
    return s;
  }
  async listCurricula(): Promise<CurriculaCatalog> {
    await this.gate("read");
    this.requireCoordinator();
    const st = this.curricula();
    return {
      curricula: st.items.map((c) => ({
        curriculum_id: c.curriculum_id,
        name: c.name,
        version: c.version,
        status: c.status,
        topic_count: c.topics.length,
        subtopic_count: c.topics.reduce((n, t) => n + t.subtopics.length, 0),
        source_count: c.sources.length,
        pending_review_count: c.sources.filter((s) => s.stage === "PENDING_REVIEW").length,
      })),
      receipts: st.receipts,
      sample_available: Boolean(SAMPLE_SOURCES[this.ws().key]),
    };
  }
  async getCurriculum(curriculum_id: string): Promise<Curriculum> {
    await this.gate("read");
    this.requireCoordinator();
    return this.findCurriculum(curriculum_id);
  }
  async createCurriculum(input: { name: string; version: string; description?: string }): Promise<Curriculum> {
    await this.gate("command");
    this.requireCoordinator();
    const name = input.name.trim();
    const version = input.version.trim();
    if (!name || !version) this.fail("MALFORMED_INPUT", "Add a curriculum name and version.");
    const st = this.curricula();
    if (st.items.some((c) => c.name.toLowerCase() === name.toLowerCase() && c.version === version)) this.fail("GUARD_FAILED", `${name} v${version} already exists. Open it, or choose another version.`);
    const c: Curriculum = { curriculum_id: this.next("curr"), name, version, status: "DRAFT", description: input.description?.trim() || undefined, revision: 1, topics: [], sources: [], seeded: false };
    st.items.push(c);
    this.emit();
    return c;
  }
  // API-only path editing (ADR-050): the preview edits paths with its own outline dialog instead.
  async removeCurriculumSource(): Promise<never> {
    this.fail("CAPABILITY_UNAVAILABLE", "Removing a linked source is part of the connected demo, not this preview.");
  }
  async setSubtopicIncluded(): Promise<never> {
    this.fail("CAPABILITY_UNAVAILABLE", "Use Edit learning path in this preview.");
  }
  async moveCurriculumTopic(): Promise<never> {
    this.fail("CAPABILITY_UNAVAILABLE", "Use Edit learning path in this preview.");
  }
  async createCurriculumRevision(curriculum_id: string): Promise<Curriculum> {
    await this.gate("command");
    this.requireCoordinator();
    const base = this.findCurriculum(curriculum_id);
    if (base.status !== "PUBLISHED") this.fail("GUARD_FAILED", "Only a published curriculum needs a draft revision; this one is already editable.");
    const st = this.curricula();
    const existing = st.items.find((c) => c.derived_from_curriculum_id === base.curriculum_id && c.status === "DRAFT");
    if (existing) return existing;
    const [major, minorStart] = base.version.split(".").map((n) => Number(n) || 0) as [number, number];
    let minor = minorStart;
    let version = `${major}.${minor + 1}`;
    while (st.items.some((c) => c.name === base.name && c.version === version)) {
      minor += 1;
      version = `${major}.${minor + 1}`;
    }
    const idMap = new Map<string, string>();
    const topics = base.topics.map((t) => ({
      ...t,
      topic_id: this.next("topic"),
      subtopics: t.subtopics.map((s) => {
        const nid = this.next("sub");
        idMap.set(s.subtopic_id, nid);
        return { ...s, subtopic_id: nid };
      }),
    }));
    // Approved exact versions may support several curricula, so they stay linked with remapped targets.
    const sources = base.sources
      .filter((s) => s.stage === "APPROVED")
      .map((s) => ({
        ...s,
        curriculum_source_id: this.next("cs"),
        sections: s.sections.map((x) => ({
          ...x,
          section_id: this.next("sec"),
          mapping: x.mapping.kind === "SUBTOPIC" ? (idMap.has(x.mapping.subtopic_id) ? { kind: "SUBTOPIC" as const, subtopic_id: idMap.get(x.mapping.subtopic_id)! } : { kind: "UNRESOLVED" as const }) : x.mapping,
        })),
      }));
    const c: Curriculum = { curriculum_id: this.next("curr"), name: base.name, version, status: "DRAFT", description: base.description, revision: 1, topics, sources, derived_from_curriculum_id: base.curriculum_id, seeded: false };
    st.items.push(c);
    this.emit();
    return c;
  }
  async stageCurriculumSource(curriculum_id: string, input: StageSourceInput, cmd: Command): Promise<Curriculum> {
    await this.gate("command");
    const c = this.draftCommand(curriculum_id, cmd);
    const sample = SAMPLE_SOURCES[this.ws().key];
    if (input.use_sample && !sample) this.fail("GUARD_FAILED", "This company pack has no synthetic sample source.");
    const meta = input.use_sample && sample ? { document_code: sample.document_code, title: sample.title, version: sample.version } : { document_code: input.document_code.trim(), title: input.title.trim(), version: input.version.trim() };
    if (!meta.document_code || !meta.title || !meta.version) this.fail("MALFORMED_INPUT", "Add the document code, title and exact version.");
    if (!input.use_sample) {
      if (!input.file) this.fail("MALFORMED_INPUT", "Select a file, or use the synthetic sample.");
      if (!/\.(md|markdown|txt)$/i.test(input.file.name)) this.fail("MALFORMED_INPUT", "This preview accepts Markdown or plain-text filenames only. PDF extraction isn't connected.");
      if (input.file.size > 10 * 1024 * 1024) this.fail("MALFORMED_INPUT", "That file is over the 10 MB upload limit.");
    }
    if (c.sources.some((s) => s.document_code.toLowerCase() === meta.document_code.toLowerCase() && s.version === meta.version))
      this.fail("GUARD_FAILED", `${meta.document_code} v${meta.version} is already linked to this curriculum.`);
    c.sources.push({
      curriculum_source_id: this.next("cs"),
      document_id: this.next("doc"),
      document_version_id: this.next("docv"),
      ...meta,
      file_label: input.use_sample && sample ? sample.file_label : input.file!.name,
      origin: input.use_sample ? "SYNTHETIC_FIXTURE" : "FILENAME_ONLY",
      stage: "STAGED",
      sections: [],
      mappings_confirmed: false,
      revision: 1,
    });
    return this.touch(c);
  }
  async parseCurriculumSource(curriculum_id: string, source_id: string, cmd: Command): Promise<Curriculum> {
    await this.gate("command");
    const c = this.draftCommand(curriculum_id, cmd);
    const s = this.findSource(c, source_id);
    if (s.stage !== "STAGED") this.fail("GUARD_FAILED", "This source already has an outline.");
    const sample = SAMPLE_SOURCES[this.ws().key];
    if (s.origin !== "SYNTHETIC_FIXTURE" || !sample)
      this.fail("CAPABILITY_UNAVAILABLE", `Document parsing isn't connected in this preview. Nothing was read from ${s.file_label}; only the synthetic sample has a recorded outline.`);
    const subs = c.topics.flatMap((t) => t.subtopics);
    s.sections = sample.sections.map((x) => {
      const match = x.kind === "INSTRUCTION" ? subs.find((st) => headingKey(st.name) === headingKey(x.subtopic_heading)) : undefined;
      return {
        ...x,
        section_id: this.next("sec"),
        suggested_subtopic_id: match?.subtopic_id,
        mapping: match ? { kind: "SUBTOPIC" as const, subtopic_id: match.subtopic_id } : x.kind === "REFERENCE" ? { kind: "REFERENCE_ONLY" as const } : { kind: "UNRESOLVED" as const },
      };
    });
    s.stage = "PARSED";
    s.revision += 1;
    return this.touch(c);
  }
  async saveLearningPath(curriculum_id: string, topics: CurriculumTopicDef[], cmd: Command): Promise<Curriculum> {
    await this.gate("command");
    const c = this.draftCommand(curriculum_id, cmd);
    if (topics.some((t) => !t.name.trim() || t.subtopics.some((s) => !s.name.trim()))) this.fail("MALFORMED_INPUT", "Every topic and subtopic needs a name.");
    const keep = new Set(topics.flatMap((t) => t.subtopics.map((s) => s.subtopic_id)));
    const locked = c.sources.filter((src) => src.stage === "PENDING_REVIEW" || src.stage === "APPROVED").flatMap((src) => src.sections).filter((x) => x.mapping.kind === "SUBTOPIC" && !keep.has(x.mapping.subtopic_id));
    if (locked.length) this.fail("GUARD_FAILED", `A source in review or approved maps to a subtopic you removed (${locked.map((x) => x.subtopic_heading).join(", ")}). Keep the subtopic, or reject that source first.`);
    c.topics = topics.map((t, ti) => ({
      topic_id: t.topic_id.startsWith("new-") ? this.next("topic") : t.topic_id,
      name: t.name.trim(),
      order_index: ti + 1,
      subtopics: t.subtopics.map((s, si) => ({ ...s, subtopic_id: s.subtopic_id.startsWith("new-") ? this.next("sub") : s.subtopic_id, name: s.name.trim(), order_index: si + 1 })),
    }));
    // Proposed paths from an outline arrive with "new-h2:1/h3:1"-style IDs: link them to their sections.
    const byKey = new Map<string, string>();
    topics.forEach((t, ti) => t.subtopics.forEach((s, si) => s.subtopic_id.startsWith("new-") && byKey.set(s.subtopic_id.slice(4), c.topics[ti]!.subtopics[si]!.subtopic_id)));
    for (const src of c.sources) {
      if (src.stage !== "PARSED" && src.stage !== "MAPPED") continue;
      let changed = false;
      for (const x of src.sections) {
        const linked = byKey.get(x.section_key);
        if (linked) {
          x.mapping = { kind: "SUBTOPIC", subtopic_id: linked };
          x.suggested_subtopic_id = linked;
          changed = true;
        } else if (x.mapping.kind === "SUBTOPIC" && !keep.has(x.mapping.subtopic_id)) {
          x.mapping = { kind: "UNRESOLVED" };
          changed = true;
        }
      }
      if (changed) {
        src.stage = "PARSED";
        src.mappings_confirmed = false;
        src.revision += 1;
      }
    }
    return this.touch(c);
  }
  async saveSourceMappings(curriculum_id: string, source_id: string, mappings: Record<string, SectionMapping>, confirm: boolean, cmd: Command): Promise<Curriculum> {
    await this.gate("command");
    const c = this.draftCommand(curriculum_id, cmd);
    const s = this.findSource(c, source_id);
    if (s.stage !== "PARSED" && s.stage !== "MAPPED") this.fail("GUARD_FAILED", s.stage === "STAGED" ? "Parse the source before mapping it." : "Mappings are locked while this exact version is in review or approved.");
    const subs = new Set(c.topics.flatMap((t) => t.subtopics.map((x) => x.subtopic_id)));
    for (const [sid, m] of Object.entries(mappings)) {
      const sec = s.sections.find((x) => x.section_id === sid);
      if (!sec) this.fail("NOT_FOUND", "A section in this mapping no longer exists.");
      if (m.kind === "SUBTOPIC" && !subs.has(m.subtopic_id)) this.fail("MALFORMED_INPUT", "A mapping points to a subtopic that isn't in this curriculum.");
      sec.mapping = m;
    }
    if (confirm && !subs.size) this.fail("GUARD_FAILED", "Add a learning path first, so sections have subtopics to map to.");
    s.mappings_confirmed = confirm;
    s.stage = confirm ? "MAPPED" : "PARSED";
    s.revision += 1;
    return this.touch(c);
  }
  async saveObjective(curriculum_id: string, subtopic_id: string, objective: CurriculumObjective, cmd: Command): Promise<Curriculum> {
    await this.gate("command");
    const c = this.draftCommand(curriculum_id, cmd);
    const sub = c.topics.flatMap((t) => t.subtopics).find((s) => s.subtopic_id === subtopic_id);
    if (!sub) this.fail("NOT_FOUND", "Subtopic not found in this curriculum.");
    if (!objective.description.trim() || !objective.assessment_criteria.trim()) this.fail("MALFORMED_INPUT", "Add both the learning objective and the assessment criteria.");
    sub.objective = { description: objective.description.trim(), assessment_criteria: objective.assessment_criteria.trim() };
    return this.touch(c);
  }
  async submitSourceForReview(curriculum_id: string, source_id: string, cmd: Command): Promise<Curriculum> {
    await this.gate("command");
    const c = this.draftCommand(curriculum_id, cmd);
    const s = this.findSource(c, source_id);
    if (s.stage !== "MAPPED" || !s.mappings_confirmed) this.fail("GUARD_FAILED", "Confirm the section mappings before submitting this version for review.");
    s.stage = "PENDING_REVIEW";
    s.submitted_by = this.name(this.ws().persona_id);
    s.revision += 1;
    for (const p of this.pack().personas.filter((x) => x.grants.includes("knowledge.review")))
      this.notify(p.employee_id, "SOURCE_REVIEW", `${s.document_code} v${s.version} is waiting for source review`, `/curricula/detail/?id=${encodeURIComponent(c.curriculum_id)}`);
    return this.touch(c);
  }
  async reviewSourceVersion(curriculum_id: string, source_id: string, decision: "APPROVED" | "REJECTED", reason: string, cmd: Command): Promise<Curriculum> {
    await this.gate("command");
    this.require("knowledge.review", "Only an authorized knowledge reviewer can approve or reject a source version.");
    const c = this.findCurriculum(curriculum_id);
    this.checkRevision(cmd.expected_revision, c.revision);
    const s = this.findSource(c, source_id);
    if (s.stage !== "PENDING_REVIEW") this.fail("GUARD_FAILED", "This version isn't waiting for review.");
    if (decision === "REJECTED" && !reason.trim()) this.fail("MALFORMED_INPUT", "Add a short reason so the coordinator knows what to fix. Don't paste document content.");
    const reviewer = this.name(this.ws().persona_id);
    this.curricula().receipts.unshift({ receipt_id: this.next("rcpt"), curriculum_id, document_code: s.document_code, version: s.version, decision, reason: reason.trim() || undefined, reviewer, label: `Just now, ${c.name} v${c.version}` });
    if (decision === "APPROVED") {
      s.stage = "APPROVED";
      s.approved_by = reviewer;
      s.revision += 1;
    } else {
      // Rejected draft uploads are purged; only the non-content receipt above remains (blueprint/04).
      c.sources = c.sources.filter((x) => x.curriculum_source_id !== source_id);
    }
    return this.touch(c);
  }
  async retryIngestion(): Promise<Curriculum> {
    await this.gate("command");
    this.fail("CAPABILITY_UNAVAILABLE", "Ingestion runs on the WorkWeave backend; this preview doesn't parse or embed documents.");
  }
  async publishCurriculum(curriculum_id: string, cmd: Command): Promise<Curriculum> {
    await this.gate("command");
    const c = this.draftCommand(curriculum_id, cmd);
    const failing = curriculumReadiness(c).filter((r) => !r.passed);
    if (failing.length) this.fail("GUARD_FAILED", `Not ready to publish: ${failing.map((r) => r.label.toLowerCase()).join("; ")}.`);
    c.status = "PUBLISHED";
    c.published_label = "Just now, in this browser tab";
    return this.touch(c);
  }

  // ---------------------------------------------------------------- handover
  private isSourceLead() {
    const h = this.ws().handover;
    return h.occurrences.find((o) => o.shift_instance_id === h.source_id)?.lead_employee_id === this.ws().persona_id && this.has("handover.publish");
  }
  async getHandoverWorkspace(): Promise<HandoverWorkspace> {
    await this.gate("read");
    return this.handoverView();
  }
  /** Template version in use: the lead's latest version, else the pack's. */
  private template() {
    const fx = this.pack().handover;
    return this.ws().handover.template ?? { version: fx.template_version, sections: fx.sections };
  }
  private handoverView(): HandoverWorkspace {
    const ws = this.ws();
    const h = ws.handover;
    const fx = this.pack().handover;
    const lead = this.isSourceLead();
    const member = h.occurrences.some((o) => o.member_ids.includes(ws.persona_id) || o.lead_employee_id === ws.persona_id);
    if (!lead && !member) this.fail("FORBIDDEN", "Shift Handover is only available to members of these shift occurrences.");
    const audience = lead ? "LEAD" : "INCOMING";
    const source = h.occurrences.find((o) => o.shift_instance_id === h.source_id)!;
    const target = h.occurrences.find((o) => o.shift_instance_id === h.target_id)!;
    const copilot = (h.copilot[ws.persona_id] ??= [
      { message_id: this.next("cp"), sender: "AI", text: lead ? fx.copilot_opening : "You can ask about the published handover. Lead drafts and suggestions aren't visible to you.", citations: [], provenance: "SCRIPTED_FIXTURE" },
    ]);
    return {
      handover_id: h.handover_id,
      revision: h.revision,
      status: h.status,
      template_name: fx.template_name,
      template_version: this.template().version,
      sections: this.template().sections,
      // Lead-only drafts and suggestions are withheld from incoming members (15-handover-user-flow).
      draft_sections: lead ? h.draft_sections : [],
      source,
      target,
      occurrences: h.occurrences,
      items: h.items,
      suggestions: lead ? h.suggestions : [],
      publications: h.publications,
      cycles: h.cycles,
      item_events: h.item_events,
      last_change_section_id: lead ? this.lastChangeSection() : undefined,
      can_configure_template: lead,
      script_prompts: fx.copilot_steps.filter((s) => s.audience === audience).map((s) => s.prompt),
      copilot,
    };
  }
  private lastChangeSection() {
    const h = this.ws().handover;
    const u = h.changes[h.changes.length - 1];
    if (!u) return undefined;
    return u.kind === "SECTION" ? u.section_id : (h.items.find((i) => i.handover_item_id === u.item.handover_item_id)?.section_id ?? u.item.section_id);
  }
  private leadCommand(cmd: Command) {
    if (!this.isSourceLead()) this.fail("FORBIDDEN", "Only the authorized lead of the source shift can change or publish this handover.");
    const h = this.ws().handover;
    this.checkRevision(cmd.expected_revision, h.revision);
    if (h.status === "PUBLISHED") h.status = "DRAFT"; // further edits start a new draft revision
    return h;
  }
  async editDraftSection(section_id: string, content: string, declaration: { kind?: "UNKNOWN_WITH_FOLLOW_UP" | "NOT_APPLICABLE"; reason?: string }, cmd: Command): Promise<HandoverWorkspace> {
    await this.gate("command");
    const h = this.leadCommand(cmd);
    const sec = h.draft_sections.find((s) => s.section_id === section_id);
    if (!sec) this.fail("NOT_FOUND", "Section not found in this template version.");
    if (declaration.kind && !declaration.reason?.trim()) this.fail("MALFORMED_INPUT", "Add a reason or follow-up for the declaration.");
    const name = this.template().sections.find((s) => s.section_id === section_id)?.name ?? "section";
    h.changes.push({ kind: "SECTION", section_id, previous: { ...sec }, label: `Edit to ${name}` });
    sec.content = content;
    sec.declaration = declaration.kind;
    sec.declaration_reason = declaration.reason;
    h.revision += 1;
    this.emit();
    return this.handoverView();
  }
  async acceptSuggestion(id: string, mode: "APPLY" | "REPORT_ONLY" | "VALIDATE_COMPLETION", cmd: Command, note?: string): Promise<HandoverWorkspace> {
    await this.gate("command");
    const h = this.leadCommand(cmd);
    const edited = note?.trim();
    const sg = h.suggestions.find((s) => s.suggestion_id === id);
    if (!sg) this.fail("NOT_FOUND", "Suggestion not found.");
    if (sg.status !== "PENDING") this.fail("GUARD_FAILED", "This suggestion has already been reviewed.");
    const hi = h.items.find((i) => i.handover_item_id === sg.handover_item_id);
    if (sg.suggestion_type === "STATUS_UPDATE" && mode === "VALIDATE_COMPLETION") {
      const ev = this.ws().events.find((e) => e.work_event_id === sg.report_event_id);
      if (!hi?.work_item_id) this.fail("GUARD_FAILED", "Only linked work can be validated here.");
      if (edited) {
        h.changes.push({ kind: "ITEM", item: { ...hi }, suggestion_id: id, label: `Activity note on ${hi.display_id}` });
        hi.description = edited;
      }
      this.completeWork(hi.work_item_id, ev);
      sg.status = "ACCEPTED";
    } else if (sg.suggestion_type === "STATUS_UPDATE" && mode === "REPORT_ONLY") {
      if (!hi) this.fail("NOT_FOUND", "Item not found.");
      h.changes.push({ kind: "ITEM", item: { ...hi }, suggestion_id: id, label: `Report note on ${hi.display_id}` });
      hi.description = edited || `${hi.description} Completion reported (not yet validated).`;
      sg.status = "ACCEPTED";
    } else if (sg.suggestion_type === "MISSING_ITEM") {
      if (hi) {
        h.changes.push({ kind: "ITEM", item: { ...hi }, suggestion_id: id, label: `Move ${hi.display_id} to Scheduled Activities` });
        hi.section_id = "sec-scheduled";
        if (edited) hi.description = edited;
      } else {
        const item: HandoverItem = { handover_item_id: this.next("hi"), display_id: `HI-${this.ws().seq}`, title: sg.title, description: edited || sg.proposed, originating_shift_instance_id: h.source_id, work_status: "ACTIVE", acknowledgement_status: "NOT_REQUIRED", section_id: "sec-scheduled", evidence_type: sg.evidence_type, source_label: sg.source_label };
        h.items.push(item);
        h.changes.push({ kind: "ITEM", item, suggestion_id: id, created: true, label: `Add ${item.display_id}` });
      }
      sg.status = "ACCEPTED";
    } else {
      if (!hi) this.fail("NOT_FOUND", "Item not found.");
      h.changes.push({ kind: "ITEM", item: { ...hi }, suggestion_id: id, label: `Update ${hi.display_id}` });
      hi.description = edited || sg.proposed;
      sg.status = "ACCEPTED";
    }
    h.revision += 1;
    this.emit();
    return this.handoverView();
  }
  async ignoreSuggestion(id: string, cmd: Command): Promise<HandoverWorkspace> {
    await this.gate("command");
    const h = this.leadCommand(cmd);
    const sg = h.suggestions.find((s) => s.suggestion_id === id);
    if (!sg || sg.status !== "PENDING") this.fail("GUARD_FAILED", "This suggestion has already been reviewed.");
    sg.status = "IGNORED";
    h.revision += 1;
    this.emit();
    return this.handoverView();
  }
  async createTemplateVersion(sections: TemplateSectionInput[], cmd: Command): Promise<HandoverWorkspace> {
    await this.gate("command");
    const h = this.leadCommand(cmd);
    const current = this.template();
    const names = sections.map((s) => s.name.trim());
    if (names.some((n) => !n)) this.fail("MALFORMED_INPUT", "Every section needs a name.");
    if (new Set(names.map((n) => n.toLowerCase())).size !== names.length) this.fail("MALFORMED_INPUT", "Section names must be unique.");
    // Sections are never removed: older snapshots keep resolving their section names.
    if (current.sections.some((c) => !sections.some((s) => s.section_id === c.section_id))) this.fail("GUARD_FAILED", "Existing sections can't be removed in this preview; mark them optional instead.");
    if (!sections.some((s) => s.is_required)) this.fail("GUARD_FAILED", "Keep at least one required section.");
    const next: TemplateSection[] = sections.map((s, i) => ({ section_id: s.section_id ?? this.next("sec"), name: s.name.trim(), order_index: i + 1, is_required: s.is_required }));
    next.forEach((s) => {
      if (!h.draft_sections.some((d) => d.section_id === s.section_id)) h.draft_sections.push({ section_id: s.section_id, content: "" });
    });
    h.template = { version: String(Number(current.version) + 1), sections: next };
    h.revision += 1;
    this.emit();
    return this.handoverView();
  }
  async publishHandover(cmd: Command): Promise<HandoverWorkspace> {
    await this.gate("command");
    if (!this.isSourceLead()) this.fail("FORBIDDEN", "Only the authorized lead of the source shift can publish. Members can't publish, and no second reviewer is involved.");
    const h = this.ws().handover;
    if (h.status === "PUBLISHED") return this.handoverView(); // idempotent replay
    this.checkRevision(cmd.expected_revision, h.revision);
    const missing = missingRequiredSections({ sections: this.template().sections, draft_sections: h.draft_sections });
    if (missing.length) this.fail("GUARD_FAILED", `Required sections need content or an explicit unknown/not-applicable declaration: ${missing.join(", ")}.`);
    const number = (h.publications[h.publications.length - 1]?.publication_number ?? 0) + 1;
    h.publications.push({
      publication_id: this.next("pub"),
      publication_number: number,
      source_shift_instance_id: h.source_id,
      target_shift_instance_id: h.target_id,
      template_version: this.template().version,
      sections: h.draft_sections.filter((d) => this.template().sections.some((s) => s.section_id === d.section_id)).map((s) => ({ ...s })),
      entries: h.items.map((i) => ({ handover_item_id: i.handover_item_id, display_id: i.display_id, title: i.title, section_id: i.section_id, snapshot_work_status: i.work_status, snapshot_acknowledgement_status: i.acknowledgement_status, snapshot_description: i.description })),
      published_by: this.ws().persona_id,
      published_label: `Just now, ${this.occName(h.source_id)} shift`,
      receipts: [],
    });
    h.items.forEach((i) => h.item_events.push({ event_id: this.next("hie"), handover_item_id: i.handover_item_id, label: `Included in publication #${number}`, shift_name: this.occName(h.source_id) }));
    h.status = "PUBLISHED";
    h.changes = [];
    h.revision += 1;
    const target = h.occurrences.find((o) => o.shift_instance_id === h.target_id);
    target?.member_ids.forEach((m) => this.notify(m, "HANDOVER_PUBLISHED", `Handover publication #${number} is ready`, "/handover/"));
    this.emit();
    return this.handoverView();
  }
  async confirmHandoverReceipt(publication_id: string, cmd: Command): Promise<HandoverWorkspace> {
    await this.gate("command");
    void cmd;
    const ws = this.ws();
    const h = ws.handover;
    const pub = h.publications.find((p) => p.publication_id === publication_id);
    if (!pub) this.fail("NOT_FOUND", "Publication not found.");
    const target = h.occurrences.find((o) => o.shift_instance_id === pub.target_shift_instance_id);
    if (!target || target.lead_employee_id !== ws.persona_id) this.fail("FORBIDDEN", "Only the receiving shift's lead confirms receipt.");
    if (!pub.receipts.some((r) => r.employee_id === ws.persona_id)) pub.receipts.push({ employee_id: ws.persona_id, received_label: "Just now" });
    this.emit();
    return this.handoverView();
  }
  async acknowledgeCompletion(cycle_id: string, decision: "ACKNOWLEDGE" | "DISPUTE", comment: string, cmd: Command): Promise<HandoverWorkspace> {
    await this.gate("command");
    void cmd;
    const ws = this.ws();
    const h = ws.handover;
    const cycle = h.cycles.find((c) => c.completion_cycle_id === cycle_id);
    if (!cycle) this.fail("NOT_FOUND", "Completion cycle not found.");
    const hi = h.items.find((i) => i.handover_item_id === cycle.handover_item_id)!;
    const originLead = h.occurrences.find((o) => o.shift_instance_id === cycle.requested_from_shift_instance_id)?.lead_employee_id;
    if (originLead !== ws.persona_id) this.fail("FORBIDDEN", "Only the originating shift's lead can acknowledge or dispute this completion.");
    if (cycle.status !== "PENDING" || hi.completion_cycle_id !== cycle_id) this.fail("GUARD_FAILED", "This response is for an older completion cycle, so it can't close the item's current state.");
    if (decision === "DISPUTE" && !comment.trim()) this.fail("MALFORMED_INPUT", "Explain what's disputed so the current shift can follow up.");
    cycle.comment = comment || undefined;
    if (decision === "ACKNOWLEDGE") {
      cycle.status = "ACKNOWLEDGED";
      hi.acknowledgement_status = "ACKNOWLEDGED";
      hi.work_status = "CLOSED";
      const wi = ws.items.find((i) => i.work_item_id === hi.work_item_id);
      if (wi) wi.status = "CLOSED";
      h.item_events.push({ event_id: this.next("hie"), handover_item_id: hi.handover_item_id, label: "Source acknowledged; item closed", shift_name: this.occName(cycle.requested_from_shift_instance_id) });
    } else {
      cycle.status = "DISPUTED";
      hi.acknowledgement_status = "DISPUTED";
      hi.work_status = "IN_PROGRESS";
      const wi = ws.items.find((i) => i.work_item_id === hi.work_item_id);
      if (wi) {
        wi.status = "IN_PROGRESS";
        wi.revision += 1;
        ws.events.push({ work_event_id: this.next("ev"), work_item_id: wi.work_item_id, employee_id: ws.persona_id, event_type: "REOPENED", description: `Completion disputed: ${comment}`, evidence_type: "REPORTED", observed_label: "Just now" });
      }
      h.item_events.push({ event_id: this.next("hie"), handover_item_id: hi.handover_item_id, label: `REOPENED: completion disputed (${comment})`, shift_name: this.occName(cycle.requested_from_shift_instance_id) });
    }
    this.emit();
    return this.handoverView();
  }
  async confirmItemCompletion(handover_item_id: string, cmd: Command): Promise<HandoverWorkspace> {
    await this.gate("command");
    const h = this.leadCommand(cmd);
    const hi = h.items.find((i) => i.handover_item_id === handover_item_id);
    if (!hi) this.fail("NOT_FOUND", "Item not found.");
    if (hi.work_status === "COMPLETED" || hi.work_status === "CLOSED") this.fail("GUARD_FAILED", "This item is already complete.");
    if (hi.work_item_id) {
      const wi = this.ws().items.find((i) => i.work_item_id === hi.work_item_id)!;
      wi.status = "COMPLETED";
      wi.revision += 1;
    }
    this.openCycle(h, hi);
    h.revision += 1;
    this.emit();
    return this.handoverView();
  }
  async askHandoverCopilot(input: TurnInput): Promise<HandoverWorkspace> {
    await this.gate("command");
    const ws = this.ws();
    const view = this.handoverView();
    const thread = ws.handover.copilot[ws.persona_id]!;
    thread.push({ message_id: this.next("cp"), sender: "EMPLOYEE", text: input.text, citations: [], provenance: "EMPLOYEE_INPUT" });
    const step = this.pack().handover.copilot_steps.find((s) => s.prompt.prompt_id === input.preview_prompt_id && view.script_prompts.some((p) => p.prompt_id === s.prompt.prompt_id));
    thread.push(step ? { message_id: this.next("cp"), sender: "AI", text: step.reply, citations: this.citations(step.excerpt_keys), provenance: "SCRIPTED_FIXTURE" } : { message_id: this.next("cp"), sender: "SYSTEM", text: NOT_INTERPRETED, citations: [], provenance: "PREVIEW_SYSTEM" });
    this.emit();
    return this.handoverView();
  }

  // ---------------------------------------------------------------- exit kt
  private ktRole(c: ExitKtCase): "SUBJECT" | "REVIEWER" | "SUCCESSOR" | "NONE" {
    const me = this.ws().persona_id;
    if (c.employee_id === me) return "SUBJECT";
    if (c.reviewer_employee_id === me || this.has("responsibility.confirm")) return "REVIEWER";
    if (c.package.successor_employee_id === me || c.transfers.some((t) => (t.final_owner_employee_id ?? t.recommended_owner_employee_id) === me)) return "SUCCESSOR";
    return "NONE";
  }
  private kt(): ExitKtCase {
    const c = this.ws().exitKt;
    if (this.ktRole(c) === "NONE") this.fail("FORBIDDEN", "You aren't part of an Exit KT case in this workspace.");
    return c;
  }
  private ktView(c: ExitKtCase): ExitKtCase {
    const role = this.ktRole(c);
    if (role === "SUCCESSOR") {
      // Successors see the approved package and Q&A only; interviews, drafts and findings stay private.
      return { ...c, interviews: [], artifacts: [], findings: [], knowledge_items: [], successor_prompts: this.pack().exit_kt.successor_steps.map((s) => s.prompt) };
    }
    return { ...c, interviews: role === "SUBJECT" ? c.interviews.map((i) => ({ ...i, script_prompts: this.interviewPrompts(i.interview_id) })) : [], successor_prompts: [] };
  }
  private interviewPrompts(interview_id: string): ScriptPrompt[] {
    const i = this.ws().exitKt.interviews.find((x) => x.interview_id === interview_id);
    if (!i || i.status === "COMPLETED") return [];
    const used = new Set(i.messages.map((m) => m.message_id));
    void used;
    return this.pack().exit_kt.interview_steps.filter((s) => !i.messages.some((m) => m.content === s.prompt.text)).slice(0, 1).map((s) => s.prompt);
  }
  private ktCommand(roles: ("SUBJECT" | "REVIEWER" | "SUCCESSOR")[], message: string, cmd?: Command) {
    const c = this.kt();
    const role = this.ktRole(c);
    if (!roles.includes(role as "SUBJECT")) this.fail("FORBIDDEN", message);
    if (cmd) this.checkRevision(cmd.expected_revision, c.revision);
    return c;
  }
  private bump(c: ExitKtCase) {
    c.revision += 1;
    this.emit();
    return this.ktView(c);
  }
  async getExitKtCase(): Promise<ExitKtCase | null> {
    await this.gate("read");
    const c = this.ws().exitKt;
    return this.ktRole(c) === "NONE" ? null : this.ktView(c);
  }
  async createExitKtCase(input: { employee_id: string; case_kind: CaseKind; final_working_date?: string; reviewer_employee_id: string }, cmd: Command): Promise<ExitKtCase> {
    await this.gate("command");
    void cmd;
    if (!this.has("responsibility.confirm") && input.employee_id !== this.ws().persona_id) this.fail("FORBIDDEN", "Only the employee or an authorized manager can open a case.");
    if (input.case_kind === "DEPARTURE" && !input.final_working_date) this.fail("MALFORMED_INPUT", "A departure case needs a final working date.");
    if (input.reviewer_employee_id === input.employee_id) this.fail("MALFORMED_INPUT", "The reviewer can't be the employee in the case.");
    const c: ExitKtCase = { ...JSON.parse(JSON.stringify(this.pack().exit_kt.case)), exit_kt_case_id: this.next("kt"), employee_id: input.employee_id, case_kind: input.case_kind, final_working_date: input.case_kind === "DEPARTURE" ? input.final_working_date : undefined, reviewer_employee_id: input.reviewer_employee_id, status: "DISCOVERY", knowledge_items: [], findings: [], interviews: [], artifacts: [], responsibilities: [], transfers: [], checklist: [], revision: 1 };
    this.ws().extraCases.push(c);
    this.emit();
    return c;
  }
  listExtraCases(): ExitKtCase[] {
    try {
      return this.ws().extraCases;
    } catch {
      return [];
    }
  }
  async addKnowledgeItem(title: string, description: string, cmd: Command): Promise<ExitKtCase> {
    await this.gate("command");
    const c = this.ktCommand(["SUBJECT", "REVIEWER"], "Only the employee or reviewer can add knowledge areas.", cmd);
    if (!title.trim()) this.fail("MALFORMED_INPUT", "Give the knowledge area a title.");
    c.knowledge_items.push({ kt_item_id: this.next("kti"), title, description, documentation_status: "MISSING", kt_status: "INTERVIEW_REQUIRED", risk_level: "MEDIUM", origin: "MANUAL" });
    return this.bump(c);
  }
  async linkExistingKnowledge(kt_item_id: string, cmd: Command): Promise<ExitKtCase> {
    await this.gate("command");
    const c = this.ktCommand(["SUBJECT", "REVIEWER"], "Only the employee or reviewer can verify existing knowledge.", cmd);
    const it = c.knowledge_items.find((k) => k.kt_item_id === kt_item_id);
    if (!it || it.documentation_status !== "DOCUMENTED" || !it.linked_source) this.fail("GUARD_FAILED", "Only an area with an approved current source can skip the interview.");
    it.kt_status = "COMPLETE";
    return this.bump(c);
  }
  async reviewFinding(finding_id: string, decision: "CONFIRM" | "DISMISS" | "RESOLVE", reason: string, cmd: Command): Promise<ExitKtCase> {
    await this.gate("command");
    const c = this.ktCommand(["SUBJECT", "REVIEWER"], "Only the employee or reviewer can review findings.", cmd);
    const f = c.findings.find((x) => x.finding_id === finding_id);
    if (!f) this.fail("NOT_FOUND", "Finding not found.");
    if (!reason.trim()) this.fail("MALFORMED_INPUT", "Give a reason or evidence for this decision.");
    f.status = decision === "CONFIRM" ? "CONFIRMED" : decision === "DISMISS" ? "DISMISSED" : "RESOLVED";
    f.review_reason = reason;
    return this.bump(c);
  }
  async runDiscovery(): Promise<ExitKtCase> {
    await this.gate("command");
    this.fail("CAPABILITY_UNAVAILABLE", "Knowledge discovery (discover_kt_knowledge) isn't connected. The inventory and findings shown are seeded synthetic records; you can still add areas manually.");
  }
  async startInterview(kt_item_id: string, consent: boolean, cmd: Command): Promise<ExitKtCase> {
    await this.gate("command");
    const c = this.ktCommand(["SUBJECT"], "Only the employee can start their own targeted interview.", cmd);
    if (!consent) this.fail("MALFORMED_INPUT", "Accept the purpose, audience and retention notice to start.");
    const it = c.knowledge_items.find((k) => k.kt_item_id === kt_item_id);
    if (!it) this.fail("NOT_FOUND", "Knowledge area not found.");
    const existing = c.interviews.find((i) => i.kt_item_id === kt_item_id);
    if (existing) {
      existing.status = "IN_PROGRESS";
    } else {
      c.interviews.push({ interview_id: this.next("int"), kt_item_id, status: "IN_PROGRESS", consent_accepted: true, messages: [{ message_id: this.next("im"), sender_type: "AI", content: this.pack().exit_kt.interview_opening, provenance: "SCRIPTED_FIXTURE" }], script_prompts: [] });
    }
    if (it.kt_status === "INTERVIEW_REQUIRED" || it.kt_status === "NOT_STARTED") it.kt_status = "INTERVIEW_IN_PROGRESS";
    return this.bump(c);
  }
  async sendInterviewMessage(interview_id: string, input: TurnInput): Promise<ExitKtCase> {
    await this.gate("command");
    const c = this.ktCommand(["SUBJECT"], "Interview messages are private to the employee.");
    const i = c.interviews.find((x) => x.interview_id === interview_id);
    if (!i) this.fail("NOT_FOUND", "Interview not found.");
    if (!input.text.trim()) this.fail("MALFORMED_INPUT", "Write a response first.");
    i.messages.push({ message_id: this.next("im"), sender_type: "EMPLOYEE", content: input.text, provenance: "EMPLOYEE_INPUT" });
    const step = this.pack().exit_kt.interview_steps.find((s) => s.prompt.prompt_id === input.preview_prompt_id);
    i.messages.push(
      step
        ? { message_id: this.next("im"), sender_type: "AI", content: step.ai_follow_up, provenance: "SCRIPTED_FIXTURE" }
        : { message_id: this.next("im"), sender_type: "AI", content: "Saved privately. Follow-up questions need the interview engine, which isn't connected in this preview.", provenance: "PREVIEW_SYSTEM" },
    );
    return this.bump(c);
  }
  async draftArtifactFromInterview(interview_id: string): Promise<ExitKtCase> {
    await this.gate("command");
    void interview_id;
    this.fail("CAPABILITY_UNAVAILABLE", "Artifact drafting (draft_kt_artifact) isn't connected. Write the artifact manually; it stays private until you submit it.");
  }
  async createManualArtifact(kt_item_id: string, title: string, content: string, cmd: Command): Promise<ExitKtCase> {
    await this.gate("command");
    const c = this.ktCommand(["SUBJECT"], "Only the employee can author their KT artifact.", cmd);
    if (!title.trim() || !content.trim()) this.fail("MALFORMED_INPUT", "Add a title and content.");
    const it = c.knowledge_items.find((k) => k.kt_item_id === kt_item_id);
    if (!it) this.fail("NOT_FOUND", "Knowledge area not found.");
    const rid = this.next("artr");
    const aid = this.next("art");
    c.artifacts.push({ artifact_id: aid, kt_item_id, artifact_type: "PROCEDURE", title, current_revision_id: rid, revisions: [{ artifact_revision_id: rid, version: 1, content, status: "DRAFT", audience: "PRIVATE" }] });
    it.artifact_id = aid;
    it.kt_status = "DRAFT_CREATED";
    return this.bump(c);
  }
  private artifact(c: ExitKtCase, id: string) {
    const a = c.artifacts.find((x) => x.artifact_id === id);
    if (!a) this.fail("NOT_FOUND", "Artifact not found.");
    return a;
  }
  async editArtifact(artifact_id: string, content: string, cmd: Command): Promise<ExitKtCase> {
    await this.gate("command");
    const c = this.ktCommand(["SUBJECT"], "Only the employee can edit their draft.", cmd);
    const a = this.artifact(c, artifact_id);
    const cur = a.revisions.find((r) => r.artifact_revision_id === a.current_revision_id)!;
    if (cur.status === "DRAFT") {
      cur.content = content;
    } else {
      // Submitted/reviewed revisions are immutable; a change creates a new draft revision.
      const rid = this.next("artr");
      a.revisions.push({ artifact_revision_id: rid, version: cur.version + 1, content, status: "DRAFT", audience: cur.audience });
      a.current_revision_id = rid;
      const it = c.knowledge_items.find((k) => k.kt_item_id === a.kt_item_id);
      if (it) it.kt_status = "DRAFT_CREATED";
    }
    return this.bump(c);
  }
  async submitArtifact(artifact_id: string, rev: string, audience: "TEAM" | "ORGANIZATION", cmd: Command): Promise<ExitKtCase> {
    await this.gate("command");
    const c = this.ktCommand(["SUBJECT"], "Only the employee can submit their artifact.", cmd);
    const a = this.artifact(c, artifact_id);
    const cur = a.revisions.find((r) => r.artifact_revision_id === rev);
    if (!cur || a.current_revision_id !== rev || cur.status !== "DRAFT") this.fail("REVISION_CONFLICT", "Only the current draft revision can be submitted.");
    cur.status = "PENDING_REVIEW";
    cur.audience = audience;
    const it = c.knowledge_items.find((k) => k.kt_item_id === a.kt_item_id);
    if (it) it.kt_status = "PENDING_REVIEW";
    this.notify(c.reviewer_employee_id, "REVIEW_REQUESTED", `KT artifact "${a.title}" v${cur.version} is waiting for review`, "/reviews/");
    return this.bump(c);
  }
  async decideArtifact(artifact_id: string, rev: string, decision: "APPROVE" | "REQUEST_REVISION" | "REJECT", comment: string, cmd: Command): Promise<ExitKtCase> {
    await this.gate("command");
    const c = this.kt();
    this.require("knowledge.review", "Only an authorized knowledge reviewer can decide.");
    if (c.employee_id === this.ws().persona_id) this.fail("FORBIDDEN", "You can't approve your own shared knowledge.");
    this.checkRevision(cmd.expected_revision, c.revision);
    const a = this.artifact(c, artifact_id);
    const cur = a.revisions.find((r) => r.artifact_revision_id === rev);
    if (!cur || a.current_revision_id !== rev || cur.status !== "PENDING_REVIEW") this.fail("REVISION_CONFLICT", "This decision must target the exact submitted revision. The content has changed or was already reviewed.");
    if (decision !== "APPROVE" && !comment.trim()) this.fail("MALFORMED_INPUT", "Add a comment explaining what needs to change.");
    cur.status = decision === "APPROVE" ? "APPROVED" : decision === "REJECT" ? "REJECTED" : "REVISION_REQUIRED";
    cur.review_comment = comment || undefined;
    cur.reviewed_by = this.ws().persona_id;
    const it = c.knowledge_items.find((k) => k.kt_item_id === a.kt_item_id);
    if (it) it.kt_status = decision === "APPROVE" ? "PENDING_REVIEW" : "DRAFT_CREATED";
    this.notify(c.employee_id, "REVIEW_DECISION", `"${a.title}" v${cur.version}: ${cur.status.replace("_", " ").toLowerCase()}`, "/exit-kt/");
    return this.bump(c);
  }
  async retryKtIndexing(): Promise<ExitKtCase> {
    await this.gate("command");
    this.fail("CAPABILITY_UNAVAILABLE", "Indexing runs on the WorkWeave backend; this preview doesn't embed documents.");
  }
  async promoteArtifact(artifact_id: string, rev: string, cmd: Command): Promise<ExitKtCase> {
    await this.gate("command");
    const c = this.kt();
    this.require("knowledge.review", "Only an authorized knowledge reviewer can promote approved knowledge.");
    this.checkRevision(cmd.expected_revision, c.revision);
    const a = this.artifact(c, artifact_id);
    if (a.promotion) return this.ktView(c); // idempotent
    const cur = a.revisions.find((r) => r.artifact_revision_id === rev);
    if (!cur || cur.status !== "APPROVED" || a.current_revision_id !== rev) this.fail("GUARD_FAILED", "Only the current approved revision can be promoted.");
    const dv: DocumentVersion = { document_version_id: this.next("dv"), document_id: `kt-${artifact_id}`, document_code: `KT-${artifact_id.split("-").pop()}`, title: a.title, version: "1", approval_status: "APPROVED", temporal_status: "CURRENT", approved_by: this.name(this.ws().persona_id), effective_label: "New approved version (no existing SOP overwritten)", document_type: "KT_ARTIFACT", index_status: "PENDING" };
    this.ws().extraDocuments.push(dv);
    this.ws().extraTimeline.push({ entry_id: this.next("tl"), label: `${dv.document_code} v1 approved from Exit KT`, detail: `${a.title}. Semantic index pending; indexing isn't connected.`, kind: "KT_PROMOTION", temporal: "PENDING", evidence_type: "REPORTED", document_version_id: dv.document_version_id });
    a.promotion = { document_version_label: `${dv.document_code} v1`, index_status: "PENDING" };
    const it = c.knowledge_items.find((k) => k.kt_item_id === a.kt_item_id);
    if (it) {
      it.kt_status = "COMPLETE";
      it.documentation_status = "DOCUMENTED";
    }
    return this.bump(c);
  }
  async editTransfer(transfer_id: string, final_owner: string, cmd: Command): Promise<ExitKtCase> {
    await this.gate("command");
    const c = this.kt();
    this.require("responsibility.confirm", "Only the authorized manager can edit successor selections.");
    this.checkRevision(cmd.expected_revision, c.revision);
    const t = c.transfers.find((x) => x.transfer_id === transfer_id);
    if (!t || t.status === "TRANSFERRED") this.fail("GUARD_FAILED", "This responsibility can't be edited.");
    if (final_owner === t.current_owner_employee_id) this.fail("MALFORMED_INPUT", "Choose someone other than the current owner, or leave it with them.");
    t.final_owner_employee_id = final_owner;
    t.status = "EDITED";
    return this.bump(c);
  }
  async reviewEffectiveTime(transfer_id: string, cmd: Command): Promise<ExitKtCase> {
    await this.gate("command");
    const c = this.kt();
    this.require("responsibility.confirm", "Only the authorized manager can review the effective time.");
    this.checkRevision(cmd.expected_revision, c.revision);
    const t = c.transfers.find((x) => x.transfer_id === transfer_id);
    if (!t) this.fail("NOT_FOUND", "Transfer not found.");
    t.effective_label = `Now (reviewed by ${this.name(this.ws().persona_id)})`;
    t.effective_reached = true;
    return this.bump(c);
  }
  async assemblePackage(cmd: Command): Promise<ExitKtCase> {
    await this.gate("command");
    const c = this.ktCommand(["SUBJECT"], "Only the employee can assemble their successor package.", cmd);
    const approved = c.artifacts.filter((a) => a.promotion);
    const excluded = c.artifacts.filter((a) => !a.promotion);
    const base = this.pack().exit_kt.case.package.draft_sections.filter((s) => s.title !== "Approved knowledge" && s.title !== "Excluded");
    c.package.draft_sections = [
      ...base,
      { title: "Approved knowledge", content: approved.length ? approved.map((a) => `${a.title} (${a.promotion!.document_version_label})`).join("; ") : "None approved yet.", evidence_type: "OBSERVED" },
      ...(excluded.length ? [{ title: "Excluded", content: `${excluded.map((a) => a.title).join("; ")}: not approved, so not shared with the successor.`, evidence_type: "UNKNOWN" as const }] : []),
    ];
    c.package.status = "DRAFT";
    c.package.revision += 1;
    return this.bump(c);
  }
  async submitPackage(cmd: Command): Promise<ExitKtCase> {
    await this.gate("command");
    const c = this.ktCommand(["SUBJECT"], "Only the employee can submit their package.", cmd);
    if (c.package.status !== "DRAFT" && c.package.status !== "REJECTED") this.fail("GUARD_FAILED", "This package is already submitted or approved.");
    c.package.status = "SUBMITTED";
    this.notify(c.reviewer_employee_id, "REVIEW_REQUESTED", "A successor package is waiting for review", "/reviews/");
    return this.bump(c);
  }
  async decidePackage(decision: "APPROVE" | "REJECT", comment: string, cmd: Command): Promise<ExitKtCase> {
    await this.gate("command");
    const c = this.kt();
    this.require("knowledge.review", "Only an authorized reviewer can decide on the package.");
    if (c.employee_id === this.ws().persona_id) this.fail("FORBIDDEN", "The employee in the case can't approve their own package.");
    this.checkRevision(cmd.expected_revision, c.revision);
    if (c.package.status !== "SUBMITTED") this.fail("GUARD_FAILED", "Only a submitted package can be reviewed.");
    if (decision === "REJECT") {
      if (!comment.trim()) this.fail("MALFORMED_INPUT", "Explain what needs to change.");
      c.package.status = "REJECTED";
      c.package.review_comment = comment;
    } else {
      const v = { package_version_id: this.next("pkv"), content_revision: c.package.revision, sections: c.package.draft_sections.map((s) => ({ ...s })), approved_by: this.ws().persona_id };
      c.package.versions.push(v);
      c.package.current_approved_version_id = v.package_version_id;
      c.package.status = "APPROVED";
      this.notify(c.package.successor_employee_id, "PACKAGE_APPROVED", "Your successor package is ready to read", "/exit-kt/");
    }
    return this.bump(c);
  }
  async receivePackage(package_version_id: string, cmd: Command): Promise<ExitKtCase> {
    await this.gate("command");
    void cmd;
    const c = this.kt();
    if (c.package.successor_employee_id !== this.ws().persona_id) this.fail("FORBIDDEN", "Only the named successor can confirm receipt.");
    if (c.package.current_approved_version_id !== package_version_id) this.fail("REVISION_CONFLICT", "A newer approved version exists. Read it before confirming receipt.");
    if (!c.package.receipts.some((r) => r.package_version_id === package_version_id)) c.package.receipts.push({ package_version_id, employee_id: this.ws().persona_id });
    this.notify(c.reviewer_employee_id, "PACKAGE_RECEIVED", "The successor confirmed receipt of the approved package", "/exit-kt/");
    return this.bump(c);
  }
  async askPackage(input: TurnInput): Promise<ExitKtCase> {
    await this.gate("command");
    const c = this.kt();
    if (c.package.successor_employee_id !== this.ws().persona_id) this.fail("FORBIDDEN", "Package Q&A is for the successor.");
    if (!c.package.current_approved_version_id) this.fail("GUARD_FAILED", "There's no approved package to ask about yet.");
    c.successor_qa.push({ message_id: this.next("qa"), sender: "EMPLOYEE", text: input.text, citations: [], provenance: "EMPLOYEE_INPUT" });
    const step = this.pack().exit_kt.successor_steps.find((s) => s.prompt.prompt_id === input.preview_prompt_id);
    c.successor_qa.push(step ? { message_id: this.next("qa"), sender: "AI", text: step.reply, citations: this.citations(step.excerpt_keys), provenance: "SCRIPTED_FIXTURE" } : { message_id: this.next("qa"), sender: "SYSTEM", text: NOT_INTERPRETED, citations: [], provenance: "PREVIEW_SYSTEM" });
    return this.bump(c);
  }
  async confirmTransfer(transfer_id: string, cmd: Command): Promise<ExitKtCase> {
    await this.gate("command");
    const c = this.kt();
    this.require("responsibility.confirm", "Only the authorized manager can confirm a responsibility transfer.");
    const t = c.transfers.find((x) => x.transfer_id === transfer_id);
    if (!t) this.fail("NOT_FOUND", "Transfer not found.");
    if (t.status === "TRANSFERRED") return this.ktView(c); // replay
    const r = c.responsibilities.find((x) => x.responsibility_id === t.responsibility_id)!;
    if (this.takeStale() || r.ownership_revision !== t.expected_owner_revision) this.fail("REVISION_CONFLICT", "Ownership changed since this transfer was prepared. Reload and review again; the owner is unchanged.");
    const blockers = transferBlockers(c, transfer_id);
    if (blockers.length) this.fail("GUARD_FAILED", `Ownership is unchanged: ${blockers.join("; ")}.`);
    r.owner_employee_id = (t.final_owner_employee_id ?? t.recommended_owner_employee_id)!;
    r.ownership_revision += 1;
    t.status = "TRANSFERRED";
    this.notify(r.owner_employee_id, "RESPONSIBILITY_TRANSFERRED", `You now own "${r.title}"`, "/exit-kt/");
    void cmd;
    return this.bump(c);
  }
  async resolveChecklistItem(item_id: string, evidence_ref: string, cmd: Command): Promise<ExitKtCase> {
    await this.gate("command");
    const c = this.ktCommand(["SUBJECT", "REVIEWER"], "Only the employee or reviewer can resolve checklist items.", cmd);
    const it = c.checklist.find((x) => x.checklist_item_id === item_id);
    if (!it) this.fail("NOT_FOUND", "Checklist item not found.");
    if (!checklistEvidence(c, (id) => this.name(id)).some((e) => e.ref === evidence_ref)) this.fail("GUARD_FAILED", "Choose reviewed evidence. A receipt or a conversation alone doesn't resolve a checklist item.");
    it.status = "RESOLVED";
    it.evidence_refs = [evidence_ref];
    return this.bump(c);
  }
  async recordChecklistException(item_id: string, reason: string, cmd: Command): Promise<ExitKtCase> {
    await this.gate("command");
    const c = this.kt();
    this.require("responsibility.confirm", "Only the authorized manager can record an exception.");
    this.checkRevision(cmd.expected_revision, c.revision);
    const it = c.checklist.find((x) => x.checklist_item_id === item_id);
    if (!it) this.fail("NOT_FOUND", "Checklist item not found.");
    if (!reason.trim()) this.fail("MALFORMED_INPUT", "Explain the exception; it's disclosed on the case.");
    it.status = "RESOLVED";
    it.exception_reason = reason;
    return this.bump(c);
  }
  async recommendSuccessors(): Promise<ExitKtCase> {
    await this.gate("command");
    this.fail("CAPABILITY_UNAVAILABLE", "Successor recommendations run on the WorkWeave backend with the knowledge-transfer graph.");
  }
  async decidePlanItem(): Promise<ExitKtCase> {
    await this.gate("command");
    this.fail("CAPABILITY_UNAVAILABLE", "The AI plan runs on the WorkWeave backend.");
  }
  async askKtCopilot(): Promise<ExitKtCase> {
    await this.gate("command");
    this.fail("CAPABILITY_UNAVAILABLE", "The knowledge-transfer assistant runs on the WorkWeave backend.");
  }
  async assignSuccessor(): Promise<ExitKtCase> {
    await this.gate("command");
    this.fail("CAPABILITY_UNAVAILABLE", "Successor assignment runs on the WorkWeave backend.");
  }
  async completeExitKtCase(cmd: Command): Promise<ExitKtCase> {
    await this.gate("command");
    const c = this.kt();
    this.require("responsibility.confirm", "Only the authorized manager can complete the case.");
    this.checkRevision(cmd.expected_revision, c.revision);
    const open = c.checklist.filter((i) => i.required && i.status !== "RESOLVED");
    if (open.length) this.fail("GUARD_FAILED", `Required checklist items are still open: ${open.map((i) => i.label).join("; ")}.`);
    c.status = "COMPLETE";
    return this.bump(c);
  }

  // ---------------------------------------------------------------- reviews / inbox / knowledge
  async runHandoverGapCheck(): Promise<HandoverWorkspace> {
    await this.gate("command");
    this.fail("CAPABILITY_UNAVAILABLE", "The gap check runs on the WorkWeave backend with the handover graph; the preview shows its scripted suggestions.");
  }
  async draftHandoverSections(): Promise<HandoverSectionDraft[]> {
    await this.gate("command");
    this.fail("CAPABILITY_UNAVAILABLE", "Drafting runs on the WorkWeave backend with the handover graph.");
  }
  async getShiftClock(): Promise<ShiftClock> {
    await this.gate("read");
    this.fail("CAPABILITY_UNAVAILABLE", "The preview moves shifts from Review tools.");
  }
  async advanceShiftClock(): Promise<ShiftClock> {
    await this.gate("command");
    this.fail("CAPABILITY_UNAVAILABLE", "The preview moves shifts from Review tools.");
  }
  async listReviews(): Promise<ReviewQueueItem[]> {
    await this.gate("read");
    this.require("knowledge.review", "The reviewer workspace is for authorized knowledge reviewers.");
    const ws = this.ws();
    const me = ws.persona_id;
    const out: ReviewQueueItem[] = [];
    for (const d of ws.memoryDrafts.filter((x) => x.status === "PENDING_REVIEW" && x.owner_employee_id !== me)) {
      out.push({ review_id: d.draft_id, kind: "MEMORY_DRAFT", title: "Knowledge note", submitted_by: this.name(d.owner_employee_id), revision_label: `Revision ${d.revision}`, content: d.content, audience: d.requested_audience, resource_id: d.draft_id, href: "/reviews/" });
    }
    const c = ws.exitKt;
    if (c.employee_id !== me) {
      for (const a of c.artifacts) {
        const cur = a.revisions.find((r) => r.artifact_revision_id === a.current_revision_id);
        if (cur?.status === "PENDING_REVIEW") out.push({ review_id: cur.artifact_revision_id, kind: "KT_ARTIFACT", title: a.title, submitted_by: this.name(c.employee_id), revision_label: `v${cur.version}`, content: cur.content, audience: cur.audience, resource_id: a.artifact_id, href: "/exit-kt/?area=knowledge" });
      }
      if (c.package.status === "SUBMITTED") out.push({ review_id: c.package.package_id, kind: "KT_PACKAGE", title: `Successor package for ${this.name(c.package.successor_employee_id)}`, submitted_by: this.name(c.employee_id), revision_label: `Revision ${c.package.revision}`, content: c.package.draft_sections.map((s) => `${s.title}: ${s.content}`).join("\n"), audience: "Successor", resource_id: c.package.package_id, href: "/exit-kt/?area=responsibility" });
    }
    return out;
  }
  async decideMemoryDraft(draft_id: string, decision: "APPROVE" | "REJECT", comment: string, cmd: Command): Promise<void> {
    await this.gate("command");
    this.require("knowledge.review", "Only an authorized reviewer can decide.");
    const ws = this.ws();
    const d = ws.memoryDrafts.find((x) => x.draft_id === draft_id);
    if (!d) this.fail("NOT_FOUND", "Draft not found.");
    if (d.owner_employee_id === ws.persona_id) this.fail("FORBIDDEN", "You can't approve your own knowledge note.");
    this.checkRevision(cmd.expected_revision, d.revision);
    if (d.status !== "PENDING_REVIEW") this.fail("GUARD_FAILED", "This note isn't waiting for review.");
    if (decision === "REJECT" && !comment.trim()) this.fail("MALFORMED_INPUT", "Explain why the note isn't approved.");
    d.status = decision === "APPROVE" ? "APPROVED" : "REJECTED";
    d.review_comment = comment || undefined;
    d.revision += 1;
    if (decision === "APPROVE") ws.extraTimeline.push({ entry_id: this.next("tl"), label: "Knowledge note approved", detail: `${d.content.slice(0, 120)} (still a reported observation; approval doesn't make it verified)`, kind: "MEMORY_RECORD", temporal: "CURRENT", evidence_type: "REPORTED" });
    this.notify(d.owner_employee_id, "REVIEW_DECISION", `Your knowledge note was ${d.status.toLowerCase()}`, "/companion/");
    this.emit();
  }
  async listNotifications(): Promise<InboxNotification[]> {
    await this.gate("read");
    return this.ws().notifications[this.ws().persona_id] ?? [];
  }
  unreadCount(): number {
    try {
      return (this.ws().notifications[this.ws().persona_id] ?? []).filter((n) => !n.read_at).length;
    } catch {
      return 0;
    }
  }
  async markNotificationRead(id: string): Promise<void> {
    const n = (this.ws().notifications[this.ws().persona_id] ?? []).find((x) => x.notification_id === id);
    if (n && !n.read_at) n.read_at = "Just now";
    this.emit();
  }
  async getTimeline(): Promise<TimelineEntry[]> {
    await this.gate("read");
    return [...this.ws().extraTimeline.slice().reverse(), ...this.pack().timeline];
  }
  async listDocumentVersions(): Promise<DocumentVersion[]> {
    await this.gate("read");
    return this.allDocuments();
  }
  async getSourceContent(id: string): Promise<{ version: DocumentVersion; text: string }> {
    await this.gate("read");
    const version = this.allDocuments().find((d) => d.document_version_id === id);
    if (!version) this.fail("NOT_FOUND", "Source not found or not available to you.");
    if (this.ws().revokedVersions.includes(id)) this.fail("FORBIDDEN", "This source has been revoked. Its content is no longer available, and cached copies aren't shown.");
    const text = this.pack().full_text[id] ?? (version.document_type === "KT_ARTIFACT" ? this.promotedText(id) : "");
    return { version, text };
  }
  private promotedText(id: string) {
    const c = this.ws().exitKt;
    const dv = this.ws().extraDocuments.find((d) => d.document_version_id === id);
    const a = c.artifacts.find((x) => x.promotion && dv && x.title === dv.title);
    return a?.revisions.find((r) => r.status === "APPROVED")?.content ?? "";
  }
  async getExcerpt(source_id: string): Promise<SourceExcerpt> {
    await this.gate("read");
    const e = Object.values(this.pack().excerpts).find((x) => x.source_id === source_id);
    if (!e) this.fail("NOT_FOUND", "Excerpt not found.");
    return e;
  }
}

const CLIENT_METHODS: (keyof WorkWeaveClient)[] = [
  "listScenarios", "startDemoSession", "getLocalDemoRun", "getSession", "endSession", "listPersonas", "switchPersona", "getCapabilities",
  "getOnboarding", "startOnboardingSession", "getOnboardingSession", "sendOnboardingTurn", "continueOnboarding", "pauseOnboarding", "getSupervisorProgress",
  "startWorkSession", "sendWorkMessage", "dismissPendingReport", "getWorkDashboard", "listWorkItems", "listWorkEvents", "getGuidance", "reportWorkEvent", "getTicketSystem", "updateTicketStatus",
  "listProposals", "getProposal", "editProposalItem", "confirmProposal", "rejectProposal",
  "createMemoryDraft", "listMyMemoryDrafts", "submitMemoryDraft", "deleteMemoryDraft",
  "getHandoverWorkspace", "editDraftSection", "acceptSuggestion", "createTemplateVersion", "ignoreSuggestion", "publishHandover", "confirmHandoverReceipt", "acknowledgeCompletion", "confirmItemCompletion", "askHandoverCopilot",
  "getExitKtCase", "createExitKtCase", "addKnowledgeItem", "linkExistingKnowledge", "reviewFinding", "runDiscovery", "startInterview", "sendInterviewMessage", "draftArtifactFromInterview", "createManualArtifact", "editArtifact", "submitArtifact", "decideArtifact", "promoteArtifact", "retryKtIndexing", "editTransfer", "reviewEffectiveTime", "assemblePackage", "submitPackage", "decidePackage", "receivePackage", "askPackage", "confirmTransfer", "resolveChecklistItem", "recordChecklistException", "completeExitKtCase", "recommendSuccessors", "decidePlanItem", "askKtCopilot", "assignSuccessor",
  "listCurricula", "getCurriculum", "createCurriculum", "createCurriculumRevision", "stageCurriculumSource", "parseCurriculumSource", "saveLearningPath", "saveSourceMappings", "saveObjective", "submitSourceForReview", "reviewSourceVersion", "retryIngestion", "publishCurriculum",
  "runHandoverGapCheck", "draftHandoverSections", "getShiftClock", "advanceShiftClock", "listReviews", "decideMemoryDraft", "listNotifications", "markNotificationRead", "getTimeline", "listDocumentVersions", "getSourceContent", "getExcerpt",
];

function safeSession(): Storage | null {
  try {
    const s = window.sessionStorage;
    s.setItem("__ww", "1");
    s.removeItem("__ww");
    return s;
  } catch {
    return null;
  }
}
