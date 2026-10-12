import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { asPersona, startCompany } from "./helpers";

test.describe("Shell, routing and accessibility", () => {
  test("preview label is persistent; deep link without a session explains what to do", async ({ page }) => {
    await page.goto("/companion/");
    await expect(page.getByRole("note", { name: "Preview notice" })).toContainText("UI preview with simulated data");
    await expect(page.getByText("No preview workspace is open")).toBeVisible();
    const res = await page.goto("/does-not-exist/");
    expect(res?.status()).toBe(404);
    await expect(page.getByText("This page doesn't exist")).toBeVisible();
  });

  test("direct links and refresh work on the static export", async ({ page }) => {
    await startCompany(page, "Acme");
    for (const path of ["/onboarding/", "/companion/", "/handover/", "/exit-kt/?area=findings", "/reviews/", "/inbox/", "/memory/"]) {
      const res = await page.goto(path);
      expect(res?.status(), path).toBe(200);
      await page.reload();
      await expect(page.getByRole("note", { name: "Preview notice" })).toBeVisible();
    }
  });

  test("session expiry shows a clear state", async ({ page }) => {
    await startCompany(page, "Northstar");
    await page.getByRole("button", { name: "Review tools" }).click();
    await page.getByLabel(/Expire session/).check();
    await page.getByRole("button", { name: "Close Review tools" }).click();
    // The next request (the page refreshing its data) reports expiry; no reload, which would reset the mode.
    await expect(page.getByText(/Your preview session has ended|No preview workspace is open/).first()).toBeVisible();
  });

  test("Harbor uses its own terminology, not manufacturing nouns", async ({ page }) => {
    await startCompany(page, "Harbor");
    await expect(page.getByRole("heading", { level: 1, name: /, Nora\./ })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Your cases" })).toBeVisible();
    await asPersona(page, "Leo Cruz");
    await page.goto("/companion/");
    await page.getByRole("button", { name: "Focus on cases", exact: true }).click();
    await expect(page.locator("#h-canvas")).toHaveText("Cases");
    await expect(page.locator("main")).toContainText("CASE-104");
    await expect(page.locator("main")).not.toContainText("Machine #14");
    await page.goto("/handover/");
    await expect(page.getByText("Support queue shift handover")).toBeVisible();
  });

  const pages: [string, string, string][] = [
    ["catalog", "/demo/", ""],
    ["app-boundary", "/app/", ""],
    ["home", "/home/", "Alex Chen"],
    ["onboarding", "/onboarding/", "Sam Lim"],
    ["companion", "/companion/", "Alex Chen"],
    ["handover", "/handover/", "Alex Chen"],
    ["exit-kt", "/exit-kt/", "Pat Reyes"],
    ["reviews", "/reviews/", "Morgan Lee"],
    ["inbox", "/inbox/", "John Tan"],
    ["memory", "/memory/", "John Tan"],
    ["curricula", "/curricula/", "Morgan Lee"],
  ];
  for (const [name, path, persona] of pages) {
    test(`axe: no serious or critical violations on ${name}`, async ({ page }) => {
      if (persona) {
        await startCompany(page, "Acme");
        await asPersona(page, persona);
      }
      await page.goto(path);
      await page.waitForLoadState("networkidle");
      await page.waitForTimeout(600);
      const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
      const bad = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
      expect(bad.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).slice(0, 3).join(", ")}`)).toEqual([]);
    });
  }

  test("dialogs close with Escape and return focus", async ({ page }) => {
    await startCompany(page, "Northstar");
    const trigger = page.getByRole("button", { name: "Switch persona" });
    await trigger.click();
    await expect(page.getByRole("dialog", { name: "Switch persona" })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog", { name: "Switch persona" })).toBeHidden();
    await expect(trigger).toBeFocused();
  });
});
