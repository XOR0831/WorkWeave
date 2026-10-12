/**
 * API mode: curricula screens built only from what PostgreSQL stores.
 *
 * Authoring (ADR-040) is shown to curriculum:manage holders on drafts (features/curricula/Authoring):
 * create, upload Markdown, approve the exact version, ingestion status, objectives, publish.
 * Everyone else reads. Preview-only concepts with no stored column (processing stage, section kind,
 * excerpts, reference-only vs unresolved, review receipts) are stated as not recorded, not guessed.
 */
import Link from "next/link";
import { PageHeader, StateView, Status, Unavailable } from "@/components/ui";
import type { CurriculaCatalog, Curriculum, CurriculumStatus, CurriculumTopicDef, LinkedSourceVersion } from "@/types/contracts";
import { curriculumHref } from "./shared";
import { AuthoringPanel, CreateCurriculumButton, CreateRevisionButton, ObjectiveEditor, RemoveSourceButton, SourceActions, SubtopicInclusion, TopicMoveButtons, useIngestionPolling } from "./Authoring";

const STATUS_LABEL: Record<CurriculumStatus, string> = { DRAFT: "Draft", PUBLISHED: "Published", ARCHIVED: "Archived" };
const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;
const date = (iso: string) => new Date(iso).toLocaleDateString("en", { year: "numeric", month: "short", day: "numeric" });

export function AuthoringUnavailable({ reason = "role" }: { reason?: "role" | "frozen" }) {
  return (
    <Unavailable capability="Curriculum authoring">
      {reason === "frozen"
        ? "This curriculum is published, so it's frozen. To change it, create a draft revision: people already learning keep this version."
        : "Creating curricula, uploading sources, approving them and publishing are for curriculum managers. This view is read-only for you."}
    </Unavailable>
  );
}

export function ReadOnlyCatalog({ catalog, companyName, canManage = false }: { catalog: CurriculaCatalog; companyName: string; canManage?: boolean }) {
  const { curricula } = catalog;
  return (
    <div className="stack">
      <PageHeader
        eyebrow={`${companyName} · Coordinator workspace`}
        title="Curricula & sources"
        purpose="The curricula stored for this workspace, with their learning paths and linked source versions."
        actions={canManage ? <CreateCurriculumButton /> : undefined}
      />
      {!canManage && <AuthoringUnavailable />}
      {curricula.length === 0 ? (
        <StateView title="No curricula in this workspace">{canManage ? "Create a draft curriculum, then add its first source from inside it." : "This workspace has no curriculum records yet."}</StateView>
      ) : (
        <div className="grid-3">
          {curricula.map((c) => (
            <article key={c.curriculum_id} className="panel curriculum-card" aria-labelledby={`cur-${c.curriculum_id}`}>
              <div className="row-between">
                <Status value={c.status} label={STATUS_LABEL[c.status]} />
                <span className="small muted">v{c.version}</span>
              </div>
              <h2 id={`cur-${c.curriculum_id}`}>{c.name}</h2>
              <ul className="facts" aria-label="Contents">
                <li>{plural(c.topic_count, "topic")}</li>
                <li>{plural(c.subtopic_count, "subtopic")}</li>
                <li>{plural(c.source_count, "linked source version")}</li>
              </ul>
              {c.pending_review_count > 0 && <Status value="PENDING_REVIEW" label={`${plural(c.pending_review_count, "source version")} pending review`} />}
              <Link className="btn btn-full" href={curriculumHref(c.curriculum_id)} aria-describedby={`cur-${c.curriculum_id}`}>
                Open curriculum
              </Link>
            </article>
          ))}
        </div>
      )}
      <p className="small muted">Stored in PostgreSQL for this demo workspace.</p>
    </div>
  );
}

function subtopicNames(topics: CurriculumTopicDef[]) {
  return new Map(topics.flatMap((t) => t.subtopics.map((s) => [s.subtopic_id, `${t.name} › ${s.name}`] as const)));
}

function TopicList({ topics, start = 0, edit }: { topics: CurriculumTopicDef[]; start?: number; edit?: Curriculum }) {
  return (
    <ol className="path-tree">
      {topics.map((t, ti) => (
        <li key={t.topic_id}>
          <div className="row-between">
            <h3>
              <span className="path-num">{start + ti + 1}</span> {t.name}
            </h3>
            {edit && topics.length > 1 && <TopicMoveButtons c={edit} topicId={t.topic_id} first={ti === 0} last={ti === topics.length - 1} />}
          </div>
          {t.subtopics.length === 0 ? (
            <p className="small muted">No active subtopics.</p>
          ) : (
            <ol>
              {t.subtopics.map((s, si) => {
                const objectives = s.objectives ?? [];
                return (
                  <li key={s.subtopic_id} className={`path-sub${s.left_out ? " path-sub-out" : ""}`}>
                    <span className="path-num path-num-small">
                      {start + ti + 1}.{si + 1}
                    </span>
                    <span className="stack-s" style={{ gap: 4 }}>
                      <b>{s.name}</b>
                      {s.left_out && <Status value="DRAFT" label="Left out of the path" />}
                      {edit && <SubtopicInclusion c={edit} s={s} />}
                      {s.left_out ? null : objectives.length === 0 ? (
                        <Status value="MISSING" label="No objective stored" />
                      ) : (
                        objectives.map((o) => (
                          <span key={o.objective_id} className="small">
                            <span className="muted">Objective{o.required ? "" : " (optional)"}:</span> {o.description}{" "}
                            <span className="muted">
                              · Criteria {o.criteria_version}: <code style={{ overflowWrap: "anywhere" }}>{o.assessment_criteria}</code>
                            </span>
                          </span>
                        ))
                      )}
                      {edit && !s.left_out && <ObjectiveEditor c={edit} s={s} />}
                    </span>
                  </li>
                );
              })}
            </ol>
          )}
        </li>
      ))}
    </ol>
  );
}

function SourceRecord({ s, names, edit }: { s: LinkedSourceVersion; names: Map<string, string>; edit?: Curriculum }) {
  const headingId = `src-${s.curriculum_source_id}`;
  return (
    <section className="panel" aria-labelledby={headingId}>
      <div className="row-between">
        <div>
          <p className="eyebrow">{s.relationship_type === "TEACHES" ? "Teaches this curriculum" : "Supports this curriculum"}</p>
          <h3 id={headingId}>
            {s.document_code} v{s.version} · {s.title}
          </h3>
        </div>
        <span className="row">
          <Status value={s.approval_status} />
          <Status value={s.is_current_version ? "CURRENT" : s.temporal_status} label={s.is_current_version ? "Current version" : undefined} />
        </span>
      </div>
      <p className="small muted">
        {s.approved_by && s.approved_at ? `Approved by ${s.approved_by} on ${date(s.approved_at)}` : "No approval recorded"} · link revision {s.revision}
      </p>
      {edit && <SourceActions c={edit} s={s} />}
      {edit && (
        <div>
          <RemoveSourceButton c={edit} s={s} />
        </div>
      )}
      {s.source_revoked || s.sections === null ? (
        <div className="notice notice-warn" role="note">
          <span className="notice-title">Source revoked</span>
          <span>This version&apos;s source was revoked, so its section headings are withheld.</span>
        </div>
      ) : s.sections.length === 0 ? (
        <p className="small muted">No parsed H2/H3 sections are stored for this version.</p>
      ) : (
        <div className="table-wrap" role="region" tabIndex={0} aria-label={`${s.document_code} v${s.version} sections (scrolls horizontally)`}>
          <table>
            <thead>
              <tr>
                <th scope="col">Section</th>
                <th scope="col">H2 topic</th>
                <th scope="col">H3 heading</th>
                <th scope="col">Recorded link</th>
              </tr>
            </thead>
            <tbody>
              {s.sections.map((x) => (
                <tr key={x.section_id}>
                  <td>
                    <code>{x.section_key}</code>
                  </td>
                  <td>{x.topic_heading}</td>
                  <td>{x.subtopic_heading}</td>
                  <td>
                    {x.links.length === 0 ? (
                      <span className="muted">No link recorded</span>
                    ) : (
                      x.links.map((l) => (
                        <span key={`${l.subtopic_id}-${l.relationship_type}`} className="stack-s">
                          {names.get(l.subtopic_id) ?? "A subtopic outside the active path"} <span className="small muted">({l.relationship_type.toLowerCase()})</span>
                        </span>
                      ))
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function CurriculumRecordView({ c, companyName, reload = () => undefined }: { c: Curriculum; companyName: string; reload?: () => void }) {
  const edit = c.can_manage && c.status === "DRAFT" ? c : undefined;
  useIngestionPolling(c, reload);
  const learner = c.topics.filter((t) => !t.document_version_id);
  const sources = c.linked_sources ?? [];
  const byVersion = new Map(sources.map((s) => [s.document_version_id, s]));
  const documentTopics = [...new Set(c.topics.filter((t) => t.document_version_id).map((t) => t.document_version_id!))];
  const names = subtopicNames(c.topics);
  return (
    <div className="stack">
      <nav className="crumbs small" aria-label="Breadcrumb">
        <Link href="/curricula/">Curricula &amp; sources</Link> <span aria-hidden="true">›</span> <span aria-current="page">{c.name} v{c.version}</span>
      </nav>
      <PageHeader
        eyebrow={`${companyName} · Coordinator workspace`}
        title={
          <>
            {c.name} <span className="title-version">v{c.version}</span>
          </>
        }
        purpose={c.description || "Learning path and linked source versions, as stored."}
        actions={
          <>
            <Status value={c.status} label={STATUS_LABEL[c.status]} />
            {c.can_manage && c.status === "PUBLISHED" && <CreateRevisionButton c={c} />}
          </>
        }
      />
      <p className="small muted id-line">
        Database ID <code>{c.curriculum_id}</code> · revision {c.revision}
        {c.published_at ? ` · published ${date(c.published_at)}` : ""}
      </p>
      <VersionsLine c={c} />
      {edit ? <AuthoringPanel c={edit} /> : <AuthoringUnavailable reason={c.can_manage ? "frozen" : "role"} />}

      <section className="panel" aria-labelledby="h-path">
        <div className="panel-head">
          <div>
            <h2 id="h-path">Learning path</h2>
            <p className="small muted">Active topics and subtopics with their stored objectives.</p>
          </div>
        </div>
        {learner.length === 0 ? (
          documentTopics.length === 0 && <p className="small muted">{edit ? "The learning path appears here once an approved source is ingested." : "No learner-path topics are stored."}</p>
        ) : (
          <TopicList topics={learner} edit={edit} />
        )}
        {documentTopics.map((v) => {
          const src = byVersion.get(v);
          const topics = c.topics.filter((t) => t.document_version_id === v);
          return (
            <div key={v} className="stack-s" style={{ marginTop: 16 }}>
              <h3 className="small">Topics bound to {src ? `${src.document_code} v${src.version}` : "a document version that isn't linked to this curriculum"}</h3>
              <p className="small muted">Their order is local to that document version.</p>
              <TopicList topics={topics} edit={edit} />
            </div>
          );
        })}
      </section>

      <section className="stack" aria-labelledby="h-sources">
        <div className="panel-head">
          <div>
            <h2 id="h-sources">Linked source versions</h2>
            <p className="small muted">
              Exact document versions linked in <code>curriculum_sources</code>. Section content and excerpts aren&apos;t shown here, and an unlinked section may be reference-only or unresolved; that distinction isn&apos;t stored.
            </p>
          </div>
        </div>
        {sources.length === 0 ? (
          <StateView title="No linked source versions">No document version is linked to this curriculum in the database.</StateView>
        ) : (
          sources.map((s) => <SourceRecord key={s.curriculum_source_id} s={s} names={names} edit={edit} />)
        )}
      </section>
    </div>
  );
}

/** ADR-050: where this version sits among the curriculum's versions. */
function VersionsLine({ c }: { c: Curriculum }) {
  const others = c.other_versions ?? [];
  const replacedBy = others.find((v) => v.status === "PUBLISHED");
  return (
    <>
      {c.status === "ARCHIVED" && (
        <div className="notice notice-info" role="note">
          <span className="notice-title">Replaced{replacedBy ? ` by v${replacedBy.version}` : ""}</span>
          <span>People who had already started keep learning this version. New and not-yet-started assignments use the newer version.</span>
        </div>
      )}
      {c.status === "DRAFT" && others.some((v) => v.status === "PUBLISHED") && (
        <div className="notice notice-info" role="note">
          <span className="notice-title">Draft revision of v{others.find((v) => v.status === "PUBLISHED")!.version}</span>
          <span>
            It started as a copy of the published version. To update a document, upload its newer version here: once approved and ingested it replaces the old one, and objectives follow subtopics with the same heading. Publishing archives the previous version; people who already started keep it.
          </span>
        </div>
      )}
      {others.length > 0 && (
        <p className="small muted">
          Other versions:{" "}
          {others.map((v, i) => (
            <span key={v.curriculum_id}>
              {i > 0 && " · "}
              <a href={curriculumHref(v.curriculum_id)}>v{v.version}</a> ({STATUS_LABEL[v.status].toLowerCase()})
            </span>
          ))}
        </p>
      )}
    </>
  );
}
