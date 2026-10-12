"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useOnChange } from "@/lib/preview/use-on-change";
import { RequireSession } from "@/components/shell/AppShell";
import { ChatErrorNote, ChatHeader, Composer, ExamplePrompts, ScriptPrompts, SourceDrawer, Transcript, type ChatMessageView } from "@/components/chat";
import { companionExamples, ticketOf } from "@/features/chat/examples";
import { Dialog, ErrorNotice, Loading, PageHeader, PageError, Status } from "@/components/ui";
import { newKey, useClient, useCommand, useResource, useRuntime, useSession } from "@/lib/preview/client-context";
import { VoiceComposer } from "@/features/onboarding/VoiceComposer";
import { LiveListener, MicCapture } from "@/lib/voice/live-listener";
import { playCue, prefersQuiet } from "@/lib/voice/cues";
import { micPermission } from "@/lib/voice/mic-permission";
import { SPEEDS, loadPrefs, savePrefs, type VoicePrefs } from "@/lib/voice/prefs";
import { resetTime } from "@/lib/limits";
import { Canvas, Dashboard, Delegation, ItemDetail, canvasTitle } from "@/features/companion/canvases";
import { useReadAloud } from "@/features/companion/useReadAloud";
import { CalendarConnect } from "@/features/companion/CalendarConnect";
import type { Citation, MemoryDraft, WorkItem, WorkMessage } from "@/types/contracts";

export default function CompanionPage() {
  return (
    <RequireSession>
      <Companion />
    </RequireSession>
  );
}

function Companion() {
  const { session } = useSession();
  const pid = session?.persona.employee_id;
  const view = useResource((c) => c.startWorkSession(), [pid]);
  const dash = useResource((c) => c.getWorkDashboard(), [pid]);
  const cmd = useCommand();
  const client = useClient();
  const api = useRuntime().mode === "http";
  // API mode: voice transport works now; the Companion's AI engine isn't connected yet.
  const caps = useResource((c) => (api ? c.getCapabilities() : Promise.resolve(null)), [api]);
  const voiceAvailable = caps.data?.voice_adapter === "AVAILABLE";
  // Example prompts name a real teammate (for the lead's delegation example).
  const people = useResource((c) => (api ? c.listPersonas() : Promise.resolve([])), [pid, api]);
  const [voicePrefs, setVoicePrefs] = useState<VoicePrefs>(() => loadPrefs(prefersQuiet()));
  const updatePrefs = (patch: Partial<VoicePrefs>) => setVoicePrefs(savePrefs(patch, prefersQuiet()));
  // API: stay current when someone else changes the team's work (e.g. the shift lead reassigns a ticket).
  useEffect(() => (api ? client.watchWork() : undefined), [api, client]);

  // Replies read aloud like onboarding's tutor (ADR-034): new replies only, the opening brief once.
  const voice = useReadAloud({
    client,
    enabled: api && view.data?.assistant?.status === "ok",
    sessionId: view.data?.work_session_id,
    transcript: view.data?.transcript,
    readAloud: voicePrefs.readAloud,
    voiceAvailable,
    capsLoading: caps.loading,
    speed: voicePrefs.speed,
  });
  // Read-aloud commands said in the chat ("stop reading", "speak slower"): applied once, when the reply
  // arrives; history on screen at a reload is never replayed.
  const applyVoiceCommand = (a: NonNullable<WorkMessage["client_action"]>) => {
    const speeds = SPEEDS;
    const at = speeds.indexOf(voicePrefs.speed);
    if (a === "READ_ALOUD_ON") updatePrefs({ readAloud: true, readAloudOffered: true });
    else if (a === "READ_ALOUD_OFF") {
      voice.stop();
      updatePrefs({ readAloud: false });
    } else if (a === "STOP_READING") voice.stop();
    else if (a === "SPEAK_SLOWER") updatePrefs({ speed: speeds[Math.max(0, at - 1)]! });
    else if (a === "SPEAK_FASTER") updatePrefs({ speed: speeds[Math.min(speeds.length - 1, at + 1)]! });
    else if (a === "NORMAL_SPEED") updatePrefs({ speed: 1 });
  };
  const lastAction = [...(view.data?.transcript ?? [])].reverse().find((m) => m.sender === "AI");
  const appliedAction = useRef<string | null | undefined>(undefined);
  useEffect(() => {
    if (!view.data) return;
    const id = lastAction?.message_id ?? null;
    if (appliedAction.current === undefined) {
      appliedAction.current = id;
      return;
    }
    if (id === appliedAction.current) return;
    appliedAction.current = id;
    const a = lastAction?.client_action;
    if (!a) return;
    void Promise.resolve().then(() => applyVoiceCommand(a)); // after this render
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view.data, lastAction?.message_id]);
  const [cite, setCite] = useState<Citation | null>(null);
  const [manualReport, setManualReport] = useState<WorkItem | null>(null);
  const [detailId, setDetailId] = useState<string | null>(null);
  const [proposalId, setProposalId] = useState<string | null>(null);
  const [capture, setCapture] = useState(false);
  // What the companion is doing right now (API): "Finding the right part of the procedure…".
  const [step, setStep] = useState<string | null>(null);

  if (view.loading) return <Loading label="Opening Work Companion" />;
  if (view.error) return <PageError error={view.error} onRetry={view.reload} />;
  const v = view.data!;
  const t = session!.scenario.terminology;

  const send = async (text: string, input_kind: "TEXT" | "VOICE_TRANSCRIPT", prompt_id?: string) => {
    setStep(null);
    const r = await cmd.run((c, k) => c.sendWorkMessage({ idempotency_key: k, client_turn_id: newKey("turn"), expected_revision: v.revision, text, input_kind, preview_prompt_id: prompt_id, onProgress: setStep }));
    setStep(null);
    return Boolean(r);
  };
  const messages: ChatMessageView[] = v.transcript.map((m) => ({
    id: m.message_id,
    sender: m.sender,
    text: m.text,
    provenance: m.provenance,
    citations: m.citations,
    meta: (
      <>
        {m.rejected_action && <Status value="REJECTED" label="Action rejected" />}
        {m.link && (
          <Link className="link-btn" href={m.link.href}>
            {m.link.label}
          </Link>
        )}
        {api && voiceAvailable && !voice.limit && m.sender === "AI" && (m.provenance === "WORK_ENGINE" || m.provenance === "BACKEND_RECORD") && (
          <button
            className="link-btn"
            onClick={() => (voice.speaking && voice.speakingId === m.message_id ? voice.stop() : void voice.play(m))}
            aria-label={voice.speaking && voice.speakingId === m.message_id ? "Stop reading this reply" : "Listen to this reply"}
          >
            {voice.speaking && voice.speakingId === m.message_id ? "Stop" : "Listen"}
          </button>
        )}
      </>
    ),
  }));
  // Why the work area shows what it shows: the request that preceded the latest validated view change.
  const viewIdx = v.transcript.findLastIndex((m) => m.ui_action && m.ui_action !== "NO_VIEW_CHANGE" && !m.rejected_action);
  const asked = viewIdx > 0 ? v.transcript.slice(0, viewIdx).findLast((m) => m.sender === "EMPLOYEE")?.text : undefined;
  const reportItem = v.pending_report ? { id: v.pending_report.work_item_id, draft: v.pending_report.draft } : manualReport ? { id: manualReport.work_item_id, draft: "" } : null;

  const canvasName = canvasTitle(v.canvas, t.workItems);
  return (
    <div className="stack">
      <PageHeader
        eyebrow="Your daily workspace"
        title="A clearer picture of your work."
        purpose="Talk with your companion; the work area follows the conversation."
        actions={
          <div className="row">
            {api && (
              <Link className="btn btn-small" href="/companion/tool/" data-tour="ticket-system">
                Open {dash.data?.system_name ?? "ticket system"}
              </Link>
            )}
            <button className="btn btn-small" onClick={() => setCapture(true)} data-tour="capture">
              Capture knowledge
            </button>
          </div>
        }
      />
    <div className="split split--chat-first">
      <div className="stack" style={{ minWidth: 0 }}>
        <section className="panel dash-panel" aria-labelledby="h-dash">
          <p className="eyebrow">
            {session!.scenario.company_name} · {session!.persona.team_name}
          </p>
          <h2 id="h-dash">Your shift at a glance</h2>
          <Dashboard data={dash.data} />
        </section>
        <section className="panel canvas-panel" aria-labelledby="h-canvas" aria-live="polite">
          <div className="canvas-reason">
            <span>
              Showing: {canvasName}
              {asked ? <> · because you asked &ldquo;{asked}&rdquo;</> : " · your starting view"}
            </span>
            {asked && <span className="fixture-tag">Workspace updated</span>}
          </div>
          <div className="canvas-body">
            <h2 id="h-canvas">{canvasName}</h2>
            <Canvas
              view={v.canvas}
              onCite={setCite}
              onReport={(i) => setManualReport(i)}
              actions={api ? { onOpenItem: (i) => setDetailId(i.work_item_id), onOpenProposal: setProposalId } : undefined}
            />
          </div>
        </section>
      </div>
      <aside className="split-aside" aria-label="Conversation">
        <section className="chat chat-tall">
          <ChatHeader
            title="WorkWeave"
            subtitle={api ? (v.assistant?.status === "ok" ? "Here with you while you work" : "Assistant not connected · your work comes from the database") : "Scripted preview · here with you while you work"}
            action={
              <span className="small muted" role="status" aria-live="polite">
                {cmd.pending ? (step ?? "Sending…") : ""}
              </span>
            }
          />
          {api && v.assistant?.status === "unavailable" && (
            <div style={{ padding: "16px 22px 0" }}>
              <div className="notice notice-info" role="note">
                <span className="notice-title">Replies aren&apos;t available yet</span>
                <span>{v.assistant.message}</span>
              </div>
            </div>
          )}
          <Transcript messages={messages} label="Work Companion conversation" onCite={setCite} />
          {/* The "not connected" notice above already explains; a failed send adds one short line, not a second notice. */}
          {cmd.error && api && cmd.error.code === "CAPABILITY_UNAVAILABLE" && v.assistant?.status === "unavailable" ? (
            <p className="small" role="status" style={{ padding: "0 22px", margin: 0 }} data-testid="not-sent">
              {cmd.error.message}
            </p>
          ) : cmd.error && (
            <div style={{ padding: "0 14px" }}>
              <ChatErrorNote error={cmd.error} onRetry={cmd.error.code === "REVISION_CONFLICT" ? () => { cmd.clearError(); view.reload(); } : undefined} onDismiss={cmd.clearError} />
            </div>
          )}
          <ScriptPrompts prompts={v.script_prompts} disabled={cmd.pending} onPick={(p) => void send(p.text, "TEXT", p.prompt_id)} />
          {api && v.assistant?.status === "ok" && (
            <>
              {v.calendar_connect && !cmd.pending && <CalendarConnect connect={v.calendar_connect} onConnected={(retry) => void send(retry, "TEXT")} />}
              {voice.briefWaiting && (
                <div className="notice notice-info" role="note" style={{ margin: "0 14px" }} data-testid="brief-waiting">
                  <span className="notice-title">Your brief is ready</span>
                  <span className="row" style={{ marginTop: 8 }}>
                    <button className="btn btn-small btn-primary" onClick={() => void voice.play(voice.briefWaiting!)}>
                      Hear the brief
                    </button>
                  </span>
                </div>
              )}
              {voiceAvailable && !voicePrefs.readAloud && !voicePrefs.readAloudOffered && !voice.limit && voice.lastReply && (
                <div className="notice notice-info" role="note" style={{ margin: "0 14px" }} data-testid="read-aloud-offer">
                  <span className="notice-title">Hear the companion?</span>
                  <span>The companion can read its replies aloud. You can switch this off any time with &quot;Read replies aloud&quot;.</span>
                  <span className="row" style={{ marginTop: 8 }}>
                    <button
                      className="btn btn-small btn-primary"
                      onClick={() => {
                        updatePrefs({ readAloud: true, readAloudOffered: true });
                        void voice.play(voice.lastReply!);
                      }}
                    >
                      Turn on spoken replies
                    </button>
                    <button className="btn btn-small" onClick={() => updatePrefs({ readAloudOffered: true })}>
                      Not now
                    </button>
                  </span>
                </div>
              )}
              <div className="row" style={{ gap: 12, padding: "0 14px" }}>
                <label className="small row" style={{ gap: 6 }}>
                  <input type="checkbox" role="switch" checked={voicePrefs.readAloud && !voice.limit} disabled={!voiceAvailable || Boolean(voice.limit)} onChange={(e) => updatePrefs({ readAloud: e.target.checked })} />
                  Read replies aloud
                </label>
                <label className="small row" style={{ gap: 6 }} title="Speaking over a reply stops it. Works best with headphones; on speakers the reply can occasionally interrupt itself.">
                  <input type="checkbox" role="switch" checked={voicePrefs.voiceInterrupt} disabled={!voiceAvailable || !voicePrefs.readAloud} onChange={(e) => updatePrefs({ voiceInterrupt: e.target.checked })} />
                  Interrupt by voice (best with headphones)
                </label>
                <label className="small row" style={{ gap: 6 }}>
                  Speed
                  <select value={voicePrefs.speed} disabled={!voiceAvailable} onChange={(e) => updatePrefs({ speed: Number(e.target.value) as VoicePrefs["speed"] })}>
                    {SPEEDS.map((x) => (
                      <option key={x} value={x}>
                        {x}×
                      </option>
                    ))}
                  </select>
                </label>
                {voice.speaking && (
                  <button className="btn btn-small" onClick={voice.stop}>
                    Stop reading
                  </button>
                )}
                {voice.limit && voiceAvailable && (
                  <span className="small muted" role="status" data-testid="speech-limit">
                    Replies are text-only for now: reading aloud has reached its {voice.limit.scope === "RUN" ? "limit for this demo workspace" : "shared demo limit"} today. Back at {resetTime(voice.limit.resets_at)}.
                  </span>
                )}
                {voice.error && !voice.limit && (
                  <span className="small" role="alert">
                    {voice.error}
                  </span>
                )}
              </div>
            </>
          )}
          {api && v.assistant?.status === "ok" && !v.script_prompts.length && (
            <ExamplePrompts
              examples={companionExamples({
                lead: Boolean(dash.data?.can_delegate),
                ticket: ticketOf(dash.data?.priorities[0]),
                teammate: (people.data ?? []).find((p) => p.employee_id !== pid && p.team_role === "MEMBER" && p.team_name === session?.persona.team_name)?.first_name,
              })}
              disabled={cmd.pending}
              onPick={(text) => void send(text, "TEXT")}
            />
          )}
          {api ? (
            <VoiceComposer
              label="Message the Work Companion"
              onSend={(text, kind) => send(text, kind)}
              pending={cmd.pending}
              placeholder="Ask about work or give an instruction"
              voiceAvailable={voiceAvailable}
              unavailableReason={caps.loading ? "Checking voice…" : "Voice isn't configured on this server."}
              speaking={voice.speaking}
              speakingText={voice.speakingText}
              voiceInterrupt={voicePrefs.voiceInterrupt}
              onInterrupt={voice.stop}
              prefs={voicePrefs}
              onPrefsChange={updatePrefs}
              playCue={playCue}
              micPermission={micPermission}
              getGrant={(mode) => client.getWorkVoiceListenGrant(mode)}
              createListener={(grant, events) => new LiveListener(grant, events, { audio: new MicCapture() })}
            />
          ) : (
            <Composer label="Message the Work Companion" onSend={send} pending={cmd.pending} placeholder="Ask about work or give an instruction" />
          )}
        </section>
      </aside>
    </div>
      <SourceDrawer citation={cite} onClose={() => setCite(null)} />
      <ReportDialog
        api={api}
        systemName={dash.data?.system_name}
        target={reportItem}
        onClose={async () => {
          setManualReport(null);
          if (v.pending_report) await cmd.run((c) => c.dismissPendingReport());
        }}
      />
      <CaptureDialog open={capture} onClose={() => setCapture(false)} />
      <ItemDrawer
        id={detailId}
        onClose={() => setDetailId(null)}
        onReport={(i) => {
          setDetailId(null);
          setManualReport(i);
        }}
      />
      <Dialog open={Boolean(proposalId)} title="Delegation proposal" variant="drawer" onClose={() => setProposalId(null)}>
        {proposalId && <Delegation id={proposalId} />}
      </Dialog>
    </div>
  );
}

/** API mode: an item's details and timeline over the briefing (the canvas itself doesn't change). */
function ItemDrawer({ id, onClose, onReport }: { id: string | null; onClose: () => void; onReport: (i: WorkItem) => void }) {
  const { session } = useSession();
  const items = useResource((c) => (id ? c.listWorkItems() : Promise.resolve([])), [session?.persona.employee_id, id]);
  const item = items.data?.find((i) => i.work_item_id === id);
  return (
    <Dialog open={Boolean(id)} title={item ? `${item.external_id} details` : "Work item"} variant="drawer" onClose={onClose}>
      {items.loading ? <Loading /> : item ? <ItemDetail item={item} onReport={onReport} /> : <p className="muted">That item isn&apos;t available to you.</p>}
    </Dialog>
  );
}

function ReportDialog({ target, onClose, api, systemName }: { target: { id: string; draft: string } | null; onClose: () => void; api: boolean; systemName?: string }) {
  const cmd = useCommand();
  const items = useResource((c) => c.listWorkItems(), [target?.id]);
  const [text, setText] = useState("");
  const [kind, setKind] = useState<"COMMENTED" | "REPORTED_COMPLETE" | "BLOCKED">("COMMENTED");
  useOnChange(`${target?.id}|${target?.draft}`, () => {
    setText(target?.draft ?? "");
    setKind(target?.draft?.toLowerCase().includes("done") ? "REPORTED_COMPLETE" : "COMMENTED");
  });
  const item = items.data?.find((i) => i.work_item_id === target?.id);
  return (
    <Dialog
      open={Boolean(target)}
      title={`Report on ${item?.external_id ?? "work item"}`}
      onClose={onClose}
      dirty={text !== (target?.draft ?? "")}
      footer={
        <>
          <button className="btn" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn btn-primary"
            disabled={cmd.pending || !text.trim()}
            onClick={async () => {
              const r = await cmd.run((c, k) => c.reportWorkEvent(target!.id, kind, text, { idempotency_key: k, expected_revision: item?.revision }));
              if (r) onClose();
            }}
          >
            {cmd.pending ? "Submitting…" : "Submit report"}
          </button>
        </>
      }
    >
      {api ? (
        <p className="small muted">
          A report tells your team what you did or saw. It doesn&apos;t change the ticket: update it in the {systemName ?? "ticket system"}, and WorkWeave matches the two.
        </p>
      ) : (
        <p className="small muted">A report records what you did or saw. It doesn&apos;t complete the item, change a published handover, or share knowledge.</p>
      )}
      <fieldset>
        <legend>Report type</legend>
        <label className="choice">
          <input type="radio" checked={kind === "COMMENTED"} onChange={() => setKind("COMMENTED")} /> Progress update
        </label>
        {api && (
          <label className="choice">
            <input type="radio" checked={kind === "BLOCKED"} onChange={() => setKind("BLOCKED")} /> I&apos;m blocked
          </label>
        )}
        <label className="choice">
          <input type="radio" checked={kind === "REPORTED_COMPLETE"} onChange={() => setKind("REPORTED_COMPLETE")} />{" "}
          {api ? "I'm done (it stays on your list until the ticket system shows it resolved)" : "I think this is complete (your lead validates it)"}
        </label>
      </fieldset>
      <div className="field">
        <label htmlFor="report-text">What happened</label>
        <textarea id="report-text" value={text} onChange={(e) => setText(e.target.value)} rows={4} />
        <span className="hint">Keep unverified causes marked as unknown.</span>
      </div>
      {cmd.error && <ErrorNotice error={cmd.error} />}
    </Dialog>
  );
}

function CaptureDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const cmd = useCommand();
  const drafts = useResource((c) => c.listMyMemoryDrafts(), [open]);
  const [consent, setConsent] = useState(false);
  const [step, setStep] = useState<"notice" | "write">("notice");
  const [text, setText] = useState("");
  const [audience, setAudience] = useState<MemoryDraft["requested_audience"]>("PRIVATE");
  useOnChange(open, () => {
    if (!open) {
      setStep("notice");
      setConsent(false);
      setText("");
    }
  });
  return (
    <Dialog open={open} title="Capture reusable knowledge" onClose={onClose} dirty={text.length > 0}>
      {step === "notice" ? (
        <>
          <div className="notice notice-info">
            <span className="notice-title">Before you start</span>
            <span>
              <b>Purpose:</b> save an explanation others might reuse. <b>Audience:</b> only you, until you submit it for review. <b>Retention:</b> typed text only; no audio is recorded. Ordinary chat isn&apos;t captured.
            </span>
          </div>
          <label className="choice">
            <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
            <span>I understand and want to start a private knowledge note.</span>
          </label>
          <div className="row">
            <button className="btn btn-primary" disabled={!consent} onClick={() => setStep("write")}>
              Start note
            </button>
          </div>
        </>
      ) : (
        <>
          <p className="small muted">Automatic extraction isn&apos;t connected, so write the note yourself. Mark anything unverified as reported.</p>
          <div className="field">
            <label htmlFor="cap-text">Explanation</label>
            <textarea id="cap-text" rows={5} value={text} onChange={(e) => setText(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="cap-aud">Who should see it after review</label>
            <select id="cap-aud" value={audience} onChange={(e) => setAudience(e.target.value as MemoryDraft["requested_audience"])}>
              <option value="PRIVATE">Only me (keep private)</option>
              <option value="TEAM">My team</option>
              <option value="ORGANIZATION">Organization</option>
            </select>
          </div>
          {cmd.error && <ErrorNotice error={cmd.error} />}
          <div className="row">
            <button
              className="btn btn-primary"
              disabled={cmd.pending || !text.trim()}
              onClick={async () => {
                const r = await cmd.run((c, k) => c.createMemoryDraft(text, audience, { idempotency_key: k }));
                if (r) setText("");
              }}
            >
              Save private draft
            </button>
          </div>
        </>
      )}
      <section className="stack-s">
        <h3>Your knowledge notes</h3>
        {(drafts.data ?? []).length === 0 && <p className="small muted">No notes yet.</p>}
        {(drafts.data ?? []).map((d) => (
          <div key={d.draft_id} className="list-item">
            <div className="row-between">
              <Status value={d.status} />
              <span className="small muted">Audience: {d.requested_audience.toLowerCase()}</span>
            </div>
            <p className="small">{d.content}</p>
            {d.review_comment && <p className="small muted">Reviewer: {d.review_comment}</p>}
            {d.status === "DRAFT" && (
              <div className="row">
                <button className="btn btn-small" disabled={cmd.pending || d.requested_audience === "PRIVATE"} onClick={() => void cmd.run((c, k) => c.submitMemoryDraft(d.draft_id, { idempotency_key: k, expected_revision: d.revision }))}>
                  Submit for review
                </button>
                <button className="btn btn-small btn-danger" disabled={cmd.pending} onClick={() => void cmd.run((c, k) => c.deleteMemoryDraft(d.draft_id, { idempotency_key: k }))}>
                  Delete
                </button>
              </div>
            )}
          </div>
        ))}
      </section>
    </Dialog>
  );
}
