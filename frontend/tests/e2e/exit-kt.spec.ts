import { expect, test, type Page } from "@playwright/test";
import { asPersona, btn, startCompany } from "./helpers";

const area = (p: Page, name: string) => p.getByRole("tab", { name }).click();

test.describe("Exit Knowledge Transfer (screens/exit-knowledge-transfer)", () => {
  test("full Northstar path: artifact review → promotion → package → receipt → guarded transfer → completeness", async ({ page }) => {
    await startCompany(page, "Northstar");
    await asPersona(page, "Alex Rivera");
    await page.goto("/exit-kt/");
    await expect(page.getByRole("tablist", { name: "Exit KT areas" })).toBeVisible();
    for (const t of ["Knowledge Transfer", "Responsibility Transfer", "AI Findings", "KT Completeness"]) await expect(page.getByRole("tab", { name: t })).toBeVisible();

    // Discovery is honestly unavailable.
    await btn(page, "Run discovery").click();
    await expect(page.getByRole("alert").filter({ hasText: "isn't connected" })).toBeVisible();

    // Employee submits exact revision of the private draft.
    await page.locator(".list-item", { hasText: "Evidence-based escalation practice" }).getByRole("button", { name: "Open artifact" }).click();
    const art = page.getByRole("dialog", { name: "Requesting evidence-based clarification" });
    await expect(art).toContainText("Private draft");
    await expect(art.getByRole("button", { name: /Approve/ })).toHaveCount(0); // no self-approval
    await art.getByRole("button", { name: "Submit v1 for review" }).click();
    await expect(art).toContainText("Pending review");
    await art.getByRole("button", { name: "Close Requesting evidence-based clarification" }).click();

    // Responsibility transfer is blocked before any package exists.
    await area(page, "Responsibility Transfer");
    await expect(page.getByLabel("Why ownership can't transfer yet").first()).toContainText("No approved successor package");

    // Reviewer approves and promotes the exact revision.
    await asPersona(page, "Morgan Lee");
    await page.goto("/reviews/");
    await expect(page.getByText("Requesting evidence-based clarification")).toBeVisible();
    await page.getByRole("link", { name: "Review in Exit KT" }).click();
    await page.locator(".list-item", { hasText: "Evidence-based escalation practice" }).getByRole("button", { name: "Open artifact" }).click();
    await btn(page, "Approve v1").click();
    await btn(page, "Promote v1 to a new document version").click();
    await expect(page.getByRole("dialog")).toContainText("No existing SOP was overwritten");
    await expect(page.getByRole("dialog")).toContainText("Pending");
    await page.getByRole("button", { name: "Close Requesting evidence-based clarification" }).click();

    // Employee assembles and submits the package.
    await asPersona(page, "Alex Rivera");
    await page.goto("/exit-kt/?area=responsibility");
    await btn(page, "Assemble from approved knowledge").click();
    await expect(page.getByText(/Requesting evidence-based clarification \(KT-/)).toBeVisible();
    await btn(page, "Submit package for review").click();

    await asPersona(page, "Morgan Lee");
    await page.goto("/exit-kt/?area=responsibility");
    await btn(page, "Approve package").click();
    await expect(page.getByText("Waiting for Jamie Chen to confirm receipt.")).toBeVisible();

    // Successor reads and receives; receipt does not transfer.
    await asPersona(page, "Jamie Chen");
    await page.goto("/exit-kt/");
    await expect(page.getByText("Successor briefing from Alex Rivera")).toBeVisible();
    await expect(page.getByRole("tablist")).toHaveCount(0);
    await btn(page, "What's still open on Machine #14?").click();
    await expect(page.getByRole("log", { name: "Package questions" })).toContainText("cause is unknown");
    await btn(page, "Confirm receipt of this version").click();
    await expect(page.getByText("Receipt confirmed")).toBeVisible();

    // Manager: effective time still in the future blocks the transfer.
    await asPersona(page, "Morgan Lee");
    await page.goto("/exit-kt/?area=responsibility");
    const resp = page.locator("section[aria-labelledby=\"h-resp\"] .list-item", { hasText: "Machine #14 maintenance responsibility" });
    await expect(resp.getByLabel("Why ownership can't transfer yet")).toContainText("Effective time hasn't been reached");
    await resp.getByRole("button", { name: "Review transfer" }).click();
    await expect(page.getByRole("dialog", { name: "Confirm responsibility transfer" }).getByRole("button", { name: "Confirm transfer" })).toBeDisabled();
    await page.getByRole("button", { name: "Close Confirm responsibility transfer" }).click();
    await resp.getByRole("button", { name: "Review and set to now" }).click();
    await expect(resp).toContainText("All transfer conditions are met");
    await resp.getByRole("button", { name: "Review transfer" }).click();
    await page.getByRole("dialog", { name: "Confirm responsibility transfer" }).getByRole("button", { name: "Confirm transfer" }).click();
    await expect(resp).toContainText("Transferred");
    await expect(resp).toContainText("Jamie Chen (ownership revision 2)");

    // Completeness resolves only with reviewed evidence; open work stays open.
    await area(page, "KT Completeness");
    await btn(page, "Complete case").click();
    await expect(page.getByRole("alert").filter({ hasText: "Required checklist items are still open" })).toBeVisible();
    const items = page.locator(".list-item");
    const pick = async (n: number, text: string) => {
      const sel = items.nth(n).getByRole("combobox");
      const value = await sel.locator("option", { hasText: text }).getAttribute("value");
      await sel.selectOption(value!);
    };
    await pick(0, "promoted as");
    await items.nth(0).getByRole("button", { name: "Resolve with evidence" }).click();
    await pick(1, "transferred to Jamie Chen");
    await items.nth(1).getByRole("button", { name: "Resolve with evidence" }).click();
    await expect(page.getByText("Ticket #829 stays open")).toBeVisible();
    await btn(page, "Complete case").click();
    await expect(btn(page, "Case complete")).toBeVisible();
  });

  test("targeted interview needs consent; drafting is unavailable; manual path works", async ({ page }) => {
    await startCompany(page, "Acme");
    await asPersona(page, "Pat Reyes");
    await page.goto("/exit-kt/");
    await expect(page.getByText(/Departure, final working day in 14 days/)).toBeVisible();
    await page.locator(".list-item", { hasText: "Certificate renewal verification" }).getByRole("button", { name: "Start targeted interview" }).click();
    const d = page.getByRole("dialog", { name: /Targeted interview/ });
    await expect(d.getByRole("button", { name: "Start interview" })).toBeDisabled();
    await d.getByLabel(/I understand/).check();
    await d.getByRole("button", { name: "Start interview" }).click();
    await expect(d.getByRole("log", { name: "Interview" })).toContainText("lists issuance but not verification");
    await d.getByRole("button", { name: "Describe your checks", exact: true }).click();
    await expect(d.getByRole("log", { name: "Interview" })).toContainText("old certificate");
    await d.getByRole("button", { name: "Draft artifact from interview" }).click();
    await expect(d.getByRole("alert").filter({ hasText: "Write the artifact manually" })).toBeVisible();
    await d.getByRole("button", { name: "Write artifact manually" }).click();
    const w = page.getByRole("dialog", { name: "Write a KT artifact" });
    await w.getByLabel("Content").fill("1. Check expiry on each endpoint.\n2. Confirm vendor portal.\nUnknown: alerting thresholds.");
    await w.getByRole("button", { name: "Save private draft" }).click();
    await expect(page.locator(".list-item", { hasText: "Certificate renewal verification" })).toContainText("Draft created");
  });

  test("departure requires a final working date; role transition doesn't", async ({ page }) => {
    await startCompany(page, "Northstar");
    await asPersona(page, "Morgan Lee");
    await page.goto("/exit-kt/");
    await btn(page, "New case").click();
    const d = page.getByRole("dialog", { name: "Open a knowledge-transfer case" });
    await d.getByLabel("Employee").selectOption({ label: "Jamie Chen" });
    await d.getByLabel(/Departure/).check();
    await d.getByRole("button", { name: "Open case" }).click();
    await expect(d.getByRole("alert").filter({ hasText: "needs a final working date" })).toBeVisible();
    await d.getByLabel(/Role transition/).check();
    await d.getByRole("button", { name: "Open case" }).click();
    await expect(d).toContainText("Case opened in discovery");
  });

  test("people outside the case are denied", async ({ page }) => {
    await startCompany(page, "Northstar");
    await page.goto("/exit-kt/");
    await expect(page.getByText("You aren't part of a knowledge-transfer case")).toBeVisible();
  });
});
