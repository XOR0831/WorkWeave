"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { RequireSession } from "@/components/shell/AppShell";
import { ErrorNotice, Loading, PageError, PageHeader, StateView, Status } from "@/components/ui";
import { useCommand, useResource, useRuntime, useSession } from "@/lib/preview/client-context";
import { CurriculumRecordView } from "@/features/curricula/RecordView";
import { useSearch } from "@/lib/preview/use-search";
import { useOnChange } from "@/lib/preview/use-on-change";
import { curriculumReadiness } from "@/lib/domain/rules";
import { StageBadge } from "@/features/curricula/shared";
import { LearningPathPanel } from "@/features/curricula/LearningPath";
import { SourceWorkspace } from "@/features/curricula/SourceWorkspace";
import { DiscardDialog, PublishDialog, UploadDialog } from "@/features/curricula/dialogs";
import type { Curriculum } from "@/types/contracts";

export default function CurriculumDetailPage() {
  return (
    <RequireSession>
      <Detail />
    </RequireSession>
  );
}

function Detail() {
  const search = useSearch();
  const id = search?.get("id") ?? "";
  const { session } = useSession();
  const api = useRuntime().mode === "http";
  const q = useResource((c) => (id ? c.getCurriculum(id) : Promise.resolve(null)), [id, session?.persona.employee_id]);
  if (search === null || q.loading) return <Loading label="Loading curriculum" />;
  if (!id)
    return (
      <StateView title="No curriculum selected" action={<Link className="btn btn-primary" href="/curricula/">All curricula</Link>}>
        Open a curriculum from the list to see its learning path and sources.
      </StateView>
    );
  if (q.error) return <PageError error={q.error} onRetry={q.reload} />;
  // API mode: read-only, database-backed view; authoring actions aren't rendered.
  if (api) return <CurriculumRecordView c={q.data!} companyName={session!.scenario.company_name} reload={q.reload} />;
  return <CurriculumWorkspace c={q.data!} />;
}

function CurriculumWorkspace({ c }: { c: Curriculum }) {
  const { session } = useSession();
  const cmd = useCommand();
  const [selected, setSelected] = useState<string | null>(c.sources[c.sources.length - 1]?.curriculum_source_id ?? null);
  const [mapDirty, setMapDirty] = useState(false);
  const [pendingSwitch, setPendingSwitch] = useState<string | null>(null);
  const [upload, setUpload] = useState(false);
  const [publish, setPublish] = useState(false);
  const draft = c.status === "DRAFT";
  const isReviewer = session!.persona.grants.includes("knowledge.review");
  const source = c.sources.find((s) => s.curriculum_source_id === selected) ?? c.sources[c.sources.length - 1] ?? null;
  // A rejected (removed) source falls back to the latest remaining one.
  useOnChange(c.sources.map((s) => s.curriculum_source_id).join("|"), () => {
    if (selected && !c.sources.some((s) => s.curriculum_source_id === selected)) setSelected(c.sources[c.sources.length - 1]?.curriculum_source_id ?? null);
  });
  // Unsaved mapping edits survive in-page work but warn before the tab is closed or reloaded.
  useEffect(() => {
    if (!mapDirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [mapDirty]);
  const select = (sid: string) => {
    if (sid === source?.curriculum_source_id) return;
    if (mapDirty) setPendingSwitch(sid);
    else setSelected(sid);
  };
  const checks = curriculumReadiness(c);
  const ready = checks.every((x) => x.passed);

  return (
    <div className="stack">
      <nav className="crumbs small" aria-label="Breadcrumb">
        <Link href="/curricula/">Curricula &amp; sources</Link> <span aria-hidden="true">›</span> <span aria-current="page">{c.name} v{c.version}</span>
      </nav>
      <PageHeader
        eyebrow={`${session!.scenario.company_name} · Coordinator workspace`}
        title={
          <>
            {c.name} <span className="title-version">v{c.version}</span>
          </>
        }
        purpose={draft ? "Build the learning path, add source documents from here, then review before publishing." : "Published versions are frozen. Create a draft revision to change sources or the learning path."}
        actions={
          <>
            <Status value={draft ? "DRAFT" : "PUBLISHED"} label={draft ? "Draft" : "Published"} />
            {draft ? (
              <button className="btn btn-primary" onClick={() => setUpload(true)}>
                Upload document
              </button>
            ) : (
              <RevisionButton c={c} />
            )}
          </>
        }
      />
      <p className="small muted id-line">
        {c.seeded ? "Seeded pack curriculum" : "Created in this browser tab"} · Preview ID <code>{c.curriculum_id}</code> · revision {c.revision}
        {c.published_label ? ` · ${c.published_label}` : ""}
      </p>
      {cmd.error && <ErrorNotice error={cmd.error} onDismiss={cmd.clearError} />}

      <div className="cur-grid">
        <LearningPathPanel c={c} />
        <section className="panel" aria-labelledby="h-sources">
          <div className="panel-head">
            <h2 id="h-sources">Linked sources</h2>
            <span className="small muted">Exact document versions</span>
          </div>
          {c.sources.length === 0 ? (
            <div className="empty-inline">
              <p className="small muted">No documents are linked yet. A document uploaded here carries this curriculum&apos;s ID automatically.</p>
              {draft && (
                <button className="btn btn-small" onClick={() => setUpload(true)}>
                  Upload document
                </button>
              )}
            </div>
          ) : (
            <ul className="source-list" aria-label="Linked source versions">
              {c.sources.map((s) => (
                <li key={s.curriculum_source_id}>
                  <button className="source-row" aria-pressed={s.curriculum_source_id === source?.curriculum_source_id} onClick={() => select(s.curriculum_source_id)}>
                    <span className="source-icon" aria-hidden="true">
                      ▤
                    </span>
                    <span className="source-text">
                      <b>
                        {s.document_code} v{s.version}
                      </b>
                      <span className="small muted">
                        {s.title} · {s.file_label}
                      </span>
                    </span>
                    <StageBadge stage={s.stage} />
                  </button>
                </li>
              ))}
            </ul>
          )}
          {draft && c.sources.length > 0 && (
            <button className="btn btn-small" style={{ marginTop: 12 }} onClick={() => setUpload(true)}>
              Add another source
            </button>
          )}
        </section>
      </div>

      {source ? (
        <SourceWorkspace key={`${source.curriculum_source_id}-${source.revision}`} c={c} source={source} isReviewer={isReviewer} onDirtyChange={setMapDirty} />
      ) : (
        <section className="panel empty-workspace" aria-labelledby="h-srcws">
          <h2 id="h-srcws">Source workspace</h2>
          <p className="muted">Upload a document from this curriculum to see its processing, H2/H3 outline and section mappings here.</p>
          {draft && (
            <button className="btn btn-primary" onClick={() => setUpload(true)}>
              Upload document
            </button>
          )}
        </section>
      )}

      {draft && (
        <section className="panel readiness" aria-labelledby="h-ready">
          <div className="row-between">
            <div>
              <p className="eyebrow">Publication gate</p>
              <h2 id="h-ready">{ready ? "Ready to publish" : "Not ready to publish yet"}</h2>
            </div>
            <button className="btn btn-primary" disabled={!ready} aria-describedby="ready-note" onClick={() => setPublish(true)}>
              Publish curriculum
            </button>
          </div>
          <ul className="checks">
            {checks.map((x) => (
              <li key={x.key} className={x.passed ? "check-pass" : "check-fail"}>
                <span className="check-mark" aria-hidden="true">
                  {x.passed ? "✓" : "○"}
                </span>
                <span>
                  <b>{x.label}</b>
                  <span className="small muted">
                    <span className="sr-only">{x.passed ? "Passed. " : "Not met. "}</span>
                    {x.detail}
                  </span>
                </span>
              </li>
            ))}
          </ul>
          <p id="ready-note" className="small muted">
            Publishing is a separate decision from approving a source. It freezes this version; it doesn&apos;t assign anyone or change the tutor&apos;s current curriculum in this preview.
          </p>
        </section>
      )}

      <details className="panel data-trace">
        <summary>How this maps to the data model</summary>
        <dl className="kv small">
          <dt>
            <code>curricula</code>
          </dt>
          <dd>This curriculum, {c.status.toLowerCase()} ({c.curriculum_id})</dd>
          <dt>
            <code>curriculum_sources</code>
          </dt>
          <dd>One row per linked exact document version ({c.sources.length}); the document row itself stores no curriculum ID</dd>
          <dt>
            <code>knowledge_sections</code>
          </dt>
          <dd>One row per parsed H3 under its H2; H4 and deeper stay inside the section content</dd>
          <dt>
            <code>curriculum_source_sections</code>
          </dt>
          <dd>Confirmed section → subtopic links; reference-only and unresolved sections have no row</dd>
          <dt>
            <code>learning_objectives</code>
          </dt>
          <dd>Reviewed objective and assessment criteria per subtopic</dd>
          <dt>
            <code>knowledge_chunks</code>
          </dt>
          <dd>Chunks and embeddings belong to the backend ingestion pipeline; none are created in this preview</dd>
        </dl>
        <p className="small muted">Preview IDs are browser-local. No PostgreSQL rows or Cloud Storage objects are written.</p>
      </details>

      <UploadDialog open={upload} c={c} onClose={() => setUpload(false)} onStaged={(sid) => setSelected(sid)} />
      <PublishDialog open={publish} c={c} onClose={() => setPublish(false)} />
      <DiscardDialog
        open={Boolean(pendingSwitch)}
        onKeep={() => setPendingSwitch(null)}
        onDiscard={() => {
          setMapDirty(false);
          setSelected(pendingSwitch);
          setPendingSwitch(null);
        }}
      />
    </div>
  );
}

function RevisionButton({ c }: { c: Curriculum }) {
  const cmd = useCommand();
  return (
    <>
      <button
        className="btn btn-primary"
        disabled={cmd.pending}
        onClick={async () => {
          const r = await cmd.run((cl, k) => cl.createCurriculumRevision(c.curriculum_id, { idempotency_key: k }));
          // Full navigation: this page reads ?id= from location, which client-side pushes don't announce.
          // eslint-disable-next-line @next/next/no-location-assign-relative-destination
          if (r) window.location.assign(`/curricula/detail/?id=${encodeURIComponent(r.curriculum_id)}`);
        }}
      >
        {cmd.pending ? "Opening…" : "Create draft revision"}
      </button>
      {cmd.error && <ErrorNotice error={cmd.error} onDismiss={cmd.clearError} />}
    </>
  );
}
