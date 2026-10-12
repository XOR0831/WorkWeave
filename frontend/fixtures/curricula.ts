/**
 * Coordinator "Curricula & sources" fixtures (UI preview only).
 *
 * The published curriculum is derived from each pack's onboarding fixture. The Northstar sample
 * outline is a recorded H2/H3 parse of src/seed/sources/northstar/SOP-001-v3.4-TEST.md: H2 is a
 * source topic, H3 a source section, and H4+ headings stay inside the section's content
 * (blueprint/17 §curriculum and source mapping). It is replayed for the sample only; no file is
 * read, parsed, chunked or embedded in the browser.
 */
import type { Curriculum, CurriculumTopicDef, ParsedSourceSection, ScenarioKey } from "@/types/contracts";
import type { PackFixture } from "./types";

type SampleSection = Omit<ParsedSourceSection, "section_id" | "mapping" | "suggested_subtopic_id">;

const NORTHSTAR_SAMPLE: SampleSection[] = [
  {
    section_key: "h2:1/h3:1",
    topic_heading: "1. Fundamentals",
    topic_order_index: 1,
    subtopic_heading: "1. Find the current procedure",
    subtopic_order_index: 1,
    kind: "INSTRUCTION",
    excerpt: "Use this section when preparing for a calibration-related task, answering a coworker's procedure question, onboarding a new team member, or handing work to another shift or owner.",
    nested_headings: ["1.1 When this section applies", "1.2 Resolve the source in order", "1.3 If the source is missing or conflicting", "1.4 Evidence of correct source selection"],
  },
  {
    section_key: "h2:1/h3:2",
    topic_heading: "1. Fundamentals",
    topic_order_index: 1,
    subtopic_heading: "2. Separate history from evidence",
    subtopic_order_index: 2,
    kind: "INSTRUCTION",
    excerpt: "Every statement added to a work update should be recognizable as observed, reported, inferred or unknown.",
    nested_headings: ["2.1 Use explicit evidence labels", "2.2 Record the minimum useful work context", "2.3 Compare prior cases without copying conclusions", "2.4 Make uncertainty visible at handover and transfer", "2.5 Evidence-quality check"],
  },
  {
    section_key: "h2:1/h3:3",
    topic_heading: "1. Fundamentals",
    topic_order_index: 1,
    subtopic_heading: "3. Ask a clearer question",
    subtopic_order_index: 3,
    kind: "INSTRUCTION",
    excerpt: "Ask for clarification when the approved source is missing, out of scope, ambiguous, inaccessible, or contradicted by another source.",
    nested_headings: ["3.1 When clarification is needed", "3.2 Build the question from five parts", "3.3 Worked training example", "3.4 Close the information loop"],
  },
  {
    section_key: "h2:2/h3:1",
    topic_heading: "2. Reference aids",
    topic_order_index: 2,
    subtopic_heading: "A. Source-selection checklist",
    subtopic_order_index: 1,
    kind: "REFERENCE",
    excerpt: "Correct organization, asset and work item identified; controlled document record opened, not only a copied excerpt or search snippet.",
    nested_headings: [],
  },
  {
    section_key: "h2:2/h3:2",
    topic_heading: "2. Reference aids",
    topic_order_index: 2,
    subtopic_heading: "B. Work-evidence note template",
    subtopic_order_index: 2,
    kind: "REFERENCE",
    excerpt: "A field-by-field template: exact work item or asset identifiers, evidence status, remaining gap and reviewer.",
    nested_headings: [],
  },
  {
    section_key: "h2:2/h3:3",
    topic_heading: "2. Reference aids",
    topic_order_index: 2,
    subtopic_heading: "C. Training checks",
    subtopic_order_index: 3,
    kind: "REFERENCE",
    excerpt: "Discussion prompts such as: a search returns an older version above the current one; which version supplies current guidance, and why?",
    nested_headings: [],
  },
  {
    section_key: "h2:2/h3:4",
    topic_heading: "2. Reference aids",
    topic_order_index: 2,
    subtopic_heading: "D. Version and publication boundary",
    subtopic_order_index: 4,
    kind: "REFERENCE",
    excerpt: "This version is intentionally separate from the previously seeded approved versions; the approved current version controls retrieval, not the newest-looking file.",
    nested_headings: [],
  },
];

/** Recorded sample outline per pack. Only Northstar has one in this preview. */
export const SAMPLE_SOURCES: Partial<Record<ScenarioKey, { document_code: string; title: string; version: string; file_label: string; sections: SampleSection[] }>> = {
  northstar: { document_code: "SOP-001", title: "Calibration and evidence handling", version: "3.4", file_label: "SOP-001-v3.4-TEST.md", sections: NORTHSTAR_SAMPLE },
};

/** Reviewed assessment criteria for the seeded published curriculum (prototype curriculum.js). */
const NORTHSTAR_CRITERIA: Record<string, string> = {
  "ns-st-1": "Checks approval and current version before citing; keeps unknowns explicit.",
  "ns-st-2": "Doesn't transfer a prior diagnosis to a new ticket; labels evidence type.",
  "ns-st-3": "Names the work item, source, exact gap and authorized reviewer.",
};

/** Normalizes a heading for name-matching suggestions ("1. Find the current procedure" → "find the current procedure"). */
export const headingKey = (h: string) => h.replace(/^[\dA-Z]+[.)]\s*/, "").trim().toLowerCase();

export function seedCurricula(key: ScenarioKey, pack: PackFixture): Curriculum[] {
  const ob = pack.onboarding;
  const sample = SAMPLE_SOURCES[key];
  const topics: CurriculumTopicDef[] = ob.topics.map((t) => ({
    topic_id: t.topic_id,
    name: t.name,
    order_index: t.order_index,
    subtopics: t.subtopics.map((st) => ({
      subtopic_id: st.subtopic_id,
      name: st.name,
      order_index: st.order_index,
      objective: { description: st.objective ?? "", assessment_criteria: NORTHSTAR_CRITERIA[st.subtopic_id] ?? "Reviewed criteria are held in the pack's objective records." },
    })),
  }));
  const subs = topics.flatMap((t) => t.subtopics);
  const published: Curriculum = {
    curriculum_id: `${key}-curr-${ob.curriculum_version}`,
    name: ob.curriculum_name,
    version: ob.curriculum_version,
    status: "PUBLISHED",
    revision: 1,
    seeded: true,
    published_label: "Published in the pack fixture",
    topics,
    sources: ob.source_version_ids.flatMap((vid) => {
      const d = pack.documents.find((x) => x.document_version_id === vid);
      if (!d) return [];
      const sections: ParsedSourceSection[] =
        sample && sample.document_code === d.document_code && sample.version === d.version
          ? sample.sections.map((s, i) => {
              const match = subs.find((st) => headingKey(st.name) === headingKey(s.subtopic_heading));
              return { ...s, section_id: `${key}-pub-sec-${i + 1}`, mapping: match && s.kind === "INSTRUCTION" ? { kind: "SUBTOPIC", subtopic_id: match.subtopic_id } : { kind: "REFERENCE_ONLY" } };
            })
          : [];
      return [
        {
          curriculum_source_id: `${key}-cs-${vid}`,
          document_id: d.document_id,
          document_version_id: d.document_version_id,
          document_code: d.document_code,
          title: d.title,
          version: d.version,
          file_label: "Seeded approved version",
          origin: "SEEDED_APPROVED" as const,
          stage: "APPROVED" as const,
          sections,
          mappings_confirmed: true,
          approved_by: d.approved_by,
          revision: 1,
        },
      ];
    }),
  };
  if (!sample) return [published];
  // Northstar also starts with an editable draft revision (prototype walkthrough): same path and
  // objectives, no linked sources yet, so the upload flow starts from inside a known curriculum.
  const draft: Curriculum = {
    curriculum_id: `${key}-curr-draft-1-1`,
    name: ob.curriculum_name,
    version: "1.1",
    status: "DRAFT",
    revision: 1,
    seeded: true,
    derived_from_curriculum_id: published.curriculum_id,
    topics: topics.map((t) => ({ ...t, topic_id: `${t.topic_id}-r11`, subtopics: t.subtopics.map((st) => ({ ...st, subtopic_id: `${st.subtopic_id}-r11` })) })),
    sources: [],
  };
  return [published, draft];
}
