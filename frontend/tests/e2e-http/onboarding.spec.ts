import { expect, test, type Page } from "@playwright/test";

/** Onboarding read paths backed by PostgreSQL: overview, resume position, supervisor progress. */
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

test("a new learner sees the assigned path from the database; the tutor says it isn't connected", async ({ page }) => {
  await as(page, "Northstar", "Sam Kim");
  await page.goto("/onboarding/");
  await expect(page.getByRole("heading", { level: 1, name: "Machine Fundamentals" })).toBeVisible();
  await expect(page.getByText("0 of 3 required subtopics complete · 4 optional.")).toBeVisible();
  const path = page.getByRole("list", { name: "Subtopics" });
  await expect(path.locator("li")).toHaveCount(7); // SOP-001 v3.4: 3 Fundamentals + 4 optional Reference aids
  await expect(path.locator("li").first()).toContainText("Find the current procedure");
  await expect(page.getByText("The tutor isn't connected yet")).toBeVisible();
  await expect(page.getByRole("button", { name: "Start conversation" })).toBeVisible();
  await expect(page.getByText("Sources: SOP-001 v3.4 (current)")).toBeVisible();
});

test("a returning learner's saved progress and next step survive a reload", async ({ page }) => {
  await as(page, "Northstar", "Jamie Chen");
  await page.goto("/onboarding/");
  await expect(page.getByText("1 of 3 required subtopics complete · 4 optional.")).toBeVisible();
  await expect(page.getByText(/In progress: Separate history from evidence/)).toBeVisible();
  await page.reload();
  await expect(page.getByText(/In progress: Separate history from evidence/)).toBeVisible();
});

test("a supervisor sees team progress by subtopic; other personas are denied", async ({ page }) => {
  await as(page, "Northstar", "Morgan Lee");
  await page.goto("/onboarding/");
  await page.getByRole("link", { name: "View team progress" }).click();
  const table = page.getByRole("table");
  await expect(table.getByRole("row", { name: /Jamie Chen/ })).toContainText("Completed");
  await expect(table.getByRole("row", { name: /Jamie Chen/ })).toContainText("In progress");
  await expect(table.getByRole("row", { name: /Sam Kim/ })).toBeVisible();

  await as(page, "Northstar", "Alex Rivera");
  await page.goto("/onboarding/progress/");
  await expect(page.getByText("This isn't available to your persona")).toBeVisible();
});

test("tutor shell: the session, place and break are saved; replies are honestly unavailable", async ({ page }) => {
  await as(page, "Northstar", "Jamie Chen");
  await page.goto("/onboarding/");
  await page.getByRole("button", { name: /Start conversation|Resume conversation/ }).click();
  await page.waitForURL("**/onboarding/session/");
  const chat = page.locator("section[aria-labelledby='h-tutor']");
  await expect(chat).toContainText("Tutor not connected");
  await expect(chat.getByText("Replies aren't available yet")).toBeVisible();
  await expect(chat).toContainText("Sessions, position and breaks are saved");
  await expect(page.getByRole("log", { name: "Tutor conversation" }).locator(".msg")).toHaveCount(0); // nothing invented
  await expect(page.getByRole("list", { name: "Subtopics" }).locator("li", { hasText: "Current position" })).toContainText("Separate history from evidence");

  const box = page.getByLabel("Ask, answer, or tell me what you need");
  await box.fill("Which SOP version is current?");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Your message wasn't sent" })).toBeVisible();
  await expect(box).toHaveValue("Which SOP version is current?");

  await page.getByRole("button", { name: "Take a break" }).click();
  await expect(page.getByText("The conversation is paused and your progress is saved.")).toBeVisible();
  await page.reload();
  await expect(page.getByText("The conversation is paused and your progress is saved.")).toBeVisible();
  await page.getByRole("button", { name: "Resume conversation" }).click();
  await expect(page.getByLabel("Ask, answer, or tell me what you need")).toBeVisible();
  await expect(page.getByRole("list", { name: "Subtopics" }).locator("li", { hasText: "Current position" })).toContainText("Separate history from evidence");
});
