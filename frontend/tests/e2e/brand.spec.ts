import { createHash } from "node:crypto";
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { asPersona, startCompany } from "./helpers";

// docs/29-brand-identity.md: exact approved exports, no recolour/crop/redraw.
const APPROVED = {
  "/brand/workweave-horizontal-logo.png": "baabe4456458cc23f14b155c98d928251785f0cd736de3dc217462d128643049",
  "/brand/workweave-icon.png": "21c9146413e5da5706e1f47dcecb7357638586d71a29f8548a9609f805bec1db",
};

test.describe("Approved WorkWeave branding", () => {
  test("served assets are byte-identical to the approved exports", async ({ request }) => {
    for (const [path, sha] of Object.entries(APPROVED)) {
      const res = await request.get(path);
      expect(res.status()).toBe(200);
      expect(createHash("sha256").update(await res.body()).digest("hex"), path).toBe(sha);
    }
  });

  test("light surfaces: horizontal lockup and header icon at legible, unstretched sizes", async ({ page }) => {
    await page.goto("/demo/");
    const lockup = page.getByRole("img", { name: "WorkWeave: Weaving Knowledge Into Every Work" });
    await expect(lockup).toBeVisible();
    const lb = (await lockup.boundingBox())!;
    expect(lb.width).toBeGreaterThanOrEqual(120);
    expect(lb.width / lb.height).toBeCloseTo(2172 / 724, 1);
    const icon = page.locator("header img.brand-icon");
    await expect(icon).toBeVisible();
    const ib = (await icon.boundingBox())!;
    expect(ib.width).toBeGreaterThanOrEqual(24);
    expect(ib.width / ib.height).toBeCloseTo(693 / 347, 1);
    await expect(page.getByRole("link", { name: "WorkWeave" })).toBeVisible();
  });

  test("dark surfaces: no light plate; icon on the surface and a live-text wordmark in the hero", async ({ browser }) => {
    const ctx = await browser.newContext({ colorScheme: "dark" });
    const page = await ctx.newPage();
    await page.goto("/demo/");
    // The dark-lettered horizontal PNG is replaced by the approved icon plus live text.
    await expect(page.locator("img.lockup-light")).toBeHidden();
    const lockup = page.getByRole("img", { name: "WorkWeave: Weaving Knowledge Into Every Work" });
    await expect(lockup).toBeVisible();
    await expect(lockup.locator("img.lockup-dark-icon")).toBeVisible();
    await expect(page.locator(".lockup-dark-tagline")).toHaveText("Weaving Knowledge Into Every Work");
    const icon = page.locator("header img.brand-icon");
    await expect(icon).toBeVisible();
    // Nothing behind the artwork: it sits directly on the dark surface.
    for (const el of [icon, page.locator(".brand-lockup"), page.locator("header .brand-inner")]) {
      expect(await el.evaluate((e) => getComputedStyle(e).backgroundColor)).toBe("rgba(0, 0, 0, 0)");
    }
    await expect(page.getByRole("link", { name: "WorkWeave" })).toBeVisible();
    await ctx.close();
  });

  test("dark mode: primary button and persona hover stay dark-theme colours, not near-white", async ({ browser }) => {
    const ctx = await browser.newContext({ colorScheme: "dark" });
    const page = await ctx.newPage();
    await page.goto("/demo/");
    const lum = (c: string) => {
      const [r, g, b] = (c.match(/[\d.]+/g) ?? []).map(Number);
      return (0.2126 * r! + 0.7152 * g! + 0.0722 * b!) / 255;
    };
    const open = page.getByRole("link", { name: "Open demo" }).first();
    const rest = await open.evaluate((e) => getComputedStyle(e).backgroundColor);
    await open.hover();
    await page.waitForTimeout(250);
    const hover = await open.evaluate((e) => getComputedStyle(e).backgroundColor);
    expect(lum(hover)).toBeLessThan(lum(rest));
    await open.click();
    await page.waitForURL("**/demo/company/**");
    const persona = page.locator(".persona-btn").first();
    await persona.hover();
    await page.waitForTimeout(250);
    expect(lum(await persona.evaluate((e) => getComputedStyle(e).backgroundColor))).toBeLessThan(0.3);
    // The current persona in the switcher is marked selected (aria-pressed) without a light fill.
    await persona.click();
    await page.waitForURL("**/home/");
    await page.getByRole("button", { name: "Switch persona" }).click();
    const selected = page.getByRole("dialog", { name: "Switch persona" }).locator('.persona-btn[aria-pressed="true"]');
    await expect(selected).toHaveCount(1);
    expect(lum(await selected.evaluate((e) => getComputedStyle(e).backgroundColor))).toBeLessThan(0.3);
    await ctx.close();
  });

  test("keyboard focus uses the accessible olive focus ring", async ({ page }) => {
    await page.goto("/demo/");
    const link = page.getByRole("link", { name: "Open demo" }).first();
    await link.focus();
    const outline = await link.evaluate((el) => getComputedStyle(el).outlineColor);
    expect(outline).toBe("rgb(90, 122, 31)"); // #5A7A1F, 4.7:1 on cream
  });

  for (const [name, path, persona] of [
    ["catalog", "/demo/", ""],
    ["companion", "/companion/", "Alex Chen"],
    ["handover", "/handover/", "Alex Chen"],
    ["exit-kt", "/exit-kt/", "Pat Reyes"],
    ["inbox (empty state)", "/inbox/", "Sam Lim"],
  ] as const) {
    test(`dark-mode axe: no serious or critical violations on ${name}`, async ({ browser }) => {
      const ctx = await browser.newContext({ colorScheme: "dark", viewport: { width: 1360, height: 900 } });
      const page = await ctx.newPage();
      if (persona) {
        await startCompany(page, "Acme");
        await asPersona(page, persona);
      }
      await page.goto(path);
      await page.waitForLoadState("networkidle");
      await page.waitForTimeout(600);
      const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
      expect(r.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).slice(0, 3).join(", ")}`)).toEqual([]);
      await ctx.close();
    });
  }
});
