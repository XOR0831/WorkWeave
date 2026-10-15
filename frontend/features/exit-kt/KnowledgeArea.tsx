"use client";

import { useState } from "react";
import { useOnChange } from "@/lib/preview/use-on-change";
import { ChatErrorNote, ScriptPrompts, Transcript } from "@/components/chat";
import { ChatVoiceComposer, KT_VOICE, ListenButton, ReadAloudControls, useChatVoice } from "@/features/voice/ChatVoice";
import { Dialog, ErrorNotice, OriginTag, Status, humanize } from "@/components/ui";
import { newKey, useCommand, useRuntime, useSession } from "@/lib/preview/client-context";
import type { ExitKtCase, KtArtifact, KtKnowledgeItem } from "@/types/contracts";
import { DiscoveryPanel, riskWhy } from "./Discovery";

export function KnowledgeArea({ c, role }: { c: ExitKtCase; role: "SUBJECT" | "REVIEWER" }) {
  const cmd = useCommand();
  const [interviewFor, setInterviewFor] = useState<KtKnowledgeItem | null>(null);
  const [artifactId, setArtifactId] = useState<string | null>(null);
  const [newArtifactFor, setNewArtifactFor] = useState<KtKnowledgeItem | null>(null);
  const [adding, setAdding] = useState(false);
  const [title, setTitle] = useState("");
  const [desc, setDesc] = useState("");
  const isSubject = role === "SUBJECT";

  return (
    <div className="stack">
      <div className="kt-counts" aria-label="Documentation status">
        {(["DOCUMENTED", "OUTDATED", "MISSING"] as const).map((st) => (
          <div key={st} className="metric">
            <span className="metric-value">{c.knowledge_items.filter((k) => k.documentation_status === st).length}</span>
            <span className="metric-label">{humanize(st)}</span>
          </div>
        ))}
      </div>
      {c.discovery && <DiscoveryPanel d={c.discovery} />}
      <p className="muted small" style={{ maxWidth: "70ch" }}>
        What {isSubject ? "you know" : "the employee knows"} that others rely on. Areas with a current approved source can skip the interview after a human check. Drafts and interviews stay private until submitted.
      </p>
      <div className="row-between kt-toolbar">
        {c.knowledge_items.some((k) => k.origin === "SYNTHETIC_SEED") ? <OriginTag origin="SYNTHETIC_SEED" /> : <span />}
        <div className="row">
          <button className="btn btn-small" disabled={cmd.pending} onClick={() => void cmd.run((cl) => cl.runDiscovery())}>
            Run discovery
          </button>
          <button className="btn btn-small" onClick={() => setAdding(true)}>
            Add knowledge area
          </button>
        </div>
      </div>
      {cmd.error && <ErrorNotice error={cmd.error} onDismiss={cmd.clearError} />}
      <ul className="list">
        {c.knowledge_items.map((it) => {
          const interview = c.interviews.find((i) => i.kt_item_id === it.kt_item_id);
          const art = c.artifacts.find((a) => a.kt_item_id === it.kt_item_id);
          return (
            <li key={it.kt_item_id} className="list-item">
              <div className="row-between">
                <b>{it.title}</b>
                <span className="row">
                  <Status value={it.documentation_status} />
                  <Status value={it.kt_status} />
                </span>
              </div>
              <span className="small">{it.description}</span>
              <span className="row small muted">
                <span className={it.risk_level === "HIGH" ? "risk-high" : undefined} title={it.risk_factors ? `Why: ${riskWhy(it.risk_factors)}` : undefined}>
                  {humanize(it.risk_level)} risk{it.risk_factors ? ` (${riskWhy(it.risk_factors)})` : ""}
                </span>
                {it.origin !== "SYNTHETIC_SEED" && <OriginTag origin={it.origin} />}
                {it.linked_source && <span>Source: {it.linked_source}</span>}
                {art && (
                  <span>
                    Artifact: {art.title}
                    {art.promotion ? ` (promoted as ${art.promotion.document_version_label})` : ""}
                  </span>
                )}
              </span>
              <div className="row">
                {it.documentation_status === "DOCUMENTED" && it.linked_source && it.kt_status !== "COMPLETE" && (
                  <button className="btn btn-small" disabled={cmd.pending} onClick={() => void cmd.run((cl, k) => cl.linkExistingKnowledge(it.kt_item_id, { idempotency_key: k, expected_revision: c.revision }))}>
                    Verify existing source (skip interview)
                  </button>
                )}
                {isSubject && it.documentation_status !== "DOCUMENTED" && (
                  <button className="btn btn-small btn-primary" onClick={() => setInterviewFor(it)}>
                    {interview ? "Resume targeted interview" : "Start targeted interview"}
                  </button>
                )}
                {art && (
                  <button className="btn btn-small" onClick={() => setArtifactId(art.artifact_id)}>
                    Open artifact
                  </button>
                )}
                {isSubject && !art && it.documentation_status !== "DOCUMENTED" && (
                  <button className="btn btn-small" onClick={() => setNewArtifactFor(it)}>
                    Write artifact manually
                  </button>
                )}
              </div>
            </li>
          );
        })}
      </ul>

      <Dialog
        open={adding}
        title="Add knowledge area"
        onClose={() => setAdding(false)}
        dirty={title.length > 0 || desc.length > 0}
        footer={
          <button
            className="btn btn-primary"
            disabled={cmd.pending}
            onClick={async () => {
              const r = await cmd.run((cl, k) => cl.addKnowledgeItem(title, desc, { idempotency_key: k, expected_revision: c.revision }));
              if (r) {
                setTitle("");
                setDesc("");
                setAdding(false);
              }
            }}
          >
            Add area
          </button>
        }
      >
        <div className="field">
          <label htmlFor="ka-title">Title</label>
          <input id="ka-title" type="text" value={title} onChange={(e) => setTitle(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="ka-desc">What&apos;s missing or undocumented</label>
          <textarea id="ka-desc" value={desc} onChange={(e) => setDesc(e.target.value)} />
        </div>
        {cmd.error && <ErrorNotice error={cmd.error} />}
      </Dialog>

      <InterviewDialog c={c} item={interviewFor} onClose={() => setInterviewFor(null)} onWriteArtifact={(it) => { setInterviewFor(null); setNewArtifactFor(it); }} />
      <ArtifactDialog c={c} role={role} artifact={c.artifacts.find((a) => a.artifact_id === artifactId) ?? null} onClose={() => setArtifactId(null)} />
      <NewArtifactDialog c={c} item={newArtifactFor} onClose={() => setNewArtifactFor(null)} />
    </div>
  );
}

function InterviewDialog({ c, item, onClose, onWriteArtifact }: { c: ExitKtCase; item: KtKnowledgeItem | null; onClose: () => void; onWriteArtifact: (it: KtKnowledgeItem) => void }) {
  const cmd = useCommand();
  const [consent, setConsent] = useState(false);
  const interview = c.interviews.find((i) => i.kt_item_id === item?.kt_item_id);
  const started = interview && interview.status !== "NOT_STARTED";
  useOnChange(item?.kt_item_id, () => setConsent(false));
  // Voice (ADR-045): answer by speaking; questions can be read aloud. Only the transcript is kept.
  // From the moment the dialog opens (an empty conversation before Start), so the first question counts as new and is read aloud.
  const spoken = (started ? interview?.messages : [])?.map((m) => ({ message_id: m.message_id, text: m.content, sender: m.sender_type, provenance: m.provenance }));
  const cv = useChatVoice({ channel: KT_VOICE, conversationId: item?.kt_item_id, messages: item ? spoken : undefined, enabled: Boolean(item) && c.kt_available });
  const send = async (text: string, input_kind: "TEXT" | "VOICE_TRANSCRIPT", prompt_id?: string) =>
    Boolean(await cmd.run((cl, k) => cl.sendInterviewMessage(interview!.interview_id, { idempotency_key: k, client_turn_id: newKey("turn"), text, input_kind, preview_prompt_id: prompt_id })));
  return (
    <Dialog open={Boolean(item)} title={`Targeted interview: ${item?.title ?? ""}`} onClose={onClose} variant="drawer">
      {item && !started && (
        <>
          <div className="notice notice-info">
            <span className="notice-title">Before you start</span>
            <span>
              <b>Purpose:</b> capture this one gap so a successor can rely on it. <b>Audience:</b> only you. Nothing is shared until you submit a reviewed artifact. <b>Retention:</b> text only. If you answer by voice, it&apos;s turned into text and the audio is never stored. The conversation itself never becomes shared knowledge.
            </span>
          </div>
          <label className="choice">
            <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
            <span>I understand and want to start this interview.</span>
          </label>
          <button className="btn btn-primary" disabled={!consent || cmd.pending} onClick={() => void cmd.run((cl, k) => cl.startInterview(item.kt_item_id, consent, { idempotency_key: k, expected_revision: c.revision }))}>
            {cmd.pending ? "Starting…" : "Start interview"}
          </button>
          {cmd.pending && (
            <p className="small muted" role="status" aria-live="polite">
              The assistant is preparing its first question about {item.title}…
            </p>
          )}
        </>
      )}
      {item && started && interview && (
        <div className="chat" style={{ minHeight: 420 }}>
          <div className="chat-head">
            <span className="small">Private to you</span>
            <Status value={interview.status} />
          </div>
          <Transcript
            label="Interview"
            messages={(spoken ?? []).map((m) => ({ id: m.message_id, sender: m.sender, text: m.text, provenance: m.provenance, meta: <ListenButton cv={cv} m={m} /> }))}
          />
          <ScriptPrompts prompts={interview.script_prompts} disabled={cmd.pending} onPick={(p) => void send(p.text, "TEXT", p.prompt_id)} />
          {c.kt_available && <ReadAloudControls cv={cv} />}
          <ChatVoiceComposer cv={cv} label="Your answer" onSend={send} pending={cmd.pending} placeholder="Answer in your own words" />
        </div>
      )}
      {cmd.error && (started ? <ChatErrorNote error={cmd.error} onDismiss={cmd.clearError} /> : <ErrorNotice error={cmd.error} onDismiss={cmd.clearError} />)}
      {item && started && (
        <div className="row">
          <button className="btn" disabled={cmd.pending} onClick={() => void cmd.run((cl) => cl.draftArtifactFromInterview(interview!.interview_id))}>
            Draft artifact from interview
          </button>
          {!c.artifacts.some((a) => a.kt_item_id === item.kt_item_id) && (
            <button className="btn" onClick={() => onWriteArtifact(item)}>
              Write artifact manually
            </button>
          )}
        </div>
      )}
    </Dialog>
  );
}

function NewArtifactDialog({ c, item, onClose }: { c: ExitKtCase; item: KtKnowledgeItem | null; onClose: () => void }) {
  const cmd = useCommand();
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  useOnChange(item?.kt_item_id, () => {
    setTitle(item?.title ?? "");
    setContent("");
  });
  return (
    <Dialog
      open={Boolean(item)}
      title="Write a KT artifact"
      onClose={onClose}
      dirty={content.length > 0}
      footer={
        <button
          className="btn btn-primary"
          disabled={cmd.pending}
          onClick={async () => {
            const r = await cmd.run((cl, k) => cl.createManualArtifact(item!.kt_item_id, title, content, { idempotency_key: k, expected_revision: c.revision }));
            if (r) onClose();
          }}
        >
          Save private draft
        </button>
      }
    >
      <p className="small muted">Written manually (recorded as manual origin). Include steps, how to check the result, limits and unknowns.</p>
      <div className="field">
        <label htmlFor="na-title">Title</label>
        <input id="na-title" type="text" value={title} onChange={(e) => setTitle(e.target.value)} />
      </div>
      <div className="field">
        <label htmlFor="na-body">Content</label>
        <textarea id="na-body" rows={8} value={content} onChange={(e) => setContent(e.target.value)} />
      </div>
      {cmd.error && <ErrorNotice error={cmd.error} />}
    </Dialog>
  );
}

function ArtifactDialog({ c, role, artifact, onClose }: { c: ExitKtCase; role: "SUBJECT" | "REVIEWER"; artifact: KtArtifact | null; onClose: () => void }) {
  const cmd = useCommand();
  const { nameOf, session } = useSession();
  const api = useRuntime().mode === "http";
  const cur = artifact?.revisions.find((r) => r.artifact_revision_id === artifact.current_revision_id);
  const [text, setText] = useState(cur?.content ?? "");
  const [audience, setAudience] = useState<"TEAM" | "ORGANIZATION">("TEAM");
  const [comment, setComment] = useState("");
  useOnChange(`${cur?.artifact_revision_id}|${cur?.content}`, () => {
    setText(cur?.content ?? "");
    setComment("");
  });
  if (!artifact || !cur) return <Dialog open={false} title="Artifact" onClose={onClose}>{null}</Dialog>;
  const isSubject = role === "SUBJECT";
  const canReview = session?.persona.grants.includes("knowledge.review") && c.employee_id !== session.persona.employee_id;
  const dirty = isSubject && text !== cur.content;
  const ver = { idempotency_key: "", expected_revision: c.revision };
  return (
    <Dialog open title={artifact.title} onClose={onClose} variant="drawer" dirty={dirty}>
      <div className="row">
        <Status value={cur.status} />
        <span className="small muted">
          {humanize(artifact.artifact_type)}. Revision v{cur.version}. Audience: {cur.audience.toLowerCase()}
        </span>
      </div>
      {cur.status === "DRAFT" && <p className="small muted">Private draft. Reviewers can&apos;t see it until you submit this exact revision.</p>}
      {cur.review_comment && (
        <div className="notice notice-warn">
          <span>
            Reviewer ({nameOf(cur.reviewed_by)}): {cur.review_comment}
          </span>
        </div>
      )}
      {isSubject ? (
        <div className="field">
          <label htmlFor="art-body">Content</label>
          <textarea id="art-body" rows={8} value={text} onChange={(e) => setText(e.target.value)} />
          {cur.status !== "DRAFT" && <span className="hint">This revision is locked. Saving changes creates v{cur.version + 1}, which needs its own review.</span>}
        </div>
      ) : (
        <div className="excerpt" style={{ whiteSpace: "pre-wrap" }}>
          {cur.status === "DRAFT" ? "This draft is private to the employee." : cur.content}
        </div>
      )}
      {cmd.error && <ErrorNotice error={cmd.error} onDismiss={cmd.clearError} />}
      {isSubject && (
        <div className="row">
          <button className="btn" disabled={!dirty || cmd.pending} onClick={() => void cmd.run((cl, k) => cl.editArtifact(artifact.artifact_id, text, { ...ver, idempotency_key: k }))}>
            {cur.status === "DRAFT" ? "Save draft" : `Save as v${cur.version + 1}`}
          </button>
        </div>
      )}
      {isSubject && cur.status === "DRAFT" && !dirty && (
        <fieldset>
          <legend>Submit for knowledge review</legend>
          <label className="choice">
            <input type="radio" checked={audience === "TEAM"} onChange={() => setAudience("TEAM")} /> Team
          </label>
          <label className="choice">
            <input type="radio" checked={audience === "ORGANIZATION"} onChange={() => setAudience("ORGANIZATION")} /> Organization
          </label>
          <button className="btn btn-primary" disabled={cmd.pending} onClick={() => void cmd.run((cl, k) => cl.submitArtifact(artifact.artifact_id, cur.artifact_revision_id, audience, { ...ver, idempotency_key: k }))}>
            Submit v{cur.version} for review
          </button>
        </fieldset>
      )}
      {canReview && cur.status === "PENDING_REVIEW" && (
        <fieldset>
          <legend>Your decision on v{cur.version}</legend>
          <div className="field">
            <label htmlFor="art-comment">Comment</label>
            <textarea id="art-comment" value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Required to request a revision or reject" />
          </div>
          <div className="row">
            <button className="btn btn-primary" disabled={cmd.pending} onClick={() => void cmd.run((cl, k) => cl.decideArtifact(artifact.artifact_id, cur.artifact_revision_id, "APPROVE", comment, { ...ver, idempotency_key: k }))}>
              Approve v{cur.version}
            </button>
            <button className="btn" disabled={cmd.pending} onClick={() => void cmd.run((cl, k) => cl.decideArtifact(artifact.artifact_id, cur.artifact_revision_id, "REQUEST_REVISION", comment, { ...ver, idempotency_key: k }))}>
              Request revision
            </button>
            <button className="btn btn-danger" disabled={cmd.pending} onClick={() => void cmd.run((cl, k) => cl.decideArtifact(artifact.artifact_id, cur.artifact_revision_id, "REJECT", comment, { ...ver, idempotency_key: k }))}>
              Reject
            </button>
          </div>
        </fieldset>
      )}
      {cur.status === "APPROVED" && (
        <section className="stack-s">
          <h3>Organizational knowledge</h3>
          {artifact.promotion ? (
            <div className={`notice ${artifact.promotion.index_status === "FAILED" ? "notice-warn" : "notice-ok"}`}>
              <span>
                Promoted as a new approved version, <b>{artifact.promotion.document_version_label}</b>. No existing SOP was overwritten.
              </span>
              <span>
                Search index: <Status value={artifact.promotion.index_status} label={INDEX_LABEL[artifact.promotion.index_status]} />{" "}
                {api ? INDEX_NOTE[artifact.promotion.index_status] : "This preview doesn't index documents, so it isn't searchable here."}
              </span>
              {api && artifact.promotion.index_status === "FAILED" && canReview && (
                <div>
                  <button className="btn btn-small" disabled={cmd.pending} onClick={() => void cmd.run((cl, k) => cl.retryKtIndexing(artifact.artifact_id, cur.artifact_revision_id, { ...ver, idempotency_key: k }))}>
                    Retry indexing
                  </button>
                </div>
              )}
            </div>
          ) : canReview ? (
            <button className="btn btn-primary" disabled={cmd.pending} onClick={() => void cmd.run((cl, k) => cl.promoteArtifact(artifact.artifact_id, cur.artifact_revision_id, { ...ver, idempotency_key: k }))}>
              Promote v{cur.version} to a new document version
            </button>
          ) : (
            <p className="small muted">Approved. Waiting for the reviewer to promote it.</p>
          )}
        </section>
      )}
      <section className="stack-s">
        <h3>Revisions</h3>
        {artifact.revisions.map((r) => (
          <span key={r.artifact_revision_id} className="row small">
            v{r.version} <Status value={r.status} /> {r.reviewed_by && <span className="muted">by {nameOf(r.reviewed_by)}</span>}
          </span>
        ))}
      </section>
    </Dialog>
  );
}

/** Promoted knowledge in the assistants' search (ADR-053). */
const INDEX_LABEL = { PENDING: "Indexing", READY: "Searchable", FAILED: "Indexing failed", REVOKED: "Removed" } as const;
const INDEX_NOTE = {
  PENDING: "It's being added to the assistants' search; this usually takes under a minute.",
  READY: "The Work Companion, Shift Handover and Exit KT assistants can now find and cite it.",
  FAILED: "It isn't in the assistants' answers yet. A reviewer can retry indexing.",
  REVOKED: "It's no longer in the assistants' answers.",
} as const;
