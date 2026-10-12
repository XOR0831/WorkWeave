"use client";

import { useState } from "react";
import { ErrorNotice, Status } from "@/components/ui";
import { useCommand, useSession } from "@/lib/preview/client-context";
import { useOnChange } from "@/lib/preview/use-on-change";
import type { Curriculum, CurriculumSource, CurriculumTopicDef, ParsedSourceSection, SectionMapping } from "@/types/contracts";
import { STAGE_LABEL, SourceTracker, StageBadge } from "./shared";
import { PathDialog, ReviewDialog } from "./dialogs";

const encode = (m: SectionMapping) => (m.kind === "SUBTOPIC" ? `sub:${m.subtopic_id}` : m.kind === "REFERENCE_ONLY" ? "ref" : "unresolved");
const decode = (v: string): SectionMapping => (v.startsWith("sub:") ? { kind: "SUBTOPIC", subtopic_id: v.slice(4) } : v === "ref" ? { kind: "REFERENCE_ONLY" } : { kind: "UNRESOLVED" });
const stripNum = (h: string) => h.replace(/^[\dA-Z]+[.)]\s*/, "");

/** A draft learning path proposed from the instructional H2/H3 outline; objectives stay blank for human review. */
function proposePath(source: CurriculumSource): CurriculumTopicDef[] {
  const inst = source.sections.filter((s) => s.kind === "INSTRUCTION");
  const h2 = [...new Map(inst.map((s) => [s.topic_order_index, s.topic_heading])).entries()];
  return h2.map(([order, heading]) => ({
    topic_id: `new-topic-${order}`,
    name: stripNum(heading),
    order_index: order,
    subtopics: inst
      .filter((s) => s.topic_order_index === order)
      .map((s) => ({ subtopic_id: `new-${s.section_key}`, name: stripNum(s.subtopic_heading), order_index: s.subtopic_order_index })),
  }));
}

export function SourceWorkspace({ c, source, isReviewer, onDirtyChange }: { c: Curriculum; source: CurriculumSource; isReviewer: boolean; onDirtyChange: (dirty: boolean) => void }) {
  const { session } = useSession();
  const cmd = useCommand();
  const draftCurriculum = c.status === "DRAFT";
  const editable = draftCurriculum && (source.stage === "PARSED" || source.stage === "MAPPED");
  const initial = Object.fromEntries(source.sections.map((s) => [s.section_id, encode(s.mapping)]));
  const [draft, setDraft] = useState<Record<string, string>>(initial);
  const [proposal, setProposal] = useState<CurriculumTopicDef[] | null>(null);
  const [review, setReview] = useState<"APPROVED" | "REJECTED" | null>(null);
  const dirty = source.sections.some((s) => draft[s.section_id] !== initial[s.section_id]);
  useOnChange(dirty, () => onDirtyChange(dirty));
  const subs = c.topics.flatMap((t) => t.subtopics);
  const counts = { mapped: 0, reference: 0, unresolved: 0 };
  source.sections.forEach((s) => {
    const v = draft[s.section_id] ?? "unresolved";
    if (v.startsWith("sub:")) counts.mapped += 1;
    else if (v === "ref") counts.reference += 1;
    else counts.unresolved += 1;
  });
  const mappings = () => Object.fromEntries(Object.entries(draft).map(([k, v]) => [k, decode(v)]));
  const save = async (confirm: boolean) => {
    const r = await cmd.run((cl, k) => cl.saveSourceMappings(c.curriculum_id, source.curriculum_source_id, mappings(), confirm, { idempotency_key: k, expected_revision: c.revision }));
    if (r) onDirtyChange(false);
  };
  const byTopic = [...new Map(source.sections.map((s) => [s.topic_order_index, s.topic_heading])).entries()];
  const selfSubmitted = source.submitted_by === `${session?.persona.first_name} ${session?.persona.last_name}`;

  return (
    <section className="panel source-ws" aria-labelledby="h-srcws">
      <div className="row-between">
        <div>
          <p className="eyebrow">Document version · {source.document_code}</p>
          <h2 id="h-srcws">
            {source.title} <span className="title-version">v{source.version}</span>
          </h2>
        </div>
        <StageBadge stage={source.stage} />
      </div>

      <div className={`provenance provenance-${source.origin.toLowerCase()}`}>
        {source.origin === "FILENAME_ONLY" ? (
          <>
            <b>Selected file: {source.file_label}</b>
            <span className="small">Only the filename was recorded. The file wasn&apos;t uploaded or read, and it can&apos;t be parsed in this preview, so this isn&apos;t a processed document.</span>
          </>
        ) : source.origin === "SYNTHETIC_FIXTURE" ? (
          <>
            <b>Synthetic sample: {source.file_label}</b>
            <span className="small">A recorded outline of the fictional SOP-001 v3.4 test source. The tutor already uses the approved v3.4 test overlay; this walkthrough&apos;s staging and review are separate and don&apos;t change it.</span>
          </>
        ) : (
          <>
            <b>Seeded approved version</b>
            <span className="small">Linked from the pack&apos;s knowledge library{source.approved_by ? `; approved by ${source.approved_by}` : ""}.</span>
          </>
        )}
      </div>

      <SourceTracker source={source} />
      <p className="small muted lineage">
        <b>{c.name} v{c.version}</b> → <b>{source.document_code} v{source.version}</b> → {source.sections.length ? `${source.sections.length} H3 sections` : "no outline yet"}. The curriculum was set by this page, not inferred from the file.
      </p>

      {cmd.error && <ErrorNotice error={cmd.error} onDismiss={cmd.clearError} />}

      {source.stage === "STAGED" && (
        <div className="notice notice-info stage-action">
          <span className="notice-title">{source.origin === "FILENAME_ONLY" ? "Can't process this file in the preview" : "Staged, not processed yet"}</span>
          <span>
            {source.origin === "FILENAME_ONLY"
              ? "Document parsing isn't connected, so this filename can't become a processed document here. Trying shows the real error; upload the synthetic sample to continue the walkthrough."
              : "Generate the H2/H3 outline. In this preview it replays a recorded outline of the sample; no parser, chunking or embedding runs."}
          </span>
          {draftCurriculum && (
            <div className="row">
              <button className="btn btn-primary btn-small" disabled={cmd.pending} onClick={() => void cmd.run((cl, k) => cl.parseCurriculumSource(c.curriculum_id, source.curriculum_source_id, { idempotency_key: k, expected_revision: c.revision }))}>
                {cmd.pending ? "Processing…" : source.origin === "FILENAME_ONLY" ? "Try to parse" : "Generate outline"}
              </button>
            </div>
          )}
        </div>
      )}

      {source.sections.length > 0 && (
        <>
          <div className="row-between">
            <div>
              <h3>Source outline and mappings</h3>
              <p className="small muted">H2 = source topic, H3 = source section. H4 and deeper stay inside the section&apos;s content. Proposed mappings are name matches from the fixture; nothing is linked until you confirm.</p>
            </div>
            {editable && c.topics.length === 0 && (
              <button className="btn btn-small" onClick={() => setProposal(proposePath(source))}>
                Propose learning path from outline
              </button>
            )}
          </div>

          {byTopic.map(([order, heading]) => (
            <div key={order} className="outline-group">
              <p className="outline-h2">
                <span className="heading-tag">H2</span> {heading}
              </p>
              <ul className="mapping-list">
                {source.sections
                  .filter((s) => s.topic_order_index === order)
                  .map((s) => (
                    <MappingRow key={s.section_id} s={s} value={draft[s.section_id] ?? "unresolved"} subs={subs} editable={editable} onChange={(v) => setDraft({ ...draft, [s.section_id]: v })} />
                  ))}
              </ul>
            </div>
          ))}

          <div className="mapping-foot" role="status" aria-live="polite">
            <span className="small">
              {counts.mapped} mapped · {counts.reference} reference only · {counts.unresolved} unresolved · {source.mappings_confirmed ? "Confirmed by coordinator" : "Not confirmed"}
              {dirty && <b className="unsaved"> · Unsaved changes</b>}
            </span>
            {editable && (
              <span className="row">
                {dirty && (
                  <button className="btn btn-small btn-ghost" onClick={() => setDraft(initial)}>
                    Discard changes
                  </button>
                )}
                <button className="btn btn-small" disabled={!dirty || cmd.pending} onClick={() => void save(false)}>
                  Save as draft
                </button>
                <button className="btn btn-small btn-primary" disabled={cmd.pending || subs.length === 0 || (source.mappings_confirmed && !dirty)} onClick={() => void save(true)}>
                  Confirm mappings
                </button>
              </span>
            )}
          </div>
          {editable && counts.unresolved > 0 && (
            <p className="small muted">Unresolved sections can be confirmed as they are. They won&apos;t teach any subtopic, and the publication gate still needs every subtopic covered by an approved source.</p>
          )}
          {editable && subs.length === 0 && <p className="small muted">Add a learning path first (or propose one from this outline), so sections have subtopics to map to.</p>}
        </>
      )}

      {source.stage === "MAPPED" && draftCurriculum && (
        <div className="notice notice-info stage-action">
          <span className="notice-title">Ready to submit for source review</span>
          <span>Submission sends this exact version and its confirmed mappings to a knowledge reviewer. Mappings lock while it&apos;s in review.</span>
          <div className="row">
            <button className="btn btn-primary btn-small" disabled={cmd.pending || dirty} onClick={() => void cmd.run((cl, k) => cl.submitSourceForReview(c.curriculum_id, source.curriculum_source_id, { idempotency_key: k, expected_revision: c.revision }))}>
              Submit for review
            </button>
            {dirty && <span className="small muted">Save or discard your mapping changes first.</span>}
          </div>
        </div>
      )}

      {source.stage === "PENDING_REVIEW" && (
        <div className="notice notice-warn stage-action">
          <span className="notice-title">In review: {source.document_code} v{source.version}</span>
          <span>
            Submitted by {source.submitted_by}. Approval applies to this exact version and its mappings only; it doesn&apos;t publish the curriculum.
            {selfSubmitted && isReviewer ? " In this pack the coordinator is also the knowledge reviewer; a real deployment may require a different person." : ""}
          </span>
          {isReviewer ? (
            <div className="row">
              <button className="btn btn-primary btn-small" onClick={() => setReview("APPROVED")}>
                Approve source version
              </button>
              <button className="btn btn-small btn-danger" onClick={() => setReview("REJECTED")}>
                Reject source version
              </button>
            </div>
          ) : (
            <span className="small muted">Waiting for a knowledge reviewer.</span>
          )}
        </div>
      )}

      {source.stage === "APPROVED" && (
        <div className="notice notice-ok stage-action">
          <span className="notice-title">Source version approved · curriculum publication is separate</span>
          <span>
            {source.document_code} v{source.version} is approved{source.approved_by ? ` by ${source.approved_by}` : ""}.{" "}
            {draftCurriculum ? "The curriculum still needs its own publication gate below." : "This published curriculum uses it as an approved source."}
          </span>
        </div>
      )}

      <PathDialog c={c} initial={proposal} title="Review proposed learning path" proposal onClose={() => setProposal(null)} />
      <ReviewDialog c={c} source={source} decision={review} onClose={() => setReview(null)} />
      <span className="sr-only">Current stage: {STAGE_LABEL[source.stage]}</span>
    </section>
  );
}

function MappingRow({ s, value, subs, editable, onChange }: { s: ParsedSourceSection; value: string; subs: { subtopic_id: string; name: string }[]; editable: boolean; onChange: (v: string) => void }) {
  const id = `map-${s.section_id}`;
  const suggested = s.suggested_subtopic_id ? `sub:${s.suggested_subtopic_id}` : undefined;
  return (
    <li className={`mapping-row ${value === "unresolved" && s.kind === "INSTRUCTION" ? "mapping-open" : ""}`}>
      <div className="mapping-source">
        <span className="small muted">
          <span className="heading-tag">H3</span> {s.section_key}
          {s.kind === "REFERENCE" && <span className="fixture-tag" style={{ marginLeft: 6 }}>Reference aid</span>}
        </span>
        <b>{s.subtopic_heading}</b>
        <span className="small">{s.excerpt}</span>
        {s.nested_headings.length > 0 && (
          <details className="small">
            <summary>{s.nested_headings.length} H4 headings kept as content</summary>
            <ul className="h4-list">
              {s.nested_headings.map((h) => (
                <li key={h}>{h}</li>
              ))}
            </ul>
          </details>
        )}
      </div>
      <span className="mapping-arrow" aria-hidden="true">
        →
      </span>
      <div className="mapping-target">
        <label htmlFor={id}>Learning subtopic for &ldquo;{s.subtopic_heading}&rdquo;</label>
        <select id={id} value={value} disabled={!editable} onChange={(e) => onChange(e.target.value)}>
          <option value="unresolved">Unresolved (decide later)</option>
          <option value="ref">Reference only (not a learning subtopic)</option>
          {subs.map((st) => (
            <option key={st.subtopic_id} value={`sub:${st.subtopic_id}`}>
              {st.name}
            </option>
          ))}
        </select>
        <span className="small muted">
          {value === suggested ? (
            <Status value="PROPOSED" label="Proposed: heading name match" />
          ) : value === "unresolved" ? (
            s.kind === "INSTRUCTION" ? "Instructional section without a subtopic" : "No decision yet"
          ) : value === "ref" ? (
            "Citable as reference; doesn't count toward learning progress"
          ) : (
            "Set by you"
          )}
        </span>
      </div>
    </li>
  );
}
