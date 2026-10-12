import { expect, test } from "@playwright/test";
import { asPersona, chip, startCompany } from "./helpers";

// Runs in the "mobile" project (Pixel 7 viewport).
test.describe("Narrow screens", () => {
  for (const [path, persona, company] of [
    ["/", "", "Acme"],
    ["/onboarding/session/", "Sam Kim", "Northstar"],
    ["/companion/", "Alex Chen", "Acme"],
    ["/handover/", "Alex Chen", "Acme"],
    ["/exit-kt/", "Pat Reyes", "Acme"],
  ] as const) {
    test(`no horizontal page scroll on ${path}`, async ({ page }) => {
      if (persona) {
        await startCompany(page, company);
        await asPersona(page, persona);
        if (path === "/onboarding/session/") {
          await page.goto("/onboarding/");
          await page.getByRole("button", { name: "Start conversation" }).click();
        }
      }
      await page.goto(path);
      await page.waitForTimeout(700);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow).toBeLessThanOrEqual(1);
    });
  }

  test("companion stacks the conversation above the work area", async ({ page }) => {
    await startCompany(page, "Acme");
    await page.goto("/companion/");
    const chat = await page.getByRole("complementary", { name: "Conversation" }).boundingBox();
    const dash = await page.locator("#h-dash").boundingBox();
    expect(chat && dash && chat.y < dash.y).toBeTruthy();
  });
});

test("mobile: brand lockup stays above the 120 px minimum and inside the viewport", async ({ page }) => {
  await page.goto("/demo/");
  const box = (await page.getByRole("img", { name: /WorkWeave: Weaving/ }).boundingBox())!;
  const vw = page.viewportSize()!.width;
  expect(box.width).toBeGreaterThanOrEqual(120);
  expect(box.x + box.width).toBeLessThanOrEqual(vw);
});

test("mobile tutor: the reference opens as a bottom sheet, not stacked under the conversation", async ({ page }) => {
  await startCompany(page, "Northstar");
  await page.goto("/onboarding/");
  await page.getByRole("button", { name: "Start conversation" }).click();
  await page.waitForURL("**/onboarding/session/");
  await expect(page.getByRole("heading", { name: "Reference for this explanation", exact: true })).toBeHidden();
  await chip(page, "Answer the opening question");
  await page.getByRole("button", { name: "View reference" }).click();
  const sheet = page.getByRole("dialog", { name: "Reference for this explanation" });
  await expect(sheet).toContainText("SOP-001 v3.4");
  // The composer stays reachable: the transcript scrolls inside its panel.
  const log = await page.getByRole("log", { name: "Tutor conversation" }).boundingBox();
  expect(log!.height).toBeLessThanOrEqual(page.viewportSize()!.height * 0.56 + 1);
});

test("mobile curricula: outline and mappings fit without horizontal scroll", async ({ page }) => {
  await startCompany(page, "Northstar", "Morgan Lee");
  await page.goto("/curricula/");
  await page.locator("article", { hasText: "v1.1" }).getByRole("link", { name: "Open curriculum" }).click();
  await page.getByRole("button", { name: "Upload document" }).first().click();
  await page.getByRole("button", { name: /Use synthetic sample/ }).click();
  await page.getByRole("button", { name: "Stage document" }).click();
  await page.getByRole("button", { name: "Generate outline" }).click();
  await expect(page.getByText("2. Reference aids")).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
