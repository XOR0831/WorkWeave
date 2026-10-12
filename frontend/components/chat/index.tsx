"use client";

import { RichText } from "@/lib/text/RichText";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import type { Citation, ScriptPrompt } from "@/types/contracts";
import { useUiPrefs } from "@/lib/preview/ui-prefs";
import { useOnChange } from "@/lib/preview/use-on-change";
import { useResource } from "@/lib/preview/client-context";
import { Dialog, ErrorNotice, Evidence, Loading, Status } from "@/components/ui";
import { resetTime } from "@/lib/limits";
import type { ApiError } from "@/types/contracts";

export interface ChatMessageView {
  id: string;
  sender: "AI" | "EMPLOYEE" | "SYSTEM" | "REVIEWER";
  text: string;
  provenance: "SCRIPTED_FIXTURE" | "EMPLOYEE_INPUT" | "PREVIEW_SYSTEM" | "TUTOR_ENGINE" | "WORK_ENGINE" | "HANDOVER_ENGINE" | "KT_ENGINE" | "BACKEND_RECORD";
  citations?: Citation[];
  kindClass?: string;
  meta?: ReactNode;
  inputKind?: "TEXT" | "VOICE_TRANSCRIPT";
}

export function Transcript({
  messages,
  label,
  onCite,
  activeCitation,
  footer,
}: {
  messages: ChatMessageView[];
  label: string;
  onCite?: (c: Citation) => void;
  activeCitation?: string;
  footer?: ReactNode;
}) {
  const logRef = useRef<HTMLDivElement>(null);
  // Scroll only the transcript itself; scrollIntoView would also move the page.
  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages.length]);
  return (
    <div ref={logRef} className="transcript" role="log" aria-label={label} aria-live="polite" tabIndex={0}>
      {messages.map((m) => (
        <div key={m.id} className={`msg msg-${m.sender === "EMPLOYEE" ? "employee" : m.sender === "SYSTEM" ? "system" : "ai"} ${m.kindClass ?? ""}`}>
          <div className="msg-meta">
            <span>{m.sender === "EMPLOYEE" ? "You" : m.sender === "SYSTEM" ? "WorkWeave" : m.sender === "REVIEWER" ? "Reviewer" : "Assistant"}</span>
            {m.inputKind === "VOICE_TRANSCRIPT" && <span className="fixture-tag">Voice transcript</span>}
            {m.meta}
          </div>
          <div className="msg-body">{m.sender === "EMPLOYEE" ? m.text : <RichText text={m.text} />}</div>
          {m.citations && m.citations.length > 0 && onCite && (
            <div className="row" aria-label="Sources for this message">
              {m.citations.map((c) => (
                <button key={c.citation_id} className="cite" aria-pressed={activeCitation === c.citation_id} onClick={() => onCite(c)}>
                  {c.label}
                </button>
              ))}
            </div>
          )}
        </div>
      ))}
      {footer}
    </div>
  );
}

/**
 * Conversation panel header. Carries the panel's single honesty label ("Scripted preview"), so
 * individual messages don't repeat it (design-system.md: one label per panel).
 */
export function ChatHeader({ title, subtitle = "Scripted preview", id, action }: { title: string; subtitle?: ReactNode; id?: string; action?: ReactNode }) {
  return (
    <div className="chat-head">
      <div className="chat-head-title">
        <span className="chat-avatar" aria-hidden="true">
          ✧
        </span>
        <div>
          <h2 id={id}>{title}</h2>
          <span className="small muted">{subtitle}</span>
        </div>
      </div>
      {action}
    </div>
  );
}

/** Recorded preview prompts. The first few stay visible; the rest open from "More prompts". */
export function ScriptPrompts({ prompts, onPick, disabled, visible = 3 }: { prompts: ScriptPrompt[]; onPick: (p: ScriptPrompt) => void; disabled?: boolean; visible?: number }) {
  const [all, setAll] = useState(false);
  const id = useId();
  if (!prompts.length) return null;
  const hidden = prompts.length - visible;
  const shown = all || hidden <= 0 ? prompts : prompts.slice(0, visible);
  return (
    <div className="script">
      <div className="script-chips" role="group" aria-labelledby={`${id}-label`}>
        <span className="fixture-tag" id={`${id}-label`} title="Recorded prompts that play fixture responses. Typed text isn't interpreted.">
          Preview script
        </span>
        {shown.map((p) => (
          <button key={p.prompt_id} className="chip" disabled={disabled} onClick={() => onPick(p)} title={p.text}>
            {p.label}
          </button>
        ))}
        {hidden > 0 && (
          <button className="link-btn" aria-expanded={all} onClick={() => setAll((v) => !v)}>
            {all ? "Fewer prompts" : `More prompts (${hidden})`}
          </button>
        )}
      </div>
    </div>
  );
}

function MicIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0M12 18v3" strokeLinecap="round" />
    </svg>
  );
}

/**
 * Text composer with a visible tap-to-talk control (build_spec §4, screens/onboarding/03).
 * No voice adapter is connected: the mic is disabled with an explanation. Reviewers can enable a
 * simulated listening state from Review tools; it never touches a microphone.
 */
export function Composer({
  onSend,
  disabled,
  pending,
  placeholder = "Type a message",
  voiceDraft,
  label,
}: {
  onSend: (text: string, inputKind: "TEXT" | "VOICE_TRANSCRIPT", promptId?: string) => Promise<boolean>;
  disabled?: boolean;
  pending?: boolean;
  placeholder?: string;
  /** Simulated transcript source: next script prompt (reviewer simulation only). */
  voiceDraft?: ScriptPrompt;
  label: string;
}) {
  const { simulateVoice } = useUiPrefs();
  const [text, setText] = useState("");
  const [listening, setListening] = useState(false);
  const [voice, setVoice] = useState<{ promptId?: string } | null>(null);
  const id = useId();
  const voiceHelp = `${id}-voice`;

  const submit = async () => {
    if (!text.trim() || disabled || pending) return;
    const ok = await onSend(text.trim(), voice ? "VOICE_TRANSCRIPT" : "TEXT", voice?.promptId);
    if (ok) {
      setText("");
      setVoice(null);
    }
  };

  return (
    <div className="composer">
      {listening && (
        <div className="listening" role="status">
          <span className="listening-dot" aria-hidden="true" />
          <span style={{ flex: 1 }}>Listening (simulated, no microphone). Tap stop to review the transcript before sending.</span>
          <button
            className="btn btn-small"
            onClick={() => {
              setListening(false);
              if (voiceDraft) {
                setText(voiceDraft.text);
                setVoice({ promptId: voiceDraft.prompt_id });
              } else setVoice({});
            }}
          >
            Stop
          </button>
          <button className="btn btn-small btn-ghost" onClick={() => setListening(false)}>
            Cancel
          </button>
        </div>
      )}
      {voice && !listening && <span className="small muted">Transcript draft (simulated). Edit it if needed, then send.</span>}
      <label className="composer-label" htmlFor={`${id}-input`}>
        {label}
      </label>
      <textarea
        id={`${id}-input`}
        value={text}
        rows={2}
        placeholder={placeholder}
        disabled={disabled}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            void submit();
          }
        }}
      />
      <div className="composer-controls">
        <div className="row">
          <button
            className="btn btn-small mic"
            aria-label={simulateVoice ? "Tap to talk (simulated)" : "Tap to talk: voice isn't connected"}
            aria-describedby={voiceHelp}
            disabled={!simulateVoice || disabled || listening}
            onClick={() => setListening(true)}
          >
            <MicIcon />
            Tap to talk
          </button>
          <span id={voiceHelp} className="small muted">
            {simulateVoice ? "Voice simulated for review" : "Voice not connected"}
          </span>
          <span className="small muted" title="Hands-free needs explicit opt-in once a voice adapter is connected.">
            Hands-free: off
          </span>
        </div>
        <button className="btn btn-primary" onClick={() => void submit()} disabled={disabled || pending || !text.trim()}>
          {pending ? "Sending…" : "Send"}
        </button>
      </div>
    </div>
  );
}

/** Source drawer: document/version/heading path/status + exact excerpt; revocation fails closed. */
export function SourceDrawer({ citation, onClose }: { citation: Citation | null; onClose: () => void }) {
  const [full, setFull] = useState(false);
  const dv = citation?.excerpt.document_version_id ?? "";
  const src = useResource((c) => (dv ? c.getSourceContent(dv) : Promise.resolve(null)), [dv, citation?.citation_id]);
  useOnChange(citation?.citation_id, () => setFull(false));
  return (
    <Dialog open={Boolean(citation)} title="Source" onClose={onClose} variant="drawer">
      {citation && (
        <>
          <div className="stack-s">
            <h3>{citation.label}</h3>
            <span className="small muted">{citation.excerpt.heading_path.join(" › ")}</span>
          </div>
          {!dv ? (
            <div className="stack-s">
              <div className="row">
                <Status value="CURRENT" label="Work record" />
                <Evidence type={citation.excerpt.evidence_type} />
              </div>
              <div className="excerpt"><RichText text={citation.excerpt.text} /></div>
            </div>
          ) : src.loading ? (
            <Loading label="Loading source" />
          ) : src.error ? (
            <ErrorNotice error={src.error} />
          ) : src.data ? (
            <div className="stack-s">
              <dl className="kv">
                <dt>Document</dt>
                <dd>
                  {src.data.version.document_code} v{src.data.version.version}: {src.data.version.title}
                </dd>
                <dt>Status</dt>
                <dd className="row">
                  <Status value={src.data.version.approval_status} />
                  <Status value={src.data.version.temporal_status} />
                </dd>
                <dt>Effective</dt>
                <dd>{src.data.version.effective_label}</dd>
                {src.data.version.approved_by && (
                  <>
                    <dt>Approved by</dt>
                    <dd>{src.data.version.approved_by}</dd>
                  </>
                )}
              </dl>
              {src.data.version.temporal_status !== "CURRENT" && (
                <div className="notice notice-warn">
                  <span className="notice-title">Historical version</span>
                  <span>This version is superseded. It explains history; it isn&apos;t current guidance.</span>
                </div>
              )}
              <div className={`excerpt ${src.data.version.temporal_status !== "CURRENT" ? "excerpt-historical" : ""}`}><RichText text={citation.excerpt.text} /></div>
              {citation.excerpt.illustrative && <span className="small muted">Illustrative example, not company procedure.</span>}
              <button className="btn btn-small" onClick={() => setFull((v) => !v)} aria-expanded={full}>
                {full ? "Hide full source" : "Open full source"}
              </button>
              {full && (
                <div className="panel panel-quiet small" style={{ whiteSpace: "pre-wrap" }}>
                  {src.data.text || "No further text is available in this preview."}
                  <p className="muted" style={{ marginTop: 8 }}>
                    The preview includes selected sections only.
                  </p>
                </div>
              )}
            </div>
          ) : null}
        </>
      )}
    </Dialog>
  );
}

/**
 * A chat action that didn't work, said inside the conversation instead of as a red banner (owner,
 * 2026-10-11): why (the server's own reason), what happened (nothing changed; your text is kept) and
 * what to do next (try again, wait, or the reset time of a demo limit).
 */
export function ChatErrorNote({ error, onRetry, onDismiss, keptText = true }: { error: ApiError; onRetry?: () => void; onDismiss?: () => void; keptText?: boolean }) {
  const said = error.message.trim();
  const unchanged = /nothing (was |has been )?(changed|saved|sent|committed|stored)|(wasn't|weren't|was not) (sent|saved|changed)|nothing changed|changed nothing/i.test(said) ? "" : " Nothing was changed.";
  const resets = error.code === "LIMIT_REACHED" && error.limit ? ` It resets at ${resetTime(error.limit.resets_at)}.` : "";
  const kept = keptText && error.code !== "LIMIT_REACHED" && !/still in the box|(input|text|message|answer) is (kept|still)/i.test(said) ? " What you typed is still in the box." : "";
  const canRetry = onRetry && (error.retryable || error.code === "REVISION_CONFLICT");
  return (
    <div className="msg msg-system chat-error" role="alert" data-testid="chat-error">
      <div className="msg-meta">
        <span>WorkWeave</span>
      </div>
      <div className="msg-body stack-s">
        <span>
          {said}
          {unchanged}
          {resets}
          {kept}
        </span>
        {(canRetry || onDismiss) && (
          <span className="row">
            {canRetry && (
              <button className="btn btn-small" onClick={onRetry}>
                {error.code === "REVISION_CONFLICT" ? "Reload latest" : "Try again"}
              </button>
            )}
            {onDismiss && (
              <button className="btn btn-small btn-ghost" onClick={onDismiss}>
                Dismiss
              </button>
            )}
          </span>
        )}
      </div>
    </div>
  );
}
