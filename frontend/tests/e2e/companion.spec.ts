import { expect, test } from "@playwright/test";
import { asPersona, btn, chip, startCompany } from "./helpers";

test.describe("AI Work Companion (screens/work-companion)", () => {
  test("chat alone changes the canvas; no view dropdowns or tabs; transcript persists", async ({ page }) => {
    await startCompany(page, "Acme");
    await page.goto("/companion/");
    const canvasTitle = page.locator("#h-canvas");
    await expect(canvasTitle).toHaveText("Work briefing");
    await expect(page.getByRole("tablist")).toHaveCount(0);
    await expect(page.getByRole("combobox")).toHaveCount(0);

    await chip(page, "Focus on tickets");
    await expect(canvasTitle).toHaveText("Incidents and activities");
    await chip(page, "Only blocked tickets");
    await expect(canvasTitle).toContainText("blocked only");
    await chip(page, "Show INC-203");
    await expect(canvasTitle).toHaveText("Item detail");
    await chip(page, "Ask how to troubleshoot it");
    await expect(canvasTitle).toHaveText("Guidance from approved sources");
    await expect(page.getByText("The approved sources don't answer this")).toBeVisible();

    const log = page.getByRole("log", { name: "Work Companion conversation" });
    await expect(log).toContainText("I want to focus on tickets.");
    await expect(log).toContainText("How do I troubleshoot that payment timeout?");
  });

  test("invalid ui_action and free text keep the current canvas", async ({ page }) => {
    await startCompany(page, "Acme");
    await page.goto("/companion/");
    await chip(page, "Focus on tickets");
    const title = page.locator("#h-canvas");
    await expect(title).toHaveText("Incidents and activities");
    await chip(page, "Preview: invalid ui_action");
    await expect(page.getByRole("log", { name: "Work Companion conversation" })).toContainText("Rejected an unsupported view action");
    await expect(title).toHaveText("Incidents and activities");
    await page.getByLabel("Message the Work Companion").fill("show the briefing");
    await btn(page, "Send").click();
    await expect(page.getByRole("log", { name: "Work Companion conversation" })).toContainText("Not interpreted");
    await expect(title).toHaveText("Incidents and activities");
    await chip(page, "Ask about \"that one\"");
    await expect(title).toHaveText("Incidents and activities");
  });

  test("delegation: edit keeps original recommendation, nothing assigned until explicit confirm", async ({ page }) => {
    await startCompany(page, "Acme");
    await page.goto("/companion/");
    await chip(page, "Recommend assignments");
    await expect(btn(page, "Review and confirm")).toBeVisible();
    await chip(page, "Reassign INC-203 and ACT-101");
    await expect(page.getByText("Updated: INC-203 → Maria")).toBeVisible();
    const table = page.getByRole("table");
    await expect(table.getByRole("row", { name: /INC-203/ })).toContainText("John Tan");
    await expect(table.getByRole("row", { name: /INC-203/ })).toContainText("(edited)");
    // Not yet assigned.
    await asPersona(page, "Maria Garcia");
    await page.goto("/inbox/");
    await expect(page.getByText("No notifications")).toBeVisible();
    await asPersona(page, "Alex Chen");
    await page.goto("/companion/");
    await chip(page, "Recommend assignments");
    await btn(page, "Review and confirm").click();
    await btn(page, "Confirm assignments").click();
    await expect(page.getByText("Assignments confirmed")).toBeVisible();
    await asPersona(page, "Maria Garcia");
    await page.goto("/inbox/");
    await expect(page.getByText("You've been assigned INC-203")).toBeVisible();
  });

  test("member report is a report; it waits for the ticket system", async ({ page }) => {
    await startCompany(page, "Acme");
    await page.goto("/companion/");
    await chip(page, "Recommend assignments");
    await btn(page, "Review and confirm").click();
    await btn(page, "Confirm assignments").click();
    await asPersona(page, "John Tan");
    await page.goto("/companion/");
    // Members never see proposal views.
    await expect(btn(page, "Recommend assignments")).toHaveCount(0);
    await chip(page, "Report INC-203 done");
    const dlg = page.getByRole("dialog", { name: "Report on INC-203" });
    await expect(dlg).toBeVisible();
    await dlg.getByRole("button", { name: "Submit report" }).click();
    await expect(page.getByRole("log", { name: "Work Companion conversation" })).toContainText("until the ticket system shows it resolved");
    await asPersona(page, "Alex Chen");
    await page.goto("/companion/");
    await chip(page, "Show INC-203");
    await expect(page.getByText("Reported done · waiting for the ticket system").first()).toBeVisible();
    await expect(btn(page, "Review report")).toHaveCount(0); // leads monitor; nobody validates
    await expect(page.locator(".panel").filter({ hasText: "Item detail" }).locator(".badge").first()).toHaveText("In progress");
  });

  test("capture requires consent and stays private until submitted", async ({ page }) => {
    await startCompany(page, "Northstar");
    await asPersona(page, "Alex Rivera");
    await page.goto("/companion/");
    await btn(page, "Capture knowledge").click();
    const dlg = page.getByRole("dialog", { name: "Capture reusable knowledge" });
    await expect(dlg.getByRole("button", { name: "Start note" })).toBeDisabled();
    await dlg.getByLabel(/I understand/).check();
    await dlg.getByRole("button", { name: "Start note" }).click();
    await dlg.getByLabel("Explanation").fill("When evidence is missing I name the ticket and source version.");
    await dlg.getByLabel("Who should see it after review").selectOption("TEAM");
    await dlg.getByRole("button", { name: "Save private draft" }).click();
    await dlg.getByRole("button", { name: "Submit for review" }).click();
    await expect(dlg.getByText("Pending review")).toBeVisible();
    await dlg.getByRole("button", { name: "Close Capture reusable knowledge" }).click();
    await asPersona(page, "Morgan Lee");
    await page.goto("/reviews/");
    await expect(page.getByText("When evidence is missing")).toBeVisible();
    await btn(page, "Approve note").click();
    await expect(page.getByText("Nothing is waiting for review")).toBeVisible();
  });
});
