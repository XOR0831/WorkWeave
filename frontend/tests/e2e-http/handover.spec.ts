import { expect, test, type Page } from "@playwright/test";

/** Shift Handover backed by PostgreSQL: the lead's draft for the next shift, members' published view. */
async function as(page: Page, company: string, persona: string) {
  await page.goto("/demo/");
  await page.locator("article", { hasText: company }).getByRole("link", { name: /Open demo|Resume or restart/ }).click();
  await page.waitForURL("**/demo/company/**");
  const resume = page.getByRole("button", { name: "Choose another persona" });
  await expect(page.getByRole("heading", { name: "Who do you want to be?" }).or(resume)).toBeVisible();
  if (await resume.isVisible()) await resume.click();
  const pick = page.getByRole("button", { name: new RegExp(`^${persona}`) });
  const showAll = page.getByRole("button", { name: /^Show all \d+ personas$/ });
  if (!(await pick.isVisible()) && (await showAll.isVisible())) await showAll.click();
  await pick.click();
  await page.waitForURL("**/home/");
}

test("the shift lead edits and publishes the handover to the next shift", async ({ page }) => {
  await as(page, "Northstar", "Alex Rivera");
  await page.goto("/handover/");
  await expect(page.getByRole("heading", { name: "Afternoon → Evening handover" })).toBeVisible();
  await expect(page.getByText("Companion not connected")).toBeVisible();
  await expect(page.getByText(/updates? needs? your attention/)).toBeVisible(); // the stored suggestions

  await page.getByRole("button", { name: "Edit Shift Summary" }).click();
  await page.getByRole("textbox", { name: "Shift Summary" }).fill("Machine #14 inspection continues on the Evening shift.");
  await page.getByRole("button", { name: "Save section" }).click();
  await expect(page.getByText("Machine #14 inspection continues on the Evening shift.")).toBeVisible();

  await page.getByRole("button", { name: "Review and publish" }).click();
  const review = page.getByRole("dialog", { name: "Review and publish" });
  await review.getByLabel(/reviewed the sections, items and evidence/).check();
  await review.getByRole("button", { name: "Publish handover" }).click();
  await expect(page.getByText(/Published #1/)).toBeVisible();
});

test("members don't see Shift Handover; the receiving lead reads the incoming handover and confirms receipt", async ({ page }) => {
  await as(page, "Northstar", "Jamie Chen");
  await expect(page.getByRole("navigation", { name: "Modules" }).getByRole("link", { name: "Shift Handover" })).toHaveCount(0);
  await page.goto("/handover/");
  await expect(page.getByRole("heading", { name: "Shift Handover is for shift leads" })).toBeVisible();
  await as(page, "Northstar", "Alex Rivera"); // leads the Afternoon shift that received #1 from Morning
  await page.goto("/handover/");
  await expect(page.getByRole("heading", { name: /Incoming handover #1 from Morning/ })).toBeVisible();
  await page.getByRole("button", { name: "Confirm receipt of #1" }).click();
  await expect(page.getByText("Receipt confirmed")).toBeVisible();
});

test("Demo tools move the run to the next shift after a warning about the unpublished handover", async ({ page }) => {
  await as(page, "Harbor", "Leo Cruz");
  await page.getByRole("button", { name: "Demo tools ↗" }).click();
  const tools = page.getByRole("dialog", { name: "Demo tools" });
  await expect(tools).toContainText("In progress");
  const advance = tools.getByRole("button", { name: /^Advance to / });
  await expect(advance).toBeDisabled(); // the handover in progress isn't published
  await tools.getByLabel("Move on anyway").check();
  await advance.click();
  await expect(tools.getByText(/Moved ahead/)).toBeVisible();
  await page.getByRole("button", { name: "Close Demo tools" }).click();
  await page.goto("/handover/");
  await expect(page.getByRole("heading", { name: /Evening → / })).toBeVisible();
});
