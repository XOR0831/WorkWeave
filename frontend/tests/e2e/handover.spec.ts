import { expect, test } from "@playwright/test";
import { asPersona, btn, startCompany } from "./helpers";

test.describe("Intelligent Shift Handover (screens/smart-handover)", () => {
  test("lead publishes directly; required sections guard; no transfer control", async ({ page }) => {
    await startCompany(page, "Acme");
    await page.goto("/handover/");
    await expect(page.getByRole("heading", { name: "Afternoon → Evening handover" })).toBeVisible();
    await expect(page.getByRole("button", { name: /transfer/i })).toHaveCount(0); // no responsibility transfer here
    await expect(btn(page, "Confirm transfer")).toHaveCount(0);

    // Empty a required section → publish blocked.
    await btn(page, "Edit Shift Summary").click();
    await page.getByRole("textbox", { name: "Shift Summary" }).fill("");
    await btn(page, "Save section").click();
    await btn(page, "Review and publish").click();
    const dlg = page.getByRole("dialog", { name: "Review and publish" });
    await expect(dlg).toContainText("No second reviewer is needed");
    await expect(dlg).toContainText("Add content or a declaration for: Shift Summary");
    await dlg.getByLabel(/reviewed the sections/).check();
    await expect(dlg.getByRole("button", { name: "Publish handover" })).toBeDisabled();
    await dlg.getByRole("button", { name: "Close Review and publish" }).click();

    // Explicit unknown declaration satisfies the requirement.
    await btn(page, "Edit Shift Summary").click();
    await page.getByLabel("Or declare").first().selectOption("UNKNOWN_WITH_FOLLOW_UP");
    await page.getByLabel("Declaration reason").fill("Summary pending; follow up at shift start");
    await btn(page, "Save section").click();
    await btn(page, "Review and publish").click();
    await dlg.getByLabel(/reviewed the sections/).check();
    await dlg.getByRole("button", { name: "Publish handover" }).click();
    await expect(page.getByText("Published #2")).toBeVisible();
  });

  test("validated completion → COMPLETED/PENDING; dispute reopens; stale cycle rejected; snapshot immutable", async ({ page }) => {
    await startCompany(page, "Acme");
    await page.goto("/handover/");
    await btn(page, "Review change").first().click();
    await btn(page, "Validate completion").click();
    const item = page.locator("section[aria-labelledby=\"h-ledger\"] .list-item", { hasText: "HI-144" });
    await expect(item).toContainText("Completed");
    await expect(item).toContainText("Pending");

    // Morning publication #1 still shows the original snapshot status.
    await page.locator("section[aria-labelledby=\"h-history\"] .list-item", { hasText: "#1" }).getByRole("button", { name: "View snapshot" }).click();
    const snap = page.getByRole("dialog", { name: "Publication #1 snapshot" });
    await expect(snap.getByRole("row", { name: /HI-144/ })).toContainText("In progress");
    await expect(snap.getByRole("row", { name: /HI-144/ })).toContainText("Now: completed");
    await snap.getByRole("button", { name: "Close Publication #1 snapshot" }).click();

    await btn(page, "Dispute").click();
    await page.getByLabel(/What's disputed/).fill("Transactions still timing out in one region");
    await btn(page, "Dispute and reopen").click();
    await expect(item).toContainText("Disputed");
    await expect(item).toContainText("In progress");

    await btn(page, "Confirm completion again").click();
    await expect(item).toContainText("Completed");
    await btn(page, "Try acknowledging this older cycle").click();
    await expect(page.getByRole("alert").filter({ hasText: "older completion cycle" })).toBeVisible();
    await btn(page, "Acknowledge completion").click();
    await expect(item).toContainText("Closed");
  });

  test("only shift leads: members don't see Shift Handover; the incoming lead confirms receipt", async ({ page }) => {
    await startCompany(page, "Acme");
    await page.goto("/handover/");
    await btn(page, "Review and publish").click();
    await page.getByRole("dialog", { name: "Review and publish" }).getByLabel(/reviewed the sections/).check();
    await btn(page, "Publish handover").click();
    await expect(page.getByText("Published #2")).toBeVisible();
    await asPersona(page, "Maria Garcia"); // a member
    await expect(page.getByRole("navigation", { name: "Modules" }).getByRole("link", { name: "Shift Handover" })).toHaveCount(0);
    await page.goto("/handover/");
    await expect(page.getByRole("heading", { name: "Shift Handover is for shift leads" })).toBeVisible();
    await asPersona(page, "Aisha Rahman"); // leads the receiving Evening shift
    await page.goto("/handover/");
    await expect(btn(page, "Review and publish")).toHaveCount(0);
    await btn(page, "Confirm receipt of #2").click();
    await expect(page.getByText("Receipt confirmed")).toBeVisible();
  });

  test("three shifts: the same item appears in Morning, Afternoon and Evening publications", async ({ page }) => {
    await startCompany(page, "Northstar");
    await asPersona(page, "Alex Rivera");
    await page.goto("/handover/");
    await btn(page, "Review and publish").click();
    await page.getByRole("dialog", { name: "Review and publish" }).getByLabel(/reviewed the sections/).check();
    await btn(page, "Publish handover").click();
    await expect(page.getByText("Published #2")).toBeVisible();
    await page.getByRole("button", { name: "Review tools" }).click();
    await btn(page, "Advance to next shift").click();
    await page.getByRole("button", { name: "Close Review tools" }).click();
    await asPersona(page, "Dana Brooks"); // a switch always starts from Home
    await page.goto("/handover/");
    await expect(page.getByRole("heading", { name: "Evening → Morning handover" })).toBeVisible();
    await btn(page, "Review and publish").click();
    await page.getByRole("dialog", { name: "Review and publish" }).getByLabel(/reviewed the sections/).check();
    await btn(page, "Publish handover").click();
    await expect(page.getByText("Published #3")).toBeVisible();
    await page.locator("section[aria-labelledby=\"h-ledger\"] .list-item", { hasText: "HI-111" }).getByRole("button", { name: "Item history" }).click();
    const hist = page.getByRole("dialog", { name: "HI-111 history" });
    await expect(hist).toContainText("Included in publication #2");
    await expect(hist).toContainText("Included in publication #3");
  });

  test("change preview: the lead edits the note before accepting; the affected section is highlighted", async ({ page }) => {
    await startCompany(page, "Northstar", "Alex Rivera");
    await page.goto("/handover/");
    const card = page.locator(".suggestion-card", { hasText: "Upcoming team briefing" });
    await card.getByRole("button", { name: "Review change" }).click();
    const dlg = page.getByRole("dialog", { name: "Review suggested change" });
    await dlg.getByLabel("Proposed note (you can edit before accepting)").fill("Team briefing at shift start; time still to be confirmed.");
    await dlg.getByRole("button", { name: "Accept into draft" }).click();
    const section = page.locator(".doc-section", { hasText: "Scheduled Activities" });
    await expect(section).toContainText("Just updated");
    await expect(section).toContainText("Team briefing at shift start; time still to be confirmed.");
  });

  test("configure sections creates a new template version; earlier publications keep theirs", async ({ page }) => {
    await startCompany(page, "Northstar", "Alex Rivera");
    await page.goto("/handover/");
    await btn(page, "Configure sections").click();
    const drawer = page.getByRole("dialog", { name: "Configure sections" });
    await expect(drawer).toContainText("Saving creates template v2");
    await drawer.locator(".config-row", { hasText: "Incidents / Issues" }).getByRole("switch").check();
    await drawer.getByLabel("Add an optional section").fill("Safety observations");
    await drawer.getByRole("button", { name: "Add section" }).click();
    await drawer.getByRole("button", { name: "Save template" }).click();
    await expect(page.locator("section[aria-labelledby=\"h-hand\"]")).toContainText("template v2");
    await expect(page.locator(".doc-section", { hasText: "Incidents / Issues" })).toContainText("Required");
    await expect(btn(page, "+ Safety observations")).toBeVisible();

    // The newly required section now guards publishing.
    await btn(page, "Review and publish").click();
    const review = page.getByRole("dialog", { name: "Review and publish" });
    await expect(review).toContainText("Add content or a declaration for: Incidents / Issues");
    await review.getByRole("button", { name: "Close Review and publish" }).click();

    // Publication #1 still records template v1.
    await expect(page.locator("section[aria-labelledby=\"h-history\"] .list-item", { hasText: "#1" })).toContainText("Template v1");
  });
});
