import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { CurriculumRecordView, ReadOnlyCatalog } from "@/features/curricula/RecordView";
import type { CurriculaCatalog, Curriculum } from "@/types/contracts";

// Labelled test data shaped like the API responses (GET /curricula, GET /curricula/{id}).
const TEST_CATALOG: CurriculaCatalog = {
  curricula: [
    { curriculum_id: "test-cur-1", name: "Machine Fundamentals", version: "1.0", status: "PUBLISHED", topic_count: 1, subtopic_count: 3, source_count: 2, pending_review_count: 1 },
    { curriculum_id: "test-cur-2", name: "Old Path", version: "0.9", status: "ARCHIVED", topic_count: 0, subtopic_count: 0, source_count: 0, pending_review_count: 0 },
  ],
  receipts: [],
  sample_available: false,
};

const TEST_CURRICULUM: Curriculum = {
  curriculum_id: "test-cur-1",
  name: "Machine Fundamentals",
  version: "1.0",
  status: "PUBLISHED",
  revision: 4,
  published_at: "2026-09-01T00:00:00Z",
  seeded: true,
  sources: [],
  topics: [
    {
      topic_id: "test-t1",
      name: "Machine Fundamentals",
      order_index: 1,
      document_version_id: null,
      subtopics: [
        { subtopic_id: "test-s1", name: "Find the current procedure", order_index: 1, objectives: [{ objective_id: "test-o1", description: "Demonstrate find the current procedure.", assessment_criteria: '{"required_checks":["use_current_approved_evidence"]}', criteria_version: "synthetic-criteria-v1", required: true }] },
        { subtopic_id: "test-s2", name: "Ask a clearer question", order_index: 2, objectives: [] },
      ],
    },
  ],
  linked_sources: [
    {
      curriculum_source_id: "test-cs1",
      document_id: "test-d1",
      document_version_id: "test-v34",
      document_code: "SOP-001",
      title: "Machine start-up",
      version: "3.4",
      relationship_type: "TEACHES",
      approval_status: "APPROVED",
      temporal_status: "CURRENT",
      is_current_version: true,
      approved_by: "Morgan Lee",
      approved_at: "2026-09-30T00:00:00Z",
      source_revoked: false,
      revision: 1,
      sections: [
        { section_id: "test-sec1", section_key: "h2:1/h3:1", topic_heading: "Fundamentals", subtopic_heading: "Find the current procedure", topic_order_index: 1, subtopic_order_index: 1, links: [{ topic_id: "test-t1", subtopic_id: "test-s1", relationship_type: "TEACHES" }] },
        { section_id: "test-sec2", section_key: "h2:2/h3:1", topic_heading: "Reference aids", subtopic_heading: "Glossary", topic_order_index: 2, subtopic_order_index: 1, links: [] },
      ],
    },
    {
      curriculum_source_id: "test-cs2",
      document_id: "test-d1",
      document_version_id: "test-v40",
      document_code: "SOP-001",
      title: "Machine start-up",
      version: "4.0-draft",
      relationship_type: "SUPPORTS",
      approval_status: "PENDING_REVIEW",
      temporal_status: "CURRENT",
      is_current_version: false,
      approved_by: null,
      approved_at: null,
      source_revoked: true,
      revision: 1,
      sections: null,
    },
  ],
};

const AUTHORING = /create|upload|parse|map|review|publish|revision|edit|add/i;

describe("curricula, API mode (read-only)", () => {
  it("lists stored curricula with their real status, counts and no authoring controls", () => {
    render(<ReadOnlyCatalog catalog={TEST_CATALOG} companyName="Northstar" />);
    const card = screen.getByRole("article", { name: "Machine Fundamentals" });
    expect(within(card).getByText("Published")).toBeInTheDocument();
    expect(within(card).getByText("2 linked source versions")).toBeInTheDocument();
    expect(within(card).getByText("1 source version pending review")).toBeInTheDocument();
    expect(within(screen.getByRole("article", { name: "Old Path" })).getByText("Archived")).toBeInTheDocument();
    expect(screen.getByText("Curriculum authoring isn't connected")).toBeInTheDocument();
    // The only actions are navigation links to open a curriculum.
    expect(screen.queryAllByRole("button")).toHaveLength(0);
    expect(screen.getAllByRole("link").every((l) => l.textContent === "Open curriculum")).toBe(true);
  });

  it("shows an empty workspace honestly, without offering to create", () => {
    render(<ReadOnlyCatalog catalog={{ ...TEST_CATALOG, curricula: [] }} companyName="Northstar" />);
    expect(screen.getByText("No curricula in this workspace")).toBeInTheDocument();
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("renders the stored path, objectives, sources and recorded links, and nothing editable", () => {
    render(<CurriculumRecordView c={TEST_CURRICULUM} companyName="Northstar" />);
    expect(screen.getByText(/Database ID/)).toHaveTextContent("test-cur-1");
    expect(screen.getByText(/Demonstrate find the current procedure/)).toBeInTheDocument();
    expect(screen.getByText("No objective stored")).toBeInTheDocument();

    const approved = screen.getByRole("region", { name: /SOP-001 v3\.4 · Machine start-up/ });
    expect(within(approved).getByText("Approved by Morgan Lee on Sep 30, 2026", { exact: false })).toBeInTheDocument();
    const rows = within(screen.getByRole("region", { name: /SOP-001 v3\.4 sections/ })).getAllByRole("row");
    expect(rows[1]).toHaveTextContent("Machine Fundamentals › Find the current procedure");
    expect(rows[2]).toHaveTextContent("No link recorded"); // not guessed as reference-only

    const revoked = screen.getByRole("region", { name: /SOP-001 v4\.0-draft/ });
    expect(within(revoked).getByText("Source revoked")).toBeInTheDocument();
    expect(within(revoked).queryByRole("table")).toBeNull();

    expect(screen.queryAllByRole("button")).toHaveLength(0);
    expect(screen.queryAllByRole("textbox")).toHaveLength(0);
    const links = screen.getAllByRole("link").map((l) => l.textContent ?? "");
    expect(links.filter((t) => AUTHORING.test(t))).toEqual([]);
  });

  it("states when no source version is linked", () => {
    render(<CurriculumRecordView c={{ ...TEST_CURRICULUM, linked_sources: [] }} companyName="Northstar" />);
    expect(screen.getByText("No linked source versions")).toBeInTheDocument();
  });
});
