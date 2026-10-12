import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { btn, startCompany } from "./helpers";

/** Coordinator flow (prototypes/onboarding README: "Try curriculum and document upload"). */
async function openDraft(page: Page) {
  await startCompany(page, "Northstar", "Morgan Lee");
  await page.getByRole("link", { name: "Curricula & sources" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Curricula & sources" })).toBeVisible();
  await page.locator("article", { hasText: "v1.1" }).getByRole("link", { name: "Open curriculum" }).click();
  await expect(page.getByRole("heading", { level: 1, name: /Machine Fundamentals/ })).toContainText("v1.1");
}

async function stageSampleAndParse(page: Page) {
  await btn(page, "Upload document").first().click();
  const dlg = page.getByRole("dialog", { name: "Upload a source document" });
  // The destination comes from the page, never from the file.
  await expect(dlg).toContainText("Destination curriculum · set by this page");
  await expect(dlg).toContainText("Machine Fundamentals v1.1");
  await dlg.getByRole("button", { name: /Use synthetic sample/ }).click();
  await expect(dlg.getByLabel("Document code")).toHaveValue("SOP-001");
  await dlg.getByRole("button", { name: "Stage document" }).click();
  await expect(dlg).toBeHidden();
  const tracker = page.getByRole("list", { name: /^Processing:/ });
  await expect(tracker).toHaveAttribute("aria-label", "Processing: Staged");
  await btn(page, "Generate outline").click();
  await expect(tracker).toHaveAttribute("aria-label", "Processing: Outline ready");
}

test.describe("Curricula & sources (coordinator)", () => {
  test("upload inside a draft, review the outline, approve the exact version, then publish separately", async ({ page }) => {
    await openDraft(page);
    await expect(page.getByText("No documents are linked yet")).toBeVisible();
    await stageSampleAndParse(page);

    // H2 topics and H3 sections; H4 headings stay as content.
    await expect(page.getByText("1. Fundamentals")).toBeVisible();
    await expect(page.getByText("2. Reference aids")).toBeVisible();
    await expect(page.getByText("4 H4 headings kept as content").first()).toBeVisible();
    await expect(page.getByLabel(/Learning subtopic for .A\. Source-selection checklist/)).toHaveValue("ref");

    const gate = page.locator("section[aria-labelledby='h-ready']");
    await expect(gate.getByRole("button", { name: "Publish curriculum" })).toBeDisabled();
    await expect(gate).toContainText("SOP-001 v3.4: mappings not confirmed");

    await btn(page, "Confirm mappings").click();
    await btn(page, "Submit for review").click();
    await expect(page.getByRole("list", { name: /^Processing:/ })).toHaveAttribute("aria-label", "Processing: In review");
    await expect(page.getByLabel(/Learning subtopic for .1\. Find the current procedure/)).toBeDisabled();

    await btn(page, "Approve source version").click();
    const review = page.getByRole("dialog", { name: "Approve this source version?" });
    await expect(review).toContainText("SOP-001 v3.4");
    await review.getByRole("button", { name: "Approve source version" }).click();
    await expect(page.getByText("Source version approved · curriculum publication is separate")).toBeVisible();

    // Approval didn't publish anything; the gate is now satisfied and publishing is its own decision.
    await expect(page.getByRole("heading", { level: 1 })).not.toContainText("Published");
    await expect(gate.getByRole("heading", { name: "Ready to publish" })).toBeVisible();
    await gate.getByRole("button", { name: "Publish curriculum" }).click();
    await page.getByRole("dialog", { name: "Publish this curriculum?" }).getByRole("button", { name: /^Publish Machine Fundamentals/ }).click();
    await expect(btn(page, "Create draft revision")).toBeVisible();
    await expect(btn(page, "Upload document")).toHaveCount(0);

    await page.getByRole("link", { name: "Curricula & sources" }).first().click();
    const outcomes = page.locator("section[aria-labelledby='h-outcomes']");
    await expect(outcomes).toContainText("SOP-001 v3.4");
    await expect(outcomes).toContainText("Source approved");
  });

  test("unresolved mappings can be confirmed; rejection removes the source and keeps only a note", async ({ page }) => {
    await openDraft(page);
    await stageSampleAndParse(page);
    const sel = page.getByLabel(/Learning subtopic for .3\. Ask a clearer question/);
    await sel.selectOption("unresolved");
    await expect(page.getByText("Unsaved changes")).toBeVisible();
    await btn(page, "Discard changes").click();
    await expect(page.getByText("Unsaved changes")).toHaveCount(0);
    await sel.selectOption("unresolved");
    await btn(page, "Confirm mappings").click();
    await expect(page.locator(".mapping-foot")).toContainText("1 unresolved");
    await expect(page.locator(".mapping-foot")).toContainText("Confirmed by coordinator");

    await btn(page, "Submit for review").click();
    await btn(page, "Reject source version").click();
    const dlg = page.getByRole("dialog", { name: "Reject this source version?" });
    await expect(dlg.getByRole("button", { name: "Reject and remove" })).toBeDisabled();
    await dlg.getByLabel("Reason for the coordinator").fill("Map Ask a clearer question before resubmitting.");
    await dlg.getByRole("button", { name: "Reject and remove" }).click();
    await expect(page.getByText("No documents are linked yet")).toBeVisible();
    await expect(page.locator("section[aria-labelledby='h-ready']")).toContainText("Submit a source version and have it approved.");
  });

  test("a selected file is only a filename: staging works, parsing honestly isn't available", async ({ page }) => {
    await openDraft(page);
    await btn(page, "Upload document").first().click();
    const dlg = page.getByRole("dialog", { name: "Upload a source document" });
    await dlg.getByLabel("Document code").fill("SOP-002");
    await dlg.getByLabel("Document title").fill("Fictional test notes");
    await dlg.getByLabel("Exact document version").fill("1.0");
    await dlg.getByLabel("Source file (Markdown or plain text)").setInputFiles({ name: "fictional-notes.md", mimeType: "text/markdown", buffer: Buffer.from("## A\n### B\n") });
    await expect(dlg).toContainText("Selected file: fictional-notes.md");
    await expect(dlg).toContainText("Not uploaded, not processed.");
    await dlg.getByRole("button", { name: "Stage document" }).click();
    await expect(page.getByText("Selected file: fictional-notes.md")).toBeVisible();
    await expect(page.getByText("The file wasn't uploaded or read")).toBeVisible();
    await btn(page, "Try to parse").click();
    await expect(page.getByRole("alert").filter({ hasText: "Document parsing isn't connected" })).toBeVisible();
    await expect(page.getByRole("list", { name: /^Processing:/ })).toHaveAttribute("aria-label", "Processing: Staged");
  });

  test("published curricula are frozen; a draft revision is the way to change them", async ({ page }) => {
    await startCompany(page, "Northstar", "Morgan Lee");
    await page.goto("/curricula/");
    await page.locator("article", { hasText: "v1.0" }).getByRole("link", { name: "Open curriculum" }).click();
    await expect(page.locator(".provenance")).toContainText("Seeded approved version");
    await expect(btn(page, "Upload document")).toHaveCount(0);
    await btn(page, "Create draft revision").click();
    await page.waitForURL("**/curricula/detail/**");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("v1.1");
    await expect(btn(page, "Upload document").first()).toBeVisible();
  });

  test("a new curriculum starts empty and explains what it needs", async ({ page }) => {
    await startCompany(page, "Northstar", "Morgan Lee");
    await page.goto("/curricula/");
    await btn(page, "Create curriculum").click();
    const dlg = page.getByRole("dialog", { name: "Create a draft curriculum" });
    await dlg.getByLabel("Curriculum name").fill("Evidence reporting refresher");
    await dlg.getByRole("button", { name: "Create draft curriculum" }).click();
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Evidence reporting refresher");
    await expect(page.getByText("No learning path yet.")).toBeVisible();
    await btn(page, "Add topics").click();
    const path = page.getByRole("dialog", { name: "Add topics" });
    await path.getByRole("button", { name: "Add topic", exact: true }).click();
    await path.getByLabel("Topic 1 name").fill("Reporting");
    await path.getByLabel("Subtopic 1.1 name").fill("Label evidence");
    await path.getByRole("button", { name: "Save learning path" }).click();
    const gate = page.locator("section[aria-labelledby='h-ready']");
    await expect(gate).toContainText("Missing: Label evidence");
    await expect(gate).toContainText("No approved coverage: Label evidence");
  });

  test("other personas see who can open the coordinator workspace", async ({ page }) => {
    await startCompany(page, "Northstar");
    await page.getByRole("link", { name: "Curricula & sources" }).click();
    await expect(page.getByText("This isn't available to your persona")).toBeVisible();
    await expect(page.getByText(/Morgan Lee/).first()).toBeVisible();
  });

  test("axe: outline and mapping review has no serious violations", async ({ page }) => {
    await openDraft(page);
    await stageSampleAndParse(page);
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
    const bad = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
    expect(bad.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).slice(0, 3).join(", ")}`)).toEqual([]);
  });
});
