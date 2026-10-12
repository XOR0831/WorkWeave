import { expect, test, type Page } from "@playwright/test";

/** Database-backed demo entry: catalog → isolated workspace → personas → persona → home → refresh. */
async function openCompany(page: Page, company: string) {
  await page.goto("/demo/");
  await page.locator("article", { hasText: company }).getByRole("link", { name: /Open demo|Resume or restart/ }).click();
  await page.waitForURL("**/demo/company/**");
}
async function pickPersona(page: Page, name: string) {
  const resume = page.getByRole("button", { name: "Choose another persona" });
  await expect(page.getByRole("heading", { name: "Who do you want to be?" }).or(resume)).toBeVisible();
  if (await resume.isVisible()) await resume.click();
  const pick = page.getByRole("button", { name: new RegExp(`^${name}`) });
  const showAll = page.getByRole("button", { name: /^Show all \d+ personas$/ });
  if (!(await pick.isVisible()) && (await showAll.isVisible())) await showAll.click(); // only the main personas show first
  await pick.click();
  await page.waitForURL("**/home/");
  await expect(page.getByRole("heading", { level: 1, name: new RegExp(`, ${name.split(" ")[0]}\\.$`) })).toBeVisible();
}

test("catalog comes from GET /scenarios and states it's backend-backed", async ({ page }) => {
  await page.goto("/demo/");
  const titles = page.locator("article h2");
  await expect(titles).toHaveText(["Northstar Manufacturing", "Acme Infrastructure Operations", "Harbor Support"]);
  await expect(page.getByRole("note", { name: "Preview notice" })).toContainText("local WorkWeave backend");
  await expect(page.getByText("isolated copy on the local WorkWeave server")).toBeVisible();
});

test("persona choice and switch persist across reloads; cookies are HttpOnly", async ({ page, context }) => {
  await openCompany(page, "Northstar");
  await expect(page.getByText("Isolated server-side run")).toBeVisible();
  const names = page.locator(".persona-btn b");
  await expect(names).toHaveText(["Sam Kim", "Alex Rivera", "Jamie Chen", "Morgan Lee"]); // the pack's main personas
  const alex = page.locator(".persona-card", { hasText: "Alex Rivera" });
  await alex.getByRole("button").hover();
  await expect(alex.locator(".persona-show")).toBeVisible();
  await expect(alex.locator(".persona-show")).toContainText("Use Alex to test the lead's side.");
  await expect(alex.locator(".persona-show li", { hasText: "Exit KT" })).not.toContainText("coming soon");
  await expect(alex.locator(".persona-show li", { hasText: "Shift Handover" })).not.toContainText("coming soon");
  await expect(alex.locator(".persona-show li", { hasText: "Work Companion" })).not.toContainText("coming soon");
  await page.getByRole("button", { name: "Show all 6 personas" }).click();
  await expect(names).toHaveText(["Sam Kim", "Alex Rivera", "Jamie Chen", "Morgan Lee", "Priya Nair", "Dana Brooks"]);
  await pickPersona(page, "Alex Rivera");
  await page.reload();
  await expect(page.getByRole("heading", { level: 1, name: /, Alex\.$/ })).toBeVisible();
  await expect(page.locator(".context")).toContainText("Alex Rivera");

  await page.getByRole("button", { name: "Switch persona" }).click();
  await page.getByRole("dialog", { name: "Switch persona" }).getByRole("button", { name: /Morgan Lee/ }).click();
  await expect(page.locator(".context")).toContainText("Morgan Lee");
  await page.reload();
  await expect(page.locator(".context")).toContainText("Morgan Lee");

  expect(await page.evaluate(() => document.cookie)).toBe("");
  const cookies = await context.cookies();
  // One __session cookie (Firebase Hosting forwards only this name to Cloud Run).
  const session = cookies.filter((c) => c.name === "__session");
  expect(session).toHaveLength(1);
  expect(session.every((c) => c.httpOnly && c.sameSite === "Lax" && c.path === "/api")).toBe(true);
  expect(cookies.filter((c) => c.name.startsWith("ww_"))).toHaveLength(0);
});

test("module screens say they aren't connected instead of showing fixture data", async ({ page }) => {
  await openCompany(page, "Northstar");
  await pickPersona(page, "Sam Kim");
  // Learning, work and Exit KT are database-backed now: home shows no "not connected" card.
  await expect(page.getByText("Not connected yet")).toHaveCount(0);
  await expect(page.locator("section[aria-labelledby='h-work']")).toContainText("2 open"); // real data: Sam's two sample tickets (seed 17)
  await expect(page.locator("section[aria-labelledby='h-work']")).toContainText("Ticket #947");
  await expect(page.locator("section[aria-labelledby='h-learning']")).toContainText("0 of 3 required subtopics complete · 4 optional");
  // Every module screen is database-backed now. The inbox is wired to Firestore (ADR-048); this test server
  // runs without it (NOTIFICATIONS=none), so the inbox says so instead of showing an empty list.
  await page.goto("/inbox/");
  await expect(page.getByRole("alert").filter({ hasText: "Notifications aren't switched on for this server." }).first()).toBeVisible();
});

test("start fresh replaces only this company's run; another company's run is kept", async ({ page }) => {
  await openCompany(page, "Acme");
  await pickPersona(page, "John Tan");
  await openCompany(page, "Northstar");
  await pickPersona(page, "Jamie Chen");
  await openCompany(page, "Northstar");
  await expect(page.getByRole("heading", { name: "You have a run in progress" })).toBeVisible();
  await expect(page.getByText("Saved on the server")).toBeVisible();
  await page.getByRole("button", { name: "Start fresh demo" }).click();
  const dlg = page.getByRole("dialog", { name: "Start a fresh demo?" });
  await expect(dlg).toContainText("only your run for this company is replaced");
  await dlg.getByRole("button", { name: "Start fresh demo" }).click();
  await expect(page.getByText("Fresh run ready.")).toBeVisible();
  await pickPersona(page, "Sam Kim");
  // Acme still resumes with John.
  await openCompany(page, "Acme");
  await expect(page.getByText(/Last persona: John Tan/)).toBeVisible();
});

test("without a session cookie, module pages ask you to choose a company", async ({ page, context }) => {
  await openCompany(page, "Harbor");
  await pickPersona(page, "Nora Santos");
  await context.clearCookies();
  await page.goto("/home/");
  await expect(page.getByRole("heading", { name: "No demo workspace is open" })).toBeVisible();
});
