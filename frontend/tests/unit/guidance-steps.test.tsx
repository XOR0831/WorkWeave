import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { summarizeSteps } from "@/lib/text/steps";
import { RichText } from "@/lib/text/RichText";

// The reply shape from the owner's test (her guidance step, 2026-10-10): bullets inline after a lead sentence.
const INLINE =
  "To write the evidence note for Machine #22, use the work-evidence note template from SOP-001 by filling in the following fields: " +
  "* **Work item / asset:** Enter the exact identifier for Machine #22. * **Recorder / recorded at:** Enter your name and the system timestamp. " +
  "* **Observation time:** Record the time the findings were observed, or enter \"not known\" if the exact time is not available.";

describe("guidance step summary", () => {
  it("keeps the reply's own steps, shortened to their lead and first sentence", () => {
    expect(summarizeSteps(INLINE)).toEqual([
      { label: "Work item / asset", detail: "Enter the exact identifier for Machine #22." },
      { label: "Recorder / recorded at", detail: "Enter your name and the system timestamp." },
      { label: "Observation time", detail: 'Record the time the findings were observed, or enter "not known" if the exact time is not available.' },
    ]);
  });

  it("reads numbered lists without bold leads, and gives nothing for a reply without steps", () => {
    expect(summarizeSteps("Do this:\n1. Open the registry. Then check the version.\n2. Record the code.")).toEqual([
      { label: "Open the registry.", detail: "" },
      { label: "Record the code.", detail: "" },
    ]);
    expect(summarizeSteps("The approved knowledge doesn't say.")).toEqual([]);
  });
});

describe("rich text tables", () => {
  it("renders a pipe table as a table, skipping the rule line", () => {
    render(<RichText text={"| Field | Entry guidance |\n| --- | --- |\n| **Claim** | Concise statement |\n| Source | Ticket event |"} />);
    expect(screen.getByRole("columnheader", { name: "Field" })).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(3);
    expect(screen.getByRole("cell", { name: "Claim" }).querySelector("strong")).not.toBeNull();
    expect(screen.queryByText(/---/)).toBeNull();
  });
});
