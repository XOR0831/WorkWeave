import { expect, test } from "@playwright/test";
import { startCompany } from "./helpers";

/** Optional page tours (owner, 2026-10-11): offered once per module, skippable, replayable. */
test.describe("Optional page tours", () => {
  test("the first visit offers a tour that walks through the page; the answer is remembered", async ({ page }) => {
    await startCompany(page, "Acme");
    await page.goto("/companion/");
    const offer = page.getByTestId("tour-offer");
    await expect(offer).toContainText("New to Work Companion?");
    await offer.getByRole("button", { name: "Take the tour" }).click();

    const card = page.getByRole("dialog");
    await expect(card).toContainText(/Work Companion tour · 1 of \d+/);
    await expect(card.getByRole("heading", { name: "Talk about your work" })).toBeFocused();
    await card.getByRole("button", { name: "Next" }).click();
    await expect(card).toContainText("2 of");
    await card.getByRole("button", { name: "Back" }).click();
    await expect(card).toContainText("1 of");
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);

    await page.reload();
    await expect(page.locator("#h-canvas")).toBeVisible();
    await expect(page.getByTestId("tour-offer")).toHaveCount(0); // answered once for this run

    await page.getByRole("button", { name: "Page tour" }).click(); // replay any time
    await expect(page.getByRole("dialog")).toContainText("Work Companion tour · 1 of");
    for (let i = 0; i < 10 && (await page.getByRole("button", { name: "Next" }).count()); i++) await page.getByRole("button", { name: "Next" }).click();
    await page.getByRole("button", { name: "Finish" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
  });

  test("skipping hides the offer for that module only; a fresh demo offers it again", async ({ page, context }) => {
    await startCompany(page, "Acme");
    await page.goto("/home/");
    await page.getByTestId("tour-offer").getByRole("button", { name: "Skip tour" }).click();
    await expect(page.getByTestId("tour-offer")).toHaveCount(0);
    await page.reload();
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByTestId("tour-offer")).toHaveCount(0);
    await page.goto("/reviews/");
    await expect(page.getByTestId("tour-offer")).toContainText("New to Reviews?");

    const tab = await context.newPage(); // the preview keeps a run per tab: a new tab is a fresh demo run
    await startCompany(tab, "Acme");
    await expect(tab.getByTestId("tour-offer")).toContainText("New to Home?"); // same browser storage, new run
  });
});

test("the Home tour includes the demo's tools", async ({ page }) => {
  await startCompany(page, "Acme");
  await page.getByTestId("tour-offer").getByRole("button", { name: "Take the tour" }).click();
  const card = page.getByRole("dialog");
  for (let i = 0; i < 12 && !(await card.getByRole("heading", { name: "Review tools" }).count()); i++) await card.getByRole("button", { name: "Next" }).click();
  await expect(card.getByRole("heading", { name: "Review tools" })).toBeVisible(); // the preview's tools; "Demo tools" on the API
  await expect(card).toContainText("Nothing leaves this browser tab");
});
