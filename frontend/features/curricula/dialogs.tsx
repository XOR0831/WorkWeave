"use client";

import { useRef, useState } from "react";
import { Dialog, ErrorNotice, Field } from "@/components/ui";
import { useCommand, useResource } from "@/lib/preview/client-context";
import { useOnChange } from "@/lib/preview/use-on-change";
import type { Curriculum, CurriculumSource, CurriculumSubtopicDef, CurriculumTopicDef } from "@/types/contracts";

// ---------------------------------------------------------------- upload
export function UploadDialog({ open, c, onClose, onStaged }: { open: boolean; c: Curriculum; onClose: () => void; onStaged: (source_id: string) => void }) {
  const cmd = useCommand();
  const catalog = useResource((cl) => (open ? cl.listCurricula() : Promise.resolve(null)), [open]);
  const sampleAvailable = Boolean(catalog.data?.sample_available);
  const fileRef = useRef<HTMLInputElement>(null);
  const [code, setCode] = useState("");
  const [title, setTitle] = useState("");
  const [version, setVersion] = useState("");
  const [file, setFile] = useState<{ name: string; size: number } | null>(null);
  const [sample, setSample] = useState(false);
  const reset = () => {
    setCode("");
    setTitle("");
    setVersion("");
    setFile(null);
    setSample(false);
    cmd.clearError();
    if (fileRef.current) fileRef.current.value = "";
  };
  useOnChange(open, () => {
    if (open) reset();
  });
  const dirty = Boolean(code || title || version || file || sample);
  const close = () => {
    reset();
    onClose();
  };
  return (
    <Dialog
      open={open}
      title="Upload a source document"
      dirty={dirty}
      onClose={close}
      footer={
        <>
          <button className="btn" onClick={close}>
            Cancel
          </button>
          <button
            className="btn btn-primary"
            disabled={cmd.pending || (!sample && (!file || !code.trim() || !title.trim() || !version.trim()))}
            onClick={async () => {
              const r = await cmd.run((cl, k) => cl.stageCurriculumSource(c.curriculum_id, { document_code: code, title, version, file: file ?? undefined, use_sample: sample }, { idempotency_key: k, expected_revision: c.revision }));
              if (r) {
                const staged = r.sources[r.sources.length - 1];
                reset();
                onClose();
                if (staged) onStaged(staged.curriculum_source_id);
              }
            }}
          >
            {cmd.pending ? "Staging…" : "Stage document"}
          </button>
        </>
      }
    >
      <div className="locked-target">
        <span className="eyebrow">Destination curriculum · set by this page</span>
        <b>
          {c.name} v{c.version}
        </b>
        <span className="small muted">
          Preview ID <code>{c.curriculum_id}</code>. The upload is linked to this curriculum; it never picks one from the filename or title.
        </span>
      </div>

      {sampleAvailable && (
        <div className="sample-choice">
          <button
            className="btn btn-small"
            aria-pressed={sample}
            onClick={() => {
              const on = !sample;
              setSample(on);
              setFile(null);
              if (fileRef.current) fileRef.current.value = "";
              setCode(on ? "SOP-001" : "");
              setTitle(on ? "Calibration and evidence handling" : "");
              setVersion(on ? "3.4" : "");
            }}
          >
            {sample ? "Using the synthetic sample" : "Use synthetic sample SOP-001 v3.4"}
          </button>
          <span className="small muted">The only source with a recorded H2/H3 outline in this preview.</span>
        </div>
      )}

      <Field label="Document code" htmlFor="up-code">
        <input id="up-code" type="text" value={code} maxLength={40} disabled={sample} onChange={(e) => setCode(e.target.value)} placeholder="SOP-001" />
      </Field>
      <Field label="Document title" htmlFor="up-title">
        <input id="up-title" type="text" value={title} maxLength={120} disabled={sample} onChange={(e) => setTitle(e.target.value)} />
      </Field>
      <Field label="Exact document version" htmlFor="up-version" hint="The link is to this exact version. A later version is a new upload.">
        <input id="up-version" type="text" value={version} maxLength={30} disabled={sample} onChange={(e) => setVersion(e.target.value)} placeholder="3.4" />
      </Field>
      <Field label="Source file (Markdown or plain text)" htmlFor="up-file" hint="Only the filename and size are used. The file isn't read, uploaded or stored.">
        <input
          id="up-file"
          ref={fileRef}
          type="file"
          accept=".md,.markdown,.txt,text/markdown,text/plain"
          disabled={sample}
          onChange={(e) => {
            const f = e.target.files?.[0];
            setFile(f ? { name: f.name, size: f.size } : null);
          }}
        />
      </Field>
      <p className="small file-status" role="status" aria-live="polite">
        {sample ? (
          <>
            <b>Selected:</b> SOP-001-v3.4-TEST.md (synthetic sample with a recorded outline)
          </>
        ) : file ? (
          <>
            <b>Selected file:</b> {file.name} ({Math.max(1, Math.round(file.size / 1024))} KB). Not uploaded, not processed.
          </>
        ) : (
          <span className="muted">No file selected.</span>
        )}
      </p>
      {cmd.error && <ErrorNotice error={cmd.error} />}
    </Dialog>
  );
}

// ---------------------------------------------------------------- objective
export function ObjectiveDialog({ c, subtopic, onClose }: { c: Curriculum; subtopic: CurriculumSubtopicDef | null; onClose: () => void }) {
  const cmd = useCommand();
  const [description, setDescription] = useState("");
  const [criteria, setCriteria] = useState("");
  useOnChange(subtopic?.subtopic_id, () => {
    setDescription(subtopic?.objective?.description ?? "");
    setCriteria(subtopic?.objective?.assessment_criteria ?? "");
    cmd.clearError();
  });
  const dirty = description !== (subtopic?.objective?.description ?? "") || criteria !== (subtopic?.objective?.assessment_criteria ?? "");
  return (
    <Dialog
      open={Boolean(subtopic)}
      title="Review learning objective"
      dirty={dirty}
      onClose={onClose}
      footer={
        <button
          className="btn btn-primary"
          disabled={cmd.pending || !dirty || !description.trim() || !criteria.trim()}
          onClick={async () => {
            const r = await cmd.run((cl, k) => cl.saveObjective(c.curriculum_id, subtopic!.subtopic_id, { description, assessment_criteria: criteria }, { idempotency_key: k, expected_revision: c.revision }));
            if (r) onClose();
          }}
        >
          {cmd.pending ? "Saving…" : "Save reviewed objective"}
        </button>
      }
    >
      <p className="small muted">
        <b>{subtopic?.name}</b>. Human-reviewed criteria decide completion; source headings alone never do.
      </p>
      <Field label="Learning objective" htmlFor="obj-desc">
        <textarea id="obj-desc" rows={3} maxLength={500} value={description} onChange={(e) => setDescription(e.target.value)} />
      </Field>
      <Field label="Assessment criteria (required evidence)" htmlFor="obj-crit" hint="What a learner must show. The tutor's assessment is external and isn't connected in this preview.">
        <textarea id="obj-crit" rows={3} maxLength={500} value={criteria} onChange={(e) => setCriteria(e.target.value)} />
      </Field>
      {cmd.error && <ErrorNotice error={cmd.error} />}
    </Dialog>
  );
}

// ---------------------------------------------------------------- learning path
export function PathDialog({ c, initial, title, proposal = false, onClose }: { c: Curriculum; initial: CurriculumTopicDef[] | null; title: string; proposal?: boolean; onClose: () => void }) {
  const cmd = useCommand();
  const [topics, setTopics] = useState<CurriculumTopicDef[]>([]);
  const seq = useRef(0);
  const nid = (p: string) => `new-${p}-${++seq.current}`;
  useOnChange(initial, () => {
    setTopics(initial ? structuredClone(initial) : []);
    cmd.clearError();
  });
  const dirty = proposal || JSON.stringify(topics) !== JSON.stringify(initial ?? []);
  const setTopic = (ti: number, t: CurriculumTopicDef) => setTopics(topics.map((x, i) => (i === ti ? t : x)));
  return (
    <Dialog
      open={Boolean(initial)}
      title={title}
      dirty={dirty}
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn btn-primary"
            disabled={cmd.pending || !dirty}
            onClick={async () => {
              const r = await cmd.run((cl, k) => cl.saveLearningPath(c.curriculum_id, topics, { idempotency_key: k, expected_revision: c.revision }));
              if (r) onClose();
            }}
          >
            {cmd.pending ? "Saving…" : proposal ? "Use as draft learning path" : "Save learning path"}
          </button>
        </>
      }
    >
      {proposal && (
        <div className="notice notice-info">
          <span>
            Proposed from the instructional H2/H3 headings. Rename, remove or add items before accepting. Reference-aid sections aren&apos;t included. Objectives stay blank for your review, and the matching sections are proposed as mappings that you still confirm.
          </span>
        </div>
      )}
      {topics.length === 0 && <p className="small muted">No topics yet.</p>}
      {topics.map((t, ti) => (
        <fieldset key={t.topic_id} className="path-edit">
          <legend className="sr-only">Topic {ti + 1}</legend>
          <div className="row">
            <label className="sr-only" htmlFor={`pt-${t.topic_id}`}>
              Topic {ti + 1} name
            </label>
            <input id={`pt-${t.topic_id}`} type="text" value={t.name} placeholder={`Topic ${ti + 1}`} onChange={(e) => setTopic(ti, { ...t, name: e.target.value })} style={{ flex: 1 }} />
            <button className="btn btn-small btn-ghost" aria-label={`Remove topic ${t.name || ti + 1}`} onClick={() => setTopics(topics.filter((_, i) => i !== ti))}>
              Remove
            </button>
          </div>
          <ol className="path-edit-subs">
            {t.subtopics.map((s, si) => (
              <li key={s.subtopic_id} className="row">
                <label className="sr-only" htmlFor={`ps-${s.subtopic_id}`}>
                  Subtopic {ti + 1}.{si + 1} name
                </label>
                <input id={`ps-${s.subtopic_id}`} type="text" value={s.name} placeholder={`Subtopic ${ti + 1}.${si + 1}`} onChange={(e) => setTopic(ti, { ...t, subtopics: t.subtopics.map((x, i) => (i === si ? { ...x, name: e.target.value } : x)) })} style={{ flex: 1 }} />
                <button className="btn btn-small btn-ghost" aria-label={`Remove subtopic ${s.name || `${ti + 1}.${si + 1}`}`} onClick={() => setTopic(ti, { ...t, subtopics: t.subtopics.filter((_, i) => i !== si) })}>
                  Remove
                </button>
              </li>
            ))}
          </ol>
          <button className="link-btn" onClick={() => setTopic(ti, { ...t, subtopics: [...t.subtopics, { subtopic_id: nid("sub"), name: "", order_index: t.subtopics.length + 1 }] })}>
            + Add subtopic
          </button>
        </fieldset>
      ))}
      <button className="btn btn-small" onClick={() => setTopics([...topics, { topic_id: nid("topic"), name: "", order_index: topics.length + 1, subtopics: [{ subtopic_id: nid("sub"), name: "", order_index: 1 }] }])}>
        Add topic
      </button>
      {cmd.error && <ErrorNotice error={cmd.error} />}
    </Dialog>
  );
}

// ---------------------------------------------------------------- review
export function ReviewDialog({ c, source, decision, onClose }: { c: Curriculum; source: CurriculumSource; decision: "APPROVED" | "REJECTED" | null; onClose: () => void }) {
  const cmd = useCommand();
  const [reason, setReason] = useState("");
  useOnChange(decision, () => {
    setReason("");
    cmd.clearError();
  });
  const mapped = source.sections.filter((s) => s.mapping.kind === "SUBTOPIC").length;
  const approve = decision === "APPROVED";
  return (
    <Dialog
      open={Boolean(decision)}
      title={approve ? "Approve this source version?" : "Reject this source version?"}
      dirty={reason.length > 0}
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>
            Cancel
          </button>
          <button
            className={approve ? "btn btn-primary" : "btn btn-danger"}
            disabled={cmd.pending || (!approve && !reason.trim())}
            onClick={async () => {
              const r = await cmd.run((cl, k) => cl.reviewSourceVersion(c.curriculum_id, source.curriculum_source_id, decision!, reason, { idempotency_key: k, expected_revision: c.revision }));
              if (r) onClose();
            }}
          >
            {cmd.pending ? "Saving…" : approve ? "Approve source version" : "Reject and remove"}
          </button>
        </>
      }
    >
      <div className="locked-target">
        <span className="eyebrow">Exact version under review</span>
        <b>
          {source.document_code} v{source.version}: {source.title}
        </b>
        <span className="small muted">
          {source.sections.length} H3 sections, {mapped} mapped to subtopics · for {c.name} v{c.version}
        </span>
      </div>
      {approve ? (
        <p>Approve this exact version and its confirmed mappings. This doesn&apos;t publish the curriculum or replace an existing approved SOP version.</p>
      ) : (
        <>
          <p>The staged document, its outline and mappings are removed. Only a short rejection note (document code, version, reviewer and your reason) remains.</p>
          <Field label="Reason for the coordinator" htmlFor="rej-reason" hint="Describe what to fix. Don't paste document content.">
            <textarea id="rej-reason" rows={3} maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)} />
          </Field>
        </>
      )}
      {cmd.error && <ErrorNotice error={cmd.error} />}
    </Dialog>
  );
}

// ---------------------------------------------------------------- publish
export function PublishDialog({ open, c, onClose }: { open: boolean; c: Curriculum; onClose: () => void }) {
  const cmd = useCommand();
  return (
    <Dialog
      open={open}
      title="Publish this curriculum?"
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn btn-primary"
            disabled={cmd.pending}
            onClick={async () => {
              const r = await cmd.run((cl, k) => cl.publishCurriculum(c.curriculum_id, { idempotency_key: k, expected_revision: c.revision }));
              if (r) onClose();
            }}
          >
            {cmd.pending ? "Publishing…" : `Publish ${c.name} v${c.version}`}
          </button>
        </>
      }
    >
      <p>Publishing freezes this reviewed learning path and its approved source links. Later changes need a draft revision.</p>
      <p className="small muted">It doesn&apos;t assign employees, and in this preview it doesn&apos;t change what the tutor teaches. Assignment is a separate, authorized step.</p>
      {cmd.error && <ErrorNotice error={cmd.error} />}
    </Dialog>
  );
}

// ---------------------------------------------------------------- unsaved-change guard
export function DiscardDialog({ open, onKeep, onDiscard }: { open: boolean; onKeep: () => void; onDiscard: () => void }) {
  return (
    <Dialog
      open={open}
      title="Discard unsaved mapping changes?"
      onClose={onKeep}
      footer={
        <>
          <button className="btn" onClick={onKeep}>
            Keep editing
          </button>
          <button className="btn btn-danger" onClick={onDiscard}>
            Discard changes
          </button>
        </>
      }
    >
      <p>You changed section mappings without saving. Switching sources discards those changes.</p>
    </Dialog>
  );
}
