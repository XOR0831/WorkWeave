"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { RequireSession } from "@/components/shell/AppShell";
import { Dialog, ErrorNotice, Field, Loading, PageError, PageHeader, StateView, Status } from "@/components/ui";
import { useCommand, useResource, useRuntime, useSession } from "@/lib/preview/client-context";
import { ReviewOutcomes, curriculumHref } from "@/features/curricula/shared";
import { ReadOnlyCatalog } from "@/features/curricula/RecordView";

export default function CurriculaPage() {
  return (
    <RequireSession>
      <Curricula />
    </RequireSession>
  );
}

function Curricula() {
  const { session } = useSession();
  const api = useRuntime().mode === "http";
  const q = useResource((c) => c.listCurricula(), [session?.persona.employee_id]);
  const [creating, setCreating] = useState(false);
  if (q.loading) return <Loading label="Loading curricula" />;
  if (q.error) return <PageError error={q.error} onRetry={q.reload} />;
  // API mode: read-only, database-backed view; authoring actions aren't rendered.
  if (api) return <ReadOnlyCatalog catalog={q.data!} companyName={session!.scenario.company_name} canManage={session!.persona.grants.includes("curriculum.manage")} />;
  const { curricula, receipts } = q.data!;
  return (
    <div className="stack">
      <PageHeader
        eyebrow={`${session!.scenario.company_name} · Coordinator workspace`}
        title="Curricula & sources"
        purpose="Start with the learning path. Upload documents from inside a curriculum, so the link is never guessed from a filename."
        actions={
          <button className="btn btn-primary" onClick={() => setCreating(true)}>
            Create curriculum
          </button>
        }
      />

      <ol className="flow-strip" aria-label="How a source becomes curriculum content">
        <li>Curriculum</li>
        <li>Exact document version</li>
        <li>H2/H3 outline</li>
        <li>Reviewed mappings</li>
        <li>Source approval</li>
        <li>Curriculum publication</li>
      </ol>

      {curricula.length === 0 ? (
        <StateView title="No curricula yet" action={<button className="btn btn-primary" onClick={() => setCreating(true)}>Create curriculum</button>}>
          Create a draft curriculum, then add its first source document from inside it.
        </StateView>
      ) : (
        <div className="grid-3">
          {curricula.map((c) => (
            <article key={c.curriculum_id} className="panel curriculum-card" aria-labelledby={`cur-${c.curriculum_id}`}>
              <div className="row-between">
                <Status value={c.status === "DRAFT" ? "DRAFT" : "PUBLISHED"} label={c.status === "DRAFT" ? "Draft" : "Published"} />
                <span className="small muted">v{c.version}</span>
              </div>
              <div>
                <h2 id={`cur-${c.curriculum_id}`}>{c.name}</h2>
                <p className="small muted">{c.status === "DRAFT" ? "Editable. Sources need review before publication." : "Frozen. Create a draft revision to change it."}</p>
              </div>
              <ul className="facts" aria-label="Contents">
                <li>
                  {c.topic_count} topic{c.topic_count === 1 ? "" : "s"}
                </li>
                <li>
                  {c.subtopic_count} subtopic{c.subtopic_count === 1 ? "" : "s"}
                </li>
                <li>
                  {c.source_count} source{c.source_count === 1 ? "" : "s"}
                </li>
              </ul>
              {c.pending_review_count > 0 && <Status value="PENDING_REVIEW" label={`${c.pending_review_count} source${c.pending_review_count === 1 ? "" : "s"} awaiting review`} />}
              <Link className="btn btn-full" href={curriculumHref(c.curriculum_id)} aria-describedby={`cur-${c.curriculum_id}`}>
                Open curriculum
              </Link>
            </article>
          ))}
        </div>
      )}

      <ReviewOutcomes receipts={receipts} />

      <p className="small muted">
        Preview only. Curricula, IDs, files and approvals live in this browser tab. Nothing is written to PostgreSQL or Cloud Storage, and no document is parsed or embedded.
      </p>
      <CreateCurriculum open={creating} onClose={() => setCreating(false)} />
    </div>
  );
}

function CreateCurriculum({ open, onClose }: { open: boolean; onClose: () => void }) {
  const cmd = useCommand();
  const router = useRouter();
  const [name, setName] = useState("");
  const [version, setVersion] = useState("1.0");
  const [description, setDescription] = useState("");
  const dirty = Boolean(name || description || version !== "1.0");
  const reset = () => {
    setName("");
    setVersion("1.0");
    setDescription("");
    cmd.clearError();
  };
  return (
    <Dialog
      open={open}
      title="Create a draft curriculum"
      dirty={dirty}
      onClose={() => {
        reset();
        onClose();
      }}
      footer={
        <button
          className="btn btn-primary"
          disabled={cmd.pending || !name.trim() || !version.trim()}
          onClick={async () => {
            const r = await cmd.run((c, k) => c.createCurriculum({ name, version, description }, { idempotency_key: k }));
            if (r) {
              reset();
              onClose();
              router.push(curriculumHref(r.curriculum_id));
            }
          }}
        >
          {cmd.pending ? "Creating…" : "Create draft curriculum"}
        </button>
      }
    >
      <p className="small muted">The curriculum gets its own ID first. Documents you upload from its page are linked to that ID through a separate, version-specific source link.</p>
      <Field label="Curriculum name" htmlFor="cur-name">
        <input id="cur-name" type="text" value={name} maxLength={100} onChange={(e) => setName(e.target.value)} placeholder="For example: Machine Fundamentals" />
      </Field>
      <Field label="Version" htmlFor="cur-version" hint="Name and version together must be unique.">
        <input id="cur-version" type="text" value={version} maxLength={30} onChange={(e) => setVersion(e.target.value)} />
      </Field>
      <Field label="Description (optional)" htmlFor="cur-desc">
        <textarea id="cur-desc" rows={2} value={description} maxLength={300} onChange={(e) => setDescription(e.target.value)} />
      </Field>
      {cmd.error && <ErrorNotice error={cmd.error} />}
    </Dialog>
  );
}
