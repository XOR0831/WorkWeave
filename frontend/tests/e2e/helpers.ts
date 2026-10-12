import { expect, type Page } from "@playwright/test";

export const btn = (p: Page, name: string) => p.getByRole("button", { name, exact: true });

const FIRST_PERSONA = { Northstar: "Sam Kim", Acme: "Alex Chen", Harbor: "Nora Santos" } as const;
type Company = keyof typeof FIRST_PERSONA;

/** Demo entry (ADR-024): /demo/ → /demo/company/ → persona picker → home. */
export async function startCompany(p: Page, company: Company, persona: string = FIRST_PERSONA[company]) {
  await p.goto("/demo/");
  await p.locator("article", { hasText: company }).getByRole("link", { name: /Open demo|Resume or restart/ }).click();
  await p.waitForURL("**/demo/company/**");
  await pickPersona(p, persona);
}

export async function pickPersona(p: Page, persona: string) {
  await expect(p.getByRole("heading", { name: "Who do you want to be?" })).toBeVisible();
  await p.locator(".persona-btn b", { hasText: new RegExp(`^${persona}$`) }).click();
  await p.waitForURL("**/home/");
  // Home greets the persona by first name ("Good afternoon, Sam.") and names them in the sidebar.
  await expect(p.getByRole("heading", { level: 1, name: new RegExp(`, ${persona.split(" ")[0]}\\.$`) })).toBeVisible();
  await expect(p.locator(".context")).toContainText(persona);
}

export async function asPersona(p: Page, fullName: string) {
  await btn(p, "Switch persona").click();
  await p.getByRole("dialog", { name: "Switch persona" }).locator(".persona-btn b", { hasText: new RegExp(`^${fullName}$`) }).click();
  await expect(p.getByRole("dialog", { name: "Switch persona" })).toBeHidden();
  await expect(p.locator(".context")).toContainText(fullName);
  await p.waitForURL("**/home/"); // switching always starts the new persona from Home
}

/** Click a preview-script chip, opening "More prompts" first when the chip is collapsed. */
export async function chip(p: Page, label: string) {
  const target = btn(p, label);
  await p.locator(".script-chips").first().waitFor();
  if (!(await target.isVisible())) {
    const more = p.getByRole("button", { name: /^More prompts/ });
    if (await more.count()) await more.first().click();
  }
  await target.click();
}

export async function reviewTool(p: Page, label: RegExp) {
  await p.getByRole("button", { name: "Review tools" }).click();
  await p.getByLabel(label).check();
  await p.getByRole("button", { name: "Close Review tools" }).click();
}
