"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { RequireSession } from "@/components/shell/AppShell";
import { ChatErrorNote, ChatHeader, Composer, ExamplePrompts, ScriptPrompts, SourceDrawer, Transcript, type ChatMessageView } from "@/components/chat";
import { ONBOARDING_EXAMPLES } from "@/features/chat/examples";
import { Dialog, ErrorNotice, Loading, PageHeader, PageError, Status, humanize } from "@/components/ui";
import { newKey, useClient, useCommand, useResource, useRuntime, useSession } from "@/lib/preview/client-context";
import { VoiceComposer } from "@/features/onboarding/VoiceComposer";
import { LiveListener, MicCapture, ReplySpeaker } from "@/lib/voice/live-listener";
import { playCue, prefersQuiet } from "@/lib/voice/cues";
import { micPermission } from "@/lib/voice/mic-permission";
import { SPEEDS, loadPrefs, markFreshStart, savePrefs, takeFreshStart, type VoicePrefs } from "@/lib/voice/prefs";
import type { WorkWeaveClient } from "@/lib/clients/WorkWeaveClient";
import { LearningPath, pathProgress } from "@/features/onboarding/LearningPath";
import { ReferencePanel } from "@/features/onboarding/ReferencePanel";
import { LOW_REMAINING, blockedFrom, limitOf, resetTime, type Blocked } from "@/lib/limits";
import { companyEntryHref } from "@/lib/preview/use-search";
import { WorkWeaveError, type ApiError, type Citation, type LimitInfo, type OnboardingSessionView, type TranscriptMessage } from "@/types/contracts";

export default function TutorPage() {
  return (
    <RequireSession>
      <Tutor />
    </RequireSession>
  );
}


/** Fetch and play one committed reply; reports progress through the callbacks. */
function playReply(
  client: WorkWeaveClient,
  speaker: ReplySpeaker,
  reply: { message_id: string; text: string },
  rate: number,
  on: { start: (id: string, text: string) => void; done: () => void; error: (message: string, limit?: LimitInfo) => void },
) {
  // Streamed: sound starts as soon as the first audio arrives (~1.5 s), not after the whole reply.
  return client
    .streamReplySpeech(reply.message_id)
    .then((stream) => speaker.playStream(stream, { start: () => on.start(reply.message_id, reply.text), done: on.done }, rate))
    .catch((e: { error?: ApiError }) => {
      on.done();
      on.error(e.error?.message ?? "The reply couldn't be read aloud.", limitOf(e.error, "VOICE_SPEECH") ?? undefined);
    });
}

const KIND_CLASS: Partial<Record<TranscriptMessage["kind"], string>> = { CHECK: "msg-check", COMPLETION: "msg-completion" };
const KIND_TAG: Partial<Record<TranscriptMessage["kind"], string>> = {
  CHECK: "Comprehension check",
  HINT: "Hint (doesn't count as an attempt)",
  EXAMPLE: "Example",
  PAUSE: "Paused",
};

function Tutor() {
  const { session } = useSession();
  const pid = session?.persona.employee_id;
  const api = useRuntime().mode === "http";
  const view = useResource((c) => c.getOnboardingSession(), [pid]);
  const cmd = useCommand();
  const client = useClient();
  // API mode: which external capabilities are connected (voice transport, tutor engine).
  const caps = useResource((c) => (api ? c.getCapabilities() : Promise.resolve(null)), [api]);
  const voiceAvailable = caps.data?.voice_adapter === "AVAILABLE";
  // Voice settings remembered in this browser (read aloud, voice interrupt, speed, sounds, …).
  const [voicePrefs, setVoicePrefs] = useState<VoicePrefs>(() => loadPrefs(prefersQuiet()));
  const updatePrefs = (patch: Partial<VoicePrefs>) => setVoicePrefs(savePrefs(patch, prefersQuiet()));
  const readAloud = voicePrefs.readAloud;
  const voiceInterrupt = voicePrefs.voiceInterrupt;
  const [speaking, setSpeaking] = useState(false);
  const [speakingId, setSpeakingId] = useState<string | null>(null);
  const [speakingText, setSpeakingText] = useState("");
  // "Tutor is thinking…": when the current send started, and a clock ticking while it runs.
  const [sendingSince, setSendingSince] = useState<number | null>(null);
  // What the tutor is doing right now (API, connected engine): "Writing a reply…".
  const [tutorStep, setTutorStep] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const [welcomeDismissed, setWelcomeDismissed] = useState(false);
  // Set when the learner cuts a reply off; sent with their next message so the tutor knows.
  const interrupted = useRef(false);
  const [speechError, setSpeechError] = useState<string | null>(null);
  const speaker = useRef<ReplySpeaker | null>(null);
  const lastSpoken = useRef<string | null | undefined>(undefined);
  // The opening of a conversation the learner just started, waiting to be read once voice is known.
  const freshOpening = useRef<string | null>(null);
  const [pinned, setPinned] = useState<Citation | null>(null);
  const [drawer, setDrawer] = useState<Citation | null>(null);
  const [prefs, setPrefs] = useState(false);
  const [sheet, setSheet] = useState(false);
  // Demo caps refused during this visit (the session view reports caps already used up on load).
  const [hits, setHits] = useState<{ tutor_turn?: LimitInfo; voice_listen?: LimitInfo; voice_speech?: LimitInfo }>({});

  const playback = {
    start: (id: string, text: string) => {
      setSpeechError(null);
      setSpeakingId(id);
      setSpeakingText(text);
      setSpeaking(true);
    },
    done: () => {
      setSpeaking(false);
      setSpeakingId(null);
    },
    error: (message: string, limit?: LimitInfo) => {
      if (limit) setHits((h) => ({ ...h, voice_speech: limit }));
      else setSpeechError(message);
    },
  };
  const stopReading = () => {
    speaker.current?.stop();
    setSpeaking(false);
    setSpeakingId(null);
  };

  const v = view.data;
  const speechBlocked = blockedFrom(v?.demo_limits, "voice_speech", hits.voice_speech ?? null);
  const listenBlocked = blockedFrom(v?.demo_limits, "voice_listen", hits.voice_listen ?? null);
  const turnHit = hits.tutor_turn ?? limitOf(cmd.error, "TUTOR_TURN");
  const tutorBlocked = blockedFrom(v?.demo_limits, "tutor_turn", turnHit);
  const turnsLeft = v?.demo_limits?.tutor_turn.remaining ?? null;
  // Read new committed tutor replies aloud (opt-in). History already on screen is never read.
  const lastReply = [...(v?.transcript ?? [])].reverse().find((m) => m.sender === "AI" && m.provenance === "TUTOR_ENGINE");
  useEffect(() => {
    if (!api || !v) return;
    if (lastSpoken.current === undefined) {
      lastSpoken.current = lastReply?.message_id ?? null;
      // History on screen is never replayed, except the opening of a conversation just started.
      if (lastReply && takeFreshStart(v.learning_session_id)) freshOpening.current = lastReply.message_id;
    }
    if (freshOpening.current && !caps.loading) {
      const id = freshOpening.current;
      freshOpening.current = null;
      if (lastReply?.message_id === id && readAloud && voiceAvailable && !speechBlocked) {
        speaker.current ??= new ReplySpeaker();
        void playReply(client, speaker.current, lastReply, voicePrefs.speed, playback);
      }
      return;
    }
    if (!lastReply || lastReply.message_id === lastSpoken.current) return;
    lastSpoken.current = lastReply.message_id;
    if (!readAloud || !voiceAvailable || speechBlocked) return;
    speaker.current ??= new ReplySpeaker();
    void playReply(client, speaker.current, lastReply, voicePrefs.speed, playback);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, v, lastReply, readAloud, voiceAvailable, client, caps.loading]);
  useEffect(() => () => speaker.current?.stop(), []);
  useEffect(() => speaker.current?.setRate(voicePrefs.speed), [voicePrefs.speed]);
  useEffect(() => {
    if (sendingSince === null) return;
    const t = setInterval(() => setTick(Date.now()), 1000);
    return () => clearInterval(t);
  }, [sendingSince]);
  const latestCitation = useMemo(() => {
    const msgs = v?.transcript ?? [];
    for (let i = msgs.length - 1; i >= 0; i--) {
      const c = msgs[i]!.citations[0];
      if (msgs[i]!.sender === "AI" && c) return c;
    }
    return null;
  }, [v?.transcript]);

  if (view.loading) return <Loading label="Loading conversation" />;
  if (view.error) return <PageError error={view.error} onRetry={view.reload} />;
  if (!v) return <NotStarted onStarted={view.reload} />;

  const send = async (text: string, input_kind: "TEXT" | "VOICE_TRANSCRIPT", prompt_id?: string) => {
    const started = Date.now();
    setSendingSince(started);
    setTick(started);
    const r = await cmd.run((c, k) =>
      c
        .sendOnboardingTurn({
          idempotency_key: k,
          client_turn_id: newKey("turn"),
          expected_revision: v.revision,
          text,
          input_kind,
          preview_prompt_id: prompt_id,
          interrupted_previous_reply: interrupted.current || undefined,
          onProgress: setTutorStep,
        })
        .catch((e: unknown) => {
          // Keep the limit panel up even if this error is later cleared by another action.
          const limit = e instanceof WorkWeaveError ? limitOf(e.error, "TUTOR_TURN") : null;
          if (limit) setHits((h) => ({ ...h, tutor_turn: limit }));
          throw e;
        }),
    );
    setSendingSince(null);
    setTutorStep(null);
    if (r) interrupted.current = false;
    return Boolean(r);
  };
  const messages: ChatMessageView[] = v.transcript.map((m) => ({
    id: m.message_id,
    sender: m.sender,
    text: m.text,
    provenance: m.provenance,
    citations: m.citations,
    kindClass: KIND_CLASS[m.kind],
    inputKind: m.input_kind,
    meta: (
      <>
        {KIND_TAG[m.kind] && <span className="fixture-tag">{KIND_TAG[m.kind]}</span>}
        {api && voiceAvailable && !speechBlocked && m.sender === "AI" && m.provenance === "TUTOR_ENGINE" && (
          <button
            className="link-btn"
            onClick={() => {
              if (speaking && speakingId === m.message_id) return stopReading();
              speaker.current ??= new ReplySpeaker();
              void playReply(client, speaker.current, m, voicePrefs.speed, playback);
            }}
            aria-label={speaking && speakingId === m.message_id ? "Stop reading this reply" : "Listen to this reply"}
          >
            {speaking && speakingId === m.message_id ? "Stop" : "Listen"}
          </button>
        )}
        {m.assessment &&
          (api ? (
            <>
              <Status value={m.assessment.outcome === "CORRECT" ? "COMPLETED" : "PENDING"} label={`Assessed: ${humanize(m.assessment.outcome)}`} />
              <span>
                {m.assessment.note} Criteria {m.assessment.criteria_version}.
              </span>
            </>
          ) : (
            <>
              <Status value={m.assessment.outcome === "CORRECT" ? "COMPLETED" : "PENDING"} label={`Evidence: ${humanize(m.assessment.outcome)}`} />
              <span title={m.assessment.note}>Fixture outcome, not an AI assessment</span>
            </>
          ))}
      </>
    ),
  }));
  // The next eligible subtopic is the first NOT_STARTED one (the current one is already completed).
  const subs = v.overview.topics.flatMap((t) => t.subtopics);
  const progress = pathProgress(v.overview.topics);
  const currentSub = v.overview.topics.flatMap((t) => t.subtopics).find((s) => s.subtopic_id === v.overview.current_subtopic_id);
  const showWelcome =
    api && !welcomeDismissed && (v.status === "ACTIVE" || v.status === "PAUSED") && (v.transcript.length > 0 || progress.done > 0 || currentSub?.status === "IN_PROGRESS");
  const thinkingSeconds = sendingSince === null ? 0 : Math.max(0, Math.floor((tick - sendingSince) / 1000));
  const thinking =
    api && sendingSince !== null ? (
      <div className="msg-thinking small muted" role="status" aria-live="polite">
        {tutorStep ?? "Tutor is thinking…"}
        {thinkingSeconds >= 3 ? ` ${thinkingSeconds}s` : ""}
      </div>
    ) : null;
  const nextSub = subs.find((s) => s.status === "NOT_STARTED");

  const engineConnected = v.tutor?.status === "ok";
  const completionActions =
    v.awaiting_continue && v.status === "ACTIVE" && api && !engineConnected ? (
      // Without the tutor engine there is nothing to open the next item; the completion itself is saved.
      <div className="stack-s" style={{ marginLeft: 4 }}>
        <p className="small muted">Starting {nextSub?.name ?? "the next subtopic"} from here isn&apos;t connected yet. Your completion is saved.</p>
        <button className="btn" disabled={cmd.pending} onClick={() => void cmd.run((c, k) => c.pauseOnboarding({ idempotency_key: k, expected_revision: v.revision }))}>
          Take a break
        </button>
      </div>
    ) : v.awaiting_continue && v.status === "ACTIVE" ? (
      <div className="row" style={{ marginLeft: 4 }}>
        <button className="btn btn-primary" disabled={cmd.pending} onClick={() => void cmd.run((c, k) => c.continueOnboarding({ idempotency_key: k, expected_revision: v.revision }))}>
          Continue to {nextSub?.name ?? "next subtopic"}
        </button>
        <button className="btn" disabled={cmd.pending} onClick={() => void cmd.run((c, k) => c.pauseOnboarding({ idempotency_key: k, expected_revision: v.revision }))}>
          Take a break
        </button>
      </div>
    ) : v.status === "COMPLETED" ? (
      <div className="row">
        <Link className="btn btn-primary" href="/companion/">
          Open Work Companion
        </Link>
        <Link className="btn" href="/onboarding/">
          Back to overview
        </Link>
      </div>
    ) : null;

  return (
    <div className="stack">
      <PageHeader
        eyebrow={`${v.overview.curriculum_name} · ${session?.persona.first_name}'s learning space`}
        title="Let's work through it."
        purpose="Ask, answer, or ask for an example in the same conversation. Progress changes only when an objective is met and saved."
        actions={
          <>
            <span className="small muted" role="status" aria-live="polite">
              {cmd.pending ? "Saving…" : v.overview.saved_at}
            </span>
            <button className="btn btn-small" onClick={() => setPrefs(true)}>
              Preferences
            </button>
            {v.status === "ACTIVE" && !v.awaiting_continue && (
              <button className="btn btn-small" disabled={cmd.pending} onClick={() => void cmd.run((c, k) => c.pauseOnboarding({ idempotency_key: k, expected_revision: v.revision }))}>
                Take a break
              </button>
            )}
          </>
        }
      />

      {showWelcome && (
        <div className="notice notice-info" role="note">
          <span className="notice-title">Welcome back</span>
          <span>
            {currentSub ? `You're on ${currentSub.name}.` : "Your place is saved."} {progress.label}.
            {v.pending_check ? ` Your open question: ${v.pending_check.text}` : ""} {v.overview.saved_at ?? ""}
          </span>
          <span>
            <button className="btn btn-small" onClick={() => setWelcomeDismissed(true)}>
              Got it
            </button>
          </span>
        </div>
      )}
      <div className="split">
        <section className="chat chat-contained" aria-labelledby="h-tutor">
          <ChatHeader
            id="h-tutor"
            title="Your work tutor"
            subtitle={
              v.tutor?.status === "unavailable"
                ? "Tutor not connected · your place and breaks are saved"
                : api
                  ? "Replies are saved only after their sources and answers are checked"
                  : "Scripted preview · fictional approved source"
            }
            action={
              <button className="link-btn ref-sheet-btn" onClick={() => setSheet(true)} disabled={!(pinned ?? latestCitation)}>
                View reference
              </button>
            }
          />
          {v.tutor?.status === "unavailable" && (
            <div style={{ padding: "16px 22px 0" }}>
              <div className="notice notice-info">
                <span className="notice-title">Replies aren&apos;t available yet</span>
                <span>{v.tutor.message}</span>
              </div>
            </div>
          )}
          <Transcript messages={messages} label="Tutor conversation" onCite={(c) => setPinned(c)} activeCitation={pinned?.citation_id} footer={
              <>
                {thinking}
                {completionActions}
              </>
            }
          />
          {cmd.error && !turnHit && (
            <div style={{ padding: "0 14px" }}>
              <ChatErrorNote error={cmd.error} onRetry={cmd.error.code === "REVISION_CONFLICT" ? () => { cmd.clearError(); view.reload(); } : undefined} onDismiss={cmd.clearError} />
            </div>
          )}
          {v.status === "PAUSED" ? (
            <div className="composer">
              <p>The conversation is paused and your progress is saved.</p>
              <div className="row">
                <button className="btn btn-primary" disabled={cmd.pending} onClick={() => void cmd.run((c) => c.startOnboardingSession())}>
                  Resume conversation
                </button>
                <Link className="btn" href="/onboarding/">
                  Back to overview
                </Link>
              </div>
            </div>
          ) : v.status === "COMPLETED" ? null : api && tutorBlocked ? (
            <TutorLimitPanel blocked={tutorBlocked} evaluator={v.demo_limits?.tier === "EVALUATOR"} freshHref={session ? companyEntryHref(session.scenario.key, session.scenario.scenario_id) : "/demo/"} />
          ) : (
            <>
              {api && v.pending_check && (
                <div className="notice notice-quiet" role="note" style={{ margin: "0 14px" }}>
                  <span className="notice-title">Open question</span>
                  <span>{v.pending_check.text}</span>
                </div>
              )}
              <ScriptPrompts prompts={v.script_prompts} disabled={cmd.pending} onPick={(p) => void send(p.text, "TEXT", p.prompt_id)} />
              {api ? (
                <>
                  {voiceAvailable && !readAloud && !voicePrefs.readAloudOffered && !speechBlocked && lastReply && (
                    <div className="notice notice-info" role="note" style={{ margin: "0 14px" }} data-testid="read-aloud-offer">
                      <span className="notice-title">Hear the tutor?</span>
                      <span>The tutor can read its replies aloud. You can switch this off any time with &quot;Read replies aloud&quot;.</span>
                      <span className="row" style={{ marginTop: 8 }}>
                        <button
                          className="btn btn-small btn-primary"
                          onClick={() => {
                            updatePrefs({ readAloud: true, readAloudOffered: true });
                            speaker.current ??= new ReplySpeaker();
                            void playReply(client, speaker.current, lastReply, voicePrefs.speed, playback);
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
                      <input type="checkbox" role="switch" checked={readAloud && !speechBlocked} disabled={!voiceAvailable || Boolean(speechBlocked)} onChange={(e) => updatePrefs({ readAloud: e.target.checked })} />
                      Read replies aloud
                    </label>
                    <label className="small row" style={{ gap: 6 }} title="Speaking over a reply stops it. Works best with headphones; on speakers the reply can occasionally interrupt itself.">
                      <input type="checkbox" role="switch" checked={voiceInterrupt} disabled={!voiceAvailable || !readAloud} onChange={(e) => updatePrefs({ voiceInterrupt: e.target.checked })} />
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
                    {speaking && (
                      <button
                        className="btn btn-small"
                        onClick={stopReading}
                      >
                        Stop reading
                      </button>
                    )}
                    {speechBlocked && voiceAvailable && (
                      <span className="small muted" role="status" data-testid="speech-limit">
                        Replies are text-only for now: reading aloud has reached its {speechBlocked.scope === "RUN" ? "limit for this demo workspace" : "shared demo limit"} today. Back at {resetTime(speechBlocked.resets_at)}.
                      </span>
                    )}
                    {speechError && !speechBlocked && (
                      <span className="small" role="alert">
                        {speechError}
                      </span>
                    )}
                  </div>
                  {caps.data?.conversation_engine === "AVAILABLE" && !v.awaiting_continue && !v.script_prompts.length && (
                    <ExamplePrompts examples={ONBOARDING_EXAMPLES} disabled={cmd.pending} onPick={(text) => void send(text, "TEXT")} />
                  )}
                  <VoiceComposer
                    label="Ask, answer, or tell me what you need"
                    onSend={(text, kind) => send(text, kind)}
                    pending={cmd.pending}
                    disabled={v.awaiting_continue}
                    placeholder={v.awaiting_continue ? "Choose an option above" : "Type a question or answer"}
                    voiceAvailable={voiceAvailable}
                    voiceBlocked={listenBlocked}
                    onLimit={(limit) => setHits((h) => ({ ...h, voice_listen: limit }))}
                    unavailableReason={caps.loading ? "Checking voice…" : "Voice isn't configured on this server."}
                    speaking={speaking}
                    speakingText={speakingText}
                    voiceInterrupt={voiceInterrupt}
                    onInterrupt={() => {
                      stopReading();
                      interrupted.current = true;
                    }}
                    prefs={voicePrefs}
                    onPrefsChange={updatePrefs}
                    playCue={playCue}
                    micPermission={micPermission}
                    getGrant={(mode) => client.getVoiceListenGrant(mode)}
                    createListener={(grant, events) => new LiveListener(grant, events, { audio: new MicCapture() })}
                  />
                </>
              ) : (
                <Composer label="Ask, answer, or tell me what you need" onSend={send} pending={cmd.pending} disabled={v.awaiting_continue} voiceDraft={v.script_prompts[0]} placeholder={v.awaiting_continue ? "Choose Continue or Take a break above" : "Type a question or answer"} />
              )}
              {api && turnsLeft !== null && turnsLeft > 0 && turnsLeft <= LOW_REMAINING && (
                <p className="small muted" role="status" style={{ padding: "0 14px" }} data-testid="turns-left">
                  {turnsLeft === 1 ? "1 assistant message left" : `${turnsLeft} assistant messages left`} in this demo today.
                </p>
              )}
              <p className="composer-note">
                {api
                  ? "Progress changes only when the tutor assesses an answer as correct and it is saved. Learning never grants operational permission."
                  : "Local preview. No microphone, model calls or real assessment. Learning never grants operational permission."}
              </p>
            </>
          )}
        </section>

        <aside className="split-aside stack" aria-label="Learning path and reference">
          <section className="panel" aria-labelledby="h-path">
            <div className="row-between" style={{ marginBottom: 14 }}>
              <h2 id="h-path">Your learning path</h2>
              <span className="small muted">
                {progress.short}
              </span>
            </div>
            <LearningPath topics={v.overview.topics} currentId={v.overview.current_subtopic_id} expanded />
          </section>
          <div className="ref-aside">
            <ReferencePanel citation={pinned ?? latestCitation} pinned={Boolean(pinned)} onReturn={() => setPinned(null)} onOpen={(c) => setDrawer(c)} />
          </div>
          <p className="small muted need-person">Need a person? Ask your supervisor directly. In-app help requests aren&apos;t part of this release, so nothing is sent from here.</p>
        </aside>
      </div>
      <Dialog open={sheet} title="Reference for this explanation" onClose={() => setSheet(false)} variant="sheet">
        <ReferencePanel
          citation={pinned ?? latestCitation}
          pinned={Boolean(pinned)}
          onReturn={() => setPinned(null)}
          onOpen={(c) => {
            setSheet(false);
            setDrawer(c);
          }}
          bare
        />
      </Dialog>
      <SourceDrawer citation={drawer} onClose={() => setDrawer(null)} />
      <PreferencesDialog open={prefs} onClose={() => setPrefs(false)} api={api} engineConnected={engineConnected} />
    </div>
  );
}

/** Replaces the composer once tutor messages hit a demo cap: what happened, what's saved, what to do. */
function TutorLimitPanel({ blocked, evaluator, freshHref }: { blocked: Blocked; evaluator: boolean; freshHref: string }) {
  const when = resetTime(blocked.resets_at);
  return (
    <div className="composer" data-testid="tutor-limit">
      <div className="notice notice-info" role="status">
        <span className="notice-title">{blocked.scope === "RUN" ? "This demo has used today's assistant messages" : "The demo assistants have reached today's shared limit"}</span>
        <span>
          {blocked.scope === "RUN"
            ? `Your conversation and progress are saved. To keep chatting now, start a fresh demo (a new copy of the company), or come back after ${when}.`
            : evaluator
              ? `The evaluator allowance for today is used up. Your conversation and progress are saved; the tutor is available again at ${when}.`
              : `The demo has a daily allowance shared by every visitor, and it's used up. Your conversation and progress are saved; the tutor is available again at ${when}.`}
        </span>
      </div>
      <div className="row">
        {blocked.scope === "RUN" && (
          <Link className="btn btn-primary" href={freshHref}>
            Start a fresh demo
          </Link>
        )}
        <Link className={blocked.scope === "RUN" ? "btn" : "btn btn-primary"} href="/onboarding/">
          Back to overview
        </Link>
      </div>
    </div>
  );
}

function NotStarted({ onStarted }: { onStarted: () => void }) {
  // markFreshStart: the opening that comes back is new, so it may be read aloud (read-aloud on).
  const cmd = useCommand();
  return (
    <div className="state">
      <h2>The conversation hasn&apos;t started</h2>
      <p>The tutor opens the conversation for you; you don&apos;t need to type first.</p>
      {cmd.error && <ErrorNotice error={cmd.error} />}
      <div className="row">
        <button
          className="btn btn-primary"
          disabled={cmd.pending}
          onClick={async () => {
            const r: OnboardingSessionView | undefined = await cmd.run((c) => c.startOnboardingSession());
            if (r && !r.transcript.some((m) => m.sender === "EMPLOYEE")) markFreshStart(r.learning_session_id);
            if (r) onStarted();
          }}
        >
          {cmd.pending ? "Opening…" : "Start conversation"}
        </button>
        <Link className="btn" href="/onboarding/">
          Back to overview
        </Link>
      </div>
    </div>
  );
}

function PreferencesDialog({ open, onClose, api = false, engineConnected = false }: { open: boolean; onClose: () => void; api?: boolean; engineConnected?: boolean }) {
  const [style, setStyle] = useState("CONCISE");
  const [applied, setApplied] = useState<string | null>(null);
  return (
    <Dialog
      open={open}
      title="Conversation preferences"
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn btn-primary"
            onClick={() => {
              setApplied(style);
              onClose();
            }}
          >
            Apply preferences
          </button>
        </>
      }
    >
      <p className="small muted">Preferences change how explanations are presented, never what counts as progress. Text is always available.</p>
      <fieldset>
        <legend>Explanation style</legend>
        {[
          ["CONCISE", "Concise"],
          ["DETAILED", "Detailed"],
          ["STEPS", "Step by step"],
        ].map(([v, l]) => (
          <label key={v} className="choice">
            <input type="radio" name="style" checked={style === v} onChange={() => setStyle(v!)} /> {l}
          </label>
        ))}
      </fieldset>
      <fieldset>
        <legend>Language</legend>
        <label className="choice">
          <input type="radio" checked readOnly /> English
        </label>
        <span className="small muted">Other languages appear only after their support is measured.</span>
      </fieldset>
      <fieldset disabled>
        <legend>Read aloud and visuals</legend>
        {api ? (
          <span className="small muted">To hear replies, switch on &quot;Read replies aloud&quot; above the message box.</span>
        ) : (
          <label className="choice">
            <input type="checkbox" /> Read explanations aloud (narration isn&apos;t connected)
          </label>
        )}
        <label className="choice">
          <input type="checkbox" /> Show source-backed visuals (no reviewed visuals in this pack)
        </label>
      </fieldset>
      {applied && (
        <p className="small">
          {api && engineConnected
            ? `Noted: ${applied.toLowerCase()} for this visit. The tutor doesn't take style preferences yet; you can also just ask it in the conversation.`
            : `Applied: ${applied.toLowerCase()} (preview only; the tutor engine isn't connected).`}
        </p>
      )}
    </Dialog>
  );
}
