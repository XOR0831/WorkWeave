import { expect, test, type Page } from "@playwright/test";

/** Reviews and Knowledge backed by PostgreSQL (ADR-040, ADR-041). */
async function as(page: Page, persona: string) {
  await page.goto("/demo/");
  await page.locator("article", { hasText: "Northstar" }).getByRole("link", { name: /Open demo|Resume or restart/ }).click();
  await page.waitForURL("**/demo/company/**");
  const resume = page.getByRole("button", { name: "Choose another persona" });
  await expect(page.getByRole("heading", { name: "Who do you want to be?" }).or(resume)).toBeVisible();
  if (await resume.isVisible()) await resume.click();
  await page.getByRole("button", { name: new RegExp(`^${persona}`) }).click();
  await page.waitForURL("**/home/");
}

test("a submitted knowledge note waits for the reviewer, who approves it", async ({ page }) => {
  await as(page, "Jamie Chen");
  const key = () => `${Date.now()}-${Math.random()}`;
  const headers = { "X-WorkWeave-Client": "web" };
  const note = await page.request.post("/api/memory-drafts", { headers, data: { idempotency_key: key(), content: "Guard bolts on #14 take 12 Nm.", requested_audience: "TEAM" } });
  const d = (await note.json()).data;
  expect((await page.request.post(`/api/memory-drafts/${d.draft_id}/review`, { headers, data: { idempotency_key: key(), expected_revision: d.revision } })).ok()).toBe(true);

  await as(page, "Morgan Lee");
  await page.goto("/reviews/");
  const item = page.locator(".list-item", { hasText: "Guard bolts on #14 take 12 Nm." });
  await expect(item).toContainText("Submitted by Jamie Chen");
  await item.getByRole("button", { name: "Approve note" }).click();
  await expect(item).toHaveCount(0);
});

test("Knowledge lists approved versions with their history and opens the real text", async ({ page }) => {
  await as(page, "Sam Kim");
  await page.goto("/memory/");
  await expect(page.getByText("SOP-001 v3.4 approved")).toBeVisible();
  await page.getByRole("radio", { name: "Historical" }).check();
  await expect(page.getByText("SOP-001 v3.3 approved")).toBeVisible();
  await page.locator(".list-item", { hasText: "SOP-001 v3.3 approved" }).getByRole("button", { name: "View source" }).click();
  await expect(page.getByRole("dialog")).toContainText("SOP-001 v3.3");
});
