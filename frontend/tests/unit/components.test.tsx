import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Evidence, Status } from "@/components/ui";
import { transferBlockers, missingRequiredSections } from "@/lib/domain/rules";
import { PACKS } from "@/fixtures";

describe("status vocabulary", () => {
  it("evidence tags always carry a text label, not colour alone", () => {
    render(<Evidence type="REPORTED" />);
    expect(screen.getByText("Reported")).toHaveClass("evidence-reported");
  });
  it("status badge humanizes enum values", () => {
    render(<Status value="PENDING_REVIEW" />);
    expect(screen.getByText("Pending review")).toBeInTheDocument();
  });
});

describe("display rules", () => {
  it("explains every transfer blocker from the seeded state", () => {
    const c = PACKS.northstar.exit_kt.case;
    expect(transferBlockers(c, "ns-rt-138")).toEqual(["No approved successor package", "Effective time hasn't been reached or reviewed"]);
    expect(transferBlockers(c, "ns-rt-139")).toContain("No successor selected");
  });
  it("required sections need content or a declared reason", () => {
    const h = PACKS.acme.handover;
    expect(missingRequiredSections({ sections: h.sections, draft_sections: h.draft_sections })).toEqual([]);
    const empty = h.draft_sections.map((d) => (d.section_id === "sec-summary" ? { ...d, content: "" } : d));
    expect(missingRequiredSections({ sections: h.sections, draft_sections: empty })).toEqual(["Shift Summary"]);
    const declared = empty.map((d) => (d.section_id === "sec-summary" ? { ...d, declaration: "NOT_APPLICABLE" as const, declaration_reason: "No activity" } : d));
    expect(missingRequiredSections({ sections: h.sections, draft_sections: declared })).toEqual([]);
  });
});
