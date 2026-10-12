import { expect, test, type Page } from "@playwright/test";

/** Curricula screens backed by PostgreSQL (disposable workweave_test database); authoring per ADR-040. */
async function as(page: Page, company: string, persona: string) {
  await page.goto("/demo/");
  await page.locator("article", { hasText: company }).getByRole("link", { name: /Open demo|Resume or restart/ }).click();
  await page.waitForURL("**/demo/company/**");
  const resume = page.getByRole("button", { name: "Choose another persona" });
  await expect(page.getByRole("heading", { name: "Who do you want to be?" }).or(resume)).toBeVisible();
  if (await resume.isVisible()) await resume.click();
  const pick = page.getByRole("button", { name: new RegExp(`^${persona}`) });
  const showAll = page.getByRole("button", { name: /^Show all \d+ personas$/ });
  if (!(await pick.isVisible()) && (await showAll.isVisible())) await showAll.click(); // only the main personas show first
  await pick.click();
  await page.waitForURL("**/home/");
}

const AUTHORING = /Create curriculum|Upload document|Add another source|Publish curriculum|Create draft revision|Edit path|Add objective|Approve|Reject/;

test("the manager reads the stored curriculum and its detail; a published curriculum is frozen", async ({ page }) => {
  await as(page, "Northstar", "Morgan Lee");
  const nav = page.getByRole("navigation", { name: "Modules" });
  await nav.getByRole("link", { name: "Curricula & sources" }).click();
  await page.waitForURL("**/curricula/");
  // 1.1 is the SOP-001 v3.4 path; 1.0 is archived.
  await expect(page.getByRole("article", { name: "Machine Fundamentals" }).filter({ hasText: "v1.0" })).toContainText("Archived");
  const card = page.getByRole("article", { name: "Machine Fundamentals" }).filter({ hasText: "v1.1" });
  await expect(card).toContainText("Published");
  await expect(card).toContainText("2 topics");
  await expect(card).toContainText("7 subtopics");
  await expect(card).toContainText("1 linked source version");
  await expect(page.getByRole("button", { name: "Create curriculum" })).toBeVisible(); // Morgan holds curriculum:manage

  await card.getByRole("link", { name: "Open curriculum" }).click();
  await page.waitForURL("**/curricula/detail/**");
  await expect(page.getByRole("heading", { level: 1, name: /Machine Fundamentals/ })).toBeVisible();
  await expect(page.getByText(/Database ID/)).toBeVisible();
  await expect(page.getByText(/Identify the approved, current controlled instruction/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "SOP-001 v3.4 · Calibration and evidence handling" })).toBeVisible();
  await expect(page.getByRole("region", { name: /SOP-001 v3\.4 sections/ }).getByRole("row")).toHaveCount(8); // header + 7 sections
  await expect(page.getByText("Reference aids › Training checks")).toBeVisible();
  await expect(page.getByText(/published, so it's frozen/)).toBeVisible();
  // Frozen: nothing edits it in place; the only way to change it is a draft revision (ADR-050).
  await expect(page.getByRole("button", { name: AUTHORING })).toHaveText(["Create draft revision"]);
  await expect(page.getByText(/Preview ID|browser tab/)).toHaveCount(0); // no preview copy in API mode
});

test("an unknown curriculum ID shows not-found, distinct from forbidden", async ({ page }) => {
  await as(page, "Northstar", "Morgan Lee");
  await page.goto("/curricula/detail/?id=00000000-0000-4000-8000-000000000000");
  await expect(page.getByText("This curriculum doesn't exist in this workspace.")).toBeVisible();
  await expect(page.getByText("This isn't available to your persona")).toHaveCount(0);
});

test("a learner gets no Coordinator nav and is forbidden from the curricula list and detail", async ({ page }) => {
  await as(page, "Northstar", "Jamie Chen");
  await expect(page.getByRole("navigation", { name: "Modules" }).getByRole("link", { name: "Curricula & sources" })).toHaveCount(0);
  await page.goto("/curricula/");
  await expect(page.getByRole("heading", { name: "This isn't available to your persona" })).toBeVisible();
  await expect(page.getByText("Machine Fundamentals")).toHaveCount(0);
  await page.goto("/curricula/detail/?id=00000000-0000-4000-8000-000000000000");
  await expect(page.getByRole("heading", { name: "This isn't available to your persona" })).toBeVisible();
});

test("the manager creates a draft, uploads a numbered Markdown source and approves that exact version", async ({ page }) => {
  await as(page, "Northstar", "Morgan Lee");
  await page.goto("/curricula/");
  await page.getByRole("button", { name: "Create curriculum" }).click();
  const dlg = page.getByRole("dialog", { name: "Create a draft curriculum" });
  await dlg.getByLabel("Curriculum name").fill("Packaging Line Basics");
  await dlg.getByLabel("Version").fill(`e2e-${Date.now()}`);
  await dlg.getByRole("button", { name: "Create draft curriculum" }).click();
  await page.waitForURL("**/curricula/detail/**");
  await expect(page.getByRole("heading", { name: "Prepare and publish" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Publish curriculum" })).toBeDisabled();

  await page.getByLabel("Document code").fill(`PKG-${Date.now() % 100000}`);
  await page.getByLabel("Title", { exact: true }).fill("Packaging line basics");
  await page.getByLabel("Markdown file").setInputFiles({
    name: "packaging.md",
    mimeType: "text/markdown",
    buffer: Buffer.from("# Packaging\n\n## 1. Line start-up\n\n### 1. Pre-start checks\nCheck the guards.\n"),
  });
  await page.getByRole("button", { name: "Upload for review" }).click();
  await expect(page.getByText(/I reviewed this exact version/)).toBeVisible();
  const approve = page.getByRole("button", { name: "Approve v1.0" });
  await expect(approve).toBeDisabled(); // only after confirming the review
  await page.getByLabel(/I reviewed this exact version/).check();
  await approve.click();
  // The e2e server has no ingestion configured: approval is recorded and the page says so honestly.
  await expect(page.getByText(/Ingestion isn't connected on this server/)).toBeVisible();
});
