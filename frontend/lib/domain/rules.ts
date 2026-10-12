/**
 * Pure display rules over DTOs: explain why an action is blocked before the user tries it.
 * The server remains the authority (12-implementation-contracts); these only shape the UI.
 */
import type { Curriculum, ExitKtCase, HandoverWorkspace, ReadinessCheck } from "@/types/contracts";

/** Exit KT transfer guards: approved package receipt, matching successor, effective time. */
export function transferBlockers(c: ExitKtCase, transfer_id: string): string[] {
  const t = c.transfers.find((x) => x.transfer_id === transfer_id);
  if (!t) return ["Transfer not found"];
  const owner = t.final_owner_employee_id ?? t.recommended_owner_employee_id;
  const out: string[] = [];
  if (!owner) out.push("No successor selected");
  if (!c.package.current_approved_version_id) out.push("No approved successor package");
  else if (!c.package.receipts.some((r) => r.package_version_id === c.package.current_approved_version_id && r.employee_id === owner))
    out.push("Successor hasn't confirmed receipt of the current approved package");
  if (owner && owner !== c.package.successor_employee_id) out.push("The package is addressed to a different successor");
  if (!t.effective_reached) out.push("Effective time hasn't been reached or reviewed");
  return out;
}

/** Reviewed evidence that can resolve a KT checklist item. Receipts and conversations don't qualify. */
export function checklistEvidence(c: ExitKtCase, nameOf: (id?: string) => string): { ref: string; label: string }[] {
  return [
    ...c.artifacts
      .filter((a) => a.promotion)
      .map((a) => ({ ref: `promotion:${a.artifact_id}`, label: `${a.title} promoted as ${a.promotion!.document_version_label}` })),
    ...c.transfers
      .filter((t) => t.status === "TRANSFERRED")
      .map((t) => {
        const r = c.responsibilities.find((x) => x.responsibility_id === t.responsibility_id);
        return { ref: `transfer:${t.transfer_id}`, label: `${r?.title} transferred to ${nameOf(r?.owner_employee_id)}` };
      }),
  ];
}

/** Required template sections lacking content or an explicit declaration with reason. */
export function missingRequiredSections(w: Pick<HandoverWorkspace, "sections" | "draft_sections">): string[] {
  return w.sections
    .filter((s) => s.is_required)
    .filter((s) => {
      const d = w.draft_sections.find((x) => x.section_id === s.section_id);
      return !d || (!d.content.trim() && !(d.declaration && d.declaration_reason?.trim()));
    })
    .map((s) => s.name);
}

/**
 * Curriculum publication gate (blueprint/17: coordinator confirms target curriculum and reviewed
 * objectives before publication). Source approval is one input, never publication itself.
 */
const STAGE_TEXT = { STAGED: "staged, no outline yet", PARSED: "mappings not confirmed", MAPPED: "not submitted for review", PENDING_REVIEW: "in review", APPROVED: "approved" } as const;

export function curriculumReadiness(c: Curriculum): ReadinessCheck[] {
  const subs = c.topics.flatMap((t) => t.subtopics);
  const approved = c.sources.filter((s) => s.stage === "APPROVED");
  const unsettled = c.sources.filter((s) => s.stage !== "APPROVED");
  const missingObjectives = subs.filter((s) => !s.objective?.description.trim() || !s.objective?.assessment_criteria.trim());
  const uncovered = subs.filter((st) => !approved.some((src) => src.sections.some((x) => x.mapping.kind === "SUBTOPIC" && x.mapping.subtopic_id === st.subtopic_id)));
  const list = (xs: { name: string }[]) => xs.map((x) => x.name).join(", ");
  return [
    { key: "PATH", label: "Learning path has subtopics", passed: subs.length > 0, detail: subs.length ? `${c.topics.length} topic${c.topics.length === 1 ? "" : "s"}, ${subs.length} subtopic${subs.length === 1 ? "" : "s"}` : "Add topics and subtopics, or accept a parsed outline as the draft path." },
    { key: "SOURCE_APPROVED", label: "At least one approved source version", passed: approved.length > 0, detail: approved.length ? approved.map((s) => `${s.document_code} v${s.version}`).join(", ") : "Submit a source version and have it approved." },
    { key: "SOURCES_SETTLED", label: "No linked source still in progress", passed: unsettled.length === 0, detail: unsettled.length ? unsettled.map((s) => `${s.document_code} v${s.version}: ${STAGE_TEXT[s.stage]}`).join("; ") : "Every linked source is approved." },
    { key: "OBJECTIVES", label: "Every subtopic has a reviewed objective and assessment criteria", passed: subs.length > 0 && missingObjectives.length === 0, detail: missingObjectives.length ? `Missing: ${list(missingObjectives)}` : subs.length ? "All reviewed." : "No subtopics yet." },
    { key: "COVERAGE", label: "Every subtopic maps to an approved source section", passed: subs.length > 0 && uncovered.length === 0, detail: uncovered.length ? `No approved coverage: ${list(uncovered)}` : subs.length ? "All covered." : "No subtopics yet." },
  ];
}
