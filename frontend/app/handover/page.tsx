"use client";

import { useState } from "react";
import { RequireSession } from "@/components/shell/AppShell";
import { ChatErrorNote, ChatHeader, ScriptPrompts, SourceDrawer, Transcript } from "@/components/chat";
import { Dialog, ErrorNotice, Evidence, Loading, PageHeader, PageError, StateView, Status, humanize } from "@/components/ui";
import { useOnChange } from "@/lib/preview/use-on-change";
import { newKey, useClient, useCommand, useResource, useRuntime, useSession } from "@/lib/preview/client-context";
import { missingRequiredSections } from "@/lib/domain/rules";
import { ChatVoiceComposer, HANDOVER_VOICE, ListenButton, ReadAloudControls, useChatVoice } from "@/features/voice/ChatVoice";
import type { Citation, HandoverItem, HandoverPublication, HandoverSuggestion, HandoverWorkspace, TemplateSectionInput } from "@/types/contracts";

export default function HandoverPage() {
  return (
    <RequireSession>
      <LeadsOnly />
    </RequireSession>
  );
}

/** Shift Handover is only for shift leads (owner decision 2026-10-10); the server enforces it too. */
function LeadsOnly() {
  const { session } = useSession();
  if (!session?.persona.grants.includes("handover.publish"))
    return (
      <StateView title="Shift Handover is for shift leads">
        Your shift lead prepares and publishes the handover. Your own work, and anything handed over to you, is in the Work Companion.
      </StateView>
    );
  return <Handover />;
}

function Handover() {
  const { session } = useSession();
  // API: completion comes from the ticket system (ADR-033), disputes only flag, and the copilot isn't connected yet.
  const api = useRuntime().mode === "http";
  const ws = useResource((c) => c.getHandoverWorkspace(), [session?.persona.employee_id]);
  const cmd = useCommand();
  // The companion's own commands (ask, brief, gap check): their errors show in the chat, not at the page top.
  const chatCmd = useCommand();
  const [cite, setCite] = useState<Citation | null>(null);
  const [review, setReview] = useState(false);
  const [configure, setConfigure] = useState(false);
  const [preview, setPreview] = useState<HandoverSuggestion | null>(null);
  const [snapshot, setSnapshot] = useState<HandoverPublication | null>(null);
  const [highlight, setHighlight] = useState<string | null>(null);
  // Voice for the copilot (ADR-045): tap-to-talk, and new answers read aloud when switched on.
  const cv = useChatVoice({ channel: HANDOVER_VOICE, conversationId: ws.data?.handover_id, messages: ws.data?.copilot, enabled: Boolean(ws.data?.copilot_available) });

  if (ws.loading) return <Loading label="Loading handover" />;
  if (ws.error) return <PageError error={ws.error} onRetry={ws.reload} />;
  const w = ws.data!;
  const me = session!.persona.employee_id;
  const isLead = w.source.lead_employee_id === me && session!.persona.grants.includes("handover.publish");
  const pending = w.suggestions.filter((s) => s.status === "PENDING");
  // The latest answer's proposed edit, until a later message replaces it (docs/31: never applied by itself).
  const lastAi = [...w.copilot].reverse().find((m) => m.sender === "AI");
  const proposal = lastAi?.proposed_edit && w.draft_sections.find((d) => d.section_id === lastAi.proposed_edit!.section_id)?.content !== lastAi.proposed_edit.content ? lastAi.proposed_edit : null;
  const latestPub = w.publications[w.publications.length - 1];
  const incomingPub = [...w.publications].reverse().find((p) => w.occurrences.find((o) => o.shift_instance_id === p.target_shift_instance_id && (o.lead_employee_id === me || o.member_ids.includes(me))));
  const ackRequests = w.cycles.filter((c) => c.status === "PENDING" && w.occurrences.find((o) => o.shift_instance_id === c.requested_from_shift_instance_id)?.lead_employee_id === me);

  // No draft for the shift in progress yet (its lead hasn't opened it): nothing to brief or ask about.
  const noHandover = api && !w.handover_id;
  const send = async (text: string, input_kind: "TEXT" | "VOICE_TRANSCRIPT", prompt_id?: string) => Boolean(await chatCmd.run((c, k) => c.askHandoverCopilot({ idempotency_key: k, client_turn_id: newKey("turn"), text, input_kind, preview_prompt_id: prompt_id })));

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Shift continuity"
        title="Leave clarity for the next shift."
        purpose={isLead ? "The handover stays in view; the companion suggests, you decide." : "Read the published handover and confirm what you received."}
      />

      <section className="handover-band" aria-labelledby="h-hand">
        <div className="handover-band-main">
          <div className="stack-s">
            <h2 id="h-hand">
              {w.source.name} → {w.target.name} handover
            </h2>
            <span className="small muted">
              {w.template_name}, template v{w.template_version}. Source window {w.source.window_label}. Lead: {isLead ? "you" : "the source-shift lead"}.
            </span>
          </div>
          <div className="stack-s">
            <Status value={w.status} label={w.status === "PUBLISHED" ? `Published #${latestPub?.publication_number}` : `Draft revision ${w.revision}`} />
            {isLead && pending.length > 0 && (
              <span className="small band-attention">
                {pending.length} suggestion{pending.length === 1 ? "" : "s"} to review
              </span>
            )}
          </div>
          <ShiftThread w={w} />
          {isLead && (
            <div className="row handover-band-actions">
              {w.can_configure_template && (
                <button className="btn btn-small" onClick={() => setConfigure(true)}>
                  Configure sections
                </button>
              )}
              <button className="btn btn-primary" disabled={w.status === "PUBLISHED"} onClick={() => setReview(true)} data-tour="publish">
                Review and publish
              </button>
            </div>
          )}
        </div>
        {cmd.error && <ErrorNotice error={cmd.error} onRetry={cmd.error.code === "REVISION_CONFLICT" ? () => { cmd.clearError(); ws.reload(); } : undefined} onDismiss={cmd.clearError} />}
        {!isLead && <p className="small muted">You lead another shift: you see published handovers and current item status. The draft and its suggestions stay with the lead of the shift in progress.</p>}
      </section>

      <div className="split split--chat-first">
        <div className="stack" style={{ minWidth: 0 }}>
          {ackRequests.length > 0 && <AckPanel w={w} />}

          {incomingPub && <IncomingPanel w={w} pub={incomingPub} onOpen={() => setSnapshot(incomingPub)} />}

          {isLead ? (
            <HandoverDocument w={w} highlight={highlight} onEdited={setHighlight} />
          ) : (
            <section className="panel" aria-labelledby="h-ledger">
              <div className="panel-head">
                <h2 id="h-ledger">Persistent items</h2>
                <span className="small muted">Work status and source acknowledgement are tracked separately</span>
              </div>
              <ItemList w={w} items={w.items} isLead={false} />
            </section>
          )}

          <section className="panel" aria-labelledby="h-history">
            <h2 id="h-history" style={{ marginBottom: 10 }}>
              Publication history
            </h2>
            <ul className="list">
              {[...w.publications].reverse().map((p) => (
                <li key={p.publication_id} className="list-item">
                  <div className="row-between">
                    <span>
                      <b>#{p.publication_number}</b> {occ(w, p.source_shift_instance_id)} → {occ(w, p.target_shift_instance_id)}
                    </span>
                    <span className="row">
                      <Status value="PUBLISHED" label="Immutable snapshot" />
                      <button className="btn btn-small" onClick={() => setSnapshot(p)}>
                        View snapshot
                      </button>
                    </span>
                  </div>
                  <span className="small muted">
                    {p.published_label}. Template v{p.template_version}. {p.entries.length} items. Receipts: {p.receipts.length}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        </div>

        <aside className="split-aside" aria-label="Handover companion">
          <section className="chat chat-tall">
            <ChatHeader
              title="WorkWeave"
              subtitle={api ? (w.copilot_available ? "Answers from this handover's records · you decide" : "Companion not connected · the handover comes from the database") : "Scripted preview · keeps the next shift in the loop"}
            />
            {api && (w.can_check || (!isLead && w.copilot_available && w.copilot.length === 0)) && (
              <div className="row copilot-actions">
                {w.can_check && (
                  <button className="btn btn-small" disabled={chatCmd.pending} onClick={() => void chatCmd.run((c, k) => c.runHandoverGapCheck({ idempotency_key: k }))} data-tour="check-gaps">
                    {chatCmd.pending ? "Checking…" : "Check for gaps"}
                  </button>
                )}
                {!isLead && w.copilot_available && w.copilot.length === 0 && !noHandover && (
                  <button className="btn btn-small" disabled={chatCmd.pending} onClick={() => void send("", "TEXT")}>
                    {chatCmd.pending ? "Preparing…" : "Get the brief"}
                  </button>
                )}
              </div>
            )}
            <Transcript
              label="Handover companion"
              onCite={setCite}
              messages={w.copilot.map((m) => ({ id: m.message_id, sender: m.sender, text: m.text, provenance: m.provenance, citations: m.citations, meta: <ListenButton cv={cv} m={m} /> }))}
              footer={
                isLead && proposal ? (
                  <ProposedEdit w={w} edit={proposal} onApplied={setHighlight} />
                ) : isLead && pending.length > 0 ? (
                  <section className="suggestion-group" aria-labelledby="h-pending">
                    <h3 id="h-pending">
                      {pending.length} update{pending.length === 1 ? " needs" : "s need"} your attention
                    </h3>
                    {pending.map((s) => (
                      <SuggestionCard key={s.suggestion_id} s={s} w={w} onPreview={() => setPreview(s)} />
                    ))}
                  </section>
                ) : null
              }
            />
            {chatCmd.error && (
              <div style={{ padding: "0 14px" }}>
                <ChatErrorNote error={chatCmd.error} onDismiss={chatCmd.clearError} />
              </div>
            )}
            <ScriptPrompts prompts={w.script_prompts} disabled={chatCmd.pending} onPick={(p) => void send(p.text, "TEXT", p.prompt_id)} />
            {noHandover && (
              <p className="small muted" role="note" style={{ padding: "0 16px" }} data-testid="no-handover-yet">
                Nothing to ask about yet: the {w.source.name} shift&apos;s lead hasn&apos;t started this handover. The brief and questions open once they do.
              </p>
            )}
            {api && w.copilot_available && !noHandover && <ReadAloudControls cv={cv} />}
            <ChatVoiceComposer cv={cv} label="Ask the handover companion" onSend={send} pending={chatCmd.pending} disabled={noHandover} placeholder="Ask about this handover" />
          </section>
        </aside>
      </div>

      <SourceDrawer citation={cite} onClose={() => setCite(null)} />
      <ChangePreview s={preview} w={w} onClose={() => setPreview(null)} onAccepted={setHighlight} />
      <PublishReview open={review} w={w} onClose={() => setReview(false)} />
      <ConfigureSections open={configure} w={w} onClose={() => setConfigure(false)} />
      <SnapshotDialog pub={snapshot} w={w} onClose={() => setSnapshot(null)} />
    </div>
  );
}

const occ = (w: HandoverWorkspace, id: string) => w.occurrences.find((o) => o.shift_instance_id === id)?.name ?? id;

function ShiftThread({ w }: { w: HandoverWorkspace }) {
  return (
    <ol className="shift-steps" aria-label="Shift occurrences">
      {w.occurrences.map((o) => {
        const on = o.shift_instance_id === w.source.shift_instance_id;
        return (
          <li key={o.shift_instance_id} className={on ? "shift-step-on" : o.status === "SCHEDULED" ? "shift-step-future" : undefined}>
            <span className="shift-knot" aria-hidden="true" />
            <b>{o.name}</b> {on ? "current source" : o.shift_instance_id === w.target.shift_instance_id ? "receiving" : humanize(o.status).toLowerCase()}
          </li>
        );
      })}
    </ol>
  );
}

/** The lead's structured handover document: every section in template order, with its items. */
function HandoverDocument({ w, highlight, onEdited }: { w: HandoverWorkspace; highlight: string | null; onEdited: (sectionId: string) => void }) {
  const [editing, setEditing] = useState<string | null>(null);
  const hasContent = (id: string) => {
    const d = w.draft_sections.find((s) => s.section_id === id);
    return Boolean(d?.content || d?.declaration) || w.items.some((i) => i.section_id === id);
  };
  const shown = w.sections.filter((s) => s.is_required || hasContent(s.section_id) || editing === s.section_id);
  const empty = w.sections.filter((s) => !shown.includes(s));
  return (
    <section className="panel doc-panel" aria-labelledby="h-ledger">
      <div className="doc-head">
        <h2 id="h-ledger">Handover document</h2>
        <span className="small muted">Required sections need content, or an explicit unknown or not-applicable declaration.</span>
      </div>
      <div className="doc-body">
        {shown.map((s) => (
          <SectionBlock
            key={`${s.section_id}-${w.revision}`}
            w={w}
            sectionId={s.section_id}
            editing={editing === s.section_id}
            highlighted={highlight === s.section_id && w.last_change_section_id === s.section_id}
            onEdit={() => setEditing(s.section_id)}
            onDone={(saved) => {
              setEditing(null);
              if (saved) onEdited(s.section_id);
            }}
          />
        ))}
        {empty.length > 0 && (
          <div className="doc-add" role="group" aria-label="Add an optional section">
            {empty.map((s) => (
              <button key={s.section_id} className="btn btn-small doc-add-btn" onClick={() => setEditing(s.section_id)}>
                + {s.name}
              </button>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

function SectionBlock({ w, sectionId, editing, highlighted, onEdit, onDone }: { w: HandoverWorkspace; sectionId: string; editing: boolean; highlighted: boolean; onEdit: () => void; onDone: (saved: boolean) => void }) {
  const sec = w.sections.find((s) => s.section_id === sectionId)!;
  const draft = w.draft_sections.find((d) => d.section_id === sectionId);
  const items = w.items.filter((i) => i.section_id === sectionId);
  return (
    <div className={`doc-section ${highlighted ? "doc-section-updated" : ""}`}>
      <div className="row-between">
        <div className="row">
          <h3>{sec.name}</h3>
          {sec.is_required ? <Status value="PENDING" label="Required" /> : <span className="small muted">Optional</span>}
          {highlighted && <span className="updated-tag">Just updated</span>}
        </div>
        {!editing && (
          <button className="link-btn" onClick={onEdit} aria-label={`Edit ${sec.name}`}>
            Edit
          </button>
        )}
      </div>
      {editing ? (
        <SectionEditor w={w} sectionId={sectionId} onDone={onDone} />
      ) : draft?.declaration ? (
        <p>
          <Status value="PENDING" label={humanize(draft.declaration)} /> {draft.declaration_reason}
        </p>
      ) : draft?.content ? (
        <p>{draft.content}</p>
      ) : (
        <p className="small muted">{items.length ? "No summary for this section." : "Nothing recorded yet."}</p>
      )}
      {items.length > 0 && <ItemList w={w} items={items} isLead />}
    </div>
  );
}

function SectionEditor({ w, sectionId, onDone }: { w: HandoverWorkspace; sectionId: string; onDone: (saved: boolean) => void }) {
  const sec = w.sections.find((s) => s.section_id === sectionId)!;
  const draft = w.draft_sections.find((d) => d.section_id === sectionId);
  const cmd = useCommand();
  const client = useClient();
  const api = useRuntime().mode === "http";
  const [drafting, setDrafting] = useState(false);
  const [draftError, setDraftError] = useState<string | null>(null);
  const [unknowns, setUnknowns] = useState("");
  const [text, setText] = useState(draft?.content ?? "");
  const [decl, setDecl] = useState<"" | "UNKNOWN_WITH_FOLLOW_UP" | "NOT_APPLICABLE">(draft?.declaration ?? "");
  const [reason, setReason] = useState(draft?.declaration_reason ?? "");
  const dirty = text !== (draft?.content ?? "") || decl !== (draft?.declaration ?? "") || reason !== (draft?.declaration_reason ?? "");
  const id = `sec-${sectionId}`;
  return (
    <div className="stack-s">
      <label className="sr-only" htmlFor={id}>
        {sec.name}
      </label>
      <textarea id={id} value={text} onChange={(e) => setText(e.target.value)} rows={api && unknowns ? 6 : 3} autoFocus />
      {api && w.can_check && (
        <div className="row small">
          <button
            className="btn btn-small"
            disabled={drafting}
            onClick={async () => {
              setDrafting(true);
              setDraftError(null);
              try {
                const d = (await client.draftHandoverSections([sectionId]))[0];
                if (d) {
                  setText(d.content);
                  setUnknowns(d.unknowns.length ? d.unknowns.join("; ") : "");
                } else setDraftError("No draft came back for this section.");
              } catch (e) {
                setDraftError(e instanceof Error ? e.message : "The draft couldn't be made.");
              } finally {
                setDrafting(false);
              }
            }}
          >
            {drafting ? "Drafting…" : "Draft with AI"}
          </button>
          <span className="muted">A proposal from the records, for you to edit. Nothing is saved until you save the section.</span>
        </div>
      )}
      {unknowns && <p className="small muted">Not in the records: {unknowns}</p>}
      {draftError && (
        <p className="small" role="alert">
          {draftError}
        </p>
      )}
      {sec.is_required && (
        <div className="row">
          <label className="small" htmlFor={`${id}-decl`}>
            Or declare
          </label>
          <select id={`${id}-decl`} style={{ width: "auto" }} value={decl} onChange={(e) => setDecl(e.target.value as typeof decl)}>
            <option value="">No declaration</option>
            <option value="UNKNOWN_WITH_FOLLOW_UP">Unknown, with follow-up</option>
            <option value="NOT_APPLICABLE">Not applicable</option>
          </select>
          {decl && <input type="text" aria-label="Declaration reason" placeholder="Reason or follow-up" value={reason} onChange={(e) => setReason(e.target.value)} style={{ flex: 1, minWidth: 180 }} />}
        </div>
      )}
      {cmd.error && <ErrorNotice error={cmd.error} onDismiss={cmd.clearError} />}
      <div className="row">
        <button
          className="btn btn-small btn-primary"
          disabled={cmd.pending || !dirty}
          onClick={async () => {
            const r = await cmd.run((c, k) => c.editDraftSection(sectionId, text, { kind: decl || undefined, reason }, { idempotency_key: k, expected_revision: w.revision }));
            if (r) onDone(true);
          }}
        >
          {cmd.pending ? "Saving…" : "Save section"}
        </button>
        <button className="btn btn-small btn-ghost" onClick={() => onDone(false)}>
          {dirty ? "Discard" : "Cancel"}
        </button>
      </div>
    </div>
  );
}

function ItemList({ w, items, isLead }: { w: HandoverWorkspace; items: HandoverItem[]; isLead: boolean }) {
  const cmd = useCommand();
  const api = useRuntime().mode === "http";
  const [events, setEvents] = useState<HandoverItem | null>(null);
  return (
    <>
      <ul className="list">
        {items.map((i) => (
          <li key={i.handover_item_id} className={`list-item item-card stitched stitched-${i.evidence_type.toLowerCase()}`}>
            <div className="row-between">
              <b>
                <span className="mono-id">{i.display_id}</span> {i.title}
              </b>
              <Evidence type={i.evidence_type} />
            </div>
            <div className="row">
              <Status value={i.work_status} label={`Work: ${humanize(i.work_status)}`} />
              <Status value={i.acknowledgement_status} label={`Source ack: ${humanize(i.acknowledgement_status)}`} />
            </div>
            <span className="small">{i.description}</span>
            <span className="small muted">
              Originated {occ(w, i.originating_shift_instance_id)} · Source {i.source_label}
              {!isLead && <> · Section: {w.sections.find((s) => s.section_id === i.section_id)?.name}</>}
            </span>
            <div className="row">
              <button className="link-btn" onClick={() => setEvents(i)}>
                Item history
              </button>
              {!api && isLead && (i.work_status === "IN_PROGRESS" || i.work_status === "ACTIVE") && i.acknowledgement_status === "DISPUTED" && (
                <button className="btn btn-small" disabled={cmd.pending} onClick={() => void cmd.run((c, k) => c.confirmItemCompletion(i.handover_item_id, { idempotency_key: k, expected_revision: w.revision }))}>
                  Confirm completion again
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
      {cmd.error && <ErrorNotice error={cmd.error} onDismiss={cmd.clearError} />}
      <Dialog open={Boolean(events)} title={`${events?.display_id ?? ""} history`} onClose={() => setEvents(null)}>
        <ol className="list">
          {w.item_events
            .filter((e) => e.handover_item_id === events?.handover_item_id)
            .map((e) => (
              <li key={e.event_id} className="list-item small">
                <b>{e.shift_name}</b> {e.label}
              </li>
            ))}
        </ol>
        <p className="small muted">The same persistent item carries across shifts; publications keep their original snapshot.</p>
      </Dialog>
    </>
  );
}

function SuggestionCard({ s, w, onPreview }: { s: HandoverSuggestion; w: HandoverWorkspace; onPreview: () => void }) {
  const cmd = useCommand();
  return (
    <div className={`suggestion-card stitched stitched-${s.evidence_type.toLowerCase()}`}>
      <span className="suggestion-kind">{humanize(s.suggestion_type)}</span>
      <b>{s.title}</b>
      <span className="small">{s.reason}</span>
      <span className="small muted row">
        {s.source_label} <Evidence type={s.evidence_type} />
      </span>
      <div className="row">
        <button className="btn btn-small btn-primary" onClick={onPreview}>
          Review change
        </button>
        <button className="btn btn-small" disabled={cmd.pending} onClick={() => void cmd.run((c, k) => c.ignoreSuggestion(s.suggestion_id, { idempotency_key: k, expected_revision: w.revision }))}>
          Ignore
        </button>
      </div>
      {cmd.error && <ErrorNotice error={cmd.error} onDismiss={cmd.clearError} />}
    </div>
  );
}

/** Change preview: source, before/proposed, an editable activity note, then an explicit lead decision. */
function ChangePreview({ s, w, onClose, onAccepted }: { s: HandoverSuggestion | null; w: HandoverWorkspace; onClose: () => void; onAccepted: (sectionId: string) => void }) {
  const cmd = useCommand();
  const api = useRuntime().mode === "http";
  const item = w.items.find((i) => i.handover_item_id === s?.handover_item_id);
  const initial = !s ? "" : s.suggestion_type === "STATUS_UPDATE" ? `${item?.description ?? ""} ${api ? "A completion was reported; the ticket system decides when it's done." : "Completion reported (not yet validated)."}`.trim() : s.proposed;
  const [note, setNote] = useState(initial);
  useOnChange(s?.suggestion_id, () => setNote(initial));
  const act = async (mode: "APPLY" | "REPORT_ONLY" | "VALIDATE_COMPLETION") => {
    const r = await cmd.run((c, k) => c.acceptSuggestion(s!.suggestion_id, mode, { idempotency_key: k, expected_revision: w.revision }, note !== initial ? note : undefined));
    if (r) {
      if (r.last_change_section_id) onAccepted(r.last_change_section_id);
      onClose();
    }
  };
  return (
    <Dialog
      open={Boolean(s)}
      title="Review suggested change"
      onClose={onClose}
      dirty={note !== initial}
      footer={
        s?.suggestion_type === "STATUS_UPDATE" ? (
          <>
            <button className="btn" disabled={cmd.pending} onClick={() => void act("REPORT_ONLY")}>
              Add as report only
            </button>
            {!api && (
              <button className="btn btn-primary" disabled={cmd.pending} onClick={() => void act("VALIDATE_COMPLETION")}>
                Validate completion
              </button>
            )}
          </>
        ) : (
          <>
            <button className="btn" onClick={onClose}>
              Cancel
            </button>
            <button className="btn btn-primary" disabled={cmd.pending || !note.trim()} onClick={() => void act("APPLY")}>
              Accept into draft
            </button>
          </>
        )
      }
    >
      {s && (
        <>
          <div className="notice notice-quiet">
            <span>
              <b>Reason:</b> {s.reason}
            </span>
          </div>
          <dl className="kv">
            <dt>Item</dt>
            <dd>{item ? `${item.display_id} ${item.title}` : "New item"}</dd>
            <dt>Source</dt>
            <dd className="row">
              {s.source_label} <Evidence type={s.evidence_type} />
            </dd>
            {s.before && (
              <>
                <dt>Before</dt>
                <dd>{s.before}</dd>
              </>
            )}
          </dl>
          <div className="field">
            <label htmlFor="change-note">Proposed note (you can edit before accepting)</label>
            <textarea id="change-note" rows={4} value={note} onChange={(e) => setNote(e.target.value)} />
            <span className="hint">Keep unverified causes marked as unknown.</span>
          </div>
          {s.suggestion_type === "STATUS_UPDATE" && (
            <div className="notice notice-info">
              <span>
                <b>Report only</b> notes the report on the item; status stays {item?.work_status.toLowerCase().replace("_", " ")}.{" "}
                {api ? "The ticket system decides when it's done; resolving it there completes the item and asks the originating shift to acknowledge." : <><b>Validate completion</b> is your lead decision: work becomes completed and the originating shift is asked to acknowledge.</>}
              </span>
            </div>
          )}
          <p className="small muted">Accepting updates the draft only. Published snapshots never change.</p>
          {cmd.error && <ErrorNotice error={cmd.error} />}
        </>
      )}
    </Dialog>
  );
}

/** Template configuration: saving creates a new template version; earlier publications keep theirs. */
function ConfigureSections({ open, w, onClose }: { open: boolean; w: HandoverWorkspace; onClose: () => void }) {
  const cmd = useCommand();
  const initial = (): TemplateSectionInput[] => w.sections.map((s) => ({ section_id: s.section_id, name: s.name, is_required: s.is_required }));
  const [rows, setRows] = useState<TemplateSectionInput[]>(initial);
  const [added, setAdded] = useState("");
  useOnChange(open, () => {
    if (open) {
      setRows(initial());
      setAdded("");
      cmd.clearError();
    }
  });
  const dirty = JSON.stringify(rows) !== JSON.stringify(initial());
  const nextVersion = Number(w.template_version) + 1;
  return (
    <Dialog
      open={open}
      title="Configure sections"
      variant="drawer"
      onClose={onClose}
      dirty={dirty}
      footer={
        <>
          <span className="small muted" style={{ marginRight: "auto" }}>
            Saving creates template v{nextVersion}; published handovers keep the version they used.
          </span>
          <button
            className="btn btn-primary"
            disabled={!dirty || cmd.pending}
            onClick={async () => {
              const r = await cmd.run((c, k) => c.createTemplateVersion(rows, { idempotency_key: k, expected_revision: w.revision }));
              if (r) onClose();
            }}
          >
            {cmd.pending ? "Saving…" : "Save template"}
          </button>
        </>
      }
    >
      <p className="small muted">
        {w.template_name}, currently v{w.template_version}. Required sections must have content or an explicit declaration before you publish.
      </p>
      <ul className="list" aria-label="Sections">
        {rows.map((r, idx) => (
          <li key={r.section_id ?? `new-${idx}`} className="list-item config-row">
            <span>
              {r.name}
              {!r.section_id && <span className="fixture-tag" style={{ marginLeft: 8 }}>New</span>}
            </span>
            <label className="choice">
              <input
                type="checkbox"
                role="switch"
                checked={r.is_required}
                onChange={(e) => setRows(rows.map((x, i) => (i === idx ? { ...x, is_required: e.target.checked } : x)))}
              />
              Required
            </label>
          </li>
        ))}
      </ul>
      <div className="field">
        <label htmlFor="new-section">Add an optional section</label>
        <div className="row">
          <input id="new-section" type="text" value={added} onChange={(e) => setAdded(e.target.value)} placeholder="For example: Safety observations" style={{ flex: 1, minWidth: 180 }} />
          <button
            className="btn btn-small"
            disabled={!added.trim()}
            onClick={() => {
              setRows([...rows, { name: added.trim(), is_required: false }]);
              setAdded("");
            }}
          >
            Add section
          </button>
        </div>
        <span className="hint">Existing sections can be made optional but not removed, so earlier snapshots stay readable.</span>
      </div>
      {cmd.error && <ErrorNotice error={cmd.error} />}
    </Dialog>
  );
}

function PublishReview({ open, w, onClose }: { open: boolean; w: HandoverWorkspace; onClose: () => void }) {
  const cmd = useCommand();
  const [confirmed, setConfirmed] = useState(false);
  const missing = missingRequiredSections(w);
  const pending = w.suggestions.filter((s) => s.status === "PENDING");
  const unresolved = w.items.filter((i) => !["COMPLETED", "CLOSED", "CANCELLED"].includes(i.work_status));
  return (
    <Dialog
      open={open}
      title="Review and publish"
      onClose={() => {
        setConfirmed(false);
        onClose();
      }}
      footer={
        <button
          className="btn btn-primary"
          disabled={!confirmed || missing.length > 0 || cmd.pending}
          onClick={async () => {
            const r = await cmd.run((c, k) => c.publishHandover({ idempotency_key: k, expected_revision: w.revision }));
            if (r) {
              setConfirmed(false);
              onClose();
            }
          }}
        >
          {cmd.pending ? "Publishing…" : "Publish handover"}
        </button>
      }
    >
      <p>
        You&apos;re publishing directly as the {w.source.name} shift lead. No second reviewer is needed. The publication is an immutable snapshot for the {w.target.name} shift.
      </p>
      <section className="stack-s">
        <h3>Required sections</h3>
        {w.sections
          .filter((s) => s.is_required)
          .map((s) => (
            <span key={s.section_id} className="row">
              <Status value={missing.includes(s.name) ? "BLOCKED" : "COMPLETED"} label={missing.includes(s.name) ? "Missing" : "Ready"} /> {s.name}
            </span>
          ))}
      </section>
      <section className="stack-s">
        <h3>Disclosed open work</h3>
        {unresolved.map((i) => (
          <span key={i.handover_item_id} className="small">
            {i.display_id} {i.title}: {humanize(i.work_status).toLowerCase()}
          </span>
        ))}
      </section>
      {pending.length > 0 && (
        <div className="notice notice-warn">
          <span>
            {pending.length} suggestion{pending.length > 1 ? "s are" : " is"} still unreviewed. They won&apos;t be included unless you accept them.
          </span>
        </div>
      )}
      <dl className="kv small">
        <dt>Template</dt>
        <dd>v{w.template_version}</dd>
        <dt>Draft revision</dt>
        <dd>{w.revision}</dd>
        <dt>Audience</dt>
        <dd>{w.target.name} shift lead{w.target.lead_employee_id ? "" : " (none assigned)"}</dd>
      </dl>
      <label className="choice">
        <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />
        <span>I&apos;ve reviewed the sections, items and evidence.</span>
      </label>
      {missing.length > 0 && <ErrorNotice error={{ code: "GUARD_FAILED", message: `Add content or a declaration for: ${missing.join(", ")}.`, retryable: false }} />}
      {cmd.error && <ErrorNotice error={cmd.error} />}
    </Dialog>
  );
}

function IncomingPanel({ w, pub, onOpen }: { w: HandoverWorkspace; pub: HandoverPublication; onOpen: () => void }) {
  const cmd = useCommand();
  const { session } = useSession();
  const received = pub.receipts.some((r) => r.employee_id === session?.persona.employee_id);
  return (
    <section className="panel stack-s" aria-labelledby="h-incoming">
      <div className="row-between">
        <h2 id="h-incoming">
          Incoming handover #{pub.publication_number} from {occ(w, pub.source_shift_instance_id)}
        </h2>
        {received ? <Status value="COMPLETED" label="Receipt confirmed" /> : <Status value="PENDING" label="Not yet received" />}
      </div>
      <p className="small">Receipt means you received this version. It doesn&apos;t resolve work, acknowledge completions, or transfer responsibility.</p>
      <div className="row">
        <button className="btn" onClick={onOpen}>
          Read snapshot
        </button>
        {!received && (
          <button className="btn btn-primary" disabled={cmd.pending} onClick={() => void cmd.run((c, k) => c.confirmHandoverReceipt(pub.publication_id, { idempotency_key: k }))}>
            Confirm receipt of #{pub.publication_number}
          </button>
        )}
      </div>
      {cmd.error && <ErrorNotice error={cmd.error} />}
    </section>
  );
}

function AckPanel({ w }: { w: HandoverWorkspace }) {
  const cmd = useCommand();
  const api = useRuntime().mode === "http";
  const { session } = useSession();
  const [dispute, setDispute] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const me = session?.persona.employee_id;
  const mine = w.cycles.filter((c) => w.occurrences.find((o) => o.shift_instance_id === c.requested_from_shift_instance_id)?.lead_employee_id === me);
  return (
    <section className="panel stack-s" aria-labelledby="h-ack">
      <h2 id="h-ack">Completion acknowledgements for your originating shift</h2>
      <p className="small muted">
        Pending acknowledgements don&apos;t block later shifts. Acknowledging closes this completion cycle;{" "}
        {api ? "disputing flags it for follow-up and tells the assignee (the ticket system still decides its status)." : "disputing reopens the item."}
      </p>
      {mine.map((c) => {
        const it = w.items.find((i) => i.handover_item_id === c.handover_item_id);
        const current = it?.completion_cycle_id === c.completion_cycle_id;
        return (
          <div key={c.completion_cycle_id} className="list-item">
            <div className="row-between">
              <span>
                <span className="mono-id">{it?.display_id}</span> {it?.title}
              </span>
              <span className="row">
                <span className="small muted">Cycle {c.completion_cycle_id}</span>
                <Status value={c.status} />
                {!current && <Status value="SUPERSEDED" label="Older cycle" />}
              </span>
            </div>
            <span className="small">
              Completed in {occ(w, c.completed_in_shift_instance_id)}; acknowledgement requested from {occ(w, c.requested_from_shift_instance_id)}.
              {c.comment && ` Comment: ${c.comment}`}
            </span>
            {c.status === "PENDING" && (
              <div className="row">
                <button className="btn btn-small btn-primary" disabled={cmd.pending} onClick={() => void cmd.run((cl, k) => cl.acknowledgeCompletion(c.completion_cycle_id, "ACKNOWLEDGE", "", { idempotency_key: k }))}>
                  Acknowledge completion
                </button>
                <button className="btn btn-small btn-danger" onClick={() => setDispute(c.completion_cycle_id)}>
                  Dispute
                </button>
              </div>
            )}
            {c.status === "DISPUTED" && !current && (
              <div className="row">
                <button className="btn btn-small" disabled={cmd.pending} onClick={() => void cmd.run((cl, k) => cl.acknowledgeCompletion(c.completion_cycle_id, "ACKNOWLEDGE", "", { idempotency_key: k }))}>
                  Try acknowledging this older cycle
                </button>
                <span className="small muted">Demonstrates the stale-cycle guard</span>
              </div>
            )}
          </div>
        );
      })}
      {cmd.error && <ErrorNotice error={cmd.error} onDismiss={cmd.clearError} />}
      <Dialog
        open={Boolean(dispute)}
        title="Dispute completion"
        onClose={() => setDispute(null)}
        dirty={comment.length > 0}
        footer={
          <button
            className="btn btn-danger"
            disabled={cmd.pending}
            onClick={async () => {
              const r = await cmd.run((cl, k) => cl.acknowledgeCompletion(dispute!, "DISPUTE", comment, { idempotency_key: k }));
              if (r) {
                setDispute(null);
                setComment("");
              }
            }}
          >
            {api ? "Dispute" : "Dispute and reopen"}
          </button>
        }
      >
        <div className="field">
          <label htmlFor="disp">What&apos;s disputed and what follow-up is needed</label>
          <textarea id="disp" value={comment} onChange={(e) => setComment(e.target.value)} />
        </div>
        {cmd.error && <ErrorNotice error={cmd.error} />}
      </Dialog>
    </section>
  );
}

function SnapshotDialog({ pub, w, onClose }: { pub: HandoverPublication | null; w: HandoverWorkspace; onClose: () => void }) {
  const { nameOf } = useSession();
  return (
    <Dialog open={Boolean(pub)} title={pub ? `Publication #${pub.publication_number} snapshot` : "Snapshot"} onClose={onClose}>
      {pub && (
        <>
          <div className="notice notice-info">
            <span>
              Immutable snapshot published by {nameOf(pub.published_by)} ({pub.published_label}), template v{pub.template_version}. Later changes appear as current state below, never in this snapshot.
            </span>
          </div>
          {pub.sections
            .filter((s) => s.content || s.declaration)
            .map((s) => (
              <div key={s.section_id} className="stack-s">
                <h3>{w.sections.find((x) => x.section_id === s.section_id)?.name}</h3>
                <p>{s.content || `${humanize(s.declaration!)}: ${s.declaration_reason}`}</p>
              </div>
            ))}
          <h3>Items in this snapshot</h3>
          <div className="table-wrap" role="region" tabIndex={0} aria-label="Snapshot items (scrolls horizontally)">
            <table>
              <thead>
                <tr>
                  <th scope="col">Item</th>
                  <th scope="col">Snapshot status</th>
                  <th scope="col">Current status</th>
                </tr>
              </thead>
              <tbody>
                {pub.entries.map((e) => {
                  const cur = w.items.find((i) => i.handover_item_id === e.handover_item_id);
                  return (
                    <tr key={e.handover_item_id}>
                      <th scope="row">
                        {e.display_id} {e.title}
                        <br />
                        <span className="small muted">{e.snapshot_description}</span>
                      </th>
                      <td>
                        <Status value={e.snapshot_work_status} />
                      </td>
                      <td>{cur ? <Status value={cur.work_status} label={`Now: ${humanize(cur.work_status).toLowerCase()}`} /> : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="small muted">Receipts: {pub.receipts.map((r) => nameOf(r.employee_id)).join(", ") || "none yet"}.</p>
        </>
      )}
    </Dialog>
  );
}

/** A copilot answer's proposed edit (docs/31): shown to the outgoing lead, applied only if they apply it. */
function ProposedEdit({ w, edit, onApplied }: { w: HandoverWorkspace; edit: { section_id: string; content: string }; onApplied: (sectionId: string) => void }) {
  const cmd = useCommand();
  const sec = w.sections.find((x) => x.section_id === edit.section_id);
  return (
    <section className="suggestion-group" aria-labelledby="h-proposed">
      <h3 id="h-proposed">Proposed change to {sec?.name ?? "a section"}</h3>
      <div className="excerpt" style={{ whiteSpace: "pre-wrap" }}>
        {edit.content}
      </div>
      <p className="small muted">This replaces the section&apos;s current text in your draft. Nothing is published.</p>
      {cmd.error && <ErrorNotice error={cmd.error} onDismiss={cmd.clearError} />}
      <div>
        <button
          className="btn btn-small btn-primary"
          disabled={cmd.pending}
          onClick={async () => {
            const r = await cmd.run((c, k) => c.editDraftSection(edit.section_id, edit.content, {}, { idempotency_key: k, expected_revision: w.revision }));
            if (r) onApplied(edit.section_id);
          }}
        >
          Apply to draft
        </button>
      </div>
    </section>
  );
}
