/**
 * API mode: curriculum authoring for curriculum:manage holders (owner decisions 2026-10-10, ADR-040).
 *
 * Create a draft → upload a numbered Markdown source (read in the browser, sent as text) → approve
 * that exact version (the manager may approve their own upload after confirming the review) →
 * the AI engineer's ingestion builds the learning path and embeddings in the background → write
 * each subtopic's objective → publish. Each is a separate command; nothing happens automatically.
 */
"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Dialog, ErrorNotice, Field, Status } from "@/components/ui";
import { useCommand } from "@/lib/preview/client-context";
import type { Curriculum, CurriculumSubtopicDef, LinkedSourceVersion } from "@/types/contracts";
import { curriculumHref } from "./shared";

const MAX_BYTES = 300_000;
type DocType = "SOP" | "PROCEDURE" | "GUIDE" | "CHECKLIST" | "REFERENCE";

export function CreateCurriculumButton() {
  const [open, setOpen] = useState(false);
  const cmd = useCommand();
  const router = useRouter();
  const [name, setName] = useState("");
  const [version, setVersion] = useState("1.0");
  const [description, setDescription] = useState("");
  const close = () => {
    setOpen(false);
    cmd.clearError();
  };
  return (
    <>
      <button className="btn btn-primary" onClick={() => setOpen(true)}>
        Create curriculum
      </button>
      <Dialog
        open={open}
        title="Create a draft curriculum"
        dirty={Boolean(name || description)}
        onClose={close}
        footer={
          <button
            className="btn btn-primary"
            disabled={cmd.pending || !name.trim() || !version.trim()}
            onClick={async () => {
              const r = await cmd.run((c, k) => c.createCurriculum({ name, version, description }, { idempotency_key: k }));
              if (r) {
                close();
                router.push(curriculumHref(r.curriculum_id));
              }
            }}
          >
            {cmd.pending ? "Creating…" : "Create draft curriculum"}
          </button>
        }
      >
        <p className="small muted">You add its source documents from inside the curriculum. Nothing is published until you publish it.</p>
        <Field label="Curriculum name" htmlFor="new-cur-name">
          <input id="new-cur-name" type="text" value={name} maxLength={100} onChange={(e) => setName(e.target.value)} placeholder="For example: Packaging Line Basics" />
        </Field>
        <Field label="Version" htmlFor="new-cur-version" hint="Name and version together must be unique.">
          <input id="new-cur-version" type="text" value={version} maxLength={30} onChange={(e) => setVersion(e.target.value)} />
        </Field>
        <Field label="Description (optional)" htmlFor="new-cur-desc">
          <textarea id="new-cur-desc" rows={2} value={description} maxLength={300} onChange={(e) => setDescription(e.target.value)} />
        </Field>
        {cmd.error && <ErrorNotice error={cmd.error} />}
      </Dialog>
    </>
  );
}

/** Keeps the record fresh while an ingestion job is queued or running. */
export function useIngestionPolling(c: Curriculum, reload: () => void) {
  const busy = (c.linked_sources ?? []).some((s) => s.ingestion && (s.ingestion.status === "QUEUED" || s.ingestion.status === "RUNNING"));
  useEffect(() => {
    if (!busy) return;
    const t = window.setInterval(reload, 3000);
    return () => window.clearInterval(t);
  }, [busy, reload]);
}

export function AuthoringPanel({ c }: { c: Curriculum }) {
  const cmd = useCommand();
  const checks = c.readiness ?? [];
  const ready = checks.length > 0 && checks.every((x) => x.passed);
  return (
    <section className="panel stack-s" aria-labelledby="h-authoring">
      <div className="row-between">
        <h2 id="h-authoring">Prepare and publish</h2>
        <button className="btn btn-primary" disabled={!ready || cmd.pending} onClick={() => void cmd.run((cl, k) => cl.publishCurriculum(c.curriculum_id, { idempotency_key: k, expected_revision: c.revision }))}>
          {cmd.pending ? "Publishing…" : "Publish curriculum"}
        </button>
      </div>
      <ul className="list" aria-label="Publication checks">
        {checks.map((x) => (
          <li key={x.key} className="row-between small">
            <span>{x.label}</span>
            <span className="row">
              <span className="muted">{x.detail}</span>
              <Status value={x.passed ? "COMPLETED" : "PENDING"} label={x.passed ? "Ready" : "Not yet"} />
            </span>
          </li>
        ))}
      </ul>
      <p className="small muted">Publishing freezes this version. It doesn&apos;t assign the curriculum to anyone.</p>
      {cmd.error && <ErrorNotice error={cmd.error} onDismiss={cmd.clearError} />}
      <UploadSource c={c} />
    </section>
  );
}

function UploadSource({ c }: { c: Curriculum }) {
  const cmd = useCommand();
  const [file, setFile] = useState<File | null>(null);
  const [code, setCode] = useState("");
  const [title, setTitle] = useState("");
  const [version, setVersion] = useState("1.0");
  const [type, setType] = useState<DocType>("SOP");
  const [problem, setProblem] = useState<string | null>(null);
  const upload = async () => {
    if (!file) return;
    if (file.size > MAX_BYTES) return setProblem(`The file is larger than ${MAX_BYTES / 1000} KB.`);
    const content = await file.text();
    setProblem(null);
    const r = await cmd.run((cl, k) =>
      cl.stageCurriculumSource(c.curriculum_id, { document_code: code, title, version, file: { name: file.name, size: file.size }, use_sample: false, content, document_type: type }, { idempotency_key: k, expected_revision: c.revision }),
    );
    if (r) {
      setFile(null);
      setCode("");
      setTitle("");
    }
  };
  return (
    <fieldset className="stack-s">
      <legend>Add a source document</legend>
      <p className="small muted">
        A Markdown file (.md) whose <code>##</code> headings are topics and <code>###</code> headings are subtopics, each numbered (<code>## 1. Start-up</code>, <code>### 1. Pre-start checks</code>). It&apos;s
        kept privately and waits for your review before anything is built from it.
      </p>
      <div className="grid-2">
        <Field label="Document code" htmlFor="src-code" hint="A new code, or an existing one to add a new version.">
          <input id="src-code" type="text" value={code} maxLength={40} onChange={(e) => setCode(e.target.value)} placeholder="PKG-001" />
        </Field>
        <Field label="Version" htmlFor="src-version">
          <input id="src-version" type="text" value={version} maxLength={30} onChange={(e) => setVersion(e.target.value)} />
        </Field>
        <Field label="Title" htmlFor="src-title">
          <input id="src-title" type="text" value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} />
        </Field>
        <Field label="Document type" htmlFor="src-type">
          <select id="src-type" value={type} onChange={(e) => setType(e.target.value as DocType)}>
            {(["SOP", "PROCEDURE", "GUIDE", "CHECKLIST", "REFERENCE"] as const).map((t) => (
              <option key={t} value={t}>
                {t === "SOP" ? "SOP" : t.charAt(0) + t.slice(1).toLowerCase()}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <Field label="Markdown file" htmlFor="src-file">
        <input id="src-file" type="file" accept=".md,.markdown,text/markdown" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </Field>
      {problem && (
        <p className="small" role="alert">
          {problem}
        </p>
      )}
      {cmd.error && <ErrorNotice error={cmd.error} onDismiss={cmd.clearError} />}
      <div>
        <button className="btn" disabled={!file || !code.trim() || !title.trim() || !version.trim() || cmd.pending} onClick={() => void upload()}>
          {cmd.pending ? "Uploading…" : "Upload for review"}
        </button>
      </div>
    </fieldset>
  );
}

const JOB_LABEL = { QUEUED: "Queued", RUNNING: "Building sections and embeddings…", SUCCEEDED: "Ingested", FAILED: "Ingestion failed" } as const;

/** Review of one exact uploaded version, and its ingestion status once approved. */
export function SourceActions({ c, s }: { c: Curriculum; s: LinkedSourceVersion }) {
  const cmd = useCommand();
  const [reviewed, setReviewed] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const ver = { expected_revision: c.revision };
  if (s.approval_status === "PENDING_REVIEW")
    return (
      <div className="stack-s">
        <label className="choice small">
          <input type="checkbox" checked={reviewed} onChange={(e) => setReviewed(e.target.checked)} /> I reviewed this exact version ({s.document_code} v{s.version})
        </label>
        <p className="small muted">You uploaded it and you approve it; the audit log records that. Approval makes it the current version and starts ingestion. Older versions stay as history.</p>
        <div className="row">
          <button className="btn btn-primary" disabled={!reviewed || cmd.pending} onClick={() => void cmd.run((cl, k) => cl.reviewSourceVersion(c.curriculum_id, s.curriculum_source_id, "APPROVED", "", { ...ver, idempotency_key: k }, true))}>
            Approve v{s.version}
          </button>
          <button className="btn" disabled={cmd.pending} onClick={() => setRejecting(true)}>
            Reject
          </button>
        </div>
        {rejecting && (
          <div className="stack-s">
            <Field label="Reason" htmlFor={`rej-${s.curriculum_source_id}`}>
              <textarea id={`rej-${s.curriculum_source_id}`} rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
            </Field>
            <div>
              <button className="btn btn-danger" disabled={!reason.trim() || cmd.pending} onClick={() => void cmd.run((cl, k) => cl.reviewSourceVersion(c.curriculum_id, s.curriculum_source_id, "REJECTED", reason, { ...ver, idempotency_key: k }))}>
                Reject and unlink
              </button>
            </div>
          </div>
        )}
        {cmd.error && <ErrorNotice error={cmd.error} onDismiss={cmd.clearError} />}
      </div>
    );
  if (s.approval_status !== "APPROVED") return null;
  const job = s.ingestion;
  if (!job)
    return <p className="small muted">{c.ingestion_available ? "Approved before ingestion was tracked." : "Approved. Ingestion isn't connected on this server, so no learning path or embeddings were built."}</p>;
  return (
    <div className="stack-s" role="status" aria-live="polite">
      <span className="row small">
        <Status value={job.status === "SUCCEEDED" ? "COMPLETED" : job.status === "FAILED" ? "FAILED" : "PENDING"} label={JOB_LABEL[job.status]} />
        <span className="muted">
          {job.status === "SUCCEEDED" ? "Sections, learning path and embeddings are stored." : `Attempt ${job.attempts}`}
        </span>
      </span>
      {job.status === "FAILED" && (
        <>
          {job.error_summary && <span className="small">{job.error_summary}</span>}
          <div>
            <button className="btn btn-small" disabled={cmd.pending} onClick={() => void cmd.run((cl, k) => cl.retryIngestion(c.curriculum_id, job.job_id, { idempotency_key: k }))}>
              Retry ingestion
            </button>
          </div>
        </>
      )}
      {cmd.error && <ErrorNotice error={cmd.error} onDismiss={cmd.clearError} />}
    </div>
  );
}

/** One subtopic's objective and assessment criteria, written by the manager before publishing. */
export function ObjectiveEditor({ c, s }: { c: Curriculum; s: CurriculumSubtopicDef }) {
  const cmd = useCommand();
  const stored = s.objectives?.[0];
  const storedCriteria = (() => {
    try {
      return stored ? (JSON.parse(stored.assessment_criteria) as { criteria?: string }).criteria ?? stored.assessment_criteria : "";
    } catch {
      return stored?.assessment_criteria ?? "";
    }
  })();
  const [editing, setEditing] = useState(!stored);
  const [description, setDescription] = useState(stored?.description ?? "");
  const [criteria, setCriteria] = useState(storedCriteria);
  if (!editing)
    return (
      <div>
        <button className="btn btn-small btn-ghost" onClick={() => setEditing(true)}>
          Edit objective
        </button>
      </div>
    );
  const id = `obj-${s.subtopic_id}`;
  return (
    <div className="stack-s">
      <Field label="Objective" htmlFor={`${id}-d`}>
        <input id={`${id}-d`} type="text" value={description} maxLength={1000} onChange={(e) => setDescription(e.target.value)} placeholder="What the learner can do after this subtopic" />
      </Field>
      <Field label="How it's assessed" htmlFor={`${id}-c`}>
        <input id={`${id}-c`} type="text" value={criteria} maxLength={2000} onChange={(e) => setCriteria(e.target.value)} placeholder="What a correct answer must include" />
      </Field>
      {cmd.error && <ErrorNotice error={cmd.error} onDismiss={cmd.clearError} />}
      <div className="row">
        <button
          className="btn btn-small"
          disabled={!description.trim() || !criteria.trim() || cmd.pending}
          onClick={async () => {
            const r = await cmd.run((cl, k) => cl.saveObjective(c.curriculum_id, s.subtopic_id, { description, assessment_criteria: criteria }, { idempotency_key: k, expected_revision: c.revision }));
            if (r) setEditing(false);
          }}
        >
          {cmd.pending ? "Saving…" : "Save objective"}
        </button>
        {stored && (
          <button className="btn btn-small btn-ghost" onClick={() => setEditing(false)}>
            Cancel
          </button>
        )}
      </div>
    </div>
  );
}

/**
 * ADR-050: a published curriculum changes only through a draft revision (1.0 → 1.1) that copies its
 * approved sources, path and objectives. People already learning keep their version; publishing the
 * revision archives this one and moves assignments nobody has started.
 */
export function CreateRevisionButton({ c }: { c: Curriculum }) {
  const cmd = useCommand();
  const open = (id: string) => {
    // Full navigation: the detail page reads ?id= from the address, which a client-side push doesn't announce.
    window.location.assign(curriculumHref(id));
  };
  if (c.draft_revision)
    return (
      <button className="btn btn-primary" onClick={() => open(c.draft_revision!.curriculum_id)}>
        Open draft v{c.draft_revision.version}
      </button>
    );
  return (
    <span className="stack-s" style={{ alignItems: "flex-end" }}>
      <button
        className="btn btn-primary"
        disabled={cmd.pending}
        onClick={async () => {
          const r = await cmd.run((cl, k) => cl.createCurriculumRevision(c.curriculum_id, { idempotency_key: k }));
          if (r) open(r.curriculum_id);
        }}
      >
        {cmd.pending ? "Creating…" : "Create draft revision"}
      </button>
      {cmd.error && <ErrorNotice error={cmd.error} onDismiss={cmd.clearError} />}
    </span>
  );
}

/** Draft path editing (ADR-050): move a topic within its document version. */
export function TopicMoveButtons({ c, topicId, first, last }: { c: Curriculum; topicId: string; first: boolean; last: boolean }) {
  const cmd = useCommand();
  const move = (direction: "UP" | "DOWN") => void cmd.run((cl, k) => cl.moveCurriculumTopic(c.curriculum_id, topicId, direction, { idempotency_key: k, expected_revision: c.revision }));
  return (
    <span className="row" style={{ gap: 4 }}>
      <button className="btn btn-small" disabled={first || cmd.pending} onClick={() => move("UP")} aria-label="Move topic up">
        ↑
      </button>
      <button className="btn btn-small" disabled={last || cmd.pending} onClick={() => move("DOWN")} aria-label="Move topic down">
        ↓
      </button>
      {cmd.error && <ErrorNotice error={cmd.error} onDismiss={cmd.clearError} />}
    </span>
  );
}

/** Leave a subtopic out of the path (it keeps its objective), or bring it back. */
export function SubtopicInclusion({ c, s }: { c: Curriculum; s: CurriculumSubtopicDef }) {
  const cmd = useCommand();
  return (
    <span className="row" style={{ gap: 6 }}>
      <button
        className="link-btn"
        disabled={cmd.pending}
        onClick={() => void cmd.run((cl, k) => cl.setSubtopicIncluded(c.curriculum_id, s.subtopic_id, Boolean(s.left_out), { idempotency_key: k, expected_revision: c.revision }))}
      >
        {s.left_out ? "Include in the path" : "Leave out of the path"}
      </button>
      {cmd.error && <ErrorNotice error={cmd.error} onDismiss={cmd.clearError} />}
    </span>
  );
}

/** Take a source (and the topics built from it) out of this draft. Published versions are untouched. */
export function RemoveSourceButton({ c, s }: { c: Curriculum; s: LinkedSourceVersion }) {
  const cmd = useCommand();
  const [confirming, setConfirming] = useState(false);
  if (!confirming)
    return (
      <button className="btn btn-small" onClick={() => setConfirming(true)}>
        Remove from this draft
      </button>
    );
  return (
    <div className="notice notice-warn stack-s" role="note">
      <span>
        Remove {s.document_code} v{s.version} from this draft? Its topics, subtopics and their objectives leave the draft. The document itself and published versions don&apos;t change.
      </span>
      <span className="row">
        <button className="btn btn-small btn-danger" disabled={cmd.pending} onClick={() => void cmd.run((cl, k) => cl.removeCurriculumSource(c.curriculum_id, s.curriculum_source_id, { idempotency_key: k, expected_revision: c.revision }))}>
          Remove
        </button>
        <button className="btn btn-small" onClick={() => setConfirming(false)}>
          Keep it
        </button>
      </span>
      {cmd.error && <ErrorNotice error={cmd.error} onDismiss={cmd.clearError} />}
    </div>
  );
}
