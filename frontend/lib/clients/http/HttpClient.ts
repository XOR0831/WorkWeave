/**
 * WorkWeave API client (same-origin /api; the browser never talks to PostgreSQL).
 *
 * Wired in this slice: GET /scenarios, POST /demo-sessions, GET /demo-sessions/current,
 * GET /demo-sessions/runs (PROPOSED), DELETE /demo-sessions/current (PROPOSED),
 * POST /demo-sessions/current/persona, GET /personas, and the onboarding read paths
 * GET /onboarding and GET /onboarding/progress, and the tutor shell (POST /onboarding/sessions,
 * GET /onboarding/sessions/{id}, .../turns, .../pause; replies are unavailable until the AI
 * package is connected), and the read-only curricula catalog/detail (GET /curricula,
 * GET /curricula/{id}; PROPOSED). The session is an HttpOnly cookie that
 * scripts can't read. Every other method rejects with CAPABILITY_UNAVAILABLE until its slice
 * is built; no fixture data is substituted.
 */
import type { Command, TurnInput, WorkWeaveClient } from "../WorkWeaveClient";
import type { ListenMode, VoiceGrant } from "@/lib/voice/live-listener";
import type { PcmStream } from "@/lib/voice/stream-player";
import type { ClientRuntime } from "../runtime";
import {
  WorkWeaveError,
  type AccessInfo,
  type DemoUsage,
  type InboxNotification,
  type ApiError,
  type Capabilities,
  type CurriculaCatalog,
  type Curriculum,
  type DelegationProposal,
  type AssignmentCandidate,
  type AssignmentExplanation,
  type CalendarStatus,
  type DemoSession,
  type CaseKind,
  type ExitKtCase,
  type ReviewQueueItem,
  type ShiftClock,
  type CurriculumObjective,
  type StageSourceInput,
  type DocumentVersion,
  type TimelineEntry,
  type HandoverSectionDraft,
  type HandoverWorkspace,
  type TemplateSectionInput,
  type GuidanceProjection,
  type LocalDemoRun,
  type MemoryDraft,
  type OnboardingOverview,
  type OnboardingSessionView,
  type Persona,
  type ScenarioCard,
  type ScenarioKey,
  type SupervisorProgressRow,
  type SyncStatus,
  type TicketSystemItem,
  type TicketSystemView,
  type WorkEvent,
  type WorkItem,
  type WorkDashboard,
  type WorkSessionView,
} from "@/types/contracts";

/** The fixed wording for a real failure: no codes, causes or technical detail ever reach the person. */
const FAILED = "Couldn't do that because an error was encountered. Nothing was changed; try again.";

/** When the server sent no explanation. Expected situations keep their reason; failures stay generic. */
function plainStatus(status: number): string {
  if (status === 401 || status === 403) return "You aren't allowed to do that here, so nothing was changed.";
  if (status === 409) return "Something changed while you were working, so nothing was saved. Reload the page and try again.";
  if (status === 413) return "That's too large to send. Shorten it and try again.";
  if (status === 429) return "There are too many requests right now. Wait a moment, then try again.";
  return FAILED;
}

const BASE = process.env.NEXT_PUBLIC_WORKWEAVE_API_BASE ?? "/api";

/** Server-sent events from a fetch body (event + JSON data per block). */
export async function* readEvents(body: ReadableStream<Uint8Array>): AsyncGenerator<{ event: string; data: unknown }> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (value) buf += decoder.decode(value, { stream: true });
    let cut: number;
    while ((cut = buf.indexOf("\n\n")) >= 0) {
      const block = buf.slice(0, cut);
      buf = buf.slice(cut + 2);
      let event = "message";
      const data: string[] = [];
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data.push(line.slice(5).trim());
      }
      if (!data.length) continue;
      try {
        yield { event, data: JSON.parse(data.join("\n")) };
      } catch {
        /* not JSON: ignore */
      }
    }
    if (done) return;
  }
}
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

type Wired = "listScenarios" | "startDemoSession" | "getLocalDemoRun" | "getSession" | "endSession" | "listPersonas" | "switchPersona" | "getCapabilities" | "getOnboarding" | "getSupervisorProgress" | "startOnboardingSession" | "getOnboardingSession" | "sendOnboardingTurn" | "continueOnboarding" | "pauseOnboarding" | "listCurricula" | "getCurriculum" | "getVoiceListenGrant" | "getReplySpeech" | "streamReplySpeech" | "streamWorkReplySpeech" | "getHandoverVoiceListenGrant" | "streamHandoverReplySpeech" | "getKtVoiceListenGrant" | "streamKtReplySpeech" | "getCalendarStatus" | "createCurriculum" | "stageCurriculumSource" | "reviewSourceVersion" | "retryIngestion" | "saveObjective" | "publishCurriculum" | "getShiftClock" | "advanceShiftClock" | "listReviews" | "decideMemoryDraft" | "getTimeline" | "listDocumentVersions" | "getSourceContent" | "getExitKtCase" | "createExitKtCase" | "addKnowledgeItem" | "linkExistingKnowledge" | "reviewFinding" | "runDiscovery" | "startInterview" | "sendInterviewMessage" | "draftArtifactFromInterview" | "askPackage" | "createManualArtifact" | "editArtifact" | "submitArtifact" | "decideArtifact" | "promoteArtifact" | "editTransfer" | "reviewEffectiveTime" | "confirmTransfer" | "assemblePackage" | "submitPackage" | "decidePackage" | "receivePackage" | "resolveChecklistItem" | "recordChecklistException" | "completeExitKtCase" | "recommendSuccessors" | "decidePlanItem" | "askKtCopilot" | "assignSuccessor" | "getHandoverWorkspace" | "editDraftSection" | "acceptSuggestion" | "ignoreSuggestion" | "createTemplateVersion" | "publishHandover" | "confirmHandoverReceipt" | "acknowledgeCompletion" | "askHandoverCopilot" | "runHandoverGapCheck" | "draftHandoverSections" | "watchWork" | "getAssignmentExplanation" | "getAssignmentCandidates" | "reassignWorkItem" | "startWorkSession" | "getWorkDashboard" | "listWorkItems" | "listWorkEvents" | "sendWorkMessage" | "getGuidance" | "getWorkVoiceListenGrant" | "reportWorkEvent" | "getTicketSystem" | "updateTicketStatus" | "listProposals" | "getProposal" | "editProposalItem" | "confirmProposal" | "rejectProposal" | "createMemoryDraft" | "listMyMemoryDrafts" | "submitMemoryDraft" | "deleteMemoryDraft" | "getAccess" | "redeemAccessCode" | "leaveAccess" | "getDemoUsage" | "listNotifications" | "markNotificationRead" | "createCurriculumRevision" | "removeCurriculumSource" | "setSubtopicIncluded" | "moveCurriculumTopic";

class HttpCore {
  readonly mode = "http" as const;
  private version = 0;
  private listeners = new Set<() => void>();
  private session: DemoSession | null = null;
  private personas: Persona[] = [];
  private catalog = new Map<string, ScenarioCard>();
  private loaded = false;
  private error: ApiError | null = null;

  constructor() {
    if (typeof window !== "undefined") void this.refresh();
  }

  // ---------------------------------------------------------------- runtime
  subscribe = (fn: () => void) => {
    this.listeners.add(fn);
    return () => {
      this.listeners.delete(fn);
    };
  };
  getVersion() {
    return this.version;
  }
  isLoaded() {
    return this.loaded;
  }
  loadError() {
    return this.error;
  }
  peekSession() {
    return this.session;
  }
  peekPersonas() {
    return this.personas;
  }
  /** Unread inbox notices, from the last inbox read (ADR-048); the shell's Inbox badge. */
  private unread = 0;
  unreadCount() {
    return this.unread;
  }
  private setUnread(n: number) {
    if (n === this.unread) return;
    this.unread = n;
    this.emit();
  }
  // ---------------------------------------------------------------- Inbox (ADR-048: backend-mediated Firestore projection)
  async listNotifications(): Promise<InboxNotification[]> {
    const rows = await this.call<(Omit<InboxNotification, "created_label"> & { created_at: string | null; read_at: string | null })[]>("GET", "/notifications", undefined, false);
    const list = rows.map((n) => ({
      ...n,
      created_at: n.created_at ?? undefined,
      read_at: n.read_at ?? undefined,
      created_label: n.created_at ? new Date(n.created_at).toLocaleString(undefined, { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" }) : "",
    }));
    this.setUnread(list.filter((n) => !n.read_at).length);
    return list;
  }
  /** Only the read marker: it doesn't accept work, acknowledge a handover or approve anything. */
  async markNotificationRead(notification_id: string): Promise<void> {
    await this.call<unknown>("PATCH", `/notifications/${encodeURIComponent(notification_id)}/read`, undefined, false);
    this.unread = Math.max(0, this.unread - 1);
    this.emit(); // the inbox list and badge read again
  }
  private emit() {
    this.version += 1;
    this.listeners.forEach((fn) => fn());
  }
  /** Notify only on real changes: screens refetch on every version bump, so reads must not bump it. */
  private update(session: DemoSession | null, personas: Persona[]) {
    if (JSON.stringify(session) === JSON.stringify(this.session) && JSON.stringify(personas) === JSON.stringify(this.personas)) return;
    this.session = session;
    this.personas = personas;
    this.emit();
  }
  private async refresh() {
    try {
      await this.getSession();
      if (this.session) await this.listPersonas();
      this.error = null;
    } catch (e) {
      this.session = null;
      this.error = e instanceof WorkWeaveError ? (e.error.code === "SESSION_EXPIRED" ? null : e.error) : { code: "DEPENDENCY_UNAVAILABLE", message: String(e), retryable: true };
    } finally {
      this.loaded = true;
      this.emit(); // first load always notifies so the shell can leave its loading state
    }
  }

  // ---------------------------------------------------------------- transport
  private async call<T>(method: "GET" | "POST" | "PATCH" | "PUT" | "DELETE", path: string, body?: unknown, notify = true): Promise<T> {
    let res: Response;
    try {
      res = await fetch(`${BASE}${path}`, {
        method,
        credentials: "same-origin",
        cache: "no-store",
        headers: { Accept: "application/json", ...(method === "GET" ? {} : { "Content-Type": "application/json", "X-WorkWeave-Client": "web" }) },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch {
      throw new WorkWeaveError({ code: "DEPENDENCY_UNAVAILABLE", message: FAILED, retryable: true }, "network");
    }
    const json = (await res.json().catch(() => null)) as { request_id?: string; data?: T; error?: ApiError } | null;
    if (!res.ok || !json || json.error) {
      const error: ApiError = json?.error ?? { code: "DEPENDENCY_UNAVAILABLE", message: plainStatus(res.status), retryable: res.status >= 500 };
      if (error.code === "SESSION_EXPIRED") this.update(null, []);
      throw new WorkWeaveError(error, json?.request_id ?? res.headers.get("x-request-id") ?? "unknown");
    }
    // Like the preview client, a committed command tells screens to re-read their data.
    // Reads never notify, so a refetch can't trigger another refetch.
    if (method !== "GET" && notify) queueMicrotask(() => this.emit());
    return json.data as T;
  }

  // ---------------------------------------------------------------- wired methods
  async listScenarios(): Promise<ScenarioCard[]> {
    const list = await this.call<ScenarioCard[]>("GET", "/scenarios");
    this.catalog = new Map(list.map((s) => [s.key, s]));
    return list;
  }
  private async scenarioId(key: ScenarioKey) {
    if (!this.catalog.has(key)) await this.listScenarios();
    const card = this.catalog.get(key);
    if (!card) throw new WorkWeaveError({ code: "NOT_FOUND", message: "This company isn't in the demo catalog.", retryable: false }, "client");
    return card.scenario_id;
  }
  async startDemoSession(key: ScenarioKey, fresh: boolean): Promise<DemoSession> {
    const scenario_id = await this.scenarioId(key);
    const s = await this.call<DemoSession>("POST", "/demo-sessions", { scenario_id, intent: fresh ? "FRESH" : "RESUME" });
    this.update(s, await this.call<Persona[]>("GET", "/personas"));
    return s;
  }
  async getLocalDemoRun(key: ScenarioKey): Promise<LocalDemoRun | null> {
    const runs = await this.call<LocalDemoRun[]>("GET", "/demo-sessions/runs");
    return runs.find((r) => r.key === key) ?? null;
  }
  async getSession(): Promise<DemoSession | null> {
    const s = await this.call<DemoSession | null>("GET", "/demo-sessions/current");
    this.update(s, s ? this.personas : []);
    return s;
  }
  async endSession(): Promise<void> {
    await this.call<null>("DELETE", "/demo-sessions/current");
    this.update(null, []);
  }
  async listPersonas(): Promise<Persona[]> {
    this.update(this.session, await this.call<Persona[]>("GET", "/personas"));
    return this.personas;
  }
  async switchPersona(employee_id: string): Promise<DemoSession> {
    const s = await this.call<DemoSession>("POST", "/demo-sessions/current/persona", { employee_id });
    this.update(s, this.personas);
    return s;
  }
  async getOnboarding(): Promise<OnboardingOverview | null> {
    return this.call<OnboardingOverview | null>("GET", "/onboarding");
  }
  async getSupervisorProgress(): Promise<SupervisorProgressRow[]> {
    return this.call<SupervisorProgressRow[]>("GET", "/onboarding/progress");
  }
  async startOnboardingSession(): Promise<OnboardingSessionView> {
    return this.call<OnboardingSessionView>("POST", "/onboarding/sessions");
  }
  async getOnboardingSession(): Promise<OnboardingSessionView | null> {
    const ov = await this.getOnboarding();
    if (!ov?.learning_session_id) return null;
    return this.call<OnboardingSessionView>("GET", `/onboarding/sessions/${encodeURIComponent(ov.learning_session_id)}`);
  }
  private async openSessionId() {
    const ov = await this.getOnboarding();
    if (!ov?.learning_session_id) throw new WorkWeaveError({ code: "GUARD_FAILED", message: "Start the conversation first.", retryable: false }, "client");
    return encodeURIComponent(ov.learning_session_id);
  }
  /** One UUID per command idempotency key, so a retried send reuses its client_turn_id (the server dedupes it). */
  private turnIds = new Map<string, string>();
  private turnId(input: TurnInput) {
    if (UUID_RE.test(input.client_turn_id)) return input.client_turn_id;
    let id = this.turnIds.get(input.idempotency_key);
    if (!id) this.turnIds.set(input.idempotency_key, (id = crypto.randomUUID()));
    return id;
  }
  /**
   * POST …/turns/stream: server-sent `progress` {label} events while the tutor works, then `done`
   * (the saved view) or `error`. Checks that fail before the tutor starts come back as a JSON error.
   */
  async sendOnboardingTurn(input: TurnInput): Promise<OnboardingSessionView> {
    const id = await this.openSessionId();
    const body = {
      client_turn_id: this.turnId(input),
      expected_revision: input.expected_revision,
      text: input.text,
      input_kind: input.input_kind,
      ...(input.interrupted_previous_reply ? { interrupted_previous_reply: true } : {}),
    };
    return this.streamTurn<OnboardingSessionView>(`${BASE}/onboarding/sessions/${id}/turns/stream`, body, input.onProgress, "The tutor's reply was cut off. Nothing was lost; reload to see the saved conversation.");
  }
  /** A turn answered as server-sent events: `progress` labels, then `done` (the saved view) or `error`. */
  private async streamTurn<T>(url: string, body: unknown, onProgress: ((label: string) => void) | undefined, cutOff: string): Promise<T> {
    let res: Response;
    try {
      res = await fetch(url, {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        headers: { Accept: "text/event-stream", "Content-Type": "application/json", "X-WorkWeave-Client": "web" },
        body: JSON.stringify(body),
      });
    } catch {
      throw new WorkWeaveError({ code: "DEPENDENCY_UNAVAILABLE", message: FAILED, retryable: true }, "network");
    }
    if (!res.ok || !res.body || !(res.headers.get("content-type") ?? "").startsWith("text/event-stream")) {
      const json = (await res.json().catch(() => null)) as { request_id?: string; data?: T; error?: ApiError } | null;
      if (res.ok && json?.data) return json.data;
      const error: ApiError = json?.error ?? { code: "DEPENDENCY_UNAVAILABLE", message: plainStatus(res.status), retryable: res.status >= 500 };
      if (error.code === "SESSION_EXPIRED") this.update(null, []);
      throw new WorkWeaveError(error, json?.request_id ?? res.headers.get("x-request-id") ?? "unknown");
    }
    for await (const ev of readEvents(res.body)) {
      if (ev.event === "progress") onProgress?.(String((ev.data as { label?: string }).label ?? ""));
      else if (ev.event === "done") {
        queueMicrotask(() => this.emit()); // a committed command: screens re-read
        return (ev.data as { data: T }).data;
      } else if (ev.event === "error") {
        const e = ev.data as { request_id?: string; error: ApiError };
        throw new WorkWeaveError(e.error, e.request_id ?? "unknown");
      }
    }
    throw new WorkWeaveError({ code: "DEPENDENCY_UNAVAILABLE", message: cutOff, retryable: true }, "stream");
  }
  /** After a completed item the tutor opens the next one (ADR-030; needs the connected engine). */
  async continueOnboarding(cmd: Command): Promise<OnboardingSessionView> {
    const id = await this.openSessionId();
    return this.call<OnboardingSessionView>("POST", `/onboarding/sessions/${id}/continue`, { expected_revision: cmd.expected_revision });
  }
  async pauseOnboarding(cmd: Command): Promise<OnboardingSessionView> {
    const id = await this.openSessionId();
    return this.call<OnboardingSessionView>("POST", `/onboarding/sessions/${id}/pause`, { client_turn_id: cmd.idempotency_key, expected_revision: cmd.expected_revision });
  }
  async listCurricula(): Promise<CurriculaCatalog> {
    return this.call<CurriculaCatalog>("GET", "/curricula");
  }
  async getCurriculum(curriculum_id: string): Promise<Curriculum> {
    return this.call<Curriculum>("GET", `/curricula/${encodeURIComponent(curriculum_id)}`);
  }
  // ---------------------------------------------------------------- Work Companion (reads + shell + voice)
  private workSessionId: string | null = null;
  async startWorkSession(): Promise<WorkSessionView> {
    const view = await this.call<WorkSessionView>("POST", "/work-sessions", undefined, false);
    this.workSessionId = view.work_session_id;
    return view;
  }
  private async openWorkSessionId(): Promise<string> {
    return this.workSessionId ?? (await this.startWorkSession()).work_session_id;
  }
  async getWorkDashboard(): Promise<WorkDashboard> {
    return this.call<WorkDashboard>("GET", "/work-state");
  }
  async listWorkItems(): Promise<WorkItem[]> {
    return this.call<WorkItem[]>("GET", "/assignments");
  }
  async listWorkEvents(): Promise<WorkEvent[]> {
    return this.call<WorkEvent[]>("GET", "/work-events");
  }
  /** The AI engine's reply and the saved conversation (ADR-034); "not connected" when it isn't configured. */
  async sendWorkMessage(input: TurnInput): Promise<WorkSessionView> {
    const id = await this.openWorkSessionId();
    const body = { client_turn_id: this.turnId(input), expected_revision: input.expected_revision, text: input.text, input_kind: input.input_kind };
    // Streamed: `progress` labels while the companion works, then the saved conversation.
    return this.streamTurn<WorkSessionView>(`${BASE}/work-sessions/${id}/messages/stream`, body, input.onProgress, "The companion's reply was cut off. Nothing was lost; reload to see the saved conversation.");
  }
  /** A guidance reply in the work area: the answer, the question and its approved sources. */
  async getGuidance(guidance_id: string): Promise<GuidanceProjection> {
    const id = await this.openWorkSessionId();
    return this.call<GuidanceProjection>("GET", `/work-sessions/${id}/guidance/${encodeURIComponent(guidance_id)}`);
  }
  async getWorkVoiceListenGrant(mode: ListenMode): Promise<VoiceGrant> {
    const id = await this.openWorkSessionId();
    return this.call<VoiceGrant>("POST", `/work-sessions/${id}/voice/listen`, { mode }, false);
  }
  // ---------------------------------------------------------------- Work Companion commands (ADR-032)
  /** A Companion report (ADR-033): what the employee says. It never changes the ticket's status. */
  async reportWorkEvent(work_item_id: string, event_type: "COMMENTED" | "REPORTED_COMPLETE" | "BLOCKED", description: string, cmd: Command): Promise<WorkEvent> {
    const reported_status = event_type === "REPORTED_COMPLETE" ? "DONE" : event_type === "BLOCKED" ? "BLOCKED" : "IN_PROGRESS";
    const r = await this.call<{ reported_update_id: string; work_item_id: string; employee_id: string; description: string; sync_status: SyncStatus; reported_label: string }>(
      "POST",
      `/work-items/${work_item_id}/reports`,
      { ...cmd, reported_status, description },
    );
    return { work_event_id: r.reported_update_id, work_item_id: r.work_item_id, employee_id: r.employee_id, event_type, description: r.description, evidence_type: "REPORTED", observed_label: r.reported_label, source: "COMPANION", sync_status: r.sync_status };
  }
  async getTicketSystem(): Promise<TicketSystemView> {
    return this.call<TicketSystemView>("GET", "/ticket-system");
  }
  async updateTicketStatus(work_item_id: string, status: "IN_PROGRESS" | "BLOCKED" | "COMPLETED" | "CANCELLED", note: string, cmd: Command): Promise<TicketSystemItem> {
    return this.call<TicketSystemItem>("POST", `/ticket-system/items/${work_item_id}/status`, { ...cmd, status, note });
  }
  async listProposals(): Promise<DelegationProposal[]> {
    return this.call<DelegationProposal[]>("GET", "/delegation-proposals");
  }
  async getProposal(id: string): Promise<DelegationProposal> {
    return this.call<DelegationProposal>("GET", `/delegation-proposals/${id}`);
  }
  async editProposalItem(id: string, work_item_id: string, final_employee_id: string, cmd: Command): Promise<DelegationProposal> {
    return this.call<DelegationProposal>("PATCH", `/delegation-proposals/${id}`, { ...cmd, work_item_id, final_employee_id });
  }
  async confirmProposal(id: string, cmd: Command): Promise<DelegationProposal> {
    return this.call<DelegationProposal>("POST", `/delegation-proposals/${id}/confirm`, cmd);
  }
  async rejectProposal(id: string, reason: string, cmd: Command): Promise<DelegationProposal> {
    return this.call<DelegationProposal>("POST", `/delegation-proposals/${id}/reject`, { ...cmd, reason });
  }
  async createMemoryDraft(content: string, requested_audience: MemoryDraft["requested_audience"], cmd: Command): Promise<MemoryDraft> {
    return this.call<MemoryDraft>("POST", "/memory-drafts", { ...cmd, content, requested_audience });
  }
  async listMyMemoryDrafts(): Promise<MemoryDraft[]> {
    return this.call<MemoryDraft[]>("GET", "/memory-drafts");
  }
  async submitMemoryDraft(draft_id: string, cmd: Command): Promise<MemoryDraft> {
    return this.call<MemoryDraft>("POST", `/memory-drafts/${draft_id}/review`, cmd);
  }
  async deleteMemoryDraft(draft_id: string, cmd: Command): Promise<void> {
    await this.call<unknown>("DELETE", `/memory-drafts/${draft_id}?idempotency_key=${encodeURIComponent(cmd.idempotency_key)}`);
  }
  async getCapabilities(): Promise<Capabilities> {
    return this.call<Capabilities>("GET", "/capabilities");
  }
  async getAccess(): Promise<AccessInfo> {
    return this.call<AccessInfo>("GET", "/demo-access");
  }
  async getDemoUsage(): Promise<DemoUsage> {
    return this.call<DemoUsage>("GET", "/demo-usage");
  }
  /** Changes this browser's tier: re-read the session so the badge and limits update everywhere. */
  async redeemAccessCode(code: string): Promise<AccessInfo> {
    const info = await this.call<AccessInfo>("POST", "/demo-access", { code });
    await this.refresh();
    return info;
  }
  async leaveAccess(): Promise<AccessInfo> {
    const info = await this.call<AccessInfo>("DELETE", "/demo-access");
    await this.refresh();
    return info;
  }
  async getVoiceListenGrant(mode: ListenMode): Promise<VoiceGrant> {
    const id = await this.openSessionId();
    // Minting a token changes no business state, so screens aren't asked to re-read.
    return this.call<VoiceGrant>("POST", `/onboarding/sessions/${id}/voice/listen`, { mode }, false);
  }
  async streamReplySpeech(message_id: string): Promise<PcmStream> {
    const id = await this.openSessionId();
    return this.pcm(`${BASE}/onboarding/sessions/${id}/voice/speech/${encodeURIComponent(message_id)}/stream`);
  }
  watchWork(everyMs = 15000): () => void {
    let last: string | undefined;
    let stopped = false;
    const check = async () => {
      if (stopped || (typeof document !== "undefined" && document.hidden)) return;
      const d = await this.getWorkDashboard().catch(() => null);
      if (!d?.changes_token || stopped) return;
      if (last !== undefined && d.changes_token !== last) this.emit(); // someone changed the team's work
      last = d.changes_token;
    };
    void check();
    const t = setInterval(() => void check(), everyMs);
    return () => {
      stopped = true;
      clearInterval(t);
    };
  }
  // ---------------------------------------------------------------- demo shift clock (ADR-042)
  async getShiftClock(): Promise<ShiftClock> {
    return this.call<ShiftClock>("GET", "/demo-sessions/current/shift-clock", undefined, false);
  }
  async advanceShiftClock(confirm_unpublished: boolean, cmd: Command): Promise<ShiftClock> {
    return this.call<ShiftClock>("POST", "/demo-sessions/current/shift-clock/advance", { idempotency_key: cmd.idempotency_key, confirm_unpublished });
  }

  // ---------------------------------------------------------------- Reviews (ADR-041)
  async listReviews(): Promise<ReviewQueueItem[]> {
    return this.call<ReviewQueueItem[]>("GET", "/reviews");
  }
  async decideMemoryDraft(draft_id: string, decision: "APPROVE" | "REJECT", comment: string, cmd: Command): Promise<void> {
    await this.call("POST", `/memory-drafts/${encodeURIComponent(draft_id)}/decision`, { idempotency_key: cmd.idempotency_key, decision, comment });
  }

  // ---------------------------------------------------------------- curriculum authoring (ADR-040): commands, then the stored record
  async createCurriculum(input: { name: string; version: string; description?: string }, cmd: Command): Promise<Curriculum> {
    const r = await this.call<{ curriculum_id: string }>("POST", "/curricula", { idempotency_key: cmd.idempotency_key, name: input.name, version: input.version, description: input.description ?? "" });
    return this.getCurriculum(r.curriculum_id);
  }
  async stageCurriculumSource(curriculum_id: string, input: StageSourceInput, cmd: Command): Promise<Curriculum> {
    const id = encodeURIComponent(curriculum_id);
    await this.call("POST", `/curricula/${id}/sources`, {
      idempotency_key: cmd.idempotency_key,
      expected_revision: cmd.expected_revision,
      document_code: input.document_code,
      title: input.title,
      version: input.version,
      document_type: input.document_type ?? "SOP",
      filename: input.file?.name ?? "",
      content: input.content ?? "",
    });
    return this.getCurriculum(curriculum_id);
  }
  async reviewSourceVersion(curriculum_id: string, source_id: string, decision: "APPROVED" | "REJECTED", reason: string, cmd: Command, reviewedExactVersion = false): Promise<Curriculum> {
    await this.call("POST", `/curricula/${encodeURIComponent(curriculum_id)}/sources/${encodeURIComponent(source_id)}/review`, {
      idempotency_key: cmd.idempotency_key,
      expected_revision: cmd.expected_revision,
      decision,
      reason,
      reviewed_exact_version: reviewedExactVersion,
    });
    return this.getCurriculum(curriculum_id);
  }
  async retryIngestion(curriculum_id: string, job_id: string, cmd: Command): Promise<Curriculum> {
    await this.call("POST", `/curricula/${encodeURIComponent(curriculum_id)}/ingestion-jobs/${encodeURIComponent(job_id)}/retry`, { idempotency_key: cmd.idempotency_key });
    return this.getCurriculum(curriculum_id);
  }
  async saveObjective(curriculum_id: string, subtopic_id: string, objective: CurriculumObjective, cmd: Command): Promise<Curriculum> {
    await this.call("PUT", `/curricula/${encodeURIComponent(curriculum_id)}/subtopics/${encodeURIComponent(subtopic_id)}/objective`, {
      idempotency_key: cmd.idempotency_key,
      expected_revision: cmd.expected_revision,
      description: objective.description,
      assessment_criteria: objective.assessment_criteria,
    });
    return this.getCurriculum(curriculum_id);
  }
  // ADR-050: draft revisions of a published curriculum, and editing a draft's path.
  async createCurriculumRevision(curriculum_id: string, cmd: Command): Promise<Curriculum> {
    const r = await this.call<{ curriculum_id: string }>("POST", `/curricula/${encodeURIComponent(curriculum_id)}/revisions`, { idempotency_key: cmd.idempotency_key });
    return this.getCurriculum(r.curriculum_id);
  }
  async removeCurriculumSource(curriculum_id: string, curriculum_source_id: string, cmd: Command): Promise<Curriculum> {
    await this.call("DELETE", `/curricula/${encodeURIComponent(curriculum_id)}/sources/${encodeURIComponent(curriculum_source_id)}`, { idempotency_key: cmd.idempotency_key, expected_revision: cmd.expected_revision });
    return this.getCurriculum(curriculum_id);
  }
  async setSubtopicIncluded(curriculum_id: string, subtopic_id: string, included: boolean, cmd: Command): Promise<Curriculum> {
    await this.call("POST", `/curricula/${encodeURIComponent(curriculum_id)}/subtopics/${encodeURIComponent(subtopic_id)}/inclusion`, { idempotency_key: cmd.idempotency_key, expected_revision: cmd.expected_revision, included });
    return this.getCurriculum(curriculum_id);
  }
  async moveCurriculumTopic(curriculum_id: string, topic_id: string, direction: "UP" | "DOWN", cmd: Command): Promise<Curriculum> {
    await this.call("POST", `/curricula/${encodeURIComponent(curriculum_id)}/topics/${encodeURIComponent(topic_id)}/move`, { idempotency_key: cmd.idempotency_key, expected_revision: cmd.expected_revision, direction });
    return this.getCurriculum(curriculum_id);
  }
  async publishCurriculum(curriculum_id: string, cmd: Command): Promise<Curriculum> {
    await this.call("POST", `/curricula/${encodeURIComponent(curriculum_id)}/publish`, { idempotency_key: cmd.idempotency_key, expected_revision: cmd.expected_revision });
    return this.getCurriculum(curriculum_id);
  }

  // ---------------------------------------------------------------- Knowledge (ADR-040): read-only, approved versions only
  async getTimeline(): Promise<TimelineEntry[]> {
    return this.call<TimelineEntry[]>("GET", "/knowledge/timeline");
  }
  async listDocumentVersions(): Promise<DocumentVersion[]> {
    return this.call<DocumentVersion[]>("GET", "/knowledge/documents");
  }
  async getSourceContent(document_version_id: string): Promise<{ version: DocumentVersion; text: string }> {
    return this.call<{ version: DocumentVersion; text: string }>("GET", `/knowledge/documents/${encodeURIComponent(document_version_id)}`);
  }

  // ---------------------------------------------------------------- Exit KT (owner decisions 2026-10-10, ADR-039)
  /** The case this persona takes part in (null when none), filtered by their role on the server. */
  async getExitKtCase(): Promise<ExitKtCase | null> {
    return this.call<ExitKtCase | null>("GET", "/exit-kt/case");
  }
  private kt(path: string, cmd: Command | undefined, body: Record<string, unknown> = {}, method: "POST" | "PATCH" = "POST"): Promise<ExitKtCase> {
    return this.call<ExitKtCase>(method, `/exit-kt/${path}`, { ...(cmd ? { idempotency_key: cmd.idempotency_key, expected_revision: cmd.expected_revision } : {}), ...body });
  }
  /** The manager opens a case (docs/32). */
  async createExitKtCase(input: { employee_id: string; case_kind: CaseKind; final_working_date?: string }, cmd: Command): Promise<ExitKtCase> {
    return this.call<ExitKtCase>("POST", "/exit-kt/cases", { idempotency_key: cmd.idempotency_key, employee_id: input.employee_id, case_kind: input.case_kind, final_working_date: input.final_working_date || null });
  }
  async addKnowledgeItem(title: string, description: string, cmd: Command): Promise<ExitKtCase> {
    return this.kt("knowledge-items", cmd, { title, description });
  }
  async linkExistingKnowledge(kt_item_id: string, cmd: Command): Promise<ExitKtCase> {
    return this.kt(`knowledge-items/${encodeURIComponent(kt_item_id)}/link-existing`, cmd);
  }
  async reviewFinding(finding_id: string, decision: "CONFIRM" | "DISMISS" | "RESOLVE", reason: string, cmd: Command): Promise<ExitKtCase> {
    return this.kt(`findings/${encodeURIComponent(finding_id)}/review`, cmd, { decision, reason });
  }
  /** The knowledge-transfer graph (docs/32): discovery, targeted interview, drafts, recommendations, questions. */
  async runDiscovery(): Promise<ExitKtCase> {
    return this.kt("discovery", undefined, { idempotency_key: `discover-${Date.now()}` });
  }
  async startInterview(kt_item_id: string, consent: boolean, cmd: Command): Promise<ExitKtCase> {
    return this.kt(`knowledge-items/${encodeURIComponent(kt_item_id)}/interview`, undefined, { idempotency_key: cmd.idempotency_key, consent });
  }
  async sendInterviewMessage(interview_id: string, input: TurnInput): Promise<ExitKtCase> {
    return this.kt(`interviews/${encodeURIComponent(interview_id)}/messages`, undefined, { text: input.text });
  }
  async draftArtifactFromInterview(interview_id: string): Promise<ExitKtCase> {
    return this.kt(`interviews/${encodeURIComponent(interview_id)}/draft`, undefined);
  }
  async askPackage(input: TurnInput): Promise<ExitKtCase> {
    return this.kt("package/questions", undefined, { idempotency_key: input.idempotency_key, text: input.text });
  }
  async askKtCopilot(input: TurnInput): Promise<ExitKtCase> {
    return this.kt("copilot", undefined, { idempotency_key: input.idempotency_key, text: input.text });
  }
  async recommendSuccessors(cmd: Command): Promise<ExitKtCase> {
    return this.kt("recommendations", undefined, { idempotency_key: cmd.idempotency_key });
  }
  async decidePlanItem(item_id: string, decision: "ACCEPT" | "DECLINE", required: boolean, cmd: Command): Promise<ExitKtCase> {
    return this.kt(`plan/${encodeURIComponent(item_id)}/${decision === "ACCEPT" ? "accept" : "decline"}`, cmd, { required });
  }
  async assignSuccessor(successor_employee_id: string, cmd: Command): Promise<ExitKtCase> {
    return this.kt("successor", cmd, { successor_employee_id });
  }
  async createManualArtifact(kt_item_id: string, title: string, content: string, cmd: Command): Promise<ExitKtCase> {
    return this.kt(`knowledge-items/${encodeURIComponent(kt_item_id)}/artifacts`, cmd, { title, content });
  }
  async editArtifact(artifact_id: string, content: string, cmd: Command): Promise<ExitKtCase> {
    return this.kt(`artifacts/${encodeURIComponent(artifact_id)}`, cmd, { content }, "PATCH");
  }
  async submitArtifact(artifact_id: string, artifact_revision_id: string, audience: "TEAM" | "ORGANIZATION", cmd: Command): Promise<ExitKtCase> {
    return this.kt(`artifacts/${encodeURIComponent(artifact_id)}/submit`, cmd, { artifact_revision_id, audience });
  }
  async decideArtifact(artifact_id: string, artifact_revision_id: string, decision: "APPROVE" | "REQUEST_REVISION" | "REJECT", comment: string, cmd: Command): Promise<ExitKtCase> {
    return this.kt(`artifacts/${encodeURIComponent(artifact_id)}/decision`, cmd, { artifact_revision_id, decision, comment });
  }
  async promoteArtifact(artifact_id: string, artifact_revision_id: string, cmd: Command): Promise<ExitKtCase> {
    return this.kt(`artifacts/${encodeURIComponent(artifact_id)}/promote`, cmd, { artifact_revision_id });
  }
  async editTransfer(transfer_id: string, final_owner_employee_id: string, cmd: Command): Promise<ExitKtCase> {
    return this.kt(`transfers/${encodeURIComponent(transfer_id)}`, cmd, { final_owner_employee_id }, "PATCH");
  }
  async reviewEffectiveTime(transfer_id: string, cmd: Command): Promise<ExitKtCase> {
    return this.kt(`transfers/${encodeURIComponent(transfer_id)}/effective-time`, cmd);
  }
  async confirmTransfer(transfer_id: string, cmd: Command): Promise<ExitKtCase> {
    return this.kt(`transfers/${encodeURIComponent(transfer_id)}/confirm`, cmd);
  }
  async assemblePackage(cmd: Command): Promise<ExitKtCase> {
    return this.kt("package/assemble", cmd);
  }
  async submitPackage(cmd: Command): Promise<ExitKtCase> {
    return this.kt("package/submit", cmd);
  }
  async decidePackage(decision: "APPROVE" | "REJECT", comment: string, cmd: Command): Promise<ExitKtCase> {
    return this.kt("package/decision", cmd, { decision, comment });
  }
  async receivePackage(package_version_id: string, cmd: Command): Promise<ExitKtCase> {
    return this.kt(`package/versions/${encodeURIComponent(package_version_id)}/receipt`, { idempotency_key: cmd.idempotency_key });
  }
  async resolveChecklistItem(item_id: string, evidence_ref: string, cmd: Command): Promise<ExitKtCase> {
    return this.kt(`checklist/${encodeURIComponent(item_id)}/resolve`, cmd, { evidence_ref });
  }
  async recordChecklistException(item_id: string, reason: string, cmd: Command): Promise<ExitKtCase> {
    return this.kt(`checklist/${encodeURIComponent(item_id)}/exception`, cmd, { reason });
  }
  async completeExitKtCase(cmd: Command): Promise<ExitKtCase> {
    return this.kt("complete", cmd);
  }

  // ---------------------------------------------------------------- Shift Handover (owner decisions 2026-10-10)
  private handoverId: string | null = null;
  /** POST /handovers/active: the handover from the shift in progress (its lead's first open creates the draft). */
  async getHandoverWorkspace(): Promise<HandoverWorkspace> {
    const w = await this.call<HandoverWorkspace>("POST", "/handovers/active", undefined, false);
    this.handoverId = w.handover_id || null;
    return w;
  }
  private async handover(): Promise<string> {
    const id = this.handoverId ?? (await this.getHandoverWorkspace()).handover_id;
    // No draft yet (the shift in progress' lead hasn't opened it): say so, never call /handovers//…
    if (!id) throw new WorkWeaveError({ code: "GUARD_FAILED", message: "There's no handover for the shift in progress yet. Its lead starts it by opening Shift Handover.", retryable: false }, "client");
    return id;
  }
  async editDraftSection(section_id: string, content: string, declaration: { kind?: "UNKNOWN_WITH_FOLLOW_UP" | "NOT_APPLICABLE"; reason?: string }, cmd: Command): Promise<HandoverWorkspace> {
    const id = await this.handover();
    return this.call<HandoverWorkspace>("PATCH", `/handovers/${id}/sections/${encodeURIComponent(section_id)}`, {
      idempotency_key: cmd.idempotency_key,
      expected_revision: cmd.expected_revision,
      content,
      declaration: declaration.kind ?? null,
      reason: declaration.reason ?? "",
    });
  }
  async acceptSuggestion(suggestion_id: string, mode: "APPLY" | "REPORT_ONLY" | "VALIDATE_COMPLETION", cmd: Command, note?: string): Promise<HandoverWorkspace> {
    const id = await this.handover();
    return this.call<HandoverWorkspace>("POST", `/handover-suggestions/${encodeURIComponent(suggestion_id)}/accept`, { idempotency_key: cmd.idempotency_key, expected_revision: cmd.expected_revision, handover_id: id, mode, note: note ?? null });
  }
  async ignoreSuggestion(suggestion_id: string, cmd: Command): Promise<HandoverWorkspace> {
    const id = await this.handover();
    return this.call<HandoverWorkspace>("POST", `/handover-suggestions/${encodeURIComponent(suggestion_id)}/ignore`, { idempotency_key: cmd.idempotency_key, expected_revision: cmd.expected_revision, handover_id: id });
  }
  async createTemplateVersion(sections: TemplateSectionInput[], cmd: Command): Promise<HandoverWorkspace> {
    const id = await this.handover();
    return this.call<HandoverWorkspace>("POST", `/handovers/${id}/template-versions`, { idempotency_key: cmd.idempotency_key, expected_revision: cmd.expected_revision, sections });
  }
  async publishHandover(cmd: Command): Promise<HandoverWorkspace> {
    const id = await this.handover();
    return this.call<HandoverWorkspace>("POST", `/handovers/${id}/publish`, { idempotency_key: cmd.idempotency_key, expected_revision: cmd.expected_revision });
  }
  async confirmHandoverReceipt(publication_id: string, cmd: Command): Promise<HandoverWorkspace> {
    return this.call<HandoverWorkspace>("POST", `/handover-publications/${encodeURIComponent(publication_id)}/receipt`, { idempotency_key: cmd.idempotency_key });
  }
  async acknowledgeCompletion(cycle_id: string, decision: "ACKNOWLEDGE" | "DISPUTE", comment: string, cmd: Command): Promise<HandoverWorkspace> {
    return this.call<HandoverWorkspace>("POST", `/handover-acknowledgements/${encodeURIComponent(cycle_id)}/${decision === "ACKNOWLEDGE" ? "acknowledge" : "dispute"}`, { idempotency_key: cmd.idempotency_key, comment });
  }
  /** A turn with the handover graph (docs/31); empty text asks for the incoming lead's brief. */
  async askHandoverCopilot(input: TurnInput): Promise<HandoverWorkspace> {
    const id = await this.handover();
    return this.call<HandoverWorkspace>("POST", `/handovers/${id}/copilot`, { idempotency_key: input.idempotency_key, text: input.text });
  }
  async runHandoverGapCheck(cmd: Command): Promise<HandoverWorkspace> {
    const id = await this.handover();
    return this.call<HandoverWorkspace>("POST", `/handovers/${id}/gap-check`, { idempotency_key: cmd.idempotency_key });
  }
  async draftHandoverSections(section_ids: string[]): Promise<HandoverSectionDraft[]> {
    const id = await this.handover();
    return (await this.call<{ drafts: HandoverSectionDraft[] }>("POST", `/handovers/${id}/section-drafts`, { section_ids }, false)).drafts;
  }
  async getAssignmentExplanation(work_item_id: string): Promise<AssignmentExplanation> {
    return this.call<AssignmentExplanation>("GET", `/work-items/${encodeURIComponent(work_item_id)}/assignment`);
  }
  async getAssignmentCandidates(work_item_id: string): Promise<AssignmentCandidate[]> {
    return this.call<AssignmentCandidate[]>("GET", `/work-items/${encodeURIComponent(work_item_id)}/assignment-candidates`);
  }
  async reassignWorkItem(work_item_id: string, employee_id: string, cmd: Command): Promise<AssignmentExplanation> {
    return this.call<AssignmentExplanation>("POST", `/work-items/${encodeURIComponent(work_item_id)}/assignee`, { idempotency_key: cmd.idempotency_key, expected_revision: cmd.expected_revision, employee_id });
  }
  async getCalendarStatus(): Promise<CalendarStatus> {
    return this.call<CalendarStatus>("GET", "/calendar/status");
  }
  async streamWorkReplySpeech(message_id: string): Promise<PcmStream> {
    const id = await this.openWorkSessionId();
    return this.pcm(`${BASE}/work-sessions/${id}/voice/speech/${encodeURIComponent(message_id)}/stream`);
  }
  async getHandoverVoiceListenGrant(mode: ListenMode): Promise<VoiceGrant> {
    return this.call<VoiceGrant>("POST", "/handover/voice/listen", { mode }, false);
  }
  async streamHandoverReplySpeech(message_id: string): Promise<PcmStream> {
    return this.pcm(`${BASE}/handover/voice/speech/${encodeURIComponent(message_id)}/stream`);
  }
  async getKtVoiceListenGrant(mode: ListenMode): Promise<VoiceGrant> {
    return this.call<VoiceGrant>("POST", "/exit-kt/voice/listen", { mode }, false);
  }
  async streamKtReplySpeech(message_id: string): Promise<PcmStream> {
    return this.pcm(`${BASE}/exit-kt/voice/speech/${encodeURIComponent(message_id)}/stream`);
  }
  /**
   * A reply read aloud sentence by sentence (?part=N; the first response says how many parts in
   * X-Speech-Parts). Firebase Hosting delivers a response only once it is complete, so asking for
   * the whole reply would play nothing until all of it was generated. Each part arrives whole and is
   * handed to the player as one piece, which also avoids the clicks Chrome makes where many small
   * pieces join. The next part is fetched while the current one plays; the stream ends only after
   * the last part, so the reply counts as playing (and hands-free stays paused) between parts.
   * A server without parts sends the whole reply as before.
   */
  private async pcm(url: string): Promise<PcmStream> {
    const first = await this.pcmPart(`${url}?part=0`);
    const rate = Number(first.headers.get("x-sample-rate")) || 24000;
    const total = Number(first.headers.get("x-speech-parts"));
    if (!(total >= 1)) return { rate, body: first.body! };
    let next = 0;
    let pending: Response | null = first;
    let abort: AbortController | null = null;
    const body = new ReadableStream<Uint8Array>(
      {
        pull: async (c) => {
          try {
            if (!pending) {
              abort = new AbortController();
              pending = await this.pcmPart(`${url}?part=${next}`, abort.signal);
            }
            const part = new Uint8Array(await pending.arrayBuffer());
            pending = null;
            next += 1;
            if (part.length) c.enqueue(part);
            if (next >= total) c.close();
          } catch (e) {
            c.error(e); // the player stops; the reply stays on screen
          }
        },
        cancel: () => {
          abort?.abort();
          void pending?.body?.cancel().catch(() => undefined);
          pending = null;
        },
      },
      { highWaterMark: 1 }, // one part ahead: fetched while the one before it plays
    );
    return { rate, body };
  }
  private async pcmPart(url: string, signal?: AbortSignal): Promise<Response> {
    let res: Response;
    try {
      res = await fetch(url, { credentials: "same-origin", cache: "no-store", signal });
    } catch {
      throw new WorkWeaveError({ code: "DEPENDENCY_UNAVAILABLE", message: FAILED, retryable: true }, "network");
    }
    if (!res.ok || !res.body) {
      const json = (await res.json().catch(() => null)) as { request_id?: string; error?: ApiError } | null;
      throw new WorkWeaveError(json?.error ?? { code: "DEPENDENCY_UNAVAILABLE", message: plainStatus(res.status), retryable: res.status >= 500 }, json?.request_id ?? "unknown");
    }
    return res;
  }
  async getReplySpeech(message_id: string): Promise<Blob> {
    const id = await this.openSessionId();
    let res: Response;
    try {
      res = await fetch(`${BASE}/onboarding/sessions/${id}/voice/speech/${encodeURIComponent(message_id)}`, { credentials: "same-origin", cache: "no-store" });
    } catch {
      throw new WorkWeaveError({ code: "DEPENDENCY_UNAVAILABLE", message: FAILED, retryable: true }, "network");
    }
    if (!res.ok) {
      const json = (await res.json().catch(() => null)) as { request_id?: string; error?: ApiError } | null;
      throw new WorkWeaveError(json?.error ?? { code: "DEPENDENCY_UNAVAILABLE", message: plainStatus(res.status), retryable: res.status >= 500 }, json?.request_id ?? "unknown");
    }
    return res.blob();
  }
}

const WIRED = new Set<string>(["listScenarios", "startDemoSession", "getLocalDemoRun", "getSession", "endSession", "listPersonas", "switchPersona", "getCapabilities", "getOnboarding", "getSupervisorProgress", "startOnboardingSession", "getOnboardingSession", "sendOnboardingTurn", "continueOnboarding", "pauseOnboarding", "listCurricula", "getCurriculum", "getVoiceListenGrant", "getReplySpeech", "streamReplySpeech", "streamWorkReplySpeech", "getHandoverVoiceListenGrant", "streamHandoverReplySpeech", "getKtVoiceListenGrant", "streamKtReplySpeech", "getCalendarStatus", "getShiftClock", "advanceShiftClock", "listReviews", "decideMemoryDraft", "createCurriculum", "stageCurriculumSource", "reviewSourceVersion", "retryIngestion", "saveObjective", "publishCurriculum", "getTimeline", "listDocumentVersions", "getSourceContent", "getExitKtCase", "createExitKtCase", "addKnowledgeItem", "linkExistingKnowledge", "reviewFinding", "runDiscovery", "startInterview", "sendInterviewMessage", "draftArtifactFromInterview", "askPackage", "createManualArtifact", "editArtifact", "submitArtifact", "decideArtifact", "promoteArtifact", "editTransfer", "reviewEffectiveTime", "confirmTransfer", "assemblePackage", "submitPackage", "decidePackage", "receivePackage", "resolveChecklistItem", "recordChecklistException", "completeExitKtCase", "recommendSuccessors", "decidePlanItem", "askKtCopilot", "assignSuccessor", "getHandoverWorkspace", "editDraftSection", "acceptSuggestion", "ignoreSuggestion", "createTemplateVersion", "publishHandover", "confirmHandoverReceipt", "acknowledgeCompletion", "askHandoverCopilot", "runHandoverGapCheck", "draftHandoverSections", "watchWork", "getAssignmentExplanation", "getAssignmentCandidates", "reassignWorkItem", "startWorkSession", "getWorkDashboard", "listWorkItems", "listWorkEvents", "sendWorkMessage", "getGuidance", "getWorkVoiceListenGrant", "reportWorkEvent", "getTicketSystem", "updateTicketStatus", "listProposals", "getProposal", "editProposalItem", "confirmProposal", "rejectProposal", "createMemoryDraft", "listMyMemoryDrafts", "submitMemoryDraft", "deleteMemoryDraft", "getAccess", "redeemAccessCode", "leaveAccess", "getDemoUsage", "listNotifications", "markNotificationRead", "createCurriculumRevision", "removeCurriculumSource", "setSubtopicIncluded", "moveCurriculumTopic"] satisfies Wired[]);
const RUNTIME = new Set(["mode", "subscribe", "getVersion", "isLoaded", "loadError", "peekSession", "peekPersonas", "unreadCount"]);

/** Methods outside this slice reject honestly instead of returning fixture data. */
export function createHttpClient(): ClientRuntime {
  const core = new HttpCore();
  return new Proxy(core, {
    get(target, prop, receiver) {
      if (typeof prop !== "string" || WIRED.has(prop) || RUNTIME.has(prop) || prop === "then") {
        const v = Reflect.get(target, prop, receiver);
        return typeof v === "function" ? v.bind(target) : v;
      }
      return () =>
        Promise.reject(
          new WorkWeaveError({ code: "CAPABILITY_UNAVAILABLE", message: "This screen isn't connected to the WorkWeave backend yet.", retryable: false }, "client"),
        );
    },
  }) as unknown as ClientRuntime & WorkWeaveClient;
}
