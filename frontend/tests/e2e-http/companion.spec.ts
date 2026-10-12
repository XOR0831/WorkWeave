import { expect, test, type Page } from "@playwright/test";

/** Work Companion backed by PostgreSQL: the pack's work story copied into each demo, as "today". */
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

test("the shift lead sees today's work from the database; the assistant says it isn't connected", async ({ page }) => {
  await as(page, "Northstar", "Alex Rivera");
  await page.goto("/companion/");
  const dash = page.locator(".dash-panel");
  await expect(dash.getByText(/Afternoon shift · ends in/)).toBeVisible();
  await expect(dash.locator(".metric").first()).toContainText("8"); // #829, #910 and the six sample tickets (seed 17)
  await expect(page.getByText(/Ticket #829 · Machine #14 inspection · Due in 1 h/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Open Ticket #910 details" })).toBeVisible(); // in the work list (sample tickets due sooner lead the priorities)
  await expect(page.getByText("Replies aren't available yet")).toBeVisible();
  await page.getByLabel("Message the Work Companion").fill("What should I focus on?");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByTestId("not-sent")).toContainText("Not sent");
  await expect(page.getByLabel("Message the Work Companion")).toHaveValue("What should I focus on?");
});

test("delegate, report and resolve: a report waits until the ticket system closes the ticket", async ({ page }) => {
  await page.goto("/demo/");
  await page.locator("article", { hasText: "Northstar" }).getByRole("link", { name: /Open demo|Resume or restart/ }).click();
  await page.waitForURL("**/demo/company/**");
  const fresh = page.getByRole("button", { name: "Start fresh demo" });
  if (await fresh.first().isVisible()) {
    await fresh.first().click();
    await page.getByRole("dialog").getByRole("button", { name: "Start fresh demo" }).click();
  }
  await page.getByRole("button", { name: /^Alex Rivera/ }).click();
  await page.waitForURL("**/home/");

  // The lead (on shift) confirms the seeded proposal; nothing was assigned before.
  await page.goto("/companion/");
  await page.getByRole("button", { name: "Review proposal" }).click();
  const drawer = page.getByRole("dialog", { name: "Delegation proposal" });
  await drawer.getByRole("button", { name: "Review and confirm" }).click();
  await page.getByRole("button", { name: "Confirm assignments", exact: true }).last().click();
  await expect(drawer.getByText("Assignments confirmed")).toBeVisible();
  await page.keyboard.press("Escape");

  // The member says "done" in the Companion: the ticket stays open, at lower priority.
  await as(page, "Northstar", "Jamie Chen");
  await page.goto("/companion/");
  await page.getByRole("button", { name: "Open Ticket #829 details" }).click();
  await page.getByRole("button", { name: "Report on this item" }).click();
  const report = page.getByRole("dialog", { name: "Report on Ticket #829" });
  await report.getByLabel(/I'm done/).check();
  await report.getByLabel("What happened").fill("Inspection finished; photos attached to the ticket.");
  await report.getByRole("button", { name: "Submit report" }).click();
  await expect(page.getByText("Reported done · waiting for the ticket system").first()).toBeVisible();
  await expect(page.getByText("Waiting for the ticket system", { exact: true })).toBeVisible();
  await expect(page.locator(".dash-panel .metric").first()).toContainText("3"); // still open (Jamie sees only her own: #829 and her two sample tickets)

  // Resolving it in the ticket system closes it and the report matches.
  await page.getByRole("link", { name: "Open Northstar Manufacturing ticket system" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Northstar Manufacturing ticket system" })).toBeVisible();
  await page.getByRole("button", { name: "Open Ticket #829" }).click();
  await page.getByLabel("Work note (optional)").fill("Resolved after inspection.");
  await page.getByRole("button", { name: "Resolve" }).click();
  await expect(page.getByText("Matches what Jamie Chen reported.")).toBeVisible();
  await page.getByRole("link", { name: "Back to Work Companion" }).click();
  await expect(page.getByRole("button", { name: "Open Ticket #829 details" })).toHaveCount(0); // closed, off the list
  await expect(page.locator(".dash-panel .metric").first()).toContainText("2"); // #829 closed; Jamie's two sample tickets remain
});

test("every company has its own ticket system", async ({ page }) => {
  await as(page, "Harbor", "Leo Cruz");
  await page.goto("/companion/tool/");
  await expect(page.getByRole("heading", { level: 1, name: /case system$/ })).toBeVisible();
  await expect(page.getByText("CASE-104")).toBeVisible();
});

test("knowledge notes stay private until submitted", async ({ page }) => {
  await as(page, "Northstar", "Sam Kim");
  await page.goto("/companion/");
  await page.getByRole("button", { name: "Capture knowledge" }).click();
  const d = page.getByRole("dialog", { name: "Capture reusable knowledge" });
  await d.getByLabel("I understand and want to start a private knowledge note.").check();
  await d.getByRole("button", { name: "Start note" }).click();
  await d.getByLabel("Explanation").fill("Check the mounting bolts before the vibration test.");
  await d.getByLabel("Who should see it after review").selectOption("TEAM");
  await d.getByRole("button", { name: "Save private draft" }).click();
  await expect(d.getByText("Check the mounting bolts before the vibration test.")).toBeVisible();
  await d.getByRole("button", { name: "Submit for review" }).click();
  await expect(d.getByText("Pending review")).toBeVisible();
});

test("a lead who isn't on shift doesn't get lead actions", async ({ page }) => {
  await as(page, "Northstar", "Dana Brooks");
  await page.goto("/companion/");
  await expect(page.locator(".dash-panel").getByText(/Next: Evening shift · starts in/)).toBeVisible();
  await expect(page.getByText(/Ticket #829 · Machine #14 inspection/)).toHaveCount(0); // not on shift: only her own tickets
  await expect(page.locator(".dash-panel .metric").first()).toContainText("Your tickets");
  await expect(page.getByRole("button", { name: "Review proposal" })).toHaveCount(0);
});
