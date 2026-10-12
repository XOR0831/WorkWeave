import { expect, test, type Page } from "@playwright/test";

/** Exit KT backed by PostgreSQL: the employee submits an exact revision, the reviewer approves and promotes it. */
async function as(page: Page, persona: string, fresh = false) {
  await page.goto("/demo/");
  await page.locator("article", { hasText: "Northstar" }).getByRole("link", { name: /Open demo|Resume or restart/ }).click();
  await page.waitForURL("**/demo/company/**");
  const restart = page.getByRole("button", { name: "Start fresh demo" });
  if (fresh && (await restart.isVisible())) {
    await restart.click();
    const confirm = page.getByRole("dialog").getByRole("button", { name: "Start fresh demo" });
    if (await confirm.isVisible()) await confirm.click();
  }
  const resume = page.getByRole("button", { name: "Choose another persona" });
  await expect(page.getByRole("heading", { name: "Who do you want to be?" }).or(resume)).toBeVisible();
  if (await resume.isVisible()) await resume.click();
  await page.getByRole("button", { name: new RegExp(`^${persona}`) }).click();
  await page.waitForURL("**/home/");
  await page.goto("/exit-kt/");
}

test("knowledge moves from a private draft to a promoted document version", async ({ page }) => {
  await as(page, "Alex Rivera", true);
  await expect(page.getByRole("heading", { name: "A role changes. Knowledge stays." })).toBeVisible();
  await page.getByRole("button", { name: "Run discovery" }).click();
  await expect(page.getByText(/knowledge-transfer assistant isn't connected right now/).first()).toBeVisible(); // EXIT_KT_ENGINE=none here
  await expect(page.getByRole("button", { name: "New case" })).toHaveCount(0); // the employee doesn't open cases

  await page.getByRole("button", { name: "Open artifact" }).click();
  const drawer = page.getByRole("dialog", { name: "Requesting evidence-based clarification" });
  await drawer.getByRole("button", { name: "Submit v1 for review" }).click();
  await expect(drawer.getByText("Pending review").first()).toBeVisible();

  await as(page, "Morgan Lee");
  await expect(page.getByRole("button", { name: "New case" })).toBeVisible(); // the manager does (docs/32)
  await page.getByRole("button", { name: "Open artifact" }).click();
  const review = page.getByRole("dialog", { name: "Requesting evidence-based clarification" });
  await review.getByRole("button", { name: "Approve v1" }).click();
  await review.getByRole("button", { name: "Promote v1 to a new document version" }).click();
  await expect(review.getByText("KT-001 v1")).toBeVisible();
});

test("the successor sees the package side only", async ({ page }) => {
  await as(page, "Jamie Chen");
  await expect(page.getByRole("tab", { name: "AI Findings" })).toHaveCount(0);
  await expect(page.getByText("Not yet received").or(page.getByText(/no approved package/i)).first()).toBeVisible();
});
