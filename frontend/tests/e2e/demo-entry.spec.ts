import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { asPersona, btn, chip, pickPersona, reviewTool, startCompany } from "./helpers";

test.describe("Public demo entry (ADR-024)", () => {
  test("catalog → fixed company route → initialization → required first persona choice", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("link", { name: "Explore the synthetic demo" }).click();
    await page.waitForURL("**/demo/");
    await expect(page.locator("article")).toHaveCount(3);
    await page.locator("article", { hasText: "Northstar" }).getByRole("link", { name: "Open demo" }).click();
    await expect(page).toHaveURL(/\/demo\/company\/\?company_key=northstar&scenario=northstar-machine14$/);
    await expect(page.getByText("Browser-local preview run")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Who do you want to be?" })).toBeVisible();
    for (const n of ["Sam Kim", "Alex Rivera", "Jamie Chen", "Morgan Lee", "Priya Nair", "Dana Brooks"]) await expect(page.locator(".persona-btn b", { hasText: new RegExp(`^${n}$`) })).toBeVisible();

    // Module deep link before choosing a persona sends the visitor back to the picker.
    await page.goto("/companion/");
    await expect(page.getByText("Choose who you want to be first")).toBeVisible();
    await page.getByRole("link", { name: "Choose a persona" }).click();
    await pickPersona(page, "Jamie Chen");
    await expect(page.locator(".context")).toContainText("Jamie Chen");
  });

  test("refresh and deep links recover the run; persona switching stays available", async ({ page }) => {
    await startCompany(page, "Acme", "John Tan");
    await page.reload();
    await expect(page.getByRole("heading", { level: 1, name: /, John\./ })).toBeVisible();
    await page.goto("/demo/company/?company_key=acme&scenario=acme-platform-ops");
    await expect(page.getByRole("heading", { name: "You have a run in progress" })).toBeVisible();
    await page.reload();
    await btn(page, "Resume as John").click();
    await page.waitForURL("**/home/");
    await asPersona(page, "Maria Garcia");
    await page.reload();
    await expect(page.locator(".context")).toContainText("Maria Garcia");
    await page.getByRole("link", { name: "Change company" }).click();
    await expect(page.locator("article", { hasText: "Acme" })).toContainText("Run in progress");
    await expect(page.locator("article", { hasText: "Harbor" })).not.toContainText("Run in progress");
  });

  test("unknown or mismatched keys show a clear state, not a crash", async ({ page }) => {
    await page.goto("/demo/company/?company_key=nope&scenario=x");
    await expect(page.getByText("This company isn't in the demo catalog")).toBeVisible();
    await page.goto("/demo/company/?company_key=acme&scenario=northstar-machine14");
    await expect(page.getByText("This company isn't in the demo catalog")).toBeVisible();
    await page.goto("/demo/company/");
    await expect(page.getByText("This company isn't in the demo catalog")).toBeVisible();
  });

  test("Start fresh: cancel keeps the run; Escape returns focus", async ({ page }) => {
    await startCompany(page, "Acme");
    await page.goto("/companion/");
    await chip(page, "Recommend assignments");
    await btn(page, "Review and confirm").click();
    await btn(page, "Confirm assignments").click();
    await expect(page.getByText("Assignments confirmed")).toBeVisible();
    await page.goto("/demo/company/?company_key=acme&scenario=acme-platform-ops");
    const trigger = btn(page, "Start fresh demo");
    await trigger.click();
    const dlg = page.getByRole("dialog", { name: "Start a fresh demo?" });
    await expect(dlg).toContainText("your Acme Infrastructure Operations run in this browser tab");
    await expect(dlg).toContainText("Runs for other companies in this tab are kept");
    await page.keyboard.press("Escape");
    await expect(dlg).toBeHidden();
    await expect(trigger).toBeFocused();
    await trigger.click();
    await dlg.getByRole("button", { name: "Keep my current run" }).click();
    await btn(page, "Resume as Alex").click();
    await page.goto("/companion/");
    await chip(page, "Recommend assignments");
    await expect(page.getByText("Assignments confirmed")).toBeVisible();
  });

  test("Start fresh: confirmed discard affects only the selected company", async ({ page }) => {
    await startCompany(page, "Northstar");
    await startCompany(page, "Acme");
    await page.goto("/companion/");
    await chip(page, "Recommend assignments");
    await btn(page, "Review and confirm").click();
    await btn(page, "Confirm assignments").click();
    await page.goto("/demo/company/?company_key=acme&scenario=acme-platform-ops");
    await btn(page, "Start fresh demo").click();
    await page.getByRole("dialog", { name: "Start a fresh demo?" }).getByRole("button", { name: "Start fresh demo" }).click();
    await expect(page.getByText("Fresh run ready.")).toBeVisible();
    await pickPersona(page, "Alex Chen");
    await page.goto("/companion/");
    await chip(page, "Recommend assignments");
    await expect(btn(page, "Review and confirm")).toBeVisible();
    await page.goto("/demo/");
    await expect(page.locator("article", { hasText: "Northstar" })).toContainText("Run in progress");
  });

  test("failed fresh start leaves the existing run usable", async ({ page }) => {
    await startCompany(page, "Acme");
    await page.goto("/companion/");
    await chip(page, "Recommend assignments");
    await btn(page, "Review and confirm").click();
    await btn(page, "Confirm assignments").click();
    // Client-side navigation keeps the reviewer-selected failure mode.
    await reviewTool(page, /Next save fails/);
    await page.getByRole("link", { name: "Change company" }).click();
    await page.locator("article", { hasText: "Acme" }).getByRole("link", { name: "Resume or restart" }).click();
    await btn(page, "Start fresh demo").click();
    const dlg = page.getByRole("dialog", { name: "Start a fresh demo?" });
    await dlg.getByRole("button", { name: "Start fresh demo" }).click();
    await expect(dlg.getByRole("alert").filter({ hasText: "Your current run is unchanged" })).toBeVisible();
    await dlg.getByRole("button", { name: "Keep my current run" }).click();
    await btn(page, "Resume as Alex").click();
    await page.goto("/companion/");
    await chip(page, "Recommend assignments");
    await expect(page.getByText("Assignments confirmed")).toBeVisible();
  });

  test("failed first initialization shows retry and keeps other runs", async ({ page }) => {
    await startCompany(page, "Northstar");
    await reviewTool(page, /Next save fails/);
    await page.getByRole("link", { name: "Change company" }).click();
    await page.locator("article", { hasText: "Harbor" }).getByRole("link", { name: "Open demo" }).click();
    await expect(page.getByRole("alert").filter({ hasText: "Didn't save" })).toBeVisible();
    await btn(page, "Retry").click();
    await pickPersona(page, "Nora Santos");
    await page.goto("/demo/");
    await expect(page.locator("article", { hasText: "Northstar" })).toContainText("Run in progress");
  });

  test("persona picker works from the keyboard", async ({ page }) => {
    await page.goto("/demo/company/?company_key=harbor&scenario=harbor-account-queue");
    const leo = page.locator(".persona-btn").filter({ has: page.locator("b", { hasText: /^Leo Cruz$/ }) });
    await leo.focus();
    await page.keyboard.press("Enter");
    await page.waitForURL("**/home/");
    await expect(page.getByRole("heading", { level: 1, name: /, Leo\./ })).toBeVisible();
  });

  test("/app/ is a reserved boundary with no demo controls", async ({ page }) => {
    await startCompany(page, "Northstar");
    await page.goto("/app/");
    await expect(page.getByText("Organization sign-in isn't available yet")).toBeVisible();
    for (const name of ["Review tools", "Switch persona", "Start fresh demo"]) await expect(page.getByRole("button", { name })).toHaveCount(0);
    await expect(page.locator("body")).not.toContainText("Northstar");
    await expect(page.getByRole("textbox")).toHaveCount(0);
  });

  test("axe: company entry and fresh-start dialog", async ({ page }) => {
    await startCompany(page, "Acme");
    await page.goto("/demo/company/?company_key=acme&scenario=acme-platform-ops");
    await btn(page, "Start fresh demo").click();
    await page.waitForTimeout(400);
    const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
    expect(r.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id)).toEqual([]);
  });
});
