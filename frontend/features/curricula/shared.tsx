import { Status } from "@/components/ui";
import type { CurriculumSource, SourceReviewReceipt, SourceStage } from "@/types/contracts";

export const curriculumHref = (id: string) => `/curricula/detail/?id=${encodeURIComponent(id)}`;

export const STAGE_LABEL: Record<SourceStage, string> = {
  STAGED: "Staged",
  PARSED: "Outline ready",
  MAPPED: "Mappings confirmed",
  PENDING_REVIEW: "In review",
  APPROVED: "Approved",
};

const STAGE_TONE: Record<SourceStage, string> = { STAGED: "DRAFT", PARSED: "DRAFT", MAPPED: "PROPOSED", PENDING_REVIEW: "PENDING_REVIEW", APPROVED: "APPROVED" };

export function StageBadge({ stage }: { stage: SourceStage }) {
  return <Status value={STAGE_TONE[stage]} label={STAGE_LABEL[stage]} />;
}

const STEPS: { stage: SourceStage; label: string; note: (s: CurriculumSource) => string }[] = [
  { stage: "STAGED", label: "Staged", note: (s) => (s.origin === "FILENAME_ONLY" ? "Filename recorded. File not uploaded or read." : s.origin === "SEEDED_APPROVED" ? "Seeded approved version." : "Synthetic sample selected.") },
  { stage: "PARSED", label: "Outline", note: () => "H2 topics and H3 sections." },
  { stage: "MAPPED", label: "Mapped", note: () => "Coordinator confirmed." },
  { stage: "PENDING_REVIEW", label: "Review", note: () => "Exact version submitted." },
  { stage: "APPROVED", label: "Approved", note: () => "Source version only." },
];
const ORDER: SourceStage[] = STEPS.map((s) => s.stage);

/** Honest processing tracker: shows only stages this preview actually reached. */
export function SourceTracker({ source }: { source: CurriculumSource }) {
  const at = ORDER.indexOf(source.stage);
  const blocked = source.stage === "STAGED" && source.origin === "FILENAME_ONLY";
  return (
    <ol className="tracker" aria-label={`Processing: ${STAGE_LABEL[source.stage]}`}>
      {STEPS.map((step, i) => {
        const state = i < at || (i === at && step.stage === "APPROVED") ? "done" : i === at ? "current" : i === at + 1 && blocked ? "blocked" : "todo";
        return (
          <li key={step.stage} className={`tracker-step tracker-${state}`} aria-current={i === at ? "step" : undefined}>
            <span className="tracker-knot" aria-hidden="true">
              {state === "done" ? "✓" : i + 1}
            </span>
            <span>
              <b>{step.label}</b>
              <span className="small muted">{state === "blocked" ? "Parsing isn't connected." : i <= at ? step.note(source) : "Not reached"}</span>
            </span>
            <span className="sr-only">{state === "done" ? "complete" : state === "current" ? "current stage" : state === "blocked" ? "unavailable" : "not reached"}</span>
          </li>
        );
      })}
    </ol>
  );
}

/** Source review decisions, shown separately from curriculum publication. */
export function ReviewOutcomes({ receipts, title = "Source review outcomes" }: { receipts: SourceReviewReceipt[]; title?: string }) {
  if (!receipts.length) return null;
  return (
    <section className="panel" aria-labelledby="h-outcomes">
      <h2 id="h-outcomes">{title}</h2>
      <p className="small muted">Decisions on exact source versions. Approving a source doesn&apos;t publish a curriculum; rejected uploads are removed and only this note remains.</p>
      <ul className="list" style={{ marginTop: 12 }}>
        {receipts.map((r) => (
          <li key={r.receipt_id} className="list-item">
            <div className="row-between">
              <b>
                {r.document_code} v{r.version}
              </b>
              <Status value={r.decision} label={r.decision === "APPROVED" ? "Source approved" : "Source rejected"} />
            </div>
            <span className="small muted">
              {r.reviewer} · {r.label}
              {r.reason ? ` · Reason: ${r.reason}` : ""}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
