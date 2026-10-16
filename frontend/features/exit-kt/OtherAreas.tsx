"use client";

import { useState } from "react";
import { ScriptPrompts, SourceDrawer, Transcript } from "@/components/chat";
import { Dialog, ErrorNotice, Evidence, OriginTag, Status, humanize } from "@/components/ui";
import { newKey, useCommand, useSession } from "@/lib/preview/client-context";
import { checklistEvidence } from "@/lib/domain/rules";
import { ChatVoiceComposer, KT_VOICE, ListenButton, ReadAloudControls, useChatVoice } from "@/features/voice/ChatVoice";
import type { Citation, ExitKtCase, KtFinding } from "@/types/contracts";

export function FindingsArea({ c }: { c: ExitKtCase }) {
  const cmd = useCommand();
  const [target, setTarget] = useState<{ f: KtFinding; d: "CONFIRM" | "DISMISS" | "RESOLVE" } | null>(null);
  const [reason, setReason] = useState("");
  return (
    <div className="stack">
      <div className="notice notice-info">
        <span>
          Findings are suggestions to review, not facts about the organization or the employee. These came from the seeded scenario; automated discovery isn&apos;t connected.
        </span>
      </div>
      <ul className="list">
        {c.findings.map((f) => (
          <li key={f.finding_id} className="list-item">
            <div className="row-between">
              <b>{humanize(f.finding_type)}</b>
              <span className="row">
                <Status value={f.status} />
                <OriginTag origin={f.origin} />
              </span>
            </div>
            <span>{f.description}</span>
            <span className="small muted">Evidence: {f.evidence.join("; ")}</span>
            {f.review_reason && <span className="small">Decision note: {f.review_reason}</span>}
            {f.status === "OPEN" && (
              <div className="row">
                <button className="btn btn-small" onClick={() => setTarget({ f, d: "CONFIRM" })}>
                  Confirm
                </button>
                <button className="btn btn-small" onClick={() => setTarget({ f, d: "DISMISS" })}>
                  Dismiss
                </button>
                <button className="btn btn-small" onClick={() => setTarget({ f, d: "RESOLVE" })}>
                  Resolve
                </button>
              </div>
            )}
          </li>
        ))}
      </ul>
      <Dialog
        open={Boolean(target)}
        title={target ? `${humanize(target.d)} finding` : "Finding"}
        onClose={() => setTarget(null)}
        dirty={reason.length > 0}
        footer={
          <button
            className="btn btn-primary"
            disabled={cmd.pending}
            onClick={async () => {
              const r = await cmd.run((cl, k) => cl.reviewFinding(target!.f.finding_id, target!.d, reason, { idempotency_key: k, expected_revision: c.revision }));
              if (r) {
                setReason("");
                setTarget(null);
              }
            }}
          >
            {target ? humanize(target.d) : ""}
          </button>
        }
      >
        <p>{target?.f.description}</p>
        <div className="field">
          <label htmlFor="f-reason">Reason or evidence</label>
          <textarea id="f-reason" value={reason} onChange={(e) => setReason(e.target.value)} />
        </div>
        {cmd.error && <ErrorNotice error={cmd.error} />}
      </Dialog>
    </div>
  );
}

export function CompletenessArea({ c }: { c: ExitKtCase }) {
  const cmd = useCommand();
  const { nameOf, session } = useSession();
  const isManager = session?.persona.grants.includes("responsibility.confirm");
  const evidence = checklistEvidence(c, nameOf);
  const [sel, setSel] = useState<Record<string, string>>({});
  const [exception, setException] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const ver = (k: string) => ({ idempotency_key: k, expected_revision: c.revision });
  const open = c.checklist.filter((i) => i.required && i.status !== "RESOLVED" && i.proposal_status !== "PROPOSED");
  return (
    <div className="stack">
      <p className="small muted" style={{ maxWidth: "70ch" }}>
        Each check resolves only against reviewed evidence, such as a promoted artifact or a confirmed transfer. A package receipt or a conversation doesn&apos;t resolve a gap.
      </p>
      {cmd.error && <ErrorNotice error={cmd.error} onDismiss={cmd.clearError} />}
      {c.checklist.some((i) => i.proposal_status === "PROPOSED") && (
        <section className="panel stack-s" aria-labelledby="h-plan">
          <h3 id="h-plan">Proposed knowledge-transfer plan</h3>
          <p className="small muted">The assistant proposes these from the records. They join the checklist only when the manager accepts them; accepting never reassigns work or changes access.</p>
          <ul className="list">
            {c.checklist
              .filter((i) => i.proposal_status === "PROPOSED")
              .sort((a, b) => (a.priority ?? 9) - (b.priority ?? 9))
              .map((i) => (
                <li key={i.checklist_item_id} className="list-item">
                  <div className="row-between">
                    <b>{i.label}</b>
                    <span className="small muted">
                      Priority {i.priority ?? "–"} · {i.method ? humanize(i.method) : "Method not set"}
                    </span>
                  </div>
                  {i.completion_criteria && <span className="small">Done when: {i.completion_criteria}</span>}
                  {i.evidence_sources && i.evidence_sources.length > 0 && <span className="small muted">From: {i.evidence_sources.map((x) => x.label).join(" · ")}</span>}
                  {isManager && (
                    <div className="row">
                      <button className="btn btn-small btn-primary" disabled={cmd.pending} onClick={() => void cmd.run((cl, k) => cl.decidePlanItem(i.checklist_item_id, "ACCEPT", true, ver(k)))}>
                        Accept as required
                      </button>
                      <button className="btn btn-small" disabled={cmd.pending} onClick={() => void cmd.run((cl, k) => cl.decidePlanItem(i.checklist_item_id, "ACCEPT", false, ver(k)))}>
                        Accept as optional
                      </button>
                      <button className="btn btn-small btn-ghost" disabled={cmd.pending} onClick={() => void cmd.run((cl, k) => cl.decidePlanItem(i.checklist_item_id, "DECLINE", false, ver(k)))}>
                        Decline
                      </button>
                    </div>
                  )}
                </li>
              ))}
          </ul>
        </section>
      )}
      <ul className="list">
        {c.checklist.filter((i) => i.proposal_status !== "PROPOSED").map((i) => (
          <li key={i.checklist_item_id} className="list-item">
            <div className="row-between">
              <b>{i.label}</b>
              <span className="row">
                {i.required && <Status value="PENDING" label="Required" />}
                <Status value={i.status} />
              </span>
            </div>
            {i.evidence_refs.length > 0 && <span className="small">Evidence: {evidence.find((e) => e.ref === i.evidence_refs[0])?.label ?? i.evidence_refs[0]}</span>}
            {i.exception_reason && <span className="small">Exception: {i.exception_reason}</span>}
            {i.status !== "RESOLVED" && (
              <div className="row">
                <label className="sr-only" htmlFor={`ev-${i.checklist_item_id}`}>
                  Evidence for {i.label}
                </label>
                <select id={`ev-${i.checklist_item_id}`} style={{ width: "auto", maxWidth: "100%" }} value={sel[i.checklist_item_id] ?? ""} onChange={(e) => setSel({ ...sel, [i.checklist_item_id]: e.target.value })}>
                  <option value="">{evidence.length ? "Choose reviewed evidence" : "No reviewed evidence yet"}</option>
                  {evidence.map((e) => (
                    <option key={e.ref} value={e.ref}>
                      {e.label}
                    </option>
                  ))}
                </select>
                <button className="btn btn-small" disabled={!sel[i.checklist_item_id] || cmd.pending} onClick={() => void cmd.run((cl, k) => cl.resolveChecklistItem(i.checklist_item_id, sel[i.checklist_item_id]!, ver(k)))}>
                  Resolve with evidence
                </button>
                {isManager && (
                  <button className="btn btn-small btn-ghost" onClick={() => setException(i.checklist_item_id)}>
                    Record exception
                  </button>
                )}
              </div>
            )}
          </li>
        ))}
      </ul>
      <div className="notice">
        <span className="notice-title">Open operational work</span>
        <span>{c.open_work_note}</span>
      </div>
      {isManager && (
        <div className="row">
          <button className="btn btn-primary" disabled={cmd.pending || c.status === "COMPLETE"} onClick={() => void cmd.run((cl, k) => cl.completeExitKtCase(ver(k)))}>
            {c.status === "COMPLETE" ? "Case complete" : "Complete case"}
          </button>
          {open.length > 0 && c.status !== "COMPLETE" && <span className="small muted">{open.length} required check(s) still open</span>}
        </div>
      )}
      <Dialog
        open={Boolean(exception)}
        title="Record an authorized exception"
        onClose={() => setException(null)}
        dirty={reason.length > 0}
        footer={
          <button
            className="btn btn-primary"
            disabled={cmd.pending}
            onClick={async () => {
              const r = await cmd.run((cl, k) => cl.recordChecklistException(exception!, reason, ver(k)));
              if (r) {
                setException(null);
                setReason("");
              }
            }}
          >
            Record exception
          </button>
        }
      >
        <p className="small">An exception is disclosed on the case. It doesn&apos;t mean the knowledge was transferred.</p>
        <div className="field">
          <label htmlFor="ex-reason">Reason</label>
          <textarea id="ex-reason" value={reason} onChange={(e) => setReason(e.target.value)} />
        </div>
        {cmd.error && <ErrorNotice error={cmd.error} />}
      </Dialog>
    </div>
  );
}

/** Successor's view: approved package snapshot, grounded Q&A (scripted), version-bound receipt. */
export function SuccessorView({ c }: { c: ExitKtCase }) {
  const cmd = useCommand();
  const { nameOf } = useSession();
  const [cite, setCite] = useState<Citation | null>(null);
  const v = c.package.versions.find((x) => x.package_version_id === c.package.current_approved_version_id);
  const received = v && c.package.receipts.some((r) => r.package_version_id === v.package_version_id);
  // Voice (ADR-045): the same Exit KT channel as the case assistant; the questions are this person's own conversation.
  const cv = useChatVoice({ channel: KT_VOICE, conversationId: c.exit_kt_case_id, messages: c.successor_qa, enabled: Boolean(v) && c.kt_available });
  if (!v)
    return (
      <div className="state">
        <h2>No approved package yet</h2>
        <p>{nameOf(c.employee_id)}&apos;s package will appear here after the reviewer approves it.</p>
      </div>
    );
  const send = async (text: string, input_kind: "TEXT" | "VOICE_TRANSCRIPT", prompt_id?: string) => Boolean(await cmd.run((cl, k) => cl.askPackage({ idempotency_key: k, client_turn_id: newKey("turn"), text, input_kind, preview_prompt_id: prompt_id })));
  return (
    <div className="split">
      <section className="panel stack" aria-labelledby="h-brief">
        <div className="row-between">
          <h2 id="h-brief">Successor briefing from {nameOf(c.employee_id)}</h2>
          {received ? <Status value="COMPLETED" label="Receipt confirmed" /> : <Status value="PENDING" label="Not yet received" />}
        </div>
        <span className="small muted">
          Approved version {c.package.versions.length}, approved by {nameOf(v.approved_by)}. This is a snapshot; current work status may have changed since.
        </span>
        <div className="list">
          {v.sections.map((s) => (
            <div key={s.title} className={`list-item ${s.evidence_type ? `stitched stitched-${s.evidence_type.toLowerCase()}` : ""}`}>
              <span className="row">
                <b>{s.title}</b> {s.evidence_type && <Evidence type={s.evidence_type} />}
              </span>
              <span>{s.content}</span>
            </div>
          ))}
        </div>
        <p className="small">Confirming receipt means you received this version. It doesn&apos;t transfer ownership; your manager confirms that separately.</p>
        {!received && (
          <div>
            <button className="btn btn-primary" disabled={cmd.pending} onClick={() => void cmd.run((cl, k) => cl.receivePackage(v.package_version_id, { idempotency_key: k }))}>
              Confirm receipt of this version
            </button>
          </div>
        )}
        {cmd.error && <ErrorNotice error={cmd.error} onDismiss={cmd.clearError} />}
      </section>
      <aside className="split-aside">
        <section className="chat" style={{ minHeight: 420 }}>
          <div className="chat-head">
            <h2>Ask about this package</h2>
          </div>
          <Transcript
            label="Package questions"
            onCite={setCite}
            messages={[
              { id: "intro", sender: "AI", text: "Ask about the approved package. Answers use only the approved snapshot and permitted sources.", provenance: "SCRIPTED_FIXTURE" },
              ...c.successor_qa.map((m) => ({ id: m.message_id, sender: m.sender, text: m.text, provenance: m.provenance, citations: m.citations, meta: <ListenButton cv={cv} m={m} /> })),
            ]}
          />
          <ScriptPrompts prompts={c.successor_prompts} disabled={cmd.pending} onPick={(p) => void send(p.text, "TEXT", p.prompt_id)} />
          {c.kt_available && <ReadAloudControls cv={cv} />}
          <ChatVoiceComposer cv={cv} label="Ask about the package" onSend={send} pending={cmd.pending} />
        </section>
      </aside>
      <SourceDrawer citation={cite} onClose={() => setCite(null)} />
    </div>
  );
}
